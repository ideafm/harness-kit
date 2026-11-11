import json
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness.project_view import ProjectView, configure, profile
from harness.operator import OperatorError
from harness.security import git
from harness.view_control import ViewControl, preview_descriptor
from harness.service import TaskService
from harness.web import WebApplication, PORT


class ProjectViewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        (self.store.root / 'index.html').write_text('<html><body>first</body></html>')
        git(self.store.root, 'add', 'index.html')
        git(self.store.root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'view fixture')
        configure(self.store, 'static')
        with patch.object(ProjectView, 'start', return_value={'running': True}):
            self.fixture.run_task()
        self.view = ProjectView(self.store.root)
        self.headers = {'Host': f'127.0.0.1:{self.view.port}'}

    def tearDown(self):
        self.fixture.tearDown()

    def body(self):
        status, _, body = self.view.dispatch('GET', '/', self.headers)
        self.assertEqual(status, 200)
        return body

    def test_manual_stop_survives_restart_and_prevents_automatic_publish(self):
        from harness.auto_preview import publish
        self.view.stop()
        self.assertTrue(ProjectView(self.store.root).status()['manually_stopped'])
        with patch.object(ProjectView, 'start') as start:
            publish(self.store, 1)
            start.assert_not_called()
        self.assertEqual(self.store.get(1)['state'], 'review')

    def test_failed_automatic_preview_preserves_review_result(self):
        from harness.auto_preview import publish
        with patch.object(ProjectView, 'start', side_effect=RuntimeError('port occupied')):
            publish(self.store, 1)
        task = self.store.get(1)
        self.assertEqual(task['state'], 'review')
        self.assertEqual(task['data']['preview_error'], 'port occupied')

    def test_stop_available_after_workspace_removed(self):
        task = self.store.get(1)
        task['data'].pop('workspace', None)
        self.store.save(task, 'workspace_removed')
        service = TaskService(self.store.root)
        self.addCleanup(service.close)
        operator = ViewControl(service)
        control = operator.get(1)
        self.assertFalse(control['available'])
        self.assertEqual(control['actions'], ['stop'])
        result = operator.perform(1, {'action': 'stop', 'mode': 'checked'},
                                  'stop-no-workspace', control['revision'])
        self.assertEqual(result['status'], 'succeeded')

    def test_interrupted_stop_is_rejected_after_newer_launch(self):
        service = TaskService(self.store.root)
        self.addCleanup(service.close)
        operator = ViewControl(service)
        revision = operator.get(1)['revision']
        payload = {'action': 'stop', 'mode': 'checked'}
        stop = ProjectView.stop
        def interrupted(view, *args, **kwargs):
            stop(view, *args, **kwargs)
            raise KeyboardInterrupt()
        with patch.object(ProjectView, 'stop', interrupted):
            with self.assertRaises(KeyboardInterrupt):
                operator.perform(1, payload, 'interrupted-stop-key', revision)
        self.view.write('lifecycle.json', {'manually_stopped': False, 'revision': 'new-launch'})
        result = operator.perform(1, payload, 'interrupted-stop-key', revision)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error']['code'], 'stale_revision')
        self.assertFalse(self.view.lifecycle()['manually_stopped'])

    def test_replayed_stop_cannot_stop_a_newer_launch(self):
        service = TaskService(self.store.root)
        self.addCleanup(service.close)
        operator = ViewControl(service)
        revision = operator.get(1)['revision']
        payload = {'action': 'stop', 'mode': 'checked'}
        result = operator.perform(1, payload, 'stop-preview-operation', revision)
        self.assertEqual(result['status'], 'succeeded')
        self.view.write('lifecycle.json', {'manually_stopped': False, 'revision': 'new-launch'})
        self.assertEqual(operator.perform(1, payload, 'stop-preview-operation', revision), result)
        self.assertFalse(self.view.lifecycle()['manually_stopped'])
        with self.assertRaises(OperatorError):
            self.view.stop('old-stop', revision, 1)
        self.assertFalse(self.view.lifecycle()['manually_stopped'])

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

    def test_restart_restores_published_snapshot_when_new_selection_is_broken(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        original_revision = self.view.state['revision']
        self.view.select(1, 'working')
        (self.store.folder(1) / 'workspace/index.html').unlink()
        (self.store.folder(1) / 'runtime-receipt.json').unlink()
        restarted = ProjectView(self.store.root)
        restarted.restore()
        self.assertIn(b'first', restarted.dispatch('GET', '/', self.headers)[2])
        self.assertEqual(restarted.state['revision'], original_revision)
        self.assertEqual(restarted.selection()['mode'], 'working')
        self.assertFalse(restarted.state['current'])
        with patch.object(restarted.stop_event, 'wait', side_effect=[False, True]):
            restarted.build_loop()
        self.assertIn('error', restarted.state)
        self.assertIn(b'first', restarted.dispatch('GET', '/', self.headers)[2])

    def test_restart_restores_working_export_without_its_source(self):
        self.view.select(1, 'working')
        self.view.refresh()
        (self.store.folder(1) / 'workspace/index.html').unlink()
        restarted = ProjectView(self.store.root)
        restarted.restore()
        self.assertEqual(restarted.state['mode'], 'working')
        self.assertFalse(restarted.state['current'])
        self.assertIn(b'first', restarted.dispatch('GET', '/', self.headers)[2])

    def test_restore_rejects_tampered_receipt_and_foreign_project(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        record = self.view.read('last-good.json')
        path = self.view.home / record['receipt']
        original = path.read_bytes()
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'receipt изменился'):
            ProjectView(self.store.root).restore()
        path.write_bytes(original)
        record['project_id'] = 'foreign'
        self.view.write('last-good.json', record)
        with self.assertRaisesRegex(ValueError, 'владелец'):
            ProjectView(self.store.root).restore()

    def test_restore_rejects_export_symlink_or_changed_asset(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        export = self.view.preview.app.assets
        asset = export / 'index.html'
        original = asset.read_bytes()
        asset.write_text('tampered')
        with self.assertRaises(OperatorError):
            ProjectView(self.store.root).restore()
        asset.write_bytes(original)
        moved = export.with_name('moved-export')
        export.rename(moved)
        export.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'экспорт'):
            ProjectView(self.store.root).restore()

    def test_restore_rejects_rejected_task(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        task = self.store.get(1)
        task['state'] = 'rejected'
        self.store.save(task, 'rejected')
        with self.assertRaisesRegex(ValueError, 'отклонена'):
            ProjectView(self.store.root).restore()

    def test_pinned_link_rejects_another_task_and_old_version(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        path = '/?__tw_task=1&__tw_version=' + self.view.state['source_digest']
        self.assertEqual(self.view.dispatch('GET', path, self.headers)[0], 200)
        self.assertEqual(self.view.dispatch('GET', path.replace('__tw_task=1', '__tw_task=2'), self.headers)[0], 409)
        self.assertEqual(self.view.dispatch('GET', '/?__tw_task=1', self.headers)[0], 409)
        self.view.select(1, 'working')
        (self.store.folder(1) / 'workspace/index.html').write_text('<html>changed</html>')
        self.view.refresh()
        self.assertEqual(self.view.dispatch('GET', path, self.headers)[0], 409)

    def test_view_operation_is_idempotent_and_cannot_restore_old_selection(self):
        service = TaskService(self.store.root)
        self.addCleanup(service.close)
        operator = ViewControl(service)
        revision = operator.get(1)['revision']
        payload = {'action': 'select', 'mode': 'checked'}
        with patch.object(ProjectView, 'start', return_value={'running': True}) as start:
            result = operator.perform(1, payload, 'view-operation-key', revision)
            self.assertEqual(result['status'], 'succeeded')
            selection = self.view.select(1, 'working')
            repeated = operator.perform(1, payload, 'view-operation-key', revision)
            self.assertEqual(result, repeated)
            start.assert_called_once()
        self.assertEqual(self.view.selection(), selection)
        with self.assertRaises(OperatorError) as stale:
            operator.perform(1, payload, 'new-view-operation', revision)
        self.assertEqual(stale.exception.status, 409)
        with self.assertRaises(OperatorError) as conflict:
            operator.perform(1, dict(payload, mode='working'), 'view-operation-key', revision)
        self.assertEqual(conflict.exception.status, 409)

    def test_interrupted_view_operation_resumes_without_reselecting(self):
        service = TaskService(self.store.root)
        self.addCleanup(service.close)
        operator = ViewControl(service)
        revision = operator.get(1)['revision']
        payload = {'action': 'select', 'mode': 'checked'}
        with patch.object(ProjectView, 'start', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                operator.perform(1, payload, 'interrupted-view-key', revision)
        selected = self.view.selection()
        with patch.object(ProjectView, 'start', return_value={'running': True}):
            result = operator.perform(1, payload, 'interrupted-view-key', revision)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(self.view.selection(), selected)

    def test_interrupted_operation_does_not_replace_a_newer_choice(self):
        service = TaskService(self.store.root)
        self.addCleanup(service.close)
        operator = ViewControl(service)
        revision = operator.get(1)['revision']
        payload = {'action': 'select', 'mode': 'checked'}
        with patch.object(ProjectView, 'start', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                operator.perform(1, payload, 'superseded-view-key', revision)
        selected = self.view.select(1, 'working')
        with patch.object(ProjectView, 'start') as start:
            result = operator.perform(1, payload, 'superseded-view-key', revision)
            start.assert_not_called()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error']['code'], 'stale_revision')
        self.assertEqual(self.view.selection(), selected)

    def test_view_api_enforces_origin_csrf_and_preconditions(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        app = WebApplication(self.store.root, 'test', self.view.preview.app.assets,
            self.view.preview.app.receipt)
        headers = {'Host': f'127.0.0.1:{PORT}'}
        path = '/api/v1/tasks/1/view'
        status, _, body = app.dispatch('GET', path, headers)
        self.assertEqual(status, 200)
        revision = json.loads(body)['data']['revision']
        payload = json.dumps({'action': 'select', 'mode': 'checked'}).encode()
        self.assertEqual(app.dispatch('POST', path, headers, payload)[0], 403)
        headers.update(Origin=f'http://127.0.0.1:{PORT}', **{'X-CSRF-Token': app.csrf,
            'Content-Type': 'application/json', 'Idempotency-Key': 'api-view-key-123', 'If-Match': revision})
        with patch.object(ProjectView, 'start', return_value={'running': True}):
            self.assertEqual(app.dispatch('POST', path, headers, payload)[0], 200)
        headers['If-Match'] = revision
        headers['Idempotency-Key'] = 'api-view-key-new'
        self.assertEqual(app.dispatch('POST', path, headers, payload)[0], 409)
        self.assertEqual(self.view.dispatch('POST', path, self.headers)[0], 403)
        self.assertIsNone(preview_descriptor(self.store.root, 1))

    def test_project_level_view_api_get_and_post(self):
        self.view.select(1, 'checked')
        self.view.refresh()
        app = WebApplication(self.store.root, 'test', self.view.preview.app.assets,
            self.view.preview.app.receipt)
        headers = {'Host': f'127.0.0.1:{PORT}'}
        path = '/api/v1/view'
        status, _, body = app.dispatch('GET', path, headers)
        self.assertEqual(status, 200)
        data = json.loads(body)['data']
        self.assertEqual(data['task_id'], 1)
        self.assertTrue(data['available'])
        self.assertIn('select', data['actions'])
        self.assertIn('stop', data['actions'])
        revision = data['revision']
        self.assertIsNotNone(revision)

        # Stop at project level
        payload = json.dumps({'action': 'stop', 'mode': 'checked'}).encode()
        post_headers = dict(headers, Origin=f'http://127.0.0.1:{PORT}', **{
            'X-CSRF-Token': app.csrf,
            'Content-Type': 'application/json',
            'Idempotency-Key': 'proj-stop-key-1',
            'If-Match': revision
        })
        with patch.object(ProjectView, 'stop') as stop_mock:
            status, _, stop_body = app.dispatch('POST', path, post_headers, payload)
            self.assertEqual(status, 200)
            stop_mock.assert_called_once()

        # Start/select at project level
        select_payload = json.dumps({'action': 'select', 'mode': 'checked'}).encode()
        status, _, get_body = app.dispatch('GET', path, headers)
        new_rev = json.loads(get_body)['data']['revision']
        post_headers.update({
            'Idempotency-Key': 'proj-select-key-1',
            'If-Match': new_rev
        })
        with patch.object(ProjectView, 'start', return_value={'running': True}):
            status, _, select_body = app.dispatch('POST', path, post_headers, select_payload)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(select_body)['data']['status'], 'succeeded')

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

    def test_foreign_project_id_in_selection_ignored_and_overwritable(self):
        (self.view.home / 'selection.json').unlink(missing_ok=True)
        (self.view.home / 'selection.json').write_text(json.dumps({
            'project_id': '0' * 16,
            'task': 1,
            'mode': 'checked',
            'revision': 'abc'
        }))
        self.assertIsNone(self.view.selection())
        new_sel = self.view.select(1, 'working')
        self.assertEqual(new_sel['project_id'], self.view.ident)
        self.assertEqual(self.view.selection(), new_sel)

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
