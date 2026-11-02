import hashlib
import json

from .approval import verify_documents
from .runner import Runner, lock


def retry_review(store, ident):
    with lock(store):
        task = store.get(ident)
        if task['state'] != 'blocked':
            raise ValueError('Повтор ревью возможен только для остановленной задачи')
        data = task['data']
        verify_documents(store, task)
        if data.get('plan_approval', {}).get('version') != data['plan_version']:
            raise ValueError('План не утверждён')
        receipt = data.get('check_receipt')
        if not receipt or receipt.get('exit_code') != 0:
            raise ValueError('Нет успешных проверок')
        folder = store.folder(ident)
        if hashlib.sha256((folder / 'check.log').read_bytes()).hexdigest() != receipt['log_sha256']:
            raise ValueError('Журнал проверок изменился')
        Runner(store).report(task)
        if data['changes'] != receipt['changes']:
            raise ValueError('Исходники изменились после проверок')
        if data.get('frontend_toolchain'):
            from pathlib import Path
            from .node import source_digest
            frontend = json.loads((folder / 'frontend-receipt.json').read_text())
            if frontend['source_digest'] != source_digest(Path(data['workspace'])):
                raise ValueError('Frontend изменился после сборки')
        previous = {'attempts': dict(data['attempts']), 'reason': data.get('reason'),
                    'feedback': data.get('feedback'), 'stage': task['stage']}
        data['attempts']['review'] = 0
        data.pop('reason', None)
        task['stage'], task['state'] = 'review', 'queued'
        store.save(task, 'review_retry_requested', previous, expected='blocked', expected_updated=task['updated'])
