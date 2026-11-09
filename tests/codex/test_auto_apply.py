import json
import re
import unittest
from urllib.parse import urlencode
from unittest.mock import patch

import test_harness as fixtures
from harness.auto_apply import policy, set_policy, maybe_apply, recover, eligible
from harness.runner import Runner
from harness.service import TaskService
from harness.security import git
from harness.state import atomic_json
from harness.web import WebApplication, PORT, CONFIRM_PORT
from harness.projects import project_id
from harness.operator import OperatorError


class AutoApplyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        config = json.loads((self.store.home / 'config.json').read_text())
        config['integration_branch'] = git(self.store.root, 'symbolic-ref', '--short', 'HEAD').decode().strip()
        atomic_json(self.store.home / 'config.json', config)

    def tearDown(self):
        self.fixture.tearDown()

    def enable(self):
        return set_policy(self.store, True, policy(self.store)['revision'])

    def test_disabled_default_and_existing_ready_result_never_retroactively_applied(self):
        task, _ = self.fixture.run_task()
        self.assertEqual(task['state'], 'review')
        self.enable()
        self.assertFalse(maybe_apply(self.store, 1))
        self.assertEqual(self.store.get(1)['state'], 'review')

    def test_fresh_task_is_accepted_and_integrated_by_controller(self):
        self.enable()
        task, _ = self.fixture.run_task()
        self.assertEqual(task['state'], 'accepted')
        self.assertEqual(task['data']['accepted_by'], 'automatic')
        self.assertIn('integration', task['data'])
        self.assertFalse(task['data']['auto_apply_pending'])
        self.assertIn('return 2', (self.store.root / 'app.py').read_text())
        head = git(self.store.root, 'rev-parse', 'HEAD')
        recover(self.store)
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), head)

    def test_manual_override_and_human_verdict_remain_for_human(self):
        self.enable()
        task = self.store.get(1)
        task['data']['manual_acceptance'] = True
        self.store.save(task, 'fixture_manual')
        task, _ = self.fixture.run_task()
        self.assertEqual(task['state'], 'review')
        task['data']['manual_acceptance'] = False
        task['data']['review_verdict'] = 'human'
        self.store.save(task, 'fixture_human')
        self.assertFalse(maybe_apply(self.store, 1))

    def test_disable_and_reenable_does_not_reauthorize_inflight_task(self):
        self.enable()
        def check(workspace, folder):
            set_policy(self.store, False, policy(self.store)['revision'])
            self.enable()
            return self.fixture.check(workspace, folder)
        task, _ = self.fixture.run_task(check=check)
        self.assertEqual(task['state'], 'review')
        self.assertNotEqual(task['data']['auto_apply_generation'], policy(self.store)['generation'])

    def test_tampered_check_log_blocks_auto_acceptance(self):
        self.enable()
        def review():
            (self.store.folder(1) / 'check.log').write_text('tampered')
            return fixtures.response(verdict='pass', evidence=['criterion'])
        task, _ = self.fixture.run_task(backend=fixtures.FakeCodex({'review': [review]}))
        self.assertEqual(task['state'], 'review')
        self.assertIn('auto_apply_error', task['data'])
        self.assertNotIn('accepted_by', task['data'])

    def test_integration_failure_is_recorded_without_retries(self):
        self.enable()
        with patch('harness.integration.apply_accepted', side_effect=ValueError('merge conflict')) as apply:
            task, _ = self.fixture.run_task()
            self.assertEqual(task['state'], 'accepted')
            self.assertIn('merge conflict', task['data']['auto_apply_error'])
            recover(self.store)
            self.assertEqual(apply.call_count, 1)

    def test_crash_after_acceptance_recovers_even_when_policy_disabled(self):
        self.enable()
        with patch('harness.auto_apply.finish_integration'):
            task, _ = self.fixture.run_task()
        self.assertTrue(task['data']['auto_apply_pending'])
        set_policy(self.store, False, policy(self.store)['revision'])
        recover(self.store)
        task = self.store.get(1)
        self.assertIn('integration', task['data'])
        self.assertFalse(task['data']['auto_apply_pending'])

    def test_policy_form_requires_separate_origin_current_revision_and_one_time_token(self):
        assets = self.store.root / 'export'
        assets.mkdir()
        receipt = self.store.home / 'form-receipt.json'
        atomic_json(receipt, {'assets': {}})
        app = WebApplication(self.store.root, 'test', assets, receipt)
        path = '/policy/embed?project=' + project_id(self.store.root)
        headers = {'Host': f'127.0.0.1:{CONFIRM_PORT}'}
        status, _, body = app.dispatch('GET', path, headers, confirmation=True)
        self.assertEqual(status, 200)
        self.assertFalse(policy(self.store)['enabled'])
        token = re.search(r'name="token" value="([^"]+)"', body.decode())[1]
        payload = urlencode({'token': token, 'enabled': 'true'}).encode()
        headers.update({'Origin': f'http://127.0.0.1:{PORT}', 'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(app.dispatch('POST', '/policy/embed', headers, payload, True)[0], 403)
        headers['Origin'] = f'http://127.0.0.1:{CONFIRM_PORT}'
        self.assertEqual(app.dispatch('POST', '/policy/embed', headers, payload, True)[0], 200)
        self.assertTrue(policy(self.store)['enabled'])
        self.assertEqual(app.dispatch('POST', '/policy/embed', headers, payload, True)[0], 409)

    def test_manual_acceptance_is_persisted_by_creation(self):
        service = TaskService(self.store.root)
        try:
            result = service.submit('manual task', start=False, manual_acceptance=True)
            self.assertTrue(result['task']['manual_acceptance'])
        finally:
            service.close()

    def test_failed_task_does_not_stop_independent_queue(self):
        from argparse import Namespace
        from harness.cli import dispatch_store
        from harness.integration import apply_accepted
        self.enable()
        second = self.store.add('second independent task')['id']
        runner = Runner(self.store, backend=fixtures.FakeCodex(), check=self.fixture.check)
        def integrate(store, ident):
            if ident == 1:
                raise ValueError('conflict in first task')
            return apply_accepted(store, ident)
        with patch('harness.cli.Runner', return_value=runner), patch('harness.integration.apply_accepted', side_effect=integrate):
            dispatch_store(Namespace(command='worker', once=True, backend=None), self.store)
        self.assertIn('auto_apply_error', self.store.get(1)['data'])
        self.assertIn('integration', self.store.get(second)['data'])

    def test_stale_policy_form_cannot_overwrite_newer_setting(self):
        revision = policy(self.store)['revision']
        self.enable()
        with self.assertRaises(OperatorError) as error:
            set_policy(self.store, False, revision)
        self.assertEqual(error.exception.status, 409)
        self.assertTrue(policy(self.store)['enabled'])

    def test_missing_integration_configuration_cannot_enable_policy(self):
        config = json.loads((self.store.home / 'config.json').read_text())
        config.pop('integration_branch')
        atomic_json(self.store.home / 'config.json', config)
        with self.assertRaises(OperatorError):
            self.enable()
        self.assertFalse(policy(self.store)['enabled'])

    def test_controller_launchers_and_instruction_files_require_human(self):
        self.enable()
        task = {'state': 'review', 'stage': 'done', 'data': {'auto_apply_generation': policy(self.store)['generation'],
                'risk': 'low', 'scope': 'small', 'review_verdict': 'pass', 'check_receipt': {'exit_code': 0}}}
        for name in ('bin/tw', 'harness/security.py', 'web/AGENTS.md', 'web/package.json', 'web/next.config.mjs'):
            task['data']['files'] = [name]
            self.assertFalse(eligible(self.store, task))
