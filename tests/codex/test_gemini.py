import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.cli import main as cli_main
from harness.gemini import Gemini, extract_json_payload
from harness.runner import Codex, RateLimited, Runner, create_backend
from harness.security import sandbox_command, seatbelt_profile
from harness.state import Store, atomic_json
from harness.tw import chat_command, connect, verify_servers
from tests.codex.test_harness import response


class GeminiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / "project"
        self.root.mkdir()
        (self.root / ".harness").mkdir()
        self.config = {
            "backend": "gemini",
            "agy": "/usr/bin/agy",
            "codex": "codex",
            "sandbox": "/usr/bin/sandbox-exec",
            "check": ["python3", "-m", "unittest"],
            "timeout": 10,
            "max_attempts": 3,
            "model": "gemini-4-argon",
        }
        atomic_json(self.root / ".harness/config.json", self.config)
        self.store = Store(self.root)

    def tearDown(self):
        self.store.db.close()
        self.temporary.cleanup()

    def test_backend_selection_supports_gemini_and_preserves_codex_compatibility(self):
        self.assertIsInstance(create_backend(self.config), Gemini)
        self.assertIsInstance(create_backend({"codex": "codex"}), Codex)
        self.assertIsInstance(create_backend({"backend": "codex", "codex": "codex"}), Codex)

    def test_seatbelt_profile_enforces_readonly_and_denies_secrets(self):
        readonly = seatbelt_profile(self.root, False)
        writable = seatbelt_profile(self.root, True)
        self.assertIn("(deny default)", readonly)
        self.assertNotIn("allow file-write* (subpath", readonly)
        self.assertIn("allow file-write* (subpath", writable)
        self.assertIn("credentials", readonly)
        self.assertIn("\\.env", readonly)
        cmd = sandbox_command(self.config, self.root, False, ["python3", "-V"])
        self.assertEqual(cmd[0], "/usr/bin/sandbox-exec")
        self.assertEqual(cmd[1], "-p")
        self.assertEqual(cmd[-2:], ["python3", "-V"])

    def test_extract_json_payload_handles_direct_envelope_and_stream_lines(self):
        expected = response()
        self.assertEqual(extract_json_payload(json.dumps(expected)), expected)
        envelope = {"status": "ok", "response": expected, "usage": {"input": 10, "output": 20}}
        self.assertEqual(extract_json_payload(json.dumps(envelope)), expected)
        string_envelope = {"status": "ok", "response": json.dumps(expected)}
        self.assertEqual(extract_json_payload("log line\n" + json.dumps(string_envelope)), expected)
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

    def test_gemini_cli_call_unwraps_envelope_and_validates_schema(self):
        folder = self.store.folder(1)
        workspace = folder / "workspace"
        workspace.mkdir(parents=True)
        adapter = Gemini(self.config)
        expected = response(summary="Сводка от Gemini")

        def fake_execute(command, cwd, output, timeout, interrupted=None, input_text=None, env=None):
            Path(output).write_text(json.dumps({"status": "completed", "response": expected}))
            return 0

        with patch("harness.gemini.resolve_agy", return_value="/usr/bin/agy"), \
                patch("harness.gemini.execute", side_effect=fake_execute) as run_exec:
            result = adapter.call("plan", workspace, folder, "prompt text", lambda: False)
        self.assertEqual(result["summary"], "Сводка от Gemini")
        self.assertTrue((folder / "plan.response.json").is_file())
        called_cmd = run_exec.call_args.args[0]
        self.assertEqual(called_cmd[0], "/usr/bin/sandbox-exec")
        self.assertIn("--json-schema", called_cmd)
        self.assertIn("gemini-4-argon", called_cmd)

    def test_gemini_rate_limit_markers_raise_rate_limited(self):
        folder = self.store.folder(1)
        workspace = folder / "workspace"
        workspace.mkdir(parents=True)
        adapter = Gemini(self.config)

        def fake_execute(command, cwd, output, timeout, interrupted=None, input_text=None, env=None):
            Path(output).write_text("Error 429: RESOURCE_EXHAUSTED quota_exceeded")
            return 1

        with patch("harness.gemini.resolve_agy", return_value="/usr/bin/agy"), \
                patch("harness.gemini.execute", side_effect=fake_execute):
            with self.assertRaises(RateLimited):
                adapter.call("implement", workspace, folder, "prompt", lambda: False)

    def test_gemini_sdk_command_fallback_when_cli_absent(self):
        folder = self.store.folder(1)
        workspace = folder / "workspace"
        workspace.mkdir(parents=True)
        adapter = Gemini({**self.config, "gemini_mode": "sdk"})
        with patch("harness.gemini.sdk_available", return_value=True):
            cmd = adapter.build_command("review", workspace, folder / "review.schema.json", folder / "review.response.json")
        self.assertEqual(cmd[0], "/usr/bin/sandbox-exec")
        self.assertIn("harness.gemini", cmd)
        self.assertIn("review", cmd)

    def test_tw_chat_command_supports_gemini_backend(self):
        cmd = chat_command(self.root, headless=False, prompt="check status")
        self.assertEqual(cmd[0], "/usr/bin/agy")
        self.assertIn("--sandbox", cmd)
        self.assertIn("gemini-4-argon", cmd)
        self.assertEqual(cmd[-1], "check status")
        verify_servers(cmd)
        headless_cmd = chat_command(self.root, headless=True, prompt="headless status")
        self.assertIn("--output-format", headless_cmd)
        self.assertIn("json", headless_cmd)

    def test_tw_connect_switches_backend_on_existing_project(self):
        atomic_json(self.root / ".harness/config.json", {"codex": "codex", "check": ["python3", "-m", "unittest"], "timeout": 10, "max_attempts": 3})
        with contextlib.redirect_stdout(io.StringIO()):
            connect(self.root, backend="gemini")
        updated = json.loads((self.root / ".harness/config.json").read_text())
        self.assertEqual(updated["backend"], "gemini")
        with contextlib.redirect_stdout(io.StringIO()):
            connect(self.root, backend="codex")
        switched_back = json.loads((self.root / ".harness/config.json").read_text())
        self.assertEqual(switched_back["backend"], "codex")

