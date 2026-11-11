import json
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .git_results import commit_accepted, remove_worktree
from .runner import lock
from .security import git, protected
from .state import atomic_json


def ancestor(root, before, after):
    try:
        git(root, 'merge-base', '--is-ancestor', before, after)
        return True
    except subprocess.CalledProcessError as error:
        if error.returncode != 1:
            raise
        return False


def frontend_root(store, ident):
    from .runner import Runner
    scope = Runner(store).task_scope_dir(store.get(ident))
    base = store.git_toplevel() if scope else store.root
    root = base / scope if scope else base
    if not root.is_dir() or any(parent.is_symlink()
            for parent in (root, *root.parents) if parent.is_relative_to(base)):
        raise ValueError('Недопустимый каталог frontend основной версии')
    return root


@contextmanager
def frontend_snapshot(store, ident):
    from .security import export_snapshot, regular_files, read_regular
    root = frontend_root(store, ident)
    with tempfile.TemporaryDirectory(prefix='tw-integrated-source-') as temporary:
        snapshot = Path(temporary).resolve()
        export_snapshot(store.git_toplevel(), snapshot, 'HEAD')
        source = snapshot / root.relative_to(store.git_toplevel())
        for name, _ in regular_files(source):
            (source / name).write_bytes(read_regular(root, name))
        yield source


def deployment_receipt(store, ident):
    folder = store.folder(ident)
    integrated = folder / 'integrated-build'
    receipt = integrated / 'frontend-receipt.json'
    if integrated.is_symlink() or receipt.is_symlink():
        raise ValueError('Сборка объединённой версии заменена ссылкой')
    if not receipt.exists():
        receipt = folder / 'frontend-receipt.json'
    if receipt.is_symlink():
        raise ValueError('Receipt сборки заменён ссылкой')
    from .node import source_digest
    data = json.loads(receipt.read_text())
    with frontend_snapshot(store, ident) as source:
        current_digest = source_digest(source)
    if data.get('source_digest') != current_digest or not data.get('checks') or any(
            check.get('exit_code') != 0 for check in data['checks']):
        raise ValueError('Объединённая сборка не соответствует проверенной основной версии')
    return receipt


def prepare_deployment(store, ident):
    try:
        return deployment_receipt(store, ident)
    except (FileNotFoundError, ValueError):
        folder = store.folder(ident) / 'integrated-build'
        if folder.is_symlink():
            raise ValueError('Сборка объединённой версии заменена ссылкой')
        folder.mkdir(exist_ok=True)
        if (folder / 'frontend-receipt.json').is_symlink():
            raise ValueError('Receipt сборки заменён ссылкой')
        config = json.loads((store.home / 'config.json').read_text())
        from .node import check
        root = frontend_root(store, ident)
        toolchain_root = root if (root / '.harness/toolchains/next-ui/toolchain.json').is_file() else store.root
        with frontend_snapshot(store, ident) as source:
            if check(source, folder, config, project_root=toolchain_root):
                raise ValueError('Проверки объединённой основной версии не прошли; прежняя панель сохранена')
        return deployment_receipt(store, ident)


def complete_integration(store, ident):
    task = store.get(ident)
    task['data']['integration_in_progress'] = False
    task['data'].pop('auto_apply_error', None)
    if task['data'].get('accepted_by') == 'automatic':
        task['data']['auto_apply_pending'] = False
    store.save(task, 'integration_verified', expected='accepted', expected_updated=task['updated'])


def apply_accepted(store, ident):
    result = commit_accepted(store, ident)
    with lock(store, 'git-results.lock'):
        task = store.get(ident)
        task['data']['integration_in_progress'] = True
        store.save(task, 'integration_started', expected='accepted', expected_updated=task['updated'])
        task = store.get(ident)
        config = json.loads((store.home / 'config.json').read_text())
        branch = config.get('integration_branch')
        if not branch:
            raise ValueError('Основная ветка интеграции не настроена')
        current_branch = git(store.root, 'symbolic-ref', '--short', 'HEAD').decode().strip()
        if branch != current_branch or branch.startswith('tw/'):
            raise ValueError('Откройте основную ветку проекта перед применением')
        before = git(store.root, 'rev-parse', 'HEAD').decode().strip()
        if not ancestor(store.root, result['commit'], before):
            if git(store.root, 'status', '--porcelain', '--untracked-files=all', '--', '.',
                   ':(exclude).harness', ':(exclude).tw-web').strip():
                raise ValueError('В основной копии есть изменения; применение остановлено, файлы сохранены')
            changed = git(store.root, 'diff', '--name-only', '-z', before + '...' + result['commit']).split(b'\0')
            if any(protected(name.decode()) for name in changed if name):
                raise ValueError('Merge затрагивает защищённые пути; требуется отдельное разрешение')
            try:
                tree = git(store.root, 'merge-tree', '--write-tree', before, result['commit']).decode().strip()
            except subprocess.CalledProcessError as error:
                raise ValueError('Не удалось подготовить объединённую версию; требуется разбор конфликта или поддержки Git merge-tree') from error
            from .integration_check import verify_candidate
            verify_candidate(store, task, before, result['commit'], tree, config)
            task = store.get(ident)
            if (task['state'] != 'accepted' or git(store.root, 'rev-parse', 'HEAD').decode().strip() != before
                    or git(store.root, 'symbolic-ref', '--short', 'HEAD').decode().strip() != branch
                    or git(store.root, 'status', '--porcelain', '--untracked-files=all', '--', '.',
                           ':(exclude).harness', ':(exclude).tw-web').strip()):
                raise ValueError('Основная копия изменилась во время проверок; повторите применение')
            candidate = git(store.root, '-c', 'commit.gpgsign=false', 'commit-tree', tree,
                            '-p', before, '-p', result['commit'], '-m',
                            f'Merge TASK-{ident:03}: accepted result').decode().strip()
            atomic_json(store.folder(ident) / 'integration-pending.json',
                        {'before': before, 'source': result['commit'], 'branch': branch, 'candidate': candidate})
            try:
                git(store.root, '-c', 'commit.gpgsign=false', 'merge', '--ff-only', candidate)
            except subprocess.CalledProcessError as error:
                raise ValueError('Не удалось слить результат. Основная копия сохранена; требуется разбор конфликта') from error
        commit = git(store.root, 'rev-parse', 'HEAD').decode().strip()
        if not task['data'].get('integration'):
            checked = task['data'].get('integration_check')
            current_tree = git(store.root, 'rev-parse', commit + '^{tree}').decode().strip()
            if not checked or checked.get('tree') != current_tree or checked.get('source_commit') != result['commit']:
                from .integration_check import verify_candidate
                verify_candidate(store, task, commit, result['commit'], current_tree, config)
                task = store.get(ident)
            if (git(store.root, 'rev-parse', 'HEAD').decode().strip() != commit
                    or git(store.root, 'symbolic-ref', '--short', 'HEAD').decode().strip() != branch
                    or git(store.root, 'status', '--porcelain', '--untracked-files=all', '--', '.',
                           ':(exclude).harness', ':(exclude).tw-web').strip()):
                raise ValueError('Основная копия изменилась; завершение интеграции остановлено')
        previous = task['data'].get('integration')
        if previous and previous.get('source_commit') == result['commit'] and ancestor(store.root, previous['commit'], commit):
            record = previous
        else:
            record = {'source_commit': result['commit'], 'commit': commit, 'branch': branch}
            if task['data'].get('integration_check'):
                record['check'] = task['data']['integration_check']
        if task['data'].get('integration') != record or task['data'].get('integration_error'):
            task['data']['integration'] = record
            task['data'].pop('integration_error', None)
            store.save(task, 'result_applied', record, expected='accepted', expected_updated=task['updated'])
        pending = store.folder(ident) / 'integration-pending.json'
        if pending.exists():
            pending.unlink()
        remove_worktree(store, ident)
        if (store.home / 'web-ui.json').is_file() and task['data'].get('frontend_toolchain') == 'next-ui':
            deployed = json.loads((store.home / 'web-ui.json').read_text())
            if deployed.get('task') != ident and type(deployed.get('task')) is int:
                newer = store.get(deployed['task'])['data'].get('integration')
                if newer and newer['commit'] != record['commit'] and ancestor(store.root, record['commit'], newer['commit']):
                    complete_integration(store, ident)
                    return record
            receipt = prepare_deployment(store, ident)
            if receipt.is_symlink():
                raise ValueError('Receipt сборки заменён ссылкой')
            data = json.loads(receipt.read_text())
            export = Path(data['export'])
            if not export.is_relative_to(store.folder(ident)):
                raise ValueError('Сборка находится вне состояния задачи')
            from .web import WebApplication
            WebApplication(store.root, 'preflight', export, receipt).static('/')
            atomic_json(store.home / 'web-ui.json', {'task': ident, 'export': str(export), 'receipt': str(receipt)})
        complete_integration(store, ident)
        return record


def apply_if_enabled(store, ident):
    config = json.loads((store.home / 'config.json').read_text())
    if not config.get('apply_after_accept'):
        return None
    try:
        return apply_accepted(store, ident)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        task = store.get(ident)
        task['data']['integration_error'] = str(error)
        store.save(task, 'result_apply_failed', {'reason': str(error)},
                   expected='accepted', expected_updated=task['updated'])
        raise RuntimeError('Результат принят, но применение не завершено: ' + str(error)) from error
