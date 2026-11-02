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


def regular_files(root):
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not protected(Path(directory, d).relative_to(root).as_posix())
                   and not Path(directory, d).is_symlink()]
        for name in files:
            path = Path(directory, name)
            relative = path.relative_to(root).as_posix()
            if not protected(relative) and stat.S_ISREG(path.lstat().st_mode):
                yield relative, path


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


def sandbox_command(codex, workspace, writable, command):
    return [codex, "sandbox", *permission_args(workspace, writable), "-P", "harness",
            "-C", str(workspace), "--", *command]


def doctor(codex):
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
            env=safe_env(), capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError("Проверка sandbox не прошла:\n" + result.stdout + result.stderr)
        readonly = subprocess.run(sandbox_command(codex, workspace, False,
            [str(Path(sys.executable).resolve()), "-c", "from pathlib import Path; Path('readonly-probe').write_text('x')"]),
            env=safe_env(), capture_output=True, text=True, timeout=30)
        if readonly.returncode == 0 or (workspace / "readonly-probe").exists():
            raise RuntimeError("Проверка read-only sandbox не прошла")
        return result.stdout.strip()
