import errno
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


ASSETS = Path(__file__).resolve().parent / 'static'
PORT = 47831


class Application:
    def __init__(self, project, instance, port):
        self.project = str(Path(project).resolve())
        self.instance = instance
        self.host = f'127.0.0.1:{port}'
        self.origin = f'http://{self.host}'

    def dispatch(self, method, path, headers, body=b''):
        def response(status, data):
            return status, 'application/json; charset=utf-8', json.dumps(data, ensure_ascii=False).encode()

        if headers.get('Host') != self.host:
            return response(403, {'error': 'Недопустимый Host'})
        if headers.get('Origin') not in (None, self.origin):
            return response(403, {'error': 'Недопустимый Origin'})
        if method == 'GET' and path == '/api/health':
            if not hmac.compare_digest(headers.get('X-Tw-Instance', '').encode(), self.instance.encode()):
                return response(403, {'error': 'Нужен идентификатор экземпляра'})
            return response(200, {'application': 'tw-web', 'project': self.project, 'instance': self.instance})
        if method == 'POST' and path == '/api/shutdown':
            if not hmac.compare_digest(headers.get('X-Tw-Instance', '').encode(), self.instance.encode()):
                return response(403, {'error': 'Нужен идентификатор экземпляра'})
            if headers.get('Content-Type') != 'application/json' or body != b'{}':
                return response(400, {'error': 'Ожидается пустой JSON-объект'})
            return response(200, {'stopping': True})
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if method == 'GET' and path in assets:
            name, content_type = assets[path]
            return 200, content_type, (ASSETS / name).read_bytes()
        return response(404, {'error': 'Не найдено'})


def make_server(project, instance):
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            if any(len(self.headers.get_all(name, [])) > 1 for name in
                   ('Host', 'Origin', 'Content-Length', 'Content-Type', 'X-Tw-Instance')):
                self.send_error(400)
                return
            if self.headers.get('Transfer-Encoding'):
                self.send_error(400)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 0 or size > 4096:
                    raise ValueError()
            except ValueError:
                self.send_error(400)
                return
            body = self.rfile.read(size)
            status, content_type, data = self.server.application.dispatch(
                self.command, self.path, self.headers, body)
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(data)
            if self.command == 'POST' and self.path == '/api/shutdown' and status == 200:
                threading.Thread(target=self.server.shutdown, daemon=True).start()

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        do_GET = handle_request
        do_POST = handle_request

        def log_message(self, *_):
            pass

    try:
        server = HTTPServer(('127.0.0.1', PORT), Handler)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            raise RuntimeError(f'Порт {PORT} занят; освободите его перед запуском tw-web') from error
        raise
    server.application = Application(project, instance, server.server_port)
    return server
