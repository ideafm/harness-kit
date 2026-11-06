import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from .cli import main as harness_main
from .security import doctor, permission_args, safe_env, toml
from .service import KIT, TaskService
from .state import atomic_json


BLOCK = """\n\n## Tw workflow\n\nThis project uses Tw. In a Tw session, use the `tw` skill and MCP tools for\nimplementation tasks; do not edit the original project directly. The controller\nsaves a specification and plan, publishes a summary, then executes in isolation.\nDo not read secrets, env files or hidden paths, use SSH, or bypass sandbox.\nGeneral task approval does not grant protected access. Accept results only after\nthe human explicitly runs the operator command; never accept on their behalf.\nIf Tw tools are unavailable, stop task execution and ask to launch `tw`.\n"""
BLOCK += "When the controller supplies stage context, execute that stage directly\nin its isolated workspace; do not enqueue a nested Tw task.\n"


def inferred_check(root):
    tests = root / "tests"
    if tests.is_dir() and any(tests.glob("test*.py")):
        return shlex.join([str(Path(sys.executable).resolve()), "-m", "unittest", "discover", "-s", "tests", "-v"])
    return None


def connect(root, check=None, model=None, backend=None):
    from .projects import Projects
    root = Projects(KIT).validate(str(Path(root).absolute())).resolve()
    if root == KIT:
        raise ValueError("Не подключайте контроллер к самому себе; используйте отдельный проект")
    manifest = root / ".harness/tw.json"
    skill = root / ".agents/skills/tw"
    source = KIT / "codex-skills/tw"
    files = {"SKILL.md": (source / "SKILL.md").read_bytes(),
             "agents/openai.yaml": (source / "agents/openai.yaml").read_bytes()}
    if any(path.is_symlink() for path in (root / ".harness", manifest, root / ".harness/config.json")):
        raise ValueError("Состояние Tw заменено ссылкой; подключение отменено")
    owned = {}
    if manifest.exists():
        owned = json.loads(manifest.read_text()).get("files", {})
    if skill.exists() and not owned:
        raise ValueError("Существующий skill tw не принадлежит этому подключению; файлы не перезаписаны")
    for directory in (root / ".agents", root / ".agents/skills", skill, skill / "agents"):
        if directory.is_symlink():
            raise ValueError("Каталог skills заменён ссылкой; подключение отменено")
    for name in files:
        path = skill / name
        if path.exists() or path.is_symlink():
            if path.is_symlink() or str(path.relative_to(root)) not in owned:
                raise ValueError("Существующий skill tw не принадлежит этому подключению; файлы не перезаписаны")
            if hashlib.sha256(path.read_bytes()).hexdigest() != owned[str(path.relative_to(root))]:
                raise ValueError("Skill tw изменён вручную; файлы не перезаписаны")
    agents = root / "AGENTS.md"
    if agents.is_symlink():
        raise ValueError("AGENTS.md является ссылкой; подключение отменено")
    content = agents.read_text() if agents.exists() else "# Project instructions\n"
    if "## Tw workflow" in content and BLOCK.strip() not in content:
        if owned.get("AGENTS.md") != hashlib.sha256(agents.read_bytes()).hexdigest():
            raise ValueError("Раздел Tw workflow уже существует и отличается; подключение отменено")
        content = content[:content.index("## Tw workflow")].rstrip()
    config = root / ".harness/config.json"
    if not config.exists():
        selected = check or inferred_check(root)
        if not selected and sys.stdin.isatty():
            selected = input("Команда проверок проекта: ").strip()
        if not selected:
            raise ValueError("Укажите команду проверок: tw init --check 'команда'")
        arguments = ["--project", str(root), "init", "--check", selected]
        if model:
            arguments += ["--model", model]
        if backend:
            arguments += ["--backend", backend]
        harness_main(arguments)
    elif check or model:
        raise ValueError("Проект уже подключён; повторный init не меняет check/model")
    elif backend:
        current = json.loads(config.read_text())
        current["backend"] = backend
        current.setdefault("agy", "agy")
        current.setdefault("sandbox", "/usr/bin/sandbox-exec")
        atomic_json(config, current)
    if BLOCK.strip() not in content:
        agents.write_text(content.rstrip() + BLOCK)
    for name, data in files.items():
        path = skill / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    owned_files = {str((skill / name).relative_to(root)): hashlib.sha256(data).hexdigest() for name, data in files.items()}
    owned_files["AGENTS.md"] = hashlib.sha256(agents.read_bytes()).hexdigest()
    atomic_json(manifest, {"version": 1, "kit": str(KIT), "files": owned_files})
    print(f"Tw подключён: {root}\nТеперь запустите tw и опишите задачу обычным языком.")


def register_project(root):
    from .projects import Projects
    panel = KIT.parent / 'tw-web'
    registry = panel if (panel / '.harness/config.json').is_file() else root
    return Projects(registry).add(str(root))


def verified_setup_paths(root):
    root = Path(root)
    manifest = root / ".harness/tw.json"
    if not manifest.is_file():
        return []
    paths = {"AGENTS.md", ".agents/skills/tw/SKILL.md", ".agents/skills/tw/agents/openai.yaml"}
    hashes = json.loads(manifest.read_text()).get("files", {})
    if set(hashes) != paths:
        raise ValueError("Некорректный список файлов подключения Tw")
    for name in paths:
        path = root / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
            raise ValueError("Файлы подключения Tw изменены после init; проверьте изменения")
    return sorted(paths)


def chat_command(root, headless=False, prompt=None):
    root = Path(root).resolve()
    config = json.loads((root / ".harness/config.json").read_text())
    default_prompt = "Работай со skill $tw. Покажи текущий статус через MCP Tw и помоги поставить следующую задачу. Не меняй исходники напрямую."
    if config.get("backend") == "gemini":
        agy = config.get("agy") or "agy"
        command = [agy, "--sandbox"]
        if config.get("model"):
            command += ["--model", config["model"]]
        if headless:
            command += ["--output-format", "json", "--dangerously-skip-permissions", "-p", prompt or default_prompt]
        else:
            command += [prompt or default_prompt]
        return command
    server = {"command": str(Path(sys.executable).resolve()), "args": [str(KIT / "bin/tw-mcp"), "--project", str(root)],
              "required": True, "default_tools_approval_mode": "auto", "startup_timeout_sec": 20}
    command = [config["codex"], "--no-daemon"]
    if headless:
        command += ["exec", "--ignore-user-config", "--ephemeral", "--json"]
    command += ["-C", str(root), *permission_args(root, False), "-c", 'approval_policy="never"',
                "-c", "mcp_servers=" + toml({"tw": server}),
                "-c", 'web_search="disabled"', "-c", "features.apps=false", "-c", "features.plugins=false",
                "-c", "features.browser_use=false", "-c", "features.computer_use=false",
                "-c", "features.image_generation=false", "-c", "features.hooks=false",
                "-c", "agents.enabled=false", "-c", "features.shell_snapshot=false",
                "-c", 'shell_environment_policy.inherit="none"',
                "-c", "shell_environment_policy.experimental_use_profile=false"]
    if config.get("model"):
        command += ["-m", config["model"]]
    command += [prompt or default_prompt]
    return command


def verify_servers(command):
    if Path(command[0]).name == "agy":
        return
    options = command[1:-1]
    if options and options[0] == "--no-daemon":
        options = options[1:]
    headless = bool(options and options[0] == "exec")
    if headless:
        if "--ignore-user-config" not in options:
            raise RuntimeError("Headless Tw требует изоляции пользовательской конфигурации")
        options = [x for x in options[1:] if x not in {"--ignore-user-config", "--ephemeral", "--json"}]
    for attempt in range(2):
        result = subprocess.run([command[0], *options, "mcp", "list", "--json"], env=safe_env(),
                                capture_output=True, text=True, timeout=30, check=True)
        entries = json.loads(result.stdout)
        enabled = [entry["name"] for entry in entries if entry.get("enabled", True)]
        if enabled == ["tw"]:
            return
        if attempt or "tw" not in enabled:
            break
        for name in enabled:
            if name != "tw":
                if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                    raise RuntimeError("Имя MCP не поддерживает безопасное отключение")
                override = ["-c", "mcp_servers." + name + ".enabled=false"]
                options.extend(override)
                if not headless:
                    command[-1:-1] = override
    raise RuntimeError("Не удалось изолировать MCP: включены посторонние серверы. Сессия не запущена.")


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = arguments[0] if arguments else "chat"
    if command in {'install', 'diagnose'}:
        from .installation import main as installation_main
        return installation_main(arguments)
    if command in {"--help", "-h", "help"}:
        print("Tw — Codex со скиллом и контроллером задач\n\n"
              "  tw install [--bin-dir PATH]  Установить launcher без изменения shell-конфигов\n"
              "  tw diagnose [--sandbox]      Проверить установку до подключения проекта\n"
              "  tw profile configure --adapter static|next-ui\n"
              "  tw view TASK-NNN --mode working|checked\n"
              "  tw view status / stop        Постоянный просмотр проекта\n"
              "  tw init [--check 'команда']   Подключить текущий проект\n"
              "  tw                            Открыть сессию Codex с Tw\n"
              "  tw status / show TASK-NNN      Посмотреть задачи\n"
              "  tw add 'задача'                Поставить в очередь\n"
              "  tw add 'задача' --approval approve-plan\n"
              "  tw approve-plan TASK-NNN --version SHA256 --confirm TASK-NNN\n"
              "  tw revise-plan TASK-NNN 'замечания'\n"
              "  tw run TASK-NNN / worker       Исполнять без чата\n"
              "  tw add 'задача' --backlog       Сохранить без автозапуска\n"
              "  tw enqueue TASK-NNN ... --start Запустить выбранную группу\n"
              "  tw pause / resume TASK-NNN     Управление задачей\n"
              "  tw accept TASK-NNN --confirm TASK-NNN\n"
              "  tw request-changes TASK-NNN 'замечания'\n"
              "  tw reject TASK-NNN --reason 'причина' --confirm TASK-NNN\n"
              "  tw stop                       Остановить фоновый worker\n\n"
              "Настройки оболочки и глобальные конфиги не изменяются.")
        return
    if command == "stop":
        if len(arguments) != 1:
            raise SystemExit("Запустите tw stop из корня подключённого проекта")
        service = TaskService(Path.cwd())
        try:
            service.stop()
            print("Запрошена остановка worker; активная задача поставлена на паузу.")
        finally:
            service.close()
        return
    if command not in {"init", "chat"}:
        harness_main(arguments)
        return
    parser = argparse.ArgumentParser(prog="tw", description="Подключить проект и открыть защищённую сессию Tw")
    parser.add_argument("command", nargs="?", choices=["init", "chat"], default="chat")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--check")
    parser.add_argument("--model")
    parser.add_argument("--backend", choices=["gemini", "codex"])
    args = parser.parse_args(arguments)
    try:
        from .projects import Projects
        root = Projects(KIT).validate(str(args.project.absolute())).resolve()
        if args.command == "init":
            connect(root, args.check, args.model, args.backend)
            register_project(root)
            return
        if not (root / ".harness/tw.json").is_file():
            connect(root, args.check, args.model, args.backend)
        elif args.check or args.model:
            raise ValueError("check/model задаются при первом подключении или tw init")
        elif args.backend:
            connect(root, backend=args.backend)
        register_project(root)
        verified_setup_paths(root)
        config = json.loads((root / ".harness/config.json").read_text())
        doctor(config if config.get("backend") == "gemini" else config["codex"])
        launch = chat_command(root)
        verify_servers(launch)
        engine = "Gemini" if config.get("backend") == "gemini" else "Codex"
        print(f"Tw: {engine} + skill tw + контроллер. Задачи исполняются внешним worker; исходник в чате только для чтения.", flush=True)
        os.execvpe(launch[0], launch, safe_env())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"tw: {error}\n")
