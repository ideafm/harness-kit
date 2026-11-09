import html
import json
import secrets
import time
from urllib.parse import parse_qs

from .auto_apply import policy, set_policy
from .operator import OperatorError
from .projects import project_id
from .service import TaskService


def dispatch(app, method, parsed, headers, body):
    from .web import CONFIRM_PORT, PORT
    if method == 'GET':
        query = parse_qs(parsed.query)
        if set(query) != {'project'} or len(query['project']) != 1:
            raise OperatorError('invalid_request', 'Нужен проект')
        ident = query['project'][0]
        pending = None
    elif method == 'POST':
        if (headers.get('Origin') != f'http://127.0.0.1:{CONFIRM_PORT}'
                or headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded'):
            raise OperatorError('csrf', 'Подтвердите настройку в форме контроллера', 403)
        fields = parse_qs(body.decode(), keep_blank_values=True)
        if set(fields) - {'token', 'enabled'} or any(len(values) != 1 for values in fields.values()):
            raise OperatorError('invalid_request', 'Некорректная форма')
        with app.guard:
            pending = app.pending.get(fields.get('token', [''])[0])
        if not pending or pending.get('kind') != 'policy' or pending['expires'] < time.time():
            raise OperatorError('expired', 'Форма истекла. Обновите панель', 409)
        if fields.get('enabled', [''])[0] not in ('', 'true'):
            raise OperatorError('invalid_request', 'Некорректная настройка')
        ident = pending['project']
    else:
        raise OperatorError('not_found', 'Маршрут не найден', 404)
    try:
        root = app.projects.resolve(ident)
    except KeyError:
        raise OperatorError('not_found', 'Проект не подключён', 404) from None
    service = TaskService(root)
    try:
        if method == 'POST':
            current = set_policy(service.store, fields.get('enabled') == ['true'], pending['revision'])
            with app.guard:
                app.pending.pop(fields['token'][0], None)
        else:
            current = policy(service.store)
        token = secrets.token_urlsafe(32)
        with app.guard:
            app.pending = {key: value for key, value in app.pending.items() if value['expires'] > time.time()}
            if len(app.pending) >= 100:
                raise OperatorError('busy', 'Слишком много открытых форм', 429)
            app.pending[token] = {'kind': 'policy', 'project': project_id(root), 'revision': current['revision'], 'expires': time.time() + 600}
        checked = ' checked' if current['enabled'] else ''
        content = ('<form method="post" action="/policy/embed"><input type="hidden" name="token" value="' + html.escape(token) + '">'
            '<label><input type="checkbox" name="enabled" value="true"' + checked + '> Автоматически применять результаты</label>'
            '<p>После успешных проверок и независимого ревью. Только небольшие изменения низкого риска. '
            'Изменяет основную версию проекта. Разрешение действует только для новых запусков; готовые результаты ждут вашей приёмки. '
            'Код контроллера, настройки и обновления библиотек остаются на ручной приёмке. Утверждение плана настраивается отдельно в задаче.</p>'
            '<button type="submit">Подтвердить настройку</button></form>')
        if method == 'POST':
            message = json.dumps({'type': 'tw:policy', 'project': ident})
            content += f'<p>Настройка сохранена.</p><script>parent.postMessage({message},"http://127.0.0.1:{PORT}")</script>'
        return app.page('Применение результатов', content, embedded=True)
    finally:
        service.close()
