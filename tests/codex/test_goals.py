import json
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness.goals import submit, show, recheck
from harness.integration import apply_accepted
from harness.mcp import Server
from harness.runner import Runner
from harness.service import TaskService
from harness.security import git
from harness.state import Store, atomic_json


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        self.tasks = [{'key': 'first', 'request': 'Return 2', 'depends_on': []},
                      {'key': 'second', 'request': 'Return 3', 'depends_on': ['first']}]
        self.criteria = ['value returns 3', 'original request is satisfied']
        self.config = json.loads((self.store.home / 'config.json').read_text())
        self.config['integration_branch'] = git(self.store.root, 'symbolic-ref', '--short', 'HEAD').decode().strip()
        atomic_json(self.store.home / 'config.json', self.config)
        checks = patch('harness.integration_check.run_checks', side_effect=self.fixture.integration_check)
        checks.start()
        self.addCleanup(checks.stop)

    def tearDown(self):
        self.fixture.tearDown()

    def create(self, **options):
        return submit(self.store, 'Build the requested feature', self.criteria, self.tasks, 'goal-key', **options)

    def complete_children(self, goal):
        for number, ident in enumerate(goal['task_ids'].values(), 2):
            def implement():
                (self.store.folder(ident) / 'workspace/app.py').write_text(f'def value():\n    return {number}\n')
                return fixtures.response()
            Runner(self.store, backend=fixtures.FakeCodex({'implement': [implement]}), check=self.fixture.check).run(ident)
            self.fixture.cli('accept', str(ident), '--confirm', f'TASK-{ident:03}')
            apply_accepted(self.store, ident)

    def verify(self, goal, verdict='pass', check=None):
        backend = fixtures.FakeCodex({'plan': [fixtures.response(files=[])],
                                     'review': [fixtures.response(verdict=verdict, evidence=self.criteria)]})
        Runner(self.store, backend=backend, check=check or self.fixture.check).run(goal['verification_task'])
        return backend

    def test_atomic_creation_idempotency_and_dependency_mapping(self):
        goal = self.create()
        self.assertEqual(len(self.store.tasks()), 4)
        self.assertEqual(self.create(), goal)
        first, second = goal['task_ids'].values()
        self.assertEqual(self.store.get(second)['data']['depends_on'], [first])
        final = self.store.get(goal['verification_task'])
        self.assertEqual(final['data']['depends_on'], [first, second])
        self.assertTrue(final['data']['manual_acceptance'])
        self.assertTrue(final['data']['verification_only'])
        self.tasks[0]['request'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'другим планом'):
            self.create()
        self.assertEqual(len(self.store.tasks()), 4)

    def test_invalid_graph_and_partial_creation_roll_back(self):
        self.tasks[0]['depends_on'] = ['second']
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(len(self.store.tasks()), 1)
        self.tasks[0]['depends_on'] = []
        original = self.store.add
        calls = 0
        def fail(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('interrupted insertion')
            return original(*args, **kwargs)
        with patch.object(self.store, 'add', side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertEqual(len(self.store.tasks()), 1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM goals').fetchone()[0], 0)
        self.create()

    def test_backlog_and_original_approval_requirement_are_preserved(self):
        goal = submit(self.store, 'Сначала согласуй план большой задачи', self.criteria, self.tasks, 'approval', placement='backlog')
        for task in goal['tasks']:
            data = self.store.get(task['id'])
            self.assertEqual(data['state'], 'backlog')
            self.assertEqual(data['data']['approval_mode'], 'approve-plan')

    def test_mcp_validates_nested_payload_and_retry_does_not_duplicate(self):
        service = TaskService(self.store.root)
        self.addCleanup(service.close)
        server = Server(service)
        payload = {'request': 'feature', 'criteria': self.criteria, 'tasks': self.tasks,
                   'request_key': 'mcp-key', 'start': False}
        goal = server.call('tw_submit_goal', payload)['goal']
        self.assertEqual(server.call('tw_submit_goal', payload)['goal']['id'], goal['id'])
        self.assertEqual(server.call('tw_show_goal', {'goal': goal['id']})['request'], 'feature')
        self.assertEqual(len(server.call('tw_goals', {})), 1)
        with self.assertRaises(ValueError):
            server.call('tw_submit_goal', {**payload, 'tasks': [dict(self.tasks[0], command='unsafe')]})
        with self.assertRaises(ValueError):
            server.call('tw_submit_goal', {**payload, 'tasks': [dict(self.tasks[0], depends_on=[True])]})

    def test_full_chain_restart_verification_and_human_acceptance(self):
        goal = self.create()
        self.assertTrue(self.store.dependency_wait(self.store.get(goal['verification_task'])))
        self.complete_children(goal)
        reopened = Store(self.store.root)
        try:
            self.assertEqual(show(reopened, goal['id'])['state'], 'in_progress')
        finally:
            reopened.db.close()
        backend = self.verify(goal)
        self.assertEqual(backend.calls, ['plan', 'review'])
        final = self.store.get(goal['verification_task'])
        self.assertEqual(final['data']['criteria'], self.criteria)
        self.assertEqual(final['data']['changes'], [])
        self.assertEqual(show(self.store, goal['id'])['state'], 'awaiting_acceptance')
        ident = final['id']
        self.fixture.cli('accept', str(ident), '--confirm', f'TASK-{ident:03}')
        self.assertEqual(show(self.store, goal['id'])['state'], 'completed')
        (self.store.root / 'app.py').write_text('def value():\n    return 4\n')
        git(self.store.root, 'add', 'app.py')
        git(self.store.root, '-c', 'commit.gpgsign=false', 'commit', '-m', 'new result')
        self.assertEqual(show(self.store, goal['id'])['state'], 'stale_verification')

    def test_failed_goal_review_never_starts_implementation(self):
        goal = self.create()
        self.complete_children(goal)
        backend = self.verify(goal, verdict='fail')
        self.assertNotIn('implement', backend.calls)
        self.assertEqual(self.store.get(goal['verification_task'])['state'], 'blocked')
        self.assertEqual(show(self.store, goal['id'])['state'], 'needs_attention')

    def test_human_review_waits_for_explicit_final_acceptance(self):
        goal = self.create()
        self.complete_children(goal)
        self.verify(goal, verdict='human')
        self.assertEqual(show(self.store, goal['id'])['state'], 'awaiting_acceptance')
        ident = goal['verification_task']
        self.fixture.cli('accept', str(ident), '--confirm', f'TASK-{ident:03}')
        self.assertEqual(show(self.store, goal['id'])['state'], 'completed')

    def test_recheck_preserves_history_waits_for_repairs_and_is_idempotent(self):
        goal = self.create()
        self.complete_children(goal)
        self.verify(goal, verdict='fail')
        repair = self.store.add('repair remaining criterion')
        next_goal = recheck(self.store, goal['id'], 'repair-check', [repair['id']])
        self.assertNotEqual(next_goal['verification_task'], goal['verification_task'])
        self.assertEqual(recheck(self.store, goal['id'], 'repair-check', [repair['id']]), next_goal)
        self.assertTrue(self.store.dependency_wait(self.store.get(next_goal['verification_task'])))
        self.store.delete(repair['id'])
        self.assertEqual(show(self.store, goal['id'])['state'], 'needs_attention')
        self.assertEqual(self.store.get(goal['verification_task'])['state'], 'blocked')
        with self.assertRaises(ValueError):
            recheck(self.store, goal['id'], 'repair-check', [])

    def test_stale_goal_can_be_reverified_without_repeating_children(self):
        goal = self.create()
        self.complete_children(goal)
        self.verify(goal)
        original_count = len(self.store.tasks())
        (self.store.root / 'note.txt').write_text('new main')
        git(self.store.root, 'add', 'note.txt')
        git(self.store.root, '-c', 'commit.gpgsign=false', 'commit', '-m', 'new main')
        with self.assertRaises(SystemExit):
            self.fixture.cli('accept', str(goal['verification_task']), '--confirm', f"TASK-{goal['verification_task']:03}")
        refreshed = recheck(self.store, goal['id'], 'fresh-main')
        self.assertEqual(len(self.store.tasks()), original_count + 1)
        self.verify(refreshed)
        self.assertEqual(show(self.store, goal['id'])['state'], 'awaiting_acceptance')
        self.assertEqual(self.store.get(refreshed['verification_task'])['data']['base'], git(self.store.root, 'rev-parse', 'HEAD').decode().strip())

    def test_final_acceptance_can_use_normal_integration_policy(self):
        goal = self.create()
        self.complete_children(goal)
        self.verify(goal)
        self.config['apply_after_accept'] = True
        atomic_json(self.store.home / 'config.json', self.config)
        ident = goal['verification_task']
        self.fixture.cli('accept', str(ident), '--confirm', f'TASK-{ident:03}')
        self.assertEqual(show(self.store, goal['id'])['state'], 'completed')
        self.assertIn('integration', self.store.get(ident)['data'])

    def test_final_plan_cannot_request_writes(self):
        goal = self.create()
        self.complete_children(goal)
        with self.assertRaisesRegex(ValueError, 'пустой список'):
            Runner(self.store, backend=fixtures.FakeCodex(), check=self.fixture.check).run(goal['verification_task'])
        self.assertEqual(show(self.store, goal['id'])['state'], 'needs_attention')

    def test_failed_goal_checks_do_not_start_review_or_implementation(self):
        goal = self.create()
        self.complete_children(goal)
        def failure(workspace, folder):
            (folder / 'check.log').write_text('whole project failed')
            return 1
        backend = self.verify(goal, check=failure)
        self.assertEqual(backend.calls, ['plan'])
        self.assertEqual(show(self.store, goal['id'])['state'], 'needs_attention')

    def test_deleted_prerequisite_is_visible_without_stopping_unrelated_work(self):
        goal = self.create()
        first = goal['task_ids']['first']
        self.store.delete(first)
        status = show(self.store, goal['id'])
        self.assertEqual(status['blockers'][0]['task'], first)
        self.assertEqual(status['state'], 'needs_attention')
        self.assertIn(1, [task['id'] for task in self.store.runnable()])

    def test_cli_can_submit_and_inspect_goal(self):
        payload = {'request': 'feature', 'criteria': self.criteria, 'tasks': self.tasks,
                   'request_key': 'cli-key', 'start': False}
        self.fixture.cli('goal-submit', json.dumps(payload))
        self.fixture.cli('goal-show', '1')
        self.fixture.cli('goals')
        self.assertEqual(len(self.store.tasks()), 4)
