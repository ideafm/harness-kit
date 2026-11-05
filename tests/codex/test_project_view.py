import json
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness.project_view import ProjectView, configure, profile
from harness.security import git


class ProjectViewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        (self.store.root / 'index.html').write_text('<html><body>first</body></html>')
        git(self.store.root, 'add', 'index.html')
        git(self.store.root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'view fixture')
        configure(self.store, 'static')
        self.fixture.run_task()
        self.view = ProjectView(self.store.root)
        self.headers = {'Host': f'127.0.0.1:{self.view.port}'}

    def tearDown(self):
        self.fixture.tearDown()

    def body(self):
        status, _, body = self.view.dispatch('GET', '/', self.headers)
        self.assertEqual(status, 200)
        return body

    def test_checked_view_survives_workspace_changes_and_switches_to_working(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        self.assertIn(b'first', self.body())
        workspace = self.store.folder(1) / 'workspace'
        (workspace / 'index.html').write_text('<html>working version</html>')
        self.view.refresh()
        self.assertIn(b'first', self.body())
        self.assertFalse(self.view.state['workspace_current'])
        address = self.view.url
        self.view.select(1, 'working')
        self.view.refresh()
        self.assertIn(b'working version', self.body())
        self.assertEqual(self.view.url, address)

    def test_stale_build_cannot_replace_new_selection(self):
        initial = self.view.select(1, 'checked')
        build = self.view.build
        def change_selection(selection, settings):
            candidate = build(selection, settings)
            self.view.select(1, 'working')
            return candidate
        with patch.object(self.view, 'build', side_effect=change_selection):
            self.view.refresh()
        self.assertIsNone(self.view.preview)
        self.assertNotEqual(self.view.selection(), initial)

    def test_failed_new_build_preserves_previous_view(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        revision = self.view.state['revision']
        self.view.select(1, 'working')
        (self.store.folder(1) / 'workspace/index.html').unlink()
        with self.assertRaises(ValueError):
            self.view.refresh()
        self.assertEqual(self.view.state['revision'], revision)
        self.assertIn(b'first', self.body())

    def test_build_failure_status_preserves_view_and_clears_after_repair(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        self.view.select(1, 'working')
        path = self.store.folder(1) / 'workspace/index.html'
        path.unlink()
        with patch.object(self.view.stop_event, 'wait', side_effect=[False, True]):
            self.view.build_loop()
        self.assertFalse(self.view.state['current'])
        self.assertIn('error', self.view.state)
        self.assertIn(b'first', self.body())
        path.write_text('<html>repaired</html>')
        with patch.object(self.view.stop_event, 'wait', side_effect=[False, True]):
            self.view.build_loop()
        self.assertTrue(self.view.state['current'])
        self.assertNotIn('error', self.view.state)
        self.assertIn(b'repaired', self.body())

    def test_view_is_readonly_and_does_not_leak_operator_authority(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        self.assertEqual(self.view.dispatch('POST', '/api/v1/tasks', self.headers)[0], 403)
        for path in ('/api/v1/tasks/1/control', '/api/v1/capabilities', '/api/v1/session'):
            status, _, body = self.view.dispatch('GET', path, self.headers)
            self.assertEqual(status, 200)
            data = json.loads(body)['data']
            for name in ('allowed_actions', 'actions', 'confirmation_widgets', 'csrf_token'):
                if name in data:
                    self.assertFalse(data[name])
        self.assertEqual(self.view.dispatch('GET', '/', dict(self.headers, Origin='http://evil.invalid'))[0], 403)
        self.assertEqual(self.view.dispatch('GET', '/app.py', self.headers)[0], 404)

    def test_selection_and_profile_survive_restart_and_repeat_is_idempotent(self):
        selection = self.view.select(1, 'checked')
        restarted = ProjectView(self.store.root)
        self.assertEqual(restarted.select(1, 'checked'), selection)
        self.assertEqual(restarted.url, self.view.url)
        restarted.refresh()
        self.assertEqual(restarted.state['active_task'], 1)
        self.assertEqual(profile(self.store)['adapter'], 'static')

    def test_unknown_adapter_missing_proof_and_symlink_fail_closed(self):
        with self.assertRaises(ValueError):
            configure(self.store, 'container')
        receipt = self.store.folder(1) / 'runtime-receipt.json'
        receipt.unlink()
        self.view.select(1, 'checked')
        with self.assertRaises(ValueError):
            self.view.refresh()
        (self.view.home / 'selection.json').unlink()
        (self.view.home / 'selection.json').symlink_to(self.store.root / 'index.html')
        with self.assertRaises(ValueError):
            self.view.selection()

    def test_source_changes_during_checks_are_not_published_as_checked(self):
        self.fixture.task = self.store.add('another task')
        def mutate(workspace, folder):
            (folder / 'check.log').write_text('passed')
            (workspace / 'index.html').write_text('changed during checks')
            return 0
        with self.assertRaisesRegex(RuntimeError, 'Исходники изменились'):
            self.fixture.run_task(check=mutate)
        task = self.store.get(self.fixture.task['id'])
        self.assertEqual(task['state'], 'blocked')
        self.assertNotIn('check_receipt', task['data'])
        self.assertFalse((self.store.folder(task['id']) / 'runtime-receipt.json').exists())
