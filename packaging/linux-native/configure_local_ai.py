"""Explicit optional local-AI setup for the tested native Linux API whitelist.

Enable is opt-in and generates protected LOCAL PLAINTEXT configuration, not an
encrypted vault. No key is accepted on argv or printed. Disable preserves the
key, model and selected profile. No package or shared API code is modified.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import socket
import stat
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

OWNER = 'DRAGONHYDRA.optional-local-ai/1'
API = 'dragonhydra-api.service'
MODEL = 'dragonhydra-local-ai.service'
DIRECTORY = Path('/etc/dragonhydra/local-ai')
KEY = DIRECTORY/'key'
ENV = DIRECTORY/'api.env'
MARKER = DIRECTORY/'ownership.json'
LOCK = DIRECTORY/'configure.lock'
UNIT = Path('/etc/systemd/system')/MODEL
DROPIN_DIRECTORY = Path('/etc/systemd/system')/(API+'.d')
DROPIN = DROPIN_DIRECTORY/'60-dragonhydra-local-ai.conf'
SERVER = Path('/opt/dragonhydra/local-ai/bin/llama-server')
PROFILE = Path('/opt/dragonhydra/local-ai/profiles/qwen3-4b-q4_k_m.json')
RUNTIME = Path('/opt/dragonhydra/local-ai')
RUNTIME_IDENTITY = RUNTIME/'BUILD-IDENTITY.json'
MANAGED = (KEY, ENV, MARKER, UNIT, DROPIN)


class ConfigurationError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None


def fail(code, message):
    raise ConfigurationError(code, message)


@dataclass(frozen=True)
class Contract:
    profile_sha256: str = '9514c3b1279821d7a9690c5a6fa7d74d401d1ade0628c515ac7c1fdc664875ff'
    server_sha256: str = '4e7bec6e2edd7c84e4fb0f8bdc3788e961b8eaad381a3fdb1f9119ecfb349281'
    runtime_identity_sha256: str = '8cbab7eda95de3fcdb6414503f4b66a0e2d1a2d3296ef11e3f97107316b386c4'
    runtime_files: int = 16
    runtime_links: int = 12
    api_version: str = '0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1'
    api_effective: str = '4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'
    known_api_pairs: tuple = (
        ('0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1', '4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'),
        ('0.4.0~alpha.1+dev20261031.r8.ac7e694e9e38-1', '1116ee30e64527c61207b6e753b71f69e37082549f76cf5e33e923d513c81158'),
    )
    minimum_available_bytes: int = 6*1024**3


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2)+'\n').encode()


def unit_argument(value):
    """systemd double-quoted argv, including literal $ and % characters."""
    return '"'+str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$')+'"'


def model_unit(model, port):
    return (f'''# {OWNER}
[Unit]
Description=Optional DRAGONHYDRA local CPU model
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=exec
DynamicUser=yes
LoadCredential=local-ai-key:{KEY}
ExecStart={SERVER} --model {unit_argument(model)} --host 127.0.0.1 --port {port} --threads 4 --threads-batch 4 --ctx-size 2048 --parallel 1 --n-gpu-layers 0 --offline --api-key-file %d/local-ai-key
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes

[Install]
WantedBy=multi-user.target
''').encode()


def api_dropin():
    return (f'# {OWNER}\n[Service]\nEnvironmentFile=-{ENV}\n').encode()


class FileStore:
    """Native POSIX file operations; tests substitute only this OS boundary."""
    def path(self, path):
        return Path(path)

    def info(self, path):
        try:
            s = self.path(path).lstat()
        except FileNotFoundError:
            return None
        return {'kind': 'link' if stat.S_ISLNK(s.st_mode) else 'file' if stat.S_ISREG(s.st_mode) else 'dir' if stat.S_ISDIR(s.st_mode) else 'other',
                'mode': stat.S_IMODE(s.st_mode), 'uid': s.st_uid, 'gid': s.st_gid}

    def safe(self, path, *, managed=False):
        path = Path(path)
        if not path.is_absolute() or '..' in path.parts or any(ord(c) < 32 or ord(c) == 127 for c in str(path)):
            fail('UNSAFE_PATH', 'Use an absolute path without traversal or control characters.')
        for part in reversed((path, *path.parents)):
            info = self.info(part)
            if info and info['kind'] == 'link':
                fail('SYMLINK_REJECTED', 'A selected or managed path contains a symbolic link.')
            if managed and info and (info['uid'] != 0 or info['gid'] != 0 or info['mode'] & 0o022):
                fail('UNSAFE_OWNERSHIP', 'Managed configuration must be root-owned and not group/world writable.')
        return path

    def private(self, path, mode=0o600, kind='file'):
        self.safe(path, managed=True)
        info = self.info(path)
        if info and (info['kind'] != kind or info['mode'] != mode or info['uid'] or info['gid']):
            fail('UNSAFE_PERMISSIONS', 'Existing private configuration has unexpected ownership, type or permissions.')
        return info

    def read(self, path):
        return self.path(path).read_bytes()

    def readlink(self, path):
        return os.readlink(self.path(path))

    def resolve(self, path):
        return self.path(path).resolve()

    def json(self, path):
        try:
            return json.loads(self.read(path))
        except (ValueError, UnicodeError):
            fail('INVALID_CONFIGURATION', 'Owned JSON configuration is invalid.')

    def sha(self, path):
        digest = hashlib.sha256()
        with self.path(path).open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                digest.update(block)
        return digest.hexdigest()

    def mkdir(self, path, mode):
        self.safe(path, managed=True)
        self.path(path).mkdir(mode=mode)

    def atomic(self, path, body, mode):
        self.safe(path, managed=True)
        fd, name = tempfile.mkstemp(prefix='.'+Path(path).name+'-', dir=self.path(Path(path).parent))
        try:
            with os.fdopen(fd, 'wb') as stream:
                os.fchmod(stream.fileno(), mode)
                os.fchown(stream.fileno(), 0, 0)
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path(path))
            directory = os.open(self.path(Path(path).parent), os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def remove(self, path):
        self.safe(path, managed=True)
        self.path(path).unlink(missing_ok=True)

    def rmdir(self, path):
        self.path(path).rmdir()

    @contextmanager
    def lock(self):
        import fcntl
        self.private(LOCK)
        fd = os.open(self.path(LOCK), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fail('CONFIGURATION_BUSY', 'Another optional AI configuration action is running.')
            yield
        finally:
            os.close(fd)


class NativeHost:
    def __init__(self, files):
        self.files = files
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def require_root(self):
        if platform.system() != 'Linux' or os.geteuid() != 0:
            fail('ROOT_REQUIRED', 'Apply optional Linux AI configuration as root.')

    def environment(self):
        release = self.files.read('/etc/os-release').decode()
        if 'ID=ubuntu\n' not in release or 'VERSION_ID="26.04"' not in release or platform.machine() != 'x86_64':
            fail('UNTESTED_PLATFORM', 'This helper is tested only on Ubuntu26.04 x86_64.')
        cpu = self.files.read('/proc/cpuinfo').decode()
        if not all(re.search(r'\b'+flag+r'\b', cpu) for flag in ('sse4_2', 'f16c', 'fma', 'bmi2', 'avx', 'avx2')):
            fail('CPU_UNSUPPORTED', 'The installed CPU runtime requires its declared AVX2/FMA feature set.')
        memory = self.files.read('/proc/meminfo').decode()
        return int(re.search(r'^MemAvailable:\s+(\d+) kB', memory, re.M).group(1))*1024

    def command(self, action, unit=None):
        argv = ['/usr/bin/systemctl', action]+([unit] if unit else [])
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            fail('SERVICE_COMMAND_TIMEOUT', 'The owned service operation '+action+' exceeded its deadline.')
        if result.returncode:
            fail('SERVICE_COMMAND_FAILED', 'The owned service operation '+action+' failed (exit'+str(result.returncode)+').')

    def state(self, unit):
        argv = ['/usr/bin/systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'UnitFileState', '-p', 'FragmentPath',
                '-p', 'ExecStart', '-p', 'MainPID', '-p', 'DynamicUser', '-p', 'DropInPaths']
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)

    def api_configuration(self, wait=False):
        deadline = time.monotonic()+(45 if wait else 5)
        while time.monotonic() < deadline:
            try:
                state = self.state(API)
                doc = self.files.json('/var/lib/dragonhydra-api/endpoint.json')
                if doc['pid'] != int(state['MainPID']) or not re.fullmatch(r'http://127\.0\.0\.1:\d{1,5}', doc['url']):
                    raise OSError()
                token = self.files.json('/var/lib/dragonhydra-api/local-session.json')['token']
                def request(route):
                    with self.opener.open(Request(doc['url']+'/dragon/api/v1'+route, headers={'Authorization': 'Bearer '+token}), timeout=3) as response:
                        return json.load(response)
                if request('/health/ready')['status'] == 'ready':
                    return request('/local-model/configuration')
            except (OSError, ValueError, KeyError):
                if not wait:
                    break
                time.sleep(.2)
        fail('API_NOT_READY', 'The owned API is not ready; optional configuration was not confirmed.')

    def available(self, port):
        try:
            with socket.socket() as listener:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(('127.0.0.1', port))
        except OSError:
            fail('PORT_BUSY', 'The selected loopback port is busy; no existing listener was stopped.')

    def model_ready(self, port, key):
        deadline = time.monotonic()+120
        while time.monotonic() < deadline:
            # Do not disclose a credential to a process which won a bind race.
            # Model loading may legitimately precede opening its listener.
            if not self.owns_model_listener(port):
                if self.state(MODEL).get('ActiveState') == 'failed':
                    break
                time.sleep(.5)
                continue
            try:
                with self.opener.open(Request('http://127.0.0.1:'+str(port)+'/health', headers={'Authorization': 'Bearer '+key}), timeout=3) as response:
                    if response.status == 200:
                        try:
                            healthy = json.loads(response.read(4096))
                        except (ValueError, UnicodeError):
                            fail('MODEL_HEALTH_INVALID', 'The optional model returned an invalid health response.')
                        if not isinstance(healthy, dict) or healthy.get('status') != 'ok':
                            fail('MODEL_HEALTH_INVALID', 'The optional model did not report its supported ready status.')
                        if not self.owns_model_listener(port):
                            fail('MODEL_LISTENER_MISMATCH', 'The health response is not bound to the owned active model process.')
                        return
            except HTTPError as error:
                code = error.code
                error.close()
                if code in (401, 403):
                    fail('MODEL_AUTH_FAILED', 'The optional model did not accept its generated credential.')
                if code != 503:
                    fail('MODEL_HEALTH_INVALID', 'The optional model health endpoint returned an unexpected HTTP status.')
            except OSError:
                pass
            if self.state(MODEL).get('ActiveState') == 'failed':
                break
            time.sleep(.5)
        fail('MODEL_NOT_READY', 'The optional model did not become ready within its startup deadline.')

    def owns_model_listener(self, port):
        state = self.state(MODEL)
        if (state.get('ActiveState') != 'active' or state.get('FragmentPath') != str(UNIT) or state.get('DynamicUser') != 'yes'
                or str(SERVER) not in state.get('ExecStart', '') or state.get('DropInPaths')):
            return False
        try:
            pid = int(state.get('MainPID', '0'))
            if pid <= 0 or Path('/proc/'+str(pid)+'/exe').resolve() != SERVER:
                return False
            inodes = set()
            for fd in Path('/proc/'+str(pid)+'/fd').iterdir():
                try:
                    target = os.readlink(fd)
                    if target.startswith('socket:['): inodes.add(target[8:-1])
                except FileNotFoundError:
                    pass
            for line in Path('/proc/'+str(pid)+'/net/tcp').read_text().splitlines()[1:]:
                fields = line.split()
                address, raw_port = fields[1].split(':')
                if fields[3] == '0A' and fields[9] in inodes and address == '0100007F' and int(raw_port, 16) == port:
                    return True
        except (OSError, ValueError, IndexError):
            pass
        return False


class Controller:
    def __init__(self, files=None, host=None, contract=None):
        self.files = files or FileStore()
        self.host = host or NativeHost(self.files)
        self.contract = contract or Contract()

    def owner(self, *, strict=False):
        f = self.files
        f.private(DIRECTORY, 0o700, 'dir')
        for path in (KEY, ENV, MARKER, LOCK):
            f.private(path)
        for path in (UNIT, DROPIN):
            f.safe(path, managed=True)
            info = f.info(path)
            if info and (info['kind'] != 'file' or info['mode'] != 0o644):
                fail('UNSAFE_PERMISSIONS', 'Owned service configuration must be a regular root0644 file.')
        if not f.info(MARKER):
            if any(f.info(p) for p in (KEY, ENV, UNIT, DROPIN)):
                fail('FOREIGN_CONFIGURATION', 'Optional AI paths exist without this helper ownership marker.')
            return None
        owner = f.json(MARKER)
        if set(owner) != {'owner', 'schema_version', 'model', 'port', 'key_sha256', 'enabled'} or owner['owner'] != OWNER or owner['schema_version'] != 1:
            fail('FOREIGN_MARKER', 'The optional AI marker is not owned by this helper.')
        self.arguments(owner['model'], owner['port'])
        if type(owner['enabled']) is not bool or not re.fullmatch('[a-f0-9]{64}', owner['key_sha256']):
            fail('INVALID_CONFIGURATION', 'Owned optional AI metadata is invalid.')
        if f.info(UNIT) and f.read(UNIT) != model_unit(owner['model'], owner['port']):
            fail('FOREIGN_UNIT', 'The optional model unit was modified outside this helper.')
        if f.info(DROPIN) and f.read(DROPIN) != api_dropin():
            fail('FOREIGN_DROPIN', 'The API optional-model drop-in was modified outside this helper.')
        if strict:
            if not f.info(KEY):
                fail('OWNED_KEY_MISSING', 'The owned model key is missing; key rotation is not implicit.')
            raw = f.read(KEY)
            if not re.fullmatch(rb'[a-f0-9]{64}\n', raw) or hashlib.sha256(raw).hexdigest() != owner['key_sha256']:
                fail('OWNED_KEY_CHANGED', 'The owned model key changed; rotation is not implemented by enable.')
            if f.info(ENV) and f.read(ENV) != self.environment(owner['port'], raw.decode().rstrip('\n')):
                fail('FOREIGN_ENVIRONMENT', 'The protected optional API environment was modified outside this helper.')
        return owner

    @staticmethod
    def arguments(model, port):
        model = Path(model)
        if not model.is_absolute() or '..' in model.parts or any(ord(c) < 32 or ord(c) == 127 for c in str(model)):
            fail('UNSAFE_MODEL_PATH', 'Choose an absolute model path without traversal or control characters.')
        if type(port) is not int or not 1 <= port <= 65535:
            fail('INVALID_PORT', 'Choose an explicit loopback port from1 to65535.')
        return model

    @staticmethod
    def environment(port, key):
        return ('DRAGONHYDRA_LOCAL_AI_URL=http://127.0.0.1:'+str(port)+'\nDRAGONHYDRA_LOCAL_AI_KEY='+key+'\n').encode()

    def api_guard(self):
        identity = self.files.json('/opt/dragonhydra/api/BUILD-IDENTITY.json')
        state = self.host.state(API)
        if ((identity['debian_version'], identity['source_content_sha256']) not in self.contract.known_api_pairs
                or state.get('FragmentPath') != '/usr/lib/systemd/system/'+API or state.get('DynamicUser') != 'yes'
                or '/opt/dragonhydra/api/bin/dragonhydra-server' not in state.get('ExecStart', '')
                or '--state /var/lib/dragonhydra-api' not in state.get('ExecStart', '')):
            fail('FOREIGN_API_UNIT', 'The installed API version/source pair does not match a tested owned component.')
        return {**state, 'api_version': identity['debian_version'], 'api_effective_sha256': identity['source_content_sha256']}

    @staticmethod
    def model_guard(state):
        if state.get('FragmentPath') and state['FragmentPath'] != str(UNIT):
            fail('FOREIGN_MODEL_UNIT', 'The model unit is not the owned configuration.')
        if state.get('DropInPaths'):
            fail('FOREIGN_MODEL_DROPIN', 'The model has additional unowned unit configuration.')
        if state.get('FragmentPath') and (state.get('DynamicUser') != 'yes' or str(SERVER) not in state.get('ExecStart', '')):
            fail('FOREIGN_MODEL_UNIT', 'The loaded model service does not match the owned private runtime.')

    def runtime_guard(self):
        f = self.files
        f.safe(RUNTIME_IDENTITY, managed=True)
        if f.sha(RUNTIME_IDENTITY) != self.contract.runtime_identity_sha256:
            fail('INSTALLED_RUNTIME_MISMATCH', 'The installed private runtime inventory identity changed.')
        identity = f.json(RUNTIME_IDENTITY)
        if (identity.get('component') != 'dragonhydra-local-ai-runtime'
                or identity.get('upstream_commit') != '2280f0fd163b03d4331d49e08460f66502e35854'
                or len(identity['runtime_files']) != self.contract.runtime_files
                or len(identity['relative_soname_links']) != self.contract.runtime_links):
            fail('INSTALLED_RUNTIME_MISMATCH', 'The private runtime closure does not match the tested inventory.')
        for entry in identity['runtime_files']:
            relative = Path(entry['path'])
            if relative.is_absolute() or '..' in relative.parts:
                fail('INSTALLED_RUNTIME_MISMATCH', 'A private runtime inventory path is unsafe.')
            path = RUNTIME/relative
            f.safe(path, managed=True)
            info = f.info(path)
            if not info or info['kind'] != 'file' or f.path(path).stat().st_size != entry['bytes'] or f.sha(path) != entry['sha256']:
                fail('INSTALLED_RUNTIME_MISMATCH', 'A private runtime companion differs from its pinned hash.')
        for entry in identity['relative_soname_links']:
            relative, target = Path(entry['path']), Path(entry['target'])
            if relative.is_absolute() or '..' in relative.parts or target.is_absolute() or '..' in target.parts:
                fail('INSTALLED_RUNTIME_MISMATCH', 'A private runtime link is unsafe.')
            path = RUNTIME/relative
            info = f.info(path)
            if (not info or info['kind'] != 'link' or info['uid'] or info['gid'] or f.readlink(path) != entry['target']
                    or not f.resolve(path).is_relative_to(RUNTIME) or f.resolve(path).relative_to(RUNTIME).as_posix() != entry['resolved_path']
                    or f.sha(f.resolve(path)) != entry['resolved_sha256'] or not entry['safe_contained_resolution']):
                fail('INSTALLED_RUNTIME_MISMATCH', 'A private runtime SONAME alias changed or escapes its prefix.')

    def preflight(self, model, port):
        model = self.arguments(model, port)
        if any(model.is_relative_to(Path(hidden)) for hidden in ('/home', '/root', '/run/user')):
            fail('MODEL_HIDDEN_BY_PROTECT_HOME', 'ProtectHome=yes hides this model location from the optional service; choose a readable external/product model path.')
        f = self.files
        f.safe(model)
        self.host.require_root()
        available = self.host.environment()
        if available < self.contract.minimum_available_bytes:
            fail('INSUFFICIENT_MEMORY', 'The selected compact profile requires at least6GiB available RAM before loading.')
        f.safe(PROFILE, managed=True)
        f.safe(SERVER, managed=True)
        if f.sha(PROFILE) != self.contract.profile_sha256 or f.sha(SERVER) != self.contract.server_sha256:
            fail('INSTALLED_PROFILE_MISMATCH', 'The installed runtime or pinned model profile does not match verified bytes.')
        self.runtime_guard()
        profile = f.json(PROFILE)
        if (profile['verified_context_tokens'] != 2048 or profile['verified_compute_threads'] != 4
                or profile['verified_parallel_slots'] != 1 or profile['verified_gpu_layers'] != 0):
            fail('PROFILE_UNSUPPORTED', 'Only the tested compact CPU profile is implemented.')
        model_info = f.info(model)
        if not model_info or model_info['kind'] != 'file' or self.files.path(model).stat().st_size != profile['bytes'] or f.sha(model) != profile['sha256']:
            fail('MODEL_HASH_MISMATCH', 'The existing GGUF must match the installed pinned model size and SHA256.')
        if not model_info['mode'] & 0o004 or any(f.info(p) and not f.info(p)['mode'] & 0o001 for p in model.parents):
            fail('MODEL_NOT_READABLE', 'The optional DynamicUser must be able to read the model; no permissions were changed.')
        owner = self.owner(strict=True)
        api_state = self.api_guard()
        model_state = self.host.state(MODEL)
        if model_state.get('FragmentPath') and (owner is None or model_state['FragmentPath'] != str(UNIT)):
            fail('FOREIGN_MODEL_UNIT', 'A model service already exists outside this helper ownership.')
        self.model_guard(model_state)
        if api_state.get('ActiveState') != 'active':
            fail('API_NOT_RUNNING', 'Start the owned server before enabling optional AI.')
        current = self.host.api_configuration()
        own_configuration = bool(owner and current.get('configured') and current.get('endpoint') == 'http://127.0.0.1:'+str(owner['port']) and current.get('credential_source') == 'environment')
        if (current.get('configured') or current.get('endpoint') or current.get('credential_source', 'none') != 'none') and not own_configuration:
            fail('FOREIGN_API_CONFIGURATION', 'Existing local AI settings are not owned by this helper.')
        same = bool(owner and owner['model'] == str(model) and owner['port'] == port)
        if owner and owner['enabled'] and not same:
            fail('DISABLE_BEFORE_CHANGE', 'Disable the owned model before selecting a different path or port.')
        already = bool(same and owner['enabled'] and f.info(UNIT) and model_state.get('ActiveState') == 'active'
                       and model_state.get('UnitFileState') == 'enabled' and f.info(DROPIN) and f.info(ENV) and own_configuration)
        if not already:
            self.host.available(port)
        return {'owner': owner, 'api_state': api_state, 'model_state': model_state, 'already_enabled': already,
                'configuration': current, 'model': str(model), 'port': port, 'available_memory_bytes': available,
                'model_sha256': profile['sha256'], 'profile': 'Qwen3-4B Q4_K_M / CPU4 / context2048 / slot1'}

    def _directory(self, path, mode, created):
        if not self.files.info(path):
            self.files.mkdir(path, mode)
            created.append(path)

    def _snapshot(self):
        return {p: (self.files.read(p), self.files.info(p)['mode']) if self.files.info(p) else None for p in MANAGED}

    def _rollback(self, before, model_state, api_active, api_touched):
        current = self.host.state(MODEL)
        self.model_guard(current)
        if current.get('FragmentPath') and current.get('ActiveState') != 'inactive':
            self.host.command('stop', MODEL)
        if current.get('UnitFileState') in ('enabled', 'enabled-runtime') and model_state.get('UnitFileState') != 'enabled':
            self.host.command('disable', MODEL)
        for path, old in before.items():
            if old is None:
                self.files.remove(path)
            else:
                self.files.atomic(path, old[0], old[1])
        self.host.command('daemon-reload')
        if model_state.get('UnitFileState') == 'enabled':
            self.host.command('enable', MODEL)
        if model_state.get('ActiveState') == 'active':
            self.host.command('start', MODEL)
        if api_active and api_touched:
            self.host.command('restart', API)
            self.host.api_configuration(wait=True)

    def _restore_or_report(self, error, before, model_state, api_active, api_touched):
        try:
            self._rollback(before, model_state, api_active, api_touched)
        except BaseException as restoration:
            primary = getattr(error, 'code', type(error).__name__)
            secondary = getattr(restoration, 'code', type(restoration).__name__)
            problem = ConfigurationError('ROLLBACK_FAILED', 'Optional AI action failed ('+primary+') and restoration failed ('+secondary+'); review the owned unit before retrying.')
            problem.details = {'primary_error': primary, 'rollback_error': secondary, 'restore_gap': True}
            raise problem from error

    def enable(self, model, port, *, preflight_only=False):
        plan = self.preflight(model, port)
        if preflight_only:
            return {'ok': True, 'action': 'preflight', **{k: plan[k] for k in ('model', 'port', 'available_memory_bytes', 'model_sha256', 'profile', 'already_enabled')},
                    'api_version': plan['api_state']['api_version'], 'api_effective_sha256': plan['api_state']['api_effective_sha256'], 'changed': False}
        f = self.files
        created = []
        api_touched = False
        failed = False
        try:
            self._directory(DIRECTORY, 0o700, created)
            with f.lock():
                # A completed concurrent action must be observed before taking
                # rollback snapshots. Never roll back a stale pre-lock view.
                plan = self.preflight(model, port)
                if plan['already_enabled']:
                    key = f.read(KEY).decode().rstrip('\n')
                    self.host.model_ready(port, key)
                    return {'ok': True, 'action': 'enable', 'changed': False, 'port': port, 'key_reused': True}
                before = self._snapshot()
                owner = plan['owner']
                key_raw = f.read(KEY) if owner else (secrets.token_hex(32)+'\n').encode()
                key = key_raw.decode().rstrip('\n')
                marker = {'owner': OWNER, 'schema_version': 1, 'model': str(model), 'port': port,
                          'key_sha256': hashlib.sha256(key_raw).hexdigest(), 'enabled': True}
                try:
                    f.atomic(KEY, key_raw, 0o600)
                    f.atomic(ENV, self.environment(port, key), 0o600)
                    f.atomic(UNIT, model_unit(model, port), 0o644)
                    self.host.command('daemon-reload')
                    self.host.command('enable', MODEL)
                    self.host.command('start', MODEL)
                    self.host.model_ready(port, key)
                    self._directory(DROPIN_DIRECTORY, 0o755, created)
                    f.atomic(DROPIN, api_dropin(), 0o644)
                    f.atomic(MARKER, canonical(marker), 0o600)
                    self.host.command('daemon-reload')
                    api_touched = True
                    self.host.command('restart', API)
                    configured = self.host.api_configuration(wait=True)
                    if not configured.get('configured') or configured.get('endpoint') != 'http://127.0.0.1:'+str(port) or configured.get('credential_source') != 'environment':
                        fail('API_CONFIGURATION_FAILED', 'The owned API did not load the optional protected environment.')
                except BaseException as error:
                    self._restore_or_report(error, before, plan['model_state'], True, api_touched)
                    raise
        except BaseException:
            failed = True
            raise
        finally:
            if failed:
                for path in reversed(created):
                    if path == DIRECTORY:
                        # Preserve the stable lock inode, including for waiters
                        # which already opened it before this action failed.
                        continue
                    try:
                        f.rmdir(path)
                    except OSError:
                        pass
        return {'ok': True, 'action': 'enable', 'changed': True, 'port': port, 'key_reused': bool(plan['owner']),
                'credential_storage': 'Root0600 local plaintext, not an encrypted vault; exclude key/api.env from diagnostics and ordinary backups.',
                'api_status': 'configured_not_tested', 'mode': 'constrained_source_fact_selection'}

    def disable(self):
        self.host.require_root()
        owner = self.owner()
        self.api_guard()
        if owner is None:
            if self.host.state(MODEL).get('FragmentPath'):
                fail('FOREIGN_MODEL_UNIT', 'No owned model configuration exists; unrelated service was not controlled.')
            return {'ok': True, 'action': 'disable', 'changed': False}
        api_touched = False
        with self.files.lock():
            owner = self.owner()
            if owner is None:
                fail('OWNERSHIP_CHANGED', 'Optional AI ownership changed before the action lock was acquired.')
            self.api_guard()
            state = self.host.state(MODEL)
            self.model_guard(state)
            api_active = self.host.state(API).get('ActiveState') == 'active'
            if not owner['enabled'] and state.get('ActiveState') != 'active' and state.get('UnitFileState') != 'enabled' and not self.files.info(DROPIN):
                return {'ok': True, 'action': 'disable', 'changed': False, 'key_retained': True}
            before = self._snapshot()
            try:
                self.host.command('stop', MODEL)
                self.host.command('disable', MODEL)
                self.files.remove(DROPIN)
                self.files.atomic(MARKER, canonical({**owner, 'enabled': False}), 0o600)
                self.host.command('daemon-reload')
                if api_active:
                    api_touched = True
                    self.host.command('restart', API)
                    self.host.api_configuration(wait=True)
            except BaseException as error:
                self._restore_or_report(error, before, state, api_active, api_touched)
                raise
        return {'ok': True, 'action': 'disable', 'changed': True, 'key_retained': bool(self.files.info(KEY)), 'model_retained': True}

    def status(self):
        owner = self.owner()
        return {'ok': True, 'action': 'status', 'managed': owner is not None, 'enabled': bool(owner and owner['enabled']),
                'model': owner['model'] if owner else None, 'port': owner['port'] if owner else None,
                'key_present': bool(self.files.info(KEY)), 'model_service': self.host.state(MODEL),
                'credential_storage': 'Protected root0600 local plaintext; not an encrypted vault.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    enable = commands.add_parser('enable')
    enable.add_argument('--model', type=Path, required=True)
    enable.add_argument('--port', type=int, required=True)
    enable.add_argument('--preflight', action='store_true', help='Read-only validation; creates no file and changes no service')
    commands.add_parser('disable')
    commands.add_parser('status')
    args = parser.parse_args()
    try:
        controller = Controller()
        result = controller.enable(args.model, args.port, preflight_only=args.preflight) if args.action == 'enable' else getattr(controller, args.action)()
        print(json.dumps(result, indent=2))
        return 0
    except ConfigurationError as error:
        print(json.dumps({'ok': False, 'error': {'code': error.code, 'message': error.message, **getattr(error, 'details', {})}}, indent=2))
        return 1
    except OSError as error:
        print(json.dumps({'ok': False, 'error': {'code': 'FILESYSTEM_FAILURE', 'errno': error.errno, 'message': 'The protected optional configuration operation failed.'}}, indent=2))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
