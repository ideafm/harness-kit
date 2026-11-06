import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import test_harness as fixtures
from harness.security import safe_env
from harness.service import TaskService


CHILD = '''import json,sys,time
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch
from harness.cli import dispatch_store
from harness.state import Store
store=Store(Path(sys.argv[1]))
class StubRunner:
 def __init__(self,store):self.store=store
 def run(self,ident):
  if ident==1:
   (store.home/'smoke-ready').write_text('ready')
   deadline=time.monotonic()+10
   while not (store.home/'smoke-continue').exists():
    if time.monotonic()>deadline:raise RuntimeError('parent timeout')
    time.sleep(.05)
  with (store.home/'smoke-order').open('a') as out:out.write(str(ident)+'\\n')
  task=store.get(ident)
  task['state']='review'
  task['stage']='done'
  store.save(task,'smoke_done')
try:
 with patch('harness.cli.Runner',StubRunner):dispatch_store(Namespace(command='worker',once=True),store)
finally:store.db.close()
'''


def main():
    fixture = fixtures.HarnessTests()
    fixture.setUp()
    process = service = None
    try:
        second = fixture.store.add('second', placement='backlog')['id']
        third = fixture.store.add('third', placement='backlog')['id']
        later = fixture.store.add('remain in backlog', placement='backlog')['id']
        process = subprocess.Popen([sys.executable, '-B', '-c', CHILD, str(fixture.root)],
            env=safe_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 10
        while not (fixture.store.home / 'smoke-ready').exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Worker did not enter the first task')
            time.sleep(.05)
        service = TaskService(fixture.root)
        assert service.worker_status()['running']
        service.enqueue([third, second], start=False)
        (fixture.store.home / 'smoke-continue').write_text('continue')
        output, _ = process.communicate(timeout=10)
        assert process.returncode == 0, output.decode()
        order = [int(line) for line in (fixture.store.home / 'smoke-order').read_text().splitlines()]
        assert order == [1, third, second], order
        assert fixture.store.get(later)['state'] == 'backlog'
        reconnected = TaskService(fixture.root)
        try:
            assert reconnected.store.get(later)['state'] == 'backlog'
            assert not reconnected.worker_status()['running']
        finally:
            reconnected.close()
        print(json.dumps({'result': 'passed', 'order': order, 'backlog': later,
            'checks': ['live worker', 'enqueue during execution', 'ordered group', 'backlog untouched', 'restart'], 'model_calls': 0}))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        if service is not None:
            service.close()
        fixture.tearDown()


if __name__ == '__main__':
    main()
