import hashlib
import http.client
import json
import os
import re
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .node import NODE, NPM, runtime_files, source_digest, tree_hash
from .security import read_regular, regular_files, seatbelt_profile, tree_entries
from .state import atomic_json


def manifest(root):
    package = json.loads(read_regular(root, 'package.json'))
    if not isinstance(package, dict) or not isinstance(package.get('scripts'), dict) or not isinstance(package['scripts'].get('dev'), str):
        raise ValueError('В package.json отсутствует scripts.dev')
    return package


def dependencies_digest(root):
    package = manifest(root)
    return hashlib.sha256(json.dumps({key: package.get(key) for key in
        ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies', 'overrides')}, sort_keys=True).encode()
        + read_regular(root, 'package-lock.json')).hexdigest()


def copy_tree(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for name, info in tree_entries(source):
        path = target / name
        if stat.S_ISDIR(info.st_mode):
            path.mkdir(exist_ok=True)
        elif stat.S_ISREG(info.st_mode):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(read_regular(source, name))
            path.chmod(0o755 if info.st_mode & 0o111 else 0o644)
        elif stat.S_ISLNK(info.st_mode):
            raise ValueError('Зависимость содержит ссылку вне подготовленного runtime: ' + name)


def create_bins(modules):
    for name, _ in regular_files(modules):
        if not name.endswith('/package.json'):
            continue
        package_root = (modules / name).parent
        parent = package_root.parent.parent if package_root.parent.name.startswith('@') else package_root.parent
        if parent.name != 'node_modules':
            continue
        data = json.loads(read_regular(modules, name))
        bins = data.get('bin', {})
        if isinstance(bins, str):
            bins = {data.get('name', '').split('/')[-1]: bins}
        if not isinstance(bins, dict):
            continue
        for command, relative in bins.items():
            if not re.fullmatch(r'[A-Za-z0-9_@.-]+', command) or command in {'.', '..'} or not isinstance(relative, str):
                raise ValueError('Некорректный bin зависимости')
            executable = (package_root / relative).resolve()
            if not executable.is_relative_to(package_root) or not executable.is_file():
                raise ValueError('bin зависимости выходит за пределы пакета')
            destination = parent / '.bin' / command
            destination.parent.mkdir(exist_ok=True)
            if not destination.exists():
                destination.symlink_to(os.path.relpath(executable, destination.parent))


def prepare(root):
    root = Path(root)
    home = root / '.harness/toolchains/npm-dev'
    if any(path.is_symlink() for path in (home, home.parent, home.parent.parent)):
        raise ValueError('Runtime заменён ссылкой')
    receipt = home / 'receipt.json'
    if receipt.exists():
        return prepared(root)
    identity = dependencies_digest(root)
    modules = root / 'node_modules'
    if modules.is_symlink() or not modules.is_dir():
        raise ValueError('Сначала установите зависимости проекта командой npm install, затем повторите запуск')
    home.parent.mkdir(parents=True, exist_ok=True)
    temporary = home.with_name('npm-dev-' + uuid.uuid4().hex)
    temporary.mkdir()
    try:
        (temporary / 'runtime').mkdir()
        (temporary / 'runtime/node').write_text('#!/bin/sh\nexec ' + str(NODE) + ' "$@"\n')
        (temporary / 'runtime/node').chmod(0o755)
        copy_tree(NPM.parent.parent, temporary / 'npm')
        copy_tree(modules, temporary / 'dependencies/node_modules')
        create_bins(temporary / 'dependencies/node_modules')
        if dependencies_digest(root) != identity:
            raise ValueError('Зависимости изменились во время подготовки')
        data = {'version': 1, 'dependencies_digest': identity,
                'system_runtime': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in runtime_files()},
                'hashes': {name: tree_hash(temporary / name) for name in ('runtime', 'npm', 'dependencies')}}
        atomic_json(temporary / 'receipt.json', data)
        temporary.rename(home)
        return data
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def prepared(root):
    home = Path(root) / '.harness/toolchains/npm-dev'
    if any(path.is_symlink() for path in (home, home.parent, home.parent.parent, home / 'receipt.json')):
        raise ValueError('Runtime заменён ссылкой')
    data = json.loads((home / 'receipt.json').read_text())
    if data.get('version') != 1:
        raise ValueError('Неизвестная версия npm runtime')
    for name, digest in data.get('system_runtime', {}).items():
        if not name.startswith('/opt/homebrew/') or hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError('Системная библиотека Node изменена')
    for name in ('runtime', 'npm', 'dependencies'):
        if (home / name).is_symlink() or tree_hash(home / name) != data['hashes'][name]:
            raise ValueError('Подготовленный npm runtime изменён')
    return data


def command(scratch, home, port, argv):
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        raise RuntimeError('npm dev требует проверенный macOS sandbox')
    policy = seatbelt_profile(scratch, True, extra_read=(home,), allow_hidden_in_workspace=True)
    policy += f'\n(allow network-bind (local ip "localhost:{port}"))\n'
    policy += f'(allow network-inbound (local ip "localhost:{port}"))\n'
    policy += f'(allow network-outbound (remote ip "localhost:{port}"))\n'
    return ['/usr/bin/sandbox-exec', '-p', policy, *argv]


def environment(scratch, home, port):
    return {'PATH': str(home / 'runtime') + ':' + str(scratch / 'bin') + ':/usr/bin:/bin', 'HOME': str(scratch / 'home'),
            'TMPDIR': str(scratch / 'temp'), 'PORT': str(port), 'HOST': '127.0.0.1',
            'HOSTNAME': '127.0.0.1', 'NEXT_TELEMETRY_DISABLED': '1', 'NUXT_TELEMETRY_DISABLED': '1',
            'OPENSSL_CONF': '/dev/null', 'npm_config_cache': str(scratch / 'npm-cache'),
            'npm_config_userconfig': str(scratch / 'npm-user-config'),
            'npm_config_globalconfig': str(scratch / 'npm-global-config'),
            'npm_config_ignore_scripts': 'true', 'npm_config_offline': 'true', 'npm_config_update_notifier': 'false'}


def doctor(scratch, home, port):
    (scratch / '.env').write_text('harmless-canary')
    outside = scratch.parent / ('outside-' + uuid.uuid4().hex)
    outside.write_text('harmless-canary')
    program = '''const fs=require('fs'),net=require('net'),cp=require('child_process');console.log('probe start');
for(const p of ['.env',process.argv[1]]){let denied=false;try{fs.readFileSync(p)}catch{denied=true}if(!denied)throw Error('read escaped')}
let denied=false;try{fs.writeFileSync(process.argv[2]+'/runtime/probe','x')}catch{denied=true}if(!denied)throw Error('runtime writable');
if(cp.spawnSync(process.execPath,['-e',"require('fs').readFileSync('.env')"],{timeout:2000}).status===0)throw Error('child escaped');
console.log('filesystem passed');const fail=()=>process.exit(4);const foreign=net.createConnection({host:'127.0.0.1',port:Number(process.argv[3])});
foreign.on('connect',fail);foreign.setTimeout(500,()=>{foreign.destroy();foreign.emit('error',new Error('timeout'))});foreign.once('error',()=>{const bad=net.createServer();bad.on('error',()=>{const good=net.createServer();good.on('error',fail);good.listen(Number(process.env.PORT),'127.0.0.1',()=>{console.log('dev sandbox verified');good.close()})});bad.listen(0,'0.0.0.0',fail)});
setTimeout(fail,5000).unref();'''
    try:
        with socket.socket() as denied_server:
            denied_server.bind(('127.0.0.1', 0)); denied_server.listen()
            args = [str(home / 'runtime/node'), '-e', program, str(outside), str(home), str(denied_server.getsockname()[1])]
            try:
                result = subprocess.run(command(scratch, home, port, args), cwd=scratch,
                    env=environment(scratch, home, port), capture_output=True, text=True, timeout=10)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError('Sandbox probe timeout: ' + repr(error.stdout) + repr(error.stderr)) from None
        if result.returncode or 'dev sandbox verified' not in result.stdout:
            raise RuntimeError('Изоляция npm dev не подтверждена: ' + result.stderr[-1500:])
    finally:
        outside.unlink(missing_ok=True)
        (scratch / '.env').unlink(missing_ok=True)


def capture(store, task):
    workspace = store.folder(task['id']) / 'workspace'
    folder = store.folder(task['id']) / ('npm-checked-' + uuid.uuid4().hex)
    copy_tree(workspace, folder)
    digest = source_digest(folder)
    if digest != task['data']['check_receipt']['source_digest']:
        raise ValueError('Исходники изменились после проверок')
    atomic_json(store.folder(task['id']) / 'runtime-receipt.json', {'task': task['id'],
        'adapter': 'npm-dev', 'source_digest': digest, 'source': str(folder), 'check_receipt': task['data']['check_receipt']})


class DevPreview:
    def __init__(self, root, folder, workspace, selection, stop_event):
        self.process = None
        self.temporary = None
        self.log = None
        self.port = None
        self.state = {}
        self.start(root, folder, workspace, selection, stop_event)

    def start(self, root, folder, workspace, selection, stop_event):
        prepare(root)
        home = root / '.harness/toolchains/npm-dev'
        toolchain = prepared(root)
        source = workspace
        if selection['mode'] == 'checked':
            receipt = json.loads(read_regular(folder, 'runtime-receipt.json'))
            source = Path(receipt['source'])
            if (source.parent != folder or not re.fullmatch(r'npm-checked-[a-f0-9]{32}', source.name)
                    or source.is_symlink() or receipt.get('task') != selection['task']
                    or receipt.get('adapter') != 'npm-dev' or receipt.get('check_receipt', {}).get('exit_code') != 0
                    or source_digest(source) != receipt.get('source_digest')
                    or receipt['check_receipt']['source_digest'] != receipt['source_digest']):
                raise ValueError('Проверенный npm snapshot не подтверждён')
        if dependencies_digest(source) != toolchain['dependencies_digest']:
            raise ValueError('Зависимости задачи отличаются от подготовленного runtime')
        digest = source_digest(source)
        self.temporary = tempfile.TemporaryDirectory(prefix='tw-npm-dev-')
        scratch = Path(self.temporary.name).resolve()
        try:
            copy_tree(source, scratch)
            if source_digest(scratch) != digest:
                raise ValueError('Исходники изменились при копировании')
            for name in ('home', 'temp'):
                (scratch / name).mkdir(exist_ok=True)
            for name in ('npm-user-config', 'npm-global-config'):
                (scratch / name).write_text('')
            (scratch / 'node_modules').symlink_to(home / 'dependencies/node_modules', target_is_directory=True)
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                self.port = reservation.getsockname()[1]
            binaries = scratch / 'bin'
            binaries.mkdir()
            source_bins = home / 'dependencies/node_modules/.bin'
            if source_bins.is_dir():
                for binary in source_bins.iterdir():
                    (binaries / binary.name).symlink_to(binary.resolve())
            doctor(scratch, home, self.port)
            script = manifest(source)['scripts']['dev']
            args = []
            if re.search(r'\bnext\s+dev\b', script):
                args = ['--hostname', '127.0.0.1', '--port', str(self.port)]
            elif re.search(r'\bvite\b', script):
                args = ['--host', '127.0.0.1', '--port', str(self.port), '--strictPort']
            argv = [str(home / 'runtime/node'), str(home / 'npm/bin/npm-cli.js'), 'run', 'dev', *(['--', *args] if args else [])]
            self.log = (scratch / 'dev.log').open('w+')
            self.process = subprocess.Popen(command(scratch, home, self.port, argv), cwd=scratch,
                env=environment(scratch, home, self.port), stdin=subprocess.DEVNULL,
                stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and not stop_event.is_set():
                if self.process.poll() is not None:
                    break
                connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=1)
                try:
                    connection.request('GET', '/')
                    response = connection.getresponse()
                    if 200 <= response.status < 400 and self.owns_listener():
                        self.state = {'revision': digest, 'current': True}
                        return
                except (OSError, http.client.HTTPException):
                    pass
                finally:
                    connection.close()
                time.sleep(.1)
            self.log.flush();self.log.seek(0)
            raise RuntimeError('npm run dev не подтвердил готовность: ' + self.log.read()[-1600:])
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=3)
            except ProcessLookupError:
                pass
            self.process = None
        if self.log:
            self.log.close();self.log = None
        if self.temporary:
            self.temporary.cleanup();self.temporary = None

    def owns_listener(self):
        if not self.process or self.process.poll() is not None:
            return False
        result = subprocess.run(['/usr/sbin/lsof', '-nP', '-t', '-iTCP@127.0.0.1:' + str(self.port), '-sTCP:LISTEN'], capture_output=True, text=True, timeout=3)
        pids = result.stdout.split()
        try:
            return bool(pids) and all(os.getpgid(int(pid)) == self.process.pid for pid in pids)
        except (ProcessLookupError, ValueError):
            return False

    def proxy(self, handler):
        if not self.owns_listener():
            handler.send_error(503, 'Development server stopped')
            return
        length = handler.headers.get('Content-Length', '0')
        if not length.isdigit() or int(length) > 10 * 1024 * 1024 or handler.headers.get('Transfer-Encoding'):
            handler.send_error(413)
            return
        body = handler.rfile.read(int(length))
        websocket = handler.headers.get('Upgrade', '').lower() == 'websocket'
        with socket.create_connection(('127.0.0.1', self.port), timeout=10) as upstream:
            headers = {key: value for key, value in handler.headers.items()
                       if key.lower() not in {'host', 'connection', 'x-tw-instance', 'proxy-connection'}}
            headers['Host'] = f'127.0.0.1:{self.port}'
            headers['Connection'] = 'Upgrade' if websocket else 'close'
            if 'Origin' in headers:
                headers['Origin'] = f'http://127.0.0.1:{self.port}'
            request = f'{handler.command} {handler.path} HTTP/1.1\r\n' + ''.join(f'{key}: {value}\r\n' for key, value in headers.items()) + '\r\n'
            upstream.sendall(request.encode('latin-1') + body)
            handler.close_connection = True
            if not websocket:
                while True:
                    data = upstream.recv(65536)
                    if not data:
                        break
                    handler.wfile.write(data)
                return
            handler.wfile.flush()
            sockets = [upstream, handler.connection]
            while self.process and self.process.poll() is None:
                ready, _, _ = select.select(sockets, [], [], 1)
                for incoming in ready:
                    data = incoming.recv(65536)
                    if not data:
                        return
                    (handler.connection if incoming is upstream else upstream).sendall(data)
