import argparse
import json
from pathlib import Path


def load_tasks(store):
    path = Path(store)
    return json.loads(path.read_text()) if path.exists() else []


def save_tasks(store, tasks):
    path = Path(store)
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")


def add_task(store, title):
    title = title.strip()
    if not title:
        raise ValueError("Название задачи не должно быть пустым")
    tasks = load_tasks(store)
    task = {"id": max((item["id"] for item in tasks), default=0) + 1, "title": title, "done": False}
    tasks.append(task)
    save_tasks(store, tasks)
    return task


def complete_task(store, ident):
    tasks = load_tasks(store)
    for task in tasks:
        if task["id"] == ident:
            task["done"] = True
            save_tasks(store, tasks)
            return task
    raise ValueError(f"Нет задачи {ident}")


def list_tasks(store):
    return load_tasks(store)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Учебный список задач")
    parser.add_argument("--store", default="tasks.json")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add")
    add.add_argument("title")
    commands.add_parser("list")
    done = commands.add_parser("done")
    done.add_argument("id", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "add":
            result = add_task(args.store, args.title)
        elif args.command == "done":
            result = complete_task(args.store, args.id)
        else:
            result = list_tasks(args.store)
        print(json.dumps(result, ensure_ascii=False))
    except ValueError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
