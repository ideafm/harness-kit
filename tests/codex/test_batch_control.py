import json
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness.batch_control import BatchControl
from harness.operator import OperatorError
from harness.queue_control import QueueControl
from harness.service import TaskService
from harness.web import WebApplication, PORT
from harness.state import atomic_json


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.service = TaskService(self.fixture.root)
        self.store = self.service.store
        self.second = self.store.add('second', placement='backlog')['id']
        self.batch = BatchControl(self.service)

    def tearDown(self):
        self.service.close()
        self.fixture.tearDown()

    def revision(self):
        return QueueControl(self.service).get()['revision']

    def test_atomic_delete_and_idempotency(self):
        revision = self.revision()
        payload = {'action': 'delete', 'tasks': [1, self.second]}
        result = self.batch.perform(payload, 'delete-group-key', revision)
        self.assertEqual(self.batch.perform(payload, 'delete-group-key', revision), result)
        self.assertEqual(self.store.runnable(), [])
        for ident in payload['tasks']:
            self.assertEqual(self.store.get(ident)['state'], 'trashed')
            self.assertEqual(len([e for e in self.store.events(ident) if e['kind'] == 'task_deleted']), 1)
        with self.assertRaises(OperatorError):
            self.batch.perform({'action': 'delete', 'tasks': [1]}, 'delete-group-key', revision)

    def test_running_unknown_duplicate_and_stale_groups_change_nothing(self):
        task = self.store.get(1)
        task['state'] = 'running'
        self.store.save(task, 'fixture_running')
        for ids in ([self.second, 1], [self.second, 999], [self.second, self.second], [True], []):
            with self.assertRaises(OperatorError):
                self.batch.perform({'action': 'delete', 'tasks': ids}, 'invalid-batch-key', self.revision())
            self.assertEqual(self.store.get(self.second)['state'], 'backlog')
        with self.assertRaises(OperatorError) as error:
            self.batch.perform({'action': 'delete', 'tasks': [self.second]}, 'stale-group-key', 'stale')
        self.assertEqual(error.exception.status, 409)

    def test_mid_group_failure_rolls_back_events_and_state(self):
        original = self.store.delete
        def delete(ident):
            if ident == self.second:
                raise RuntimeError('injected failure')
            original(ident)
        with patch.object(self.store, 'delete', side_effect=delete):
            with self.assertRaises(RuntimeError):
                self.batch.perform({'action': 'delete', 'tasks': [1, self.second]}, 'rollback-group-key', self.revision())
        self.assertEqual(self.store.get(1)['state'], 'queued')
        self.assertNotIn('task_deleted', [e['kind'] for e in self.store.events(1)])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)

    def test_http_checks_csrf_revision_and_operation_lookup(self):
        assets = self.fixture.root / 'export'
        assets.mkdir()
        receipt = self.store.home / 'test-receipt.json'
        atomic_json(receipt, {'assets': {}})
        app = WebApplication(self.fixture.root, 'test', assets, receipt)
        payload = json.dumps({'action': 'delete', 'tasks': [1, self.second]}).encode()
        headers = {'Host': f'127.0.0.1:{PORT}', 'Origin': f'http://127.0.0.1:{PORT}',
                   'Content-Type': 'application/json', 'Idempotency-Key': 'http-batch-key', 'If-Match': self.revision()}
        self.assertEqual(app.dispatch('POST', '/api/v1/tasks/batch', headers, payload)[0], 403)
        headers['X-CSRF-Token'] = app.csrf
        status, _, body = app.dispatch('POST', '/api/v1/tasks/batch', headers, payload)
        self.assertEqual(status, 200)
        operation = json.loads(body)['data']['operation_id']
        self.assertEqual(app.dispatch('GET', '/api/v1/operations/' + operation, headers)[0], 200)
