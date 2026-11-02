import io
import json
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from tw_web.launcher import NoRedirect, Runtime, main
from tw_web.server import PORT, Application, make_server


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.app = Application('/project', 'a' * 64, 34567)
        self.headers = {'Host': '127.0.0.1:34567', 'X-Tw-Instance': 'a' * 64}

    def test_health_identifies_instance_and_project(self):
        status, _, body = self.app.dispatch('GET', '/api/health', self.headers)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data['application'], 'tw-web')
        self.assertEqual(data['project'], str(Path('/project').resolve()))
        self.assertEqual(data['instance'], 'a' * 64)

    def test_foreign_hosts_and_origins_cannot_reach_app(self):
        for headers in ({'Host': 'evil.example'}, {'Host': '127.0.0.1:34567', 'Origin': 'https://evil.example'},
                        {'Host': '127.0.0.1:80'}, {}):
            with self.subTest(headers=headers):
                self.assertEqual(self.app.dispatch('GET', '/', headers)[0], 403)

    def test_shutdown_requires_token_json_and_matching_origin(self):
        valid = dict(self.headers, **{'Content-Type': 'application/json', 'Origin': self.app.origin})
        self.assertEqual(self.app.dispatch('POST', '/api/shutdown', valid, b'{}')[0], 200)
        for changes, body in (({'X-Tw-Instance': ''}, b'{}'), ({'X-Tw-Instance': 'чужой'}, b'{}'),
                              ({'Origin': 'null'}, b'{}'), ({'Content-Type': 'text/plain'}, b'{}'),
                              ({}, b'{"command":"stop"}')):
            with self.subTest(changes=changes):
                self.assertGreaterEqual(self.app.dispatch('POST', '/api/shutdown', dict(valid, **changes), body)[0], 400)

    def test_health_does_not_disclose_token_to_browser(self):
        self.assertEqual(self.app.dispatch('GET', '/api/health', {'Host': self.app.host})[0], 403)

    def test_only_exact_static_routes_exist(self):
        self.assertEqual(self.app.dispatch('GET', '/', self.headers)[0], 200)
        for method, path in [('GET', '/../AGENTS.md'), ('GET', '/%2e%2e/README.md'),
                             ('GET', '/api/file?path=/etc/passwd'), ('POST', '/api/run'),
                             ('GET', '/api/shutdown'), ('POST', '/')]:
            with self.subTest(path=path):
                self.assertEqual(self.app.dispatch(method, path, self.headers)[0], 404)

    def test_server_binds_only_dedicated_loopback_port(self):
        with patch('tw_web.server.HTTPServer', return_value=Mock(server_port=PORT)) as factory:
            server = make_server('/project', 'a' * 64)
            self.assertEqual(factory.call_args.args[0], ('127.0.0.1', PORT))
            self.assertEqual(server.application.origin, f'http://127.0.0.1:{PORT}')

    def test_occupied_port_fails_without_selecting_another(self):
        with patch('tw_web.server.HTTPServer', side_effect=OSError(errno.EADDRINUSE, 'occupied')) as factory:
            with self.assertRaisesRegex(RuntimeError, f'Порт {PORT} занят'):
                make_server('/project', 'a' * 64)
            self.assertEqual(factory.call_count, 1)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.runtime = Runtime.__new__(Runtime)
        self.runtime.root = Path('/project')
        self.runtime.home = Path('/runtime')
        self.data = {'application': 'tw-web', 'project': '/project', 'instance': 'a' * 64, 'port': PORT}

    def test_repeat_start_reuses_verified_server(self):
        with patch.object(self.runtime, 'lock', return_value=nullcontext()), \
             patch.object(self.runtime, 'running', return_value=True), \
             patch.object(self.runtime, 'ready', return_value=self.data), \
             patch('tw_web.launcher.subprocess.Popen') as spawn:
            self.assertEqual(self.runtime.start(), self.data)
            spawn.assert_not_called()

    def test_unresponsive_locked_server_does_not_spawn_replacement(self):
        with patch.object(self.runtime, 'lock', return_value=nullcontext()), \
             patch.object(self.runtime, 'running', return_value=True), \
             patch.object(self.runtime, 'ready', side_effect=OSError('unavailable')), \
             patch('tw_web.launcher.subprocess.Popen') as spawn:
            with self.assertRaises(OSError):
                self.runtime.start()
            spawn.assert_not_called()

    def test_start_detaches_server_and_waits_for_readiness(self):
        with patch.object(self.runtime, 'lock', return_value=nullcontext()), \
             patch.object(self.runtime, 'running', side_effect=[False, True]), \
             patch.object(self.runtime, 'ready', return_value=self.data), \
             patch('tw_web.launcher.os.open', return_value=42), \
             patch('tw_web.launcher.os.fdopen', return_value=io.StringIO()), \
             patch('tw_web.launcher.subprocess.Popen', return_value=Mock(poll=Mock(return_value=None))) as spawn:
            self.assertEqual(self.runtime.start(), self.data)
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])
            self.assertEqual(spawn.call_args.kwargs['stdin'], -3)
            self.assertIn('serve', spawn.call_args.args[0])

    def test_health_from_another_project_is_rejected(self):
        with patch.object(self.runtime, 'record', return_value=self.data), \
             patch.object(self.runtime, 'request', return_value=dict(self.data, project='/other')):
            with self.assertRaisesRegex(ValueError, 'другой сервер'):
                self.runtime.ready()

    def test_stop_uses_authenticated_request_without_signalling_pid(self):
        with patch.object(self.runtime, 'lock', return_value=nullcontext()), \
             patch.object(self.runtime, 'running', side_effect=[True, False, False]), \
             patch.object(self.runtime, 'ready', return_value=self.data), \
             patch.object(self.runtime, 'request') as request:
            self.assertTrue(self.runtime.stop())
            request.assert_called_once_with(self.data, shutdown=True)

    def test_stopped_server_stop_is_idempotent(self):
        with patch.object(self.runtime, 'lock', return_value=nullcontext()), \
             patch.object(self.runtime, 'running', return_value=False), \
             patch.object(self.runtime, 'request') as request:
            self.assertFalse(self.runtime.stop())
            request.assert_not_called()

    def test_no_browser_option_keeps_server_running(self):
        with patch('tw_web.launcher.Runtime', return_value=Mock(start=Mock(return_value=self.data))), \
             patch('tw_web.launcher.webbrowser.open') as browser, patch('sys.stdout', new_callable=io.StringIO):
            main(['--no-browser'])
            browser.assert_not_called()

    def test_redirect_is_not_followed(self):
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, None, None, None, 'https://example.com')


if __name__ == '__main__':
    unittest.main()
import errno
