import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .runner import Runner, lock
from .security import export_snapshot, git, regular_files
from .state import atomic_json


def prepare_worktree(store, task):
    folder = store.folder(task['id'])
    record_path = folder / 'worktree.json'
    branch = f"tw/TASK-{task['id']:03}"
    destination = folder / 'git-worktree'
    if record_path.is_symlink() or destination.is_symlink():
        raise ValueError('Состояние worktree заменено ссылкой')
    if record_path.exists():
        record = json.loads(record_path.read_text())
        if record != {'branch': branch, 'base': task['data']['base'], 'path': str(destination)}:
            raise ValueError('Worktree не соответствует задаче')
        if git(destination, 'symbolic-ref', '--short', 'HEAD').decode().strip() != branch:
            raise ValueError('Ветка worktree изменена')
        return destination
    if destination.exists():
        raise ValueError('Незавершённая подготовка Git worktree')
    git(store.root, 'worktree', 'add', '--no-checkout', '-b', branch, str(destination), task['data']['base'])
    git(destination, 'read-tree', task['data']['base'])
    export_snapshot(store.root, destination, task['data']['base'])
    atomic_json(record_path, {'branch': branch, 'base': task['data']['base'], 'path': str(destination)})
    return destination


def commit_accepted(store, ident):
    with lock(store, 'git-results.lock'):
        task = store.get(ident)
        if task['state'] != 'accepted' or task['stage'] != 'done':
            raise ValueError('Коммит разрешён только после приёмки результата')
        data = task['data']
        folder = store.folder(ident)
        Runner(store).report(task)
        receipt = data.get('check_receipt', {})
        if receipt.get('exit_code') != 0 or data['changes'] != receipt.get('changes'):
            raise ValueError('Результат не совпадает с проверенным')
        if hashlib.sha256((folder / 'check.log').read_bytes()).hexdigest() != receipt['log_sha256']:
            raise ValueError('Журнал проверок изменился')
        workspace = Path(data['workspace'])
        from .baseline import manifest
        source_manifest = manifest(workspace)
        if data.get('frontend_toolchain'):
            from .node import source_digest
            frontend = json.loads((folder / 'frontend-receipt.json').read_text())
            if frontend['source_digest'] != source_digest(workspace):
                raise ValueError('Результат отличается от собранного')
        record_path = folder / 'git-result.json'
        if record_path.is_symlink():
            raise ValueError('Запись коммита заменена ссылкой')
        if record_path.exists():
            record = json.loads(record_path.read_text())
            if git(store.root, 'rev-parse', record['branch']).decode().strip() != record['commit']:
                raise ValueError('Ветка результата изменена после коммита')
            if data.get('git_result') != record or data.get('commit_error'):
                data['git_result'] = record
                data.pop('commit_error', None)
                store.save(task, 'result_commit_recovered', record, expected='accepted', expected_updated=task['updated'])
            return record
        branch = f'tw/TASK-{ident:03}'
        destination = prepare_worktree(store, task)
        if git(destination, 'rev-parse', 'HEAD').decode().strip() != data['base']:
            raise ValueError('В worktree уже есть незарегистрированный коммит')
        git(destination, 'read-tree', data['base'])
        base_manifest = export_snapshot(store.root, destination, data['base'])
        current = dict(regular_files(workspace))
        for name in set(base_manifest) - set(current):
            (destination / name).unlink()
        for name, source in current.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)
            if hashlib.sha256(target.read_bytes()).hexdigest() != source_manifest[name]['sha256']:
                raise ValueError('Исходники изменились при подготовке коммита')
        if manifest(workspace) != source_manifest:
            raise ValueError('Исходники изменились при подготовке коммита')
        names = sorted(set(base_manifest) | set(current))
        git(destination, 'add', '--', *names)
        git(destination, '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-m',
            f'TASK-{ident:03}: accepted result')
        record = {'task': ident, 'branch': branch, 'commit': git(destination, 'rev-parse', 'HEAD').decode().strip(),
                  'base': data['base'], 'worktree': str(destination)}
        atomic_json(record_path, record)
        data['git_result'] = record
        data.pop('commit_error', None)
        store.save(task, 'result_committed', record, expected='accepted', expected_updated=task['updated'])
        return record


def commit_if_enabled(store, ident):
    config = json.loads((store.home / 'config.json').read_text())
    if config.get('commit_after_accept') or config.get('apply_after_accept'):
        try:
            result = commit_accepted(store, ident)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            task = store.get(ident)
            task['data']['commit_error'] = 'Результат принят; коммит не создан. Требуется повтор commit-result.'
            store.save(task, 'result_commit_failed', {'reason': task['data']['commit_error']},
                       expected='accepted', expected_updated=task['updated'])
            raise RuntimeError(task['data']['commit_error']) from error
        from .integration import apply_if_enabled
        apply_if_enabled(store, ident)
        return result
