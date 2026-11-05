import hashlib
import stat
from pathlib import Path

from .security import protected, regular_files, read_regular, tree_entries, export_snapshot, git
from .state import atomic_json


def manifest(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Основа отсутствует или заменена ссылкой')
    for name, info in tree_entries(root, include_protected=True):
        if info is None or stat.S_ISLNK(info.st_mode):
            raise ValueError('Защищённый путь или ссылка в основе')
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ValueError('Жёсткая ссылка в основе')
        if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
            raise ValueError('Необычный тип файла в основе')
    result = {}
    for name, path in regular_files(root):
        content, info = read_regular(root, name, with_stat=True)
        result[name] = {'sha256': hashlib.sha256(content).hexdigest(),
                        'mode': '100755' if info.st_mode & 0o111 else '100644'}
    return result


def verify(store, task):
    baseline = task['data'].get('input_baseline')
    if baseline:
        if manifest(store.folder(task['id']) / 'input-baseline') != baseline['manifest']:
            raise ValueError('Входная основа изменилась; выполнение запрещено')
        if task['data']['manifest'] != baseline['manifest']:
            raise ValueError('Manifest входной основы не совпадает')


def prepare(store, ident, source_ident):
    from .runner import Runner, lock
    with lock(store):
        target, source = store.get(ident), store.get(source_ident)
        if ident == source_ident or target['stage'] != 'plan' or target['state'] not in {'waiting', 'paused'}:
            raise ValueError('Нужна остановленная задача на планировании')
        if target['data'].get('input_baseline') or target['data'].get('attempts', {}).get('implement', 0):
            raise ValueError('Основа уже подготовлена или реализация начиналась')
        if source['stage'] != 'done' or source['state'] not in {'review', 'accepted'}:
            raise ValueError('Источник должен иметь проверенный завершённый результат')
        receipt = source['data'].get('check_receipt')
        if not receipt or receipt.get('exit_code') != 0:
            raise ValueError('Нет успешных проверок источника')
        runner = Runner(store)
        runner.report(source)
        if source['data']['changes'] != receipt['changes']:
            raise ValueError('Источник изменился после проверок')
        source_workspace = Path(source['data']['workspace'])
        source_manifest = manifest(source_workspace)
        folder = store.folder(ident)
        workspace = folder / 'workspace'
        if 'manifest' not in target['data']:
            if workspace.exists() or workspace.is_symlink():
                raise ValueError('Незавершённый экспорт целевой копии')
            target['data']['base'] = git(store.root, 'rev-parse', 'HEAD').decode().strip()
            target['data']['manifest'] = export_snapshot(store.root, workspace, target['data']['base'])
            target['data']['workspace'] = str(workspace)
        if manifest(workspace) != target['data']['manifest']:
            raise ValueError('В целевой копии уже есть изменения')
        for name in ('input-baseline', 'workspace-before-baseline', 'baseline-staging', 'baseline-preparing.json'):
            if (folder / name).exists() or (folder / name).is_symlink():
                raise ValueError('Обнаружена прежняя или незавершённая подготовка основы')
        if source['data'].get('frontend_toolchain'):
            import json
            from .node import source_digest
            frontend = json.loads((store.folder(source_ident) / 'frontend-receipt.json').read_text())
            if frontend['source_digest'] != source_digest(source_workspace):
                raise ValueError('Frontend источника изменился после сборки')
        atomic_json(folder / 'baseline-preparing.json', {'source_task': source_ident})
        for destination in (folder / 'input-baseline', folder / 'baseline-staging'):
            destination.mkdir()
            for name, metadata in source_manifest.items():
                copied = destination / name
                copied.parent.mkdir(parents=True, exist_ok=True)
                copied.write_bytes(read_regular(source_workspace, name))
                copied.chmod(0o755 if metadata['mode'] == '100755' else 0o644)
            if manifest(destination) != source_manifest:
                raise ValueError('Копия основы не совпадает с источником')
        if manifest(source_workspace) != source_manifest:
            raise ValueError('Источник изменился при копировании')
        workspace.rename(folder / 'workspace-before-baseline')
        (folder / 'baseline-staging').rename(workspace)
        target['data']['manifest'] = source_manifest
        if source['data'].get('git_result'):
            target['data']['base'] = source['data']['git_result']['commit']
        target['data']['input_baseline'] = {'source_task': source_ident, 'manifest': source_manifest,
            'source_check_receipt': receipt, 'source_state': source['state']}
        target['data']['attempts']['plan'] = 0
        if source['data'].get('frontend_toolchain'):
            target['data']['frontend_toolchain'] = source['data']['frontend_toolchain']
        existing_context = target['data'].get('runtime_context', '')
        target['data']['runtime_context'] = existing_context + '\n\n' + ('Контроллер подготовил исходники завершённой TASK-'
            f'{source_ident:03} как входную основу. Это не приёмка и не применение. '
            'Diff этой задачи считается относительно основы. Готовый toolchain запускает только контроллер. '
            'Продолжи исследование и составь точный план по текущей копии; новые зависимости запрещены.')
        store.save(target, 'baseline_prepared', {'source_task': source_ident, 'files': len(source_manifest)},
                   expected=target['state'], expected_updated=target['updated'])
        (folder / 'baseline-preparing.json').unlink()
        return store.get(ident)
