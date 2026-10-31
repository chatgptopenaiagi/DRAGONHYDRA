"""Explicit Linux-only fix for the immutable prep-r2 application wheel.

This modifies only the new package staging tree. The input wheel, shared source
checkout and working installations are never changed. Build identity must retain
the frozen base identity and this returned transformation receipt.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
from pathlib import Path
import stat
import tempfile

BASE_SERVER_SHA256 = '855c3e28d98d2aa7bad554aff2aff1683d0cb3a4e03565533b0a2fc0e869105b'
TARGET = 'dragonhydra/server.py'
RECORD = 'dragonhydra-0.4.0a1.dist-info/RECORD'
PATCH_ID = 'linux-listener-reuse-v1'


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _record_hash(body):
    return 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip('=')


def _atomic_write(path, body):
    descriptor, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_server_patch(site: Path) -> dict:
    """Validate exact known bytes and RECORD, then patch the isolated payload.

    A newer wheel requires a new reviewed transform; this is deliberately not a
    fuzzy patch or a way to silently change shared application source.
    """
    site = Path(site).resolve()
    target, record = site/TARGET, site/RECORD
    for path in (target, record):
        if path.is_symlink() or not path.resolve().is_relative_to(site) or not path.is_file():
            raise ValueError('Unsafe or missing frozen application patch input')
    if any((record.parent/name).exists() for name in ('RECORD.jws', 'RECORD.p7s')):
        raise ValueError('Refusing to invalidate a signed application RECORD')
    original, original_record = target.read_bytes(), record.read_bytes()
    if _sha(original) != BASE_SERVER_SHA256:
        raise ValueError('Unexpected frozen server.py; reviewed Linux patch cannot be applied')
    newline = b'\r\n' if b'\r\n' in original else b'\n'
    old_branch = newline.join((
        b"    if os.name == 'nt':",
        b'        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)',
        b'    try:',
        b'        listener.bind((args.host, args.port))',
        b'    except OSError:',
        b"        raise SystemExit('Configured product port is busy; no unrelated service was stopped. Use --port 0 to allocate a free port.') from None"))
    new_branch = newline.join((
        b"    if os.name == 'nt':",
        b'        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)',
        b"    elif sys.platform.startswith('linux'):",
        b'        # Rebind our fixed endpoint after graceful shutdown/TIME_WAIT.',
        b'        # SO_REUSEPORT is intentionally not enabled: live listeners stay exclusive.',
        b'        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)',
        b'    try:',
        b'        listener.bind((args.host, args.port))',
        b'    except OSError as error:',
        b'        listener.close()',
        b"        raise SystemExit(f'Configured product port cannot bind [errno={error.errno}]: {error.strerror}; no unrelated service was stopped. Use --port 0 to allocate a free port.') from None"))
    if original.count(old_branch) != 1:
        raise ValueError('Exact frozen listener block was not found once')
    patched = original.replace(old_branch, new_branch, 1)
    rows = list(csv.reader(io.StringIO(original_record.decode('utf-8'), newline='')))
    matches = [row for row in rows if row and row[0] == TARGET]
    if len(matches) != 1 or matches[0] != [TARGET, _record_hash(original), str(len(original))]:
        raise ValueError('Frozen server.py RECORD is missing, duplicated or inconsistent')
    matches[0][1:] = [_record_hash(patched), str(len(patched))]
    buffer = io.StringIO(newline='')
    csv.writer(buffer, lineterminator='\n').writerows(rows)
    patched_record = buffer.getvalue().encode('utf-8')
    # All semantic preconditions above are checked before writing either file.
    # The builder owns this fresh staging tree; a write failure fails the build.
    _atomic_write(target, patched)
    _atomic_write(record, patched_record)
    return {
        'id': PATCH_ID, 'target': TARGET,
        'base_sha256': _sha(original), 'transformed_sha256': _sha(patched),
        'transform_script_sha256': _sha(Path(__file__).read_bytes()),
        'record': RECORD, 'record_base_sha256': _sha(original_record),
        'record_transformed_sha256': _sha(patched_record),
        'purpose': 'Linux-only SO_REUSEADDR for stable-endpoint restart; preserve bind errno; Windows exclusive-bind branch unchanged',
        'shared_source_changed': False, 'input_wheel_changed': False,
    }
