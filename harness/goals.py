import json

from .operator import digest
from .security import git


def nonempty(value, limit=50000):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def submit(store, request, criteria, tasks, request_key, approval='auto', placement='queue'):
    from .approval import validate_mode, requires_approval
    validate_mode(approval)
    if placement not in {'queue', 'backlog'}:
        raise ValueError('Нужно выбрать queue или backlog')
    if not nonempty(request) or not nonempty(request_key, 128):
        raise ValueError('Нужны исходный запрос и ключ постановки до 128 символов')
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 50 or not all(nonempty(item, 2000) for item in criteria):
        raise ValueError('Нужны от 1 до 50 критериев до 2000 символов')
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 20:
        raise ValueError('Нужны от 1 до 20 подзадач')
    keys = set()
    for task in tasks:
        if (not isinstance(task, dict) or set(task) != {'key', 'request', 'depends_on'}
                or not nonempty(task['key'], 80) or task['key'] in keys or not nonempty(task['request'])):
            raise ValueError('Подзадача должна содержать уникальный key, request и depends_on')
        dependencies = task['depends_on']
        if (not isinstance(dependencies, list) or any(not isinstance(key, str) for key in dependencies)
                or len(set(dependencies)) != len(dependencies) or not set(dependencies) <= keys):
            raise ValueError('Зависимости должны ссылаться только на предыдущие подзадачи')
        keys.add(task['key'])
    payload = {'request': request, 'criteria': criteria, 'tasks': tasks, 'approval': approval, 'placement': placement}
    fingerprint = digest(payload)
    with store.transaction():
        row = store.db.execute('SELECT id,payload_hash FROM goals WHERE request_key=?', (request_key,)).fetchone()
        if row:
            if row['payload_hash'] != fingerprint:
                raise ValueError('Ключ постановки уже использован с другим планом')
            return show(store, row['id'])
        ident = store.db.execute('INSERT INTO goals(request_key,payload_hash,data) VALUES(?,?,?)',
                                 (request_key, fingerprint, '{}')).lastrowid
        created = {}
        child_approval = 'approve-plan' if requires_approval({'request': request, 'approval_mode': approval}) else approval
        for item in tasks:
            task = store.add(item['request'], child_approval, placement,
                             depends_on=[created[key] for key in item['depends_on']])
            task['data']['goal_id'] = ident
            task['data']['goal_context'] = {'request': request, 'criteria': criteria}
            store.save(task, 'goal_task_created', {'goal': ident, 'key': item['key']})
            created[item['key']] = task['id']
        final = store.add('Итоговая проверка цели: ' + request, child_approval, placement,
                          depends_on=list(created.values()), manual_acceptance=True)
        final['data'].update(goal_id=ident, verification_only=True,
                             goal_context={'request': request, 'criteria': criteria})
        store.save(final, 'goal_verification_created', {'goal': ident})
        data = {**payload, 'task_ids': created, 'verification_task': final['id']}
        store.db.execute('UPDATE goals SET data=? WHERE id=?', (json.dumps(data, ensure_ascii=False), ident))
        store.event(0, 'goal_created', {'goal': ident, 'tasks': created, 'verification_task': final['id']})
    return show(store, ident)


def show(store, ident):
    store.ensure_current()
    row = store.db.execute('SELECT data FROM goals WHERE id=?', (ident,)).fetchone()
    if row is None:
        raise ValueError('Большая задача не найдена')
    data = json.loads(row['data'])
    verification = store.get(data['verification_task'])
    identifiers = list(dict.fromkeys([*data['task_ids'].values(), *verification['data'].get('depends_on', []), data['verification_task']]))
    tasks = [store.get(number) for number in identifiers]
    final = tasks[-1]
    blockers = [{'task': task['id'], 'state': task['state'],
                 'reason': task['data'].get('integration_error') or task['data'].get('reason') or task['data'].get('question')}
                for task in tasks if task['state'] in {'blocked', 'waiting', 'awaiting_approval', 'paused', 'rejected', 'trashed'}
                or task['data'].get('integration_error') or task['data'].get('auto_apply_error')]
    state = 'needs_attention' if blockers else 'in_progress'
    if final['stage'] == 'done' and final['state'] in {'review', 'accepted'}:
        state = 'awaiting_acceptance' if final['state'] == 'review' else 'completed'
        if final['data'].get('review_verdict') not in {'pass', 'human'}:
            state = 'needs_attention'
        verified_tree = git(store.root, 'rev-parse', final['data']['base'] + '^{tree}')
        if git(store.root, 'rev-parse', 'HEAD^{tree}') != verified_tree:
            state = 'stale_verification'
        if blockers:
            state = 'needs_attention'
    return {'id': ident, 'request': data['request'], 'criteria': data['criteria'], 'state': state,
            'task_ids': data['task_ids'], 'verification_task': data['verification_task'], 'blockers': blockers,
            'tasks': [{'id': task['id'], 'state': task['state'], 'stage': task['stage'],
                       'dependency_wait': store.dependency_wait(task)} for task in tasks]}


def list_goals(store):
    return [show(store, row[0]) for row in store.db.execute('SELECT id FROM goals ORDER BY id')]


def recheck(store, ident, request_key, depends_on=None):
    if not nonempty(request_key, 128):
        raise ValueError('Нужен ключ повторной проверки до 128 символов')
    extra = [] if depends_on is None else depends_on
    if (not isinstance(extra, list) or len(extra) > 80 or any(type(number) is not int or number < 1 for number in extra)
            or len(set(extra)) != len(extra)):
        raise ValueError('Нужны до 80 разных номеров задач исправления')
    with store.transaction():
        status = show(store, ident)
        row = store.db.execute('SELECT data FROM goals WHERE id=?', (ident,)).fetchone()
        data = json.loads(row['data'])
        requests = data.setdefault('recheck_requests', {})
        if request_key in requests:
            if requests[request_key]['depends_on'] != extra:
                raise ValueError('Ключ повторной проверки использован с другим запросом')
            return status
        previous = store.get(data['verification_task'])
        if previous['state'] != 'blocked' and status['state'] != 'stale_verification':
            raise ValueError('Повторная проверка нужна после дефекта или изменения проверенной основной версии')
        dependencies = list(dict.fromkeys([*data['task_ids'].values(), *extra]))
        if previous['id'] in dependencies:
            raise ValueError('Нельзя ждать прежнюю итоговую проверку')
        final = store.add('Итоговая проверка цели: ' + data['request'],
                          previous['data']['approval_mode'], depends_on=dependencies, manual_acceptance=True)
        final['data'].update(goal_id=ident, verification_only=True,
                             goal_context={'request': data['request'], 'criteria': data['criteria']})
        store.save(final, 'goal_verification_created', {'goal': ident, 'previous': previous['id']})
        data.setdefault('verification_history', []).append(previous['id'])
        data['verification_task'] = final['id']
        requests[request_key] = {'depends_on': extra, 'task': final['id']}
        store.db.execute('UPDATE goals SET data=? WHERE id=?', (json.dumps(data, ensure_ascii=False), ident))
    return show(store, ident)
