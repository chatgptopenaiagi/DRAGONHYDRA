"""Foreground, synthetic-only development server in a new marked runtime lane."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess

from . import VERSION

SOURCE = Path(__file__).absolute().parents[3]
LANE = SOURCE.parent
MARKER = '.genesis6-runtime.json'
VIRTUAL_TOKEN = 'virtual-session-only-not-a-real-account-1234'
GIT = r'C:\Program Files\Git\cmd\git.exe'
PACKAGE_BUILD = 'GENESIS6-BUILD.json'
PACKAGE_MANIFEST = 'GENESIS6-PAYLOAD.json'


def ordinary(path):
    path = Path(path)
    if '..' in path.parts:
        raise ValueError('GENESIS6_PARENT_TRAVERSAL_REJECTED')
    path = path.absolute()
    for part in (path, *path.parents):
        if part.exists() and (part.is_symlink() or getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('GENESIS6_REPARSE_PATH_REJECTED')
    return path


def prepare_state(path, *, lane=LANE):
    """A marker may be created only in an empty new directory in this lane."""
    lane, state = ordinary(lane), ordinary(path)
    allowed = lane / 'runtime'
    if lane.name != 'GENESIS-6-REALTIME-INTELLIGENCE' or state == allowed or not state.is_relative_to(allowed):
        raise ValueError('GENESIS6_OWN_RUNTIME_REQUIRED')
    marker = state / MARKER
    expected = {'schema_version': 'dragonhydra.genesis6-runtime/1', 'state': str(state),
                'lane': str(lane), 'synthetic_only': True, 'virtual_credentials_only': True}
    if state.exists():
        if not state.is_dir():
            raise ValueError('GENESIS6_STATE_DIRECTORY_REQUIRED')
        if marker.exists():
            ordinary(marker)
            if marker.stat().st_size > 4096 or json.loads(marker.read_text(encoding='utf-8')) != expected:
                raise ValueError('GENESIS6_MARKER_MISMATCH')
        elif any(state.iterdir()):
            raise ValueError('GENESIS6_EXISTING_STATE_ADOPTION_REJECTED')
    state.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        with marker.open('x', encoding='utf-8') as stream:
            json.dump(expected, stream, sort_keys=True); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    source = ordinary(state / 'virtual-source')
    source.mkdir(exist_ok=True)
    from .router import validate_virtual_context
    validate_virtual_context(state, source)
    return state, source


@contextmanager
def runtime_lock(state):
    """OS-owned lock; no PID killing, stale-lock deletion or automatic recovery."""
    path = ordinary(Path(state) / 'server.lock')
    stream = path.open('a+b')
    acquired = False
    try:
        if path.stat().st_size == 0:
            stream.write(b'\0'); stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            try: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error: raise RuntimeError('GENESIS6_ALREADY_RUNNING') from error
        else:
            import fcntl
            try: fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error: raise RuntimeError('GENESIS6_ALREADY_RUNNING') from error
        acquired = True
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def port_number(value):
    value = int(value)
    if not 1024 <= value <= 65535 or 18740 <= value <= 18751:
        raise ValueError('GENESIS6_PORT_NOT_PERMITTED')
    return value


def source_identity():
    # A Git checkout must use Git. An unreadable/broken checkout never falls back
    # to a package seal that could hide uncommitted changes.
    ordinary(SOURCE)
    if not has_git_metadata(SOURCE):
        return packaged_source_identity()
    def git(*args):
        result = subprocess.run([GIT, '--no-optional-locks', '-C', str(SOURCE), *args],
                                capture_output=True, text=True, timeout=15)
        if result.returncode: raise RuntimeError('GENESIS6_SOURCE_IDENTITY_UNAVAILABLE')
        return result.stdout.strip()
    if Path(git('rev-parse', '--show-toplevel')).resolve() != SOURCE.resolve():
        raise RuntimeError('GENESIS6_EXACT_SOURCE_ROOT_REQUIRED')
    head = git('rev-parse', 'HEAD')
    if not re.fullmatch('[a-f0-9]{40}', head): raise RuntimeError('GENESIS6_FULL_SOURCE_IDENTITY_REQUIRED')
    return {'source_sha': head, 'source_dirty': bool(git('status', '--porcelain')),
            'component_version': VERSION, 'build_kind': 'virtual-experimental-source',
            'synthetic': True, 'real_network_providers': False}


def has_git_metadata(source):
    for part in (source, *source.parents):
        try: (part / '.git').lstat()
        except FileNotFoundError: continue
        # Permission or filesystem failures cannot establish absence of Git.
        return True
    return False


def package_member_allowed(name):
    """The same finite payload policy used by the committed-source builder."""
    parts = PurePosixPath(name).parts
    if not parts or str(PurePosixPath(name)) != name or '..' in parts or '\\' in name or ':' in name or name.startswith('/'):
        return False
    if name == 'config/runtime/server-python314.lock.txt': return True
    if any(p.startswith('.') or p in {'data','fixtures','examples','runtime','dist','__pycache__'} for p in parts):
        return False
    web = {'app.js','index.html','style.css','favicon.svg','realtime.js','realtime.css'}
    if name.startswith('src/dragonhydra/') and name.endswith('.py'): return True
    if name.startswith('src/dragonhydra/resources/web/') and PurePosixPath(name).name in web and len(parts)==5: return True
    if name.startswith('client/desktop/web/') and PurePosixPath(name).name in web and len(parts)==4: return True
    if len(parts)==2 and parts[0]=='tests' and name.endswith('.py'):
        return parts[1].startswith('test_realtime_') or parts[1]=='test_genesis6_package.py'
    if name in {'scripts/Start-Genesis6.ps1','scripts/build_genesis6.py',
                'scripts/accept_genesis6.py','scripts/browser_genesis6.py'}: return True
    if name.startswith('docs/') and name.endswith('.md'):
        return (len(parts)==2 and parts[1].startswith('GENESIS6-')) or (len(parts)==3 and parts[1]=='realtime')
    return name in {'LICENSE','LICENSE.md'}


def packaged_source_identity():
    """Verify an extracted curated payload; its trusted ZIP hash is external.

    This is local byte-integrity evidence, not a signature or an independent
    proof that a commit exists. The build receipt and ZIP SHA256 supply that
    provenance. No runtime directory or dependency is added to the payload.
    """
    def need(condition, code):
        if not condition: raise RuntimeError('GENESIS6_PACKAGE_' + code)
    source = ordinary(SOURCE)
    need(source.name == 'source' and source.parent.name == 'GENESIS-6-REALTIME-INTELLIGENCE', 'LANE_REQUIRED')
    need(not has_git_metadata(source), 'GIT_METADATA_PRESENT')

    def raw_file(path, limit):
        ordinary(path)
        need(path.is_file() and path.stat().st_size <= limit, 'FILE_MISSING_OR_OVERSIZE')
        with path.open('rb') as stream: raw = stream.read(limit + 1)
        need(len(raw) <= limit, 'FILE_OVERSIZE')
        return raw

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    build_raw = raw_file(source / PACKAGE_BUILD, 16384)
    manifest_raw = raw_file(source / PACKAGE_MANIFEST, 256*1024)
    build = json.loads(build_raw, object_pairs_hook=unique_object)
    manifest = json.loads(manifest_raw, object_pairs_hook=unique_object)
    need(type(build) is dict and type(manifest) is dict, 'METADATA_OBJECT_REQUIRED')
    need(build.get('schema_version') == 'dragonhydra.genesis6-build/1'
         and manifest.get('schema_version') == 'dragonhydra.genesis6-payload/1', 'SCHEMA_MISMATCH')
    sha = build.get('source_sha')
    need(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha)
         and manifest.get('source_sha') == sha, 'SOURCE_MISMATCH')
    need(build.get('component_version') == manifest.get('component_version') == VERSION, 'VERSION_MISMATCH')
    need(build.get('payload_manifest') == PACKAGE_MANIFEST
         and build.get('payload_manifest_sha256') == hashlib.sha256(manifest_raw).hexdigest(), 'MANIFEST_HASH_MISMATCH')
    need(build.get('package_prefix') == 'GENESIS-6-REALTIME-INTELLIGENCE/source/'
         and build.get('source_clean') is True and build.get('synthetic_only') is True
         and build.get('real_sporting_data_included') is False
         and build.get('runtime_or_credentials_included') is False
         and build.get('dependencies_included') is False
         and build.get('build_kind') == 'curated-virtual-development-source'
         and type(build.get('commit_time_unix')) is int and build['commit_time_unix'] > 0, 'SCOPE_MISMATCH')
    files = manifest.get('files')
    need(type(files) is list and 1 <= len(files) <= 1000
         and type(build.get('payload_files')) is int and build['payload_files'] == len(files), 'FILE_COUNT_MISMATCH')
    expected = set()
    expected_paths = set()
    total = 0
    for item in files:
        need(type(item) is dict and set(item) == {'path','bytes','sha256','git_blob_sha1'}, 'FILE_RECORD_INVALID')
        name = item['path']
        need(type(name) is str and name and len(name) <= 240, 'PATH_INVALID')
        parts = PurePosixPath(name).parts
        need(str(PurePosixPath(name)) == name and not name.startswith('/') and ':' not in name
             and '\\' not in name and '..' not in parts and all(not p.startswith('.') for p in parts), 'PATH_INVALID')
        need(package_member_allowed(name), 'UNCURATED_FILE_REJECTED')
        need(name not in {PACKAGE_BUILD,PACKAGE_MANIFEST} and name.casefold() not in expected, 'PATH_COLLISION')
        expected.add(name.casefold())
        expected_paths.add(name)
        need(type(item['bytes']) is int and 0 <= item['bytes'] <= 4*1024*1024
             and type(item['sha256']) is str and re.fullmatch('[a-f0-9]{64}',item['sha256'])
             and type(item['git_blob_sha1']) is str and re.fullmatch('[a-f0-9]{40}',item['git_blob_sha1']), 'FILE_RECORD_INVALID')
        total += item['bytes']
        need(total <= 64*1024*1024, 'PAYLOAD_OVERSIZE')
        raw = raw_file(source.joinpath(*parts), item['bytes'])
        need(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256']
             and hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() == item['git_blob_sha1'], 'FILE_HASH_MISMATCH')
    required = {'src/dragonhydra/api.py','src/dragonhydra/product.py','src/dragonhydra/kernel/composition.py',
                'src/dragonhydra/realtime/__init__.py','src/dragonhydra/realtime/server.py',
                'src/dragonhydra/realtime/service.py','src/dragonhydra/realtime/router.py',
                'scripts/start-genesis6.ps1','scripts/build_genesis6.py',
                'scripts/accept_genesis6.py','scripts/browser_genesis6.py','docs/genesis6-development-package.md'}
    required |= {'src/dragonhydra/resources/web/'+n for n in
                 ('app.js','index.html','style.css','favicon.svg','realtime.js','realtime.css')}
    need(required <= expected, 'REQUIRED_FILE_MISSING')
    # os.walk does not follow directory links, and we reject junctions/reparse
    # points before descent. Extra files (including bytecode caches) fail closed.
    directories_expected = {str(parent) for name in expected_paths for parent in PurePosixPath(name).parents
                            if str(parent) != '.'}
    actual = set()
    actual_paths = set()
    for current, directories, names in os.walk(source, followlinks=False):
        for name in directories:
            directory = ordinary(Path(current) / name)
            need(directory.relative_to(source).as_posix() in directories_expected, 'DIRECTORY_INVENTORY_MISMATCH')
        for name in names:
            path = ordinary(Path(current) / name)
            actual_path = path.relative_to(source).as_posix()
            relative = actual_path.casefold()
            need(relative not in actual, 'ACTUAL_PATH_COLLISION')
            actual.add(relative)
            actual_paths.add(actual_path)
            need(len(actual) <= len(expected)+2, 'INVENTORY_MISMATCH')
    need(actual_paths == expected_paths | {PACKAGE_BUILD,PACKAGE_MANIFEST}, 'INVENTORY_MISMATCH')
    return {'source_sha':sha,'source_dirty':False,'component_version':VERSION,
            'build_kind':'verified-curated-development-payload','payload_verified':True,
            'verification_scope':'LOCAL_PAYLOAD_SHA256_MANIFEST_AT_STARTUP',
            'synthetic':True,'real_network_providers':False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=LANE / 'runtime' / 'web')
    parser.add_argument('--port', type=port_number, default=19380)
    parser.add_argument('--build-info', action='store_true')
    args = parser.parse_args(argv)
    if LANE.name != 'GENESIS-6-REALTIME-INTELLIGENCE':
        raise ValueError('GENESIS6_SOURCE_LANE_REQUIRED')
    identity = source_identity()
    if args.build_info:
        print(json.dumps(identity, sort_keys=True)); return 0
    state, source = prepare_state(args.state)
    with runtime_lock(state):
        # Check only this requested loopback port; never stop an existing listener.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try: probe.bind(('127.0.0.1', args.port))
            except OSError as error: raise RuntimeError('GENESIS6_PORT_IN_USE') from error
        from ..api import create_app
        from ..kernel.contracts import KernelConfig
        import uvicorn
        config = KernelConfig('genesis6-virtual-' + hashlib.sha256(str(state).encode()).hexdigest()[:16],
            environment_id='synthetic-research', build_id='genesis6-virtual-source',
            source_commit=identity['source_sha'], version=VERSION, disabled_modules=('ai',))
        app = create_app(state, local_token=VIRTUAL_TOKEN, bridge_secret='', start_worker=False,
                         source_root=source, kernel_config=config, realtime_config={})
        app.state.virtual_build = identity
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, access_log=False))
        app.state.shutdown_callback = lambda: setattr(server, 'should_exit', True)
        print(json.dumps({'url': f'http://127.0.0.1:{args.port}/#research', **identity,
                          'pairing': 'Use the documented virtual-only token; no account credentials are read.'}), flush=True)
        server.run()
    return 0


if __name__ == '__main__': raise SystemExit(main())
