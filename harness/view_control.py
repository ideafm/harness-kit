import json
import uuid
from urllib.parse import urlencode

from .operator import OperatorError, digest
from .project_view import ProjectView, profile


class ViewControl:
    def __init__(self, service):
        self.service = service
        self.store = service.store

    def get(self, ident):
        task = self.store.get(ident)
        result = {'task_id': ident, 'available': False, 'reason': None, 'revision': None, 'view': None, 'actions': []}
        try:
            settings = profile(self.store)
            view = ProjectView(self.store.root)
            result['revision'] = view.control_revision(ident)
            result.update(view=view.status(), actions=['stop'])
            if task['state'] in {'rejected', 'trashed'}:
                raise ValueError('Результат задачи отклонён или удалён')
            workspace = self.store.folder(ident) / 'workspace'
            if task['data'].get('workspace') != str(workspace) or workspace.is_symlink() or not workspace.is_dir():
                raise ValueError('Рабочая копия задачи ещё не подготовлена')
            if settings['adapter'] == 'next-ui' and task['data'].get('frontend_toolchain') != 'next-ui':
                raise ValueError('Задача не использует настроенный runtime')
            result.update(available=True, actions=['select', 'refresh', 'stop'])
        except (OSError, ValueError, RuntimeError) as error:
            result['reason'] = str(error)[:1000]
        return result

    def perform(self, ident, payload, key, expected):
        if not isinstance(payload, dict) or set(payload) != {'action', 'mode'} or payload.get('action') not in {'select', 'refresh', 'stop'} or payload.get('mode') not in {'working', 'checked'}:
            raise OperatorError('invalid_request', 'Нужны действие select/refresh/stop и режим working/checked')
        if not isinstance(key, str) or not 8 <= len(key) <= 160 or not isinstance(expected, str):
            raise OperatorError('invalid_request', 'Нужны Idempotency-Key и If-Match')
        fingerprint = digest({'view_task': ident, 'payload': payload, 'revision': expected})
        view = ProjectView(self.store.root)
        with view.lock('control.lock', True):
            with self.store.transaction():
                row = self.store.db.execute('SELECT data,payload_hash FROM operations WHERE request_key=?', (key,)).fetchone()
                if row:
                    if row['payload_hash'] != fingerprint:
                        raise OperatorError('idempotency_conflict', 'Ключ уже использован для другого действия', 409)
                    record = json.loads(row['data'])
                    if record['status'] != 'pending':
                        return record
                else:
                    control = self.get(ident)
                    if expected != control['revision']:
                        raise OperatorError('stale_revision', 'Просмотр или задача изменились. Обновите карточку', 409)
                    if payload['action'] not in control['actions']:
                        raise OperatorError('view_unavailable', control['reason'], 422)
                    operation_id = str(uuid.uuid4())
                    record = {'operation_id': operation_id, 'task_id': ident, 'status': 'pending',
                        'selection_revision': uuid.uuid4().hex, 'lifecycle_revision': view.lifecycle()['revision']}
                    self.store.db.execute('INSERT INTO operations(id,request_key,payload_hash,data) VALUES(?,?,?,?)',
                        (operation_id, key, fingerprint, json.dumps(record)))
            try:
                if payload['action'] == 'stop':
                    view.stop(record['selection_revision'], expected, ident)
                    record.update(status='succeeded', view=view.status())
                else:
                    if view.lifecycle()['revision'] not in {record['lifecycle_revision'], record['selection_revision']}:
                        raise OperatorError('stale_revision', 'Состояние запуска просмотра изменилось', 409)
                    selection = view.selection()
                    if not selection or selection['revision'] != record['selection_revision']:
                        selection = view.select(ident, payload['mode'], refresh=True, expected=expected,
                            selection_revision=record['selection_revision'])
                    if view.selection() != selection:
                        raise OperatorError('stale_revision', 'Выбрана другая версия просмотра', 409)
                    record.update(status='succeeded', view=view.start(lifecycle_revision=record['selection_revision'],
                        expected_lifecycle=record['lifecycle_revision']))
            except (OSError, ValueError, RuntimeError) as error:
                record.update(status='failed', error={'code': getattr(error, 'code', 'view_failed'),
                    'message': str(error)[:1000], 'retryable': False})
            with self.store.transaction():
                self.store.db.execute('UPDATE operations SET data=? WHERE id=?', (json.dumps(record, ensure_ascii=False), record['operation_id']))
            return record


def preview_descriptor(root, ident):
    home = root / '.harness/project-view'
    if not home.is_dir() or home.is_symlink():
        return None
    try:
        view = ProjectView(root)
        state = view.read('status.json', {})
        if state.get('active_task') != ident or not state.get('source_digest'):
            return None
        state = view.status()
        if not state['running'] or state.get('active_task') != ident:
            return None
        url = view.url + '/?' + urlencode({'__tw_task': ident, '__tw_version': state['source_digest']})
        return {'url': url, 'read_only': True, 'mode': state['mode'],
            'version': state['source_digest'], 'current': state['current'], 'persistent': True}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return None
