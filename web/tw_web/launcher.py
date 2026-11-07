import argparse
import fcntl
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import contextmanager
from pathlib import Path

from .server import PORT, make_server


ROOT = Path(__file__).resolve().parents[1]


class Runtime:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.home = self.root / '.tw-web'
        for path in (self.home,):
            if path.is_symlink():
                raise ValueError('Runtime-каталог заменён ссылкой')
            path.mkdir(mode=0o700, exist_ok=True)

    @contextmanager
    def lock(self, name, blocking=False):
        descriptor = os.open(self.home / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a') as handle:
            flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            fcntl.flock(handle, flags)
            yield

    def running(self):
        try:
            with self.lock('server.lock'):
                return False
        except BlockingIOError:
            return True

    def record(self):
        path = self.home / 'server.json'
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor) as handle:
            data = json.load(handle)
        if (data.get('application') != 'tw-web' or data.get('project') != str(self.root)
                or type(data.get('port')) is not int or data['port'] != PORT
                or not isinstance(data.get('instance'), str) or len(data['instance']) != 64):
            raise ValueError('Некорректное состояние сервера')
        return data

    def request(self, data, shutdown=False):
        path = '/api/shutdown' if shutdown else '/api/health'
        request = urllib.request.Request(f"http://127.0.0.1:{data['port']}{path}",
            data=b'{}' if shutdown else None,
            headers={'X-Tw-Instance': data['instance'], 'Content-Type': 'application/json'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=1) as response:
            return json.loads(response.read(4096))

    def ready(self):
        data = self.record()
        health = self.request(data)
        if any(health.get(key) != data[key] for key in ('application', 'project', 'instance')):
            raise ValueError('Ответил другой сервер; запуск остановлен')
        return data

    def start(self):
        with self.lock('launcher.lock', blocking=True):
            if self.running():
                return self.ready()
            descriptor = os.open(self.home / 'server.log', os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'a') as output:
                process = subprocess.Popen([str(Path(sys.executable).resolve()), str(ROOT / 'bin/tw-web'),
                    'serve', '--project', str(self.root)], cwd=self.root,
                    env={'PATH': os.defpath, 'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1'},
                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f'Сервер не запущен на 127.0.0.1:{PORT}. Возможно, порт занят; проверьте .tw-web/server.log')
                if self.running():
                    try:
                        return self.ready()
                    except (OSError, ValueError):
                        pass
                time.sleep(0.1)
            raise RuntimeError('Сервер не подтвердил готовность; проверьте status и server.log')

    def stop(self):
        with self.lock('launcher.lock', blocking=True):
            if not self.running():
                return False
            self.request(self.ready(), shutdown=True)
            deadline = time.monotonic() + 6
            while self.running() and time.monotonic() < deadline:
                time.sleep(0.1)
            if self.running():
                raise RuntimeError('Сервер ещё работает; принудительная остановка не выполнена')
            return True

    def serve(self):
        with self.lock('server.lock'):
            instance = secrets.token_hex(32)
            server = make_server(self.root, instance)
            data = {'application': 'tw-web', 'project': str(self.root), 'instance': instance,
                    'pid': os.getpid(), 'port': server.server_port}
            temporary = f'server-{instance}.json'
            descriptor = os.open(self.home / temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(descriptor, 'w') as handle:
                    json.dump(data, handle)
                os.replace(self.home / temporary, self.home / 'server.json')
                print(f'tw-web: http://127.0.0.1:{server.server_port}', flush=True)
                server.serve_forever(poll_interval=0.1)
            finally:
                server.server_close()
                (self.home / 'server.json').unlink(missing_ok=True)
                (self.home / temporary).unlink(missing_ok=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        raise ValueError('Перенаправление локального сервера запрещено')


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == 'preview':
        from .preview import main as preview_main
        return preview_main(arguments[1:])
    if arguments and arguments[0] in {'accept', 'request-changes', 'reject'}:
        from .operator import main as operator_main
        return operator_main(arguments)
    parser = argparse.ArgumentParser(prog='tw-web', description='Локальная панель Tw')
    parser.add_argument('command', nargs='?', default='open', choices=['open', 'start', 'status', 'stop', 'serve'])
    parser.add_argument('--project', type=Path, default=ROOT)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    try:
        runtime = Runtime(args.project)
        if args.command in {'open', 'start'} and not runtime.running():
            choice = runtime.home / 'preview.json'
            if choice.exists() or choice.is_symlink():
                descriptor = os.open(choice, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(descriptor) as handle:
                    selected = json.load(handle)
                ident = selected.get('task') if isinstance(selected, dict) else None
                if type(ident) is not int or ident < 1:
                    raise ValueError('Некорректный выбранный результат панели')
                from .preview import main as preview_main
                options = [str(ident)]
                if args.no_browser or args.command == 'start':
                    options.append('--no-browser')
                return preview_main(options)
        if args.command == 'serve':
            runtime.serve()
        elif args.command == 'stop':
            print('tw-web остановлен' if runtime.stop() else 'tw-web уже остановлен')
        elif args.command == 'status':
            if not runtime.running():
                print('tw-web остановлен')
                return
            data = runtime.ready()
            print(f"tw-web работает: http://127.0.0.1:{data['port']}")
        else:
            data = runtime.start()
            url = f"http://127.0.0.1:{data['port']}"
            print(url, flush=True)
            if args.command == 'open' and not args.no_browser and not webbrowser.open(url):
                print('Откройте этот адрес в браузере.')
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f'tw-web: {error}\n')
