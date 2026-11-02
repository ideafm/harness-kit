import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.cli import main


with tempfile.TemporaryDirectory(prefix="harness-live-") as temporary:
    root = Path(temporary)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "app.py").write_text("def value():\n    return 1\n")
    subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Harness", "-c", "user.email=harness@example.invalid",
                    "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture"], check=True)
    check = f"{sys.executable} -c 'import app; assert app.value() == 2'"
    prefix = ["--project", str(root)]
    main(prefix + ["init", "--check", check, "--model", "gpt-6.1-sol", "--timeout", "180"])
    main(prefix + ["add", "Измени только app.py: value() должна возвращать 2 вместо 1. Критерий: python проверяет app.value() == 2. Другие файлы не нужны."])
    try:
        main(prefix + ["run", "1"])
    except BaseException:
        for log in (root / ".harness/tasks/TASK-001").glob("*.jsonl"):
            print(log.name, log.read_text(errors="replace")[-10000:])
        raise
    from harness.state import Store
    store = Store(root)
    task = store.get(1)
    assert task["state"] == "review", task
    assert "return 1" in (root / "app.py").read_text()
    print("LIVE SMOKE PASSED", json.dumps(task["data"]["changes"], ensure_ascii=False))
