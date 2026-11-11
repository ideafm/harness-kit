import json
import unittest

import test_harness as fixtures
from harness.integration import apply_accepted, deployment_receipt, prepare_deployment, frontend_root, frontend_snapshot
from unittest.mock import patch
from harness.node import source_digest
from harness.security import git
from harness.state import atomic_json
from harness.integration_check import run_checks as real_run_checks


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.check_patch = patch('harness.integration_check.run_checks', side_effect=self.fixture.integration_check)
        self.check = self.check_patch.start()
        self.addCleanup(self.check_patch.stop)
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
        self.assertFalse((self.store.folder(1) / 'git-worktree').exists())
        worktrees = git(self.store.root, 'worktree', 'list').decode().strip().splitlines()
        self.assertEqual(len(worktrees), 1)

    def test_dirty_main_preserves_user_changes_and_head(self):
        before = git(self.store.root, 'rev-parse', 'HEAD')
        path = self.store.root / 'app.py'
        path.write_text('user changes')
        with self.assertRaisesRegex(ValueError, 'изменения'):
            apply_accepted(self.store, 1)
        self.assertEqual(path.read_text(), 'user changes')
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)

    def test_combined_failure_keeps_main_and_dependents_waiting(self):
        dependent = self.store.add('use combined result', depends_on=[1])
        (self.store.root / 'consumer.py').write_text('from app import value\nassert value() == 1\n')
        git(self.store.root, 'add', 'consumer.py')
        git(self.store.root, '-c', 'commit.gpgsign=false', 'commit', '-m', 'independent consumer')
        before = git(self.store.root, 'rev-parse', 'HEAD')
        def incompatible(store, task, workspace, folder, config):
            self.assertIn('return 2', (workspace / 'app.py').read_text())
            self.assertIn('value() == 1', (workspace / 'consumer.py').read_text())
            self.assertFalse((workspace / '.env').exists())
            self.assertFalse((workspace / '.git').exists())
            self.assertFalse((workspace / 'alias.py').exists())
            (folder / 'check.log').write_text('consumer assertion failed')
            return {'exit_code': 1}
        self.check.side_effect = incompatible
        with self.assertRaisesRegex(ValueError, 'Проверки объединённой'):
            apply_accepted(self.store, 1)
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)
        self.assertIn('return 1', (self.store.root / 'app.py').read_text())
        self.assertTrue(self.store.dependency_wait(dependent))
        self.assertNotIn('integration', self.store.get(1)['data'])

    def test_changed_main_during_checks_is_preserved(self):
        before = git(self.store.root, 'rev-parse', 'HEAD')
        def changing(store, task, workspace, folder, config):
            (store.root / 'app.py').write_text('user edit during checks')
            return self.fixture.integration_check(store, task, workspace, folder, config)
        self.check.side_effect = changing
        with self.assertRaisesRegex(ValueError, 'изменилась во время'):
            apply_accepted(self.store, 1)
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)
        self.assertEqual((self.store.root / 'app.py').read_text(), 'user edit during checks')

    def test_advanced_head_requires_new_check(self):
        def changing(store, task, workspace, folder, config):
            (store.root / 'notes.md').write_text('new version')
            git(store.root, 'add', 'notes.md')
            git(store.root, '-c', 'commit.gpgsign=false', 'commit', '-m', 'concurrent change')
            return self.fixture.integration_check(store, task, workspace, folder, config)
        self.check.side_effect = changing
        with self.assertRaisesRegex(ValueError, 'изменилась во время'):
            apply_accepted(self.store, 1)
        self.assertIn('return 1', (self.store.root / 'app.py').read_text())
        self.check.side_effect = self.fixture.integration_check
        record = apply_accepted(self.store, 1)
        self.assertEqual(self.check.call_count, 2)
        self.assertEqual(record['check']['tree'], git(self.store.root, 'rev-parse', 'HEAD^{tree}').decode().strip())

    def test_checks_cannot_modify_candidate_sources(self):
        before = git(self.store.root, 'rev-parse', 'HEAD')
        def changing(store, task, workspace, folder, config):
            (workspace / 'app.py').write_text('modified by check')
            return self.fixture.integration_check(store, task, workspace, folder, config)
        self.check.side_effect = changing
        with self.assertRaisesRegex(ValueError, 'Исходники объединённой'):
            apply_accepted(self.store, 1)
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)

    def test_failed_isolation_never_merges(self):
        self.check.side_effect = real_run_checks
        before = git(self.store.root, 'rev-parse', 'HEAD')
        with patch('harness.integration_check.doctor', side_effect=RuntimeError('isolation failed')), patch('harness.integration_check.execute') as execute:
            with self.assertRaisesRegex(RuntimeError, 'isolation failed'):
                apply_accepted(self.store, 1)
            execute.assert_not_called()
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)

    def test_restart_after_merge_records_checked_tree_without_another_merge(self):
        with patch('harness.integration.remove_worktree', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                apply_accepted(self.store, 1)
        head = git(self.store.root, 'rev-parse', 'HEAD')
        record = apply_accepted(self.store, 1)
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), head)
        self.assertEqual(record['check']['exit_code'], 0)
        self.assertEqual(self.check.call_count, 1)

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

    def test_publication_uses_checked_integrated_receipt_without_replacing_original(self):
        original = self.store.folder(1) / 'frontend-receipt.json'
        atomic_json(original, {'source_digest': 'original task version'})
        folder = self.store.folder(1) / 'integrated-build'
        folder.mkdir()
        receipt = folder / 'frontend-receipt.json'
        atomic_json(receipt, {'source_digest': source_digest(self.store.root), 'checks': [{'exit_code': 0}]})
        self.assertEqual(deployment_receipt(self.store, 1), receipt)
        self.assertEqual(json.loads(original.read_text())['source_digest'], 'original task version')
        (self.store.root / 'app.py').write_text('changed after combined checks')
        with self.assertRaisesRegex(ValueError, 'основной версии'):
            deployment_receipt(self.store, 1)

    def test_integrated_receipt_cannot_be_a_symlink(self):
        folder = self.store.folder(1) / 'integrated-build'
        folder.mkdir()
        (folder / 'frontend-receipt.json').symlink_to(self.store.root / 'app.py')
        with self.assertRaisesRegex(ValueError, 'ссылкой'):
            deployment_receipt(self.store, 1)

    def test_original_task_receipt_cannot_publish_stale_sources(self):
        original = self.store.folder(1) / 'frontend-receipt.json'
        atomic_json(original, {'source_digest': 'old task sources', 'checks': [{'exit_code': 0}]})
        with self.assertRaisesRegex(ValueError, 'основной версии'):
            deployment_receipt(self.store, 1)
        def build(root, folder, config, project_root=None):
            atomic_json(folder / 'frontend-receipt.json',
                        {'source_digest': source_digest(root), 'checks': [{'exit_code': 0}]})
            return 0
        with patch('harness.node.check', side_effect=build) as check:
            receipt = prepare_deployment(self.store, 1)
            check.assert_called_once()
        self.assertEqual(receipt.parent.name, 'integrated-build')
        self.assertEqual(json.loads(original.read_text())['source_digest'], 'old task sources')
        with patch('harness.node.check') as check:
            self.assertEqual(prepare_deployment(self.store, 1), receipt)
            check.assert_not_called()

    def test_failed_combined_checks_do_not_return_old_task_export(self):
        atomic_json(self.store.folder(1) / 'frontend-receipt.json',
                    {'source_digest': 'old', 'checks': [{'exit_code': 0}]})
        with patch('harness.node.check', return_value=1):
            with self.assertRaisesRegex(ValueError, 'прежняя панель'):
                prepare_deployment(self.store, 1)

    def test_frontend_scope_is_relative_to_git_root_for_nested_project(self):
        from types import SimpleNamespace
        nested = self.store.root / 'web'
        nested.mkdir()
        store = SimpleNamespace(root=nested, git_toplevel=lambda: self.store.root, get=lambda ident: {})
        with patch('harness.runner.Runner') as runner:
            runner.return_value.task_scope_dir.return_value = 'web'
            self.assertEqual(frontend_root(store, 1), nested)

    def test_main_snapshot_excludes_generated_files_and_reads_current_tracked_sources(self):
        generated = self.store.root / 'node_modules'
        generated.mkdir()
        (generated / 'local.js').write_text('local dependency')
        (self.store.root / 'app.py').write_text('current tracked edit')
        with frontend_snapshot(self.store, 1) as source:
            self.assertFalse((source / 'node_modules').exists())
            self.assertEqual((source / 'app.py').read_text(), 'current tracked edit')
