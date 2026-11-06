import hashlib
import json
import unittest

import test_harness as fixtures
from harness.operator import OperatorError
from harness.projects import project_id
from harness.state import atomic_json
from harness.web import PORT, WebApplication


class LiveUpdateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.root = self.fixture.root.resolve()
        self.assets = self.root / 'export'
        self.assets.mkdir()
        content = b'<html>stream fixture</html>'
        (self.assets / 'index.html').write_bytes(content)
        receipt = self.fixture.store.home / 'stream-ui.json'
        atomic_json(receipt, {'assets': {'index.html': hashlib.sha256(content).hexdigest()}})
        self.app = WebApplication(self.root, 'stream-test', self.assets, receipt)
        self.headers = {'Host': f'127.0.0.1:{PORT}'}

    def tearDown(self):
        self.fixture.tearDown()

    def stream(self, path='/api/v1/stream', headers=None):
        stream = self.app.open_stream(path, headers or self.headers)
        self.addCleanup(stream.close)
        return stream

    def test_external_database_change_notifies_without_task_text(self):
        stream = self.stream()
        first = stream.poll(now=0)
        self.assertIn(b'event: sync\n', first)
        self.assertIsNone(stream.poll(now=1))
        task = self.fixture.store.get(1)
        task['data']['request'] = '<script>untrusted</script>'
        self.fixture.store.save(task, 'changed_for_stream')
        changed = stream.poll(now=2)
        self.assertIn(b'event: changed\n', changed)
        self.assertNotIn(b'untrusted', changed)
        self.assertIsNone(stream.poll(now=3))
        self.assertEqual(stream.poll(now=17), b': keepalive\n\n')

    def test_runtime_change_and_reconnect_force_sync(self):
        stream = self.stream()
        first = stream.poll(now=0)
        home = self.fixture.store.home / 'project-view'
        home.mkdir()
        atomic_json(home / 'status.json', {'active_task': 1})
        self.assertIn(b'event: changed\n', stream.poll(now=1))
        cursor = first.decode().split('id: ')[1].split('\n')[0]
        reconnected = self.stream(headers=dict(self.headers, **{'Last-Event-ID': cursor}))
        self.assertIn(b'event: sync\n', reconnected.poll(now=2))

    def test_host_origin_scope_and_cursor_are_validated(self):
        for headers in ({'Host': 'evil.invalid'}, dict(self.headers, Origin='https://evil.invalid'),
                        dict(self.headers, **{'Last-Event-ID': 'bad\nvalue'})):
            with self.assertRaises(OperatorError):
                self.app.open_stream('/api/v1/stream', headers)
        with self.assertRaises(OperatorError) as unknown:
            self.app.open_stream('/api/v1/projects/0000000000000000/stream', self.headers)
        self.assertEqual(unknown.exception.status, 404)
        scoped = self.stream('/api/v1/projects/' + project_id(self.root) + '/stream')
        self.assertIn(project_id(self.root).encode(), scoped.poll(now=0))
        with self.assertRaises(OperatorError):
            self.app.open_stream('/api/v1/stream?path=/tmp/anything', self.headers)

    def test_connection_capacity_is_released_exactly_once(self):
        streams = [self.stream() for _ in range(16)]
        with self.assertRaises(OperatorError) as limit:
            self.app.open_stream('/api/v1/stream', self.headers)
        self.assertEqual(limit.exception.status, 503)
        streams[0].close()
        streams[0].close()
        self.stream()
        with self.assertRaises(OperatorError):
            self.app.open_stream('/api/v1/stream', self.headers)

    def test_shutdown_closes_generator_and_refuses_new_stream(self):
        stream = self.stream()
        frames = stream.frames(self.app.stream_stop)
        self.assertIn(b'event: sync', next(frames))
        self.app.stream_stop.set()
        with self.assertRaises(StopIteration):
            next(frames)
        self.assertTrue(stream.closed)
        with self.assertRaises(OperatorError):
            self.app.open_stream('/api/v1/stream', self.headers)

    def test_symlinked_observation_file_is_not_followed(self):
        stream = self.stream()
        (self.fixture.store.home / 'quota.json').symlink_to(self.root / 'app.py')
        with self.assertRaises(ValueError):
            stream.poll(now=0)
