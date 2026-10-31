"""Keep the systemd component's loopback address stable without changing CLI port0.

This module is also embedded in the Debian preinst so an old package can hand
its active address to the new package before its endpoint.json is removed.
No credentials are read. Only the exact package-owned unit may be stopped.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import fcntl
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

CACHE = 'managed-port.json'
UNIT = 'dragonhydra-api.service'
PREFIX = '/opt/dragonhydra/api'
STATE = '/var/lib/dragonhydra-api'


def validate(data):
    if (not isinstance(data, dict) or set(data) != {'schema_version', 'host', 'port'}
            or type(data['schema_version']) is not int or data['schema_version'] != 1 or data['host'] != '127.0.0.1'
            or type(data['port']) is not int or not 1 <= data['port'] <= 65535):
        raise ValueError('Invalid managed loopback port; repair managed-port.json or configure DRAGONHYDRA_PORT explicitly.')
    return data['port']


def read_cache(state):
    try:
        fd = os.open(state / CACHE, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024:
            raise ValueError('Managed port must be a small regular file.')
        return validate(json.loads(stream.read()))


def set_owner(fd, state):
    # DynamicUser id-mapped state appears as nobody to the host root process.
    # Preserve that directory identity instead of creating unreadable root files.
    os.fchmod(fd, 0o600)
    if os.geteuid() == 0:
        owner = state.stat()
        os.fchown(fd, owner.st_uid, owner.st_gid)


def write_cache(state, port):
    data = {'schema_version': 1, 'host': '127.0.0.1', 'port': port}
    validate(data)
    destination = state / CACHE
    if destination.is_symlink():
        raise ValueError('Managed port cannot be a symbolic link.')
    fd, name = tempfile.mkstemp(prefix='.managed-port-', suffix='.tmp', dir=state)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            set_owner(stream.fileno(), state)
            stream.write((json.dumps(data, sort_keys=True) + '\n').encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked_state(state):
    fd = os.open(state / 'managed-port.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Managed port lock is not a regular file.')
        set_owner(fd, state)
        deadline = time.monotonic() + 5
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Managed port lock is busy; no existing file was changed.')
                time.sleep(.05)
        yield
    finally:
        os.close(fd)


def managed_arguments(argv):
    """Only the managed service opts in; normal --port0 stays ephemeral."""
    argv = list(argv)
    if os.environ.get('DRAGONHYDRA_MANAGED_ENDPOINT') != '1' or any(x in argv for x in ('--build-info', '--help', '-h')):
        return argv
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--state', type=Path, default=Path('runtime/product'))
    parser.add_argument('--port', type=int, default=18743)
    known, _ = parser.parse_known_args(argv)
    if known.port != 0:
        return argv
    state = known.state.resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with locked_state(state):
        port = read_cache(state)
        if port is None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            write_cache(state, port)
    # argparse's last occurrence wins, including --port=0 and duplicated options.
    return [*argv, '--port', str(port)]


def command(argv):
    result = subprocess.run(argv, check=True, capture_output=True, text=True, timeout=50)
    return result.stdout.strip()


def upgrade():
    """Capture a legacy endpoint, stop only this product and wait out TIME_WAIT."""
    if os.geteuid() != 0:
        raise RuntimeError('Debian upgrade preparation requires root.')
    identity = json.loads(Path(PREFIX, 'BUILD-IDENTITY.json').read_text())
    if identity.get('component') != 'dragonhydra-api':
        raise RuntimeError('Existing product identity does not match; no unit was stopped.')
    owner = command(['dpkg-query', '-S', PREFIX + '/BUILD-IDENTITY.json'])
    if owner != 'dragonhydra-api: ' + PREFIX + '/BUILD-IDENTITY.json':
        raise RuntimeError('Existing files are not owned by this Debian package.')
    props = dict(line.split('=', 1) for line in command([
        'systemctl', 'show', UNIT, '-p', 'MainPID', '-p', 'ActiveState', '-p', 'FragmentPath', '-p', 'ExecStart'
    ]).splitlines() if '=' in line)
    if (props.get('FragmentPath') != '/usr/lib/systemd/system/' + UNIT
            or PREFIX + '/bin/dragonhydra-server' not in props.get('ExecStart', '')
            or '--state ' + STATE not in props.get('ExecStart', '')):
        raise RuntimeError('Installed unit ownership mismatch; no unit was stopped.')
    if props.get('ActiveState') != 'active':
        return
    state = Path(STATE).resolve()
    endpoint = json.loads((state / 'endpoint.json').read_text())
    parsed = urlsplit(endpoint['url'])
    if (endpoint.get('pid') != int(props['MainPID']) or parsed.scheme != 'http'
            or parsed.hostname != '127.0.0.1' or not parsed.port
            or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise RuntimeError('Current endpoint does not belong to this unit; no unit was stopped.')
    with locked_state(state):
        if read_cache(state) is None:
            write_cache(state, parsed.port)
    print('Preserved the managed loopback port; stopping only ' + UNIT + '.', flush=True)
    command(['systemctl', 'stop', UNIT])
    deadline = time.monotonic() + 75
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(('127.0.0.1', parsed.port))
            print('Previous loopback port is available for the upgraded service.', flush=True)
            return
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE or time.monotonic() >= deadline:
                # Do not kill a listener or silently change the configured address.
                # Restore the previously installed service when preparation fails.
                try:
                    command(['systemctl', 'start', UNIT])
                except subprocess.SubprocessError:
                    pass
                raise RuntimeError('Upgrade port preparation failed; errno=' + str(exc.errno)) from exc
            time.sleep(.25)


if __name__ == '__main__':
    if sys.argv[1:] != ['upgrade']:
        raise SystemExit('Only the Debian upgrade preparation command is supported.')
    upgrade()
