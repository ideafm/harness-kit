import fcntl
import json
import os
import stat
import time
import uuid

from .projects import project_id
from .service import TaskService


class ChangeStream:
    def __init__(self, root, release):
        self.service = TaskService(root)
        self.release = release
        self.closed = False
        self.ident = project_id(root)
        self.session = uuid.uuid4().hex
        self.sequence = 0
        self.previous = None
        self.sent_at = 0

    def sample(self):
        store = self.service.store
        store.ensure_current()
        version = store.db.execute('PRAGMA data_version').fetchone()[0]
        paths = ('worker.json', 'worker.stop', 'quota.json', 'quota-policy.json',
                 'runtime-profile.json', 'project-view/status.json', 'project-view/selection.json',
                 'project-view/server.json', 'web-projects.json')
        stamps = []
        for name in paths:
            path = store.home / name
            if any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(store.home)):
                raise ValueError('Состояние наблюдения заменено ссылкой')
            try:
                info = path.lstat()
            except FileNotFoundError:
                stamps.append(None)
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Некорректный файл состояния наблюдения')
            stamps.append((info.st_ino, info.st_mtime_ns, info.st_size))
        running = False
        try:
            descriptor = os.open(store.home / 'worker.lock', os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            descriptor = None
        if descriptor is not None:
            try:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    running = True
            finally:
                os.close(descriptor)
        return version, running, stamps

    def poll(self, now=None):
        now = time.monotonic() if now is None else now
        value = self.sample()
        if value != self.previous:
            event = 'sync' if self.previous is None else 'changed'
            self.previous = value
            self.sequence += 1
            revision = f'{self.session}:{self.sequence}'
            data = json.dumps({'project_id': self.ident, 'revision': revision})
            frame = f'retry: 2000\nid: {revision}\nevent: {event}\ndata: {data}\n\n'.encode()
        elif now - self.sent_at >= 15:
            frame = b': keepalive\n\n'
        else:
            return None
        self.sent_at = now
        return frame

    def frames(self, stopped):
        try:
            while not stopped.is_set():
                frame = self.poll()
                if frame:
                    yield frame
                if stopped.wait(1):
                    break
        finally:
            self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            self.service.close()
            self.release()
