import time

from .observation import activity


LABELS = {'plan': 'Готовим план', 'implement': 'Пишем код', 'check': 'Проверяем результат', 'review': 'Независимое ревью'}
NEXT = {'plan': 'Реализация или утверждение плана', 'implement': 'Тесты и сборка', 'check': 'Независимое ревью', 'review': 'Ваша приёмка', 'done': 'Ваша приёмка'}


def describe(store, task, events, now=None):
    now = time.time() if now is None else now
    state, stage, data = task['state'], task['stage'], task['data']
    started = next((event for event in reversed(events) if event['kind'] == 'stage_started' and event['data'].get('stage') == stage), None)
    latest = events[-1]['time'] if events else task['updated']
    result = {'title': LABELS.get(stage, 'Готовим результат'), 'detail': '', 'next': NEXT.get(stage, ''),
              'attempt': data.get('attempts', {}).get(stage, 0), 'started_at': None,
              'elapsed_seconds': None, 'last_activity_at': latest, 'retry_at': None, 'waiting': state != 'running'}
    if state == 'running':
        if started:
            result.update(started_at=started['time'], elapsed_seconds=max(0, round(now - started['time'])))
        current = activity(store, task)
        if current:
            result['detail'] = current['action'] + (' · команда завершена' if current['status'] == 'completed' else '')
        if stage == 'check':
            result['detail'] = 'Контроллер выполняет проверки проекта'
        log = store.folder(task['id']) / ('check.log' if stage == 'check' else stage + '.jsonl')
        if not log.is_symlink() and log.is_file():
            stamp = log.stat().st_mtime
            if not started or stamp >= started['time']:
                result['last_activity_at'] = min(now, max(latest, stamp))
        if not result['detail']:
            result['detail'] = 'Ожидаем ответ агента'
        if result['attempt'] > 1:
            result['detail'] += ' · повторная попытка после предыдущего прогона'
    elif state == 'rate_limited':
        result.update(title='Ожидаем восстановления лимита', detail=data.get('reason', 'Работа сохранена'), retry_at=data.get('retry_at'), next='Автоматическое продолжение после снятия ограничения')
    elif state == 'queued':
        dependencies = store.dependency_wait(task)
        result.update(title='Ожидаем зависимости' if dependencies else 'В очереди',
                      detail='Нужны принятые и применённые результаты: ' + ', '.join(f"TASK-{item['id']:03}" for item in dependencies) if dependencies else 'Задача ожидает исполнителя', next=LABELS.get(stage, 'Продолжение задачи'))
    elif state in {'waiting', 'awaiting_approval'}:
        result.update(title='Нужен ваш ответ' if state == 'waiting' else 'План ждёт утверждения', detail=data.get('question', 'Откройте план и примите решение'), next='Продолжение после вашего решения')
    elif state == 'review' and stage == 'done':
        result.update(title='Готово к приёмке', detail='Проверки и ревью завершены. Посмотрите результат до принятия.', next='Принять результат или вернуть замечания')
    elif state in {'blocked', 'paused'}:
        result.update(title='Выполнение остановлено' if state == 'blocked' else 'На паузе', detail=data.get('reason', 'Работа сохранена'), next='Устранить причину и продолжить' if state == 'blocked' else 'Продолжить по вашей команде')
    else:
        result.update(title={'backlog': 'В бэклоге', 'accepted': 'Результат принят', 'rejected': 'Результат отклонён', 'trashed': 'Задача удалена'}.get(state, state), next='Поставить задачу в очередь' if state == 'backlog' else '', detail='')
    return result
