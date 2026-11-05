import json
import unittest

import test_harness as fixtures
from harness.integration import apply_accepted
from harness.security import git
from harness.state import atomic_json


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        self.fixture.run_task()
        self.fixture.cli('accept', '1', '--confirm', 'TASK-001')
        self.config = json.loads((self.store.home / 'config.json').read_text())
        self.config['integration_branch'] = git(self.store.root, 'symbolic-ref', '--short', 'HEAD').decode().strip()
        atomic_json(self.store.home / 'config.json', self.config)

    def tearDown(self):
        self.fixture.tearDown()

    def test_accepted_result_merges_and_retry_does_not_add_commits(self):
        record = apply_accepted(self.store, 1)
        self.assertIn('return 2', (self.store.root / 'app.py').read_text())
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD').decode().strip(), record['commit'])
        self.assertEqual(apply_accepted(self.store, 1), record)
        self.assertEqual(self.store.get(1)['data']['integration'], record)

    def test_dirty_main_preserves_user_changes_and_head(self):
        before = git(self.store.root, 'rev-parse', 'HEAD')
        path = self.store.root / 'app.py'
        path.write_text('user changes')
        with self.assertRaisesRegex(ValueError, 'изменения'):
            apply_accepted(self.store, 1)
        self.assertEqual(path.read_text(), 'user changes')
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)

    def test_conflict_aborts_without_leaving_main_half_merged(self):
        path = self.store.root / 'app.py'
        path.write_text('def value():\n    return 3\n')
        git(self.store.root, 'add', 'app.py')
        git(self.store.root, '-c', 'commit.gpgsign=false', 'commit', '-m', 'other change')
        before = git(self.store.root, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'конфликт'):
            apply_accepted(self.store, 1)
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)
        self.assertIn('return 3', path.read_text())
        self.assertFalse(git(self.store.root, 'diff', '--name-only', '--diff-filter=U').strip())

    def test_accept_combines_commit_and_apply_when_enabled(self):
        task = self.store.get(1)
        task['state'] = 'review'
        self.store.save(task, 'fixture_reopen')
        self.config.update(commit_after_accept=False, apply_after_accept=True)
        atomic_json(self.store.home / 'config.json', self.config)
        self.fixture.cli('accept', '1', '--confirm', 'TASK-001')
        self.assertIn('return 2', (self.store.root / 'app.py').read_text())
        self.assertIn('integration', self.store.get(1)['data'])

    def test_accept_reports_apply_failure_and_preserves_dirty_main(self):
        task = self.store.get(1)
        task['state'] = 'review'
        self.store.save(task, 'fixture_reopen')
        self.config.update(commit_after_accept=True, apply_after_accept=True)
        atomic_json(self.store.home / 'config.json', self.config)
        path = self.store.root / 'app.py'
        path.write_text('user changes')
        with self.assertRaises(SystemExit):
            self.fixture.cli('accept', '1', '--confirm', 'TASK-001')
        task = self.store.get(1)
        self.assertEqual(task['state'], 'accepted')
        self.assertIn('изменения', task['data']['integration_error'])
        self.assertNotIn('integration', task['data'])
        self.assertEqual(path.read_text(), 'user changes')

    def test_retry_preserves_original_integration_commit_after_other_changes(self):
        record = apply_accepted(self.store, 1)
        path = self.store.root / 'notes.md'
        path.write_text('later independent change')
        git(self.store.root, 'add', 'notes.md')
        git(self.store.root, '-c', 'commit.gpgsign=false', 'commit', '-m', 'later change')
        current = git(self.store.root, 'rev-parse', 'HEAD')
        self.assertEqual(apply_accepted(self.store, 1), record)
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), current)
