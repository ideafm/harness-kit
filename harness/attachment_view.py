import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .security import protected, read_regular


@contextmanager
def image_view(paths):
    with tempfile.TemporaryDirectory(prefix='tw-task-images-') as temporary:
        folder = Path(temporary).resolve()
        records = []
        for index, value in enumerate(paths):
            source = Path(value)
            if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'} or protected(source.name):
                raise ValueError('Недопустимый формат изображения задачи')
            content = read_regular(source.parent, source.name)
            if not content or len(content) > 2 * 1024 * 1024:
                raise ValueError('Недопустимый размер изображения задачи')
            target = folder / (f'image-{index + 1}' + source.suffix.lower())
            target.write_bytes(content)
            target.chmod(0o400)
            records.append({'path': str(target), 'sha256': hashlib.sha256(content).hexdigest()})
        try:
            yield folder, records
        finally:
            expected = {Path(record['path']).name for record in records}
            if {path.name for path in folder.iterdir()} != expected:
                raise RuntimeError('Состав read-only вложений изменён агентом')
            for record in records:
                path = Path(record['path'])
                if hashlib.sha256(read_regular(folder, path.name)).hexdigest() != record['sha256']:
                    raise RuntimeError('Read-only изображение изменено агентом')
