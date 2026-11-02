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
        entries = json.loads(self.path.read_text()) if self.path.exists() else {}
        if not isinstance(entries, dict):
            raise ValueError('Реестр проектов повреждён')
        for ident, path in entries.items():
            if not isinstance(path, str) or not Path(path).is_absolute() or project_id(path) != ident:
                raise ValueError('Реестр проектов повреждён')
        return {**entries, project_id(self.root): str(self.root)}

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
        entries = self.entries()
        ident = project_id(root)
        entries[ident] = str(root)
        atomic_json(self.path, entries)
        return {'id': ident, 'name': root.name}

    def listing(self):
        return [{'id': ident, 'name': Path(path).name} for ident, path in self.entries().items()]
