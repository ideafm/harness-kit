import base64
import json
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness.attachments import upload, load, context, images
from harness.operator import Operator
from harness.service import TaskService
from harness.execution_status import describe


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        self.service = TaskService(self.store.root)

    def tearDown(self):
        self.service.close()
        self.fixture.tearDown()

    def upload(self, name='reference.md', content=b'User design requirements'):
        return upload(self.store, {'name': name, 'content': base64.b64encode(content).decode()})

    def test_upload_repeat_and_submit_preserves_context(self):
        record = self.upload()
        self.assertEqual(self.upload(), record)
        payload = {'request': 'Use attachment', 'approval_mode': 'auto', 'placement': 'backlog', 'attachments': [record['id']]}
        operator = Operator(self.service)
        result = operator.perform(None, payload, 'attachment-create-key')
        self.assertEqual(operator.perform(None, payload, 'attachment-create-key'), result)
        task = self.store.get(result['task_id'])
        self.assertEqual(context(self.store, task)[0]['text'], 'User design requirements')
        self.assertEqual(self.service.show(task['id'])['attachments'], [record])
        self.assertEqual(images(self.store, task), [])

    def test_invalid_files_and_tampering_fail_closed(self):
        for name, content in [('../escape.md', b'hello'), ('.env', b'x'), ('page.html', b'<script>'), ('fake.png', b'not png'), ('binary.txt', b'\x00'), ('bad.txt', b'\xff'), ('large.log', b'x'*100001)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.upload(name, content)
        record = self.upload()
        folder = self.store.home / 'attachments'
        (folder / (record['id'] + '.md')).write_text('changed')
        with self.assertRaises(ValueError):
            load(self.store, record['id'])

    def test_symlink_and_foreign_attachment_cannot_be_used(self):
        record = self.upload()
        folder = self.store.home / 'attachments'
        path = folder / (record['id'] + '.md')
        path.unlink();path.symlink_to(self.store.root / 'app.py')
        with self.assertRaises(ValueError):
            load(self.store, record['id'])
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.service.submit('test', start=False, attachments=['a'*64])

    def test_images_are_native_inputs_outside_workspace(self):
        record = self.upload('screen.png', b'\x89PNG\r\n\x1a\nfixture')
        task = self.store.get(1)
        task['data']['attachments'] = [record]
        paths = images(self.store, task)
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].endswith('.png'))
        self.assertNotIn('workspace', paths[0])

    def test_execution_shows_attempt_wait_and_next_step(self):
        task = self.store.get(1)
        task.update(state='running', stage='check')
        task['data']['attempts'] = {'check': 2}
        events = [{'kind': 'stage_started', 'time': 100, 'data': {'stage': 'check'}}]
        value = describe(self.store, task, events, now=145)
        self.assertEqual(value['elapsed_seconds'], 45)
        self.assertEqual(value['attempt'], 2)
        self.assertIn('повторная', value['detail'])
        task['state'] = 'rate_limited'
        task['data'].update(retry_at=200, reason='лимит')
        value = describe(self.store, task, events, now=145)
        self.assertTrue(value['waiting'])
        self.assertEqual(value['retry_at'], 200)
        self.assertIsNone(value['started_at'])

    def test_api_upload_requires_csrf_and_download_is_task_scoped(self):
        from harness.web import WebApplication, PORT
        import hashlib
        assets = self.store.root / 'export'
        assets.mkdir()
        (assets / 'index.html').write_text('test')
        receipt = self.store.home / 'test-ui.json'
        receipt.write_text(json.dumps({'assets': {'index.html': hashlib.sha256(b'test').hexdigest()}}))
        app = WebApplication(self.store.root, 'test', assets, receipt)
        headers = {'Host': f'127.0.0.1:{PORT}'}
        body = json.dumps({'name': 'brief.md', 'content': base64.b64encode(b'brief').decode()}).encode()
        self.assertEqual(app.dispatch('POST', '/api/v1/attachments', headers, body)[0], 403)
        headers.update(Origin=f'http://127.0.0.1:{PORT}', **{'X-CSRF-Token': app.csrf, 'Content-Type': 'application/json'})
        status, _, response = app.dispatch('POST', '/api/v1/attachments', headers, body)
        self.assertEqual(status, 201)
        record = json.loads(response)['data']
        path = '/api/v1/tasks/1/attachments/' + record['id']
        self.assertEqual(app.dispatch('GET', path, headers)[0], 404)
        task = self.store.get(1)
        task['data']['attachments'] = [record]
        self.store.save(task, 'fixture')
        self.assertEqual(app.dispatch('GET', path, headers), (200, 'text/plain', b'brief'))

    def test_runner_context_contains_attachment_without_source_changes(self):
        from harness.runner import Runner
        record = self.upload()
        task = self.store.get(1)
        task['data']['attachments'] = [record]
        self.store.save(task, 'fixture')
        self.fixture.run_task()
        task = self.store.get(1)
        prompt = Runner(self.store).prompt(task | {'stage': 'plan'})
        self.assertIn('User design requirements', prompt)
        self.assertIn('недоверенные материалы', prompt)
        self.assertEqual([item['path'] for item in task['data']['changes']], ['app.py'])

    def test_codex_command_attaches_native_image(self):
        from harness.runner import Codex
        record = self.upload('screen.png', b'\x89PNG\r\n\x1a\nfixture')
        task = self.store.get(1)
        task['data']['attachments'] = [record]
        paths = images(self.store, task)
        folder = self.store.folder(1)
        config = json.loads((self.store.home / 'config.json').read_text())
        adapter = Codex({**config, 'attachment_images': paths})
        def execute(command, workspace, log, timeout, interrupted, prompt):
            self.assertEqual(command[command.index('--image') + 1], paths[0])
            (folder / 'plan.response.json').write_text(json.dumps(fixtures.response()))
            return 0
        with patch('harness.runner.execute', side_effect=execute):
            adapter.call('plan', self.store.root, folder, 'test prompt', lambda: False)

    def test_stale_worker_cannot_interrupt_active_task(self):
        task = self.store.get(1)
        task['state'] = 'running'
        self.store.save(task, 'fixture')
        with patch.object(self.service, 'worker_status', return_value={'running': True, 'stale': True}):
            with self.assertRaisesRegex(RuntimeError, 'Дождитесь завершения'):
                self.service.refresh_worker()
        self.assertTrue((self.store.home / 'worker.stop').exists())
        self.assertEqual(self.store.get(1)['state'], 'running')
