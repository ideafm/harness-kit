import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from harness.mcp import Server, serve
from harness.runner import lock
from harness.service import KIT, TaskService
from harness.state import Store, atomic_json
from harness.tw import BLOCK, chat_command, connect, verify_servers, main, register_project


class TwTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / 'Project With Spaces'
        self.root.mkdir()
        (self.root / '.harness').mkdir()
        atomic_json(self.root / '.harness/config.json', {'codex': 'codex', 'check': [sys.executable, '-m', 'unittest'],
                    'timeout': 30, 'max_attempts': 3, 'model': 'gpt-6.1-sol'})
        self.service = TaskService(self.root)

    def tearDown(self):
        self.service.close()
        self.temporary.cleanup()

    def connect(self):
        with contextlib.redirect_stdout(io.StringIO()):
            connect(self.root)

    def test_connect_preserves_agents_and_tasks_and_is_repeatable(self):
        (self.root / 'AGENTS.md').write_text('Keep my rules\n')
        self.service.submit('existing', start=False)
        self.connect()
        content = (self.root / 'AGENTS.md').read_text()
        self.assertTrue(content.startswith('Keep my rules'))
        self.assertIn(BLOCK.strip(), content)
        self.connect()
        self.assertEqual((self.root / 'AGENTS.md').read_text(), content)
        self.assertEqual(len(self.service.status()['tasks']), 1)
        self.assertTrue((self.root / '.agents/skills/tw/SKILL.md').is_file())

    def test_unknown_skill_is_not_read_or_overwritten(self):
        skill = self.root / '.agents/skills/tw/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('existing skill')
        with self.assertRaisesRegex(ValueError, 'не принадлежит'):
            self.connect()
        self.assertEqual(skill.read_text(), 'existing skill')
        self.assertFalse((self.root / 'AGENTS.md').exists())

    def test_modified_owned_skill_is_preserved(self):
        self.connect()
        skill = self.root / '.agents/skills/tw/SKILL.md'
        skill.write_text('my change')
        with self.assertRaisesRegex(ValueError, 'изменён вручную'):
            self.connect()
        self.assertEqual(skill.read_text(), 'my change')

    def test_source_controller_cannot_be_its_own_project(self):
        with self.assertRaises(ValueError):
            connect(KIT)

    def test_first_chat_connects_and_registers_before_launch(self):
        with patch('harness.tw.register_project') as register, \
                patch('harness.tw.doctor'), patch('harness.tw.verify_servers'), \
                patch('harness.tw.os.execvpe') as launch, contextlib.redirect_stdout(io.StringIO()):
            main(['chat', '--project', str(self.root)])
        self.assertTrue((self.root / '.harness/tw.json').is_file())
        register.assert_called_once_with(self.root)
        launch.assert_called_once()
        self.assertIn('"." = "read"', ' '.join(launch.call_args.args[1]))

    def test_unknown_check_fails_before_model_or_registration(self):
        (self.root / '.harness/config.json').unlink()
        with patch('harness.tw.inferred_check', return_value=None), \
                patch('harness.tw.sys.stdin.isatty', return_value=False), \
                patch('harness.tw.register_project') as register, patch('harness.tw.os.execvpe') as launch, \
                patch('harness.tw.harness_main', side_effect=ValueError('missing check')):
            with self.assertRaises((ValueError, SystemExit)):
                main(['chat', '--project', str(self.root)])
        launch.assert_not_called()
        register.assert_not_called()

    def test_connect_rejects_symlink_before_reading_target(self):
        alias = self.root.parent / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            connect(alias)
        self.assertFalse((self.root / 'AGENTS.md').exists())

    def test_connection_registers_in_panel_without_losing_tasks(self):
        from harness.projects import Projects, project_id
        panel = self.root.parent / 'tw-web'
        (panel / '.harness').mkdir(parents=True)
        atomic_json(panel / '.harness/config.json', {'codex': 'codex'})
        task = self.service.submit('keep existing', start=False)['task']
        with patch('harness.tw.KIT', self.root.parent / 'kit'):
            record = register_project(self.root)
            self.assertEqual(register_project(self.root), record)
        self.assertEqual(record['id'], project_id(self.root))
        self.assertIn(record['id'], [p['id'] for p in Projects(panel).listing()])
        self.assertEqual(self.service.show(task['id'])['request'], 'keep existing')

    def test_chat_has_readonly_permissions_and_required_mcp(self):
        command = chat_command(self.root)
        text = ' '.join(command)
        self.assertIn(str(self.root), command)
        self.assertIn('"required" = true', text)
        self.assertIn('"." = "read"', text)
        self.assertIn('approval_policy="never"', command)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)
        self.assertIn('features.hooks=false', command)

    def test_postforeign_mcp_rejects_session(self):
        result = Mock(stdout=json.dumps([{'name': 'tw', 'enabled': True}, {'name': 'foreign', 'enabled': True}]))
        with patch('harness.tw.subprocess.run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'посторонние'):
                verify_servers(chat_command(self.root))

    def test_only_tw_mcp_is_accepted(self):
        result = Mock(stdout=json.dumps([{'name': 'tw', 'enabled': True}]))
        with patch('harness.tw.subprocess.run', return_value=result):
            verify_servers(chat_command(self.root))

    def test_inherited_servers_are_disabled_in_launch_and_rechecked(self):
        foreign = 'foreign-server'
        initial = Mock(stdout=json.dumps([{'name': foreign, 'enabled': True}, {'name': 'tw', 'enabled': True}]))
        isolated = Mock(stdout=json.dumps([{'name': foreign, 'enabled': False}, {'name': 'tw', 'enabled': True}]))
        for headless in (False, True):
            with self.subTest(headless=headless):
                command = chat_command(self.root, headless=headless, prompt='status')
                with patch('harness.tw.subprocess.run', side_effect=[initial, isolated]) as run:
                    verify_servers(command)
                override = 'mcp_servers.' + foreign + '.enabled=false'
                if headless:
                    self.assertNotIn(override, command)
                    self.assertIn('--ignore-user-config', command)
                else:
                    self.assertIn(override, command)
                self.assertIn(override, run.call_args.args[0])
                self.assertEqual(command[-1], 'status')
                self.assertEqual(run.call_count, 2)

    def test_unsupported_server_name_fails_closed(self):
        result = Mock(stdout=json.dumps([{'name': 'foreign."quoted"', 'enabled': True}, {'name': 'tw', 'enabled': True}]))
        with patch('harness.tw.subprocess.run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'Имя MCP'):
                verify_servers(chat_command(self.root))

    def test_headless_without_ignore_user_config_fails_closed(self):
        command = chat_command(self.root, headless=True)
        command.remove('--ignore-user-config')
        with patch('harness.tw.subprocess.run') as run:
            with self.assertRaises(RuntimeError):
                verify_servers(command)
        run.assert_not_called()

    def test_missing_tw_rejects_without_retry(self):
        result = Mock(stdout=json.dumps([{'name': 'foreign', 'enabled': True}]))
        with patch('harness.tw.subprocess.run', return_value=result) as run:
            with self.assertRaises(RuntimeError):
                verify_servers(chat_command(self.root))
        self.assertEqual(run.call_count, 1)

    def test_isolation_recheck_failure_does_not_start_session(self):
        initial = Mock(stdout=json.dumps([{'name': 'foreign', 'enabled': True}, {'name': 'tw', 'enabled': True}]))
        with patch('harness.tw.subprocess.run', side_effect=[initial, subprocess.TimeoutExpired('codex', 30)]):
            with self.assertRaises(subprocess.TimeoutExpired):
                verify_servers(chat_command(self.root))

    def test_submit_preserves_text_without_start_when_requested(self):
        result = self.service.submit('original task', start=False)
        self.assertEqual(result['task']['state'], 'queued')
        self.assertEqual(self.service.store.get(1)['data']['request'], 'original task')
        self.assertFalse((self.root / '.harness/worker.json').exists())

    def test_mcp_can_request_approval_but_cannot_approve(self):
        server = Server(self.service)
        result = server.call('tw_submit', {'request': 'Review plan first', 'start': False, 'approval': 'approve-plan'})
        self.assertEqual(result['task']['approval_mode'], 'approve-plan')
        for name in ('tw_approve_plan', 'tw_revise_plan', 'tw_reject', 'tw_request_changes'):
            with self.assertRaises(ValueError):
                server.call(name, {'task': 1})

    def test_invalid_approval_mode_is_rejected_without_task(self):
        with self.assertRaises(ValueError):
            self.service.submit('task', start=False, approval_mode='unrestricted')
        self.assertEqual(self.service.status()['tasks'], [])

    def test_double_start_spawns_one_detached_worker(self):
        self.service.submit('task', start=False)
        with patch('harness.service.subprocess.Popen', return_value=Mock(pid=os.getpid())) as spawn:
            self.service.start(1)
            self.service.start(1)
        self.assertEqual(spawn.call_count, 1)
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertEqual(spawn.call_args.kwargs['stdin'], subprocess.DEVNULL)

    def test_foreground_worker_lock_prevents_second_process(self):
        self.service.submit('task', start=False)
        with lock(self.service.store, 'worker.lock'), patch('harness.service.subprocess.Popen') as spawn:
            result = self.service.start(1)
        spawn.assert_not_called()
        self.assertTrue(result['worker']['running'])

    def test_worker_status_detects_foreground_worker_without_pid_record(self):
        with lock(self.service.store, 'worker.lock'):
            self.assertTrue(self.service.worker_status()['running'])

    def test_stale_pid_record_is_not_a_running_worker(self):
        atomic_json(self.root / '.harness/worker.json', {'pid': os.getpid(), 'started': 0})
        self.assertFalse(self.service.worker_status()['running'])

    def test_unavailable_spawn_keeps_task_id(self):
        with patch('harness.service.subprocess.Popen', side_effect=OSError('cannot spawn')):
            result = self.service.submit('task')
        self.assertEqual(result['task']['id'], 1)
        self.assertIn('worker_error', result)

    def test_artifact_cannot_read_arbitrary_file_or_symlink(self):
        self.service.submit('task', start=False)
        with self.assertRaises(ValueError):
            self.service.artifact(1, '../../.env')
        folder = self.service.store.folder(1)
        (self.root / 'public.txt').write_text('public')
        (folder / 'plan.md').symlink_to(self.root / 'public.txt')
        with self.assertRaises(ValueError):
            self.service.artifact(1, 'plan')

    def test_stop_pauses_running_task(self):
        self.service.submit('task', start=False)
        task = self.service.store.get(1)
        task['state'] = 'running'
        self.service.store.save(task, 'test_running')
        self.service.stop()
        self.assertTrue((self.root / '.harness/worker.stop').exists())
        self.assertEqual(self.service.store.get(1)['state'], 'paused')

    def test_mcp_transport_has_only_protocol_messages(self):
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'tw_submit', 'arguments': {'request': 'task', 'start': False}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'tw_status', 'arguments': {}}},
        ]
        source = io.StringIO('\n'.join(map(json.dumps, requests)) + '\n')
        output = io.StringIO()
        serve(Server(self.service), source, output)
        replies = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([reply['id'] for reply in replies], [1, 2, 3, 4])
        self.assertEqual(len(json.loads(replies[-1]['result']['content'][0]['text'])['tasks']), 1)
        names = {tool['name'] for tool in replies[1]['result']['tools']}
        self.assertNotIn('tw_accept', names)
        self.assertNotIn('tw_grant', names)

    def test_mcp_rejects_unknown_action_extra_path_and_wrong_types(self):
        server = Server(self.service)
        server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})
        for name, args in [('tw_accept', {'task': 1}), ('tw_status', {'project': '/elsewhere'}),
                           ('tw_show', {'task': True}), ('tw_submit', {'request': 'x', 'start': 'yes'}),
                           ('tw_answer', {'task': 1, 'text': ''})]:
            with self.subTest(name=name):
                result = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                        'params': {'name': name, 'arguments': args}})
                self.assertTrue(result['result']['isError'])
        self.assertEqual(self.service.store.tasks(), [])

    def test_tools_require_initialize(self):
        response = Server(self.service).handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        self.assertIn('error', response)

    def test_initialize_negotiates_supported_client_versions(self):
        for version in ('2024-11-05', '2025-06-18'):
            server = Server(self.service)
            response = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                                      'params': {'protocolVersion': version}})
            self.assertEqual(response['result']['protocolVersion'], version)

    def test_initialize_offers_current_version_for_unknown_client(self):
        server = Server(self.service)
        response = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                                  'params': {'protocolVersion': 'unknown'}})
        self.assertEqual(response['result']['protocolVersion'], '2025-06-18')


if __name__ == '__main__':
    unittest.main()
