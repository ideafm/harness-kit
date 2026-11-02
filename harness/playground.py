import argparse
import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path

from .cli import main as harness_main
from .runner import lock
from .security import doctor, git, protected, safe_env, sandbox_command
from .state import Store, atomic_json


KIT = Path(__file__).resolve().parents[1]
TEMPLATE_FILES = ["app.py", "README.md", "tests/test_app.py"]


class Playground:
    def __init__(self, base=None, kit=KIT):
        self.kit = Path(kit).resolve()
        self.base = Path(base or self.kit / "lab").resolve()
        self.project = self.base / "taskboard"
        self.control = self.base / "control.json"

    @contextmanager
    def controller_lock(self):
        self.base.mkdir(parents=True, exist_ok=True)
        with (self.base / "controller.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Другая команда playground уже работает") from None
            yield

    def metadata(self):
        if not self.control.is_file() or self.control.is_symlink() or self.project.is_symlink():
            raise ValueError("Нет управляемого учебного экземпляра; сначала prepare/create")
        data = json.loads(self.control.read_text())
        if data.get("project") != str(self.project) or data.get("kind") != "harness-taskboard-v1":
            raise ValueError("Маркер учебного проекта не совпадает")
        return data

    def prepare(self):
        if self.project.exists() or self.project.is_symlink() or self.control.exists():
            raise ValueError("Учебный экземпляр уже существует; ничего не перезаписано")
        self.project.mkdir(parents=True)
        for name in TEMPLATE_FILES:
            target = self.project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.kit / "examples/taskboard" / name, target)
        (self.project / ".gitignore").write_text(".harness/\n__pycache__/\n*.pyc\ntasks.json\n")
        atomic_json(self.control, {"kind": "harness-taskboard-v1", "project": str(self.project),
                                   "created": time.time(), "baseline": None})
        return self.project

    def create(self, confirmed=False):
        if not confirmed:
            raise ValueError("Нужно явное --confirm-initial-commit для начального коммита учебного проекта")
        if not self.project.exists():
            self.prepare()
        data = self.metadata()
        if data.get("baseline"):
            raise ValueError("Учебный проект уже инициализирован")
        for name in TEMPLATE_FILES:
            path = self.project / name
            if path.is_symlink() or path.read_bytes() != (self.kit / "examples/taskboard" / name).read_bytes():
                raise ValueError(f"Подготовленный шаблон изменён: {name}; коммит не создан")
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.project)], env=safe_env(), check=True)
        git(self.project, "add", "--", *TEMPLATE_FILES, ".gitignore")
        git(self.project, "-c", "user.name=Harness Playground", "-c", "user.email=playground@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "chore: initialize taskboard playground")
        data["baseline"] = git(self.project, "rev-parse", "HEAD").decode().strip()
        atomic_json(self.control, data)
        check = shlex.join([str(Path(sys.executable).resolve()), "-m", "unittest", "discover", "-s", "tests", "-v"])
        harness_main(["--project", str(self.project), "init", "--check", check, "--model", "gpt-6.1-sol"])
        return self.project

    def ready(self):
        data = self.metadata()
        if not data.get("baseline"):
            raise ValueError("Шаблон подготовлен; нужен create --confirm-initial-commit")
        return data

    def queue(self, scenario):
        self.ready()
        if scenario not in {"filter", "clarify"}:
            raise ValueError("Неизвестный сценарий")
        prompt = (self.kit / "examples/scenarios" / f"{scenario}.md").read_text()
        harness_main(["--project", str(self.project), "add", prompt])

    def check(self):
        self.ready()
        codex = shutil.which("codex")
        if not codex:
            raise ValueError("Codex CLI не найден")
        print(doctor(codex), flush=True)
        subprocess.run(sandbox_command(codex, self.project, True,
            [str(Path(sys.executable).resolve()), "-m", "unittest", "discover", "-s", "tests", "-v"]),
            cwd=self.project, env=safe_env(), timeout=60, check=True)

    def no_active_processes(self, store):
        for task in store.tasks():
            record = store.folder(task["id"]) / "active.json"
            if not record.exists():
                continue
            pid = json.loads(record.read_text())["pid"]
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            raise RuntimeError(f"Учебный процесс {pid} ещё существует; сначала остановите исполнение")

    def apply(self, ident, confirmation):
        data = self.ready()
        if confirmation != f"TASK-{ident:03}":
            raise ValueError("Нужно точное --confirm TASK-NNN")
        store = Store(self.project)
        try:
            with lock(store):
                self.no_active_processes(store)
                task = store.get(ident)
                if task["state"] != "accepted":
                    raise ValueError("Сначала изучите результат и выполните accept TASK-NNN --confirm TASK-NNN")
                if task["data"]["base"] != data["baseline"]:
                    raise ValueError("Задача основана на другой исходной версии")
                if git(self.project, "rev-parse", "HEAD").decode().strip() != data["baseline"]:
                    raise ValueError("HEAD учебного проекта изменился; применение запрещено")
                from .tw import verified_setup_paths
                setup_paths = verified_setup_paths(self.project)
                if git(self.project, "status", "--porcelain", "--untracked-files=all", "--", ".",
                       *(f":!{name}" for name in setup_paths)):
                    raise ValueError("Исходный учебный проект изменён; сначала изучите изменения или выполните reset")
                from .runner import Runner
                before = task["data"]["changes"]
                Runner(store).report(task)
                if before != task["data"]["changes"]:
                    raise ValueError("Рабочая копия изменилась после приёмки")
                for change in before:
                    if change["path"] not in TEMPLATE_FILES or protected(change["path"]):
                        raise ValueError("Этот учебный сценарий допускает только app.py, README.md, tests/test_app.py")
                    if change["mode"] != "100644":
                        raise ValueError("Изменение прав файла не поддерживается учебным применением")
                patch_path = store.folder(ident) / "changes.patch"
                git(self.project, "apply", "--check", "--", str(patch_path))
                git(self.project, "apply", "--", str(patch_path))
                store.save(task, "playground_applied", {"paths": [c["path"] for c in before]})
                print("Изменения применены только в учебном проекте; коммит не создан.")
        finally:
            store.db.close()

    def reset(self, confirmation):
        if confirmation != "TASKBOARD":
            raise ValueError("Нужно --confirm TASKBOARD: экземпляр будет архивирован и создан заново")
        self.metadata()
        archive = self.base / "archive" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        state_exists = (self.project / ".harness/state.sqlite").exists()
        store = Store(self.project) if state_exists else None
        try:
            with lock(store, "worker.lock") if store else nullcontext(), lock(store) if store else nullcontext():
                if store:
                    self.no_active_processes(store)
                archive.mkdir(parents=True)
                self.project.rename(archive / "taskboard")
                self.control.rename(archive / "control.json")
                if store:
                    store.db.close()
                self.create(confirmed=True)
        finally:
            if store:
                store.db.close()
        print(f"Предыдущий опыт сохранён: {archive}\nЧистый экземпляр: {self.project}")
        return archive


def main(argv=None):
    parser = argparse.ArgumentParser(description="Учебная площадка Codex harness")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    create = sub.add_parser("create")
    create.add_argument("--confirm-initial-commit", action="store_true")
    sub.add_parser("check")
    queue = sub.add_parser("queue")
    queue.add_argument("scenario", choices=["filter", "clarify"])
    apply = sub.add_parser("apply")
    apply.add_argument("task", type=int)
    apply.add_argument("--confirm", required=True)
    reset = sub.add_parser("reset")
    reset.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    playground = Playground()
    try:
        with playground.controller_lock():
            if args.command == "prepare":
                print(playground.prepare())
            elif args.command == "create":
                print(playground.create(args.confirm_initial_commit))
            elif args.command == "queue":
                playground.queue(args.scenario)
            elif args.command == "check":
                playground.check()
            elif args.command == "apply":
                playground.apply(args.task, args.confirm)
            else:
                playground.reset(args.confirm)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"playground: {error}\n")
