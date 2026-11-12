import contextlib
import io
import json
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness.execution_profiles import SOL, ASTRA, escalate
from harness.runner import Runner
from harness.service import TaskService
from harness.approval import approve
from harness.operator import Operator


class ExecutionProfileTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store

    def tearDown(self):
        self.fixture.tearDown()

    def configure(self, **values):
        path = self.store.home / 'config.json'
        config = json.loads(path.read_text())
        config.update(values)
        path.write_text(json.dumps(config))

    def test_legacy_task_and_new_defaults_are_snapshotted_separately(self):
        self.configure(execution_profile='auto-balanced')
        old = self.store.get(1)
        self.assertNotIn('execution_policy', old['data'])
        task = self.store.add('new')
        self.assertEqual(Runner(self.store).task_model(task, 'plan'), SOL)
        self.configure(execution_profile='thorough')
        self.assertEqual(Runner(self.store).task_model(task, 'plan'), SOL)
        self.assertNotIn('execution_policy', self.store.get(1)['data'])
        strong = self.store.add('strong')
        self.assertEqual(Runner(self.store).task_model(strong, 'plan'), ASTRA)
        self.assertEqual(Runner(self.store).task_model(strong, 'implement'), SOL)

    def test_gemini_executor_never_receives_gpt_model(self):
        self.configure(execution_profile='auto-balanced', model=ASTRA, gemini_model='configured-gemini')
        task = self.store.add('new', backend='gemini')
        runner = Runner(self.store)
        self.assertEqual(runner.task_backend(task, 'plan'), 'codex')
        self.assertEqual(runner.task_backend(task, 'implement'), 'gemini')
        self.assertEqual(runner.task_model(task, 'implement'), 'configured-gemini')
        self.assertEqual(runner.task_backend(task, 'review'), 'codex')
        self.configure(gemini_model='')
        default_task = self.store.add('agent default', backend='gemini')
        self.assertEqual(Runner(self.store).adapter_for(default_task, stage='implement').config['model'], '')

    def test_explicit_overrides_remain_manual_and_conflicts_fail(self):
        self.configure(execution_profile='auto-balanced')
        task = self.store.add('manual', model='custom-model')
        self.assertEqual(task['data']['execution_profile'], 'manual')
        with self.assertRaises(ValueError):
            self.store.add('conflict', execution_profile='auto-balanced', stage_models={'plan': 'custom'})
        task = self.store.add('manual profile', execution_profile='manual')
        self.assertNotIn('execution_policy', task['data'])

    def test_retry_escalation_is_monotonic_and_respects_attempt_limit(self):
        task = self.store.add('new', backend='gemini', execution_profile='auto-balanced')
        task['stage'] = 'implement'
        task['data']['attempts']['implement'] = 2
        self.assertEqual(escalate(task, 4)['model'], SOL)
        task['data']['attempts']['implement'] = 3
        self.assertEqual(escalate(task, 4)['model'], ASTRA)
        task['data']['attempts']['implement'] = 0
        self.assertIsNone(escalate(task, 4))
        self.assertEqual(Runner(self.store).task_model(task), ASTRA)
        task['data']['attempts']['implement'] = 4
        self.assertIsNone(escalate(task, 4))

    def test_risk_triggers_astra_replanning_before_implementation(self):
        task = self.store.add('feature', execution_profile='auto-balanced')
        calls = []
        replies = {'plan': [fixtures.response(risk='high'), fixtures.response()]}
        class Routed(fixtures.FakeCodex):
            def __init__(self, config, backend):
                super().__init__(replies)
                self.config = config
                self.selected = backend
            def call(self, stage, *args):
                calls.append((stage, self.selected, self.config.get('model')))
                return super().call(stage, *args)
        factory = lambda config, backend=None: Routed(config, backend or config.get('backend', 'codex'))
        with patch('harness.runner.create_backend', side_effect=factory), contextlib.redirect_stdout(io.StringIO()):
            Runner(self.store, check=self.fixture.check).run(task['id'])
            task = self.store.get(task['id'])
            self.assertEqual(task['state'], 'awaiting_approval')
            self.assertEqual(calls, [('plan', 'codex', SOL), ('plan', 'codex', ASTRA)])
            approve(self.store, task['id'], task['data']['plan_version'], f"TASK-{task['id']:03}")
            Runner(self.store, check=self.fixture.check).run(task['id'])
        self.assertIn(('implement', 'codex', SOL), calls)
        self.assertIn(('review', 'codex', ASTRA), calls)
        self.assertEqual(self.store.get(task['id'])['state'], 'review')

    def test_api_task_profile_and_route_metadata(self):
        service = TaskService(self.store.root)
        try:
            result = Operator(service).perform(None, {'request': 'new', 'approval_mode': 'auto', 'placement': 'backlog', 'execution_profile': 'thorough'}, 'profile-create-request')
            task = service.show(result['task_id'])
            self.assertEqual(task['execution_policy']['stages']['plan']['model'], ASTRA)
            self.assertEqual(task['execution_profile'], 'thorough')
        finally:
            service.close()

    def test_new_project_init_defaults_to_balanced(self):
        import tempfile
        from pathlib import Path
        from harness.security import git
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / 'project'
            root.mkdir()
            git(root, 'init', '-q')
            git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'fixture')
            with patch('harness.cli.shutil.which', return_value='/usr/bin/true'), contextlib.redirect_stdout(io.StringIO()):
                from harness.cli import main
                main(['--project', str(root), 'init', '--check', 'true'])
            config = json.loads((root / '.harness/config.json').read_text())
            self.assertEqual(config['execution_profile'], 'auto-balanced')

    def test_failed_checks_escalate_executor_but_keep_independent_review(self):
        self.configure(gemini_model='configured-gemini')
        task = self.store.add('feature', backend='gemini', execution_profile='auto-balanced')
        calls = []
        class Routed(fixtures.FakeCodex):
            def __init__(self, config, backend):
                super().__init__()
                self.config, self.selected = config, backend
            def call(self, stage, *args):
                calls.append((stage, self.selected, self.config.get('model')))
                return super().call(stage, *args)
        checks = []
        def check(workspace, folder):
            checks.append(1)
            code = 1 if len(checks) < 3 else 0
            (folder / 'check.log').write_text('failed' if code else 'passed')
            return code
        factory = lambda config, backend=None: Routed(config, backend or config.get('backend', 'codex'))
        with patch('harness.runner.create_backend', side_effect=factory), contextlib.redirect_stdout(io.StringIO()):
            Runner(self.store, check=check).run(task['id'])
        implementations = [item for item in calls if item[0] == 'implement']
        self.assertEqual(implementations, [('implement', 'gemini', 'configured-gemini'), ('implement', 'gemini', 'configured-gemini'), ('implement', 'codex', SOL)])
        self.assertEqual(calls[-1], ('review', 'codex', SOL))
        self.assertEqual(self.store.get(task['id'])['state'], 'review')
