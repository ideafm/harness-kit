import base64
import fcntl
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .node import source_digest
from .operator import OperatorError
from .preview import Preview, RELOAD
from .projects import project_id
from .security import safe_env
from .service import KIT, TaskService
from .state import atomic_json
from .web_launcher import RejectRedirect


VIEW_RELOAD = b'''<aside id="tw-project-view" style="position:fixed;bottom:8px;right:8px;z-index:2147483647;background:#172033;color:white;padding:8px 12px;border-radius:8px;font:12px system-ui">Project view</aside><script>(()=>{let revision=null;setInterval(async()=>{try{const r=await fetch('/__view/status');const s=await r.json();document.getElementById('tw-project-view').textContent=s.message;if(revision&&s.revision&&revision!==s.revision)location.reload();revision=s.revision}catch{}},1500)})();</script>'''


def profile(store):
    path = store.home / 'runtime-profile.json'
    if path.is_symlink() or path.with_suffix('.json.tmp').is_symlink():
        raise ValueError('Профиль заменён ссылкой')
    if not path.is_file():
        raise ValueError('Сначала настройте tw profile configure --adapter static или next-ui')
    data = json.loads(path.read_text())
    if data.get('adapter') not in {'static', 'next-ui'} or data.get('version') != 1:
        raise ValueError('Адаптер профиля не поддерживается')
    return data


def configure(store, adapter):
    if adapter not in {'static', 'next-ui'}:
        raise ValueError('Адаптер не поддерживается; unrestricted запуск запрещён')
    config = json.loads((store.home / 'config.json').read_text())
    if adapter == 'next-ui' and config.get('frontend_toolchain') != 'next-ui':
        raise ValueError('Проверенный next-ui toolchain не подготовлен')
    path = store.home / 'runtime-profile.json'
    if path.is_symlink() or path.with_suffix('.json.tmp').is_symlink():
        raise ValueError('Профиль заменён ссылкой')
    data = {'version': 1, 'adapter': adapter}
    with ProjectView(store.root).lock('selection.lock', True):
        atomic_json(path, data)
    return data


def capture_checked(store, task):
    path = store.home / 'runtime-profile.json'
    if not path.exists():
        return
    settings = profile(store)
    if settings['adapter'] != 'static':
        return
    preview = Preview(store.root, task['id'])
    folder = store.folder(task['id']) / ('runtime-checked-' + uuid.uuid4().hex)
    folder.mkdir()
    digest = source_digest(preview.workspace)
    preview.build_static(folder, digest)
    receipt = json.loads((folder / 'frontend-receipt.json').read_text())
    if digest != task['data']['check_receipt']['source_digest']:
        raise ValueError('Исходники изменились после проверок')
    receipt.update(task=task['id'], adapter='static', checked_at=time.time(), check_receipt=task['data']['check_receipt'])
    atomic_json(store.folder(task['id']) / 'runtime-receipt.json', receipt)


class ProjectView:
    def __init__(self, root):
        service = TaskService(root)
        try:
            self.root = service.root
            self.config = json.loads((service.store.home / 'config.json').read_text())
            self.home = service.store.home / 'project-view'
        finally:
            service.close()
        if self.home.is_symlink():
            raise ValueError('Состояние просмотра заменено ссылкой')
        self.home.mkdir(exist_ok=True, mode=0o700)
        self.ident = project_id(self.root)
        self.port = 40000 + int(self.ident, 16) % 7000
        self.url = f'http://127.0.0.1:{self.port}'
        self.guard = threading.Lock()
        self.stop_event = threading.Event()
        self.preview = None
        self.state = {'project_id': self.ident, 'url': self.url, 'revision': None,
                      'active_task': None, 'mode': None, 'building': False, 'current': False,
                      'message': 'Просмотр ещё не подготовлен'}

    def read(self, name, default=None):
        path = self.home / name
        if path.is_symlink():
            raise ValueError('Состояние просмотра заменено ссылкой')
        return json.loads(path.read_text()) if path.is_file() else default

    def write(self, name, data):
        if (self.home / name).is_symlink() or (self.home / (name + '.tmp')).is_symlink():
            raise ValueError('Состояние просмотра заменено ссылкой')
        atomic_json(self.home / name, data)

    @contextmanager
    def lock(self, name, blocking=False):
        descriptor = os.open(self.home / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            yield

    def running(self):
        try:
            with self.lock('server.lock'):
                return False
        except BlockingIOError:
            return True

    def selection(self):
        value = self.read('selection.json')
        if value is not None and (value.get('project_id') != self.ident or type(value.get('task')) is not int
                or value['task'] < 1 or value.get('mode') not in {'working', 'checked'}
                or not isinstance(value.get('revision'), str)):
            raise ValueError('Некорректный выбор просмотра')
        return value

    def select(self, ident, mode='checked', refresh=False, expected=None, selection_revision=None):
        if type(ident) is not int or ident < 1 or mode not in {'working', 'checked'}:
            raise ValueError('Нужны номер задачи и режим working/checked')
        service = TaskService(self.root)
        try:
            settings = profile(service.store)
            task = service.store.get(ident)
            workspace = service.store.folder(ident) / 'workspace'
            if task['state'] == 'rejected' or task['data'].get('workspace') != str(workspace) or workspace.is_symlink():
                raise ValueError('Рабочая копия задачи недоступна для просмотра')
            if not workspace.is_dir():
                raise ValueError('Рабочая копия ещё не подготовлена')
            if settings['adapter'] == 'next-ui' and task['data'].get('frontend_toolchain') != 'next-ui':
                raise ValueError('Задача не использует проверенный next-ui toolchain')
        finally:
            service.close()
        with self.lock('selection.lock', True):
            if expected is not None and self.control_revision(ident) != expected:
                raise OperatorError('stale_revision', 'Просмотр или задача изменились. Обновите карточку', 409)
            previous = self.selection()
            if previous and previous['task'] == ident and previous['mode'] == mode and not refresh:
                return previous
            selection = {'project_id': self.ident, 'task': ident, 'mode': mode, 'revision': selection_revision or uuid.uuid4().hex}
            self.write('selection.json', selection)
            return selection

    def control_revision(self, ident):
        service = TaskService(self.root)
        try:
            value = [service.store.get(ident), profile(service.store), self.selection()]
        finally:
            service.close()
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def request(self, record, stop=False):
        if not isinstance(record, dict) or record.get('project_id') != self.ident or record.get('port') != self.port:
            raise ValueError('Неверный владелец просмотра')
        request = urllib.request.Request(self.url + '/__view/' + ('shutdown' if stop else 'health'),
            data=b'{}' if stop else None, headers={'X-Tw-Instance': record['instance']})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())
        with opener.open(request, timeout=2) as response:
            result = json.loads(response.read(8192))
        if result.get('instance') != record['instance'] or result.get('project_id') != self.ident:
            raise ValueError('На порту отвечает другой процесс')
        return result

    def status(self):
        state = self.read('status.json', dict(self.state))
        state.update(url=self.url, requested=self.selection(), running=self.running())
        if state['running']:
            self.request(self.read('server.json'))
        return state

    def start(self):
        with self.lock('launcher.lock', True):
            if self.running():
                self.request(self.read('server.json'))
                return self.status()
            if self.selection() is None:
                raise ValueError('Сначала выберите задачу просмотра')
            descriptor = os.open(self.home / 'server.log', os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'a') as log:
                process = subprocess.Popen([str(Path(sys.executable).resolve()), '-B', str(KIT / 'bin/harness'),
                    '--project', str(self.root), 'view', '--serve'], env=safe_env(), cwd=KIT,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Просмотр не запущен; проверьте постоянный порт и project-view/server.log')
                try:
                    if self.running():
                        self.request(self.read('server.json'))
                        return self.status()
                except (OSError, ValueError, TypeError):
                    pass
                time.sleep(.1)
            raise RuntimeError('Просмотр не подтвердил готовность')

    def stop(self):
        with self.lock('launcher.lock', True):
            if not self.running():
                return {'stopped': True, 'url': self.url}
            record = self.read('server.json')
            self.request(record)
            self.request(record, stop=True)
            deadline = time.monotonic() + 10
            while self.running() and time.monotonic() < deadline:
                time.sleep(.1)
            if self.running():
                raise RuntimeError('Просмотр не подтвердил остановку')
            return {'stopped': True, 'url': self.url}

    def build(self, selection, settings):
        preview = Preview(self.root, selection['task'])
        preview.port = self.port
        if preview.rejected():
            raise ValueError('Задача отклонена')
        if selection['mode'] == 'checked':
            receipt = preview.folder / ('frontend-receipt.json' if settings['adapter'] == 'next-ui' else 'runtime-receipt.json')
            if receipt.is_symlink() or not receipt.is_file():
                raise ValueError('Проверенный экспорт ещё не подготовлен')
            data = json.loads(receipt.read_text())
            if settings['adapter'] == 'static':
                proof = data.get('check_receipt', {})
                if data.get('task') != selection['task'] or proof.get('exit_code') != 0 or proof.get('source_digest') != data.get('source_digest'):
                    raise ValueError('Нет доказательства проверок static экспорта')
            elif not data.get('checks') or any(check.get('exit_code') != 0 for check in data['checks']):
                raise ValueError('Нет доказательства проверок Next экспорта')
            export = Path(data['export'])
            if '..' in export.parts or not export.is_relative_to(preview.folder) or any(
                    path.is_symlink() for path in (export, *export.parents) if path.is_relative_to(preview.folder)):
                raise ValueError('Проверенный экспорт вне состояния задачи')
        else:
            folder = self.home / ('build-' + uuid.uuid4().hex)
            folder.mkdir()
            interrupted = lambda: self.stop_event.is_set() or self.selection() != selection
            if settings['adapter'] == 'next-ui':
                from .node import check
                if check(preview.workspace, folder, self.config, interrupted, project_root=self.root):
                    raise ValueError('Сборка рабочей версии не прошла')
            else:
                preview.build_static(folder, source_digest(preview.workspace))
            receipt = folder / 'frontend-receipt.json'
        preview.publish(receipt)
        return preview

    def remember(self, candidate, selection, settings):
        receipt = self.read_receipt(Path(candidate.app.receipt))
        name = 'published-' + uuid.uuid4().hex + '.json'
        self.write(name, receipt)
        self.write('last-good.json', {'project_id': self.ident, 'selection': selection,
            'settings': settings, 'receipt': name,
            'digest': hashlib.sha256((self.home / name).read_bytes()).hexdigest()})

    def read_receipt(self, path):
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('Некорректный путь receipt')
        home = self.root / '.harness'
        if not path.is_relative_to(home) or any(parent.is_symlink()
                for parent in (path, *path.parents) if parent.is_relative_to(home)):
            raise ValueError('Receipt вне состояния контроллера или заменён ссылкой')
        return json.loads(path.read_text())

    def restore(self):
        record = self.read('last-good.json')
        if record is None:
            return
        selection, settings = record['selection'], record['settings']
        if record.get('project_id') != self.ident or selection.get('project_id') != self.ident:
            raise ValueError('Неверный владелец сохранённого просмотра')
        if type(selection.get('task')) is not int or selection['task'] < 1 or selection.get('mode') not in {'checked', 'working'}:
            raise ValueError('Некорректная сохранённая задача')
        if not re.fullmatch(r'[a-f0-9]{32}', selection.get('revision', '')) or settings not in (
                {'version': 1, 'adapter': 'static'}, {'version': 1, 'adapter': 'next-ui'}):
            raise ValueError('Некорректный сохранённый профиль')
        name = record['receipt']
        if not isinstance(name, str) or not re.fullmatch(r'published-[a-f0-9]{32}\.json', name):
            raise ValueError('Некорректный сохранённый receipt')
        path = self.home / name
        data = self.read_receipt(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.get('digest'):
            raise ValueError('Сохранённый receipt изменился')
        preview = Preview(self.root, selection['task'], snapshot=True)
        preview.port = self.port
        if preview.rejected() or preview.runtime != settings['adapter']:
            raise ValueError('Сохранённая задача отклонена или профиль изменён')
        export = Path(data['export'])
        allowed = export.is_relative_to(preview.folder) and not export.is_relative_to(preview.workspace)
        if export.is_relative_to(self.home):
            parts = export.relative_to(self.home).parts
            allowed = len(parts) >= 2 and bool(re.fullmatch(r'build-[a-f0-9]{32}', parts[0]))
        if not allowed or not export.is_absolute() or '..' in export.parts or any(parent.is_symlink()
                for parent in (export, *export.parents) if parent.is_relative_to(self.root / '.harness')):
            raise ValueError('Сохранённый экспорт вне состояния просмотра или заменён ссылкой')
        if not re.fullmatch(r'[a-f0-9]{64}', data.get('source_digest', '')):
            raise ValueError('Некорректная версия сохранённого экспорта')
        if selection['mode'] == 'checked':
            if settings['adapter'] == 'static':
                proof = data.get('check_receipt', {})
                if data.get('task') != selection['task'] or proof.get('exit_code') != 0 or proof.get('source_digest') != data['source_digest']:
                    raise ValueError('Нет доказательства проверок сохранённого экспорта')
            elif not data.get('checks') or any(check.get('exit_code') != 0 for check in data['checks']):
                raise ValueError('Нет доказательства проверок сохранённого Next экспорта')
        preview.publish(path, verify_workspace=False)
        for asset in preview.app.manifest:
            preview.app.static('/' + asset)
        with self.guard:
            self.preview = preview
            self.state.update(active_task=selection['task'], mode=selection['mode'],
                revision=selection['revision'] + ':' + data['source_digest'],
                source_digest=data['source_digest'], current=False, workspace_current=False,
                message=f"Восстановлена TASK-{selection['task']:03} · текущий выбор ещё не проверен")

    def refresh(self):
        selection = self.selection()
        if selection is None:
            return
        service = TaskService(self.root)
        try:
            settings = profile(service.store)
        finally:
            service.close()
        candidate = self.build(selection, settings)
        with self.lock('selection.lock', True):
            if self.selection() != selection:
                return
            service = TaskService(self.root)
            try:
                if profile(service.store) != settings:
                    return
            finally:
                service.close()
            self.remember(candidate, selection, settings)
            with self.guard:
                self.preview = candidate
                self.state.pop('error', None)
                self.state.pop('restore_error', None)
                self.state.update(active_task=selection['task'], mode=selection['mode'],
                    revision=selection['revision'] + ':' + candidate.state['revision'],
                    current=selection['mode'] == 'checked' or candidate.state['current'], workspace_current=candidate.state['current'],
                    building=False, source_digest=candidate.state['revision'],
                    message=f"TASK-{selection['task']:03} · " + ('рабочая версия' if selection['mode'] == 'working' else 'последняя проверенная версия'))
                self.write('status.json', self.state)

    def build_loop(self):
        previous = None
        while not self.stop_event.wait(2):
            try:
                selection = self.selection()
                if selection is None:
                    continue
                service = TaskService(self.root)
                try:
                    settings = profile(service.store)
                    folder = service.store.folder(selection['task'])
                finally:
                    service.close()
                if selection['mode'] == 'working':
                    version = source_digest(folder / 'workspace')
                else:
                    path = folder / ('frontend-receipt.json' if settings['adapter'] == 'next-ui' else 'runtime-receipt.json')
                    if path.is_symlink():
                        raise ValueError('Receipt заменён ссылкой')
                    version = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
                workspace_version = version if selection['mode'] == 'working' else source_digest(folder / 'workspace')
                fingerprint = json.dumps([selection, settings, version, workspace_version], sort_keys=True)
                if fingerprint == previous:
                    continue
                previous = fingerprint
                with self.guard:
                    self.state.update(building=True, current=False, requested=selection, message='Подготовка выбранной версии')
                    self.write('status.json', self.state)
                self.refresh()
            except Exception as error:
                with self.guard:
                    active = self.state['active_task']
                    self.state.update(building=False, current=False, error=str(error)[:1000],
                        message='Просмотр не обновлён' + (f' · сохранена TASK-{active:03}' if active else '') + ' · ' + str(error)[:200])
                    self.write('status.json', self.state)

    def dispatch(self, method, path, headers):
        if headers.get('Host') != f'127.0.0.1:{self.port}' or headers.get('Origin') not in (None, self.url):
            return 403, 'text/plain', b'Forbidden origin'
        if method != 'GET':
            return 403, 'text/plain', b'Project view is read-only'
        query = parse_qs(urlsplit(path).query, keep_blank_values=True)
        pinned = {'__tw_task', '__tw_version'} & set(query)
        with self.guard:
            preview = self.preview
            matches = not pinned or (pinned == {'__tw_task', '__tw_version'} and query['__tw_task'] == [str(self.state['active_task'])] and query['__tw_version'] == [self.state.get('source_digest')])
        if not matches:
            return 409, 'text/html; charset=utf-8', '<html lang="ru"><meta charset="utf-8"><h1>Эта версия сейчас не открыта</h1><p>Вернитесь в панель Tw и выберите результат нужной задачи.</p></html>'.encode()
        if urlsplit(path).path == '/__view/status':
            with self.guard:
                body = dict(self.state, requested=self.selection())
            return 200, 'application/json', json.dumps(body, ensure_ascii=False).encode()
        if preview is None:
            return 503, 'text/html', b'<html>Preparing project view<meta http-equiv="refresh" content="2"></html>'
        status, content_type, body = preview.dispatch(method, path, headers)
        if content_type.startswith('text/html') and body.endswith(RELOAD):
            body = body[:-len(RELOAD)] + VIEW_RELOAD
        return status, content_type, body

    def serve(self):
        view = self
        instance = secrets.token_hex(32)
        with self.lock('server.lock'):
            class Handler(BaseHTTPRequestHandler):
                def dispatch(self):
                    if any(len(self.headers.get_all(key, [])) > 1 for key in ('Host', 'Origin', 'X-Tw-Instance')):
                        self.send_error(400)
                        return
                    path = urlsplit(self.path).path
                    trusted = self.headers.get('Host') == f'127.0.0.1:{view.port}' and self.headers.get('Origin') in (None, view.url)
                    if trusted and self.headers.get('X-Tw-Instance') == instance and (
                            self.command == 'GET' and path == '/__view/health' or self.command == 'POST'
                            and path == '/__view/shutdown' and self.headers.get('Content-Length') == '2' and self.rfile.read(2) == b'{}'):
                        body = json.dumps({'instance': instance, 'project_id': view.ident}).encode()
                        status, content_type = 200, 'application/json'
                        if self.command == 'POST':
                            threading.Thread(target=server.shutdown, daemon=True).start()
                    else:
                        status, content_type, body = view.dispatch(self.command, self.path, self.headers)
                    self.send_response(status)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    hashes = ["'sha256-" + base64.b64encode(hashlib.sha256(item).digest()).decode() + "'"
                              for item in re.findall(rb'<script[^>]*>(.*?)</script>', body, re.S) if item]
                    self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' " + ' '.join(hashes)
                        + "; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
                    self.end_headers()
                    self.wfile.write(body)
                do_GET = dispatch
                do_POST = dispatch
                def log_message(self, *_):
                    pass
            server = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
            try:
                self.restore()
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, OperatorError) as error:
                self.state['restore_error'] = str(error)[:1000]
            self.state.update(building=True, requested=self.selection(), message='Подготовка выбранной версии')
            self.write('status.json', self.state)
            thread = threading.Thread(target=self.build_loop, daemon=True)
            thread.start()
            self.write('server.json', {'project_id': self.ident, 'port': self.port, 'pid': os.getpid(), 'instance': instance})
            def stop(*_):
                threading.Thread(target=server.shutdown, daemon=True).start()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            try:
                server.serve_forever()
            finally:
                self.stop_event.set()
                thread.join(timeout=35)
                server.server_close()
                self.state.update(building=False, current=False, message='Просмотр остановлен')
                self.write('status.json', self.state)
                (self.home / 'server.json').unlink(missing_ok=True)


def dispatch(args, store):
    if args.command == 'profile':
        return configure(store, args.action_adapter) if args.action == 'configure' else profile(store)
    view = ProjectView(store.root)
    if args.serve:
        return view.serve()
    if args.target == 'stop':
        return view.stop()
    if args.target == 'status':
        return view.status()
    from .cli import task_id
    view.select(task_id(args.target), args.mode, args.refresh)
    return view.start()
