import json
import sys
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness.mcp import Server
from harness.project_commands import configure, inferred_npm_check
from harness.runner import lock
from harness.service import TaskService
from harness.state import atomic_json
from harness.tw import inferred_check


class ProjectCommandTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        self.config = json.loads((self.store.home / 'config.json').read_text())

    def tearDown(self):
        self.fixture.tearDown()

    def test_npm_tests_are_inferred_without_execution(self):
        atomic_json(self.store.root / 'package.json', {'scripts': {'dev': 'next dev', 'test': 'vitest run'}})
        with patch('subprocess.Popen') as execute:
            self.assertEqual(inferred_check(self.store.root), 'npm test')
            execute.assert_not_called()

    def test_unknown_manager_or_missing_test_does_not_invent_check(self):
        for package in ({'scripts': {'dev': 'nuxt dev'}}, {'scripts': {'test': ''}},
                        {'packageManager': 'pnpm@10', 'scripts': {'test': 'vitest run'}},
                        {'scripts': ['test']}):
            atomic_json(self.store.root / 'package.json', package)
            self.assertIsNone(inferred_npm_check(self.store.root))

    def test_package_symlink_is_not_followed(self):
        (self.store.root / 'package.json').symlink_to(self.store.root / 'app.py')
        with self.assertRaises(OSError):
            inferred_npm_check(self.store.root)

    def test_python_discovery_is_preserved(self):
        folder = self.store.root / 'tests'
        folder.mkdir()
        (folder / 'test_app.py').write_text('')
        self.assertIn('unittest discover', inferred_check(self.store.root))

    def test_run_is_only_saved_and_existing_settings_are_preserved(self):
        with patch('subprocess.Popen') as execute:
            result = configure(self.store, run='npm run dev -- --port 3001')
            execute.assert_not_called()
        config = json.loads((self.store.home / 'config.json').read_text())
        self.assertEqual(config['check'], self.config['check'])
        self.assertEqual(config['timeout'], self.config['timeout'])
        self.assertEqual(result['run'], ['npm', 'run', 'dev', '--', '--port', '3001'])
        self.assertEqual(result['run_status'], 'configuration_only')
        self.assertEqual(configure(self.store), result)
        self.assertIsNone(configure(self.store, clear_run=True)['run'])

    def test_compose_configuration_does_not_contact_daemon(self):
        with patch('subprocess.Popen') as execute:
            result = configure(self.store, run='docker compose up')
            execute.assert_not_called()
        self.assertEqual(result['run'], ['docker', 'compose', 'up'])
        self.assertEqual(result['run_status'], 'configuration_only')

    def test_invalid_combination_does_not_partially_change_settings(self):
        before = (self.store.home / 'config.json').read_bytes()
        with self.assertRaises(ValueError):
            configure(self.store, check=f'{sys.executable} -m unittest', run='npm run dev && echo unsafe')
        self.assertEqual((self.store.home / 'config.json').read_bytes(), before)

    def test_active_runner_or_integration_blocks_mutation_but_not_status(self):
        for name in ('runner.lock', 'git-results.lock'):
            with lock(self.store, name):
                self.assertEqual(configure(self.store)['check'], self.config['check'])
                with self.assertRaises(RuntimeError):
                    configure(self.store, run='npm run dev')
        self.assertNotIn('run_command', json.loads((self.store.home / 'config.json').read_text()))

    def test_cli_updates_check_and_mcp_cannot_configure(self):
        self.fixture.cli('configure', '--check', f'{sys.executable} -m unittest', '--run', 'npm run dev')
        self.assertEqual(configure(self.store)['check'][1:], ['-m', 'unittest'])
        service = TaskService(self.store.root)
        try:
            with self.assertRaises(ValueError):
                Server(service).call('tw_configure', {'run': 'npm run dev'})
        finally:
            service.close()
