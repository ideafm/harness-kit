import contextlib
import io
import json
import unittest
from argparse import Namespace
from unittest.mock import patch

import test_harness as fixtures
from harness.cli import dispatch_store
from harness.mcp import Server
from harness.operator import Operator, OperatorError
from harness.queue_control import QueueControl
from harness.service import TaskService
from harness.state import atomic_json
from harness.web import PORT, WebApplication
from harness.projects import project_id


class BacklogQueueTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.service = TaskService(self.fixture.root)
        self.store = self.service.store

    def tearDown(self):
        self.service.close()
        self.fixture.tearDown()

    def test_backlog_is_not_runnable_even_with_existing_worker(self):
        with patch.object(self.service, 'start') as start, patch.object(self.service, 'worker_status', return_value={'running': True}):
            result = self.service.submit('later', start=True, placement='backlog')
            start.assert_not_called()
        ident = result['task']['id']
        self.assertEqual(self.store.get(ident)['state'], 'backlog')
        self.assertNotIn(ident, [task['id'] for task in self.store.runnable()])
        with self.assertRaises(ValueError):
            self.service.start(ident)

    def test_enqueue_preserves_group_order_after_new_connection(self):
        second = self.store.add('second', placement='backlog')['id']
        third = self.store.add('third', placement='backlog')['id']
        self.service.enqueue([third, second])
        other = TaskService(self.fixture.root)
        try:
            self.assertEqual([task['id'] for task in other.store.runnable()], [1, third, second])
        finally:
            other.close()

    def test_invalid_group_rolls_back_every_task(self):
        second = self.store.add('second', placement='backlog')['id']
        first = self.store.get(1)
        first['state'] = 'review'
        self.store.save(first, 'fixture_review')
        for group in ([second, 1], [second, 999], [second, second], [True], [], '2'):
            with self.assertRaises(ValueError):
                self.service.enqueue(group)
            self.assertEqual(self.store.get(second)['state'], 'backlog')
            self.assertNotIn('queue_order', self.store.get(second)['data'])

    def test_worker_rechecks_order_and_skips_backlog(self):
        second = self.store.add('second')['id']
        third = self.store.add('third')['id']
        backlog = self.store.add('later', placement='backlog')['id']
        visited = []
        def execute(ident):
            visited.append(ident)
            if ident == 1:
                self.store.enqueue([third, second])
            task = self.store.get(ident)
            task['state'] = 'review'
            self.store.save(task, 'fixture_done')
        with patch('harness.cli.Runner') as runner, contextlib.redirect_stdout(io.StringIO()):
            runner.return_value.run.side_effect = execute
            dispatch_store(Namespace(command='worker', once=True), self.store)
        self.assertEqual(visited, [1, third, second])
        self.assertEqual(self.store.get(backlog)['state'], 'backlog')

    def test_mcp_explicit_backlog_and_enqueue(self):
        server = Server(self.service)
        with patch.object(self.service, 'start') as start:
            result = server.call('tw_submit', {'request': 'later', 'placement': 'backlog'})
            ident = result['task']['id']
            start.assert_not_called()
            server.call('tw_enqueue', {'tasks': [ident], 'start': True})
            start.assert_called_once_with(ident)
        self.assertEqual(self.store.get(ident)['state'], 'queued')

    def test_api_creation_backlog_and_queue_idempotency(self):
        operator = Operator(self.service)
        with patch.object(self.service, 'start') as start:
            created = operator.perform(None, {'request': 'later', 'approval_mode': 'auto', 'placement': 'backlog'}, 'backlog-create-key')
            start.assert_not_called()
        ident = created['task_id']
        queue = QueueControl(self.service)
        revision = queue.get()['revision']
        payload = {'tasks': [ident], 'start': True}
        with patch.object(self.service, 'start') as start:
            first = queue.perform(payload, 'queue-start-key', revision)
            repeated = queue.perform(payload, 'queue-start-key', revision)
            self.assertEqual(first, repeated)
            self.assertEqual(first['status'], 'succeeded')
            start.assert_called_once_with(ident)
        with self.assertRaises(OperatorError) as stale:
            queue.perform(payload, 'queue-start-new-key', revision)
        self.assertEqual(stale.exception.status, 409)

    def test_interrupted_queue_start_retries_without_reordering(self):
        ident = self.store.add('later', placement='backlog')['id']
        queue = QueueControl(self.service)
        revision = queue.get()['revision']
        payload = {'tasks': [ident], 'start': True}
        with patch.object(self.service, 'start', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                queue.perform(payload, 'interrupted-queue-key', revision)
        order = self.store.get(ident)['data']['queue_order']
        with patch.object(self.service, 'start') as start:
            result = queue.perform(payload, 'interrupted-queue-key', revision)
            start.assert_called_once_with(ident)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(self.store.get(ident)['data']['queue_order'], order)

    def test_queue_http_contract_checks_csrf_scope_and_revision(self):
        receipt = self.store.home / 'queue-ui.json'
        atomic_json(receipt, {'assets': {}})
        app = WebApplication(self.store.root, 'fixture', self.store.root, receipt)
        ident = self.store.add('later', placement='backlog')['id']
        path = '/api/v1/projects/' + project_id(self.store.root) + '/queue'
        headers = {'Host': f'127.0.0.1:{PORT}'}
        status, _, body = app.dispatch('GET', path, headers)
        self.assertEqual(status, 200)
        revision = json.loads(body)['data']['revision']
        payload = json.dumps({'tasks': [ident], 'start': False}).encode()
        self.assertEqual(app.dispatch('POST', path, headers, payload)[0], 403)
        headers.update(Origin=f'http://127.0.0.1:{PORT}', **{'X-CSRF-Token': app.csrf,
            'Content-Type': 'application/json', 'Idempotency-Key': 'http-queue-key', 'If-Match': revision})
        status, _, body = app.dispatch('POST', path, headers, payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['data']['status'], 'succeeded')
        headers['Idempotency-Key'] = 'http-queue-stale'
        self.assertEqual(app.dispatch('POST', path, headers, payload)[0], 409)
        self.assertEqual(app.dispatch('GET', '/api/v1/projects/0000000000000000/queue', headers)[0], 404)
