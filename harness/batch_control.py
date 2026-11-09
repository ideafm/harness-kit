import json
import uuid

from .operator import OperatorError, digest
from .queue_control import QueueControl


class BatchControl:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def perform(self, payload, key, expected):
        if not isinstance(payload, dict) or set(payload) != {'action', 'tasks'} or payload['action'] != 'delete':
            raise OperatorError('invalid_request', 'Ожидается delete и список tasks')
        identifiers = payload['tasks']
        if (not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 100
                or any(type(ident) is not int or ident < 1 for ident in identifiers)
                or len(set(identifiers)) != len(identifiers)):
            raise OperatorError('invalid_request', 'Нужны от 1 до 100 разных номеров задач')
        if not isinstance(key, str) or not 8 <= len(key) <= 160 or not isinstance(expected, str):
            raise OperatorError('invalid_request', 'Нужны Idempotency-Key и If-Match')
        fingerprint = digest({'batch': payload, 'revision': expected})
        with self.store.transaction():
            row = self.store.db.execute('SELECT data,payload_hash FROM operations WHERE request_key=?', (key,)).fetchone()
            if row:
                if row['payload_hash'] != fingerprint:
                    raise OperatorError('idempotency_conflict', 'Ключ использован для другого действия', 409)
                return json.loads(row['data'])
            if QueueControl(self.service).get()['revision'] != expected:
                raise OperatorError('stale_revision', 'Список изменился. Проверьте выбранные задачи', 409)
            try:
                tasks = [self.store.get(ident) for ident in identifiers]
            except ValueError as error:
                raise OperatorError('invalid_group', str(error), 422) from None
            if any(task['state'] in {'running', 'trashed'} for task in tasks):
                raise OperatorError('invalid_group', 'Работающие или удалённые задачи нельзя удалить', 422)
            for ident in identifiers:
                self.store.delete(ident)
            record = {'operation_id': str(uuid.uuid4()), 'status': 'succeeded', 'task_ids': identifiers}
            self.store.db.execute('INSERT INTO operations(id,request_key,payload_hash,data) VALUES(?,?,?,?)',
                                  (record['operation_id'], key, fingerprint, json.dumps(record)))
            return record
