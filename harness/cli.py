import argparse
import json
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .approval import MODES, approve, revise
from .decisions import decide
from .runner import Runner, lock
from .security import doctor, git
from .state import Store, atomic_json


def parser():
    command = argparse.ArgumentParser(description="Автономный Codex harness")
    command.add_argument("--project", type=Path, default=Path.cwd())
    sub = command.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Инициализировать проект")
    init.add_argument("--check", required=True, help="Команда проверок без shell-операторов")
    init.add_argument("--model", default="")
    init.add_argument("--codex", default="codex")
    init.add_argument("--timeout", type=int, default=1800)
    add = sub.add_parser("add", help="Добавить задачу")
    add.add_argument("request")
    add.add_argument("--approval", choices=MODES, default="auto")
    sub.add_parser("status", help="Показать задачи и ожидания")
    sub.add_parser("doctor", help="Проверить ограничения на безопасных canary-файлах")
    baseline = sub.add_parser('prepare-baseline', help='Подготовить основу из проверенного результата задачи')
    baseline.add_argument('task', type=task_id)
    baseline.add_argument('--from-task', required=True, type=task_id)
    retry_review = sub.add_parser('retry-review', help='Повторить ревью проверенного неизменённого результата')
    retry_review.add_argument('task', type=task_id)
    for action in ("run", "show", "pause", "resume", "accept"):
        child = sub.add_parser(action)
        child.add_argument("task", type=task_id)
        if action == "accept":
            child.add_argument("--confirm", required=True, help="Точная строка TASK-NNN")
    answer = sub.add_parser("answer")
    answer.add_argument("task", type=task_id)
    answer.add_argument("text")
    approval = sub.add_parser("approve-plan", help="Утвердить конкретную версию спецификации и плана")
    approval.add_argument("task", type=task_id)
    approval.add_argument("--version", required=True)
    approval.add_argument("--confirm", required=True)
    revision = sub.add_parser("revise-plan", help="Вернуть план с замечаниями")
    revision.add_argument("task", type=task_id)
    revision.add_argument("text")
    changes = sub.add_parser("request-changes", help="Вернуть результат на доработку")
    changes.add_argument("task", type=task_id)
    changes.add_argument("text")
    rejection = sub.add_parser("reject", help="Окончательно отклонить результат с сохранением истории")
    rejection.add_argument("task", type=task_id)
    rejection.add_argument("--reason", required=True)
    rejection.add_argument("--confirm", required=True)
    worker = sub.add_parser("worker", help="Обрабатывать очередь до Ctrl-C")
    worker.add_argument("--once", action="store_true")
    return command


def task_id(value):
    try:
        ident = int(value.removeprefix("TASK-"))
        if ident < 1:
            raise ValueError()
        return ident
    except ValueError:
        raise argparse.ArgumentTypeError("Ожидается TASK-001 или 1") from None


def label(task):
    return f"TASK-{task['id']:03}"


def summary(task):
    data = task["data"]
    detail = data.get("question") if task["state"] == "waiting" else data.get("reason", "")
    retry = ""
    if task["state"] == "rate_limited":
        retry = " · повтор " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["retry_at"]))
    approval = ""
    if data.get("plan_version"):
        approval = f"\n  Режим: {data.get('effective_approval', 'auto')} · Версия плана: {data['plan_version']}"
    return f"{label(task)} · {task['state']} · {task['stage']}{retry}\n  {data['request']}" + (f"\n  {detail}" if detail else "") + approval


def init(args):
    root = args.project.resolve()
    if git(root, "rev-parse", "--show-toplevel").decode().strip() != str(root):
        raise ValueError("Укажите корень Git-проекта")
    git(root, "rev-parse", "HEAD")
    home = root / ".harness"
    if home.exists():
        raise ValueError(".harness уже существует; настройки не перезаписаны")
    check = shlex.split(args.check)
    if not check or args.timeout < 1:
        raise ValueError("Нужна команда проверок и положительный timeout")
    if any(token in {";", "&&", "||", "|", ">", "<"} for token in check):
        raise ValueError("check — argv, без shell-операторов; вынесите составную проверку в скрипт")
    codex = shutil.which(args.codex)
    if not codex:
        raise ValueError("Codex CLI не найден")
    executable = shutil.which(check[0])
    if not executable:
        raise ValueError("Исполняемый файл команды check не найден")
    check[0] = str(Path(executable).resolve())
    home.mkdir(mode=0o700)
    atomic_json(home / "config.json", {"version": 1, "codex": codex, "model": args.model,
                "check": check, "timeout": args.timeout, "max_attempts": 3})
    store = Store(root)
    store.db.close()
    print(f"Инициализировано: {home}\nПроверки: {check}\nПеред исполнением всегда запускается canary-проверка sandbox.")


def dispatch(args):
    if args.command == "init":
        init(args)
        return
    root = args.project.resolve()
    if not (root / ".harness" / "config.json").is_file():
        raise ValueError("Сначала выполните init --check 'команда проверок'")
    store = Store(root)
    try:
        return dispatch_store(args, store)
    finally:
        store.db.close()


def dispatch_store(args, store):
    action = args.command
    if action == "add":
        if not args.request.strip():
            raise ValueError("Пустая задача")
        print(summary(store.add(args.request, getattr(args, "approval", "auto"))))
    elif action == "status":
        priority = {"waiting": 0, "awaiting_approval": 0, "blocked": 1, "review": 2, "running": 3, "rate_limited": 4,
                    "paused": 5, "queued": 6, "accepted": 7, "rejected": 8}
        for task in sorted(store.tasks(), key=lambda t: (priority[t["state"]], t["id"])):
            print(summary(task))
    elif action == "doctor":
        config = json.loads((store.home / "config.json").read_text())
        print(doctor(config["codex"]))
    elif action == 'retry-review':
        from .recovery import retry_review
        retry_review(store, args.task)
        print('Проверенный результат направлен на повторное ревью.')
    elif action == 'prepare-baseline':
        from .baseline import prepare
        prepare(store, args.task, args.from_task)
        print('Основа подготовлена; приёмка и применение не выполнялись. Для продолжения используйте answer/resume.')
    elif action == "worker":
        runner = Runner(store)
        with lock(store, "worker.lock"):
            while True:
                if (store.home / "worker.stop").exists():
                    break
                for task in store.tasks():
                    if (store.home / "worker.stop").exists():
                        break
                    if task["state"] in {"queued", "running", "rate_limited"}:
                        try:
                            runner.run(task["id"])
                        except (RuntimeError, ValueError, TimeoutError, subprocess.SubprocessError) as error:
                            print(str(error), file=sys.stderr, flush=True)
                if args.once:
                    break
                time.sleep(5)
    elif action == "run":
        Runner(store).run(args.task)
        print(summary(store.get(args.task)))
    elif action == "approve-plan":
        approve(store, args.task, args.version, args.confirm)
        print("Спецификация и план утверждены. Задача в очереди; права доступа не изменены.")
    elif action == "revise-plan":
        revise(store, args.task, args.text)
        print("Замечания сохранены. Планирование вернулось в очередь.")
    elif action in {"request-changes", "reject"}:
        text = args.text if action == "request-changes" else args.reason
        decide(store, args.task, action, text, getattr(args, "confirm", None))
        print("Результат возвращён на доработку; задача в очереди." if action == "request-changes"
              else "Результат отклонён. История и рабочая копия сохранены.")
    else:
        task = store.get(args.task)
        initial_state = task["state"]
        data = task["data"]
        if action == "show":
            print(summary(task))
            print(f"Документы и логи: {store.folder(args.task)}")
            for event in store.events(args.task):
                print(time.strftime("%H:%M:%S", time.localtime(event["time"])), event["kind"],
                      json.dumps(event["data"], ensure_ascii=False))
        elif action == "pause":
            store.pause(task["id"])
        elif action == "resume":
            if task["state"] not in {"paused", "blocked", "rate_limited"}:
                raise ValueError("Для вопроса используйте answer; завершённую задачу возобновлять нельзя")
            task["state"] = "queued"
            data.pop("reason", None)
            previous_attempts = dict(data["attempts"])
            stages = ('plan', 'implement', 'check', 'review')
            for stage in stages[stages.index(task['stage']):]:
                data['attempts'][stage] = 0
            store.save(task, "resume_requested", {"previous_attempts": previous_attempts}, expected=initial_state)
        elif action == "answer":
            if task["state"] != "waiting" or not args.text.strip():
                raise ValueError("Нужна ожидающая ответа задача и непустой ответ")
            data["answers"].append({"question": data.pop("question"), "kind": data.pop("question_kind"),
                                    "answer": args.text, "time": time.time()})
            task["state"] = "queued"
            store.save(task, "answered", data["answers"][-1], expected=initial_state)
            print("Ответ сохранён. Права доступа не изменены. Продолжение: worker или run.")
        elif action == "accept":
            if task["state"] != "review" or args.confirm != label(task):
                raise ValueError("Нужна задача на приёмке и --confirm TASK-NNN")
            runner = Runner(store)
            previous = data["changes"]
            runner.report(task)
            if previous != data["changes"]:
                raise ValueError("Рабочая копия изменилась после ревью; приёмка запрещена")
            task["state"] = "accepted"
            store.save(task, "accepted", expected=initial_state, expected_updated=task['updated'])
            print("Приёмка записана. Исходная ветка не изменена. Diff: " + str(store.folder(args.task) / "changes.patch"))


def main(argv=None):
    def stop(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    args = parser().parse_args(argv)
    try:
        dispatch(args)
    except KeyboardInterrupt:
        print("Остановлено; состояние сохранено.", file=sys.stderr)
        raise SystemExit(130)
    except (OSError, RuntimeError, ValueError, TimeoutError, subprocess.SubprocessError) as error:
        print(f"harness: {error}", file=sys.stderr)
        raise SystemExit(1)
