import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .security import doctor, protected
from .service import KIT


def directory(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or protected(path):
        raise ValueError('Укажите существующий абсолютный bin-каталог без скрытых путей')
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def install(destination=None):
    entries = os.environ.get('PATH', '').split(os.pathsep)
    candidates = [Path('/opt/homebrew/bin'), Path('/usr/local/bin'), Path.home() / 'bin']
    if destination is None:
        destination = next((path for path in candidates if str(path) in entries and path.is_dir() and os.access(path, os.W_OK)), None)
        if destination is None:
            raise ValueError('Нет доступного bin-каталога в PATH; укажите --bin-dir')
    destination = Path(destination)
    descriptor = directory(destination)
    targets = {name: str(KIT / 'bin' / name) for name in ('tw', 'tw-web')}
    created = []
    try:
        for name, target in targets.items():
            try:
                os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            try:
                owned = os.readlink(name, dir_fd=descriptor) == target
            except OSError:
                owned = False
            if not owned:
                raise ValueError(f'{destination / name} уже занят; файл сохранён')
        for name, target in targets.items():
            try:
                os.symlink(target, name, dir_fd=descriptor)
                created.append(name)
            except FileExistsError:
                if os.readlink(name, dir_fd=descriptor) != target:
                    raise ValueError('Место установки изменилось; чужие файлы сохранены')
    except BaseException:
        for name in created:
            try:
                if os.readlink(name, dir_fd=descriptor) == targets[name]:
                    os.unlink(name, dir_fd=descriptor)
            except OSError:
                pass
        raise
    finally:
        os.close(descriptor)
    return {'directory': str(destination), 'launchers': list(targets), 'on_path': str(destination) in entries}


def diagnose(sandbox=False):
    result = {'python': sys.version.split()[0], 'git': shutil.which('git'),
              'codex': shutil.which('codex'), 'agy': shutil.which('agy'),
              'tw': shutil.which('tw'), 'tw-web': shutil.which('tw-web')}
    if sandbox:
        driver = result['codex'] or result['agy']
        if not driver:
            raise ValueError('Codex CLI не найден в PATH')
        result['sandbox'] = doctor(driver)
    return result


def main(arguments):
    parser = argparse.ArgumentParser(prog='tw ' + arguments[0])
    if arguments[0] == 'install':
        parser.add_argument('--bin-dir', type=Path)
    else:
        parser.add_argument('--sandbox', action='store_true')
    args = parser.parse_args(arguments[1:])
    try:
        result = install(args.bin_dir) if arguments[0] == 'install' else diagnose(args.sandbox)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if arguments[0] == 'install' and not result['on_path']:
            print('Каталог не входит в PATH. Добавьте его в настройки терминала самостоятельно.')
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'tw: {error}\n')
