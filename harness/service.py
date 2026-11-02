import contextlib
import io
import json
import os
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path

from .cli import dispatch_store
from .runner import lock
from .security import safe_env
from .state import Store, atomic_json


KIT = Path(__file__).resolve().parents[1]
ARTIFACTS = {"specification": "specification.md", "plan": "plan.md", "summary": "summary.txt",
             "diff": "changes.patch", "checks": "check.log", "review": "review.md"}


class TaskService:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if any(path.is_symlink() for path in (self.root / ".harness", self.root / ".harness/config.json",
                                              self.root / ".harness/state.sqlite")):
            raise ValueError("Состояние контроллера заменено ссылкой")
        if not (self.root / ".harness/config.json").is_file():
            raise ValueError("Проект не подключён: выполните tw init")
        self.store = Store(self.root)

    def close(self):
        self.store.db.close()

    def view(self, task):
        data = task["data"]
        result = {k: task[k] for k in ("id", "state", "stage", "updated")}
        for key in ("request", "question", "question_kind", "reason", "retry_at", "implementation_summary", "review_verdict",
                    "approval_mode", "effective_approval", "plan_version", "plan_approval", "risk", "scope", "approval_reason"):
            if key in data:
                result[key] = data[key]
        result["artifacts"] = [name for name, filename in ARTIFACTS.items()
                               if (self.store.folder(task["id"]) / filename).is_file()]
        return result

    def status(self):
        return {"project": str(self.root), "tasks": [self.view(t) for t in self.store.tasks()],
                "worker": self.worker_status()}

    def show(self, ident):
        return self.view(self.store.get(ident))

    def artifact(self, ident, name):
        if name not in ARTIFACTS:
            raise ValueError("Недопустимый артефакт")
        self.store.get(ident)
        path = self.store.folder(ident) / ARTIFACTS[name]
        if path.is_symlink() or not path.is_file():
            raise ValueError("Артефакт пока недоступен")
        with path.open() as handle:
            text = handle.read(80001)
        return {"task": ident, "artifact": name, "text": text[:80000], "truncated": len(text) > 80000}

    def worker_status(self):
        try:
            with lock(self.store, "worker.lock"):
                locked = False
        except RuntimeError:
            locked = True
        record = self.store.home / "worker.json"
        try:
            data = json.loads(record.read_text())
            os.kill(data["pid"], 0)
        except (FileNotFoundError, ProcessLookupError):
            return {"running": locked, "managed_elsewhere": locked}
        if locked or time.time() - data["started"] < 10:
            return {"running": True, "pid": data["pid"], "starting": not locked}
        return {"running": False}

    def start(self, ident):
        task = self.store.get(ident)
        if task["state"] not in {"queued", "running", "rate_limited"}:
            raise ValueError("Для этой задачи нужен ответ или resume, либо она уже завершена")
        with lock(self.store, "worker-launch.lock"):
            (self.store.home / "worker.stop").unlink(missing_ok=True)
            status = self.worker_status()
            if not status["running"]:
                try:
                    with lock(self.store, "worker.lock"):
                        pass
                except RuntimeError:
                    return {"task": self.show(ident), "worker": {"running": True, "managed_elsewhere": True}}
                with (self.store.home / "worker.log").open("a") as output:
                    process = subprocess.Popen([str(Path(sys.executable).resolve()), str(KIT / "bin/harness"),
                        "--project", str(self.root), "worker"], cwd=self.root, env=safe_env(),
                        stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                atomic_json(self.store.home / "worker.json", {"pid": process.pid, "started": time.time()})
                status = {"running": True, "pid": process.pid}
        return {"task": self.show(ident), "worker": status}

    def submit(self, request, start=True, approval_mode="auto"):
        if not isinstance(request, str) or not request.strip() or len(request) > 50000:
            raise ValueError("Нужен текст задачи от 1 до 50000 символов")
        task = self.store.add(request, approval_mode)
        if start:
            try:
                return self.start(task["id"])
            except (OSError, RuntimeError) as error:
                return {"task": self.view(task), "worker_error": str(error)}
        return {"task": self.view(task), "worker": self.worker_status()}

    def operate(self, action, ident, text=None):
        if action not in {"pause", "resume", "answer"}:
            raise ValueError("Недопустимая операция")
        if action == "answer" and (not isinstance(text, str) or not text.strip() or len(text) > 50000):
            raise ValueError("Нужен непустой ответ до 50000 символов")
        arguments = Namespace(command=action, task=ident, text=text)
        with contextlib.redirect_stdout(io.StringIO()):
            dispatch_store(arguments, self.store)
        if action in {"resume", "answer"}:
            return self.start(ident)
        return {"task": self.show(ident), "worker": self.worker_status()}

    def stop(self):
        (self.store.home / "worker.stop").write_text("stop\n")
        for task in self.store.tasks():
            if task["state"] == "running":
                self.store.pause(task["id"])
        return {"stop_requested": True}
