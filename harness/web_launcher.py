import argparse
import fcntl
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from contextlib import contextmanager
from pathlib import Path

from .service import KIT
from .state import atomic_json
from .web import PORT, WebApplication, servers


class Runtime:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.home = self.root / '.tw-web'
        if self.home.is_symlink() or (self.root / '.harness').is_symlink():
            raise ValueError('Состояние панели заменено ссылкой')
        self.home.mkdir(exist_ok=True, mode=0o700)

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

    def record(self):
        descriptor = os.open(self.home / 'server.json', os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor) as handle:
            record = json.load(handle)
        if record.get('project') != str(self.root) or record.get('application') != 'tw-web' or record.get('port') != PORT:
            raise ValueError('Некорректное состояние сервера')
        return record

    def request(self, record, stop=False):
        request = urllib.request.Request(f'http://127.0.0.1:{PORT}/api/' + ('shutdown' if stop else 'health'),
            data=b'{}' if stop else None, headers={'X-Tw-Instance': record['instance'], 'Content-Type': 'application/json'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())
        with opener.open(request, timeout=2) as response:
            result = json.loads(response.read(8192))
        if not stop and any(result.get(key) != record[key] for key in ('application', 'project', 'instance')):
            raise ValueError('На порту отвечает другой процесс')
        return result

    def deployment(self):
        path = self.root / '.harness/web-ui.json'
        if path.is_symlink() or not path.is_file():
            raise ValueError('Проверенная сборка интерфейса ещё не подготовлена')
        data = json.loads(path.read_text())
        app = WebApplication(self.root, 'preflight', data['export'], data['receipt'])
        app.static('/')
        return data

    def stop_locked(self):
        if not self.running():
            return False
        record = self.record()
        self.request(record)
        self.request(record, stop=True)
        deadline = time.monotonic() + 10
        while self.running() and time.monotonic() < deadline:
            time.sleep(.1)
        if self.running():
            raise RuntimeError('Сервер не подтвердил остановку')
        return True

    def stop(self):
        with self.lock('launcher.lock', True):
            return self.stop_locked()

    def start(self):
        deployment = self.deployment()
        with self.lock('launcher.lock', True):
            if self.running():
                record = self.record()
                health = self.request(record)
                if health.get('runtime') == 'operator-web' and record.get('receipt') == deployment['receipt']:
                    return record
                self.stop_locked()
            descriptor = os.open(self.home / 'server.log', os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'a') as log:
                process = subprocess.Popen([str(Path(sys.executable).resolve()), '-B', str(KIT / 'bin/tw-web'),
                    'serve', '--project', str(self.root)], cwd=KIT,
                    env={'PATH': str(self.root / '.harness/toolchains/next-ui/runtime') + ':/opt/homebrew/bin:/usr/bin:/bin',
                         'OPENSSL_CONF': '/dev/null', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1'},
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Сервер не запущен. Проверьте порты 47831/47832 и .tw-web/server.log')
                try:
                    if self.running():
                        record = self.record()
                        self.request(record)
                        return record
                except (OSError, ValueError):
                    pass
                time.sleep(.1)
            raise RuntimeError('Сервер не подтвердил готовность')

    def serve(self):
        with self.lock('server.lock'):
            deployment = self.deployment()
            instance = secrets.token_hex(32)
            app = WebApplication(self.root, instance, deployment['export'], deployment['receipt'])
            first, second = servers(app)
            thread = threading.Thread(target=second.serve_forever, daemon=True)
            thread.start()
            atomic_json(self.home / 'server.json', {'application': 'tw-web', 'project': str(self.root),
                'instance': instance, 'port': PORT, 'pid': os.getpid(), 'receipt': deployment['receipt']})
            def stop(*_):
                threading.Thread(target=first.shutdown_all, daemon=True).start()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            try:
                first.serve_forever()
            finally:
                second.shutdown()
                first.server_close()
                second.server_close()
                thread.join(timeout=3)
                (self.home / 'server.json').unlink(missing_ok=True)


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        raise ValueError('Перенаправление локального сервера запрещено')


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {'accept', 'request-changes', 'reject', 'approve-plan', 'revise-plan'}:
        from .cli import main as cli_main
        return cli_main(['--project', str(KIT.parent / 'tw-web'), *arguments])
    parser = argparse.ArgumentParser(prog='tw-web', description='Панель управления Tw')
    parser.add_argument('command', nargs='?', default='open', choices=['open', 'start', 'status', 'stop', 'serve'])
    parser.add_argument('--project', type=Path, default=KIT.parent / 'tw-web')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(arguments)
    try:
        runtime = Runtime(args.project)
        if args.command == 'serve':
            return runtime.serve()
        if args.command == 'stop':
            print('tw-web остановлен' if runtime.stop() else 'tw-web уже остановлен')
            return
        if args.command == 'status':
            if runtime.running():
                runtime.request(runtime.record())
                print(f'tw-web работает: http://127.0.0.1:{PORT}')
            else:
                print('tw-web остановлен')
            return
        runtime.start()
        url = f'http://127.0.0.1:{PORT}'
        print(url, flush=True)
        if args.command == 'open' and not args.no_browser:
            webbrowser.open(url)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f'tw-web: {error}\n')
