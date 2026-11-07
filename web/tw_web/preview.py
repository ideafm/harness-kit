import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from .launcher import ROOT, Runtime


def task_details(root, ident):
    kit = str(root.parent / 'harness-kit')
    sys.path.insert(0, kit)
    try:
        from harness.service import TaskService
        from harness.runner import Runner
        service = TaskService(root)
        try:
            task = service.store.get(ident)
            if task['state'] not in {'review', 'accepted'} or task['stage'] != 'done':
                raise ValueError('Задача ещё не готова к просмотру')
            expected = task['data']['changes']
            receipt = task['data']['check_receipt']['changes']
            Runner(service.store).report(task)
            if task['data']['changes'] != expected or expected != receipt:
                raise ValueError('Результат изменён после проверок')
            return task
        finally:
            service.close()
    finally:
        sys.path.remove(kit)


def preview_command(ident, root=ROOT):
    if type(ident) is not int or ident < 1:
        raise ValueError('Ожидается положительный номер задачи')
    root = Path(root).resolve()
    task = task_details(root, ident)
    if task['state'] not in {'review', 'accepted'} or task['stage'] != 'done':
        raise ValueError('Задача ещё не готова к просмотру')
    folder = root / '.harness' / 'tasks' / f'TASK-{ident:03}'
    for path in (root / '.harness', root / '.harness/tasks', folder, folder / 'workspace'):
        if path.is_symlink() or not path.is_dir():
            raise ValueError('Нет безопасной рабочей копии этой задачи')
    for name in ('check.log', 'review.md', 'changes.json'):
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Результат ещё не готов к просмотру')
    changes_path = folder / 'changes.json'
    changes = json.loads(changes_path.read_text())
    for change in changes:
        relative = Path(change['path'])
        if relative.is_absolute() or '..' in relative.parts or any(p.startswith('.') for p in relative.parts):
            raise ValueError('Недопустимый путь в результате')
        path = folder / 'workspace' / relative
        if any(parent.is_symlink() for parent in (path, *path.parents[:len(relative.parts)])):
            raise ValueError('Ссылка в результате задачи')
        if change['deleted']:
            if path.exists():
                raise ValueError('Результат изменён после проверок')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != change['sha256']:
            raise ValueError('Результат изменён после проверок')
    launcher = folder / 'workspace/bin/tw-web'
    if launcher.is_symlink() or not launcher.is_file():
        raise ValueError('В результате нет launcher tw-web')
    controller = root.parent / 'harness-kit/bin/tw-mcp'
    return [str(Path(sys.executable).resolve()), '-B', str(launcher), '--project', str(root), '--controller', str(controller)]


def main(argv=None):
    parser = argparse.ArgumentParser(prog='tw-web preview', description='Открыть результат задачи без приёмки и применения')
    parser.add_argument('task')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    try:
        ident = int(args.task.removeprefix('TASK-'))
        command = preview_command(ident)
        if args.no_browser:
            command.append('--no-browser')
        Runtime().stop()
        subprocess.run(command, check=True)
        runtime = Runtime()
        descriptor = os.open(runtime.home / 'preview.json', os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'w') as handle:
            json.dump({'task': ident}, handle)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f'tw-web preview: {error}\n')
