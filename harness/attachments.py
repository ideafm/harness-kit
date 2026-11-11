import base64
import hashlib
import json
import os
import re
from pathlib import Path

from .security import protected, read_regular
from .state import atomic_json


MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
TEXT = {'.txt', '.md', '.log', '.json', '.csv'}
IMAGES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}


def home(store):
    path = store.home / 'attachments'
    if path.is_symlink():
        raise ValueError('Хранилище вложений заменено ссылкой')
    path.mkdir(exist_ok=True, mode=0o700)
    return path


def upload(store, payload):
    if not isinstance(payload, dict) or set(payload) != {'name', 'content'}:
        raise ValueError('Нужны имя и содержимое файла')
    name, encoded = payload['name'], payload['content']
    if (not isinstance(name, str) or not 1 <= len(name) <= 160 or Path(name).name != name
            or '\\' in name or protected(name)):
        raise ValueError('Недопустимое имя вложения')
    extension = Path(name).suffix.lower()
    if extension not in TEXT | IMAGES.keys():
        raise ValueError('Поддерживаются PNG/JPEG/WebP и текстовые TXT/MD/LOG/JSON/CSV')
    if not isinstance(encoded, str) or len(encoded) > (MAX_FILE + 2) // 3 * 4:
        raise ValueError('Файл превышает 2 МиБ')
    try:
        content = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise ValueError('Некорректное содержимое файла') from None
    if not content or len(content) > MAX_FILE:
        raise ValueError('Нужен непустой файл до 2 МиБ')
    mime = IMAGES.get(extension, 'text/plain')
    if extension in TEXT:
        try:
            text = content.decode('utf-8')
        except UnicodeError:
            raise ValueError('Текстовый файл должен быть в UTF-8') from None
        if '\x00' in text:
            raise ValueError('Двоичный файл не является текстовым документом')
        if len(content) > 100000:
            raise ValueError('Текстовый документ превышает 100 КБ; приложите нужный фрагмент')
    elif not (mime == 'image/png' and content.startswith(b'\x89PNG\r\n\x1a\n') or
              mime == 'image/jpeg' and content.startswith(b'\xff\xd8\xff') or
              mime == 'image/webp' and content.startswith(b'RIFF') and content[8:12] == b'WEBP'):
        raise ValueError('Содержимое не соответствует формату изображения')
    digest = hashlib.sha256(content).hexdigest()
    ident = hashlib.sha256(name.encode() + b'\0' + content).hexdigest()
    record = {'id': ident, 'name': name, 'mime': mime, 'size': len(content), 'sha256': digest}
    from .runner import lock
    with lock(store, 'attachments.lock'):
        folder = home(store)
        path = folder / (ident + extension)
        if path.exists() or path.is_symlink():
            return load(store, ident)[0]
        total = sum(item.stat().st_size for item in folder.iterdir() if not item.is_symlink() and item.is_file())
        if total + len(content) > 100 * 1024 * 1024:
            raise ValueError('Хранилище вложений проекта заполнено (100 МиБ)')
        if (folder / (ident + '.json')).is_symlink() or (folder / (ident + '.json.tmp')).is_symlink():
            raise ValueError('Метаданные вложения заменены ссылкой')
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(content)
        atomic_json(folder / (ident + '.json'), record)
    return record


def load(store, ident):
    if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{64}', ident):
        raise ValueError('Недопустимый ID вложения')
    folder = home(store)
    metadata = folder / (ident + '.json')
    if metadata.is_symlink():
        raise ValueError('Вложение заменено ссылкой')
    record = json.loads(read_regular(folder, ident + '.json'))
    extension = Path(record['name']).suffix.lower()
    if extension not in TEXT | IMAGES.keys():
        raise ValueError('Неизвестный формат вложения')
    path = folder / (ident + extension)
    if path.is_symlink():
        raise ValueError('Вложение заменено ссылкой')
    if path.stat().st_size > MAX_FILE:
        raise ValueError('Вложение изменено')
    content = read_regular(folder, ident + extension)
    if (record.get('id') != ident or record.get('size') != len(content) or record.get('sha256') != hashlib.sha256(content).hexdigest()
            or record.get('mime') != IMAGES.get(extension, 'text/plain')
            or hashlib.sha256(record['name'].encode() + b'\0' + content).hexdigest() != ident):
        raise ValueError('Вложение изменено')
    return record, content


def resolve(store, identifiers):
    if not isinstance(identifiers, list) or len(identifiers) > 5 or any(not isinstance(value, str) for value in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError('Допускается до 5 разных вложений')
    records = [load(store, ident)[0] for ident in identifiers]
    if sum(record['size'] for record in records) > MAX_TOTAL:
        raise ValueError('Суммарный размер вложений превышает 8 МиБ')
    return records


def context(store, task):
    result = []
    for expected in task['data'].get('attachments', []):
        record, content = load(store, expected['id'])
        if record != expected:
            raise ValueError('Метаданные вложения изменены')
        item = dict(record)
        if record['mime'] == 'text/plain':
            item['text'] = content.decode('utf-8')
        result.append(item)
    return result


def images(store, task):
    return [str(home(store) / (item['id'] + Path(item['name']).suffix.lower())) for item in context(store, task) if item['mime'].startswith('image/')]
