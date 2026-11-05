import hashlib
import os
import shutil
from pathlib import Path

from .security import protected, regular_files, export_snapshot, git
from .state import atomic_json


def manifest(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Основа отсутствует или заменена ссылкой')
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink() or protected(path.relative_to(root).as_posix()):
                raise ValueError('Защищённый путь или ссылка в основе')
            if path.is_file() and path.stat().st_nlink != 1:
                raise ValueError('Жёсткая ссылка в основе')
    return {name: {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   'mode': '100755' if path.stat().st_mode & 0o111 else '100644'}
            for name, path in regular_files(root)}


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
            shutil.copytree(source_workspace, destination, symlinks=True)
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
