import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import tempfile
from functools import lru_cache
import urllib.parse
import urllib.request
from pathlib import Path

from .security import profile, regular_files, read_regular, tree_entries, safe_env, toml
from .state import atomic_json


NODE = Path('/opt/homebrew/bin/node').resolve()
NPM = Path('/opt/homebrew/lib/node_modules/npm/bin/npm-cli.js')
PACKAGES = ('next', 'react', 'react-dom', 'typescript', 'tailwindcss', '@tailwindcss/postcss', 'postcss',
            'clsx', 'tailwind-merge', 'class-variance-authority', 'lucide-react', 'radix-ui', 'sonner',
            'tw-animate-css', '@types/node', '@types/react', '@types/react-dom', 'vitest',
            '@vitejs/plugin-react', '@testing-library/react', '@testing-library/jest-dom',
            '@testing-library/user-event', 'jsdom')
COMPONENTS = ('sidebar', 'table', 'badge', 'tabs', 'sheet', 'alert-dialog', 'button', 'textarea',
              'skeleton', 'scroll-area', 'separator', 'tooltip', 'input', 'use-mobile')


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def dependency_path(source, dependency):
    if dependency.startswith('/opt/homebrew/'):
        return Path(dependency).resolve()
    if dependency.startswith('@loader_path/'):
        return (source.parent / dependency.removeprefix('@loader_path/')).resolve()
    if dependency.startswith('@rpath/'):
        name = dependency.removeprefix('@rpath/')
        for parent in (source.parent, NODE.parent.parent / 'lib'):
            candidate = parent / name
            if candidate.is_file():
                return candidate.resolve()
        raise RuntimeError('Не удалось разрешить библиотеку Node: ' + dependency)
    return None


@lru_cache(maxsize=1)
def runtime_files():
    pending = [NODE, *sorted((NODE.parent.parent / 'lib').glob('*.dylib'))]
    found = set()
    while pending:
        path = pending.pop().resolve()
        if path in found:
            continue
        if not str(path).startswith('/opt/homebrew/') or not path.is_file():
            raise RuntimeError('Не удалось проверить библиотеку Node')
        found.add(path)
        text = subprocess.check_output(['/usr/bin/otool', '-L', str(path)], text=True)
        for line in text.splitlines()[1:]:
            dependency = line.strip().split(' (', 1)[0]
            resolved = dependency_path(path, dependency)
            if resolved:
                pending.append(resolved)
    return tuple(sorted(found))


@lru_cache(maxsize=1)
def runtime_aliases():
    paths = set(runtime_files()) | set((NODE.parent.parent / 'lib').glob('*.dylib'))
    for path in runtime_files():
        text = subprocess.check_output(['/usr/bin/otool', '-L', str(path)], text=True)
        for line in text.splitlines()[1:]:
            dependency = line.strip().split(' (', 1)[0]
            if dependency.startswith('/opt/homebrew/'):
                paths.add(Path(dependency))
    return tuple(sorted(paths))


def bundle_runtime(home):
    target = home / 'runtime'
    target.mkdir(exist_ok=True)
    mapping = {path: target / path.name for path in runtime_files()}
    for source, destination in mapping.items():
        shutil.copyfile(source, destination)
        destination.chmod(0o755)
    for source, destination in mapping.items():
        text = subprocess.check_output(['/usr/bin/otool', '-L', str(source)], text=True)
        changes = []
        for line in text.splitlines()[1:]:
            dependency = line.strip().split(' (', 1)[0]
            resolved = dependency_path(source, dependency)
            if resolved in mapping:
                changes += ['-change', dependency, '@loader_path/' + mapping[resolved].name]
        if changes:
            subprocess.run(['/usr/bin/install_name_tool', *changes, str(destination)], capture_output=True, check=True)
        subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(destination)], capture_output=True, check=True)
    return target / NODE.name


def tree_hash(root):
    digest = hashlib.sha256()
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        for name in sorted(files):
            path = Path(directory) / name
            relative = str(path.relative_to(root))
            digest.update(relative.encode())
            digest.update(os.readlink(path).encode() if path.is_symlink() else path.read_bytes())
    return digest.hexdigest()


def prepare(root, ident=2):
    root = Path(root).resolve()
    home = root / '.harness' / 'toolchains' / 'next-ui'
    home.mkdir(parents=True, exist_ok=True)
    receipt = home / 'toolchain.json'
    if receipt.exists():
        return prepared_toolchain(home)
    versions = {name: fetch('https://registry.npmjs.org/' + urllib.parse.quote(name, safe='') + '/latest')['version'] for name in PACKAGES}
    dependencies = home / 'dependencies'
    dependencies.mkdir(exist_ok=True)
    manifest = {'name': 'tw-web-ui', 'version': '0.1.0', 'private': True,
                'scripts': {'dev': 'next dev', 'build': 'next build --webpack', 'typecheck': 'tsc --noEmit', 'test': 'vitest run'},
                'dependencies': versions}
    atomic_json(dependencies / 'package.json', manifest)
    for name in ('npm-user-config', 'npm-global-config'):
        (home / name).write_text('')
    command = [str(NODE), str(NPM), 'install', '--ignore-scripts', '--no-audit', '--no-fund',
               '--userconfig', str(home / 'npm-user-config'), '--globalconfig', str(home / 'npm-global-config'),
               '--cache', str(home / 'npm-cache'), '--logs-dir', str(home / 'npm-logs')]
    with (home / 'install.log').open('w') as output:
        subprocess.run(command, cwd=dependencies, env={'PATH': str(NODE.parent) + ':/usr/bin:/bin', 'NEXT_TELEMETRY_DISABLED': '1'},
                       stdout=output, stderr=subprocess.STDOUT, timeout=600, check=True)
    from .state import Store
    store = Store(root)
    try:
        workspace = store.folder(ident) / 'workspace'
    finally:
        store.db.close()
    shutil.copyfile(dependencies / 'package.json', workspace / 'package.json')
    shutil.copyfile(dependencies / 'package-lock.json', workspace / 'package-lock.json')
    for name in COMPONENTS:
        component = fetch(f'https://ui.shadcn.com/r/styles/new-york-v4/{name}.json')
        for file in component['files']:
            relative = Path('hooks/use-mobile.ts') if name == 'use-mobile' else Path('components/ui') / Path(file['path']).name
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            content = file['content'].replace('@/registry/new-york-v4/ui/', '@/components/ui/').replace('@/registry/new-york-v4/hooks/', '@/hooks/').replace('from "cn"', 'from "@/lib/utils"')
            content = re.sub(r'\{/\*.*?\*/\}', '', content, flags=re.S)
            content = re.sub(r'/\*.*?\*/', '', content, flags=re.S)
            content = '\n'.join(line for line in content.splitlines() if not line.lstrip().startswith('//')) + '\n'
            target.write_text(content)
    prepared = bundle_runtime(home)
    data = {'node': str(NODE), 'node_sha256': hashlib.sha256(NODE.read_bytes()).hexdigest(),
            'prepared_node': str(prepared), 'runtime_sha256': tree_hash(prepared.parent),
            'runtime_files': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in runtime_files()},
            'dependencies': str(dependencies / 'node_modules'), 'dependencies_sha256': tree_hash(dependencies / 'node_modules'),
            'package_sha256': hashlib.sha256((workspace / 'package.json').read_bytes()).hexdigest(),
            'lock_sha256': hashlib.sha256((workspace / 'package-lock.json').read_bytes()).hexdigest(), 'versions': versions}
    atomic_json(receipt, data)
    return data


def command(config, scratch, dependencies, argv):
    from .security import sandbox_command, sandbox_driver, validate_backend
    runtime_dir = dependencies.parents[1] / 'runtime'
    if not isinstance(config, dict):
        return sandbox_command(
            config,
            scratch,
            True,
            argv,
            extra_read=(runtime_dir, dependencies),
            allow_hidden_in_workspace=True,
        )
    backend = validate_backend(config.get('backend', 'codex'))
    if backend == 'gemini':
        return sandbox_command(
            config,
            scratch,
            True,
            argv,
            extra_read=(runtime_dir, dependencies),
            allow_hidden_in_workspace=True,
        )
    driver = sandbox_driver(config)
    if Path(str(driver)).name in {'gemini', 'agy', 'sandbox-exec'}:
        raise RuntimeError('Для backend codex требуется исполняемый файл Codex')
    policy = profile(scratch, True)
    policy['filesystem'][str(scratch)] = {'.': 'write', **{pattern: 'deny' for pattern in (
        '**/.env', '**/.env.*', '**/*.env', '**/*.pem', '**/*.key', '**/credentials*', '**/id_rsa*', '**/id_ed25519*')}}
    policy['filesystem'][str(runtime_dir)] = 'read'
    policy['filesystem'][str(dependencies)] = 'read'
    return [driver, 'sandbox', '-c', 'permissions.frontend=' + toml(policy), '-P', 'frontend', '-C', str(scratch), '--', *argv]


def doctor(config, home, dependencies):
    runtime = home / 'runtime/node'
    probe = home / 'sandbox-canary'
    probe.mkdir(exist_ok=True)
    (probe / '.env').write_text('harmless-canary')
    program = '''const fs=require('fs'),net=require('net'),cp=require('child_process');
for(const file of ['.env',process.argv[1]]){let denied=false;try{fs.readFileSync(file)}catch(e){denied=true}if(!denied)throw Error('read escaped')}
let denied=false;try{fs.writeFileSync(process.argv[2]+'/tw-write-probe','x')}catch(e){denied=true}if(!denied)throw Error('dependencies writable');
const child=cp.spawnSync(process.execPath,['-e',"require('fs').readFileSync('.env')"]);if(child.status===0)throw Error('child escaped');
const server=net.createServer();server.on('error',()=>console.log('node sandbox canaries passed'));server.listen(0,'127.0.0.1',()=>{server.close();process.exit(3)});
'''
    (home / 'outside-canary').write_text('harmless-outside')
    result = subprocess.run(command(config, probe, dependencies, [str(runtime), '-e', program, str(home / 'outside-canary'), str(dependencies)]),
        cwd=probe, env={'PATH': str(runtime.parent) + ':/usr/bin:/bin', 'NEXT_TELEMETRY_DISABLED': '1', 'OPENSSL_CONF': '/dev/null'}, capture_output=True, text=True, timeout=30)
    if result.returncode or 'node sandbox canaries passed' not in result.stdout:
        raise RuntimeError('Node sandbox verification failed: ' + result.stdout[-1000:] + result.stderr[-2000:])
    return result.stdout.strip()


def source_digest(workspace):
    return hashlib.sha256(json.dumps({name: hashlib.sha256(read_regular(workspace, name)).hexdigest() for name, path in regular_files(workspace)}, sort_keys=True).encode()).hexdigest()


def prepared_toolchain(home):
    home = Path(home)
    runtime = home / 'runtime/node'
    dependencies = home / 'dependencies/node_modules'
    receipt = home / 'toolchain.json'
    paths = (home, home.parent, home.parent.parent, runtime.parent, runtime,
             dependencies.parent, dependencies, receipt)
    if any(path.is_symlink() for path in paths):
        raise RuntimeError('Prepared toolchain path replaced with symlink')
    data = json.loads(receipt.read_text())
    if Path(data['prepared_node']) != runtime or Path(data['dependencies']) != dependencies:
        raise RuntimeError('Prepared toolchain paths changed')
    if not runtime.is_file() or not dependencies.is_dir():
        raise RuntimeError('Prepared toolchain missing')
    if any(path.is_symlink() for path in runtime.parent.rglob('*')):
        raise RuntimeError('Symlink in prepared runtime')
    if tree_hash(runtime.parent) != data['runtime_sha256']:
        raise RuntimeError('Prepared Node runtime changed')
    if tree_hash(dependencies) != data['dependencies_sha256']:
        raise RuntimeError('Node dependencies changed')
    return data


def check(workspace, folder, config, interrupted=lambda: False, project_root=None):
    root = Path(project_root) if project_root is not None else folder.parents[2]
    home = root / '.harness/toolchains/next-ui'
    toolchain = prepared_toolchain(home)
    runtime = Path(toolchain['prepared_node'])
    dependencies = Path(toolchain['dependencies'])
    for name, key in (('package.json', 'package_sha256'), ('package-lock.json', 'lock_sha256')):
        if hashlib.sha256(read_regular(workspace, name)).hexdigest() != toolchain[key]:
            raise RuntimeError('Dependencies changed; a new prepared toolchain is required')
    doctor(config, home, dependencies)
    before = source_digest(workspace)
    with tempfile.TemporaryDirectory(prefix='tw-frontend-') as temporary:
        return check_snapshot(workspace, folder, config, interrupted, toolchain, runtime,
                              dependencies, before, Path(temporary).resolve())


def check_snapshot(workspace, folder, config, interrupted, toolchain, runtime, dependencies, before, scratch):
    from .runner import execute
    for name, path in regular_files(workspace):
        target = scratch / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_regular(workspace, name))
    if source_digest(scratch) != before:
        raise RuntimeError('Snapshot changed during frontend copy')
    modules = scratch / 'node_modules'
    modules.mkdir()
    for path in dependencies.iterdir():
        if not path.name.startswith('.'):
            (modules / path.name).symlink_to(path, target_is_directory=path.is_dir())
    checks = [[str(Path(sys.executable).resolve()), '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
              [str(runtime), str(dependencies / 'typescript/bin/tsc'), '--noEmit'],
              [str(runtime), str(dependencies / 'vitest/vitest.mjs'), 'run'],
              [str(runtime), str(dependencies / 'next/dist/bin/next'), 'build', '--webpack']]
    env = {'PATH': str(runtime.parent) + ':/usr/bin:/bin', 'NEXT_TELEMETRY_DISABLED': '1', 'CI': '1',
           'OPENSSL_CONF': '/dev/null',
           'TMPDIR': str(scratch / 'temp'), 'PYTHONDONTWRITEBYTECODE': '1'}
    (scratch / 'temp').mkdir()
    results = []
    with (folder / 'check.log').open('w') as log:
        for index, argv in enumerate(checks):
            log.write('RUN ' + repr(argv) + '\n')
            log.flush()
            output = scratch / f'frontend-check-{index}.log'
            code = execute(command(config, scratch, dependencies, argv), scratch, output, 600, interrupted, env=env, active_folder=folder)
            shutil.copyfile(output, folder / output.name)
            log.write(output.read_text(errors='replace'))
            log.flush()
            results.append({'command': argv, 'exit_code': code})
            if code:
                return code
    if before != source_digest(workspace) or tree_hash(dependencies) != toolchain['dependencies_sha256']:
        raise RuntimeError('Source or toolchain changed during frontend checks')
    exports = [path for path in (scratch / 'out', scratch / 'build', scratch / 'build-next') if (path / 'index.html').is_file()]
    if len(exports) != 1:
        raise RuntimeError('Expected exactly one static frontend export')
    export = exports[0]
    if export.is_symlink():
        raise RuntimeError('Symlink in frontend export')
    assets = {}
    for name, info in tree_entries(export, include_protected=True):
        if info is None or stat.S_ISLNK(info.st_mode):
            raise RuntimeError('Protected path or symlink in frontend export')
        if stat.S_ISREG(info.st_mode):
            assets[name] = hashlib.sha256(read_regular(export, name)).hexdigest()
    published = folder / f'frontend-export-{time.time_ns()}'
    published.mkdir()
    for name, digest in assets.items():
        target = published / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_regular(export, name))
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Frontend export changed during publication')
    atomic_json(folder / 'frontend-receipt.json', {'source_digest': before, 'toolchain': toolchain,
        'checks': results, 'export': str(published), 'assets': assets})
    return 0
