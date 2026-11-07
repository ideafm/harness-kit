import argparse
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .runner import SCHEMA, RateLimited, execute, validate_result
from .security import doctor, profile, safe_env, sandbox_command, seatbelt_profile
from .state import atomic_json


RATE_LIMIT_MARKERS = (
    "usage_limit_reached",
    "rate_limit_exceeded",
    "resource_exhausted",
    "quota_exceeded",
    "usage limit",
    "rate limit",
    "429",
)


def sdk_available():
    try:
        return importlib.util.find_spec("google.antigravity") is not None
    except ModuleNotFoundError:
        return False


def resolve_agy(config=None):
    configured = (config or {}).get("agy") or (config or {}).get("gemini") or "agy"
    if configured == "sdk":
        return None
    found = shutil.which(configured)
    if found:
        return str(Path(found).resolve())
    for candidate in (Path("/opt/homebrew/bin") / configured, Path("/usr/local/bin") / configured):
        if candidate.is_file():
            return str(candidate.resolve())
    return configured if Path(configured).is_absolute() and Path(configured).is_file() else None


def validate_workspace(workspace):
    candidate = Path(workspace)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Рабочая область Gemini должна быть существующим каталогом без ссылок")
    return candidate.resolve()


def stage_settings(workspace, writable):
    resolved = validate_workspace(workspace)
    return {
        "workspace": str(resolved),
        "sandbox": True,
        "mcpServers": {},
        "permissions": profile(resolved, writable),
        "seatbeltProfile": seatbelt_profile(resolved, writable),
    }


def run_workspace_command(workspace, writable, command, timeout=30, config=None):
    resolved = validate_workspace(workspace)
    sandbox_cfg = config if isinstance(config, dict) else {"backend": "gemini", "sandbox": "/usr/bin/sandbox-exec"}
    wrapped = sandbox_command(sandbox_cfg, resolved, writable, list(command))
    return subprocess.run(wrapped, cwd=str(resolved), env=safe_env(), capture_output=True, text=True, timeout=timeout)


def extract_json_payload(raw_text):
    text = raw_text.strip()
    if not text:
        raise ValueError("Пустой ответ Gemini")
    candidates = [text]
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            candidates.append(stripped)
    for item in candidates:
        try:
            parsed = json.loads(item)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            if set(SCHEMA["properties"]).issubset(parsed):
                return parsed
            for key in ("response", "result", "output", "content", "data"):
                nested = parsed.get(key)
                if isinstance(nested, dict) and set(SCHEMA["properties"]).issubset(nested):
                    return nested
                if isinstance(nested, str):
                    try:
                        inner = json.loads(nested)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(inner, dict) and set(SCHEMA["properties"]).issubset(inner):
                        return inner
    raise ValueError("Не удалось извлечь структурированный JSON-ответ Gemini")


class Gemini:
    def __init__(self, config):
        self.config = config

    def preflight(self):
        result = doctor({**self.config, "backend": "gemini"})
        if not resolve_agy(self.config) and not sdk_available():
            raise RuntimeError("Antigravity CLI (agy) или Python SDK (google-antigravity) не найден")
        return result

    def build_command(self, stage, workspace, schema, answer):
        if stage not in {"plan", "implement", "review"}:
            raise ValueError(f"Неизвестный этап: {stage}")
        resolved_workspace = validate_workspace(workspace)
        writable = stage == "implement"
        mode = self.config.get("gemini_mode")
        agy = None if mode == "sdk" else resolve_agy(self.config)
        if agy:
            settings = stage_settings(resolved_workspace, writable)
            command = [
                agy,
                "--sandbox",
                "--mode",
                "auto" if writable else "plan",
                "--disable-slash-commands",
                "--settings",
                json.dumps(settings, sort_keys=True),
                "--output-format",
                "json",
                "--json-schema",
                str(schema),
            ]
            if writable:
                command.append("--dangerously-skip-permissions")
            if self.config.get("model"):
                command += ["--model", self.config["model"]]
            command += ["-p", "-"]
            return command
        if not sdk_available():
            raise RuntimeError("Antigravity CLI (agy) или Python SDK (google-antigravity) не найден")
        command = [
            str(Path(sys.executable).resolve()),
            "-B",
            "-m",
            "harness.gemini",
            "--stage",
            stage,
            "--workspace",
            str(resolved_workspace),
            "--schema",
            str(schema),
            "--output",
            str(answer),
        ]
        if self.config.get("model"):
            command += ["--model", self.config["model"]]
        return command

    def call(self, stage, workspace, folder, prompt, interrupted):
        resolved_workspace = validate_workspace(workspace)
        schema = folder / f"{stage}.schema.json"
        answer = folder / f"{stage}.response.json"
        atomic_json(schema, SCHEMA)
        answer.unlink(missing_ok=True)
        command = self.build_command(stage, resolved_workspace, schema, answer)
        log = folder / f"{stage}.jsonl"
        code = execute(command, resolved_workspace, log, self.config["timeout"], interrupted, prompt, env=safe_env())
        if code:
            tail = log.read_text(errors="replace")[-12000:]
            lowered = tail.lower()
            if any(marker in lowered for marker in RATE_LIMIT_MARKERS):
                raise RateLimited(tail)
            raise RuntimeError(f"Gemini завершился с кодом {code}; лог: {log}")
        if answer.exists():
            result = json.loads(answer.read_text())
        else:
            raw = log.read_text(errors="replace")
            try:
                result = extract_json_payload(raw)
            except ValueError as error:
                raise RuntimeError(f"Gemini не сохранил структурированный ответ; лог: {log}") from error
            atomic_json(answer, result)
        validate_result(result)
        return result


async def run_sdk(stage, workspace, schema_path, output_path, model, prompt):
    resolved_workspace = validate_workspace(workspace)
    writable = stage == "implement"
    from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
    readonly_tools = None
    if not writable:
        try:
            from google.antigravity.types import BuiltinTools
            readonly_tools = BuiltinTools.read_only()
        except ImportError as error:
            raise RuntimeError("Read-only инструменты SDK недоступны; выполнение запрещено") from error
        if not readonly_tools:
            raise RuntimeError("Пустой набор read-only инструментов SDK; выполнение запрещено")
    def wrap_tool_command(argv):
        return sandbox_command({"backend": "gemini", "sandbox": "/usr/bin/sandbox-exec"}, resolved_workspace, writable, list(argv))
    cap_kwargs = {"workspace": str(resolved_workspace), "sandbox_command": wrap_tool_command}
    if not writable:
        cap_kwargs["enabled_tools"] = readonly_tools
    try:
        capabilities = CapabilitiesConfig(**cap_kwargs)
    except TypeError:
        capabilities = CapabilitiesConfig(enabled_tools=readonly_tools) if not writable else CapabilitiesConfig()
        setattr(capabilities, "workspace", str(resolved_workspace))
        setattr(capabilities, "sandbox_command", wrap_tool_command)
    kwargs = {
        "workspace": str(resolved_workspace),
        "capabilities": capabilities,
        "system_instructions": "Верни строго валидный JSON по переданной схеме без Markdown-обёрток.",
    }
    if model:
        kwargs["model"] = model
    schema_text = Path(schema_path).read_text()
    full_prompt = f"{prompt}\n\nJSON Schema:\n{schema_text}"
    previous_cwd = None
    try:
        previous_cwd = Path.cwd()
    except OSError:
        previous_cwd = None
    os.chdir(resolved_workspace)
    try:
        config = LocalAgentConfig(**kwargs)
        chunks = []
        async with Agent(config) as agent:
            response = await agent.chat(full_prompt)
            if hasattr(response, "text") and callable(response.text):
                text = await response.text()
            else:
                async for token in response:
                    chunks.append(str(token))
                text = "".join(chunks)
    finally:
        if previous_cwd is not None and previous_cwd.exists():
            os.chdir(previous_cwd)
    payload = extract_json_payload(text)
    validate_result(payload)
    atomic_json(Path(output_path), payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Antigravity SDK stage runner")
    parser.add_argument("--stage", required=True, choices=["plan", "implement", "review"])
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="")
    args = parser.parse_args(argv)
    prompt = sys.stdin.read()
    asyncio.run(run_sdk(args.stage, args.workspace, args.schema, args.output, args.model, prompt))


if __name__ == "__main__":
    main()
