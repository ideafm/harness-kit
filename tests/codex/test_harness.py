import contextlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.approval import approve, revise
from harness.decisions import decide
from harness.cli import main
from harness.runner import Interrupted, RateLimited, Runner, execute, lock
from harness.security import export_snapshot, permission_args, profile, protected, regular_files, safe_env
from harness.state import Store, atomic_json


def response(**updates):
    return dict(status="done", summary="Готово", specification="# Спецификация\nВернуть 2",
                plan="# План\nИзменить app.py", files=["app.py"], criteria=["Возвращает 2"],
                question="", verdict="none", evidence=[], risk="low", scope="small", approval_reason="Локальное обратимое изменение", **{}) | updates


class FakeCodex:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def preflight(self):
        return "safe"

    def call(self, stage, workspace, folder, prompt, interrupted):
        self.calls.append(stage)
        replies = self.results.get(stage, [])
        if replies:
            answer = replies.pop(0)
            if isinstance(answer, Exception):
                raise answer
            if callable(answer):
                return answer()
            return answer
        if stage == "implement":
            (workspace / "app.py").write_text("def value():\n    return 2\n")
        return response(verdict="pass", evidence=["app.py возвращает 2"]) if stage == "review" else response()


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "app.py").write_text("def value():\n    return 1\n")
        for name in (".env", ".config", "credentials.json", "private.key"):
            (self.root / name).write_text("harmless-test-canary")
        (self.root / "alias.py").symlink_to("app.py")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture"], check=True)
        (self.root / ".harness").mkdir()
        atomic_json(self.root / ".harness/config.json", dict(codex="codex", check=["python3", "-m", "unittest"],
                    timeout=10, max_attempts=3))
        self.store = Store(self.root)
        self.task = self.store.add("Вернуть 2")

    def tearDown(self):
        self.store.db.close()
        self.temporary.cleanup()

    def check(self, workspace, folder):
        (folder / "check.log").write_text("passed")
        return 0

    def run_task(self, backend=None, check=None):
        runner = Runner(self.store, backend=backend or FakeCodex(), check=check or self.check)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            runner.run(self.task["id"])
        return self.store.get(self.task["id"]), output.getvalue()

    def cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            main(["--project", str(self.root), *args])
        return output.getvalue()

    def test_complete_pipeline_publishes_before_execution(self):
        backend = FakeCodex()
        def implementation():
            folder = self.store.folder(1)
            self.assertTrue((folder / "specification.md").exists())
            self.assertTrue((folder / "plan.md").exists())
            self.assertTrue((folder / "summary.txt").exists())
            self.assertIn("plan_published", [e["kind"] for e in self.store.events(1)])
            (folder / "workspace/app.py").write_text("def value():\n    return 2\n")
            return response()
        backend.results = {"implement": [implementation]}
        task, output = self.run_task(backend)
        self.assertEqual(task["state"], "review")
        self.assertEqual(backend.calls, ["plan", "implement", "review"])
        self.assertIn("План готов", output)
        self.assertIn("return 1", (self.root / "app.py").read_text())
        self.assertIn("+    return 2", (self.store.folder(1) / "changes.patch").read_text())

    def require_plan(self, **assessment):
        task = self.store.get(1)
        task['data']['approval_mode'] = 'approve-plan'
        self.store.save(task, 'test_require_approval')
        backend = FakeCodex({'plan': [response(**assessment)]})
        task, output = self.run_task(backend)
        self.assertEqual(task['state'], 'awaiting_approval')
        self.assertEqual(task['stage'], 'implement')
        self.assertEqual(backend.calls, ['plan'])
        self.assertIn('требуется утверждение', output)
        return task

    def test_approved_plan_resumes_after_restart_without_replanning(self):
        task = self.require_plan()
        version = task['data']['plan_version']
        self.cli('approve-plan', '1', '--version', version, '--confirm', 'TASK-001')
        backend = FakeCodex()
        task, _ = self.run_task(backend)
        self.assertEqual(task['state'], 'review')
        self.assertEqual(backend.calls, ['implement', 'review'])
        self.assertEqual(task['data']['plan_approval']['version'], version)
        self.assertNotIn('grants', task['data'])

    def test_pending_plan_cannot_be_bypassed_with_answer_resume_or_run(self):
        self.require_plan()
        for operation in (('answer', '1', 'разрешаю'), ('resume', '1')):
            with self.assertRaises(SystemExit):
                self.cli(*operation)
            self.assertEqual(self.store.get(1)['state'], 'awaiting_approval')
        with self.assertRaises(ValueError):
            self.run_task()

    def test_stale_version_and_wrong_confirmation_do_not_approve(self):
        task = self.require_plan()
        for version, confirmation in (('old', 'TASK-001'), (task['data']['plan_version'], 'TASK-002')):
            with self.assertRaises(ValueError):
                approve(self.store, 1, version, confirmation)
            self.assertEqual(self.store.get(1)['state'], 'awaiting_approval')

    def test_document_tampering_blocks_approval(self):
        task = self.require_plan()
        (self.store.folder(1) / 'plan.md').write_text('replaced')
        with self.assertRaisesRegex(ValueError, 'Документы'):
            approve(self.store, 1, task['data']['plan_version'], 'TASK-001')

    def test_document_tampering_after_approval_blocks_implementation(self):
        task = self.require_plan()
        approve(self.store, 1, task['data']['plan_version'], 'TASK-001')
        (self.store.folder(1) / 'specification.md').write_text('changed')
        backend = FakeCodex()
        with self.assertRaisesRegex(ValueError, 'Документы'):
            self.run_task(backend)
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.store.get(1)['state'], 'blocked')

    def test_unapproved_queued_task_is_gated_again(self):
        task = self.require_plan()
        task['state'] = 'queued'
        self.store.save(task, 'test_recover')
        backend = FakeCodex()
        task, _ = self.run_task(backend)
        self.assertEqual(task['state'], 'awaiting_approval')
        self.assertEqual(backend.calls, [])

    def test_revised_plan_has_new_version_and_preserves_history(self):
        task = self.require_plan()
        original = task['data']['plan_version']
        revise(self.store, 1, 'Уточни критерии')
        task, _ = self.run_task()
        self.assertEqual(task['state'], 'awaiting_approval')
        self.assertNotEqual(task['data']['plan_version'], original)
        self.assertEqual(len(task['data']['plan_versions']), 2)
        self.assertEqual(task['data']['plan_feedback'], 'Уточни критерии')
        with self.assertRaises(ValueError):
            approve(self.store, 1, original, 'TASK-001')

    def test_risk_or_large_scope_escalates_auto_mode(self):
        for assessment in ({'risk': 'high'}, {'risk': 'unknown'}, {'scope': 'large'}, {'scope': 'unknown'},
                           {'files': ['auth/policy.py']}):
            task = self.store.add('Новая задача')
            backend = FakeCodex({'plan': [response(**assessment)]})
            with contextlib.redirect_stdout(io.StringIO()):
                Runner(self.store, backend, self.check).run(task['id'])
            result = self.store.get(task['id'])
            self.assertEqual(result['state'], 'awaiting_approval')
            self.assertEqual(backend.calls, ['plan'])

    def test_request_for_approval_is_honored_in_auto_mode(self):
        task = self.store.get(1)
        task['data']['request'] = 'Сначала согласуй план со мной'
        self.store.save(task, 'test_request')
        task, _ = self.run_task()
        self.assertEqual(task['state'], 'awaiting_approval')

    def test_stale_operator_action_cannot_win_after_another_revision(self):
        task = self.require_plan()
        original_get = self.store.get
        stale = original_get(1)
        revise(self.store, 1, 'Другая версия')
        self.run_task()
        with patch.object(self.store, 'get', return_value=stale):
            with self.assertRaises((RuntimeError, ValueError)):
                approve(self.store, 1, task['data']['plan_version'], 'TASK-001')
        self.assertEqual(self.store.get(1)['state'], 'awaiting_approval')

    def test_approval_compare_and_swap_rejects_stale_same_state(self):
        task = self.require_plan()
        current = self.store.get(1)
        self.store.save(current, 'test_concurrent_update', expected='awaiting_approval')
        with patch.object(self.store, 'get', return_value=task):
            with self.assertRaisesRegex(RuntimeError, 'другим процессом'):
                approve(self.store, 1, task['data']['plan_version'], 'TASK-001')
        self.assertEqual(self.store.get(1)['state'], 'awaiting_approval')

    def test_escalated_mode_cannot_be_lowered_by_revised_assessment(self):
        backend = FakeCodex({'plan': [response(risk='high')]})
        task, _ = self.run_task(backend)
        self.assertEqual(task['state'], 'awaiting_approval')
        revise(self.store, 1, 'Уточни риск')
        task, _ = self.run_task(FakeCodex())
        self.assertEqual(task['data']['risk'], 'low')
        self.assertEqual(task['data']['effective_approval'], 'approve-plan')
        self.assertEqual(task['state'], 'awaiting_approval')

    def test_legacy_implementation_without_new_fields_can_resume(self):
        task, _ = self.run_task(FakeCodex({'implement': [RateLimited('limit')]}))
        for key in ('approval_mode', 'effective_approval', 'plan_version', 'risk', 'scope', 'approval_reason'):
            task['data'].pop(key, None)
        task['data']['retry_at'] = 0
        self.store.save(task, 'test_legacy_record')
        backend = FakeCodex()
        task, _ = self.run_task(backend)
        self.assertEqual(task['state'], 'review')
        self.assertEqual(backend.calls, ['implement', 'review'])

    def test_user_can_return_reviewed_result_with_feedback(self):
        self.run_task()
        self.cli('request-changes', '1', 'Добавь понятное пустое состояние')
        task = self.store.get(1)
        self.assertEqual((task['state'], task['stage']), ('queued', 'implement'))
        self.assertNotIn('review_verdict', task['data'])
        self.assertIn('пустое состояние', task['data']['feedback'])
        self.assertEqual(task['data']['attempts']['implement'], 0)
        event = self.store.events(1)[-1]
        self.assertEqual(event['kind'], 'changes_requested')
        self.assertEqual(event['data']['previous_verdict'], 'pass')
        backend = FakeCodex()
        task, _ = self.run_task(backend)
        self.assertEqual(task['state'], 'review')
        self.assertEqual(backend.calls, ['implement', 'review'])

    def test_rejection_is_terminal_and_preserves_result(self):
        self.run_task()
        self.cli('reject', '1', '--reason', 'Решение больше не требуется', '--confirm', 'TASK-001')
        task = self.store.get(1)
        self.assertEqual((task['state'], task['stage']), ('rejected', 'done'))
        self.assertTrue((self.store.folder(1) / 'changes.patch').is_file())
        self.assertTrue((self.store.folder(1) / 'workspace/app.py').is_file())
        self.assertIn('rejected', self.cli('status'))
        for operation in (('resume', '1'), ('answer', '1', 'Продолжай')):
            with self.assertRaises(SystemExit):
                self.cli(*operation)
        with self.assertRaises(ValueError):
            self.run_task()

    def test_result_decisions_require_review_reason_and_exact_confirmation(self):
        with self.assertRaises(ValueError):
            decide(self.store, 1, 'request-changes', 'Исправь')
        self.run_task()
        for action, text, confirmation in (('reject', 'Причина', 'TASK-002'),
                                           ('reject', '', 'TASK-001'),
                                           ('request-changes', '   ', None)):
            with self.assertRaises(ValueError):
                decide(self.store, 1, action, text, confirmation)
        self.assertEqual(self.store.get(1)['state'], 'review')

    def test_stale_rejection_cannot_overwrite_another_operator(self):
        self.run_task()
        stale = self.store.get(1)
        decide(self.store, 1, 'request-changes', 'Исправь')
        with patch.object(self.store, 'get', return_value=stale):
            with self.assertRaises(RuntimeError):
                decide(self.store, 1, 'reject', 'Отклонить', 'TASK-001')
        self.assertEqual(self.store.get(1)['state'], 'queued')

    def test_snapshot_excludes_secrets_hidden_and_symlinks(self):
        manifest = export_snapshot(self.root, self.root / ".harness/export", "HEAD")
        self.assertEqual(set(manifest), {"app.py"})
        self.assertEqual([p.name for p in (self.root / ".harness/export").iterdir()], ["app.py"])

    def test_protected_nested_paths(self):
        for name in ("a/.env.example", "a/.git/config", "a/x.env", "a/secret.txt", "id_ed25519", "keys/x.pem"):
            self.assertTrue(protected(name), name)
        self.assertFalse(protected("src/environment.py"))

    def test_question_persists_and_answer_does_not_grant_access(self):
        backend = FakeCodex({"plan": [response(status="needs_permission", question="Нужен SSH к host для диагностики")]})
        task, _ = self.run_task(backend)
        self.assertEqual(task["state"], "waiting")
        self.assertEqual(backend.calls, ["plan"])
        self.cli("answer", "1", "Я сам выполнил диагностику, вот безопасный результат")
        task = self.store.get(1)
        self.assertEqual(task["state"], "queued")
        self.assertEqual(task["data"]["answers"][0]["kind"], "needs_permission")
        self.assertNotIn("grants", task["data"])
        task, _ = self.run_task()
        self.assertEqual(task["state"], "review")

    def test_failed_check_retries_implementation(self):
        attempts = []
        def checks(workspace, folder):
            attempts.append(1)
            (folder / "check.log").write_text("failed" if len(attempts) == 1 else "passed")
            return int(len(attempts) == 1)
        backend = FakeCodex()
        task, _ = self.run_task(backend, checks)
        self.assertEqual(task["state"], "review")
        self.assertEqual(backend.calls, ["plan", "implement", "implement", "review"])

    def test_review_failure_retries(self):
        backend = FakeCodex({"review": [response(verdict="fail", evidence=["Не хватает теста"])]})
        task, _ = self.run_task(backend)
        self.assertEqual(task["state"], "review")
        self.assertEqual(backend.calls.count("implement"), 2)

    def test_attempt_limit_blocks_loop(self):
        def failed(workspace, folder):
            (folder / "check.log").write_text("failed")
            return 1
        with self.assertRaisesRegex(RuntimeError, "Исчерпаны попытки"):
            self.run_task(check=failed)
        self.assertEqual(self.store.get(1)["state"], "blocked")

    def test_rate_limit_waits_and_recovers_same_stage(self):
        backend = FakeCodex({"implement": [RateLimited("usage limit")]})
        task, _ = self.run_task(backend)
        self.assertEqual(task["state"], "rate_limited")
        self.assertEqual(task["stage"], "implement")
        self.assertGreater(task["data"]["retry_at"], time.time())
        self.run_task(backend)
        self.assertEqual(backend.calls, ["plan", "implement"])
        task["data"]["retry_at"] = 0
        self.store.save(task, "test_due")
        task, _ = self.run_task(backend)
        self.assertEqual(task["state"], "review")
        self.assertEqual(backend.calls.count("plan"), 1)

    def test_pause_during_stage_is_not_overwritten(self):
        def pause():
            self.cli("pause", "1")
            return response()
        task, _ = self.run_task(FakeCodex({"plan": [pause]}))
        self.assertEqual(task["state"], "paused")
        self.cli("resume", "1")
        task, _ = self.run_task()
        self.assertEqual(task["state"], "review")

    def test_pause_during_checks_is_not_overwritten(self):
        def checks(workspace, folder):
            self.cli("pause", "1")
            return 0
        task, _ = self.run_task(check=checks)
        self.assertEqual(task["state"], "paused")

    def test_pause_preserves_latest_stage_and_data(self):
        newer = self.store.get(1)
        newer["state"] = "running"
        newer["stage"] = "implement"
        newer["data"]["plan"] = "latest"
        self.store.save(newer, "stage_updated")
        self.store.pause(1)
        paused = self.store.get(1)
        self.assertEqual(paused["state"], "paused")
        self.assertEqual(paused["stage"], "implement")
        self.assertEqual(paused["data"]["plan"], "latest")

    def test_living_orphan_blocks_recovery_without_killing_it(self):
        atomic_json(self.store.folder(1) / "active.json", {"pid": os.getpid()})
        backend = FakeCodex()
        with self.assertRaisesRegex(RuntimeError, "ещё существует"):
            self.run_task(backend)
        self.assertEqual(backend.calls, [])

    def test_symlink_output_is_rejected(self):
        def wrong():
            (self.store.folder(1) / "workspace/escape.py").symlink_to(self.root / "app.py")
            return response()
        with self.assertRaisesRegex(RuntimeError, "ссылка"):
            self.run_task(FakeCodex({"implement": [wrong]}))

    def test_restart_recovers_from_saved_stage(self):
        backend = FakeCodex({"implement": [Interrupted()]})
        task, _ = self.run_task(backend)
        self.assertEqual(task["state"], "paused")
        self.cli("resume", "1")
        new_store = Store(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                Runner(new_store, backend=backend, check=self.check).run(1)
            self.assertEqual(new_store.get(1)["state"], "review")
            self.assertEqual(backend.calls.count("plan"), 1)
        finally:
            new_store.db.close()

    def test_scope_change_blocks_before_check(self):
        def wrong():
            workspace = self.store.folder(1) / "workspace"
            (workspace / "other.py").write_text("oops")
            return response()
        with self.assertRaisesRegex(RuntimeError, "вне плана"):
            self.run_task(FakeCodex({"implement": [wrong]}))
        self.assertEqual(self.store.get(1)["state"], "blocked")

    def test_protected_plan_is_rejected(self):
        for name in (".env", "../outside", "/etc/passwd", ".", "src/.config"):
            with self.subTest(name=name):
                ident = self.store.add("task")["id"]
                with self.assertRaises(ValueError):
                    with contextlib.redirect_stdout(io.StringIO()):
                        Runner(self.store, FakeCodex({"plan": [response(files=[name])]}), self.check).run(ident)

    def test_accept_requires_exact_confirmation_and_unchanged_output(self):
        self.run_task()
        self.cli("accept", "1", "--confirm", "TASK-001")
        self.assertEqual(self.store.get(1)["state"], "accepted")
        self.assertIn("return 1", (self.root / "app.py").read_text())

    def test_modified_output_cannot_be_accepted(self):
        self.run_task()
        (self.store.folder(1) / "workspace/app.py").write_text("changed after review")
        with self.assertRaises(SystemExit):
            self.cli("accept", "1", "--confirm", "TASK-001")
        self.assertEqual(self.store.get(1)["state"], "review")

    def test_single_runner_lock(self):
        with lock(self.store):
            with self.assertRaisesRegex(RuntimeError, "уже работает"):
                with lock(self.store):
                    pass

    def test_preflight_failure_blocks_without_agent_call(self):
        backend = FakeCodex()
        backend.preflight = lambda: (_ for _ in ()).throw(RuntimeError("sandbox unavailable"))
        with self.assertRaisesRegex(RuntimeError, "sandbox unavailable"):
            self.run_task(backend)
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.store.get(1)["state"], "blocked")

    def test_malformed_review_is_not_success(self):
        with self.assertRaisesRegex(ValueError, "Ревьюер"):
            self.run_task(FakeCodex({"review": [response(verdict="pass", evidence=[])]}))
        self.assertEqual(self.store.get(1)["state"], "blocked")

    def test_reviewer_receives_diff_and_controller_test_evidence(self):
        def review():
            task = self.store.get(1)
            prompt = Runner(self.store, FakeCodex(), self.check).prompt(task)
            self.assertIn('controller_diff', prompt)
            self.assertIn('+    return 2', prompt)
            self.assertIn('controller_check_log', prompt)
            self.assertIn('passed', prompt)
            self.assertEqual(task['data']['check_receipt']['exit_code'], 0)
            return response(verdict='pass', evidence=['app.py + controller checks'])
        task, _ = self.run_task(FakeCodex({'review': [review]}))
        self.assertEqual(task['state'], 'review')

    def test_changes_during_readonly_review_block_acceptance(self):
        def tamper():
            (self.store.folder(1) / 'workspace/app.py').write_text('tampered after checks')
            return response(verdict='pass', evidence=['looks good'])
        with self.assertRaisesRegex(RuntimeError, 'во время ревью'):
            self.run_task(FakeCodex({'review': [tamper]}))
        self.assertEqual(self.store.get(1)['state'], 'blocked')

    def test_agent_instructions_come_from_snapshot(self):
        from harness.security import git
        (self.root / 'AGENTS.md').write_text('Committed project convention')
        git(self.root, 'add', 'AGENTS.md')
        git(self.root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture instructions')
        (self.root / 'AGENTS.md').write_text('Uncommitted convention outside snapshot')
        def plan():
            task = self.store.get(1)
            prompt = Runner(self.store, FakeCodex(), self.check).prompt(task)
            self.assertIn('Committed project convention', prompt)
            self.assertNotIn('Uncommitted convention outside snapshot', prompt)
            return response()
        task, _ = self.run_task(FakeCodex({'plan': [plan]}))
        self.assertEqual(task['state'], 'review')

    def test_secret_environment_not_inherited(self):
        with patch.dict(os.environ, {"EXAMPLE_TOKEN": "harmless", "SSH_AUTH_SOCK": "/tmp/agent"}):
            env = safe_env()
        self.assertNotIn("EXAMPLE_TOKEN", env)
        self.assertNotIn("SSH_AUTH_SOCK", env)

    def test_profiles_deny_network_hidden_paths_and_home(self):
        policy = profile(self.root, True)
        self.assertFalse(policy["network"]["enabled"])
        self.assertEqual(policy["filesystem"][":root"], "deny")
        self.assertEqual(policy["filesystem"][str(self.root.resolve())]["**/.*"], "deny")
        self.assertNotIn("--dangerously", " ".join(permission_args(self.root, True)))

    def test_symlink_scan_does_not_follow_outside(self):
        external = self.root.parent / "external.txt"
        external.write_text("harmless")
        (self.root / "escape.txt").symlink_to(external)
        names = dict(regular_files(self.root))
        self.assertNotIn("escape.txt", names)

    def test_execute_timeout_kills_process_and_clears_active_record(self):
        folder = self.store.folder(1)
        with self.assertRaises(TimeoutError):
            execute(["/bin/sleep", "20"], self.root, folder / "timeout.log", 0.1)
        self.assertFalse((folder / "active.json").exists())


if __name__ == "__main__":
    unittest.main()
