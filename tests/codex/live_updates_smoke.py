import hashlib
import http.client
import json
import socket
import sys
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import test_harness as fixtures
import harness.web as web
from harness.state import atomic_json


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def frame(response):
    lines = []
    while True:
        line = response.readline()
        if not line:
            raise RuntimeError('Stream closed before frame')
        if line == b'\n':
            return b''.join(lines)
        lines.append(line)


def main():
    fixture = fixtures.HarnessTests()
    fixture.setUp()
    first = second = connection = response = app = None
    threads = []
    ports = free_port(), free_port()
    while ports[0] == ports[1]:
        ports = free_port(), free_port()
    try:
        assets = fixture.root / 'ui-export'
        assets.mkdir()
        content = b'<html>SSE smoke</html>'
        (assets / 'index.html').write_bytes(content)
        receipt = fixture.store.home / 'ui-receipt.json'
        atomic_json(receipt, {'assets': {'index.html': hashlib.sha256(content).hexdigest()}})
        with patch.object(web, 'PORT', ports[0]), patch.object(web, 'CONFIRM_PORT', ports[1]):
            app = web.WebApplication(fixture.root, 'smoke', assets, receipt)
            first, second = web.servers(app)
            for server in (first, second):
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                threads.append(thread)
            connection = http.client.HTTPConnection('127.0.0.1', ports[0], timeout=4)
            connection.request('GET', '/api/v1/stream')
            response = connection.getresponse()
            assert response.status == 200
            assert response.getheader('Content-Type').startswith('text/event-stream')
            assert b'event: sync\n' in frame(response)
            fixture.store.add('change while stream is connected')
            changed = frame(response)
            assert b'event: changed\n' in changed
            assert b'change while' not in changed
            request = http.client.HTTPConnection('127.0.0.1', ports[0], timeout=4)
            request.request('GET', '/api/v1/status')
            status = request.getresponse()
            assert status.status == 200
            assert len(json.load(status)['data']['tasks']) == 2
            request.close()
            foreign = http.client.HTTPConnection('127.0.0.1', ports[0], timeout=4)
            foreign.request('GET', '/api/v1/stream', headers={'Origin': 'https://evil.invalid'})
            denied = foreign.getresponse()
            assert denied.status == 403
            denied.read()
            foreign.close()
            first.shutdown_all()
            for thread in threads:
                thread.join(timeout=3)
                assert not thread.is_alive()
            print(json.dumps({'result': 'passed', 'checks': ['HTTP sync', 'external change',
                'concurrent GET', 'foreign origin denied', 'shutdown'], 'model_calls': 0}))
    finally:
        if app is not None:
            app.stream_stop.set()
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()
        for server in (first, second):
            if server is not None:
                server.shutdown()
                server.server_close()
        for thread in threads:
            thread.join(timeout=3)
        fixture.tearDown()


if __name__ == '__main__':
    main()
