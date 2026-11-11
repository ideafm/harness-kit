import hashlib
from pathlib import Path


def revision():
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.glob('*.py')):
        if path.is_symlink():
            raise RuntimeError('Код контроллера заменён ссылкой')
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


LOADED_REVISION = revision()
