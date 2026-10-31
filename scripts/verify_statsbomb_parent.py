"""Prove the selected StatsBomb parent binding from retained bytes, read only.

No events or lineup payloads are acquired or interpreted. The generic context
foundation and running product state are not initialized or written.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from dragonhydra.cognition import memory
from dragonhydra.connectors import statsbomb_context as binding, store
from dragonhydra.server import protect

PARENT_ID = '3c4061086077375b28d9a482c9559a0e9f31c5310031ffc6eeb7df4e454cbdc9'
PRIMARY_ID = 'f9b4a79099e94cba9b3d706610f260e9'
CATALOG_ID = '96e3d7c8812b45069d8d45720b7e59c9'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(db):
    tables = {}
    for name in ('connector_observations', 'connector_acquisitions', 'connector_attempts', 'connector_quarantine'):
        rows = db.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall()
        tables[name] = {'rows': len(rows), 'sha256': hashlib.sha256(b'\n'.join(canonical(list(row)) for row in rows)).hexdigest()}
    schema = db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall()
    return {'schema_sha256': hashlib.sha256(canonical([list(row) for row in schema])).hexdigest(), 'tables': tables}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=ROOT / 'runtime/connections/product')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not sys.flags.optimize
    state, output = args.state.resolve(), args.output.resolve()
    assert state == ROOT / 'runtime/connections/product'
    assert output.is_relative_to(ROOT / 'build/connections') and not output.exists()
    output.mkdir(parents=True)
    protect(output)
    checks, statements = [], []
    report = {'schema_version': 1, 'passed': False, 'mode': 'retained_real_parent_binding_read_only',
              'checks': checks, 'started_at': datetime.now(timezone.utc).isoformat(),
              'state': str(state.relative_to(ROOT)), 'database_mode': 'ro; query_only=ON',
              'fresh_http': False, 'context_written': False, 'events_or_lineups_acquired': False,
              'events_or_lineups_parsed': False, 'new_sports_projection_claimed': False,
              'source_bindings': {name: digest(ROOT / name) for name in (
                  'scripts/verify_statsbomb_parent.py', 'src/dragonhydra/connectors/statsbomb_context.py',
                  'src/dragonhydra/connectors/research.py', 'src/dragonhydra/connectors/store.py')}}
    forbidden = {'network': 0, 'schema_initialization': 0, 'store_construction': 0, 'extra_connection': 0}
    def refuse(kind):
        def rejected(*args, **kwargs):
            forbidden[kind] += 1
            raise AssertionError('Read-only binding proof forbids ' + kind)
        return rejected
    def check(name, **details):
        checks.append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name}), flush=True)
    def rejected(operation):
        try:
            operation()
        except ValueError as error:
            return str(error)
        raise AssertionError('An unselected or unavailable dependency was accepted.')
    try:
        with closing(sqlite3.connect((state / 'core.sqlite3').as_uri() + '?mode=ro', uri=True, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            before = snapshot(db)
            parents = db.execute("SELECT id FROM connector_observations WHERE provider='statsbomb' AND source_record_id='3869685'").fetchall()
            assert [row['id'] for row in parents] == [PARENT_ID], 'The exact selected retained parent changed; no latest-parent substitution is permitted.'
            other_match = db.execute("SELECT id FROM connector_observations WHERE provider='statsbomb' AND source_record_id<>'3869685' AND acquisition_id=? ORDER BY seq LIMIT 1", (PRIMARY_ID,)).fetchone()['id']
            other_provider = db.execute("SELECT id FROM connector_observations WHERE provider<>'statsbomb' ORDER BY seq LIMIT 1").fetchone()['id']
            raw_paths = [state / 'raw/connectors' / db.execute('SELECT raw_reference FROM connector_acquisitions WHERE id=?', (ident,)).fetchone()[0]
                         for ident in (PRIMARY_ID, CATALOG_ID)]
            raw_before = {str(path.relative_to(state)): digest(path) for path in raw_paths}
            retained_observation = db.execute('SELECT record,content_hash FROM connector_observations WHERE id=?', (PARENT_ID,)).fetchone()
            normalized = json.loads(retained_observation['record'])
            normalized.pop(store.PROVENANCE_FIELD, None)
            exact_receipts = {}
            for ident in (PRIMARY_ID, CATALOG_ID):
                row = db.execute('SELECT * FROM connector_acquisitions WHERE id=?', (ident,)).fetchone()
                exact_receipts[ident] = {key: row[key] for key in ('id', 'provider', 'sha256', 'original_url', 'resolved_url', 'captured_at')}
                path = state / 'raw/connectors' / row['raw_reference']
                assert digest(path) == row['sha256'] and path.stat().st_size == row['bytes']
            native_rows = json.loads(raw_paths[0].read_bytes())
            selected = [row for row in native_rows if row.get('match_id') == 3869685]
            assert len(selected) == 1 and canonical(selected[0]) == canonical(normalized['original'])
            expected_identity = {'match_id': 3869685, 'competition_id': 43, 'season_id': 106,
                                 'home_team_id': 779, 'away_team_id': 771, 'event_date': '2022-12-18'}
            newer_catalog_receipts = db.execute('SELECT count(*) FROM connector_acquisitions WHERE provider=? AND sha256=? AND captured_at>?',
                                                ('statsbomb', exact_receipts[CATALOG_ID]['sha256'], exact_receipts[CATALOG_ID]['captured_at'])).fetchone()[0]
            assert newer_catalog_receipts > 0
            db.set_trace_callback(statements.append)
            permitted = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
            db.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in permitted else sqlite3.SQLITE_DENY)
            with patch.object(socket.socket, 'connect', refuse('network')), patch.object(socket.socket, 'connect_ex', refuse('network')), \
                    patch.object(memory, '_schema', refuse('schema_initialization')), \
                    patch.object(store.Store, '__init__', refuse('store_construction')), \
                    patch.object(sqlite3, 'connect', refuse('extra_connection')):
                parent = binding.parent_binding(db, state / 'raw/connectors', PARENT_ID)
                assert parent['observation_id'] == PARENT_ID and parent['source_record_id'] == '3869685'
                assert parent['source_document_sha256'] == exact_receipts[PRIMARY_ID]['sha256']
                assert parent['observation_content_hash'] == retained_observation['content_hash']
                assert parent['native_identity'] == expected_identity
                assert parent['match_list_acquisition'] == exact_receipts[PRIMARY_ID]
                assert parent['catalog_acquisition'] == exact_receipts[CATALOG_ID]
                assert canonical(parent['normalized_record']) == canonical(normalized)
                report['parent'] = parent
                check('Exact selected real parent reconstructs from retained match list and original catalog receipt, preserving native identities and every normalized field',
                      newer_same_hash_catalog_receipts_not_substituted=newer_catalog_receipts)
                wrong_match = rejected(lambda: binding.parent_binding(db, state / 'raw/connectors', other_match))
                wrong_provider = rejected(lambda: binding.parent_binding(db, state / 'raw/connectors', other_provider))
                missing = rejected(lambda: binding.parent_binding(db, state / 'raw/connectors', 'not-a-retained-observation'))
                check('Another native match sharing the same primary file, another provider, and a missing parent fail closed',
                      other_match_code=wrong_match, other_provider_code=wrong_provider, missing_code=missing)
                for role in ('events', 'lineups'):
                    assert rejected(lambda: binding.document_binding(db, state / 'raw/connectors', role, PRIMARY_ID))
                    assert rejected(lambda: binding.document_binding(db, state / 'raw/connectors', role, 'not-retained-' + role))
                check('A retained match-list receipt cannot masquerade as event/lineup evidence; missing role receipts are rejected')
                validator = binding.make_binding_validator(state / 'raw/connectors')
                payload = {'provider': 'statsbomb', 'source_record_id': '3869685', 'parent': parent,
                           'documents': {'events': exact_receipts[PRIMARY_ID], 'lineups': exact_receipts[CATALOG_ID]}}
                absent_roles = rejected(lambda: validator(db, payload))
                check('Binding factory refuses a real parent whose supplied receipts do not establish the two exact context roles', code=absent_roles)
                after = snapshot(db)
                assert after == before
            db.set_authorizer(None)
            assert all(statement.lstrip().upper().startswith('SELECT') for statement in statements)
            assert {str(path.relative_to(state)): digest(path) for path in raw_paths} == raw_before
            report.update(database_snapshot_before=before, database_snapshot_after=after,
                          raw_files_sha256=raw_before, sql_statements=len(statements), forbidden_calls=forbidden,
                          selected_primary_acquisition_id=PRIMARY_ID, selected_catalog_acquisition_id=CATALOG_ID)
            assert not any(forbidden.values())
            check('Only SELECT statements ran; original raw hashes and database snapshot are unchanged; no constructor, schema, hidden connection or network call occurred')
        assert all(digest(ROOT / name) == sha for name, sha in report['source_bindings'].items())
        report['passed'] = True
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(), check_groups=len(checks))
        (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'groups': len(checks), 'error': report.get('error', {}).get('message'),
                      'evidence': str((output / 'verification.json').relative_to(ROOT))}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
