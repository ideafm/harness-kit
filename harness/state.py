import json
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


STATES = {"trashed", "backlog", "queued", "running", "waiting", "awaiting_approval", "rate_limited", "paused", "blocked", "review", "accepted", "rejected"}
STAGE_KEYS = ("plan", "implement", "check", "review")


class StateChanged(RuntimeError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.home = self.root / ".harness"
        self.db = sqlite3.connect(self.home / "state.sqlite", timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT NOT NULL, stage TEXT NOT NULL,
                data TEXT NOT NULL, updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task INTEGER NOT NULL, time REAL NOT NULL,
                kind TEXT NOT NULL, data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                payload_hash TEXT NOT NULL, data TEXT NOT NULL
            );
        """)
        stat = (self.home / "state.sqlite").stat()
        self.identity = (stat.st_dev, stat.st_ino)

    @contextmanager
    def transaction(self):
        nested = self.db.in_transaction
        name = 'operation_' + uuid.uuid4().hex
        self.db.execute('SAVEPOINT ' + name if nested else 'BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self.db.execute('ROLLBACK TO ' + name if nested else 'ROLLBACK')
            if nested:
                self.db.execute('RELEASE ' + name)
            raise
        else:
            self.db.execute('RELEASE ' + name if nested else 'COMMIT')

    def ensure_current(self):
        try:
            stat = (self.home / "state.sqlite").stat()
        except FileNotFoundError:
            raise RuntimeError("Экземпляр проекта перемещён; перезапустите контроллер") from None
        if (stat.st_dev, stat.st_ino) != self.identity:
            raise RuntimeError("Экземпляр проекта заменён; перезапустите контроллер")

    def add(self, request, approval_mode="auto", placement='queue', backend=None, stage_backends=None, model=None, stage_models=None, scope=None):
        from .approval import validate_mode
        from .security import normalize_scope, validate_backend
        validate_mode(approval_mode)
        if placement not in ('queue', 'backlog'):
            raise ValueError('Нужно выбрать queue или backlog')
        config_data = json.loads((self.home / "config.json").read_text()) if (self.home / "config.json").is_file() else {}
        if backend is not None:
            selected_backend = validate_backend(backend)
        else:
            selected_backend = validate_backend(config_data.get("backend", "codex"))
        validated_stage_backends = None
        raw_stage_backends = stage_backends if stage_backends is not None else config_data.get("stage_backends")
        if raw_stage_backends is not None:
            if not isinstance(raw_stage_backends, dict):
                raise ValueError("stage_backends должен быть словарём этапов")
            validated_stage_backends = {}
            for stage_name, stage_backend in raw_stage_backends.items():
                if stage_name not in STAGE_KEYS:
                    raise ValueError(f"Неизвестный этап в stage_backends: {stage_name}")
                validated_stage_backends[stage_name] = validate_backend(stage_backend)
        validated_stage_models = None
        raw_stage_models = stage_models if stage_models is not None else config_data.get("stage_models")
        if raw_stage_models is not None:
            if not isinstance(raw_stage_models, dict):
                raise ValueError("stage_models должен быть словарём этапов")
            validated_stage_models = {}
            for stage_name, stage_model in raw_stage_models.items():
                if stage_name not in STAGE_KEYS or not isinstance(stage_model, str):
                    raise ValueError(f"Некорректная модель этапа в stage_models: {stage_name}")
                validated_stage_models[stage_name] = stage_model
        normalized_scope = normalize_scope(scope if scope is not None else config_data.get("path_scope") or config_data.get("scope"))
        self.ensure_current()
        with self.transaction():
            data = {"request": request, "attempts": {}, "answers": [], "approval_mode": approval_mode, "backend": selected_backend}
            if validated_stage_backends:
                data["stage_backends"] = validated_stage_backends
            if model is not None:
                if not isinstance(model, str):
                    raise ValueError("model должен быть строкой")
                data["model"] = model
            if validated_stage_models:
                data["stage_models"] = validated_stage_models
            if normalized_scope:
                data["path_scope"] = normalized_scope
            if placement == 'queue':
                data['queue_order'] = self.next_queue_order()
            row = self.db.execute(
                "INSERT INTO tasks(state,stage,data,updated) VALUES(?,?,?,?)",
                ('backlog' if placement == 'backlog' else 'queued', "plan", json.dumps(data), time.time()),
            )
            ident = row.lastrowid
            event_detail = {"request": request, "approval_mode": approval_mode, 'placement': placement, "backend": selected_backend}
            if validated_stage_backends:
                event_detail["stage_backends"] = validated_stage_backends
            if normalized_scope:
                event_detail["path_scope"] = normalized_scope
            self.event(ident, "created", event_detail)
        return self.get(ident)

    def next_queue_order(self):
        return max((max(task['id'], task['data'].get('queue_order', 0)) for task in self.tasks()), default=0) + 1

    def runnable(self):
        return sorted((task for task in self.tasks() if task['state'] in {'queued', 'running', 'rate_limited'}),
            key=lambda task: (task['state'] != 'running', task['data'].get('queue_order', task['id']), task['id']))

    def enqueue(self, identifiers):
        if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 100 or any(type(ident) is not int or ident < 1 for ident in identifiers) or len(set(identifiers)) != len(identifiers):
            raise ValueError('Нужны от 1 до 100 разных положительных номеров задач')
        with self.transaction():
            tasks = [self.get(ident) for ident in identifiers]
            if any(task['state'] not in {'backlog', 'queued'} for task in tasks):
                raise ValueError('В очередь можно добавить только backlog или queued')
            position = self.next_queue_order()
            for index, task in enumerate(tasks):
                previous = task['state']
                task['state'] = 'queued'
                task['data']['queue_order'] = position + index
                self.save(task, 'enqueued', {'position': position + index, 'group': identifiers},
                    expected=previous, expected_updated=task['updated'])
        return [self.get(ident) for ident in identifiers]

    def get(self, ident):
        self.ensure_current()
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone()
        if not row:
            raise ValueError(f"Нет задачи {ident}")
        return dict(row) | {"data": json.loads(row["data"])}

    def tasks(self):
        self.ensure_current()
        return [self.get(r[0]) for r in self.db.execute("SELECT id FROM tasks ORDER BY id")]

    def save(self, task, kind, detail=None, expected=None, expected_updated=None):
        self.ensure_current()
        if task["state"] not in STATES:
            raise ValueError("Неизвестное состояние")
        with self.transaction():
            parameters = [task["state"], task["stage"], json.dumps(task["data"], ensure_ascii=False), time.time(), task["id"]]
            condition = ""
            if expected is not None:
                condition = " AND state=?"
                parameters.append(expected)
            if expected_updated is not None:
                condition += " AND updated=?"
                parameters.append(expected_updated)
            changed = self.db.execute("UPDATE tasks SET state=?,stage=?,data=?,updated=? WHERE id=?" + condition, parameters)
            if changed.rowcount != 1:
                raise StateChanged("Состояние задачи изменилось другим процессом")
            self.event(task["id"], kind, detail or {})

    def event(self, ident, kind, data):
        self.db.execute("INSERT INTO events(task,time,kind,data) VALUES(?,?,?,?)",
                        (ident, time.time(), kind, json.dumps(data, ensure_ascii=False)))

    def pause(self, ident):
        self.ensure_current()
        with self.transaction():
            changed = self.db.execute("UPDATE tasks SET state='paused',updated=? WHERE id=? AND state IN ('queued','running','rate_limited')",
                                      (time.time(), ident))
            if changed.rowcount != 1:
                raise ValueError("Эту задачу сейчас нельзя приостановить")
            self.event(ident, "pause_requested", {})

    def delete(self, ident):
        self.ensure_current()
        with self.transaction():
            task = self.get(ident)
            previous = task['state']
            if previous in {'running', 'trashed'}:
                raise ValueError('Работающую или уже удалённую задачу удалить нельзя')
            task['data']['deleted_from_state'] = previous
            task['state'] = 'trashed'
            self.save(task, 'task_deleted', {'previous_state': previous},
                      expected=previous, expected_updated=task['updated'])

    def restore(self, ident):
        self.ensure_current()
        with self.transaction():
            task = self.get(ident)
            if task['state'] != 'trashed':
                raise ValueError('Восстановить можно только удалённую задачу')
            previous = task['data'].pop('deleted_from_state', 'paused')
            task['state'] = previous if previous in STATES - {'running', 'queued', 'rate_limited', 'trashed'} else 'paused'
            task['data'].pop('retry_at', None)
            self.save(task, 'task_restored', {'restored_state': task['state']},
                      expected='trashed', expected_updated=task['updated'])

    def events(self, ident):
        self.ensure_current()
        return [dict(r) | {"data": json.loads(r["data"])} for r in self.db.execute(
            "SELECT * FROM events WHERE task=? ORDER BY id", (ident,))]

    def git_toplevel(self):
        candidates = [parent for parent in (self.root, *list(self.root.parents)[:3]) if (parent / ".git").exists()]
        return candidates[-1] if candidates else self.root

    def external_tasks_root(self):
        from .projects import project_id
        toplevel = self.git_toplevel()
        base = toplevel.parent if toplevel.parent != toplevel else Path(tempfile.gettempdir()).resolve()
        return base / f"{toplevel.name}-harness-tasks" / f"{project_id(self.root)}-{self.identity[1]}" / "tasks"

    def folder(self, ident):
        self.ensure_current()
        legacy = self.home / "tasks" / f"TASK-{ident:03}"
        if legacy.exists() or legacy.is_symlink():
            return legacy
        path = self.external_tasks_root() / f"TASK-{ident:03}"
        path.mkdir(parents=True, exist_ok=True)
        return path


def atomic_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)
