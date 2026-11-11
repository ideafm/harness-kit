import argparse
import base64
import hashlib
import html
import json
import mimetypes
import re
import secrets
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from .operator import HIGH_ACTIONS, Operator, OperatorError
from .service import TaskService
from .projects import Projects, project_id


PORT = 47831
CONFIRM_PORT = 47832
TITLES = {'approve_plan': 'Утвердить спецификацию и план', 'revise_plan': 'Вернуть план с замечаниями',
          'accept_result': 'Принять', 'request_changes': 'Доработать', 'reject_result': 'Отклонить'}


class WebApplication:
    def __init__(self, root, instance, assets, receipt, track_deployment=False):
        self.root = Path(root).resolve()
        self.instance = instance
        self.assets = Path(assets).resolve()
        receipt_bytes = Path(receipt).read_bytes()
        self.manifest = json.loads(receipt_bytes)['assets']
        self.receipt = str(Path(receipt).resolve())
        self.receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
        self.track_deployment = track_deployment
        self.csrf = secrets.token_hex(32)
        self.cookie = secrets.token_hex(32)
        self.pending = {}
        self.guard = threading.Lock()
        self.projects = Projects(self.root)
        self.project_csrf = secrets.token_hex(32)
        self.stream_slots = threading.BoundedSemaphore(16)
        self.stream_stop = threading.Event()

    def open_stream(self, path, headers):
        if headers.get('Host') != f'127.0.0.1:{PORT}' or headers.get('Origin') not in (None, f'http://127.0.0.1:{PORT}'):
            raise OperatorError('forbidden_origin', 'Недопустимый адрес запроса', 403)
        parsed = urlsplit(path)
        match = re.fullmatch(r'/api/v1/(?:projects/([a-f0-9]{16})/)?stream', parsed.path)
        if not match or parsed.query:
            raise OperatorError('invalid_request', 'Некорректный адрес потока')
        cursor = headers.get('Last-Event-ID')
        if cursor is not None and not re.fullmatch(r'[a-f0-9]{32}:[1-9][0-9]{0,18}', cursor):
            raise OperatorError('invalid_cursor', 'Некорректный курсор потока')
        try:
            root = self.projects.resolve(match[1]) if match[1] else self.root
        except KeyError:
            raise OperatorError('not_found', 'Проект не подключён', 404) from None
        if self.stream_stop.is_set() or not self.stream_slots.acquire(blocking=False):
            raise OperatorError('stream_capacity', 'Поток временно недоступен', 503)
        try:
            from .live_updates import ChangeStream
            return ChangeStream(root, self.stream_slots.release)
        except BaseException:
            self.stream_slots.release()
            raise

    def confirmation_urls(self, control, root=None):
        return {action: f'http://127.0.0.1:{CONFIRM_PORT}/confirm?' + urlencode({
            'project': project_id(root or self.root), 'task': control['task']['id'], 'action': action, 'revision': control['revision'],
            'version': (control['plan'] if action in {'approve_plan', 'revise_plan'} else control['result'])['version']})
            for action in control['allowed_actions'] if action in HIGH_ACTIONS}

    def json(self, status, data, request_id=None):
        return status, 'application/json; charset=utf-8', json.dumps({'data': data, 'request_id': request_id or str(uuid.uuid4())}, ensure_ascii=False).encode()

    def error(self, error):
        return error.status, 'application/json; charset=utf-8', json.dumps({'error': {'code': error.code,
            'message': str(error), 'retryable': False, 'details': {}}, 'request_id': str(uuid.uuid4())}, ensure_ascii=False).encode()

    def dispatch(self, method, path, headers, body=b'', confirmation=False):
        port = CONFIRM_PORT if confirmation else PORT
        origin = f'http://127.0.0.1:{port}'
        try:
            if method == 'GET' and headers.get('Host') == f'localhost:{port}' and headers.get('Origin') in (None, f'http://localhost:{port}', origin):
                parsed = urlsplit(path)
                location = origin + parsed.path + ('?' + parsed.query if parsed.query else '')
                return 200, 'text/html; charset=utf-8', ('<!doctype html><html lang="ru"><meta charset="utf-8">'
                    '<meta http-equiv="refresh" content="0;url=' + html.escape(location, quote=True) + '">'
                    '<a href="' + html.escape(location, quote=True) + '">Продолжить на локальной странице подтверждения</a></html>').encode()
            if headers.get('Host') != f'127.0.0.1:{port}' or headers.get('Origin') not in (None, origin):
                raise OperatorError('forbidden_origin', 'Недопустимый адрес запроса', 403)
            parsed = urlsplit(path)
            if method == 'GET' and parsed.path == '/api/health' and not confirmation:
                if headers.get('X-Tw-Instance') != self.instance:
                    raise OperatorError('forbidden', 'Недоступно', 403)
                return 200, 'application/json', json.dumps({'application': 'tw-web', 'project': str(self.root),
                    'instance': self.instance, 'runtime': 'operator-web'}).encode()
            if method == 'POST' and parsed.path == '/api/shutdown' and not confirmation:
                if headers.get('X-Tw-Instance') != self.instance or body != b'{}':
                    raise OperatorError('forbidden', 'Недоступно', 403)
                return self.json(200, {'stopping': True})
            if confirmation:
                return self.confirm(method, parsed, headers, body)
            if method == 'GET' and parsed.path == '/api/v1/session':
                return self.json(200, {'csrf_token': self.csrf, 'confirmation_origin': f'http://127.0.0.1:{CONFIRM_PORT}'})
            if method == 'GET' and parsed.path == '/api/v1/projects':
                return self.json(200, {'items': self.projects.listing(), 'default_project_id': next(iter(self.projects.entries()), ''), 'revision': self.projects.revision(), 'can_remove': True,
                    'connect_url': f'http://127.0.0.1:{CONFIRM_PORT}/projects'})
            if method == 'POST':
                if headers.get('Origin') != origin or headers.get('X-CSRF-Token') != self.csrf:
                    raise OperatorError('csrf', 'Обновите страницу и повторите действие', 403)
                if headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise OperatorError('invalid_content_type', 'Ожидается JSON')
            removal = re.fullmatch(r'/api/v1/projects/([a-f0-9]{16})/disconnect', parsed.path)
            if method == 'POST' and removal:
                if json.loads(body) != {'action': 'disconnect'}:
                    raise OperatorError('invalid_request', 'Ожидается отключение проекта')
                return self.json(200, self.projects.remove(removal[1], headers.get('If-Match')))
            root = self.root
            if parsed.path.startswith('/api/v1/projects/'):
                scoped = re.fullmatch(r'/api/v1/projects/([a-f0-9]{16})/(.+)', parsed.path)
                if not scoped:
                    raise OperatorError('not_found', 'Проект или маршрут не найден', 404)
                try:
                    root = self.projects.resolve(scoped[1])
                except KeyError:
                    raise OperatorError('not_found', 'Проект не подключён', 404) from None
                parsed = parsed._replace(path='/api/v1/' + scoped[2])
            service = TaskService(root)
            try:
                operator = Operator(service)
                if method == 'GET':
                    if parsed.path == '/api/v1/queue':
                        from .queue_control import QueueControl
                        return self.json(200, QueueControl(service).get())
                    match = re.fullmatch(r'/api/v1/tasks/([1-9][0-9]*)/view', parsed.path)
                    if match:
                        from .view_control import ViewControl
                        return self.json(200, ViewControl(service).get(int(match[1])))
                    if parsed.path == '/api/v1/capabilities':
                        return self.json(200, operator.capabilities())
                    if parsed.path == '/api/v1/status':
                        status = service.status()
                        from .auto_apply import policy
                        status['auto_apply'] = policy(service.store)
                        status['auto_apply']['confirmation_url'] = f'http://127.0.0.1:{CONFIRM_PORT}/policy/embed?project={project_id(root)}'
                        status['project'] = {'id': project_id(root), 'name': root.name, 'backend': service.default_backend}
                        status['tasks'] = [dict(task, revision=operator.control(task['id'])['revision']) for task in status['tasks']]
                        return self.json(200, status)
                    match = re.fullmatch(r'/api/v1/tasks/([1-9][0-9]*)(?:/(control|events|artifacts/([a-z]+)))?', parsed.path)
                    if match:
                        ident = int(match[1])
                        if match[2] == 'control':
                            control = operator.control(ident)
                            control['confirmation_urls'] = self.confirmation_urls(control, root)
                            control['confirmation_widgets'] = {name: url.replace('/confirm?', '/confirm/embed?')
                                for name, url in control['confirmation_urls'].items()}
                            return self.json(200, control)
                        if match[2] == 'events':
                            query = parse_qs(parsed.query)
                            if set(query) - {'after', 'limit'} or any(len(v) != 1 for v in query.values()):
                                raise OperatorError('invalid_query', 'Некорректный запрос истории')
                            return self.json(200, operator.events(ident, int(query.get('after', ['0'])[0]), int(query.get('limit', ['100'])[0])))
                        if match[3]:
                            return self.json(200, service.artifact(ident, match[3]))
                        return self.json(200, service.show(ident))
                    match = re.fullmatch(r'/api/v1/operations/([a-f0-9-]{36})', parsed.path)
                    if match:
                        return self.json(200, operator.operation(match[1]))
                elif method == 'POST':
                    payload = json.loads(body)
                    key = headers.get('Idempotency-Key')
                    if parsed.path == '/api/v1/tasks/batch':
                        from .batch_control import BatchControl
                        return self.json(200, BatchControl(service).perform(payload, key, headers.get('If-Match')))
                    if parsed.path == '/api/v1/queue':
                        from .queue_control import QueueControl
                        return self.json(200, QueueControl(service).perform(payload, key, headers.get('If-Match')))
                    match = re.fullmatch(r'/api/v1/tasks/([1-9][0-9]*)/view', parsed.path)
                    if match:
                        from .view_control import ViewControl
                        result = ViewControl(service).perform(int(match[1]), payload, key, headers.get('If-Match'))
                        return self.json(200, result)
                    if parsed.path == '/api/v1/tasks':
                        result = operator.perform(None, payload, key)
                        if result['status'] == 'failed':
                            raise OperatorError('action_failed', result['error']['message'], 422)
                        return self.json(201, {'task': service.show(result['task_id']), 'revision': result['revision'], 'operation_id': result['operation_id']})
                    match = re.fullmatch(r'/api/v1/tasks/([1-9][0-9]*)/actions', parsed.path)
                    if match:
                        result = operator.perform(int(match[1]), payload, key, headers.get('If-Match'))
                        return self.json(202, {'operation_id': result['operation_id'], 'status': 'pending', 'task_id': result['task_id']})
            finally:
                service.close()
            if parsed.path.startswith('/api/'):
                raise OperatorError('not_found', 'Маршрут не найден', 404)
            if method != 'GET':
                raise OperatorError('not_found', 'Маршрут не найден', 404)
            return self.static(parsed.path)
        except OperatorError as error:
            if confirmation:
                embedded = path.split('?', 1)[0] in {'/confirm/embed', '/policy/embed'}
                recovery = ('<p>Обновите карточку задачи и откройте форму ещё раз.</p>' if embedded else
                    f'<a href="http://127.0.0.1:{PORT}/">Вернуться в панель и обновить задачу</a>')
                _, content_type, data = self.page('Действие не выполнено', '<p>' + html.escape(str(error)) +
                    '</p>' + recovery, embedded=embedded)
                return error.status, content_type, data
            return self.error(error)
        except (ValueError, TypeError, KeyError, UnicodeError):
            return self.error(OperatorError('invalid_request', 'Некорректный запрос или состояние задачи', 400))
        except (OSError, RuntimeError):
            return self.error(OperatorError('unavailable', 'Контроллер временно недоступен', 503))

    def static(self, request_path):
        if self.track_deployment and request_path in {'/', '/index.html'}:
            deployment_path = self.root / '.harness/web-ui.json'
            if deployment_path.is_symlink():
                raise OperatorError('invalid_build', 'Состояние сборки заменено ссылкой', 503)
            deployment = json.loads(deployment_path.read_text())
            receipt_path = Path(deployment['receipt']).resolve()
            receipt_bytes = receipt_path.read_bytes()
            receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
            if str(receipt_path) != self.receipt or receipt_sha256 != getattr(self, 'receipt_sha256', None):
                candidate = WebApplication(self.root, self.instance, deployment['export'], str(receipt_path))
                candidate.static('/')
                with self.guard:
                    self.assets, self.manifest, self.receipt, self.receipt_sha256 = candidate.assets, candidate.manifest, candidate.receipt, candidate.receipt_sha256
        relative = 'index.html' if request_path == '/' else request_path.lstrip('/')
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or any(p.startswith('.') for p in path.parts) or relative not in self.manifest:
            raise OperatorError('not_found', 'Ресурс не найден', 404)
        target = self.assets / relative
        if any((self.assets / Path(*path.parts[:i])).is_symlink() for i in range(1, len(path.parts) + 1)):
            raise OperatorError('invalid_build', 'Ресурс сборки заменён ссылкой', 503)
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.manifest[relative]:
            raise OperatorError('invalid_build', 'Сборка изменилась после проверки', 503)
        if self.track_deployment and relative == 'index.html':
            script = ('<script>addEventListener("message",e=>{const d=e.data;'
                f'if(e.origin!=="http://127.0.0.1:{CONFIRM_PORT}"||!d||d.type!=="tw:decision"||d.action!=="accept_result"||d.status!=="succeeded")return;'
                'if([...document.querySelectorAll("iframe")].some(f=>f.contentWindow===e.source))location.reload();});</script>')
            data += script.encode()
        return 200, mimetypes.guess_type(relative)[0] or 'application/octet-stream', data

    def confirm(self, method, parsed, headers, body):
        if parsed.path == '/policy/embed':
            from .policy_form import dispatch
            return dispatch(self, method, parsed, headers, body)
        if parsed.path == '/projects':
            return self.connect_project(method, headers, body)
        embedded = parsed.path == '/confirm/embed'
        if parsed.path not in {'/confirm', '/confirm/embed'}:
            raise OperatorError('not_found', 'Страница не найдена', 404)
        fields = None
        pending = None
        if method == 'GET':
            query = parse_qs(parsed.query)
            if set(query) not in ({'task', 'action', 'revision', 'version'}, {'project', 'task', 'action', 'revision', 'version'}) or any(len(v) != 1 for v in query.values()):
                raise OperatorError('invalid_request', 'Некорректное подтверждение')
            ident = query.get('project', [project_id(self.root)])[0]
            try:
                root = self.projects.resolve(ident)
            except KeyError:
                raise OperatorError('not_found', 'Проект не подключён', 404) from None
        elif method == 'POST':
            if headers.get('Origin') != f'http://127.0.0.1:{CONFIRM_PORT}' or headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
                raise OperatorError('csrf', 'Подтверждение должно быть отправлено с этой страницы', 403)
            fields = parse_qs(body.decode(), keep_blank_values=True)
            if set(fields) - {'token', 'confirmation', 'text'} or any(len(v) != 1 for v in fields.values()):
                raise OperatorError('invalid_request', 'Некорректная форма')
            token = fields.get('token', [''])[0]
            with self.guard:
                pending = self.pending.get(token)
            if not pending or pending['expires'] < time.time():
                raise OperatorError('expired', 'Подтверждение истекло или уже использовано', 409)
            if pending.get('embedded', False) != embedded:
                raise OperatorError('invalid_token', 'Токен предназначен для другой формы', 403)
            try:
                root = self.projects.resolve(pending['project'])
            except KeyError:
                raise OperatorError('not_found', 'Проект не подключён', 404) from None
        else:
            raise OperatorError('not_found', 'Страница не найдена', 404)
        service = TaskService(root)
        try:
            operator = Operator(service)
            if method == 'GET':
                ident, action = int(query['task'][0]), query['action'][0]
                control = operator.control(ident)
                group = 'plan' if action in {'approve_plan', 'revise_plan'} else 'result'
                current = control[group]
                if action not in HIGH_ACTIONS or action not in control['allowed_actions'] or not current:
                    raise OperatorError('invalid_transition', 'Действие сейчас недоступно', 422)
                if query['revision'][0] != control['revision'] or query['version'][0] != current['version']:
                    raise OperatorError('stale_revision', 'Задача изменилась. Вернитесь в панель и обновите карточку', 409)
                token = secrets.token_urlsafe(32)
                payload = {'action': action, group + '_version': current['version'], group + '_digest': current['digest']}
                with self.guard:
                    self.pending = {k: v for k, v in self.pending.items() if v['expires'] > time.time()}
                    if len(self.pending) >= 100:
                        raise OperatorError('busy', 'Закройте лишние подтверждения и повторите позже', 429)
                    self.pending[token] = {'project': project_id(root), 'task': ident, 'payload': payload, 'revision': control['revision'], 'expires': time.time() + 600, 'embedded': embedded}
                field = ('<label>Замечания<textarea name="text" required maxlength="16000"></textarea></label>'
                    if action in {'revise_plan', 'request_changes'} else
                    '<label>Замечание (необязательно)<textarea name="text" maxlength="16000"></textarea></label>'
                    if action == 'reject_result' else '')
                task = control['task']
                confirmation_field = f'<input type="hidden" name="confirmation" value="TASK-{ident:03}">'
                button_confirmation = ''
                if embedded:
                    progress = json.dumps('Применяем…' if action == 'accept_result' else 'Отправляем…')
                    submit_script = '<script>document.querySelector("form").addEventListener("submit",function(){const b=this.querySelector("button");b.disabled=true;b.textContent=' + progress + ';});</script>'
                    return self.page(TITLES[action], ('' if action == 'accept_result' else f'<p class="context">{html.escape(root.name)} · TASK-{ident:03}</p>') +
                        f'<form method="post" action="/confirm/embed"><input type="hidden" name="token" value="{token}">{field}{confirmation_field}'
                        f'<button type="submit"{button_confirmation}>{TITLES[action]}</button></form>' + submit_script, embedded=True)
                return self.page(TITLES[action], f'<p>Проект <strong>{html.escape(root.name)}</strong> · {html.escape(project_id(root))}</p><p>Задача <strong>TASK-{ident:03}</strong></p><p>{html.escape(task["request"][:500])}</p>'
                    f'<p>Версия: <code>{current["version"]}</code></p><p>Риск: {html.escape(task.get("risk", "не указан"))}</p>'
                    '<p>Это подтверждение обслуживает контроллер. Приёмка применяет результат к основной версии проекта.</p>'
                    f'<form method="post" action="/confirm"><input type="hidden" name="token" value="{token}">{field}' +
                    confirmation_field +
                    f'<button type="submit"{button_confirmation}>{TITLES[action]}</button></form><a href="http://127.0.0.1:{PORT}/">Отмена — вернуться в панель</a>')
            if fields.get('confirmation', [''])[0] != f'TASK-{pending["task"]:03}':
                raise OperatorError('confirmation', 'Номер задачи не совпал')
            payload = dict(pending['payload'])
            if payload['action'] in {'revise_plan', 'request_changes', 'reject_result'}:
                payload['reason' if payload['action'] == 'reject_result' else 'feedback'] = fields.get('text', [''])[0]
                if payload['action'] == 'reject_result' and not payload['reason'].strip():
                    payload['reason'] = 'Отклонено пользователем'
            operator.validate(payload['action'], payload)
            result = operator.perform(pending['task'], payload, token, pending['revision'], human=True)
            with self.guard:
                self.pending.pop(token, None)
            if result['status'] != 'succeeded':
                raise OperatorError('action_failed', result['error']['message'], 422)
            if payload['action'] == 'accept_result':
                from .git_results import commit_if_enabled
                try:
                    commit_if_enabled(service.store, pending['task'])
                except (OSError, RuntimeError, ValueError) as error:
                    raise OperatorError('post_accept_failed', str(error), 503) from None
            message = ('План утверждён. Выполнение продолжится автоматически; отдельно нажимать «Запуск» не нужно.'
                if payload['action'] == 'approve_plan' else 'Действие выполнено контроллером.')
            if payload['action'] == 'accept_result' and service.store.get(pending['task'])['data'].get('integration'):
                message = 'Результат принят и применён к основной ветке. Рабочая версия обновлена.'
            if embedded:
                event = json.dumps({'type': 'tw:decision', 'task': pending['task'], 'project': project_id(root),
                    'action': payload['action'], 'status': 'succeeded'})
                return self.page('Готово', '<p>' + message + '</p><script>parent.postMessage(' + event +
                    f',"http://127.0.0.1:{PORT}");</script>', embedded=True)
            return self.page('Решение сохранено', f'<p>{message}</p><a href="http://127.0.0.1:{PORT}/?project={project_id(root)}&amp;task={pending["task"]}">Вернуться в панель</a>')
        finally:
            service.close()

    def connect_project(self, method, headers, body):
        if method == 'GET':
            return self.page('Подключить проект', '<p>Сначала выполните tw init в папке проекта. Задачи каждого проекта хранятся отдельно.</p>'
                '<form method="post" action="/projects">'
                f'<input type="hidden" name="token" value="{self.project_csrf}">'
                '<label>Абсолютный путь проекта<input name="path" required maxlength="4096" placeholder="/Users/name/projects/shop"></label>'
                '<p>Подключение разрешает контроллеру использовать состояние Harness в указанной папке. Оно не запускает задачи.</p>'
                '<button type="submit">Подключить проект</button></form>')
        if method != 'POST' or headers.get('Origin') != f'http://127.0.0.1:{CONFIRM_PORT}' or headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
            raise OperatorError('csrf', 'Отправьте форму со страницы подключения', 403)
        fields = parse_qs(body.decode(), keep_blank_values=True)
        if set(fields) != {'token', 'path'} or any(len(v) != 1 for v in fields.values()):
            raise OperatorError('invalid_request', 'Некорректная форма')
        if not secrets.compare_digest(fields['token'][0], self.project_csrf):
            raise OperatorError('csrf', 'Обновите страницу подключения', 403)
        with self.guard:
            project = self.projects.add(fields['path'][0])
        return self.page('Проект подключён', f'<p>{html.escape(project["name"])}</p>'
            f'<a href="http://127.0.0.1:{PORT}/?project={project["id"]}">Вернуться в панель</a>')

    def page(self, title, content, embedded=False):
        text = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        text += '<title>Tw — подтверждение</title><style>body{font:16px system-ui;background:#f5f6fa;color:#172033;margin:0;padding:6vh 20px}main{max-width:620px;margin:auto;background:white;padding:32px;border:1px solid #dfe3ed;border-radius:16px}h1{font-size:24px}p{line-height:1.6;white-space:pre-wrap}code{word-break:break-all;font-size:12px}label{display:block;margin:24px 0}input,textarea{display:block;width:100%;box-sizing:border-box;padding:12px;margin-top:8px;border:1px solid #ccd3df;border-radius:8px;font:inherit}textarea{min-height:130px}button{background:#4338ca;color:white;border:0;border-radius:8px;padding:12px 18px;font:inherit;cursor:pointer}a{display:block;margin-top:24px;color:#4338ca}</style>'
        if embedded:
            text += '<style>body{padding:0;background:transparent;font-size:13px}main{max-width:none;border:0;border-radius:0;padding:4px;background:transparent}p{margin:0 0 8px}.context{font-size:11px;color:#6b7280}label{margin:8px 0}textarea{min-height:80px}button{background:#466d91;padding:9px 14px;font-size:12px}</style>'
            text += '<main>' + content + '</main><script>new ResizeObserver(()=>parent.postMessage({type:"tw:widget-size",height:document.querySelector("main").getBoundingClientRect().height},'
            text += f'"http://127.0.0.1:{PORT}")).observe(document.querySelector("main"));</script></html>'
        else:
            text += '<main><small>TW · ПОДТВЕРЖДЕНИЕ КОНТРОЛЛЕРА</small><h1>' + html.escape(title) + '</h1>' + content + '</main></html>'
        return 200, 'text/html; charset=utf-8', text.encode()


def servers(application):
    class Handler(BaseHTTPRequestHandler):
        def dispatch(self):
            try:
                for name in ('Host', 'Origin', 'Content-Type', 'Content-Length', 'Idempotency-Key', 'If-Match', 'X-CSRF-Token', 'X-Tw-Instance', 'Last-Event-ID'):
                    if len(self.headers.get_all(name, [])) > 1:
                        raise ValueError()
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 80000 or self.headers.get('Transfer-Encoding'):
                    raise ValueError()
            except ValueError:
                self.send_error(400)
                return
            if self.command == 'GET' and self.server.server_port != CONFIRM_PORT and re.fullmatch(
                    r'/api/v1/(?:projects/[a-f0-9]{16}/)?stream', urlsplit(self.path).path):
                if size:
                    self.send_error(400)
                    return
                try:
                    stream = application.open_stream(self.path, self.headers)
                except OperatorError as error:
                    self.send_error(error.status, explain=str(error))
                    return
                except (OSError, ValueError, RuntimeError, sqlite3.Error):
                    self.send_error(503)
                    return
                try:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                    self.send_header('Cache-Control', 'no-cache, no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('X-Accel-Buffering', 'no')
                    self.end_headers()
                    for frame in stream.frames(application.stream_stop):
                        self.wfile.write(frame)
                        self.wfile.flush()
                except (OSError, ValueError, RuntimeError, sqlite3.Error):
                    pass
                finally:
                    stream.close()
                    self.close_connection = True
                return
            status, content_type, data = application.dispatch(self.command, self.path, self.headers, self.rfile.read(size), self.server.server_port == CONFIRM_PORT)
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'same-origin')
            script_hashes = []
            if content_type.startswith('text/html'):
                script_hashes = ["'sha256-" + base64.b64encode(hashlib.sha256(item).digest()).decode() + "'" for item in re.findall(rb'<script[^>]*>(.*?)</script>', data, re.S) if item]
            embedded = self.server.server_port == CONFIRM_PORT and urlsplit(self.path).path in {'/confirm/embed', '/policy/embed'}
            ancestors = f'http://127.0.0.1:{PORT}' if embedded else "'none'"
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' " + ' '.join(script_hashes) +
                f"; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors {ancestors}; form-action 'self'; connect-src 'self'; frame-src http://127.0.0.1:{CONFIRM_PORT}")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            if self.command == 'POST' and self.path == '/api/shutdown' and status == 200:
                threading.Thread(target=self.server.shutdown_all, daemon=True).start()

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass

        do_GET = dispatch
        do_POST = dispatch

    first = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    try:
        second = ThreadingHTTPServer(('127.0.0.1', CONFIRM_PORT), Handler)
    except BaseException:
        first.server_close()
        raise
    def shutdown():
        application.stream_stop.set()
        first.shutdown()
        second.shutdown()
    first.shutdown_all = second.shutdown_all = shutdown
    return first, second
