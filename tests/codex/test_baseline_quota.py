import contextlib
import io
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import test_harness as fixtures
from harness.baseline import prepare
from harness.quota import Guard, QuotaPause, normalize, read
from harness.runner import Runner
from harness.state import atomic_json


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.fixture.run_task()
        self.store = self.fixture.store
        task = self.store.add('Улучшить результат')
        task['state'] = 'running'
        self.store.save(task, 'fixture')
        Runner(self.store, backend=fixtures.FakeCodex()).prepare(task)
        task['state'] = 'waiting'
        task['data'].update(question='Нужна основа', question_kind='needs_input')
        self.store.save(task, 'fixture')

    def tearDown(self):
        self.fixture.tearDown()

    def test_baseline_copies_verified_result_without_accepting_or_applying(self):
        prepared = prepare(self.store, 2, 1)
        self.assertEqual(prepared['state'], 'waiting')
        self.assertEqual(prepared['data']['input_baseline']['source_task'], 1)
        self.assertEqual(self.store.get(1)['state'], 'review')
        self.assertIn('return 1', (self.fixture.root / 'app.py').read_text())
        self.assertIn('return 2', (self.store.folder(2) / 'workspace/app.py').read_text())
        self.assertIn('return 1', (self.store.folder(2) / 'workspace-before-baseline/app.py').read_text())
        self.assertFalse((self.store.folder(2) / 'baseline-preparing.json').exists())

    def test_diff_and_review_are_relative_to_verified_baseline(self):
        task = prepare(self.store, 2, 1)
        task['data']['files'] = ['app.py']
        (self.store.folder(2) / 'workspace/app.py').write_text('def value():\n    return 3\n')
        runner = Runner(self.store, backend=fixtures.FakeCodex())
        runner.report(task)
        diff = (self.store.folder(2) / 'changes.patch').read_text()
        self.assertIn('-    return 2', diff)
        self.assertIn('+    return 3', diff)
        self.assertIn('controller_input_baseline', runner.prompt(task))

    def test_tampered_source_is_rejected(self):
        (self.store.folder(1) / 'workspace/app.py').write_text('tampered')
        with self.assertRaises(ValueError):
            prepare(self.store, 2, 1)
        self.assertNotIn('input_baseline', self.store.get(2)['data'])

    def test_local_target_changes_are_preserved(self):
        path = self.store.folder(2) / 'workspace/app.py'
        path.write_text('local changes')
        with self.assertRaises(ValueError):
            prepare(self.store, 2, 1)
        self.assertEqual(path.read_text(), 'local changes')

    def test_tampered_baseline_blocks_report_and_restart(self):
        task = prepare(self.store, 2, 1)
        (self.store.folder(2) / 'input-baseline/app.py').write_text('tampered')
        runner = Runner(self.store, backend=fixtures.FakeCodex())
        with self.assertRaises(ValueError):
            runner.prepare(task)
        with self.assertRaises(ValueError):
            runner.report(task)

    def test_incomplete_preparation_fails_closed(self):
        atomic_json(self.store.folder(2) / 'baseline-preparing.json', {})
        with self.assertRaises(ValueError):
            prepare(self.store, 2, 1)
        with self.assertRaises(RuntimeError):
            Runner(self.store).prepare(self.store.get(2))

    def test_protected_source_and_repeated_preparation_are_rejected(self):
        prepare(self.store, 2, 1)
        with self.assertRaises(ValueError):
            prepare(self.store, 2, 1)
        (self.store.folder(2) / 'input-baseline/alias.py').symlink_to(self.fixture.root / 'app.py')
        with self.assertRaises(ValueError):
            Runner(self.store).report(self.store.get(2))


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        self.now = time.time()

    def tearDown(self):
        self.fixture.tearDown()

    def snapshot(self, used):
        return {'observed_at': time.time(), 'ordinary_usage_allowed': True,
                'windows': [{'window_minutes': 300, 'used_percent': used, 'resets_at': self.now + 3600}]}

    def test_selects_five_hour_window_and_rejects_stale_or_missing(self):
        result = {'rateLimits': {'primary': {'usedPercent': 81, 'windowDurationMins': 300, 'resetsAt': self.now + 3600}}}
        self.assertEqual(normalize(result, self.now)['windows'][0]['used_percent'], 81)
        result['rateLimits']['primary']['resetsAt'] = self.now - 1
        with self.assertRaises(ValueError):
            normalize(result, self.now)
        with self.assertRaises(ValueError):
            normalize({}, self.now)

    def test_new_stage_stops_at_90_and_active_at_94(self):
        guard = Guard(self.store, {'codex': 'codex', 'quota_guard': True})
        with patch('harness.quota.read', return_value=self.snapshot(95)):
            with self.assertRaises(QuotaPause) as error:
                guard.check(starting=True)
            self.assertEqual(error.exception.retry_at, self.now + 3660)
        guard.snapshot = self.snapshot(94.9)
        guard.check()
        guard.snapshot = self.snapshot(95)
        with self.assertRaises(QuotaPause):
            guard.check()

    def test_unavailable_read_stops_and_does_not_use_stale_value(self):
        guard = Guard(self.store, {'codex': 'codex', 'quota_guard': True})
        guard.snapshot = self.snapshot(1)
        with patch('harness.quota.read', side_effect=TimeoutError):
            with self.assertRaises(QuotaPause):
                guard.check(starting=True)
        self.assertIsNone(guard.snapshot)

    def test_fresh_low_value_after_reset_allows_resume(self):
        guard = Guard(self.store, {'codex': 'codex', 'quota_guard': True})
        guard.snapshot = self.snapshot(96)
        with patch('harness.quota.read', return_value=self.snapshot(2)) as fetch:
            guard.check(starting=True)
            fetch.assert_called_once()

    def test_codex_snapshot_ttl_120_seconds(self):
        guard = Guard(self.store, {'codex': 'codex', 'quota_guard': True})
        with patch('harness.quota.read', return_value=self.snapshot(2)) as fetch:
            guard.check(starting=True)
            self.assertEqual(fetch.call_count, 1)
            guard.check(starting=False)
            self.assertEqual(fetch.call_count, 1)
            guard.snapshots['codex']['observed_at'] -= 121
            guard.check(starting=False)
            self.assertEqual(fetch.call_count, 2)

    def test_wait_survives_restart_and_does_not_spend_attempts(self):
        config = {'codex': 'codex', 'check': ['python3'], 'timeout': 10, 'max_attempts': 3, 'quota_guard': True}
        atomic_json(self.store.home / 'config.json', config)
        backend = fixtures.FakeCodex()
        with patch('harness.quota.read', return_value=self.snapshot(95)):
            Runner(self.store, backend=backend).run(1)
        task = self.store.get(1)
        self.assertEqual(task['state'], 'rate_limited')
        self.assertEqual(task['data']['attempts'], {})
        self.assertEqual(backend.calls, [])
        with patch('harness.quota.read') as fetch:
            Runner(self.store, backend=backend).run(1)
            fetch.assert_not_called()

    def test_active_quota_stop_preserves_stage_and_attempt_budget(self):
        backend = fixtures.FakeCodex()
        runner = Runner(self.store, backend=backend)
        def stop(*args, **kwargs):
            if backend.calls:
                raise QuotaPause('stop', self.now + 3600)
        with patch.object(runner.quota, 'check', side_effect=stop), contextlib.redirect_stdout(io.StringIO()):
            runner.run(1)
        task = self.store.get(1)
        self.assertEqual(task['state'], 'rate_limited')
        self.assertEqual(task['stage'], 'implement')
        self.assertEqual(task['data']['attempts'], {'plan': 1})

    def test_reader_has_bounded_failure_for_dead_server(self):
        with self.assertRaises((RuntimeError, TimeoutError)):
            read('/usr/bin/false', timeout=1)

    def test_live_user_cap_stops_active_stage_at_50(self):
        guard = Guard(self.store, {'codex': 'codex', 'quota_guard': True})
        guard.snapshot = self.snapshot(49)
        atomic_json(self.store.home / 'quota-policy.json', {'stop_percent': 50})
        guard.check()
        guard.snapshot = self.snapshot(50)
        with self.assertRaises(QuotaPause) as error:
            guard.check()
        self.assertTrue(error.exception.manual)
        self.assertIsNone(error.exception.retry_at)

    def test_user_cap_pauses_without_automatic_retry_or_attempt_spending(self):
        config = {'codex': 'codex', 'check': ['python3'], 'timeout': 10, 'max_attempts': 3, 'quota_guard': True}
        atomic_json(self.store.home / 'config.json', config)
        atomic_json(self.store.home / 'quota-policy.json', {'stop_percent': 50})
        backend = fixtures.FakeCodex()
        with patch('harness.quota.read', return_value=self.snapshot(50)):
            Runner(self.store, backend=backend).run(1)
        task = self.store.get(1)
        self.assertEqual(task['state'], 'paused')
        self.assertNotIn('retry_at', task['data'])
        self.assertEqual(task['data']['attempts'], {})
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.store.events(1)[-1]['kind'], 'quota_stopped')
        with patch('harness.quota.read') as fetch:
            with self.assertRaises(ValueError):
                Runner(self.store, backend=backend).run(1)
            fetch.assert_not_called()

    def test_five_hour_user_cap_does_not_pause_for_secondary_window(self):
        atomic_json(self.store.home / 'quota-policy.json', {'stop_percent': 50})
        result = {'rateLimits': {
            'primary': {'usedPercent': 20, 'windowDurationMins': 300, 'resetsAt': self.now + 3600},
            'secondary': {'usedPercent': 67, 'windowDurationMins': 10080, 'resetsAt': self.now + 7200}}}
        guard = Guard(self.store, {'codex': 'codex', 'quota_guard': True})
        with patch('harness.quota.read', return_value=normalize(result, self.now)):
            guard.check(starting=True)

    def test_invalid_user_cap_fails_closed(self):
        guard = Guard(self.store, {'codex': 'codex', 'quota_guard': True})
        for cap in (True, 0, 96, '50'):
            with self.subTest(cap=cap):
                atomic_json(self.store.home / 'quota-policy.json', {'stop_percent': cap})
                with self.assertRaises(QuotaPause):
                    guard.check(starting=True)

    def test_next_window_checkpoint_does_not_stop_current_window(self):
        guard = Guard(self.store, {'codex': 'codex', 'quota_guard': True})
        activation = self.now + 3600
        atomic_json(self.store.home / 'quota-policy.json', {'stop_percent': 30, 'activate_at': activation})
        with patch('harness.quota.read', return_value=self.snapshot(52)):
            guard.check(starting=True)
        after = {'observed_at': activation + 1, 'ordinary_usage_allowed': True,
                 'windows': [{'window_minutes': 300, 'used_percent': 30, 'resets_at': activation + 18000}]}
        with patch('harness.quota.time.time', return_value=activation + 1), \
                patch('harness.quota.read', return_value=after):
            with self.assertRaises(QuotaPause) as error:
                Guard(self.store, guard.config).check(starting=True)
        self.assertTrue(error.exception.manual)

    def test_next_window_checkpoint_keeps_current_safety_ceiling(self):
        atomic_json(self.store.home / 'quota-policy.json', {'stop_percent': 30, 'activate_at': self.now + 3600})
        guard = Guard(self.store, {'codex': 'codex', 'quota_guard': True})
        with patch('harness.quota.read', return_value=self.snapshot(95)):
            with self.assertRaises(QuotaPause) as error:
                guard.check(starting=True)
        self.assertFalse(error.exception.manual)
