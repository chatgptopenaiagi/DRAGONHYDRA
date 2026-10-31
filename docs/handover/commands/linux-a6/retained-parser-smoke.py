"""Linux stdlib-only retained parser smoke; no HTTP or database connection."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys
from unittest.mock import patch
from urllib.request import OpenerDirector

ROOT = Path('/mnt/c/xampp/DRAGONHYDRA')
WORK = ROOT / 'build/linux/prep-20261031-a6'
SITE = WORK / 'linux-smoke/site-packages'
EXPECTED_SOURCE = '3319aed91dd0bb8d74062ed2335f5817422615e30e51d11c3fc970f477de5804'
STATE = ROOT / 'build/connections/sports-package-3-20261031/qwen-api-r1/api-state'
REAL = ROOT / 'build/connections/statsbomb-context-job-20261031/real-r1'
FILES = {
    'events': (STATE / 'raw/connectors/a0b0036d50c10a4c8879d1ee9f24a7502ec2cfb264a61951c8d500dfc897ec35.payload',
               'a0b0036d50c10a4c8879d1ee9f24a7502ec2cfb264a61951c8d500dfc897ec35'),
    'lineups': (STATE / 'raw/connectors/2b00c4cbf027b36ae2ce99f183a0943c649bb5bdcb8324683a8603785beffed5.payload',
                '2b00c4cbf027b36ae2ce99f183a0943c649bb5bdcb8324683a8603785beffed5'),
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


attempts = []
def forbidden(*args, **kwargs):
    attempts.append('blocked')
    raise AssertionError('Pure retained parser smoke permits no network, database or context writes.')


assert not sys.flags.optimize and sys.flags.isolated and sys.dont_write_bytecode
assert sys.version_info[:2] == (3, 14) and SITE.is_dir()
sys.path.insert(0,str(WORK))
from wheel_guard import guarded_wheel
sys.path.insert(0, str(SITE))
with guarded_wheel(WORK,SITE) as guard, ExitStack() as guards:
    guards.enter_context(patch.object(sqlite3, 'connect', forbidden))
    guards.enter_context(patch.object(socket.socket, 'connect', forbidden))
    guards.enter_context(patch.object(socket.socket, 'connect_ex', forbidden))
    guards.enter_context(patch.object(socket, 'create_connection', forbidden))
    guards.enter_context(patch.object(OpenerDirector, 'open', forbidden))
    import dragonhydra
    from dragonhydra import source_context
    from dragonhydra.build_meta import info
    from dragonhydra.cognition import memory
    from dragonhydra.connectors import statsbomb_context_parser as parser
    from dragonhydra.connectors.core import Transport
    from dragonhydra.connectors.store import Store
    guards.enter_context(patch.object(source_context, 'append', forbidden))
    guards.enter_context(patch.object(source_context, 'recover', forbidden))
    guards.enter_context(patch.object(memory, '_schema', forbidden))
    guards.enter_context(patch.object(Store, '__init__', forbidden))
    guards.enter_context(patch.object(Transport, 'get', forbidden))
    assert Path(dragonhydra.__file__).resolve().is_relative_to(SITE)
    assert Path(parser.__file__).resolve().is_relative_to(SITE)
    assert info()['source_content_sha256'] == EXPECTED_SOURCE and info()['source_sha'] is None
    parent_file = REAL / 'preflight.json'
    projection_file = REAL / 'context.json'
    source_hashes = {str(path.relative_to(ROOT)): digest(path) for path in (parent_file, projection_file)}
    parent = json.loads(parent_file.read_text())['request']['parent']
    expected = json.loads(projection_file.read_text())['projection']
    raw = {}
    for role, (path, expected_hash) in FILES.items():
        assert path.is_file() and not path.is_symlink() and path.stat().st_size <= 8 * 1024 * 1024
        assert digest(path) == expected_hash
        raw[role] = path.read_bytes()
    projected = parser.parse(raw['events'], raw['lineups'], parent=parent)
    assert canonical(projected) == canonical(expected)
    assert projected['event_summary']['row_count'] == 4407
    assert {team['team_id']: len(team['lineup']) for team in projected['squads']} == {771: 24, 779: 26}
    assert len(projected['event_summary']['types']) == 29
    assert len(projected['event_summary']['counts_by_team_period_type']) == 181
    native = json.loads(raw['events'])
    pages = []
    for offset in (0, 2200, 4400):
        page = parser.event_page(raw['events'], raw['lineups'], parent=parent, offset=offset, limit=200)
        fields = ('id', 'index', 'type', 'team', 'player', 'period', 'timestamp', 'minute', 'second')
        expected_page = [{key: item[key] for key in fields if key in item} for item in native[offset:offset + 200]]
        assert page['items'] == expected_page and page['total'] == 4407
        pages.append({'offset': offset, 'rows': len(page['items']), 'first_index': page['items'][0]['index'],
                      'last_index': page['items'][-1]['index']})
    for role, (path, expected_hash) in FILES.items():
        assert digest(path) == expected_hash
    assert {str(path.relative_to(ROOT)): digest(path) for path in (parent_file, projection_file)} == source_hashes
    assert not attempts
    optional_imports = {name: name in sys.modules for name in ('fastapi', 'uvicorn', 'openpyxl', 'tzdata')}
    assert not any(optional_imports.values())
    print(json.dumps({'passed': True, 'python': sys.version, 'python_executable': sys.executable,
        'wheel_module': str(Path(parser.__file__).relative_to(ROOT)), 'source_content_sha256': EXPECTED_SOURCE,
        'retained_data_not_fresh_http': True, 'event_rows': 4407, 'squad_entries': {'771': 24, '779': 26},
        'event_types': 29, 'count_groups': 181, 'projection_sha256': hashlib.sha256(canonical(projected)).hexdigest(),
        'pages': pages, 'input_payloads': {role: {'sha256': value[1], 'bytes': len(raw[role])} for role, value in FILES.items()},
        'input_files_unchanged': True, 'forbidden_attempts': len(attempts), 'optional_server_packages_imported': optional_imports,
        'guards':guard.report(), 'server_runtime_verified': False, 'database_connected': False, 'service_activated': False}, ensure_ascii=False))
