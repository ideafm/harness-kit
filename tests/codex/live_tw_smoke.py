import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.runner import lock
from harness.security import doctor, safe_env
from harness.service import TaskService
from harness.tw import chat_command, connect, verify_servers


with tempfile.TemporaryDirectory(prefix="tw-live-") as temporary:
    root = Path(temporary).resolve()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "app.py").write_text("def value():\n    return 1\n")
    subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Harness Fixture", "-c", "user.email=fixture@example.invalid",
                    "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"], check=True)
    executable = str(Path(sys.executable).resolve())
    import shlex
    check = shlex.join([executable, "-B", "-c", "import app; assert app.value() == 2"])
    connect(root, check=check, model="gpt-6.1-sol")
    print(doctor("codex"), flush=True)
    service = TaskService(root)
    try:
        command = chat_command(root, headless=True, prompt="Используй skill $tw. Один раз вызови tw_submit с start=true: 'Измени только app.py: value() должна возвращать целое число 2 вместо 1. Критерий: controller_check завершается успешно. Другие файлы не нужны.' Верни номер. Не выполняй реализацию сам, не вызывай другие изменяющие инструменты и не повторяй submit.")
        verify_servers(command)
        result = subprocess.run(command, cwd=root, env=safe_env(), capture_output=True, text=True, timeout=180)
        (root / ".harness/chat-smoke.jsonl").write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(result.stderr[-4000:] + result.stdout[-6000:])
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        calls = [e.get("item", {}) for e in events if e.get("type") == "item.completed"]
        assert any(item.get("type") == "mcp_tool_call" and item.get("tool") == "tw_submit" for item in calls), result.stdout
        print("Codex chat exited; external worker continues", flush=True)
        deadline = time.monotonic() + 300
        previous = None
        while time.monotonic() < deadline:
            tasks = service.store.tasks()
            assert len(tasks) == 1, tasks
            task = tasks[0]
            current = (task["state"], task["stage"])
            if current != previous:
                print("TASK-001:", *current, flush=True)
                previous = current
            if task["state"] in {"waiting", "blocked", "review", "accepted"}:
                break
            time.sleep(2)
        task = service.store.get(1)
        if task["state"] != "review":
            details = []
            for path in service.store.folder(1).glob('*.jsonl'):
                details.append(path.name + '\n' + path.read_text(errors='replace')[-10000:])
            raise RuntimeError(json.dumps(task, ensure_ascii=False) + "\n" + (root / ".harness/worker.log").read_text()[-6000:] + '\n' + '\n'.join(details))
        assert task["data"]["review_verdict"] == "pass", task
        assert "return 1" in (root / "app.py").read_text()
        print("LIVE TW SMOKE PASSED: chat → MCP → detached worker → checks → readonly review", flush=True)
    finally:
        service.stop()
        deadline = time.monotonic() + 30
        while True:
            try:
                with lock(service.store, "worker.lock"):
                    break
            except RuntimeError:
                if time.monotonic() > deadline:
                    raise RuntimeError("Worker did not stop; temporary fixture retained by active process")
                time.sleep(0.5)
        service.close()
