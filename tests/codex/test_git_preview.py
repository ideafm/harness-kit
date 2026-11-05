import hashlib
import json
import unittest

import test_harness as fixtures
from harness.git_results import commit_accepted, prepare_worktree
from harness.node import source_digest
from harness.preview import Preview
from harness.security import git
from harness.state import atomic_json


class GitResultTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        self.fixture.run_task()

    def tearDown(self):
        self.fixture.tearDown()

    def test_only_accepted_results_commit_once_in_controller_worktree(self):
        with self.assertRaises(ValueError):
            commit_accepted(self.store, 1)
        original = git(self.store.root, 'rev-parse', 'HEAD')
        self.fixture.cli('accept', '1', '--confirm', 'TASK-001')
        record = commit_accepted(self.store, 1)
        self.assertEqual(commit_accepted(self.store, 1), record)
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), original)
        self.assertIn(b'return 2', git(self.store.root, 'show', record['commit'] + ':app.py'))
        from pathlib import Path
        worktree = Path(record['worktree'])
        self.assertFalse((worktree / '.env').exists())
        self.assertFalse((worktree / 'credentials.json').exists())
        self.assertIn('result_committed', [e['kind'] for e in self.store.events(1)])

    def test_accept_commits_when_project_policy_enabled(self):
        config = json.loads((self.store.home / 'config.json').read_text())
        config['commit_after_accept'] = True
        atomic_json(self.store.home / 'config.json', config)
        self.fixture.cli('accept', '1', '--confirm', 'TASK-001')
        self.assertTrue(self.store.get(1)['data']['git_result']['commit'])

    def test_changed_result_cannot_commit_after_accept(self):
        self.fixture.cli('accept', '1', '--confirm', 'TASK-001')
        (self.store.folder(1) / 'workspace/app.py').write_text('changed')
        with self.assertRaises(ValueError):
            commit_accepted(self.store, 1)

    def test_worktree_exists_before_accept_without_exposing_git_to_agent(self):
        task = self.store.get(1)
        worktree = prepare_worktree(self.store, task)
        self.assertEqual(git(worktree, 'rev-parse', 'HEAD').decode().strip(), task['data']['base'])
        from pathlib import Path
        self.assertFalse(Path(task['data']['workspace'], '.git').exists())
        self.assertFalse((worktree / '.env').exists())
        self.fixture.cli('accept', '1', '--confirm', 'TASK-001')
        self.assertEqual(commit_accepted(self.store, 1)['worktree'], str(worktree))


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        self.fixture.run_task()
        task = self.store.get(1)
        task['data']['frontend_toolchain'] = 'next-ui'
        self.store.save(task, 'fixture_preview')
        self.assets = self.store.folder(1) / 'export'
        self.assets.mkdir()
        body = b'<html><body>preview</body></html>'
        (self.assets / 'index.html').write_bytes(body)
        self.receipt = self.store.folder(1) / 'frontend-receipt.json'
        atomic_json(self.receipt, {'assets': {'index.html': hashlib.sha256(body).hexdigest()},
            'export': str(self.assets), 'source_digest': source_digest(self.store.folder(1) / 'workspace')})
        self.preview = Preview(self.store.root, 1)
        self.preview.publish(self.receipt)
        self.headers = {'Host': f'127.0.0.1:{self.preview.port}'}

    def tearDown(self):
        self.fixture.tearDown()

    def test_preview_serves_verified_export_and_rejects_mutated_asset(self):
        status, _, body = self.preview.dispatch('GET', '/', self.headers)
        self.assertEqual(status, 200)
        self.assertIn(b'tw-preview', body)
        (self.assets / 'index.html').write_text('changed')
        self.assertEqual(self.preview.dispatch('GET', '/', self.headers)[0], 404)
        self.assertEqual(self.preview.dispatch('GET', '/../app.py', self.headers)[0], 404)

    def test_preview_has_no_operator_or_confirmation_authority(self):
        self.assertEqual(self.preview.dispatch('POST', '/api/v1/tasks', self.headers)[0], 403)
        self.assertEqual(self.preview.dispatch('GET', '/api/v1/operations/id', self.headers)[0], 403)
        _, _, body = self.preview.dispatch('GET', '/api/v1/tasks/1/control', self.headers)
        data = json.loads(body)['data']
        self.assertEqual(data['allowed_actions'], [])
        self.assertEqual(data['confirmation_urls'], {})
        _, _, body = self.preview.dispatch('GET', '/api/v1/session', self.headers)
        self.assertFalse(json.loads(body)['data']['csrf_token'])
        headers = dict(self.headers, Origin='http://127.0.0.1:47831')
        self.assertEqual(self.preview.dispatch('GET', '/', headers)[0], 403)

    def test_preview_tracks_last_good_version_and_marks_source_difference(self):
        (self.store.folder(1) / 'workspace/app.py').write_text('new intermediate edits')
        self.preview.publish(self.receipt)
        _, _, body = self.preview.dispatch('GET', '/__preview/status', self.headers)
        data = json.loads(body)
        self.assertFalse(data['current'])
        self.assertEqual(self.preview.dispatch('GET', '/', self.headers)[0], 200)

    def test_rejection_removes_result_from_preview_without_changing_main(self):
        before = git(self.store.root, 'rev-parse', 'HEAD')
        self.fixture.cli('reject', '1', '--reason', 'Не подходит', '--confirm', 'TASK-001')
        self.assertEqual(self.preview.dispatch('GET', '/', self.headers)[0], 410)
        _, _, body = self.preview.dispatch('GET', '/__preview/status', self.headers)
        self.assertEqual(json.loads(body)['revision'], 'rejected')
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)
        self.assertTrue((self.store.folder(1) / 'workspace/app.py').is_file())

    def test_plain_static_project_rebuilds_without_exposing_non_web_sources(self):
        task = self.store.get(1)
        task['data'].pop('frontend_toolchain')
        self.store.save(task, 'fixture_static')
        workspace = self.store.folder(1) / 'workspace'
        (workspace / 'index.html').write_text('<html>first</html>')
        preview = Preview(self.store.root, 1)
        build = preview.home / 'static-first'
        build.mkdir()
        preview.build_static(build, source_digest(workspace))
        preview.publish(build / 'frontend-receipt.json')
        headers = {'Host': f'127.0.0.1:{preview.port}'}
        self.assertIn(b'first', preview.dispatch('GET', '/', headers)[2])
        self.assertEqual(preview.dispatch('GET', '/app.py', headers)[0], 404)
        first = preview.state['revision']
        (workspace / 'index.html').write_text('<html>second</html>')
        build = preview.home / 'static-second'
        build.mkdir()
        preview.build_static(build, source_digest(workspace))
        preview.publish(build / 'frontend-receipt.json')
        self.assertNotEqual(first, preview.state['revision'])
        self.assertIn(b'second', preview.dispatch('GET', '/', headers)[2])
