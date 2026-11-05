import base64
import hashlib
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PORT = 47849
SOURCE = Path(__file__).parent / 'index.html'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if len(self.headers.get_all('Host', [])) != 1 or self.headers.get('Host') not in {f'127.0.0.1:{PORT}', f'localhost:{PORT}'}:
            self.send_error(403)
            return
        if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            self.send_error(403)
            return
        path = urlsplit(self.path).path
        if path not in {'/', '/index.html'}:
            self.send_error(404)
            return
        if SOURCE.is_symlink():
            self.send_error(503)
            return
        body = SOURCE.read_bytes()
        hashes = ["'sha256-" + base64.b64encode(hashlib.sha256(code).digest()).decode() + "'"
                  for code in re.findall(rb'<script[^>]*>(.*?)</script>', body, re.S)]
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src " + ' '.join(hashes) +
                         "; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.send_error(403)

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
