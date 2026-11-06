import argparse
import base64
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .security import safe_env
from .service import KIT, TaskService
from .state import atomic_json
from .web import PORT, WebApplication
from .projects import project_id


RELOAD = b'''<aside id="tw-preview" style="position:fixed;bottom:8px;right:8px;z-index:2147483647;background:#172033;color:white;padding:8px 12px;border-radius:8px;font:12px system-ui">Preview</aside><script>(()=>{let revision=null;setInterval(async()=>{try{const r=await fetch('/__preview/status');const s=await r.json();document.getElementById('tw-preview').textContent=s.message;if(revision&&s.revision&&revision!==s.revision)location.reload();revision=s.revision}catch{}},1500)})();</script>'''


class Preview:
    def __init__(self, root, ident, snapshot=False):
        self.root = Path(root).resolve()
        self.ident = ident
        self.port = 48000 + (int(project_id(self.root), 16) + ident) % 15000
        if type(ident) is not int or not 1 <= ident <= 17000:
            raise ValueError('Неверный номер задачи')
        service = TaskService(self.root)
        try:
            task = service.store.get(ident)
            self.folder = service.store.folder(ident)
            self.workspace = Path(task['data']['workspace'])
            if self.workspace != self.folder / 'workspace' or self.workspace.is_symlink():
                raise ValueError('Недопустимая рабочая копия')
            self.runtime = task['data'].get('frontend_toolchain')
            if self.runtime != 'next-ui':
                if not snapshot and (not (self.workspace / 'index.html').is_file() or (self.workspace / 'index.html').is_symlink()):
                    raise ValueError('Для проекта ещё не подготовлен поддерживаемый preview runtime')
                self.runtime = 'static'
            self.config = json.loads((service.store.home / 'config.json').read_text())
        finally:
            service.close()
        self.home = self.folder / 'live-preview'
        if self.home.is_symlink():
            raise ValueError('Состояние preview заменено ссылкой')
        self.home.mkdir(exist_ok=True)
        record = self.home / 'server.json'
        if record.is_symlink():
            raise ValueError('Запись preview заменена ссылкой')
        if record.is_file():
            data = json.loads(record.read_text())
            port = data.get('port')
            if data.get('task') != ident or type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError('Некорректная запись preview')
            self.port = port
        self.guard = threading.Lock()
        self.stop = threading.Event()
        self.state = {'task': ident, 'project_id': project_id(self.root), 'revision': None, 'building': False, 'message': 'Подготовка preview'}
        self.app = None

    def publish(self, receipt, verify_workspace=True):
        from .node import source_digest
        data = json.loads(receipt.read_text())
        app = WebApplication(self.root, 'preview', data['export'], receipt)
        app.static('/')
        with self.guard:
            self.app = app
            self.state.update(revision=data['source_digest'], building=False,
                message=f'TASK-{self.ident:03} · предпросмотр · изменения до приёмки',
                current=verify_workspace and data['source_digest'] == source_digest(self.workspace))

    def rejected(self):
        service = TaskService(self.root)
        try:
            rejected = service.store.get(self.ident)['state'] == 'rejected'
        finally:
            service.close()
        if rejected:
            with self.guard:
                self.app = None
                self.state.update(revision='rejected', building=False, current=False,
                    message='Результат отклонён · основная версия проекта сохранена')
        return rejected

    def build_loop(self):
        from .node import check, source_digest
        receipt = self.folder / 'frontend-receipt.json'
        if receipt.is_file() and not receipt.is_symlink():
            try:
                self.publish(receipt)
            except (OSError, ValueError, KeyError, RuntimeError):
                pass
        previous = None
        stable = None
        attempted = None
        while not self.stop.wait(2):
            try:
                if self.rejected():
                    continue
                digest = source_digest(self.workspace)
                if digest != previous:
                    previous, stable = digest, time.monotonic()
                    with self.guard:
                        self.state['current'] = digest == self.state['revision']
                    continue
                with self.guard:
                    published = self.state['revision']
                if digest in (published, attempted) or time.monotonic() - stable < 2:
                    continue
                attempted = digest
                with self.guard:
                    self.state.update(building=True, message='Изменения сохранены · собираем preview')
                build = self.home / f'build-{time.time_ns()}'
                build.mkdir()
                code = (check(self.workspace, build, self.config, lambda: self.stop.is_set() or self.rejected(), project_root=self.root)
                        if self.runtime == 'next-ui' else self.build_static(build, digest))
                if code:
                    raise RuntimeError('Проверки или сборка не прошли')
                self.publish(build / 'frontend-receipt.json')
            except Exception as error:
                with self.guard:
                    self.state.update(building=False, current=False,
                        message='Preview не обновлён · последняя успешная версия · ' + type(error).__name__)

    def build_static(self, build, digest):
        from .node import source_digest
        from .security import regular_files, read_regular
        export = build / 'export'
        export.mkdir()
        assets = {}
        expected = {name: hashlib.sha256(read_regular(self.workspace, name)).hexdigest()
                    for name, _ in regular_files(self.workspace)}
        if hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest() != digest:
            raise ValueError('Исходники изменились до подготовки preview')
        for name, path in regular_files(self.workspace):
            if path.suffix.lower() not in {'.html', '.css', '.js', '.mjs', '.png', '.jpg', '.jpeg', '.svg', '.webp', '.ico', '.woff', '.woff2'}:
                continue
            target = export / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_regular(self.workspace, name))
            assets[name] = hashlib.sha256(target.read_bytes()).hexdigest()
            if assets[name] != expected[name]:
                raise ValueError('Исходник изменился при копировании preview')
        if source_digest(self.workspace) != digest or 'index.html' not in assets:
            raise ValueError('Исходники менялись при подготовке preview')
        atomic_json(build / 'frontend-receipt.json', {'source_digest': digest, 'export': str(export), 'assets': assets})
        return 0

    def dispatch(self, method, path, headers):
        origin = f'http://127.0.0.1:{self.port}'
        if headers.get('Host') != f'127.0.0.1:{self.port}' or headers.get('Origin') not in (None, origin):
            return 403, 'text/plain; charset=utf-8', b'Forbidden origin'
        if method != 'GET':
            return 403, 'text/plain; charset=utf-8', b'Preview is read-only'
        parsed = urlsplit(path)
        rejected = self.rejected()
        if parsed.path == '/__preview/status':
            with self.guard:
                state = dict(self.state)
            return 200, 'application/json', json.dumps(state, ensure_ascii=False).encode()
        if rejected:
            return 410, 'text/html; charset=utf-8', '<html lang="ru"><meta charset="utf-8"><title>Результат отклонён</title><body><h1>Результат отклонён</h1><p>Изменения задачи не применены. Основная версия проекта сохранена.</p></body></html>'.encode()
        with self.guard:
            app = self.app
        if parsed.path.startswith('/api/v1/'):
            if parsed.path == '/api/v1/session':
                return 200, 'application/json', json.dumps({'request_id': str(uuid.uuid4()),
                    'data': {'csrf_token': '', 'confirmation_origin': ''}}).encode()
            if parsed.path.endswith('/capabilities'):
                if app is None:
                    return 503, 'text/plain', b'Preview not ready'
                status, content_type, body = app.dispatch('GET', path, {'Host': f'127.0.0.1:{PORT}'})
                if status == 200:
                    envelope = json.loads(body)
                    envelope['data'].update(actions=[], apply=False, project_view=False, stream=False)
                    body = json.dumps(envelope, ensure_ascii=False).encode()
                return status, content_type, body
            if not re.fullmatch(r'/api/v1/(?:projects|(?:projects/[a-f0-9]{16}/)?(?:status|tasks/[1-9][0-9]*(?:/(?:control|events|artifacts/[a-z]+))?))', parsed.path):
                return 403, 'text/plain', b'Read-only route unavailable'
            if app is None:
                return 503, 'text/plain', b'Preview not ready'
            status, content_type, body = app.dispatch('GET', path, {'Host': f'127.0.0.1:{PORT}'})
            if status == 200:
                envelope = json.loads(body)
                data = envelope['data']
                if isinstance(data, dict):
                    if 'allowed_actions' in data:
                        data.update(allowed_actions=[], confirmation_urls={}, confirmation_widgets={})
                    if 'connect_url' in data:
                        data['connect_url'] = ''
                body = json.dumps(envelope, ensure_ascii=False).encode()
            return status, content_type, body
        if app is None:
            return 503, 'text/html; charset=utf-8', b'<html><body>Preparing preview<meta http-equiv="refresh" content="3"></body></html>'
        try:
            status, content_type, body = app.static(parsed.path)
            if content_type.startswith('text/html'):
                body += RELOAD
            return status, content_type, body
        except (OSError, ValueError, RuntimeError):
            return 404, 'text/plain', b'Unavailable asset'

    def serve(self):
        from .runner import lock
        service = TaskService(self.root)
        preview = self
        class Handler(BaseHTTPRequestHandler):
            def dispatch(self):
                if any(len(self.headers.get_all(key, [])) > 1 for key in ('Host', 'Origin')):
                    self.send_error(400)
                    return
                status, content_type, body = preview.dispatch(self.command, self.path, self.headers)
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                hashes = ["'sha256-" + base64.b64encode(hashlib.sha256(item).digest()).decode() + "'"
                          for item in re.findall(rb'<script[^>]*>(.*?)</script>', body, re.S) if item]
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' " + ' '.join(hashes) +
                    "; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(body)
            do_GET = dispatch
            do_POST = dispatch
            def log_message(self, *_):
                pass
        try:
            with lock(service.store, f'preview-{self.ident}.lock'):
                server = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
                thread = threading.Thread(target=self.build_loop, daemon=True)
                thread.start()
                def stop(*_):
                    self.stop.set()
                    threading.Thread(target=server.shutdown, daemon=True).start()
                signal.signal(signal.SIGTERM, stop)
                signal.signal(signal.SIGINT, stop)
                atomic_json(self.home / 'server.json', {'pid': os.getpid(), 'task': self.ident, 'port': self.port})
                try:
                    server.serve_forever()
                finally:
                    self.stop.set()
                    server.server_close()
                    thread.join(timeout=35)
        finally:
            service.close()


def main(root, ident, serve=False):
    preview = Preview(root, ident)
    url = f'http://127.0.0.1:{preview.port}'
    if serve:
        preview.serve()
        return
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + '/__preview/status', timeout=2) as response:
            state = json.load(response)
            if state.get('task') != ident or state.get('project_id') != project_id(preview.root):
                raise ValueError('Порт занят другим процессом')
        print(url)
        return
    except OSError:
        pass
    with (preview.home / 'server.log').open('a') as output:
        process = subprocess.Popen([str(Path(sys.executable).resolve()), '-B', str(KIT / 'bin/harness'),
            '--project', str(preview.root), 'preview', str(ident), '--serve'], cwd=KIT, env=safe_env(),
            stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Preview не запущен; проверьте его журнал и занятость порта')
        try:
            with opener.open(url + '/__preview/status', timeout=1) as response:
                state = json.load(response)
            if state.get('task') == ident and state.get('project_id') == project_id(preview.root):
                print(url)
                return
        except OSError:
            pass
        time.sleep(.1)
    raise RuntimeError('Preview не подтвердил готовность')
