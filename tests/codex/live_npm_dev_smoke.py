import json
import sys
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import test_harness as fixtures
from harness.project_view import ProjectView, configure
from harness.security import git


def main():
    fixture = fixtures.HarnessTests()
    fixture.setUp()
    view = ProjectView(fixture.root)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        root = fixture.root
        (root / 'package.json').write_text(json.dumps({'name': 'dev-smoke', 'version': '1.0.0', 'scripts': {'dev': 'node server.js'}}))
        (root / 'package-lock.json').write_text(json.dumps({'name': 'dev-smoke', 'version': '1.0.0', 'lockfileVersion': 3, 'packages': {}}))
        (root / 'node_modules').mkdir()
        (root / 'server.js').write_text("require('http').createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end('<h1>npm dev ready</h1> '+req.method)}).listen(Number(process.env.PORT),process.env.HOST)")
        git(root, 'add', 'package.json', 'package-lock.json', 'server.js')
        git(root, '-c', 'user.name=Smoke', '-c', 'user.email=smoke@example.invalid', 'commit', '-qm', 'npm fixture')
        configure(fixture.store, 'npm-dev')
        with patch.object(ProjectView, 'start', return_value={'running': True}):
            fixture.run_task()
        view.select(1, 'checked')
        view.start()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            status = view.status()
            if status.get('error'):
                raise RuntimeError(status['error'])
            if status.get('current'):
                break
            time.sleep(.2)
        else:
            raise RuntimeError('Preview readiness timed out')
        for method in ('GET', 'POST'):
            request = urllib.request.Request(view.url, method=method, data=b'{}' if method == 'POST' else None)
            with opener.open(request) as response:
                assert ('npm dev ready</h1> ' + method).encode() in response.read()
        view.stop()
        assert not view.status()['running']
        print(json.dumps({'result': 'passed', 'checks': ['npm run dev', 'sandbox canaries', 'GET/POST proxy', 'stop'], 'model_calls': 0}))
    finally:
        view.stop()
        fixture.tearDown()


if __name__ == '__main__':
    main()
