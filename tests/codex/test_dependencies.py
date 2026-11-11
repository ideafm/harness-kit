import json
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness.runner import Runner
from harness.integration import apply_accepted
from harness.service import TaskService
from harness.security import git
from harness.state import atomic_json
from harness.mcp import Server


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        checks = patch('harness.integration_check.run_checks', side_effect=self.fixture.integration_check)
        checks.start()
        self.addCleanup(checks.stop)
        self.store = self.fixture.store

    def tearDown(self):
        self.fixture.tearDown()

    def test_invalid_references_do_not_create_tasks(self):
        for dependencies in ([999], [1, 1], [True], [-1], '1'):
            with self.assertRaises(ValueError):
                self.store.add('invalid', depends_on=dependencies)
            self.assertEqual(len(self.store.tasks()), 1)

    def test_blocked_prerequisite_does_not_stop_independent_task(self):
        dependent = self.store.add('dependent', depends_on=[1])
        independent = self.store.add('independent')
        first = self.store.get(1)
        first['state'] = 'waiting'
        self.store.save(first, 'fixture_question')
        self.assertEqual([task['id'] for task in self.store.runnable()], [independent['id']])
        self.assertEqual(self.store.dependency_wait(dependent), [{'id': 1, 'state': 'waiting'}])

    def test_review_acceptance_and_incomplete_integration_do_not_release_dependency(self):
        dependent = self.store.add('dependent', depends_on=[1])
        first = self.store.get(1)
        for state, data in [('review', {}), ('accepted', {}), ('accepted', {'integration': {'commit': 'x'}, 'integration_in_progress': True}),
                            ('accepted', {'integration': {'commit': 'x'}, 'integration_error': 'conflict'})]:
            first['state'] = state
            for key in ('integration', 'integration_in_progress', 'integration_error'):
                first['data'].pop(key, None)
            first['data'].update(data)
            self.store.save(first, 'fixture_state')
            self.assertTrue(self.store.dependency_wait(dependent))

    def test_deleted_prerequisite_stays_a_dependency(self):
        dependent = self.store.add('dependent', depends_on=[1])
        self.store.delete(1)
        self.assertEqual(self.store.get(dependent['id'])['data']['depends_on'], [1])
        self.assertEqual(self.store.dependency_wait(dependent)[0]['state'], 'trashed')

    def test_blocked_dependency_prevents_backend_preflight(self):
        dependent = self.store.add('dependent', depends_on=[1])
        backend = fixtures.FakeCodex()
        with patch.object(backend, 'preflight') as preflight:
            Runner(self.store, backend=backend, check=self.fixture.check).run(dependent['id'])
            preflight.assert_not_called()
        self.assertEqual(self.store.get(dependent['id'])['state'], 'queued')

    def test_successful_application_releases_task_with_updated_base(self):
        dependent = self.store.add('dependent', depends_on=[1])
        self.fixture.run_task()
        self.fixture.cli('accept', '1', '--confirm', 'TASK-001')
        config = json.loads((self.store.home / 'config.json').read_text())
        config['integration_branch'] = git(self.store.root, 'symbolic-ref', '--short', 'HEAD').decode().strip()
        atomic_json(self.store.home / 'config.json', config)
        record = apply_accepted(self.store, 1)
        self.assertFalse(self.store.dependency_wait(dependent))
        def implement():
            (self.store.folder(dependent['id']) / 'workspace/app.py').write_text('def value():\n    return 3\n')
            return fixtures.response()
        backend = fixtures.FakeCodex({'implement': [implement]})
        Runner(self.store, backend=backend, check=self.fixture.check).run(dependent['id'])
        result = self.store.get(dependent['id'])
        self.assertEqual(result['data']['base'], record['commit'])
        self.assertEqual(result['data']['dependency_results'], [record])

    def test_mcp_and_cli_accept_explicit_dependencies(self):
        service = TaskService(self.store.root)
        try:
            result = Server(service).call('tw_submit', {'request': 'from MCP', 'placement': 'backlog', 'depends_on': [1], 'manual_acceptance': True})
            self.assertEqual(result['task']['depends_on'], [1])
            self.assertTrue(result['task']['manual_acceptance'])
        finally:
            service.close()
        self.fixture.cli('add', 'from CLI', '--backlog', '--depends-on', '1')
        self.assertEqual(self.store.tasks()[-1]['data']['depends_on'], [1])
