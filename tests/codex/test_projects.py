import hashlib
import json
import re
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit

import test_harness as fixtures
from harness.projects import Projects, project_id
from harness.service import TaskService
from harness.state import atomic_json
from harness.web import CONFIRM_PORT, PORT, WebApplication


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests()
        self.fixture.setUp()
        self.root = self.fixture.root.resolve()
        self.other = self.root.parent / 'shop'
        self.other.mkdir()
        (self.other / '.harness').mkdir()
        atomic_json(self.other / '.harness/config.json', {})
        service = TaskService(self.other)
        service.store.add('Задача магазина')
        service.close()
        assets = self.root / 'export'
        assets.mkdir()
        (assets / 'index.html').write_text('panel')
        receipt = self.root / '.harness/frontend.json'
        atomic_json(receipt, {'assets': {'index.html': hashlib.sha256(b'panel').hexdigest()}})
        self.app = WebApplication(self.root, 'test', assets, receipt)
        self.headers = {'Host': f'127.0.0.1:{PORT}'}
        self.confirm_headers = {'Host': f'127.0.0.1:{CONFIRM_PORT}', 'Origin': f'http://127.0.0.1:{CONFIRM_PORT}',
                                'Content-Type': 'application/x-www-form-urlencoded'}
        self.ident = project_id(self.other)

    def tearDown(self):
        self.fixture.tearDown()

    def get(self, path):
        status, _, body = self.app.dispatch('GET', path, self.headers)
        return status, json.loads(body)

    def connect(self):
        status, _, body = self.app.dispatch('GET', '/projects', self.confirm_headers, confirmation=True)
        self.assertEqual(status, 200)
        token = re.search(r'name="token" value="([^"]+)"', body.decode())[1]
        return self.app.dispatch('POST', '/projects', self.confirm_headers,
            urlencode({'token': token, 'path': str(self.other)}).encode(), confirmation=True)

    def test_registration_is_human_scoped_persistent_and_idempotent(self):
        self.assertEqual(len(self.get('/api/v1/projects')[1]['data']['items']), 1)
        self.assertEqual(self.connect()[0], 200)
        self.assertEqual(self.connect()[0], 200)
        listing = Projects(self.root).listing()
        self.assertEqual(len(listing), 2)
        self.assertIn({'id': self.ident, 'name': 'shop'}, listing)
        self.assertNotIn(str(self.other), json.dumps(self.get('/api/v1/projects')[1]))

    def test_json_api_cannot_register_a_path(self):
        headers = dict(self.headers, Origin=f'http://127.0.0.1:{PORT}',
                       **{'Content-Type': 'application/json', 'X-CSRF-Token': self.app.csrf})
        status, _, _ = self.app.dispatch('POST', '/api/v1/projects', headers, json.dumps({'path': str(self.other)}).encode())
        self.assertEqual(status, 404)
        self.assertEqual(len(Projects(self.root).listing()), 1)

    def test_registration_requires_confirmation_origin_and_token(self):
        payload = urlencode({'token': self.app.project_csrf, 'path': str(self.other)}).encode()
        headers = dict(self.confirm_headers, Origin=f'http://127.0.0.1:{PORT}')
        self.assertEqual(self.app.dispatch('POST', '/projects', headers, payload, True)[0], 403)
        payload = urlencode({'token': 'wrong', 'path': str(self.other)}).encode()
        self.assertEqual(self.app.dispatch('POST', '/projects', self.confirm_headers, payload, True)[0], 403)
        self.assertEqual(len(Projects(self.root).listing()), 1)

    def test_unknown_project_never_falls_back_to_default(self):
        for resource in ('status', 'tasks/1', 'tasks/1/control', 'capabilities'):
            self.assertEqual(self.get('/api/v1/projects/' + self.ident + '/' + resource)[0], 404)

    def test_tasks_and_mutations_are_separate_per_project(self):
        self.connect()
        scoped = '/api/v1/projects/' + self.ident
        status, body = self.get(scoped + '/status')
        self.assertEqual(status, 200)
        self.assertEqual(body['data']['project']['id'], self.ident)
        self.assertEqual(body['data']['tasks'][0]['request'], 'Задача магазина')
        _, body = self.get(scoped + '/tasks/1/control')
        headers = dict(self.headers, Origin=f'http://127.0.0.1:{PORT}', **{'Content-Type': 'application/json',
            'X-CSRF-Token': self.app.csrf, 'Idempotency-Key': 'project-pause-123', 'If-Match': body['data']['revision']})
        status, _, _ = self.app.dispatch('POST', scoped + '/tasks/1/actions', headers, b'{"action":"pause"}')
        self.assertEqual(status, 202)
        self.assertEqual(self.get(scoped + '/tasks/1')[1]['data']['state'], 'paused')
        self.assertEqual(self.get('/api/v1/tasks/1')[1]['data']['state'], 'queued')

    def test_creation_and_idempotency_are_scoped_to_project(self):
        self.connect()
        headers = dict(self.headers, Origin=f'http://127.0.0.1:{PORT}', **{'Content-Type': 'application/json',
            'X-CSRF-Token': self.app.csrf, 'Idempotency-Key': 'project-create-123'})
        for prefix, request in (('/api/v1', 'Основной проект'), ('/api/v1/projects/' + self.ident, 'Магазин')):
            with patch('harness.service.TaskService.start', autospec=True,
                       side_effect=lambda service, ident: {'task': service.show(ident)}):
                status, _, body = self.app.dispatch('POST', prefix + '/tasks', headers,
                    json.dumps({'request': request, 'approval_mode': 'auto'}).encode())
            self.assertEqual(status, 201)
            self.assertEqual(json.loads(body)['data']['task']['request'], request)

    def test_confirmation_is_bound_to_its_project(self):
        self.connect()
        service = TaskService(self.other)
        try:
            task = service.store.get(1)
            task['state'] = 'awaiting_approval'
            service.store.save(task, 'fixture')
        finally:
            service.close()
        self.fixture.require_plan()
        _, body = self.get('/api/v1/tasks/1/control')
        url = body['data']['confirmation_urls']['approve_plan']
        self.assertIn('project=' + project_id(self.root), url)
        parsed = urlsplit(url)
        status, _, body = self.app.dispatch('GET', parsed.path + '?' + parsed.query, self.confirm_headers, confirmation=True)
        self.assertEqual(status, 200)
        token = re.search(r'name="token" value="([^"]+)"', body.decode())[1]
        payload = urlencode({'token': token, 'confirmation': 'TASK-001'}).encode()
        with patch('harness.service.TaskService.start'):
            self.assertEqual(self.app.dispatch('POST', '/confirm', self.confirm_headers, payload, True)[0], 200)
        self.assertEqual(self.get('/api/v1/tasks/1')[1]['data']['state'], 'queued')
        self.assertEqual(self.get('/api/v1/projects/' + self.ident + '/tasks/1')[1]['data']['state'], 'awaiting_approval')

    def test_other_project_confirmation_and_artifacts_use_its_store(self):
        self.fixture.require_plan()
        second = fixtures.HarnessTests()
        second.setUp()
        try:
            second.require_plan()
            other_id = self.app.projects.add(str(second.root.resolve()))['id']
            prefix = '/api/v1/projects/' + other_id
            status, body = self.get(prefix + '/tasks/1/artifacts/plan')
            self.assertEqual(status, 200)
            self.assertIn('Изменить app.py', body['data']['text'])
            _, body = self.get(prefix + '/tasks/1/control')
            url = urlsplit(body['data']['confirmation_urls']['approve_plan'])
            self.assertIn('project=' + other_id, url.query)
            status, _, body = self.app.dispatch('GET', url.path + '?' + url.query, self.confirm_headers, confirmation=True)
            self.assertEqual(status, 200)
            token = re.search(r'name="token" value="([^"]+)"', body.decode())[1]
            payload = urlencode({'token': token, 'confirmation': 'TASK-001'}).encode()
            with patch('harness.service.TaskService.start'):
                status, _, _ = self.app.dispatch('POST', '/confirm', self.confirm_headers, payload, True)
            self.assertEqual(status, 200)
            self.assertEqual(second.store.get(1)['state'], 'queued')
            self.assertEqual(self.fixture.store.get(1)['state'], 'awaiting_approval')
        finally:
            second.tearDown()

    def test_protected_paths_symlinks_and_uninitialized_projects_are_rejected(self):
        registry = Projects(self.root)
        alias = self.root.parent / 'alias'
        alias.symlink_to(self.other, target_is_directory=True)
        for path in (alias, self.root / '..' / 'shop', self.root / '.private', self.root / 'app.py', self.root.parent, 'relative'):
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                registry.add(str(path))
        self.assertEqual(len(registry.listing()), 1)

    def test_replaced_project_path_is_rejected(self):
        self.connect()
        moved = self.other.with_name('shop-old')
        self.other.rename(moved)
        self.other.symlink_to(moved, target_is_directory=True)
        self.assertEqual(self.get('/api/v1/projects/' + self.ident + '/status')[0], 400)

    def test_registry_symlink_fails_closed(self):
        registry = Projects(self.root)
        registry.path.symlink_to(self.root / 'app.py')
        with self.assertRaises(ValueError):
            registry.listing()
