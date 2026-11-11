import hashlib
import json
import os
import tempfile
from pathlib import Path

from .baseline import manifest
from .runner import Runner, execute
from .security import doctor, export_snapshot, sandbox_command, read_regular
from .state import atomic_json


def run_checks(store, task, workspace, folder, config):
    runner = Runner(store)
    scope = runner.task_scope_dir(task)
    check_root = workspace / scope if scope else workspace
    if not check_root.is_dir() or check_root.is_symlink():
        raise ValueError('Каталог проверок объединённой версии отсутствует')
    backend = runner.task_backend(task, stage='check')
    check_config = {**config, 'backend': backend}
    scoped_toolchain = bool(scope and (store.root / scope / '.harness/toolchains/next-ui/toolchain.json').is_file())
    if task['data'].get('frontend_toolchain') == 'next-ui' or scoped_toolchain:
        from .node import check
        root = store.root / scope if scoped_toolchain else store.root
        code = check(check_root, folder, check_config, project_root=root)
        command = json.loads(read_regular(folder, 'frontend-receipt.json'))['checks'] if not code else []
    else:
        command = config.get('scope_checks', {}).get(scope, config['check']) if scope else config['check']
        doctor(check_config)
        code = execute(sandbox_command(check_config, check_root, True, command), check_root,
                       folder / 'check.log', config['timeout'], active_folder=folder)
    return {'exit_code': code, 'command': command, 'scope': scope, 'backend': backend}


def verify_candidate(store, task, before, source, tree, config):
    folder = store.folder(task['id']) / 'integration-check'
    if folder.is_symlink():
        raise ValueError('Каталог проверок интеграции заменён ссылкой')
    folder.mkdir(exist_ok=True)
    active = folder / 'active.json'
    if active.exists() or active.is_symlink():
        pid = json.loads(read_regular(folder, 'active.json'))['pid']
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            active.unlink()
        else:
            raise RuntimeError('Предыдущая проверка интеграции ещё выполняется; повторный запуск запрещён')
    with tempfile.TemporaryDirectory(prefix='tw-integration-') as temporary:
        workspace = Path(temporary).resolve()
        expected = export_snapshot(store.git_toplevel(), workspace, tree)
        result = run_checks(store, task, workspace, folder, config)
        if result['exit_code']:
            raise ValueError('Проверки объединённой версии не прошли; основная копия сохранена')
        if manifest(workspace) != expected:
            raise ValueError('Исходники объединённой версии изменились во время проверок')
        receipt = {**result, 'before': before, 'source_commit': source, 'tree': tree,
                   'source_digest': hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest(),
                   'log_sha256': hashlib.sha256(read_regular(folder, 'check.log')).hexdigest()}
    atomic_json(folder / 'receipt.json', receipt)
    task = store.get(task['id'])
    task['data']['integration_check'] = receipt
    store.save(task, 'integration_checks_passed', receipt, expected='accepted', expected_updated=task['updated'])
    return receipt
