import hashlib
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

import test_harness as fixtures
from harness.operator import Operator, OperatorError
from harness.service import TaskService
from harness.web import CONFIRM_PORT, PORT, WebApplication


class OperatorTests(unittest.TestCase):
    def test_start_unavailable_for_running_and_already_serviced_queue(self):
        with patch.object(self.service, 'worker_status', return_value={'running': False}):
            self.assertIn('start', self.operator.control(1)['allowed_actions'])
        with patch.object(self.service, 'worker_status', return_value={'running': True}):
            self.assertNotIn('start', self.operator.control(1)['allowed_actions'])
        task = self.service.store.get(1)
        task['state'] = 'running'
        self.service.store.save(task, 'fixture_running')
        with patch.object(self.service, 'worker_status', return_value={'running': False}):
            control = self.operator.control(1)
            self.assertNotIn('start', control['allowed_actions'])
            self.assertIn('pause', control['allowed_actions'])
            with patch.object(self.service, 'start') as start:
                with self.assertRaises(OperatorError):
                    self.operator.perform(1, {'action': 'start'}, 'repeat-start-key', control['revision'])
                start.assert_not_called()

    def test_approval_starts_worker_once_even_when_retried(self):
        self.fixture.require_plan()
        control = self.operator.control(1)
        payload = {'action': 'approve_plan', 'plan_version': control['plan']['version'],
                   'plan_digest': control['plan']['digest']}
        with patch.object(self.service, 'start') as start:
            first = self.operator.perform(1, payload, 'approval-start-123', control['revision'], human=True)
            second = self.operator.perform(1, payload, 'approval-start-123', control['revision'], human=True)
        self.assertEqual(first['status'], 'succeeded')
        self.assertEqual(first, second)
        start.assert_called_once_with(1)
        self.assertEqual(self.service.show(1)['state'], 'queued')

    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.service = TaskService(self.fixture.root)
        self.operator = Operator(self.service)

    def tearDown(self):
        self.service.close()
        self.fixture.tearDown()

    def test_idempotent_submit_survives_a_new_connection(self):
        payload = {'request': 'second task', 'approval_mode': 'approve-plan'}
        with patch.object(self.service, 'start', side_effect=lambda ident: {'task': self.service.show(ident)}):
            first = self.operator.perform(None, payload, 'submit-key-123')
        other = TaskService(self.fixture.root)
        try:
            repeated = Operator(other).perform(None, payload, 'submit-key-123')
            self.assertEqual(repeated, first)
            self.assertEqual(len(other.status()['tasks']), 2)
        finally:
            other.close()

    def test_reused_key_with_different_payload_is_conflict(self):
        payload = {'request': 'task', 'approval_mode': 'auto'}
        with patch.object(self.service, 'start', side_effect=lambda ident: {'task': self.service.show(ident)}):
            self.operator.perform(None, payload, 'unique-key-123')
        with self.assertRaises(OperatorError) as error:
            self.operator.perform(None, dict(payload, request='other'), 'unique-key-123')
        self.assertEqual(error.exception.status, 409)

    def test_stale_revision_does_not_pause_or_resurrect_task(self):
        control = self.operator.control(1)
        self.service.store.pause(1)
        with self.assertRaises(OperatorError) as error:
            self.operator.perform(1, {'action': 'pause'}, 'pause-key-123', control['revision'])
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.service.show(1)['state'], 'paused')

    def test_operator_state_and_key_commit_atomically(self):
        before = len(self.service.status()['tasks'])
        with self.assertRaises(RuntimeError):
            with self.service.store.transaction():
                self.service.store.add('will rollback')
                raise RuntimeError('rollback')
        self.assertEqual(len(self.service.status()['tasks']), before)

    def test_duplicate_pause_returns_original_operation_before_revision_check(self):
        control = self.operator.control(1)
        first = self.operator.perform(1, {'action': 'pause'}, 'pause-key-123', control['revision'])
        repeated = self.operator.perform(1, {'action': 'pause'}, 'pause-key-123', control['revision'])
        self.assertEqual(first, repeated)
        self.assertEqual(first['status'], 'succeeded')

    def test_untrusted_transport_cannot_accept_result(self):
        self.fixture.run_task()
        control = self.operator.control(1)
        payload = {'action': 'accept_result', 'result_version': control['result']['version'], 'result_digest': control['result']['digest']}
        with self.assertRaises(OperatorError) as error:
            self.operator.perform(1, payload, 'accept-key-123', control['revision'])
        self.assertEqual(error.exception.status, 403)
        self.assertEqual(self.service.show(1)['state'], 'review')
        result = self.operator.perform(1, payload, 'accept-key-123', control['revision'], human=True)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(self.service.show(1)['state'], 'accepted')

    def test_failed_action_rolls_back_partial_state(self):
        control = self.operator.control(1)
        def broken(*_):
            self.service.store.pause(1)
            raise RuntimeError('failure')
        with patch.object(self.operator, 'dispatch', side_effect=broken):
            record = self.operator.perform(1, {'action': 'pause'}, 'fail-key-123', control['revision'])
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(self.service.show(1)['state'], 'queued')
        self.assertEqual(self.operator.operation(record['operation_id']), record)

    def test_submit_accepts_explicit_backend_and_rejects_invalid(self):
        with patch.object(self.service, 'start', side_effect=lambda ident: {'task': self.service.show(ident)}):
            gemini_res = self.operator.perform(None, {'request': 'gemini task', 'approval_mode': 'auto', 'backend': 'gemini'}, 'key-gemini-1')
            gemini_task = self.service.store.get(gemini_res['task_id'])
            self.assertEqual(gemini_task['data']['backend'], 'gemini')
            self.assertEqual(self.service.show(gemini_res['task_id'])['backend'], 'gemini')

            codex_res = self.operator.perform(None, {'request': 'codex task', 'approval_mode': 'auto', 'backend': 'codex'}, 'key-codex-1')
            codex_task = self.service.store.get(codex_res['task_id'])
            self.assertEqual(codex_task['data']['backend'], 'codex')
            self.assertEqual(self.service.show(codex_res['task_id'])['backend'], 'codex')

            with self.assertRaises(OperatorError) as err:
                self.operator.perform(None, {'request': 'bad task', 'approval_mode': 'auto', 'backend': 'unknown'}, 'key-bad-1')
            self.assertEqual(err.exception.status, 400)

    def test_switch_backend_updates_task_and_resets_rate_limit(self):
        self.service.store.pause(1)
        control = self.operator.control(1)
        self.assertIn('switch_backend', control['allowed_actions'])
        res = self.operator.perform(1, {'action': 'switch_backend', 'backend': 'gemini'}, 'key-switch-1', control['revision'])
        self.assertEqual(res['status'], 'succeeded')
        updated = self.service.store.get(1)
        self.assertEqual(updated['data']['backend'], 'gemini')
        events = self.service.store.events(1)
        self.assertEqual(events[-1]['kind'], 'backend_switched')
        self.assertEqual(events[-1]['data']['to'], 'gemini')

        task = self.service.store.get(1)
        task['state'] = 'rate_limited'
        task['data']['retry_at'] = 9999999999.0
        task['data']['reason'] = 'Quota exceeded'
        self.service.store.save(task, 'rate_limited')
        control_rl = self.operator.control(1)
        self.assertIn('switch_backend', control_rl['allowed_actions'])
        with patch.object(self.service, 'start') as mock_start:
            res_rl = self.operator.perform(1, {'action': 'switch_backend', 'backend': 'codex'}, 'key-switch-2', control_rl['revision'])
            self.assertEqual(res_rl['status'], 'succeeded')
            mock_start.assert_called_once_with(1)
        after_rl = self.service.store.get(1)
        self.assertEqual(after_rl['state'], 'queued')
        self.assertEqual(after_rl['data']['backend'], 'codex')
        self.assertNotIn('retry_at', after_rl['data'])


class WebTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.assets = self.root / 'export'
        self.assets.mkdir()
        data = b'<!doctype html><html>test</html>'
        (self.assets / 'index.html').write_bytes(data)
        receipt = self.root / '.harness/frontend.json'
        receipt.write_text(json.dumps({'assets': {'index.html': hashlib.sha256(data).hexdigest()}}))
        self.app = WebApplication(self.root, 'instance', self.assets, receipt)
        self.headers = {'Host': f'127.0.0.1:{PORT}'}

    def tearDown(self):
        self.fixture.tearDown()

    def test_static_files_are_bound_to_the_build_hash(self):
        self.assertEqual(self.app.dispatch('GET', '/', self.headers)[0], 200)
        (self.assets / 'index.html').write_text('modified')
        self.assertEqual(self.app.dispatch('GET', '/', self.headers)[0], 503)
        self.assertEqual(self.app.dispatch('GET', '/../app.py', self.headers)[0], 404)

    def test_operator_page_adopts_new_verified_deployment_and_listens_for_acceptance(self):
        self.app.track_deployment = True
        assets = self.root / 'next-export'
        assets.mkdir()
        data = b'<html>accepted-new-build</html>'
        (assets / 'index.html').write_bytes(data)
        receipt = self.root / '.harness/next-receipt.json'
        receipt.write_text(json.dumps({'assets': {'index.html': hashlib.sha256(data).hexdigest()}}))
        deployment = self.root / '.harness/web-ui.json'
        deployment.write_text(json.dumps({'export': str(assets), 'receipt': str(receipt)}))
        status, _, body = self.app.dispatch('GET', '/', self.headers)
        self.assertEqual(status, 200)
        self.assertIn(b'accepted-new-build', body)
        self.assertIn(b'accept_result', body)
        self.assertIn(b'location.reload()', body)

    def test_foreign_origin_and_missing_csrf_are_denied(self):
        self.assertEqual(self.app.dispatch('GET', '/', {'Host': 'evil.example'})[0], 403)
        headers = dict(self.headers, **{'Origin': 'https://evil.example'})
        self.assertEqual(self.app.dispatch('GET', '/api/v1/status', headers)[0], 403)
        self.assertEqual(self.app.dispatch('POST', '/api/v1/tasks', self.headers, b'{}')[0], 403)

    def test_control_returns_authoritative_actions_and_events(self):
        status, _, body = self.app.dispatch('GET', '/api/v1/tasks/1/control', self.headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['data']['allowed_actions'], ['start', 'pause'])
        status, _, body = self.app.dispatch('GET', '/api/v1/tasks/1/events', self.headers)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['data']['items'])

    def test_localhost_navigation_uses_canonical_address_without_mutation(self):
        status, _, body = self.app.dispatch('GET', '/confirm?task=1', {'Host': f'localhost:{CONFIRM_PORT}'}, confirmation=True)
        self.assertEqual(status, 200)
        self.assertIn(f'http://127.0.0.1:{CONFIRM_PORT}/confirm?task=1', body.decode())
        self.assertEqual(self.fixture.store.get(1)['state'], 'queued')
        for origin in ('null', 'https://evil.example'):
            headers = {'Host': f'127.0.0.1:{CONFIRM_PORT}', 'Origin': origin}
            self.assertEqual(self.app.dispatch('POST', '/confirm', headers, b'', True)[0], 403)

    def test_accept_form_uses_explicit_button_without_typing(self):
        self.fixture.run_task()
        _, _, body = self.app.dispatch('GET', '/api/v1/tasks/1/control', self.headers)
        url = json.loads(body)['data']['confirmation_urls']['accept_result']
        path = url.split(f':{CONFIRM_PORT}', 1)[1]
        headers = {'Host': f'127.0.0.1:{CONFIRM_PORT}'}
        status, _, body = self.app.dispatch('GET', path, headers, confirmation=True)
        self.assertEqual(status, 200)
        page = body.decode()
        self.assertNotIn('Введите TASK-', page)
        self.assertIn('name="confirmation" value="TASK-001"', page)
        self.assertEqual(self.fixture.store.get(1)['state'], 'review')
        token = re.search(r'name="token" value="([^"]+)"', page)[1]
        payload = urlencode({'token': token, 'confirmation': 'TASK-001'}).encode()
        headers.update({'Origin': f'http://127.0.0.1:{CONFIRM_PORT}', 'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(self.app.dispatch('POST', '/confirm', headers, payload, True)[0], 200)
        self.assertEqual(self.fixture.store.get(1)['state'], 'accepted')
        self.assertEqual(self.app.dispatch('POST', '/confirm', headers, payload, True)[0], 409)

    def test_approval_requires_a_different_origin_and_a_human_form(self):
        task = self.fixture.require_plan()
        _, _, body = self.app.dispatch('GET', '/api/v1/tasks/1/control', self.headers)
        control = json.loads(body)['data']
        url = control['confirmation_urls']['approve_plan']
        path = url.split(f':{CONFIRM_PORT}', 1)[1]
        confirm_headers = {'Host': f'127.0.0.1:{CONFIRM_PORT}'}
        status, _, body = self.app.dispatch('GET', path, confirm_headers, confirmation=True)
        self.assertEqual(status, 200)
        self.assertEqual(self.fixture.store.get(1)['state'], 'awaiting_approval')
        token = re.search(r'name="token" value="([^"]+)"', body.decode())[1]
        payload = urlencode({'token': token, 'confirmation': 'TASK-001'}).encode()
        wrong = dict(confirm_headers, **{'Origin': f'http://127.0.0.1:{PORT}', 'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(self.app.dispatch('POST', '/confirm', wrong, payload, True)[0], 403)
        correct = dict(wrong, Origin=f'http://127.0.0.1:{CONFIRM_PORT}')
        with patch('harness.service.TaskService.start'):
            status, _, body = self.app.dispatch('POST', '/confirm', correct, payload, True)
        self.assertEqual(status, 200)
        self.assertIn('Решение сохранено', body.decode())
        self.assertEqual(self.fixture.store.get(1)['state'], 'queued')
        self.assertEqual(self.app.dispatch('POST', '/confirm', correct, payload, True)[0], 409)

    def test_high_action_cannot_use_the_regular_json_endpoint(self):
        task = self.fixture.require_plan()
        service = TaskService(self.root)
        try:
            control = Operator(service).control(1)
        finally:
            service.close()
        headers = dict(self.headers, **{'Origin': f'http://127.0.0.1:{PORT}', 'X-CSRF-Token': self.app.csrf,
                    'Content-Type': 'application/json', 'Idempotency-Key': 'high-key-123', 'If-Match': control['revision']})
        payload = json.dumps({'action': 'approve_plan', 'plan_version': control['plan']['version'], 'plan_digest': control['plan']['digest']}).encode()
        self.assertEqual(self.app.dispatch('POST', '/api/v1/tasks/1/actions', headers, payload)[0], 403)
        self.assertEqual(self.fixture.store.get(1)['state'], 'awaiting_approval')

    def test_status_exposes_project_backend(self):
        status, _, body = self.app.dispatch('GET', '/api/v1/status', self.headers)
        self.assertEqual(status, 200)
        data = json.loads(body)['data']
        self.assertIn('backend', data['project'])
        self.assertEqual(data['project']['backend'], 'codex')
