import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from .runner import SCHEMA, RateLimited, execute, validate_result
from .security import doctor, normalize_scope, path_in_scope, protected, read_regular, regular_files, safe_env, sandbox_command
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

SUPPORTED_AGY_VERSIONS = ("1.5.3",)
VERIFIED_SETTINGS_KEYS = frozenset({"permissions"})
FORBIDDEN_SETTINGS_KEYS = frozenset({
    "mcpServers",
    "workspace",
    "sandbox",
    "seatbeltProfile",
    "ignoreUserConfig",
    "mode",
    "permissionPreset",
})
REQUIRED_AGY_FLAGS = (
    "--sandbox",
    "--mode",
    "--disable-slash-commands",
    "--settings",
    "--input-format",
    "--output-format",
    "--json-schema",
)
BASE_DENY_RULES = (
    "mcp(*)",
    "mcp_*",
    "read_url(*)",
    "execute_url(*)",
    "command(*)",
    "read_file(/etc/*)",
    "write_file(/etc/*)",
    "read_file(../**)",
    "write_file(../**)",
    "read_file(.env)",
    "read_file(.env.*)",
    "read_file(*.env)",
    "read_file(*.pem)",
    "read_file(*.key)",
    "read_file(*.p12)",
    "read_file(*.pfx)",
    "read_file(credentials*)",
    "read_file(secret*)",
    "read_file(id_rsa*)",
    "read_file(id_ed25519*)",
    "read_file(id_ecdsa*)",
    "read_file(.*)",
    "write_file(.env)",
    "write_file(.env.*)",
    "write_file(*.env)",
    "write_file(*.pem)",
    "write_file(*.key)",
    "write_file(*.p12)",
    "write_file(*.pfx)",
    "write_file(credentials*)",
    "write_file(secret*)",
    "write_file(id_rsa*)",
    "write_file(id_ed25519*)",
    "write_file(id_ecdsa*)",
    "write_file(.*)",
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
    for candidate in (
        Path.home() / ".local/bin" / configured,
        Path("/opt/homebrew/bin") / configured,
        Path("/usr/local/bin") / configured,
    ):
        if candidate.is_file():
            return str(candidate.resolve())
    return configured if Path(configured).is_absolute() and Path(configured).is_file() else None


def validate_workspace(workspace):
    candidate = Path(workspace)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Рабочая область Gemini должна быть существующим каталогом без ссылок")
    return candidate.resolve()


def scan_workspace_files(resolved_workspace):
    files = []
    for root_dir, dirnames, filenames in os.walk(resolved_workspace, followlinks=False):
        current_root = Path(root_dir)
        for dirname in list(dirnames):
            entry = current_root / dirname
            if entry.is_symlink():
                raise ValueError(f"В рабочей области Gemini обнаружена символическая ссылка: {entry.relative_to(resolved_workspace)}")
        for filename in sorted(filenames):
            entry = current_root / filename
            if entry.is_symlink():
                raise ValueError(f"В рабочей области Gemini обнаружена символическая ссылка: {entry.relative_to(resolved_workspace)}")
            rel = entry.relative_to(resolved_workspace).as_posix()
            files.append(rel)
    return sorted(files)


def normalize_allowed_files(allowed_files, scope=None):
    if allowed_files is None:
        return None
    if not isinstance(allowed_files, (list, tuple, set)):
        raise ValueError("Список разрешённых файлов должен быть коллекцией строк")
    scope_dir = normalize_scope(scope)
    normalized = []
    for item in allowed_files:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Пустое имя файла в плане")
        rel = PurePosixPath(item.strip())
        rel_str = rel.as_posix()
        if rel.is_absolute() or ".." in rel.parts or "." in rel.parts or rel_str in {"", "."} or protected(rel_str):
            raise ValueError(f"Запрещённый путь в списке разрешённых файлов: {item}")
        if scope_dir and not path_in_scope(rel_str, scope_dir):
            raise ValueError(f"Файл выходит за пределы разрешённого scope ({scope_dir}): {item}")
        normalized.append(rel_str)
    return normalized


def stage_settings(workspace, writable, allowed_files=None, scope=None):
    resolved = validate_workspace(workspace)
    existing_files = scan_workspace_files(resolved)
    scope_dir = normalize_scope(scope)
    allowed_list = normalize_allowed_files(allowed_files, scope=scope_dir)
    allowed_set = set(allowed_list) if allowed_list is not None else None
    deny = list(BASE_DENY_RULES)
    for rel in existing_files:
        abs_path = str(resolved / rel)
        if protected(rel) or (scope_dir and not path_in_scope(rel, scope_dir)):
            deny.extend((
                f"read_file({rel})",
                f"read_file({abs_path})",
                f"write_file({rel})",
                f"write_file({abs_path})",
            ))
    if not writable:
        deny.append("write_file(*)")
    elif allowed_set is not None:
        if not allowed_set:
            deny.append("write_file(*)")
        else:
            for rel in existing_files:
                if rel not in allowed_set:
                    abs_path = str(resolved / rel)
                    deny.extend((f"write_file({rel})", f"write_file({abs_path})"))
    deduped = list(dict.fromkeys(deny))
    settings = {"permissions": {"deny": deduped}}
    validate_stage_settings(settings, writable)
    return settings


def validate_stage_settings(settings, writable):
    if not isinstance(settings, dict):
        raise RuntimeError("Настройки --settings для Gemini должны быть объектом JSON")
    keys = set(settings.keys())
    if not keys or not keys <= VERIFIED_SETTINGS_KEYS or (keys & FORBIDDEN_SETTINGS_KEYS):
        unknown = sorted(keys - VERIFIED_SETTINGS_KEYS)
        raise RuntimeError(f"Неподдерживаемые ключи --settings для agy: {', '.join(unknown)}")
    permissions = settings.get("permissions")
    if not isinstance(permissions, dict) or set(permissions.keys()) - {"allow", "ask", "deny"}:
        raise RuntimeError("Некорректная структура permissions в --settings для agy")
    deny = permissions.get("deny")
    if not isinstance(deny, list) or not all(isinstance(item, str) and item for item in deny):
        raise RuntimeError("Список permissions.deny должен содержать непустые строки")
    required = {"mcp(*)", "command(*)", "read_url(*)", "execute_url(*)", "read_file(.env)", "write_file(.env)"}
    if not required.issubset(deny):
        raise RuntimeError("В permissions.deny отсутствуют обязательные запреты изоляции")
    if not writable and "write_file(*)" not in deny:
        raise RuntimeError("Read-only этап Gemini требует запрета write_file(*)")


def verify_agy_contract(agy_path):
    if not agy_path or not isinstance(agy_path, str):
        raise RuntimeError("Не задан путь к исполняемому файлу agy")
    candidate = Path(agy_path)
    sha256 = None
    if candidate.is_file():
        resolved = candidate.resolve()
        sha256 = hashlib.sha256(resolved.read_bytes()).hexdigest()
    ver_proc = subprocess.run(
        [str(agy_path), "--version"],
        env=safe_env(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    ver_text = (ver_proc.stdout + "\n" + ver_proc.stderr).strip()
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", ver_text)
    version = match.group(1) if match else ""
    if ver_proc.returncode != 0 or version not in SUPPORTED_AGY_VERSIONS:
        raise RuntimeError(
            f"Неподдерживаемая версия Antigravity CLI (agy): {ver_text or 'неизвестно'}; "
            f"поддерживаются: {', '.join(SUPPORTED_AGY_VERSIONS)}"
        )
    help_proc = subprocess.run(
        [str(agy_path), "--help"],
        env=safe_env(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    help_text = help_proc.stdout + "\n" + help_proc.stderr
    if help_proc.returncode != 0 or any(flag not in help_text for flag in (*REQUIRED_AGY_FLAGS, "stream-json", "accept-edits")):
        raise RuntimeError("Контракт CLI/sandbox в установленном agy не подтверждён; выполнение запрещено")
    return {"version": version, "sha256": sha256, "path": str(candidate.resolve()) if candidate.exists() else str(agy_path)}


def run_workspace_command(workspace, writable, command, timeout=30, config=None):
    resolved = validate_workspace(workspace)
    sandbox_cfg = config if isinstance(config, dict) else {"backend": "gemini", "sandbox": "/usr/bin/sandbox-exec"}
    wrapped = sandbox_command(sandbox_cfg, resolved, writable, list(command))
    return subprocess.run(wrapped, cwd=str(resolved), env=safe_env(), capture_output=True, text=True, timeout=timeout)


def format_stream_input(prompt, stage="plan", allowed_files=None, scope=None):
    guard_lines = [
        "Системные ограничения сессии agy:",
        "- Не вызывай invoke_subagent, run_command, search_web, read_url, execute_url или MCP-инструменты.",
    ]
    if stage != "implement":
        guard_lines.append("- Это read-only этап: не вызывай write_file и edit_file.")
    elif allowed_files:
        guard_lines.append("- Изменяй только разрешённые файлы плана: " + ", ".join(allowed_files))
    if scope:
        guard_lines.append(f"- Работай строго в пределах каталога scope: {scope}")
    full_prompt = prompt.rstrip() + "\n\n" + "\n".join(guard_lines)
    return json.dumps({"event": "user", "message": {"content": full_prompt}}, ensure_ascii=False) + "\n"


def extract_json_payload(raw_text):
    text = raw_text.strip()
    if not text:
        raise ValueError("Пустой ответ Gemini")
    candidates = []
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            candidates.append(stripped)
    candidates.append(text)
    for item in candidates:
        try:
            parsed = json.loads(item)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        if set(SCHEMA["properties"]).issubset(parsed):
            return parsed
        res_obj = parsed["result"] if parsed.get("event") == "result" and isinstance(parsed.get("result"), dict) else (parsed if parsed.get("type") == "result" else None)
        if isinstance(res_obj, dict):
            if res_obj.get("status") == "ERROR":
                errors = res_obj.get("errors") or [res_obj.get("error") or res_obj.get("response") or "Ошибка выполнения Gemini"]
                err_msg = "; ".join(str(e) for e in errors if e)
                lowered = err_msg.lower()
                if any(marker in lowered for marker in RATE_LIMIT_MARKERS):
                    raise RateLimited(err_msg)
                raise RuntimeError(f"Gemini вернул ошибку: {err_msg}")
            structured = res_obj.get("structured_output")
            if isinstance(structured, dict) and set(SCHEMA["properties"]).issubset(structured):
                return structured
            resp_field = res_obj.get("response")
            if isinstance(resp_field, dict) and set(SCHEMA["properties"]).issubset(resp_field):
                return resp_field
            if isinstance(resp_field, str) and resp_field.strip():
                try:
                    inner = json.loads(resp_field)
                except json.JSONDecodeError:
                    inner = None
                if isinstance(inner, dict) and set(SCHEMA["properties"]).issubset(inner):
                    return inner
        if parsed.get("event") == "step_update" and parsed.get("tool_name") == "finish":
            params = parsed.get("parameters")
            if isinstance(params, dict) and set(SCHEMA["properties"]).issubset(params):
                return params
        if parsed.get("type") == "step_update" and isinstance(parsed.get("step"), dict):
            finish_obj = (parsed["step"].get("step") or {}).get("finish")
            if isinstance(finish_obj, dict):
                raw_out = finish_obj.get("structuredOutput")
                if isinstance(raw_out, dict) and set(SCHEMA["properties"]).issubset(raw_out):
                    return raw_out
                if isinstance(raw_out, str) and raw_out.strip():
                    try:
                        inner = json.loads(raw_out)
                    except json.JSONDecodeError:
                        inner = None
                    if isinstance(inner, dict) and set(SCHEMA["properties"]).issubset(inner):
                        return inner
        for key in ("structured_output", "response", "result", "output", "content", "data"):
            nested = parsed.get(key)
            if isinstance(nested, dict) and set(SCHEMA["properties"]).issubset(nested):
                return nested
            if isinstance(nested, str) and nested.strip():
                try:
                    inner = json.loads(nested)
                except json.JSONDecodeError:
                    continue
                if isinstance(inner, dict) and set(SCHEMA["properties"]).issubset(inner):
                    return inner
    raise ValueError("Не удалось извлечь структурированный JSON-ответ Gemini")


def workspace_snapshot_digests(workspace):
    scan_workspace_files(workspace)
    return {
        name: hashlib.sha256(read_regular(workspace, name)).hexdigest()
        for name, _ in regular_files(workspace)
    }


class Gemini:
    supports_stage_scope = True

    def __init__(self, config):
        self.config = config

    def preflight(self):
        result = doctor({**self.config, "backend": "gemini"})
        mode = self.config.get("gemini_mode")
        if mode == "sdk":
            if not sdk_available():
                raise RuntimeError("Python SDK (google-antigravity) не найден")
            return result
        agy = resolve_agy(self.config)
        if not agy:
            if sdk_available():
                return result
            raise RuntimeError("Antigravity CLI (agy) или Python SDK (google-antigravity) не найден")
        verify_agy_contract(agy)
        return result

    def build_command(self, stage, workspace, schema, answer, allowed_files=None, scope=None):
        if stage not in {"plan", "implement", "review"}:
            raise ValueError(f"Неизвестный этап: {stage}")
        resolved_workspace = validate_workspace(workspace)
        writable = stage == "implement"
        if writable and allowed_files is not None and len(allowed_files) == 0:
            raise RuntimeError("Этап implement требует непустой список разрешённых файлов плана")
        mode = self.config.get("gemini_mode")
        agy = None if mode == "sdk" else resolve_agy(self.config)
        if agy:
            settings = stage_settings(resolved_workspace, writable, allowed_files=allowed_files, scope=scope)
            command = [
                agy,
                "--sandbox",
                "--mode",
                "accept-edits",
                "--disable-slash-commands",
                "--settings",
                json.dumps(settings, sort_keys=True),
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--json-schema",
                str(schema),
            ]
            if self.config.get("model"):
                command += ["--model", self.config["model"]]
            command += ["-p", ""]
            if any(token in {"--dangerously-skip-permissions", "-c", "--continue"} for token in command):
                raise RuntimeError("Обнаружен запрещённый аргумент CLI в команде Gemini")
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

    def call(self, stage, workspace, folder, prompt, interrupted, allowed_files=None, scope=None):
        if self.config.get('attachment_images'):
            raise RuntimeError('Для задачи с изображениями выберите Codex: текущий адаптер Gemini поддерживает только текстовые вложения')
        resolved_workspace = validate_workspace(workspace)
        writable = stage == "implement"
        before_digests = None if writable else workspace_snapshot_digests(resolved_workspace)
        schema = folder / f"{stage}.schema.json"
        answer = folder / f"{stage}.response.json"
        atomic_json(schema, SCHEMA)
        answer.unlink(missing_ok=True)
        command = self.build_command(stage, resolved_workspace, schema, answer, allowed_files=allowed_files, scope=scope)
        uses_stream_json = "--input-format" in command and "stream-json" in command
        stdin_payload = (
            format_stream_input(prompt, stage=stage, allowed_files=allowed_files, scope=scope)
            if uses_stream_json
            else prompt
        )
        log = folder / f"{stage}.jsonl"
        code = execute(command, resolved_workspace, log, self.config["timeout"], interrupted, stdin_payload, env=safe_env())
        if not writable:
            after_digests = workspace_snapshot_digests(resolved_workspace)
            if after_digests != before_digests:
                raise RuntimeError(f"Рабочая область была изменена на read-only этапе {stage}")
        else:
            scan_workspace_files(resolved_workspace)
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
                lowered = raw[-12000:].lower()
                if any(marker in lowered for marker in RATE_LIMIT_MARKERS):
                    raise RateLimited(raw[-12000:]) from error
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
