import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from harness.playground import Playground
from harness.security import git
from harness.state import Store


class PlaygroundTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.playground = Playground(base=Path(self.temporary.name) / "lab")

    def tearDown(self):
        self.temporary.cleanup()

    def create(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.playground.create(confirmed=True)

    def test_prepare_creates_only_template_without_git_or_harness(self):
        project = self.playground.prepare()
        self.assertTrue((project / "app.py").is_file())
        self.assertFalse((project / ".git").exists())
        self.assertFalse((project / ".harness").exists())
        self.assertIsNone(self.playground.metadata()["baseline"])

    def test_prepare_refuses_existing_instance(self):
        self.playground.prepare()
        with self.assertRaises(ValueError):
            self.playground.prepare()

    def test_create_requires_explicit_flag(self):
        with self.assertRaisesRegex(ValueError, "confirm-initial-commit"):
            self.playground.create()
        self.assertFalse(self.playground.project.exists())

    def test_create_rejects_changed_template_before_commit(self):
        self.playground.prepare()
        (self.playground.project / "app.py").write_text("changed")
        with self.assertRaisesRegex(ValueError, "изменён"):
            self.create()
        self.assertFalse((self.playground.project / ".git").exists())

    def test_create_initializes_clean_independent_repository(self):
        self.create()
        metadata = self.playground.ready()
        self.assertEqual(git(self.playground.project, "rev-parse", "HEAD").decode().strip(), metadata["baseline"])
        self.assertEqual(git(self.playground.project, "status", "--porcelain"), b"")
        self.assertTrue((self.playground.project / ".harness/state.sqlite").is_file())

    def test_reset_preserves_history_and_old_worker_is_rejected(self):
        self.create()
        project = self.playground.project
        old = Store(project)
        old.add("previous experiment")
        (project / "app.py").write_text("experiment")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                archive = self.playground.reset("TASKBOARD")
            self.assertEqual((archive / "taskboard/app.py").read_text(), "experiment")
            self.assertTrue((archive / "taskboard/.harness/state.sqlite").is_file())
            self.assertIn("def list_tasks", (project / "app.py").read_text())
            with self.assertRaisesRegex(RuntimeError, "заменён"):
                old.tasks()
            fresh = Store(project)
            try:
                self.assertEqual(fresh.tasks(), [])
            finally:
                fresh.db.close()
        finally:
            old.db.close()

    def test_reset_requires_exact_confirmation(self):
        self.playground.prepare()
        with self.assertRaises(ValueError):
            self.playground.reset("yes")
        self.assertTrue(self.playground.project.exists())

    def test_reset_refuses_running_executor(self):
        self.create()
        store = Store(self.playground.project)
        from harness.runner import lock
        try:
            with lock(store):
                with self.assertRaisesRegex(RuntimeError, "уже работает"):
                    self.playground.reset("TASKBOARD")
        finally:
            store.db.close()

    def test_reset_refuses_idle_worker(self):
        self.create()
        store = Store(self.playground.project)
        from harness.runner import lock
        try:
            with lock(store, "worker.lock"):
                with self.assertRaisesRegex(RuntimeError, "уже работает"):
                    self.playground.reset("TASKBOARD")
        finally:
            store.db.close()

    def test_apply_requires_accepted_result(self):
        self.create()
        store = Store(self.playground.project)
        store.add("not accepted")
        store.db.close()
        with self.assertRaisesRegex(ValueError, "Сначала изучите"):
            self.playground.apply(1, "TASK-001")

    def accepted_task(self):
        from harness.runner import Runner
        store = Store(self.playground.project)
        task = store.add("Изменить описание")
        folder = store.folder(task["id"])
        workspace = folder / "workspace"
        from harness.security import export_snapshot
        baseline = self.playground.ready()["baseline"]
        manifest = export_snapshot(self.playground.project, workspace, baseline)
        (workspace / "README.md").write_text("Updated taskboard\n")
        task["data"].update(workspace=str(workspace), base=baseline, manifest=manifest, files=["README.md"])
        Runner(store).report(task)
        task["state"] = "accepted"
        task["stage"] = "done"
        store.save(task, "fixture_accepted")
        store.db.close()

    def test_apply_changes_only_fixture_and_creates_no_commit(self):
        self.create()
        self.accepted_task()
        baseline = self.playground.ready()["baseline"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.playground.apply(1, "TASK-001")
        self.assertEqual((self.playground.project / "README.md").read_text(), "Updated taskboard\n")
        self.assertEqual(git(self.playground.project, "rev-parse", "HEAD").decode().strip(), baseline)

    def test_apply_refuses_dirty_original(self):
        self.create()
        self.accepted_task()
        (self.playground.project / "app.py").write_text("local work")
        with self.assertRaisesRegex(ValueError, "изменён"):
            self.playground.apply(1, "TASK-001")
        self.assertEqual((self.playground.project / "app.py").read_text(), "local work")

    def test_apply_allows_only_verified_tw_setup_files(self):
        self.create()
        self.accepted_task()
        from harness.tw import connect
        with contextlib.redirect_stdout(io.StringIO()):
            connect(self.playground.project)
            self.playground.apply(1, 'TASK-001')
        self.assertEqual((self.playground.project / 'README.md').read_text(), 'Updated taskboard\n')

    def test_apply_rejects_manually_changed_tw_setup(self):
        self.create()
        self.accepted_task()
        from harness.tw import connect
        with contextlib.redirect_stdout(io.StringIO()):
            connect(self.playground.project)
        (self.playground.project / 'AGENTS.md').write_text('manual change')
        with self.assertRaisesRegex(ValueError, 'изменены после init'):
            self.playground.apply(1, 'TASK-001')


if __name__ == "__main__":
    unittest.main()
