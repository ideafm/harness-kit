import json
import hashlib
from pathlib import Path, PurePosixPath
import subprocess
import time
import uuid

from .operator import OperatorError, digest


def policy(store):
    store.ensure_current()
    row = store.db.execute('SELECT data FROM project_policy WHERE id=1').fetchone()
    value = json.loads(row[0]) if row else {'enabled': False, 'generation': None}
    return dict(value, revision=digest(value))


def set_policy(store, enabled, revision):
    if type(enabled) is not bool:
        raise ValueError('Нужно логическое enabled')
    if enabled:
        config = json.loads((store.home / 'config.json').read_text())
        if not config.get('integration_branch'):
            raise OperatorError('integration_unconfigured', 'Сначала настройте основную ветку интеграции проекта', 422)
    with store.transaction():
        current = policy(store)
        if revision != current['revision']:
            raise OperatorError('stale_revision', 'Настройка изменилась. Обновите форму', 409)
        value = {'enabled': enabled, 'generation': uuid.uuid4().hex, 'changed_at': time.time()}
        store.db.execute('INSERT OR REPLACE INTO project_policy(id,data) VALUES(1,?)', (json.dumps(value),))
        store.event(0, 'auto_apply_policy_changed', value)
    return policy(store)


def bind_policy(store, task):
    if task['data'].get('auto_apply_bound'):
        return
    current = policy(store)
    fresh = not any(task['data'].get('attempts', {}).values()) and not task['data'].get('check_receipt')
    task['data']['auto_apply_generation'] = current['generation'] if fresh and current['enabled'] else None
    task['data']['auto_apply_bound'] = True


def eligible(store, task):
    data = task['data']
    current = policy(store)
    paths = [PurePosixPath(name.lower()) for name in data.get('files', [])]
    restricted = any(set(path.parts) & {'harness', 'bin', 'tw_web', 'codex-skills'}
                     or path.name in {'agents.md', 'skill.md', 'package.json', 'package-lock.json', 'pyproject.toml', 'requirements.txt'}
                     or '.config.' in path.name for path in paths)
    return (not restricted and task['state'] == 'review' and task['stage'] == 'done'
            and current['enabled'] and current['generation'] is not None
            and data.get('auto_apply_generation') == current['generation']
            and not data.get('manual_acceptance') and data.get('risk') == 'low' and data.get('scope') == 'small'
            and data.get('review_verdict') == 'pass'
            and data.get('check_receipt', {}).get('exit_code') == 0)


def finish_integration(store, ident):
    from .integration import apply_accepted
    try:
        apply_accepted(store, ident)
        task = store.get(ident)
        task['data']['auto_apply_pending'] = False
        store.save(task, 'automatic_application_finished', expected='accepted', expected_updated=task['updated'])
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        task = store.get(ident)
        task['data']['auto_apply_error'] = str(error)
        task['data']['integration_error'] = str(error)
        store.save(task, 'automatic_application_failed', {'reason': str(error)},
                   expected='accepted', expected_updated=task['updated'])


def maybe_apply(store, ident):
    from .approval import verify_documents, requires_approval
    from .runner import Runner
    with store.transaction():
        task = store.get(ident)
        if not eligible(store, task) or requires_approval({**task['data'], 'approval_mode': 'auto', 'effective_approval': 'auto'}):
            return False
        verify_documents(store, task)
        previous = list(task['data']['changes'])
        Runner(store).report(task)
        if previous != task['data']['changes'] or previous != task['data']['check_receipt']['changes']:
            raise ValueError('Результат изменился после проверок; автоматическая приёмка запрещена')
        from .security import read_regular
        from .node import source_digest
        receipt = task['data']['check_receipt']
        if (hashlib.sha256(read_regular(store.folder(ident), 'check.log')).hexdigest() != receipt.get('log_sha256')
                or source_digest(Path(task['data']['workspace'])) != receipt.get('source_digest')):
            raise ValueError('Подтверждение проверок изменилось; нужна ручная проверка')
        task['state'] = 'accepted'
        task['data']['accepted_by'] = 'automatic'
        task['data']['auto_apply_pending'] = True
        store.save(task, 'automatically_accepted', {'generation': task['data']['auto_apply_generation']},
                   expected='review', expected_updated=task['updated'])
    finish_integration(store, ident)
    return True


def recover(store):
    for task in store.tasks():
        data = task['data']
        if (task['state'] == 'accepted' and data.get('accepted_by') == 'automatic'
                and data.get('auto_apply_pending') and not data.get('auto_apply_error')):
            finish_integration(store, task['id'])
