import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath


SECRET_PATTERNS = ["**/.*", "**/*.env", "**/*.env.*", "**/*.pem", "**/*.key",
                   "**/*.p12", "**/*.pfx", "**/credentials*", "**/secret*",
                   "**/id_rsa*", "**/id_ed25519*", "**/id_ecdsa*"]
BACKENDS = ("codex", "gemini")


def validate_backend(backend):
    if backend is None:
        return "codex"
    if not isinstance(backend, str) or backend not in BACKENDS:
        raise ValueError(f"Неподдерживаемый backend: {backend}")
    return backend


def normalize_scope(scope):
    if scope is None:
        return ""
    if not isinstance(scope, str):
        raise ValueError("Некорректный формат scope")
    cleaned = scope.strip().strip("/")
    if not cleaned or cleaned == ".":
        return ""
    if cleaned in {"small", "large", "unknown"}:
        return ""
    path = PurePosixPath(cleaned)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or protected(cleaned):
        raise ValueError(f"Недопустимый путь scope: {scope}")
    return str(path)


def path_in_scope(path, scope):
    normalized = normalize_scope(scope)
    if not normalized:
        return True
    candidate = str(PurePosixPath(str(path).strip("/")))
    return candidate == normalized or candidate.startswith(normalized + "/")


def protected(path):
    if any(ord(character) < 32 for character in str(path)):
        return True
    parts = PurePosixPath(str(path)).parts
    return any(p.startswith(".") or re.search(
        r"(?i)(\.env($|\.)|\.(pem|key|p12|pfx)$|^credentials|^secret|^id_(rsa|ed25519|ecdsa))", p
    ) for p in parts)


def safe_env():
    allowed = {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TERM", "SYSTEMROOT"}
    env = {k: v for k, v in os.environ.items() if k in allowed}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "OPENSSL_CONF": os.devnull})
    return env


def git(root, *args):
    return subprocess.check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args], env=safe_env())


def export_snapshot(root, destination, ref):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for entry in git(root, "ls-tree", "-rz", "--full-tree", ref).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        path = raw_path.decode("utf-8")
        if protected(path) or mode not in {"100644", "100755"} or kind != "blob":
            continue
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = git(root, "cat-file", "blob", oid)
        target.write_bytes(content)
        target.chmod(0o755 if mode == "100755" else 0o644)
        manifest[path] = {"sha256": hashlib.sha256(content).hexdigest(), "mode": mode}
    return manifest


def tree_entries(root, include_protected=False):
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    def walk(folder, parts):
        for name in sorted(os.listdir(folder)):
            relative = '/'.join((*parts, name))
            if protected(relative):
                if include_protected:
                    yield relative, None
                continue
            info = os.stat(name, dir_fd=folder, follow_symlinks=False)
            yield relative, info
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
                try:
                    yield from walk(child, (*parts, name))
                finally:
                    os.close(child)
    try:
        yield from walk(descriptor, ())
    finally:
        os.close(descriptor)


def regular_files(root):
    for name, info in tree_entries(root):
        if stat.S_ISREG(info.st_mode):
            yield name, Path(root) / name


def read_regular(root, name, with_stat=False):
    relative = Path(name)
    if relative.is_absolute() or not relative.parts or '..' in relative.parts or protected(name):
        raise ValueError('Недопустимый путь обычного файла')
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        source = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(source, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Источник не является независимым обычным файлом')
            content = handle.read()
            return (content, info) if with_stat else content
    finally:
        os.close(descriptor)


def profile(workspace, writable):
    filesystem = {":root": "deny", ":minimal": "read", ":tmpdir": "deny", ":slash_tmp": "deny"}
    filesystem[str(Path.home().resolve())] = "deny"
    filesystem[str(Path(workspace).resolve())] = {".": "write" if writable else "read"}
    filesystem[str(Path(sys.base_prefix).resolve())] = "read"
    filesystem[str(Path(sys.base_prefix))] = "read"
    filesystem[str(Path(workspace).resolve())].update({pattern: "deny" for pattern in SECRET_PATTERNS})
    return {"filesystem": filesystem, "network": {"enabled": False}}


def toml(value):
    if isinstance(value, dict):
        return "{" + ", ".join(json.dumps(k) + " = " + toml(v) for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(map(toml, value)) + "]"
    return json.dumps(value)


def permission_args(workspace, writable):
    return ["-c", "permissions.harness=" + toml(profile(workspace, writable)),
            "-c", 'default_permissions="harness"']


def seatbelt_quote_regex(pattern):
    escaped = pattern.replace('"', '\\"')
    return f'#"{escaped}"'


def seatbelt_profile(workspace, writable, extra_read=(), allow_hidden_in_workspace=False):
    resolved = str(Path(workspace).resolve())
    extra_resolved = []
    for item in extra_read:
        candidate = Path(item)
        if candidate.is_symlink():
            raise ValueError("Дополнительный путь чтения не должен быть ссылкой")
        extra_resolved.append(str(candidate.resolve()))
    ancestors = {"/", "/private", "/var", "/private/var", "/tmp", "/private/tmp"}
    for item in (workspace, *extra_read):
        for candidate in (Path(item).absolute(), Path(item).resolve()):
            current = candidate
            while str(current) != current.root:
                ancestors.add(str(current))
                current = current.parent
            ancestors.add(current.root)
    metadata_rules = " ".join(f"(literal {json.dumps(path)})" for path in sorted(ancestors))
    system_roots = {"/usr", "/bin", "/sbin", "/System", "/Library", "/Applications",
                    "/opt/homebrew", "/private/var/select", "/dev",
                    str(Path(sys.base_prefix).resolve()), str(Path(sys.base_prefix)),
                    *extra_resolved}
    read_rules = " ".join(f"(subpath {json.dumps(path)})" for path in sorted(system_roots))
    write_rule = f"(allow file-write* (subpath {json.dumps(resolved)}))\n" if writable else ""
    hidden_targets = set(system_roots) | (set() if allow_hidden_in_workspace else {resolved})
    hidden_roots = [re.escape(path) for path in sorted(hidden_targets)]
    hidden_patterns = [f"^{root}/(.*/)?\\.[^/]+(/.*)?$" for root in hidden_roots]
    hidden_rules = " ".join(f"(regex {seatbelt_quote_regex(pattern)})" for pattern in hidden_patterns)
    secret_regex = (
        "^/(.*/)?("
        "[^/]*\\.[Ee][Nn][Vv](\\.[^/]+)?|"
        "[^/]*\\.([Pp][Ee][Mm]|[Kk][Ee][Yy]|[Pp]12|[Pp][Ff][Xx])|"
        "[Cc][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll][Ss][^/]*|"
        "[Ss][Ee][Cc][Rr][Ee][Tt][^/]*|"
        "[Ii][Dd]_([Rr][Ss][Aa]|[Ee][Dd]25519|[Ee][Cc][Dd][Ss][Aa])[^/]*"
        ")(/.*)?$"
    )
    return (
        "(version 1)\n"
        "(deny default)\n"
        "(allow process* signal sysctl-read mach-lookup)\n"
        f"(allow file-read-metadata {metadata_rules})\n"
        f"(allow file-read* (literal \"/\") {read_rules} (subpath {json.dumps(resolved)}))\n"
        "(allow file-write-data (literal \"/dev/null\") (literal \"/dev/tty\"))\n"
        f"{write_rule}"
        f"(deny file-read* file-write* {hidden_rules} (regex {seatbelt_quote_regex(secret_regex)}))\n"
    )


def sandbox_driver(config_or_driver):
    if isinstance(config_or_driver, dict):
        backend = validate_backend(config_or_driver.get("backend", "codex"))
        if backend == "gemini":
            driver = config_or_driver.get("sandbox") or "/usr/bin/sandbox-exec"
            if not isinstance(driver, str) or not driver.strip():
                raise RuntimeError("Не задан драйвер sandbox для Gemini")
            return driver
        driver = config_or_driver.get("codex")
        if not isinstance(driver, str) or not driver.strip():
            raise RuntimeError("Не задан исполняемый файл Codex для sandbox")
        return driver
    if not config_or_driver or not str(config_or_driver).strip():
        raise RuntimeError("Не задан драйвер sandbox")
    return str(config_or_driver)


def sandbox_command(codex, workspace, writable, command, extra_read=(), allow_hidden_in_workspace=False):
    driver = sandbox_driver(codex)
    if Path(str(driver)).name == "sandbox-exec":
        return [
            str(driver),
            "-p",
            seatbelt_profile(workspace, writable, extra_read=extra_read, allow_hidden_in_workspace=allow_hidden_in_workspace),
            *command,
        ]
    if Path(str(driver)).name in {"gemini", "agy"}:
        raise RuntimeError("Исполняемый файл агента не является драйвером sandbox")
    return [str(driver), "sandbox", *permission_args(workspace, writable), "-P", "harness",
            "-C", str(workspace), "--", *command]


def doctor(codex="codex"):
    if sys.platform != "darwin":
        raise RuntimeError("Первая версия разрешена только на macOS; Linux требует отдельной проверки изоляции")
    with tempfile.TemporaryDirectory(prefix="harness-canary-") as temporary:
        base = Path(temporary)
        workspace = base / "workspace"
        workspace.mkdir()
        (workspace / "visible.txt").write_text("public")
        forbidden = [workspace / ".env", workspace / ".hidden", workspace / "credentials.json",
                     workspace / "private.key", base / "outside.txt"]
        nested = workspace / "nested"
        nested.mkdir()
        forbidden.append(nested / ".env.local")
        for path in forbidden:
            path.write_text("harmless-canary")
        (workspace / "alias.txt").symlink_to(base / "outside.txt")
        forbidden.append(workspace / "alias.txt")
        program = "RUNTIME = " + repr(str(Path(sys.executable).resolve())) + "\n" + """
import pathlib, socket, subprocess, sys
root = pathlib.Path(sys.argv[1])
assert (root / 'visible.txt').read_text() == 'public'
for name in sys.argv[2:]:
    try:
        pathlib.Path(name).read_bytes()
    except OSError:
        pass
    else:
        raise SystemExit('FAIL: protected canary readable: ' + name)
try:
    (root / '.new-env').write_text('probe')
except OSError:
    pass
else:
    raise SystemExit('FAIL: new hidden file writable')
child = subprocess.run([RUNTIME, '-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).read_bytes()', str(root / '.env')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
assert child.returncode != 0, 'FAIL: child can read protected canary'
try:
    socket.socket().bind(('127.0.0.1', 0))
except OSError:
    pass
else:
    raise SystemExit('FAIL: network socket permitted')
try:
    (root.parent / 'escape.txt').write_text('probe')
except OSError:
    pass
else:
    raise SystemExit('FAIL: outside write permitted')
(root / 'allowed.txt').write_text('ok')
print('sandbox canaries passed')
"""
        result = subprocess.run(sandbox_command(codex, workspace, True,
            [str(Path(sys.executable).resolve()), "-c", program, str(workspace), *map(str, forbidden)]),
            cwd=str(workspace), env=safe_env(), capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError("Проверка sandbox не прошла:\n" + result.stdout + result.stderr)
        readonly = subprocess.run(sandbox_command(codex, workspace, False,
            [str(Path(sys.executable).resolve()), "-c", "from pathlib import Path; Path('readonly-probe').write_text('x')"]),
            cwd=str(workspace), env=safe_env(), capture_output=True, text=True, timeout=30)
        if readonly.returncode == 0 or (workspace / "readonly-probe").exists():
            raise RuntimeError("Проверка read-only sandbox не прошла")
        return result.stdout.strip()
