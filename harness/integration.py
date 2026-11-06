import json
import subprocess
from pathlib import Path

from .git_results import commit_accepted
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


def deployment_receipt(store, ident):
    folder = store.folder(ident)
    integrated = folder / 'integrated-build'
    receipt = integrated / 'frontend-receipt.json'
    if integrated.is_symlink() or receipt.is_symlink():
        raise ValueError('Сборка объединённой версии заменена ссылкой')
    if not receipt.exists():
        return folder / 'frontend-receipt.json'
    from .node import source_digest
    data = json.loads(receipt.read_text())
    if data.get('source_digest') != source_digest(store.root) or not data.get('checks') or any(
            check.get('exit_code') != 0 for check in data['checks']):
        raise ValueError('Объединённая сборка не соответствует проверенной основной версии')
    return receipt


def apply_accepted(store, ident):
    result = commit_accepted(store, ident)
    with lock(store, 'git-results.lock'):
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
            atomic_json(store.folder(ident) / 'integration-pending.json',
                        {'before': before, 'source': result['commit'], 'branch': branch})
            try:
                git(store.root, '-c', 'commit.gpgsign=false', 'merge', '--no-ff', '-m',
                    f'Merge TASK-{ident:03}: accepted result', result['commit'])
            except subprocess.CalledProcessError as error:
                if git(store.root, 'diff', '--name-only', '--diff-filter=U').strip():
                    git(store.root, 'merge', '--abort')
                raise ValueError('Не удалось слить результат. Основная копия сохранена; требуется разбор конфликта') from error
        commit = git(store.root, 'rev-parse', 'HEAD').decode().strip()
        previous = task['data'].get('integration')
        if previous and previous.get('source_commit') == result['commit'] and ancestor(store.root, previous['commit'], commit):
            record = previous
        else:
            record = {'source_commit': result['commit'], 'commit': commit, 'branch': branch}
        if task['data'].get('integration') != record or task['data'].get('integration_error'):
            task['data']['integration'] = record
            task['data'].pop('integration_error', None)
            store.save(task, 'result_applied', record, expected='accepted', expected_updated=task['updated'])
        pending = store.folder(ident) / 'integration-pending.json'
        if pending.exists():
            pending.unlink()
        if (store.home / 'web-ui.json').is_file() and task['data'].get('frontend_toolchain') == 'next-ui':
            deployed = json.loads((store.home / 'web-ui.json').read_text())
            if deployed.get('task') != ident and type(deployed.get('task')) is int:
                newer = store.get(deployed['task'])['data'].get('integration')
                if newer and newer['commit'] != record['commit'] and ancestor(store.root, record['commit'], newer['commit']):
                    return record
            receipt = deployment_receipt(store, ident)
            if receipt.is_symlink():
                raise ValueError('Receipt сборки заменён ссылкой')
            data = json.loads(receipt.read_text())
            export = Path(data['export'])
            if not export.is_relative_to(store.folder(ident)):
                raise ValueError('Сборка находится вне состояния задачи')
            from .web import WebApplication
            WebApplication(store.root, 'preflight', export, receipt).static('/')
            atomic_json(store.home / 'web-ui.json', {'task': ident, 'export': str(export), 'receipt': str(receipt)})
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
