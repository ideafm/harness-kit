import fcntl
import json
import os
import uuid

from .operator import OperatorError, digest


class QueueControl:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def get(self):
        tasks = self.store.tasks()
        revision = digest([{'id': task['id'], 'state': task['state'], 'updated': task['updated'],
            'queue_order': task['data'].get('queue_order')} for task in tasks])
        return {'revision': revision, 'items': [{'id': task['id'], 'state': task['state'],
            'position': task['data'].get('queue_order', task['id'])} for task in self.store.runnable()],
            'backlog': [task['id'] for task in tasks if task['state'] == 'backlog']}

    def perform(self, payload, key, expected):
        descriptor = os.open(self.store.home / 'queue-control.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            return self.perform_locked(payload, key, expected)

    def perform_locked(self, payload, key, expected):
        if not isinstance(payload, dict) or set(payload) != {'tasks', 'start'} or type(payload['start']) is not bool:
            raise OperatorError('invalid_request', 'Нужны tasks и логическое start')
        if not isinstance(key, str) or not 8 <= len(key) <= 160 or not isinstance(expected, str):
            raise OperatorError('invalid_request', 'Нужны Idempotency-Key и If-Match')
        fingerprint = digest({'queue': payload, 'revision': expected})
        with self.store.transaction():
            row = self.store.db.execute('SELECT data,payload_hash FROM operations WHERE request_key=?', (key,)).fetchone()
            if row:
                if row['payload_hash'] != fingerprint:
                    raise OperatorError('idempotency_conflict', 'Ключ уже использован для другого действия', 409)
                record = json.loads(row['data'])
                if record['status'] != 'pending':
                    return record
            else:
                if self.get()['revision'] != expected:
                    raise OperatorError('stale_revision', 'Очередь изменилась. Обновите список', 409)
                try:
                    tasks = self.store.enqueue(payload['tasks'])
                except ValueError as error:
                    raise OperatorError('invalid_queue', str(error), 422) from None
                operation_id = str(uuid.uuid4())
                record = {'operation_id': operation_id, 'status': 'pending',
                    'task_ids': [task['id'] for task in tasks]}
                self.store.db.execute('INSERT INTO operations(id,request_key,payload_hash,data) VALUES(?,?,?,?)',
                    (operation_id, key, fingerprint, json.dumps(record)))
        try:
            if payload['start']:
                target = next((ident for ident in record['task_ids'] if self.store.get(ident)['state'] == 'queued'), None)
                if target is not None:
                    self.service.start(target)
            record.update(status='succeeded', queue=self.get())
        except (OSError, ValueError, RuntimeError):
            record.update(status='failed', error={'code': 'worker_start_failed',
                'message': 'Задачи сохранены в очереди, но запуск worker не подтверждён', 'retryable': False})
        with self.store.transaction():
            self.store.db.execute('UPDATE operations SET data=? WHERE id=?', (json.dumps(record), record['operation_id']))
        return record
