import asyncio
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from harness.cli import main as cli_main
from harness.gemini import (
    Gemini,
    SUPPORTED_AGY_VERSIONS,
    VERIFIED_SETTINGS_KEYS,
    extract_json_payload,
    format_stream_input,
    run_sdk,
    run_workspace_command,
    stage_settings,
    validate_stage_settings,
    verify_agy_contract,
)
from harness.node import command as node_command
from harness.quota import Guard, QuotaPause
from harness.runner import Codex, RateLimited, Runner, create_backend
from harness.security import normalize_scope, path_in_scope, sandbox_command, seatbelt_profile
from harness.service import TaskService
from harness.state import Store, atomic_json
from harness.tw import chat_command, connect, main as tw_main, verify_servers
from tests.codex.test_harness import FakeCodex, response


class GeminiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / "project"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "app.py").write_text("def value():\n    return 1\n")
        subprocess.run(["git", "-C", str(self.root), "add", "app.py"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-qm",
                "fixture",
            ],
            check=True,
        )
        (self.root / ".harness").mkdir()
        self.config = {
            "backend": "gemini",
            "agy": "/usr/bin/agy",
            "codex": "codex",
            "sandbox": "/usr/bin/sandbox-exec",
            "check": [sys.executable, "-m", "unittest"],
            "timeout": 10,
            "max_attempts": 3,
            "model": "gemini-4-argon",
        }
        atomic_json(self.root / ".harness/config.json", self.config)
        self.store = Store(self.root)

    def tearDown(self):
        self.store.db.close()
        self.temporary.cleanup()

    def test_backend_selection_defaults_to_codex_and_rejects_unknown_backend(self):
        self.assertIsInstance(create_backend(self.config), Gemini)
        self.assertIsInstance(create_backend({"codex": "codex"}), Codex)
        self.assertIsInstance(create_backend({"backend": "codex", "codex": "codex"}), Codex)
        with self.assertRaisesRegex(ValueError, "Неподдерживаемый backend"):
            create_backend({"backend": "claude", "codex": "codex"})
        with self.assertRaisesRegex(ValueError, "Неподдерживаемый backend"):
            self.store.add("Задача", backend="claude")
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                cli_main(["--project", str(self.root), "--backend=claude", "status"])
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                tw_main(["--backend=claude", "chat", "--project", str(self.root)])

    def test_init_defaults_to_codex_and_accepts_explicit_backend(self):
        fresh = Path(self.temporary.name).resolve() / "fresh-codex"
        fresh.mkdir()
        subprocess.run(["git", "init", "-q", str(fresh)], check=True)
        (fresh / "app.py").write_text("x = 1\n")
        subprocess.run(["git", "-C", str(fresh), "add", "app.py"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(fresh),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-qm",
                "init",
            ],
            check=True,
        )
        with patch("harness.cli.shutil.which", side_effect=lambda name: "/usr/bin/" + name):
            with contextlib.redirect_stdout(io.StringIO()):
                cli_main(["--project", str(fresh), "init", "--check", "python3 -m unittest"])
        cfg = json.loads((fresh / ".harness/config.json").read_text())
        self.assertEqual(cfg["backend"], "codex")

        fresh_gemini = Path(self.temporary.name).resolve() / "fresh-gemini"
        fresh_gemini.mkdir()
        subprocess.run(["git", "init", "-q", str(fresh_gemini)], check=True)
        (fresh_gemini / "app.py").write_text("x = 1\n")
        subprocess.run(["git", "-C", str(fresh_gemini), "add", "app.py"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(fresh_gemini),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-qm",
                "init",
            ],
            check=True,
        )
        with patch("harness.cli.shutil.which", side_effect=lambda name: "/usr/bin/" + name):
            with contextlib.redirect_stdout(io.StringIO()):
                cli_main(["--project", str(fresh_gemini), "--backend=gemini", "init", "--check", "python3 -m unittest"])
        cfg_gemini = json.loads((fresh_gemini / ".harness/config.json").read_text())
        self.assertEqual(cfg_gemini["backend"], "gemini")

    def test_task_backend_is_persisted_and_preserved_across_resume_and_answer(self):
        task = self.store.add("Сделать фичу", backend="gemini")
        self.assertEqual(task["data"]["backend"], "gemini")

        atomic_json(self.root / ".harness/config.json", {**self.config, "backend": "codex"})
        gemini_backend = FakeCodex(
            {
                "plan": [
                    response(status="needs_input", question="Уточнить формат?"),
                    response(),
                ]
            }
        )
        codex_backend = FakeCodex()

        def fake_check(workspace, folder):
            (folder / "check.log").write_text("passed")
            return 0

        runner = Runner(self.store, check=fake_check)
        with patch(
            "harness.runner.create_backend",
            side_effect=lambda cfg, name=None: gemini_backend if name == "gemini" else codex_backend,
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                runner.run(task["id"])
            waiting = self.store.get(task["id"])
            self.assertEqual(waiting["state"], "waiting")
            self.assertEqual(waiting["data"]["backend"], "gemini")
            self.assertEqual(gemini_backend.calls, ["plan"])
            self.assertEqual(codex_backend.calls, [])

            with contextlib.redirect_stdout(io.StringIO()):
                cli_main(["--project", str(self.root), "answer", str(task["id"]), "JSON"])
            answered = self.store.get(task["id"])
            self.assertEqual(answered["data"]["backend"], "gemini")

            self.store.pause(task["id"])
            with contextlib.redirect_stdout(io.StringIO()):
                cli_main(["--project", str(self.root), "resume", str(task["id"])])
            resumed = self.store.get(task["id"])
            self.assertEqual(resumed["data"]["backend"], "gemini")

            with contextlib.redirect_stdout(io.StringIO()):
                runner.run(task["id"])
        final = self.store.get(task["id"])
        self.assertEqual(final["state"], "review")
        self.assertEqual(final["data"]["backend"], "gemini")
        self.assertEqual(gemini_backend.calls, ["plan", "plan", "implement", "review"])
        self.assertEqual(codex_backend.calls, [])

    def test_service_rejects_unknown_backend_before_worker_start(self):
        service = TaskService(self.root)
        try:
            with self.assertRaisesRegex(ValueError, "Неподдерживаемый backend"):
                service.submit("Задача", start=False, backend="invalid")
            task = service.submit("Задача", start=False, backend="gemini")["task"]
            self.assertEqual(task["backend"], "gemini")
            raw = service.store.get(task["id"])
            raw["data"]["backend"] = "invalid"
            service.store.save(raw, "corrupt_backend")
            with patch("harness.service.subprocess.Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "Неподдерживаемый backend"):
                    service.start(task["id"])
            spawn.assert_not_called()
        finally:
            service.close()

    def test_seatbelt_profile_blocks_secrets_and_hidden_files_inside_and_outside_workspace(self):
        outside = Path(self.temporary.name).resolve() / "outside-readable"
        outside.mkdir()
        (outside / "public.txt").write_text("outside-ok")
        (outside / ".env").write_text("OUTSIDE_ENV_SECRET")
        (outside / ".env.local").write_text("OUTSIDE_ENV_LOCAL")
        (outside / "private.key").write_text("OUTSIDE_KEY")
        (outside / "credentials.json").write_text("OUTSIDE_CREDS")
        (outside / "secret_token.txt").write_text("OUTSIDE_SECRET")
        (outside / "id_rsa").write_text("OUTSIDE_SSH")
        (outside / ".hidden_file").write_text("OUTSIDE_HIDDEN")

        workspace = Path(self.temporary.name).resolve() / "ws"
        workspace.mkdir()
        (workspace / "visible.txt").write_text("ws-ok")
        (workspace / ".env").write_text("WS_ENV")
        (workspace / "service.pem").write_text("WS_PEM")
        (workspace / ".hidden").write_text("WS_HIDDEN")

        profile_text = seatbelt_profile(workspace, False, extra_read=(outside,))
        allow_pos = profile_text.index("(allow file-read*")
        deny_pos = profile_text.index("(deny file-read* file-write*")
        self.assertLess(allow_pos, deny_pos)

        probe = """
import pathlib, sys
ws = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
assert (ws / 'visible.txt').read_text() == 'ws-ok'
assert (out / 'public.txt').read_text() == 'outside-ok'
for blocked in [
    ws / '.env',
    ws / 'service.pem',
    ws / '.hidden',
    out / '.env',
    out / '.env.local',
    out / 'private.key',
    out / 'credentials.json',
    out / 'secret_token.txt',
    out / 'id_rsa',
    out / '.hidden_file',
]:
    try:
        blocked.read_bytes()
    except OSError:
        pass
    else:
        raise SystemExit('READABLE: ' + str(blocked))
print('ok')
"""
        cmd = sandbox_command(
            self.config,
            workspace,
            False,
            [str(Path(sys.executable).resolve()), "-c", probe, str(workspace), str(outside)],
            extra_read=(outside,),
        )
        result = subprocess.run(cmd, cwd=str(workspace), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_node_seatbelt_rule_order_preserves_deny_and_rejects_agent_binary_as_driver(self):
        scratch = Path(self.temporary.name).resolve() / "scratch"
        deps = Path(self.temporary.name).resolve() / "deps"
        (scratch / ".next").mkdir(parents=True)
        (deps / "node_modules").mkdir(parents=True)
        (scratch / ".next/build.json").write_text("{}")
        (deps / "node_modules/pkg.js").write_text("module.exports = 1;")
        (scratch / ".env").write_text("SCRATCH_SECRET")
        (deps / ".env").write_text("DEPS_SECRET")
        (deps / "private.key").write_text("DEPS_KEY")

        with self.assertRaisesRegex(RuntimeError, "не является драйвером sandbox"):
            node_command("/usr/bin/agy", scratch, deps, ["python3", "-V"])

        cmd = node_command(
            self.config,
            scratch,
            deps,
            [str(Path(sys.executable).resolve()), "-c", "print('ok')"],
        )
        self.assertEqual(cmd[0], "/usr/bin/sandbox-exec")
        seatbelt = cmd[2]
        self.assertLess(seatbelt.index("(allow file-read*"), seatbelt.index("(deny file-read* file-write*"))

        probe = """
import pathlib, sys
scratch = pathlib.Path(sys.argv[1])
deps = pathlib.Path(sys.argv[2])
assert (scratch / '.next/build.json').read_text() == '{}'
assert (deps / 'node_modules/pkg.js').read_text() == 'module.exports = 1;'
for secret in [scratch / '.env', deps / '.env', deps / 'private.key']:
    try:
        secret.read_bytes()
    except OSError:
        pass
    else:
        raise SystemExit('SECRET_READABLE: ' + str(secret))
print('node-sandbox-ok')
"""
        run_cmd = node_command(
            self.config,
            scratch,
            deps,
            [str(Path(sys.executable).resolve()), "-c", probe, str(scratch), str(deps)],
        )
        result = subprocess.run(run_cmd, cwd=str(scratch), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "node-sandbox-ok")

    def test_extract_json_payload_handles_direct_envelope_and_stream_lines(self):
        expected = response()
        self.assertEqual(extract_json_payload(json.dumps(expected)), expected)
        envelope = {"status": "ok", "response": expected, "usage": {"input": 10, "output": 20}}
        self.assertEqual(extract_json_payload(json.dumps(envelope)), expected)
        string_envelope = {"status": "ok", "response": json.dumps(expected)}
        self.assertEqual(extract_json_payload("log line\n" + json.dumps(string_envelope)), expected)
        stream_result = {
            "type": "result",
            "status": "DONE",
            "structured_output": expected,
            "response": json.dumps(expected),
        }
        self.assertEqual(
            extract_json_payload(
                json.dumps({"type": "system", "subtype": "init"}) + "\n" + json.dumps(stream_result)
            ),
            expected,
        )
        stream_finish = {
            "type": "step_update",
            "status": "DONE",
            "step": {"step": {"finish": {"structuredOutput": json.dumps(expected)}}},
        }
        self.assertEqual(extract_json_payload(json.dumps(stream_finish)), expected)
        stream_error = {"type": "result", "status": "ERROR", "error": "sandbox tool denied"}
        with self.assertRaisesRegex(RuntimeError, "sandbox tool denied"):
            extract_json_payload(json.dumps(stream_error))
        with self.assertRaises(ValueError):
            extract_json_payload("not json")

    def test_preflight_fails_closed_when_sandbox_or_runtime_missing(self):
        adapter = Gemini(self.config)
        with patch("harness.gemini.doctor", side_effect=RuntimeError("sandbox blocked")):
            with self.assertRaisesRegex(RuntimeError, "sandbox blocked"):
                adapter.preflight()
        with patch("harness.gemini.doctor", return_value="ok"), \
                patch("harness.gemini.resolve_agy", return_value=None), \
                patch("harness.gemini.sdk_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "не найден"):
                adapter.preflight()
        with patch("harness.gemini.doctor", return_value="ok"), \
                patch("harness.gemini.resolve_agy", return_value="/usr/bin/agy"), \
                patch("harness.gemini.verify_agy_contract", side_effect=RuntimeError("Неподдерживаемая версия agy")):
            with self.assertRaisesRegex(RuntimeError, "Неподдерживаемая версия agy"):
                adapter.preflight()

    def test_verify_agy_contract_fails_closed_on_unsupported_version_or_missing_flags(self):
        bad_ver = Mock(returncode=0, stdout="1.4.0\n", stderr="")
        with patch("harness.gemini.subprocess.run", return_value=bad_ver):
            with self.assertRaisesRegex(RuntimeError, "Неподдерживаемая версия"):
                verify_agy_contract("/usr/bin/agy")

        ok_ver = Mock(returncode=0, stdout=f"{SUPPORTED_AGY_VERSIONS[0]}\n", stderr="")
        missing_flag_help = Mock(returncode=0, stdout="--mode --settings --json-schema", stderr="")
        with patch("harness.gemini.subprocess.run", side_effect=[ok_ver, missing_flag_help]):
            with self.assertRaisesRegex(RuntimeError, "Контракт CLI/sandbox в установленном agy не подтверждён"):
                verify_agy_contract("/usr/bin/agy")

        full_help = Mock(
            returncode=0,
            stdout="--sandbox --mode --settings --disable-slash-commands --input-format --output-format --json-schema stream-json accept-edits",
            stderr="",
        )
        with patch("harness.gemini.subprocess.run", side_effect=[ok_ver, full_help]):
            self.assertEqual(verify_agy_contract("/usr/bin/agy")["version"], SUPPORTED_AGY_VERSIONS[0])

    def test_stage_settings_only_uses_verified_keys_and_enforces_write_boundaries(self):
        workspace = self.root
        ro_settings = stage_settings(workspace, writable=False)
        self.assertEqual(set(ro_settings.keys()), set(VERIFIED_SETTINGS_KEYS))
        for forbidden in ("mcpServers", "workspace", "sandbox", "seatbeltProfile", "ignoreUserConfig", "mode"):
            self.assertNotIn(forbidden, ro_settings)
        self.assertIn("write_file(*)", ro_settings["permissions"]["deny"])
        self.assertIn("mcp_*", ro_settings["permissions"]["deny"])
        validate_stage_settings(ro_settings, writable=False)

        with self.assertRaisesRegex(RuntimeError, "Неподдерживаемые ключи"):
            validate_stage_settings({"permissions": ro_settings["permissions"], "mcpServers": {}}, writable=False)

        rw_settings = stage_settings(workspace, writable=True, allowed_files=["web/src/app.tsx"], scope="web")
        self.assertEqual(set(rw_settings.keys()), set(VERIFIED_SETTINGS_KEYS))
        validate_stage_settings(rw_settings, writable=True)
        self.assertNotIn("write_file(*)", rw_settings["permissions"]["deny"])
        self.assertIn("write_file(/etc/*)", rw_settings["permissions"]["deny"])
        self.assertIn("write_file(../**)", rw_settings["permissions"]["deny"])
        self.assertIn("write_file(app.py)", rw_settings["permissions"]["deny"])

        with self.assertRaisesRegex((ValueError, RuntimeError), "выходит за пределы"):
            stage_settings(workspace, writable=True, allowed_files=["app.py"], scope="web")

    def test_gemini_cli_call_uses_verified_flags_stream_json_and_fails_on_readonly_mutation(self):
        folder = self.store.folder(1)
        workspace = folder / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "app.py").write_text("x = 1\n")
        adapter = Gemini(self.config)
        expected = response(summary="Сводка от Gemini")

        def fake_execute(command, cwd, output, timeout, interrupted=None, input_text=None, env=None):
            stream_line = json.dumps({"type": "result", "status": "DONE", "structured_output": expected})
            Path(output).write_text(stream_line + "\n")
            return 0

        with patch("harness.gemini.resolve_agy", return_value="/usr/bin/agy"), \
                patch("harness.gemini.verify_agy_contract", return_value="1.5.3"), \
                patch("harness.gemini.execute", side_effect=fake_execute) as run_exec:
            result = adapter.call("plan", workspace, folder, "prompt text", lambda: False, scope=".")
        self.assertEqual(result["summary"], "Сводка от Gemini")
        self.assertTrue((folder / "plan.response.json").is_file())
        called_cmd = run_exec.call_args.args[0]
        self.assertEqual(called_cmd[0], "/usr/bin/agy")
        self.assertIn("--sandbox", called_cmd)
        self.assertIn("--disable-slash-commands", called_cmd)
        self.assertIn("--mode", called_cmd)
        self.assertEqual(called_cmd[called_cmd.index("--mode") + 1], "accept-edits")
        self.assertEqual(called_cmd[called_cmd.index("--input-format") + 1], "stream-json")
        self.assertEqual(called_cmd[called_cmd.index("--output-format") + 1], "stream-json")
        self.assertIn("--settings", called_cmd)
        settings = json.loads(called_cmd[called_cmd.index("--settings") + 1])
        self.assertEqual(set(settings.keys()), {"permissions"})
        self.assertIn("write_file(*)", settings["permissions"]["deny"])
        self.assertIn("--json-schema", called_cmd)
        self.assertIn("gemini-4-argon", called_cmd)
        self.assertEqual(called_cmd[-2:], ["-p", ""])

        sent_stdin = run_exec.call_args.args[5]
        stdin_payload = json.loads(sent_stdin.strip())
        self.assertEqual(stdin_payload["event"], "user")
        self.assertIn("prompt text", stdin_payload["message"]["content"])

        def mutating_execute(command, cwd, output, timeout, interrupted=None, input_text=None, env=None):
            (workspace / "app.py").write_text("x = 2\n")
            Path(output).write_text(json.dumps({"type": "result", "status": "DONE", "structured_output": expected}))
            return 0

        with patch("harness.gemini.resolve_agy", return_value="/usr/bin/agy"), \
                patch("harness.gemini.verify_agy_contract", return_value="1.5.3"), \
                patch("harness.gemini.execute", side_effect=mutating_execute):
            with self.assertRaisesRegex(RuntimeError, "была изменена на read-only этапе"):
                adapter.call("plan", workspace, folder, "prompt text", lambda: False)

    def test_gemini_rate_limit_markers_raise_rate_limited(self):
        folder = self.store.folder(1)
        workspace = folder / "workspace"
        workspace.mkdir(parents=True)
        adapter = Gemini(self.config)

        def fake_execute(command, cwd, output, timeout, interrupted=None, input_text=None, env=None):
            Path(output).write_text("Error 429: RESOURCE_EXHAUSTED quota_exceeded")
            return 1

        with patch("harness.gemini.resolve_agy", return_value="/usr/bin/agy"), \
                patch("harness.gemini.verify_agy_contract", return_value="1.5.3"), \
                patch("harness.gemini.execute", side_effect=fake_execute):
            with self.assertRaises(RateLimited):
                adapter.call("implement", workspace, folder, "prompt", lambda: False, allowed_files=["app.py"])

    def test_gemini_sdk_boundary_passes_workspace_and_isolates_workspace_commands(self):
        folder = self.store.folder(1)
        workspace = folder / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "visible.txt").write_text("hello")
        (workspace / ".env").write_text("SECRET_ENV")
        schema = folder / "plan.schema.json"
        answer = folder / "plan.response.json"
        schema.write_text(json.dumps({"type": "object"}))

        adapter = Gemini({**self.config, "gemini_mode": "sdk"})
        with patch("harness.gemini.sdk_available", return_value=True):
            cmd = adapter.build_command("review", workspace, schema, answer)
        self.assertEqual(cmd[0], str(Path(sys.executable).resolve()))
        self.assertIn("harness.gemini", cmd)
        self.assertIn("review", cmd)

        ok_res = run_workspace_command(
            workspace,
            False,
            [str(Path(sys.executable).resolve()), "-c", "import pathlib; print(pathlib.Path('visible.txt').read_text())"],
        )
        self.assertEqual(ok_res.returncode, 0)
        self.assertEqual(ok_res.stdout.strip(), "hello")

        blocked_env = run_workspace_command(
            workspace,
            False,
            [str(Path(sys.executable).resolve()), "-c", "import pathlib; pathlib.Path('.env').read_bytes()"],
        )
        self.assertNotEqual(blocked_env.returncode, 0)

        blocked_write = run_workspace_command(
            workspace,
            False,
            [str(Path(sys.executable).resolve()), "-c", "import pathlib; pathlib.Path('new.txt').write_text('x')"],
        )
        self.assertNotEqual(blocked_write.returncode, 0)

        captured = {}

        class FakeBuiltinTools:
            @staticmethod
            def read_only():
                return ["read_file", "grep_search"]

        class FakeCapabilitiesConfig:
            def __init__(self, **kwargs):
                captured["capabilities"] = kwargs

        class FakeLocalAgentConfig:
            def __init__(self, **kwargs):
                captured["agent_config"] = kwargs

        class FakeResponse:
            async def text(self):
                return json.dumps(response(summary="SDK OK"))

        class FakeAgent:
            def __init__(self, config=None):
                captured["agent_init"] = config

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def chat(self, prompt):
                wrap_fn = captured["capabilities"]["sandbox_command"]
                wrapped = wrap_fn(["python3", "-V"])
                assert wrapped[0] == "/usr/bin/sandbox-exec"
                return FakeResponse()

        fake_google = types.ModuleType("google")
        fake_agy = types.ModuleType("google.antigravity")
        fake_types = types.ModuleType("google.antigravity.types")
        fake_agy.Agent = FakeAgent
        fake_agy.CapabilitiesConfig = FakeCapabilitiesConfig
        fake_agy.LocalAgentConfig = FakeLocalAgentConfig
        fake_types.BuiltinTools = FakeBuiltinTools
        fake_agy.types = fake_types
        fake_google.antigravity = fake_agy

        with patch.dict(
            sys.modules,
            {
                "google": fake_google,
                "google.antigravity": fake_agy,
                "google.antigravity.types": fake_types,
            },
        ):
            asyncio.run(run_sdk("plan", workspace, schema, answer, "gemini-4-argon", "prompt"))
        self.assertEqual(captured["agent_config"]["workspace"], str(workspace.resolve()))
        self.assertEqual(captured["capabilities"]["workspace"], str(workspace.resolve()))
        self.assertEqual(captured["capabilities"]["enabled_tools"], ["read_file", "grep_search"])
        self.assertEqual(json.loads(answer.read_text())["summary"], "SDK OK")

        class EmptyBuiltinTools:
            @staticmethod
            def read_only():
                return []

        fake_types.BuiltinTools = EmptyBuiltinTools
        with patch.dict(
            sys.modules,
            {
                "google": fake_google,
                "google.antigravity": fake_agy,
                "google.antigravity.types": fake_types,
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "read-only инструментов SDK"):
                asyncio.run(run_sdk("plan", workspace, schema, answer, "gemini-4-argon", "prompt"))

    def test_tw_chat_command_and_verify_servers_enforce_mcp_allowlist_and_readonly_sandbox_for_gemini(self):
        cmd = chat_command(self.root, headless=False, prompt="check status")
        self.assertEqual(cmd[0], "/usr/bin/agy")
        self.assertIn("--sandbox", cmd)
        self.assertIn("--disable-slash-commands", cmd)
        self.assertIn("--mode", cmd)
        self.assertEqual(cmd[cmd.index("--mode") + 1], "accept-edits")
        self.assertIn("--settings", cmd)
        settings = json.loads(cmd[cmd.index("--settings") + 1])
        self.assertEqual(set(settings.keys()), {"permissions"})
        self.assertIn("write_file(*)", settings["permissions"]["deny"])
        self.assertIn("mcp_*", settings["permissions"]["deny"])
        self.assertIn("gemini-4-argon", cmd)
        self.assertEqual(cmd[-1], "check status")

        with patch("harness.tw.verify_agy_contract", return_value="1.5.3") as check_contract:
            verify_servers(cmd)
        check_contract.assert_called_once_with("/usr/bin/agy")

        headless_cmd = chat_command(self.root, headless=True, prompt="headless status")
        self.assertIn("--output-format", headless_cmd)
        self.assertIn("stream-json", headless_cmd)
        self.assertNotIn("-c", headless_cmd)
        with patch("harness.tw.verify_agy_contract", return_value="1.5.3"):
            verify_servers(headless_cmd)

        tampered = list(headless_cmd)
        tampered_idx = tampered.index("--settings") + 1
        tampered_settings = json.loads(tampered[tampered_idx])
        tampered_settings["mcpServers"] = {"foreign": {"enabled": True}}
        tampered[tampered_idx] = json.dumps(tampered_settings)
        with patch("harness.tw.verify_agy_contract", return_value="1.5.3"):
            with self.assertRaisesRegex(RuntimeError, "Неподдерживаемые ключи"):
                verify_servers(tampered)

        no_sandbox = list(headless_cmd)
        no_sandbox.remove("--sandbox")
        with patch("harness.tw.verify_agy_contract", return_value="1.5.3"):
            with self.assertRaisesRegex(RuntimeError, "read-only режим"):
                verify_servers(no_sandbox)

        no_disable = list(headless_cmd)
        no_disable.remove("--disable-slash-commands")
        with patch("harness.tw.verify_agy_contract", return_value="1.5.3"):
            with self.assertRaisesRegex(RuntimeError, "disable-slash-commands"):
                verify_servers(no_disable)

    def test_quota_guard_checks_selected_backend_and_raises_clear_error_on_missing_config(self):
        now = time.time()
        ok_snapshot = {
            "observed_at": now,
            "windows": [{"used_percent": 50.0, "resets_at": now + 3600, "window_minutes": 300}],
            "ordinary_usage_allowed": True,
        }
        high_snapshot = {
            "observed_at": now,
            "windows": [{"used_percent": 95.0, "resets_at": now + 3600, "window_minutes": 300}],
            "ordinary_usage_allowed": True,
        }
        gemini_cfg = {**self.config, "quota_guard": True}
        guard_gemini = Guard(self.store, gemini_cfg)
        with patch("harness.quota.read", return_value=ok_snapshot) as mock_read:
            guard_gemini.check(starting=True)
        mock_read.assert_called_once_with("/usr/bin/agy", backend="gemini")

        with patch("harness.quota.read", return_value=high_snapshot):
            with self.assertRaises(QuotaPause):
                guard_gemini.check(starting=True)

        codex_cfg = {"backend": "codex", "codex": "/usr/local/bin/codex", "quota_guard": True}
        guard_codex = Guard(self.store, codex_cfg)
        with patch("harness.quota.read", return_value=ok_snapshot) as mock_codex_read:
            guard_codex.check(starting=True)
        mock_codex_read.assert_called_once_with("/usr/local/bin/codex")

        missing_agy = Guard(self.store, {"backend": "gemini", "codex": "codex", "quota_guard": True})
        with self.assertRaisesRegex(RuntimeError, "конфигурация Gemini"):
            missing_agy.check(starting=True)

        missing_codex = Guard(self.store, {"backend": "codex", "agy": "/usr/bin/agy", "quota_guard": True})
        with self.assertRaisesRegex(RuntimeError, "конфигурация Codex"):
            missing_codex.check(starting=True)

        invalid_backend = Guard(self.store, {"backend": "unknown", "codex": "codex", "quota_guard": True})
        with self.assertRaisesRegex(ValueError, "Неподдерживаемый backend"):
            invalid_backend.check(starting=True)

    def test_normalize_gemini_extracts_buckets_and_handles_timestamps(self):
        from harness.quota import normalize_gemini
        now = 1000.0
        payload = {
            "command": {
                "name": "usage",
                "data": {
                    "groups": [
                        {
                            "name": "Gemini Models",
                            "buckets": [
                                {
                                    "window": "5h",
                                    "remaining_fraction": 0.88,
                                    "reset_time": "2026-11-08T14:59:12Z",
                                },
                                {
                                    "window": "weekly",
                                    "remaining_fraction": 0.05,
                                    "reset_time": "2026-11-14T10:35:40Z",
                                },
                            ],
                        }
                    ]
                },
            }
        }
        res = normalize_gemini(payload, now)
        self.assertEqual(len(res["windows"]), 2)
        win_5h = next(w for w in res["windows"] if w["window_minutes"] == 300)
        win_w = next(w for w in res["windows"] if w["window_minutes"] == 10080)
        self.assertEqual(win_5h["used_percent"], 12.0)
        self.assertEqual(win_w["used_percent"], 95.0)

        # Naive datetime without timezone must be rejected
        naive_payload = {
            "command": {
                "name": "usage",
                "data": {
                    "groups": [
                        {
                            "name": "Gemini Models",
                            "buckets": [
                                {"window": "5h", "remaining_fraction": 0.88, "reset_time": "2026-11-08T14:59:12"},
                                {"window": "weekly", "remaining_fraction": 0.05, "reset_time": "2026-11-14T10:35:40Z"},
                            ],
                        }
                    ]
                },
            }
        }
        with self.assertRaisesRegex(ValueError, "должно содержать часовой пояс"):
            normalize_gemini(naive_payload, now)

        # Explicit offset timezone is accepted
        offset_payload = {
            "command": {
                "name": "usage",
                "data": {
                    "groups": [
                        {
                            "name": "Gemini Models",
                            "buckets": [
                                {"window": "5h", "remaining_fraction": 0.88, "reset_time": "2026-11-08T17:59:12+03:00"},
                                {"window": "weekly", "remaining_fraction": 0.05, "reset_time": "2026-11-14T10:35:40Z"},
                            ],
                        }
                    ]
                },
            }
        }
        res_offset = normalize_gemini(offset_payload, now)
        self.assertEqual(len(res_offset["windows"]), 2)

    def test_gemini_quota_ttl_120_seconds_and_isolation_from_codex(self):
        now = time.time()
        ok_gemini = {
            "observed_at": now,
            "windows": [{"used_percent": 10.0, "resets_at": now + 3600, "window_minutes": 300}],
            "ordinary_usage_allowed": True,
        }
        guard = Guard(self.store, {**self.config, "codex": "/usr/local/bin/codex", "quota_guard": True})
        with patch("harness.quota.read", return_value=ok_gemini) as mock_read:
            guard.check(starting=True, backend="gemini")
            self.assertEqual(mock_read.call_count, 1)
            guard.check(starting=False, backend="gemini")
            self.assertEqual(mock_read.call_count, 1)

        high_codex = {
            "observed_at": now,
            "windows": [{"used_percent": 96.0, "resets_at": now + 3600, "window_minutes": 300}],
            "ordinary_usage_allowed": True,
        }
        guard.snapshots["codex"] = high_codex
        guard.check(starting=False, backend="gemini")
        with self.assertRaises(QuotaPause):
            guard.check(starting=False, backend="codex")

    def test_tw_connect_and_flag_switch_backend_on_existing_project(self):
        atomic_json(
            self.root / ".harness/config.json",
            {"codex": "codex", "check": [sys.executable, "-m", "unittest"], "timeout": 10, "max_attempts": 3},
        )
        with contextlib.redirect_stdout(io.StringIO()):
            connect(self.root, backend="gemini")
        updated = json.loads((self.root / ".harness/config.json").read_text())
        self.assertEqual(updated["backend"], "gemini")

        with patch("harness.tw.register_project"), \
                patch("harness.tw.doctor"), \
                patch("harness.tw.verify_servers"), \
                patch("harness.tw.os.execvpe") as launch, \
                contextlib.redirect_stdout(io.StringIO()):
            tw_main(["--backend=codex", "--project", str(self.root)])
        switched_back = json.loads((self.root / ".harness/config.json").read_text())
        self.assertEqual(switched_back["backend"], "codex")
        launch.assert_called_once()

    def test_stage_backends_and_stage_models_route_per_stage_and_isolate_quotas(self):
        task = self.store.add(
            "Смешанный конвейер",
            backend="gemini",
            stage_backends={"plan": "gemini", "implement": "codex", "review": "gemini"},
            model="gemini-4-argon",
            stage_models={"implement": "gpt-5.4-codex"},
        )
        self.assertEqual(task["data"]["stage_backends"]["implement"], "codex")
        self.assertEqual(task["data"]["stage_models"]["implement"], "gpt-5.4-codex")

        gemini_backend = FakeCodex()
        codex_backend = FakeCodex()
        observed_models = []
        observed_quota_backends = []

        def fake_create(cfg, name=None):
            observed_models.append((name, cfg.get("model")))
            return gemini_backend if name == "gemini" else codex_backend

        def fake_check(workspace, folder):
            (folder / "check.log").write_text("passed")
            return 0

        runner = Runner(self.store, check=fake_check)
        with patch("harness.runner.create_backend", side_effect=fake_create), \
                patch.object(runner.quota, "check", side_effect=lambda starting=False, backend=None: observed_quota_backends.append((starting, backend))):
            with contextlib.redirect_stdout(io.StringIO()):
                runner.run(task["id"])
        final = self.store.get(task["id"])
        self.assertEqual(final["state"], "review")
        self.assertEqual(gemini_backend.calls, ["plan", "review"])
        self.assertEqual(codex_backend.calls, ["implement"])
        self.assertIn(("gemini", "gemini-4-argon"), observed_models)
        self.assertIn(("codex", "gpt-5.4-codex"), observed_models)
        self.assertEqual(
            [b for starting, b in observed_quota_backends if starting],
            ["gemini", "codex", "gemini", "gemini"],
        )

    def test_external_task_folders_live_outside_git_toplevel_and_preserve_legacy_folders(self):
        toplevel = self.store.git_toplevel()
        self.assertEqual(toplevel, self.root.resolve())
        external_folder = self.store.folder(1)
        self.assertFalse(external_folder.is_relative_to(toplevel))

        legacy_folder = self.root / ".harness/tasks/TASK-009"
        legacy_folder.mkdir(parents=True)
        self.assertEqual(self.store.folder(9), legacy_folder.resolve())

    def test_monorepo_scope_restricts_plan_implement_and_runs_check_in_scope_directory(self):
        (self.root / "web").mkdir()
        (self.root / "web/AGENTS.md").write_text("USE_WEB_RULES\n")
        (self.root / "web/page.js").write_text("export const v = 1;\n")
        subprocess.run(["git", "-C", str(self.root), "add", "web/AGENTS.md", "web/page.js"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-qm",
                "add web",
            ],
            check=True,
        )

        out_of_scope_task = self.store.add("Тронуть корень из web", backend="gemini", scope="web")
        bad_backend = FakeCodex({"plan": [response(files=["app.py"])]})
        runner_bad = Runner(self.store, backend=bad_backend)
        with self.assertRaisesRegex(ValueError, "вне разрешённого scope"):
            with contextlib.redirect_stdout(io.StringIO()):
                runner_bad.run(out_of_scope_task["id"])
        blocked = self.store.get(out_of_scope_task["id"])
        self.assertEqual(blocked["state"], "blocked")
        self.assertIn("вне разрешённого scope", blocked["data"]["reason"])

        in_scope_task = self.store.add("Обновить страницу web", backend="gemini", scope="web")
        check_cwds = []

        class ScopedFakeBackend(FakeCodex):
            supports_stage_scope = True

            def call(self, stage, workspace, folder, text, interrupted=None, allowed_files=None, scope=None):
                if stage == "plan":
                    assert "USE_WEB_RULES" in text
                    assert scope == "web"
                    return response(files=["web/page.js"])
                if stage == "implement":
                    assert scope == "web"
                    assert allowed_files == ["web/page.js"]
                    (workspace / "web/page.js").write_text("export const v = 2;\n")
                    return response(files=["web/page.js"])
                return response(files=["web/page.js"], verdict="pass", evidence=["web/page.js обновлён"])

        def scoped_check(check_ws, folder):
            check_cwds.append(check_ws)
            (folder / "check.log").write_text("web check ok")
            return 0

        runner_ok = Runner(self.store, backend=ScopedFakeBackend(), check=scoped_check)
        with contextlib.redirect_stdout(io.StringIO()):
            runner_ok.run(in_scope_task["id"])
        done = self.store.get(in_scope_task["id"])
        self.assertEqual(done["state"], "review")
        self.assertEqual(done["data"]["path_scope"], "web")
        expected_ws = self.store.folder(in_scope_task["id"]) / "workspace" / "web"
        self.assertEqual(check_cwds, [expected_ws])

    def test_execute_captures_sandboxed_check_output_outside_workspace(self):
        from harness.runner import execute
        folder = self.store.folder(1)
        workspace = folder / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "app.py").write_text("x = 2\n")
        cmd = sandbox_command(
            self.config,
            workspace,
            True,
            [str(Path(sys.executable).resolve()), "-B", "-c", "import app; assert app.x == 2; print('check-pipe-ok')"],
        )
        log = folder / "check.log"
        rc = execute(cmd, workspace, log, 10)
        self.assertEqual(rc, 0)
        self.assertIn("check-pipe-ok", log.read_text())


if __name__ == "__main__":
    unittest.main()
