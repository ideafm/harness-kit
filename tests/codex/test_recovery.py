import unittest
from pathlib import Path

import test_harness as fixtures
from harness.approval import approve
from harness.recovery import retry_review
from harness.runner import Runner


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        task = self.fixture.require_plan()
        approve(self.store, 1, task['data']['plan_version'], 'TASK-001')
        self.fixture.run_task()
        task = self.store.get(1)
        task['state'], task['stage'] = 'blocked', 'implement'
        task['data']['attempts'].update(implement=4, check=3, review=1)
        task['data']['reason'] = 'attempt limit'
        self.store.save(task, 'fixture_blocked')

    def tearDown(self):
        self.fixture.tearDown()

    def test_review_retry_preserves_approved_plan_and_verified_result(self):
        before = self.store.get(1)
        retry_review(self.store, 1)
        after = self.store.get(1)
        self.assertEqual((after['state'], after['stage']), ('queued', 'review'))
        self.assertEqual(after['data']['plan_approval'], before['data']['plan_approval'])
        self.assertEqual(after['data']['criteria'], before['data']['criteria'])
        self.assertEqual(after['data']['attempts']['review'], 0)
        self.assertEqual(after['data']['attempts']['implement'], 4)
        prompt = Runner(self.store).prompt(after)
        self.assertIn('controller_plan_authorization', prompt)
        self.assertIn('controller_stage', prompt)
        self.assertIn('бессмысленную доработку', prompt)
        self.assertEqual(self.store.events(1)[-1]['data']['reason'], 'attempt limit')

    def test_changed_source_cannot_skip_new_checks(self):
        Path(self.store.get(1)['data']['workspace'], 'app.py').write_text('changed')
        with self.assertRaises(ValueError):
            retry_review(self.store, 1)
        self.assertEqual(self.store.get(1)['state'], 'blocked')

    def test_changed_check_log_cannot_skip_new_checks(self):
        (self.store.folder(1) / 'check.log').write_text('different')
        with self.assertRaises(ValueError):
            retry_review(self.store, 1)

    def test_resume_renews_downstream_attempts_and_preserves_history(self):
        self.fixture.cli('resume', '1')
        attempts = self.store.get(1)['data']['attempts']
        self.assertEqual(attempts, {'plan': 1, 'implement': 0, 'check': 0, 'review': 0})
        self.assertEqual(self.store.events(1)[-1]['data']['previous_attempts']['check'], 3)
