import json
import re
import shlex
import unittest
from urllib.parse import urlencode, urlsplit

import test_harness as fixtures
import test_operator as web_fixtures
from harness.observation import descriptor, event_text, plain, watch
from harness.service import TaskService
from harness.web import CONFIRM_PORT, PORT


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.service = TaskService(self.fixture.root)

    def tearDown(self):
        self.service.close()
        self.fixture.tearDown()

    def test_command_is_scoped_quoted_and_observational(self):
        command = descriptor('/tmp/project with spaces;echo no', 4)
        self.assertEqual(shlex.split(command['terminal_command'])[-4:],
                         ['--project', '/tmp/project with spaces;echo no', 'watch', 'TASK-004'])
        self.assertFalse(command['interactive'])

    def test_watch_once_does_not_start_or_mutate_task(self):
        before = self.service.store.get(1)
        output = []
        watch(self.service, 1, once=True, output=output.append)
        self.assertEqual(self.service.store.get(1), before)
        self.assertIn('В очереди', output[0])
        self.assertFalse(self.service.worker_status()['running'])
        self.assertNotIn('\x1b', plain('bad\x1b[31m'))
        self.assertIn('Проверки пройдены', event_text({'kind': 'checks_finished', 'data': {'exit_code': 0}}))

    def test_completed_task_does_not_display_historical_limit(self):
        task = self.service.store.get(1)
        task.update(state='review', stage='done')
        task['data'].update(reason='Лимит', retry_at=1)
        result = self.service.view(task)
        self.assertNotIn('reason', result)
        self.assertNotIn('retry_at', result)
        task['state'] = 'rate_limited'
        self.assertEqual(self.service.view(task)['reason'], 'Лимит')

    def test_worker_identifies_active_task_and_original_request_remains_available(self):
        task = self.service.store.get(1)
        task['state'] = 'running'
        self.service.store.save(task, 'fixture')
        from unittest.mock import patch
        with patch.object(self.service, 'worker_status', return_value={'running': True}):
            status = self.service.status()
        self.assertEqual(status['worker']['task_id'], 1)
        self.assertEqual(status['worker']['observation']['task_id'], 1)
        self.assertEqual(status['tasks'][0]['request'], before_request := task['data']['request'])
        self.assertTrue(before_request)


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.web = web_fixtures.WebTests()
        self.web.setUp()

    def tearDown(self):
        self.web.tearDown()

    def widget(self):
        self.web.fixture.run_task()
        _, _, body = self.web.app.dispatch('GET', '/api/v1/tasks/1/control', self.web.headers)
        url = json.loads(body)['data']['confirmation_widgets']['accept_result']
        return urlsplit(url)

    def test_embedded_accept_is_one_explicit_submission_without_navigation(self):
        url = self.widget()
        headers = {'Host': f'127.0.0.1:{CONFIRM_PORT}'}
        status, _, body = self.web.app.dispatch('GET', url.path + '?' + url.query, headers, confirmation=True)
        self.assertEqual(status, 200)
        self.assertEqual(self.web.fixture.store.get(1)['state'], 'review')
        page = body.decode()
        self.assertIn('action="/confirm/embed"', page)
        self.assertNotIn('Введите TASK-', page)
        token = re.search(r'name="token" value="([^"]+)"', page)[1]
        payload = urlencode({'token': token, 'confirmation': 'TASK-001'}).encode()
        headers.update({'Origin': f'http://127.0.0.1:{CONFIRM_PORT}', 'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(self.web.app.dispatch('POST', '/confirm', headers, payload, True)[0], 403)
        status, _, result = self.web.app.dispatch('POST', '/confirm/embed', headers, payload, True)
        self.assertEqual(status, 200)
        self.assertIn(b'parent.postMessage', result)
        self.assertIn(f'http://127.0.0.1:{PORT}'.encode(), result)
        self.assertEqual(self.web.fixture.store.get(1)['state'], 'accepted')
        self.assertEqual(self.web.app.dispatch('POST', '/confirm/embed', headers, payload, True)[0], 409)

    def test_panel_origin_cannot_post_widget(self):
        url = self.widget()
        headers = {'Host': f'127.0.0.1:{CONFIRM_PORT}', 'Origin': f'http://127.0.0.1:{PORT}'}
        self.assertEqual(self.web.app.dispatch('POST', url.path, headers, b'{}', True)[0], 403)
