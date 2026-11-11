import json
import os
import sys
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness.integration import apply_accepted
from harness.integration_check import run_checks
from harness.security import git
from harness.state import atomic_json


class CandidateCheckTests(unittest.TestCase):
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

    def test_real_check_detects_semantic_conflict_without_touching_main(self):
        (self.store.root / 'consumer.py').write_text('from app import value\nassert value() == 1\n')
        git(self.store.root, 'add', 'consumer.py')
        git(self.store.root, '-c', 'commit.gpgsign=false', 'commit', '-m', 'consumer')
        before = git(self.store.root, 'rev-parse', 'HEAD')
        self.config['check'] = [sys.executable, '-B', 'consumer.py']
        atomic_json(self.store.home / 'config.json', self.config)
        with patch('harness.integration_check.doctor') as doctor, patch('harness.integration_check.sandbox_command', side_effect=lambda config, root, writable, command: command) as sandbox:
            with self.assertRaisesRegex(ValueError, 'Проверки объединённой'):
                apply_accepted(self.store, 1)
            doctor.assert_called_once()
            sandbox.assert_called_once()
            self.assertEqual(sandbox.call_args.args[3], self.config['check'])
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)
        self.assertIn('AssertionError', (self.store.folder(1) / 'integration-check/check.log').read_text())

    def test_scope_and_check_backend_are_preserved(self):
        task = self.store.get(1)
        task['data'].update(path_scope='app', stage_backends={'check': 'gemini'})
        workspace = self.store.folder(1) / 'candidate'
        (workspace / 'app').mkdir(parents=True)
        folder = self.store.folder(1) / 'checks'
        folder.mkdir()
        config = {**self.config, 'scope_checks': {'app': ['scoped-check']}}
        with patch('harness.integration_check.doctor') as doctor, patch('harness.integration_check.sandbox_command', return_value=['sandboxed']) as sandbox, patch('harness.integration_check.execute', return_value=0) as execute:
            result = run_checks(self.store, task, workspace, folder, config)
        self.assertEqual(result['scope'], 'app')
        self.assertEqual(result['backend'], 'gemini')
        self.assertEqual(doctor.call_args.args[0]['backend'], 'gemini')
        self.assertEqual(sandbox.call_args.args[1], workspace / 'app')
        self.assertEqual(sandbox.call_args.args[3], ['scoped-check'])
        self.assertEqual(execute.call_args.args[0], ['sandboxed'])

    def test_frontend_uses_prepared_toolchain(self):
        task = self.store.get(1)
        task['data']['frontend_toolchain'] = 'next-ui'
        workspace = self.store.folder(1) / 'workspace'
        folder = self.store.folder(1) / 'checks'
        folder.mkdir()
        def build(root, output, config, project_root=None):
            atomic_json(output / 'frontend-receipt.json', {'checks': [{'command': ['build'], 'exit_code': 0}]})
            return 0
        with patch('harness.node.check', side_effect=build) as check, patch('harness.integration_check.execute') as execute:
            result = run_checks(self.store, task, workspace, folder, self.config)
        check.assert_called_once()
        execute.assert_not_called()
        self.assertEqual(result['command'][0]['command'], ['build'])
        self.assertEqual(check.call_args.kwargs['project_root'], self.store.root)

    def test_surviving_check_process_blocks_duplicate_execution(self):
        folder = self.store.folder(1) / 'integration-check'
        folder.mkdir()
        atomic_json(folder / 'active.json', {'pid': os.getpid()})
        before = git(self.store.root, 'rev-parse', 'HEAD')
        with patch('harness.integration_check.run_checks') as checks:
            with self.assertRaisesRegex(RuntimeError, 'ещё выполняется'):
                apply_accepted(self.store, 1)
            checks.assert_not_called()
        self.assertEqual(git(self.store.root, 'rev-parse', 'HEAD'), before)
