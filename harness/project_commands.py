import json
import shlex
import shutil
from contextlib import ExitStack
from pathlib import Path

from .runner import lock
from .security import read_regular
from .state import atomic_json


def parse_command(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 5000 or any(ord(char) < 32 for char in value):
        raise ValueError('Нужна однострочная команда до 5000 символов')
    command = shlex.split(value)
    if not command or any(token in {';', '&&', '||', '|', '>', '<', '&'} for token in command):
        raise ValueError('Команда задаётся без shell-операторов; составные действия вынесите в скрипт проекта')
    return command


def inferred_npm_check(root):
    try:
        package = json.loads(read_regular(root, 'package.json'))
    except FileNotFoundError:
        return None
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError('Не удалось прочитать package.json; укажите команду проверок явно') from error
    if not isinstance(package, dict):
        raise ValueError('package.json должен содержать объект')
    manager = package.get('packageManager')
    if manager and (not isinstance(manager, str) or not manager.startswith('npm@')):
        return None
    scripts = package.get('scripts')
    test = scripts.get('test') if isinstance(scripts, dict) else None
    if isinstance(test, str) and test.strip():
        return 'npm test'
    return None


def configure(store, check=None, run=None, clear_run=False, execution_profile=None, gemini_model=None):
    if execution_profile is not None:
        from .execution_profiles import validate
        validate(execution_profile)
    if gemini_model is not None and (not isinstance(gemini_model, str) or not gemini_model.strip() or len(gemini_model)>200 or any(ord(char)<32 for char in gemini_model)):
        raise ValueError('Некорректное имя модели Gemini')
    if run is not None and clear_run:
        raise ValueError('Нельзя одновременно задать и удалить команду запуска')
    parsed_check = parse_command(check) if check is not None else None
    parsed_run = parse_command(run) if run is not None else None
    if parsed_check:
        executable = shutil.which(parsed_check[0])
        if executable is None:
            raise ValueError('Исполняемый файл команды проверок не найден')
        parsed_check[0] = str(Path(executable).resolve())
    changed = parsed_check is not None or parsed_run is not None or clear_run or execution_profile is not None or gemini_model is not None
    with ExitStack() as stack:
        if changed:
            stack.enter_context(lock(store))
            stack.enter_context(lock(store, 'git-results.lock'))
        path = store.home / 'config.json'
        if path.is_symlink() or path.with_suffix('.json.tmp').is_symlink():
            raise ValueError('Конфигурация заменена ссылкой')
        config = json.loads(read_regular(store.home, 'config.json'))
        if execution_profile is not None:
            config['execution_profile'] = execution_profile
        if gemini_model is not None:
            config['gemini_model'] = gemini_model
        if parsed_check:
            config['check'] = parsed_check
        if parsed_run:
            config['run_command'] = parsed_run
        if clear_run:
            config.pop('run_command', None)
        if changed:
            store.ensure_current()
            atomic_json(path, config)
        if parsed_run == ['npm', 'run', 'dev']:
            from .project_view import configure as configure_view
            configure_view(store, 'npm-dev')
        if clear_run:
            runtime = store.home / 'runtime-profile.json'
            if runtime.is_symlink():
                raise ValueError('Профиль заменён ссылкой')
            if runtime.is_file() and json.loads(runtime.read_text()).get('adapter') == 'npm-dev':
                runtime.unlink()
        return {'execution_profile': config.get('execution_profile', 'manual'), 'gemini_model': config.get('gemini_model', ''), 'check': config['check'], 'run': config.get('run_command'),
                'run_status': 'npm-dev' if config.get('run_command') == ['npm', 'run', 'dev'] else 'configuration_only' if config.get('run_command') else 'not_configured'}
