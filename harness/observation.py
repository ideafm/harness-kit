import re
import json
import shlex
import time
from pathlib import Path


STAGES = {'plan': 'Спецификация и план', 'implement': 'Реализация', 'check': 'Проверки',
          'review': 'Ревью', 'done': 'Завершено'}
STATES = {'queued': 'В очереди', 'running': 'Выполняется', 'waiting': 'Нужен ответ',
          'awaiting_approval': 'План ждёт утверждения', 'rate_limited': 'Ожидание лимита',
          'paused': 'Пауза', 'blocked': 'Техническая остановка', 'review': 'Ожидает приёмки',
          'accepted': 'Принята', 'rejected': 'Отклонена'}


def plain(value):
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', str(value))


def descriptor(root, ident):
    command = [str(Path(__file__).resolve().parents[1] / 'bin/tw'), '--project', str(root),
               'watch', f'TASK-{ident:03}']
    return {'task_id': ident, 'terminal_command': shlex.join(command), 'mode': 'events', 'interactive': False}


def event_text(event):
    kind, data = event['kind'], event['data']
    stage = STAGES.get(data.get('stage'), data.get('stage', ''))
    if kind == 'stage_started':
        return f"{stage}: начат этап, попытка {data.get('attempt', '?')}"
    if kind == 'stage_finished':
        return f"{stage}: этап завершён → {STAGES.get(data.get('next'), data.get('next', ''))}"
    if kind == 'checks_finished':
        return 'Проверки пройдены' if data.get('exit_code') == 0 else 'Проверки обнаружили ошибку; подробности во вкладке проверок'
    if kind == 'question':
        return 'Нужен ответ: ' + plain(data.get('text', ''))
    if kind in {'blocked', 'quota_wait', 'rate_limited'}:
        return plain(data.get('reason', 'Исполнение приостановлено'))
    labels = {'created': 'Задача создана', 'plan_approved': 'План утверждён', 'started': 'Worker принял задачу',
              'resume_requested': 'Запрошено продолжение', 'pause_requested': 'Запрошена пауза',
              'accepted': 'Результат принят', 'result_committed': 'Принятый результат сохранён коммитом',
              'plan_published': 'Новая версия плана сохранена', 'baseline_prepared': 'Подготовлена основа задачи',
              'plan_revision_requested': 'План возвращён с замечаниями', 'answered': 'Ответ сохранён'}
    return labels.get(kind, 'Состояние задачи обновлено')


def activity(store, task):
    if task['stage'] not in {'plan', 'implement', 'review'} or task['state'] != 'running':
        return None
    path = store.folder(task['id']) / (task['stage'] + '.jsonl')
    if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink() or not path.is_file():
        return None
    with path.open('rb') as handle:
        handle.seek(0, 2)
        length = handle.tell()
        handle.seek(max(0, length - 262144))
        lines = handle.read(262144).splitlines()
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(event, dict):
            continue
        item = event.get('item', {})
        if not isinstance(item, dict) or item.get('type') != 'command_execution':
            continue
        command = item.get('command', '')
        if not isinstance(command, str):
            continue
        action = 'Команда в рабочей копии'
        if re.search(r'\bapply_patch\b|write_text\(|write_bytes\(', command):
            action = 'Сохраняет изменения файлов'
        elif re.search(r'\b(rg|cat|sed|head|tail)\b', command):
            action = 'Изучает файлы проекта'
        finished = event.get('type') == 'item.completed'
        code = item.get('exit_code')
        return {'id': str(item.get('id', '')), 'action': action,
                'status': 'completed' if finished else 'running', 'exit_code': code if type(code) is int else None}
    return None


def watch(service, ident, once=False, output=print):
    cursor = 0
    last = None
    last_activity = None
    while True:
        task = service.store.get(ident)
        signature = (task['state'], task['stage'])
        if signature != last:
            output(f"TASK-{ident:03} · {plain(STATES.get(task['state'], task['state']))} · {plain(STAGES.get(task['stage'], task['stage']))}")
            if last is None:
                output('Наблюдение за существующей задачей. Ctrl+C закрывает просмотр, worker продолжает работу.')
            last = signature
        events = service.store.events(ident)
        for event in events:
            if event['id'] > cursor:
                output(time.strftime('%H:%M:%S', time.localtime(event['time'])) + ' · ' + plain(event_text(event)))
                cursor = event['id']
        current = activity(service.store, task)
        if current and current != last_activity:
            ending = 'завершено' if current['status'] == 'completed' else 'в работе'
            if current['exit_code'] not in (None, 0):
                ending = 'ошибка команды'
            output(plain(current['action']) + ' · ' + ending)
            last_activity = current
        if once or task['state'] in {'accepted', 'rejected'}:
            return
        time.sleep(1)
