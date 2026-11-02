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
from harness.tw import BLOCK, chat_command, connect, verify_servers


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

    def test_submit_preserves_text_without_start_when_requested(self):
        result = self.service.submit('original task', start=False)
        self.assertEqual(result['task']['state'], 'queued')
        self.assertEqual(self.service.store.get(1)['data']['request'], 'original task')
        self.assertFalse((self.root / '.harness/worker.json').exists())

    def test_mcp_can_request_approval_but_cannot_approve(self):
        server = Server(self.service)
        result = server.call('tw_submit', {'request': 'Review plan first', 'start': False, 'approval': 'approve-plan'})
        self.assertEqual(result['task']['approval_mode'], 'approve-plan')
        for name in ('tw_approve_plan', 'tw_revise_plan'):
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
