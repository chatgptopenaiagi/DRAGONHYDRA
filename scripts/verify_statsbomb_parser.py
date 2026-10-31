"""Independent bounded StatsBomb parser acceptance using only synthetic data.

No provider HTTP, product server, live-state context write or model call occurs.
The retained real-parent snapshot supplies identity for pure parser checks; an
independent private synthetic state exercises full persisted reconstruction.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys
import traceback
from unittest.mock import patch
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from dragonhydra import source_context
from dragonhydra.cognition import memory
from dragonhydra.connectors import research, statsbomb_context as binding, statsbomb_context_parser as parser
from dragonhydra.connectors.core import Document, Transport, utc_now
from dragonhydra.product import Product
from dragonhydra.server import protect


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def event(index, **fields):
    return {'id': str(UUID(int=index)), 'index': index, 'type': {'id': 30, 'name': 'Pass'}, **fields}


SQUADS = [
    {'team_id': 779, 'team_name': 'Argentina', 'lineup': [{'player_id': 1001, 'player_name': 'SYNTHETIC Argentina player', 'jersey_number': 10}]},
    {'team_id': 771, 'team_name': 'France', 'lineup': [{'player_id': 2001, 'player_name': 'SYNTHETIC France player'}]},
]
EVENTS = [
    event(1, type={'id': 18, 'name': 'Half Start'}),
    event(2, team={'id': 779, 'name': 'Argentina'}, player={'id': 1001, 'name': 'SYNTHETIC Argentina player'},
          period=1, timestamp='00:00:01.125', minute=0, second=1),
    event(3, team={'id': 771, 'name': 'France'}, player={'id': 2001, 'name': 'SYNTHETIC France player'},
          period=2, timestamp='00:00:02.000', minute=46, second=2),
    event(4, team={'id': 779, 'name': 'Argentina'}, period=1),
]


class Acceptance:
    def __init__(self, output):
        self.output = output.resolve()
        assert self.output.is_relative_to(ROOT / 'build/connections') and not self.output.exists()
        self.output.mkdir(parents=True)
        protect(self.output)
        self.checks = []
        self.network_attempts = 0
        self.report = {'schema_version': 1, 'mode': 'synthetic_parser_no_http', 'passed': False,
                       'started_at': datetime.now(timezone.utc).isoformat(), 'checks': self.checks,
                       'real_events_or_lineups_acquired': False, 'live_context_written': False,
                       'source_bindings': {name: digest(ROOT / name) for name in (
                           'scripts/verify_statsbomb_parser.py', 'src/dragonhydra/connectors/statsbomb_context_parser.py',
                           'src/dragonhydra/connectors/statsbomb_context.py', 'src/dragonhydra/source_context.py',
                           'src/dragonhydra/cognition/memory.py')}}
        self.parent = read(ROOT / 'build/connections/statsbomb-binding-20261031/real-parent-readonly-r1/verification.json')['parent']

    def check(self, name, **details):
        self.checks.append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name}), flush=True)

    def network(self, *args, **kwargs):
        self.network_attempts += 1
        raise AssertionError('Parser acceptance forbids network access.')

    @staticmethod
    def rejected(operation):
        try:
            operation()
        except ValueError as error:
            return str(error)
        raise AssertionError('Malformed or unsupported input was accepted.')

    def parse(self, events=EVENTS, squads=SQUADS, **kwargs):
        return parser.parse(canonical(events), canonical(squads), parent=kwargs.pop('parent', self.parent), **kwargs)

    def pure_checks(self):
        projection = self.parse()
        summary = projection['event_summary']
        assert projection['parser_version'] == 'statsbomb-context/1' and projection['match_id'] == 3869685
        assert summary['row_count'] == 4
        assert summary['missing_fields'] == {'team': 1, 'player': 2, 'period': 1, 'timestamp': 2, 'minute': 2, 'second': 2}
        expected_groups = [
            {'team_id': None, 'period': None, 'type_id': 18, 'count': 1},
            {'team_id': 779, 'period': 1, 'type_id': 30, 'count': 2},
            {'team_id': 771, 'period': 2, 'type_id': 30, 'count': 1},
        ]
        assert sorted(canonical(row) for row in summary['counts_by_team_period_type']) == sorted(canonical(row) for row in expected_groups)
        page = parser.event_page(canonical(EVENTS), canonical(SQUADS), parent=self.parent, offset=0, limit=2)
        assert page['total'] == 4 and page['offset'] == 0 and page['limit'] == 2
        assert page['items'][0] == EVENTS[0] and page['items'][1] == EVENTS[1]
        assert all(key not in page['items'][0] for key in ('team', 'player', 'period', 'timestamp', 'minute', 'second'))
        assert page['items'][1]['minute'] == 0
        assert projection['squads'] == SQUADS
        self.report['small_projection'] = projection
        self.check('Native missing fields remain absent on pages; explicit zero remains present; missing counts, row groups and source squad entries are exact')

        extra = deepcopy(EVENTS)
        extra[0]['unconsumed_source_field'] = {'synthetic_only': True, 'finite_metric': .25}
        assert self.parse(extra) == projection
        assert 'unconsumed_source_field' not in parser.event_page(canonical(extra), canonical(SQUADS), parent=self.parent)['items'][0]
        self.check('Unknown unused source fields stay in retained raw bytes and do not become claimed event metrics or projection fields')

        cases = []
        def bad(label, events=None, squads=None, parent=None):
            code = self.rejected(lambda: self.parse(EVENTS if events is None else events, SQUADS if squads is None else squads,
                                                    **({'parent': parent} if parent is not None else {})))
            cases.append({'case': label, 'code': code})
        for field, value in (
            ('id', 'not-a-uuid'), ('index', True), ('index', 0), ('type', {'id': True, 'name': 'Pass'}),
            ('team', {'id': 999, 'name': 'wrong team'}), ('player', {'id': 999, 'name': 'not in source squad'}),
            ('period', True), ('period', 6), ('timestamp', '2026-10-31T00:00:01Z'), ('minute', -1), ('second', 60),
            ('team', None), ('player', None), ('timestamp', None),
        ):
            changed = deepcopy(EVENTS); changed[1][field] = value
            bad('invalid-' + field + '-' + repr(value), events=changed)
        for field in ('id', 'index'):
            changed = deepcopy(EVENTS); changed[1][field] = changed[0][field]
            bad('duplicate-' + field, events=changed)
        changed = deepcopy(SQUADS); changed[0]['lineup'] *= 2
        bad('duplicate-player', squads=changed)
        changed = deepcopy(SQUADS); changed[1]['team_id'] = 779
        bad('duplicate-team', squads=changed)
        changed = deepcopy(self.parent); changed['native_identity']['match_id'] = 1
        bad('wrong-native-parent', parent=changed)
        self.report['invalid_native_inputs'] = cases
        self.check('Invalid native UUIDs, duplicate indexes/IDs, booleans, participant identities, consumed field types and source clocks fail specifically', cases=len(cases))

        json_cases = [b'[{"id":1,"id":2}]', b'[NaN]', b'[Infinity]', b'[1e999]', b'{}', b'null', b'\xff']
        codes = []
        for body in json_cases:
            codes.append(self.rejected(lambda: parser.parse(body, canonical(SQUADS), parent=self.parent)))
        unused_overflow = canonical(EVENTS).replace(b'"index":1', b'"unused":1e999,"index":1', 1)
        assert unused_overflow != canonical(EVENTS)
        codes.append(self.rejected(lambda: parser.parse(unused_overflow, canonical(SQUADS), parent=self.parent)))
        self.report['invalid_json_codes'] = codes
        self.check('Duplicate JSON keys, nonfinite numeric constants and overflow in ignored fields, nonarray roots and invalid UTF-8 fail closed')

        large = [event(index) for index in range(1, 20001)]
        raw = canonical(large)
        maximum = parser.parse(raw, canonical(SQUADS), parent=self.parent)
        encoded = canonical(maximum)
        assert maximum['event_summary']['row_count'] == 20000 and len(encoded) < 1024 * 1024
        assert 'events' not in maximum and 'items' not in maximum
        tail = parser.event_page(raw, canonical(SQUADS), parent=self.parent, offset=19999, limit=200)
        assert tail['total'] == 20000 and len(tail['items']) == 1 and tail['items'][0]['index'] == 20000
        self.rejected(lambda: self.parse(large + [event(20001)]))
        excessive = deepcopy(SQUADS)
        excessive[0]['lineup'] = [{'player_id': index, 'player_name': 'SYNTHETIC player ' + str(index)} for index in range(1, 102)]
        self.rejected(lambda: self.parse(squads=excessive))
        for kwargs in ({'offset': -1}, {'offset': True}, {'limit': 201}, {'limit': 0}):
            self.rejected(lambda: parser.event_page(canonical(EVENTS), canonical(SQUADS), parent=self.parent, **kwargs))
        self.report['bounds'] = {'accepted_event_rows': 20000, 'event_bytes': len(raw), 'compact_projection_bytes': len(encoded),
                                 'rejected_event_rows': 20001, 'rejected_squad_entries': 101, 'maximum_page_rows': 200}
        self.check('Twenty thousand events yield a compact payload and bounded raw-backed page; event, squad and page limits reject excess inputs')

    def persistence_checks(self):
        state = self.output / 'SYNTHETIC-state'
        state.mkdir(); protect(state)
        product = Product(state)
        raw_dir = state / 'raw/connectors'; raw_dir.mkdir(parents=True)
        def document(content, role=None):
            body = canonical(content)
            sha = hashlib.sha256(body).hexdigest()
            original = binding.ROLE_URLS[role] if role in binding.ROLE_URLS else research.STATSBOMB_BASE + role
            resolved = original.replace(research.STATSBOMB_BASE, 'https://raw.githubusercontent.com/hudl/open-data/refs/heads/master/data/')
            doc = Document(original, resolved, body, utc_now(), sha, 'application/json', uuid4().hex, sha + '.payload')
            (raw_dir / doc.raw_reference).write_bytes(body)
            product.connector_store.receipt('statsbomb', doc)
            return doc
        catalog = document([{'competition_id': 43, 'season_id': 106, 'competition_name': 'FIFA World Cup', 'season_name': '2022'}], 'competitions.json')
        native_match = deepcopy(self.parent['normalized_record']['original'])
        native_match['SYNTHETIC_ACCEPTANCE_ONLY'] = True
        native_match['stadium'] = {'name': 'SYNTHETIC acceptance stadium'}
        native_match['metadata'] = {'data_version': 'SYNTHETIC-parser-acceptance'}
        matches = document([native_match], 'matches/43/106.json')
        class RetainedOnly:
            def get(self, url):
                if url == catalog.url:
                    return catalog
                assert url == matches.url
                return matches
        record = research._statsbomb({'competition_id': 43, 'season_id': 106}, RetainedOnly(), lambda: None)[0]
        imported = product.connector_store.ingest('statsbomb', [record], [catalog, matches])
        assert imported['inserted'] == 1 and imported['quarantined'] == 0
        observation_id = product.connector_store.rows('statsbomb')[0]['id']
        docs = {role: document(content, role) for role, content in (('events', EVENTS), ('lineups', SQUADS))}
        with closing(sqlite3.connect(product.db_path.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            parent = binding.parent_binding(db, raw_dir, observation_id)
            role_bindings = {role: binding.document_binding(db, raw_dir, role, doc.acquisition_id) for role, doc in docs.items()}
        draft = {'provider': 'statsbomb', 'source_record_id': '3869685', 'parent': parent, 'documents': role_bindings,
                 'parser_version': parser.VERSION, 'projection': parser.parse(docs['events'].body, docs['lineups'].body, parent=parent)}
        callback = parser.make_validator(raw_dir)
        saved = source_context.append(product.db_path, draft, validate_dependencies=callback)
        current = source_context.latest(product.db_path, 'statsbomb', '3869685', validate_dependencies=callback)
        assert current['availability'] == 'available' and current['item']['record_id'] == saved['record_id']
        statements = []
        with closing(sqlite3.connect(product.db_path.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            db.set_trace_callback(statements.append)
            permitted = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
            db.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in permitted else sqlite3.SQLITE_DENY)
            callback(db, current['item'])
            page = parser.read_event_page(db, raw_dir, current['item'], offset=1, limit=2)
            assert page['items'] == EVENTS[1:3] and page['total'] == 4
            changed = deepcopy(draft); changed['parser_version'] = 'unsupported-version'
            wrong_version = self.rejected(lambda: callback(db, changed))
            changed = deepcopy(draft); changed['parent']['native_identity']['home_team_id'] = 1
            wrong_parent = self.rejected(lambda: callback(db, changed))
            changed = deepcopy(draft); changed['projection']['event_summary']['row_count'] = 100
            wrong_projection = self.rejected(lambda: callback(db, changed))
            changed = deepcopy(draft); changed['projection']['unused_claim'] = 'unsupported projection field'
            unknown_projection = self.rejected(lambda: callback(db, changed))
            changed = deepcopy(draft); changed['projection']['event_summary']['row_count'] = 4.0
            numeric_type = self.rejected(lambda: callback(db, changed))
            db.set_authorizer(None)
        assert statements and all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
        self.report['full_callback'] = {'saved_record': saved, 'selected_native_page': page, 'select_statements': len(statements),
                                       'wrong_version': wrong_version, 'wrong_parent': wrong_parent,
                                       'wrong_projection': wrong_projection, 'unknown_projection_field': unknown_projection,
                                       'integer_to_float_projection': numeric_type}
        self.check('Full callback and bound page reconstruct exact parser version and complete projection from two exact receipts; wrong native identity, unknown claims and numeric-type tampering fail')

        corrupt = self.output / 'SYNTHETIC-rehashed-projection.sqlite3'
        with closing(sqlite3.connect(product.db_path)) as original_db, closing(sqlite3.connect(corrupt)) as clone:
            original_db.backup(clone)
            kind, old_id, natural_key, old_hash, payload = clone.execute('SELECT * FROM cognitive_records').fetchone()
            altered = json.loads(payload)
            altered['projection']['event_summary']['row_count'] = 999
            new_raw = memory._canonical(altered)
            new_hash = hashlib.sha256(new_raw).hexdigest()
            new_id = kind + ':' + hashlib.sha256(memory._canonical([kind, natural_key, new_hash])).hexdigest()
            clone.executescript('DROP TRIGGER cognitive_records_no_update; DROP TRIGGER cognitive_receipts_no_update;')
            clone.execute('UPDATE cognitive_records SET record_id=?,fingerprint=?,payload=? WHERE record_id=?', (new_id, new_hash, new_raw.decode(), old_id))
            clone.execute('UPDATE cognitive_receipts SET record_id=? WHERE record_id=?', (new_id, old_id))
            clone.commit()
            memory._schema(clone)
            assert clone.execute('PRAGMA foreign_key_check').fetchone() is None
            verified_chain = memory._revision_chain(clone, 'source_context', altered['scope'])
            assert verified_chain[0]['record_id'] == new_id and verified_chain[0]['payload']['projection']['event_summary']['row_count'] == 999
        rejected = source_context.latest(corrupt, 'statsbomb', '3869685', validate_dependencies=callback)
        assert rejected['availability'] == 'unavailable' and 'PROJECTION_RECONSTRUCTION_MISMATCH' in rejected['code']
        self.report['rehashed_projection'] = {'new_valid_record_id': new_id, 'new_valid_payload_sha256': new_hash,
                                             'store_chain_integrity_checked': True, 'read_result': rejected}
        self.check('Adversarial altered projection with recomputed payload hash, valid record ID and matching receipt foreign key is rejected by source reconstruction')

        path = raw_dir / docs['events'].raw_reference
        original_body = path.read_bytes()
        path.write_bytes(b'SYNTHETIC corrupt retained event bytes')
        assert source_context.latest(product.db_path, 'statsbomb', '3869685', validate_dependencies=callback)['availability'] == 'unavailable'
        path.write_bytes(original_body)
        restored = source_context.latest(product.db_path, 'statsbomb', '3869685', validate_dependencies=callback)
        assert restored['availability'] == 'available' and restored['item']['record_id'] == saved['record_id']
        with closing(sqlite3.connect(product.db_path.as_uri() + '?mode=ro', uri=True)) as db:
            assert db.execute('SELECT count(*) FROM cognitive_records').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM connector_observations').fetchone()[0] == 1
        self.check('Fresh retained-byte verification detects corruption without cached trust or invented zero context; restored bytes resolve the same immutable context')
        self.report['synthetic_state'] = str(state.relative_to(ROOT))

    def run(self):
        try:
            original_connect = sqlite3.connect
            def isolated_connect(database, *args, **kwargs):
                value = str(database)
                if value.startswith('file:'):
                    assert value.startswith(self.output.as_uri() + '/'), 'Live or unrelated SQLite access is forbidden.'
                else:
                    assert Path(database).resolve().is_relative_to(self.output), 'Live or unrelated SQLite access is forbidden.'
                return original_connect(database, *args, **kwargs)
            with patch.object(socket.socket, 'connect', self.network), patch.object(socket.socket, 'connect_ex', self.network), \
                    patch.object(Transport, 'get', self.network), patch.object(sqlite3, 'connect', isolated_connect):
                with patch.object(sqlite3, 'connect', side_effect=AssertionError('Pure parser must not open a database.')):
                    self.pure_checks()
                self.persistence_checks()
            assert self.network_attempts == 0
            assert all(digest(ROOT / name) == sha for name, sha in self.report['source_bindings'].items())
            self.report['passed'] = True
        except Exception as error:
            self.report['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
        finally:
            self.report.update(finished_at=datetime.now(timezone.utc).isoformat(), check_groups=len(self.checks), network_attempts=self.network_attempts)
            (self.output / 'verification.json').write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': self.report['passed'], 'groups': len(self.checks), 'network_attempts': self.network_attempts,
                          'error': self.report.get('error', {}).get('message'), 'report': str((self.output / 'verification.json').relative_to(ROOT))}))
        return 0 if self.report['passed'] else 1


def main():
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument('--output', required=True, type=Path)
    args = argument_parser.parse_args()
    assert not sys.flags.optimize
    return Acceptance(args.output).run()


if __name__ == '__main__':
    raise SystemExit(main())
