import hashlib
import io
import json
import uuid
from argparse import Namespace
from contextlib import redirect_stdout

from .approval import approve, revise
from .cli import dispatch_store
from .decisions import decide
from .state import StateChanged


HIGH_ACTIONS = {'approve_plan', 'revise_plan', 'accept_result', 'request_changes', 'reject_result'}
ACTIONS = {'start', 'pause', 'resume', 'answer'} | HIGH_ACTIONS


class OperatorError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def revision(task):
    return digest({key: task[key] for key in ('id', 'state', 'stage', 'updated', 'data')})


class Operator:
    def __init__(self, service):
        self.service = service
        self.store = service.store

    def control(self, ident):
        task = self.store.get(ident)
        data, state = task['data'], task['state']
        actions = []
        if state == 'queued' and not self.service.worker_status()['running']:
            actions.append('start')
        if state in {'queued', 'running', 'rate_limited'}:
            actions.append('pause')
        if state in {'paused', 'blocked', 'rate_limited'}:
            actions.append('resume')
        if state == 'waiting':
            actions.append('answer')
        if state == 'awaiting_approval':
            actions.append('approve_plan')
            if not data.get('attempts', {}).get('implement', 0):
                actions.append('revise_plan')
        if state == 'review' and task['stage'] == 'done':
            actions.extend(('accept_result', 'request_changes', 'reject_result'))
        plan = {'version': data['plan_version'], 'digest': data['plan_version']} if data.get('plan_version') else None
        result = None
        if data.get('check_receipt') and data.get('changes'):
            value = digest({'changes': data['changes'], 'receipt': data['check_receipt']})
            result = {'version': value, 'digest': value}
        question = digest({'question': data.get('question'), 'answers': len(data.get('answers', []))}) if state == 'waiting' else None
        return {'task': self.service.view(task), 'revision': revision(task), 'allowed_actions': actions,
                'pending_question_id': question, 'plan': plan, 'result': result}

    def capabilities(self):
        return {'project_id': digest(str(self.service.root))[:16], 'operator_api_version': '1',
                'actions': sorted(ACTIONS | {'submit', 'create_task'}), 'events': True, 'apply': False,
                'human_confirmation': 'separate-origin', 'embedded_confirmation': True,
                'project_view': True, 'stream': True, 'queue': True}

    def events(self, ident, after=0, limit=100):
        self.store.get(ident)
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise OperatorError('invalid_cursor', 'Некорректные параметры истории')
        rows = [row for row in self.store.events(ident) if row['id'] > after]
        items = [{'id': row['id'], 'cursor': str(row['id']), 'task_id': ident,
                  'revision': str(row['id']), 'type': row['kind'], 'occurred_at': row['time'],
                  'message': json.dumps(row['data'], ensure_ascii=False)[:12000]} for row in rows[:limit]]
        return {'items': items, 'next_cursor': items[-1]['cursor'] if items else str(after), 'has_more': len(rows) > limit}

    def operation(self, ident):
        row = self.store.db.execute('SELECT data FROM operations WHERE id=?', (ident,)).fetchone()
        if not row:
            raise OperatorError('not_found', 'Операция не найдена', 404)
        return json.loads(row[0])

    def perform(self, ident, payload, key, expected=None, human=False):
        if not isinstance(payload, dict) or not isinstance(key, str) or not 8 <= len(key) <= 160:
            raise OperatorError('invalid_request', 'Нужны тело запроса и ключ операции')
        action = payload.get('action', 'submit' if ident is None else None)
        if action in HIGH_ACTIONS and not human:
            raise OperatorError('human_confirmation', 'Подтвердите действие на странице контроллера', 403)
        if action not in ACTIONS | {'submit'} or (action == 'submit') != (ident is None):
            raise OperatorError('invalid_action', 'Недопустимое действие')
        fingerprint = digest({'task': ident, 'payload': payload, 'revision': expected})
        with self.store.transaction():
            existing = self.store.db.execute('SELECT id,payload_hash FROM operations WHERE request_key=?', (key,)).fetchone()
            if existing:
                if existing['payload_hash'] != fingerprint:
                    raise OperatorError('idempotency_conflict', 'Ключ уже использован для другого действия', 409)
                return self.operation(existing['id'])
            if ident is not None:
                control = self.control(ident)
                if expected != control['revision']:
                    raise OperatorError('stale_revision', 'Задача изменилась. Обновите карточку', 409)
                if action not in control['allowed_actions']:
                    raise OperatorError('invalid_transition', 'Действие сейчас недоступно', 422)
            self.validate(action, payload)
            operation_id = str(uuid.uuid4())
            record = {'operation_id': operation_id, 'status': 'pending', 'task_id': ident}
            self.store.db.execute('INSERT INTO operations(id,request_key,payload_hash,data) VALUES(?,?,?,?)',
                                  (operation_id, key, fingerprint, json.dumps(record)))
            try:
                with self.store.transaction():
                    ident = self.dispatch(action, ident, payload)
                record.update(status='succeeded', task_id=ident, revision=revision(self.store.get(ident)))
            except (ValueError, RuntimeError, OSError) as error:
                record.update(status='failed', error={'code': 'action_failed',
                    'message': 'Контроллер отклонил действие; обновите карточку и проверьте состояние',
                    'retryable': False})
            self.store.db.execute('UPDATE operations SET data=? WHERE id=?', (json.dumps(record, ensure_ascii=False), operation_id))
            return record

    def validate(self, action, payload):
        keys = {'submit': {'request', 'approval_mode'}, 'start': {'action'}, 'pause': {'action'},
                'resume': {'action'}, 'answer': {'action', 'question_id', 'text'},
                'approve_plan': {'action', 'plan_version', 'plan_digest'},
                'revise_plan': {'action', 'plan_version', 'plan_digest', 'feedback'},
                'accept_result': {'action', 'result_version', 'result_digest'},
                'request_changes': {'action', 'result_version', 'result_digest', 'feedback'},
                'reject_result': {'action', 'result_version', 'result_digest', 'reason'}}[action]
        if action == 'submit' and 'placement' in payload:
            keys = keys | {'placement'}
            if payload['placement'] not in ('queue', 'backlog'):
                raise OperatorError('invalid_request', 'Нужно выбрать queue или backlog')
        if set(payload) != keys:
            raise OperatorError('invalid_request', 'Некорректные поля действия')
        for field in ('request', 'text', 'feedback', 'reason'):
            if field in payload:
                text = payload[field]
                maximum = 50000 if field == 'request' else 16384
                if not isinstance(text, str) or not text.strip() or len(text.encode()) > maximum:
                    raise OperatorError('invalid_text', 'Текст пустой или слишком длинный')

    def dispatch(self, action, ident, payload):
        if action == 'submit':
            return self.service.submit(payload['request'], approval_mode=payload['approval_mode'],
                placement=payload.get('placement', 'queue'))['task']['id']
        control = self.control(ident)
        if action == 'answer' and payload['question_id'] != control['pending_question_id']:
            raise OperatorError('stale_question', 'Вопрос изменился', 409)
        group = 'plan' if action in {'approve_plan', 'revise_plan'} else 'result' if action in HIGH_ACTIONS else None
        if group:
            current = control[group]
            if current is None or any(payload[group + '_' + key] != current[key] for key in ('version', 'digest')):
                raise OperatorError('stale_version', 'Версия изменилась', 409)
        if action in {'pause', 'resume', 'answer'}:
            self.service.operate(action, ident, payload.get('text'))
        elif action == 'start':
            self.service.start(ident)
        elif action == 'approve_plan':
            approve(self.store, ident, payload['plan_version'], f'TASK-{ident:03}')
            self.service.start(ident)
        elif action == 'revise_plan':
            revise(self.store, ident, payload['feedback'])
            self.service.start(ident)
        elif action == 'accept_result':
            with redirect_stdout(io.StringIO()):
                dispatch_store(Namespace(command='accept', task=ident, confirm=f'TASK-{ident:03}'), self.store)
        else:
            decide(self.store, ident, 'request-changes' if action == 'request_changes' else 'reject',
                   payload.get('feedback', payload.get('reason')), f'TASK-{ident:03}')
            if action == 'request_changes':
                self.service.start(ident)
        return ident
