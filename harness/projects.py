import fcntl
import os
import uuid
from contextlib import contextmanager

import hashlib
import json
from pathlib import Path

from .service import TaskService
from .state import atomic_json


def project_id(root):
    return hashlib.sha256(json.dumps(str(root), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


class Projects:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / '.harness/web-projects.json'

    def entries(self):
        if self.path.is_symlink():
            raise ValueError('Реестр проектов заменён ссылкой')
        entries = json.loads(self.path.read_text()) if self.path.exists() else {project_id(self.root): str(self.root)}
        if isinstance(entries, dict) and entries.get('version') == 2:
            entries = entries.get('entries')
        if not isinstance(entries, dict):
            raise ValueError('Реестр проектов повреждён')
        for ident, path in entries.items():
            if not isinstance(path, str) or not Path(path).is_absolute() or project_id(path) != ident:
                raise ValueError('Реестр проектов повреждён')
        return entries

    def resolve(self, ident):
        path = self.entries().get(ident)
        if path is None:
            raise KeyError(ident)
        return self.validate(path)

    def validate(self, value):
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            raise ValueError('Укажите абсолютный путь проекта')
        path = Path(value)
        if not path.is_absolute() or any(part.startswith('.') for part in path.parts):
            raise ValueError('Нужен абсолютный путь без скрытых каталогов и переходов')
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError('Путь проекта не должен содержать символические ссылки')
        if not path.is_dir():
            raise ValueError('Каталог проекта не найден')
        return path

    def add(self, value):
        root = self.validate(value)
        service = TaskService(root)
        service.close()
        ident = project_id(root)
        with self.lock():
            entries = self.entries()
            entries[ident] = str(root)
            self.write(entries)
        return {'id': ident, 'name': root.name}

    def listing(self):
        return [{'id': ident, 'name': Path(path).name} for ident, path in self.entries().items()]

    @contextmanager
    def lock(self):
        descriptor = os.open(self.path.with_suffix('.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def write(self, entries):
        if self.path.is_symlink() or self.path.with_suffix('.json.tmp').is_symlink():
            raise ValueError('Реестр проектов заменён ссылкой')
        atomic_json(self.path, {'version': 2, 'entries': entries, 'generation': uuid.uuid4().hex})

    def revision(self):
        entries = self.entries()
        raw = self.path.read_bytes() if self.path.exists() else json.dumps(entries, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()

    def remove(self, ident, expected):
        from .operator import OperatorError
        from .project_view import ProjectView
        from .runner import lock
        with self.lock():
            entries = self.entries()
            if ident not in entries:
                return {'removed': ident}
            if expected != self.revision():
                raise OperatorError('stale_revision', 'Список проектов изменился. Обновите страницу', 409)
            root = self.validate(entries[ident])
            service = TaskService(root)
            try:
                with lock(service.store, 'worker-launch.lock'), lock(service.store, 'worker.lock'), lock(service.store):
                    view = ProjectView(root)
                    with view.lock('control.lock', True):
                        view.stop()
                        del entries[ident]
                        self.write(entries)
            except RuntimeError as error:
                raise OperatorError('project_busy', 'Не удалось отключить проект: ' + str(error) + '. Сначала остановите worker.', 409) from error
            finally:
                service.close()
            return {'removed': ident}
