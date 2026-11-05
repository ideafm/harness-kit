import json
import socket
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import test_harness as fixtures
from harness.project_view import ProjectView, configure
from harness.security import git


def main():
    fixture = fixtures.HarnessTests()
    fixture.setUp()
    view = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        store = fixture.store
        (store.root / 'index.html').write_text('<html>first task</html>')
        git(store.root, 'add', 'index.html')
        git(store.root, '-c', 'user.name=Smoke', '-c', 'user.email=smoke@example.invalid', 'commit', '-qm', 'view fixture')
        configure(store, 'static')
        fixture.run_task()
        first = fixture.task['id']
        fixture.task = store.add('second task')
        second = fixture.task['id']
        def implement():
            workspace = store.folder(second) / 'workspace'
            (workspace / 'index.html').write_text('<html>second task</html>')
            (workspace / 'app.py').write_text('def value():\n    return 2\n')
            return fixtures.response()
        backend = fixtures.FakeCodex({'plan': [fixtures.response(files=['app.py', 'index.html'])], 'implement': [implement]})
        fixture.run_task(backend=backend)
        view = ProjectView(store.root)
        def wait_for(task, text):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                with opener.open(view.url + '/__view/status', timeout=2) as response:
                    status = json.load(response)
                if status['active_task'] == task and status['current']:
                    with opener.open(view.url, timeout=2) as response:
                        body = response.read()
                    if text.encode() in body:
                        return status
                time.sleep(.1)
            raise RuntimeError('View did not publish requested task')
        view.select(first, 'checked')
        view.start()
        wait_for(first, 'first task')
        address = view.url
        view.select(second, 'checked')
        wait_for(second, 'second task')
        assert view.url == address
        (store.folder(second) / 'workspace/index.html').write_text('<html>unverified working edit</html>')
        with opener.open(view.url) as response:
            assert b'unverified working edit' not in response.read()
        view.select(second, 'working')
        wait_for(second, 'unverified working edit')
        assert fixture.store.get(first)['state'] != 'accepted'
        view.stop()
        assert not view.running()
        assert (store.folder(second) / 'workspace/index.html').is_file()
        restarted = view.start()
        assert restarted['message'] != 'Просмотр остановлен'
        wait_for(second, 'unverified working edit')
        view.stop()
        with socket.socket() as foreign:
            foreign.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            foreign.bind(('127.0.0.1', view.port))
            foreign.listen()
            try:
                view.start()
            except RuntimeError:
                pass
            else:
                raise AssertionError('Port collision was not rejected')
            assert foreign.getsockname()[1] == view.port
        print(json.dumps({'result': 'passed', 'url': address, 'tasks': [first, second],
            'checks': ['switch checked task', 'working vs checked', 'restart', 'stop ownership', 'port collision'],
            'model_calls': 0}))
    finally:
        if view is not None:
            view.stop()
        fixture.tearDown()


if __name__ == '__main__':
    main()
