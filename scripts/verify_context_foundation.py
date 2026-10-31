"""Independent synthetic persistence/migration acceptance, with network disabled.

All state is new and project-local. This checks the generic trusted-validator
seam, not a StatsBomb parser, provider HTTP, product API or MariaDB execution.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import traceback
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from dragonhydra import migration, mariadb_migration, source_context
from dragonhydra.cognition import memory
from dragonhydra.connectors.core import Document, utc_now
from dragonhydra.jobs import Jobs
from dragonhydra.product import Product


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sql_state(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        result = {'schema': db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall(), 'tables': {}}
        for name in names:
            assert name.replace('_', '').isalnum()
            rows = db.execute('SELECT * FROM "' + name + '"').fetchall()
            encoded = sorted(canonical([{'blob': item.hex()} if isinstance(item, bytes) else item for item in row]) for row in rows)
            result['tables'][name] = {'rows': len(rows), 'sha256': hashlib.sha256(b'\n'.join(encoded)).hexdigest()}
        return result


class Fixture:
    provider = 'statsbomb'
    native = 'SYNTHETIC-foundation-3869685'

    def __init__(self, state):
        self.state = state
        migration._directory(state)
        self.product = Product(state)
        Jobs(self.product)  # Initialize the complete audited core profile, no worker.
        self.db_path = self.product.db_path
        self.raw = state / 'raw/connectors'
        self.raw.mkdir(parents=True)
        self.primary = self.document('parent', {'synthetic': True, 'match_id': self.native, 'home_id': 779, 'away_id': 771})
        record = {'source_record_id': self.native, 'sport': 'football', 'competition': 'SYNTHETIC foundation',
                  'home': 'SYNTHETIC Argentina', 'away': 'SYNTHETIC France', 'event_date': '2026-10-31',
                  'status': 'synthetic', 'score_home': None, 'score_away': None,
                  'source_document_sha256': self.primary.sha256, 'odds': [], 'attributes': {'data_origin': 'synthetic'}}
        imported = self.product.connector_store.ingest(self.provider, [record], [self.primary])
        assert imported['inserted'] == 1 and imported['quarantined'] == 0
        self.parent = self.product.connector_store.rows(self.provider)[0]['id']

    def document(self, role, content):
        body = canonical(content)
        sha = hashlib.sha256(body).hexdigest()
        path = self.raw / (sha + '.payload')
        path.write_bytes(body)
        url = 'https://example.invalid/SYNTHETIC-foundation/' + role
        doc = Document(url, url, body, utc_now(), sha, 'application/json', uuid4().hex, path.name)
        self.product.connector_store.receipt(self.provider, doc)
        return doc

    def draft(self, event_rows=2):
        events = self.document('events', {'synthetic': True, 'event_rows': event_rows})
        lineups = self.document('lineups', {'synthetic': True, 'team_ids': [779, 771]})
        def binding(doc):
            return {'id': doc.acquisition_id, 'provider': self.provider, 'sha256': doc.sha256,
                    'original_url': doc.url, 'resolved_url': doc.resolved_url, 'captured_at': doc.captured_at}
        return {'provider': self.provider, 'source_record_id': self.native,
                'parent': {'observation_id': self.parent, 'source_document_sha256': self.primary.sha256,
                           'native_identity': {'match_id': self.native, 'home_id': 779, 'away_id': 771}},
                'documents': {'events': binding(events), 'lineups': binding(lineups)},
                'parser_version': 'SYNTHETIC-foundation-parser/1',
                'projection': {'synthetic': True, 'retained_event_rows': event_rows, 'team_ids': [779, 771]}}

    def validate(self, db, payload):
        """Synthetic trusted callback verifies exact retained rows and raw bytes."""
        assert payload['provider'] == self.provider and payload['source_record_id'] == self.native
        parent = db.execute('SELECT provider,source_record_id,acquisition_id,record FROM connector_observations WHERE id=?',
                            (payload['parent']['observation_id'],)).fetchone()
        if parent is None or parent[0] != self.provider or parent[1] != self.native:
            raise ValueError('SYNTHETIC_PARENT_UNAVAILABLE')
        primary = db.execute('SELECT sha256,raw_reference,bytes FROM connector_acquisitions WHERE id=?', (parent[2],)).fetchone()
        if primary is None or primary[0] != payload['parent']['source_document_sha256']:
            raise ValueError('SYNTHETIC_PARENT_HASH_MISMATCH')
        parent_raw = self.raw / primary[1]
        if not parent_raw.is_file() or digest(parent_raw) != primary[0]:
            raise ValueError('SYNTHETIC_PARENT_RAW_UNAVAILABLE')
        original_parent = read(parent_raw)
        if original_parent != {'synthetic': True, 'match_id': self.native, 'home_id': 779, 'away_id': 771}:
            raise ValueError('SYNTHETIC_PARENT_IDENTITY_MISMATCH')
        if payload['parent']['native_identity'] != {'match_id': self.native, 'home_id': 779, 'away_id': 771}:
            raise ValueError('SYNTHETIC_PARENT_SNAPSHOT_MISMATCH')
        documents = {}
        for role, binding in payload['documents'].items():
            row = db.execute('SELECT id,provider,sha256,original_url,resolved_url,captured_at,raw_reference,bytes,http_status FROM connector_acquisitions WHERE id=?',
                             (binding['id'],)).fetchone()
            if row is None or dict(zip(('id', 'provider', 'sha256', 'original_url', 'resolved_url', 'captured_at'), row[:6])) != binding:
                raise ValueError('SYNTHETIC_ACQUISITION_BINDING_MISMATCH')
            path = self.raw / row[6]
            if row[1] != self.provider or row[8] != 200 or not path.is_file() or path.stat().st_size != row[7] or digest(path) != row[2]:
                raise ValueError('SYNTHETIC_RAW_UNAVAILABLE')
            documents[role] = read(path)
        expected = {'synthetic': True, 'retained_event_rows': documents['events']['event_rows'],
                    'team_ids': documents['lineups']['team_ids']}
        if payload['projection'] != expected:
            raise ValueError('SYNTHETIC_PROJECTION_MISMATCH')


class Acceptance:
    def __init__(self, args):
        self.args = args
        self.output = args.output.resolve()
        fresh = (self.output, args.state.resolve()) if args.reuse_migration_fixture else (
            self.output, args.state.resolve(), args.preparation.resolve(), args.sql.resolve())
        for path in fresh:
            assert path.is_relative_to(ROOT) and not path.exists(), 'Use fresh project-local acceptance paths.'
        self.output.parent.mkdir(parents=True, exist_ok=True)
        migration._directory(self.output)
        args.state.parent.mkdir(parents=True, exist_ok=True)
        self.checks = []
        self.network_attempts = 0
        self.report = {'schema_version': 1, 'passed': False, 'mode': 'synthetic_foundation_no_http',
                       'checks': self.checks, 'mariadb_executed': False, 'running_services_changed': False,
                       'source_files': {name: digest(ROOT / name) for name in (
                           'scripts/verify_context_foundation.py',
                           'src/dragonhydra/cognition/memory.py', 'src/dragonhydra/source_context.py',
                           'src/dragonhydra/migration.py', 'src/dragonhydra/mariadb_migration.py',
                           'tests/installation/mariadb_roundtrip.php', 'scripts/verify_mariadb_migration.py')}}

    def check(self, name, **details):
        self.checks.append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name}), flush=True)

    def no_network(self, *args, **kwargs):
        self.network_attempts += 1
        raise AssertionError('Acceptance permits no provider or database network access.')

    def append(self, fixture, draft):
        return source_context.append(fixture.db_path, draft, validate_dependencies=fixture.validate)

    def latest(self, fixture, **kwargs):
        return source_context.latest(fixture.db_path, fixture.provider, fixture.native,
                                     validate_dependencies=fixture.validate, **kwargs)

    def case(self, name):
        cases = self.output / 'cases'
        cases.mkdir(exist_ok=True)
        return Fixture(cases / name)

    @staticmethod
    def refused(operation):
        try:
            operation()
        except (ValueError, sqlite3.DatabaseError, migration.MigrationError, mariadb_migration.MariaDBMigrationError) as error:
            return getattr(error, 'code', str(error))
        raise AssertionError('Invalid operation was unexpectedly accepted.')

    def legacy(self):
        baseline = read(ROOT / 'build/connections/context-foundation-20261031/legacy-baseline.json')
        for path, expected in baseline['files'].items():
            actual = ROOT / path
            assert actual.stat().st_size == expected['bytes'] and digest(actual) == expected['sha256']
        prepared = migration.validate_bundle(ROOT / baseline['legacy_preparation']['bundle'])
        sql = mariadb_migration.validate_script(ROOT / baseline['legacy_sql']['output'])
        assert prepared['table_count'] == sql['table_count'] == 16 and sql['trigger_count'] == 10
        assert sql['sql_sha256'] == baseline['legacy_sql']['sql_sha256'] and not sql['cutover']
        self.report['legacy'] = {'preparation': prepared, 'sql': sql, 'historical_five_files_byte_identical': True}
        self.check('Historical sixteen-table preparation and SQL validate without rewriting; regenerated SQL/statements hashes retained')

    def run(self):
        try:
            with patch.object(socket.socket, 'connect', self.no_network), patch.object(socket.socket, 'connect_ex', self.no_network):
                self.legacy()
                fixture = Fixture(self.args.state.resolve())
                baseline = sql_state(fixture.db_path)
                assert self.latest(fixture) == {'availability': 'not_requested', 'item': None}
                assert sql_state(fixture.db_path) == baseline
                missing = self.output / 'absent.sqlite3'
                assert source_context.latest(missing, fixture.provider, fixture.native,
                                             validate_dependencies=fixture.validate)['availability'] == 'not_requested'
                assert not missing.exists()
                self.check('Missing context uses SELECT only and does not initialize optional tables or a missing database')

                first_draft = fixture.draft(2)
                first = self.append(fixture, first_draft)
                first_item = self.latest(fixture)['item']
                assert first_item['revision'] == 1 and first_item['supersedes_record_id'] is None
                first_rows = sql_state(fixture.db_path)['tables']['cognitive_records']
                duplicate = self.append(fixture, fixture.draft(2))
                assert duplicate['duplicate'] and duplicate['record_id'] == first['record_id']
                assert self.latest(fixture)['item']['documents'] == first_item['documents']
                assert sql_state(fixture.db_path)['tables']['cognitive_records'] == first_rows
                correction = self.append(fixture, fixture.draft(3))
                reversal = self.append(fixture, fixture.draft(2))
                head = self.latest(fixture)['item']
                assert head['revision'] == 3 and head['supersedes_record_id'] == correction['record_id']
                assert len({first['record_id'], correction['record_id'], reversal['record_id']}) == 3
                assert head['documents']['events']['sha256'] == first_item['documents']['events']['sha256']
                assert head['documents']['events']['id'] != first_item['documents']['events']['id']
                assert self.latest(fixture, cutoff=first['usable_at'])['item']['record_id'] == first['record_id']
                assert self.latest(fixture, parent_observation_id='SYNTHETIC-new-parent')['availability'] == 'parent_changed'
                assert sql_state(fixture.db_path)['tables']['connector_observations'] == baseline['tables']['connector_observations']
                self.report['revision_records'] = [first, correction, reversal]
                self.check('Duplicate bytes keep original bindings; correction and A-to-B-to-A produce ordered immutable revisions without base-match changes')

                real_connect, statements = sqlite3.connect, []
                def traced_connect(*args, **kwargs):
                    db = real_connect(*args, **kwargs)
                    db.set_trace_callback(statements.append)
                    return db
                before_read = sql_state(fixture.db_path)
                with patch.object(sqlite3, 'connect', traced_connect):
                    assert self.latest(fixture)['availability'] == 'available'
                assert before_read == sql_state(fixture.db_path)
                assert statements and all(statement.lstrip().upper().startswith(('SELECT', 'BEGIN', 'PRAGMA QUERY_ONLY')) for statement in statements)
                self.check('Available context lookup is pure SELECT on read-only SQLite; no DDL, writes, HTTP or repair', traced_statements=len(statements))

                rejected = self.case('rejected-callbacks')
                draft = rejected.draft()
                false_code = self.refused(lambda: source_context.append(rejected.db_path, draft, validate_dependencies=lambda db, value: False))
                def mutate(db, value):
                    value['projection']['mutated'] = True
                mutation_code = self.refused(lambda: source_context.append(rejected.db_path, draft, validate_dependencies=mutate))
                def write(db, value):
                    db.execute("INSERT INTO connector_settings(provider) VALUES('SYNTHETIC-invalid-callback-write')")
                sql_code = self.refused(lambda: source_context.append(rejected.db_path, draft, validate_dependencies=write))
                assert sql_state(rejected.db_path)['tables']['cognitive_records']['rows'] == 0
                self.check('Boolean rejection, Python payload mutation and SQLite-writing callbacks fail closed without records',
                           false_code=false_code, mutation_code=mutation_code, sql_code=sql_code)

                crash = self.case('durable-pending-recovery')
                pending_draft = crash.draft()
                with patch.object(memory, '_revision_receipt', side_effect=RuntimeError('SYNTHETIC_AFTER_RECORD_COMMIT')):
                    try:
                        self.append(crash, pending_draft)
                    except RuntimeError as error:
                        assert str(error) == 'SYNTHETIC_AFTER_RECORD_COMMIT'
                    else:
                        raise AssertionError('Crash injection did not execute.')
                pending = sql_state(crash.db_path)['tables']
                assert pending['cognitive_records']['rows'] == 1 and pending['cognitive_receipts']['rows'] == 0
                assert self.latest(crash)['availability'] == 'unavailable'
                path = crash.raw / (pending_draft['documents']['events']['sha256'] + '.payload')
                original = path.read_bytes()
                path.write_bytes(b'SYNTHETIC corrupt dependency')
                bad_recovery = self.refused(lambda: source_context.recover(crash.db_path, crash.provider, crash.native,
                                                                          validate_dependencies=crash.validate))
                assert sql_state(crash.db_path)['tables']['cognitive_receipts']['rows'] == 0
                # New incoming bytes cannot move past an invalid durable head.
                blocked = self.refused(lambda: self.append(crash, crash.draft(4)))
                assert sql_state(crash.db_path)['tables']['cognitive_records']['rows'] == 1
                path.write_bytes(original)
                recovery_started = utc_now()
                recovered = source_context.recover(crash.db_path, crash.provider, crash.native, validate_dependencies=crash.validate)
                assert recovered['recovered'] and recovered['persisted_at'] >= recovery_started
                assert sql_state(crash.db_path)['tables']['cognitive_records'] == pending['cognitive_records']
                assert self.latest(crash)['item']['record_id'] == recovered['record_id']
                assert self.latest(crash, cutoff=recovery_started)['availability'] == 'not_requested'
                self.report['recovery'] = {'receipt': recovered, 'bad_raw_code': bad_recovery, 'blocked_new_revision_code': blocked}
                self.check('Crash leaves an invisible pending record; corrupt dependencies block recovery and advancement; verified recovery preserves record ID with current receipt clocks')

                rollback = self.case('clock-rollback')
                draft_a, draft_b = rollback.draft(2), rollback.draft(3)
                base = datetime.now(timezone.utc) + timedelta(seconds=30)
                def clock(offset):
                    return (base + timedelta(seconds=offset)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
                with patch.object(memory, '_now', return_value=clock(0)):
                    earlier = self.append(rollback, draft_a)
                with patch.object(memory, '_now', return_value=clock(-5)):
                    code = self.refused(lambda: self.append(rollback, draft_b))
                assert code == 'CLOCK_MOVED_BACKWARDS'
                rows = sql_state(rollback.db_path)['tables']
                assert rows['cognitive_records']['rows'] == 2 and rows['cognitive_receipts']['rows'] == 1
                assert self.latest(rollback)['availability'] == 'unavailable'
                # Construct an isolated corrupt copy: each row's own clocks
                # are ordered, but revision two's usable clock precedes one.
                corrupt = self.output / 'nonmonotonic-chain.sqlite3'
                with closing(rollback.product.connect()) as original_db, closing(sqlite3.connect(corrupt)) as clone:
                    original_db.backup(clone)
                    record_id = clone.execute('SELECT record_id FROM cognitive_records WHERE record_id NOT IN (SELECT record_id FROM cognitive_receipts)').fetchone()[0]
                    clone.execute('INSERT INTO cognitive_receipts VALUES(?,?,?,?)', (record_id, clock(-5), clock(-5), clock(-5)))
                    clone.commit()
                rejected_chain = source_context.latest(corrupt, rollback.provider, rollback.native, validate_dependencies=rollback.validate)
                assert rejected_chain['availability'] == 'unavailable' and rejected_chain['code'] == 'MEMORY_RECEIPT_CLOCK_INVALID'
                with patch.object(memory, '_now', return_value=clock(5)):
                    later = source_context.recover(rollback.db_path, rollback.provider, rollback.native, validate_dependencies=rollback.validate)
                assert later['record_id'] == record_id and later['usable_at'] >= earlier['usable_at']
                assert self.latest(rollback, cutoff=clock(0))['item']['record_id'] == earlier['record_id']
                self.report['synthetic_clock_rollback'] = {'clocks_are_simulated': True, 'receipt_refusal': code,
                                                           'corrupt_chain_refusal': rejected_chain['code'],
                                                           'earlier_record': earlier, 'recovered_record': later,
                                                           'earlier_cutoff_preserved': True}
                self.check('Backward clock cannot publish a revision before its predecessor; later recovery preserves the earlier cutoff, and a forged nonmonotonic chain fails closed')

                racing = self.case('competing-writers')
                drafts = [racing.draft(), racing.draft()]
                barrier = threading.Barrier(2)
                def competing(draft):
                    barrier.wait(timeout=10)
                    return self.append(racing, draft)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    receipts = list(pool.map(competing, drafts))
                assert len({receipt['record_id'] for receipt in receipts}) == 1
                state = sql_state(racing.db_path)['tables']
                assert state['cognitive_records']['rows'] == state['cognitive_receipts']['rows'] == 1
                drafts = [racing.draft(5), racing.draft(6)]
                barrier = threading.Barrier(2)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    differing = list(pool.map(competing, drafts))
                state = sql_state(racing.db_path)['tables']
                assert state['cognitive_records']['rows'] == state['cognitive_receipts']['rows'] == 3
                assert self.latest(racing)['item']['revision'] == 3
                self.report['concurrency'] = {'same_content_receipts': receipts, 'different_content_receipts': differing}
                self.check('Competing same-content and different-content writers serialize idempotency, revision allocation, predecessor chain and receipts')

                race = self.case('receipt-recovery-race')
                delayed, release = threading.Event(), threading.Event()
                real_receipt = memory._revision_receipt
                def delayed_receipt(db, kind, scope, record_id, acknowledged, validate):
                    if threading.current_thread().name.startswith('first-writer'):
                        delayed.set()
                        assert release.wait(15)
                    return real_receipt(db, kind, scope, record_id, acknowledged, validate)
                draft = race.draft()
                with patch.object(memory, '_revision_receipt', delayed_receipt), ThreadPoolExecutor(max_workers=1, thread_name_prefix='first-writer') as pool:
                    future = pool.submit(self.append, race, draft)
                    try:
                        assert delayed.wait(10)
                        recovered = source_context.recover(race.db_path, race.provider, race.native, validate_dependencies=race.validate)
                    finally:
                        release.set()
                    first_result = future.result(timeout=15)
                assert first_result['record_id'] == recovered['record_id']
                assert first_result['usable_at'] == recovered['usable_at']
                assert sql_state(race.db_path)['tables']['cognitive_receipts']['rows'] == 1
                self.check('Another writer can receipt the committed head before its original writer; both return the same immutable receipt')

                isolation = self.case('unknown-kind-isolation')
                self.append(isolation, isolation.draft())
                with closing(isolation.product.connect()) as db:
                    db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)', ('SYNTHETIC_unknown_kind', 'unknown-id', 'unknown-key', 'unused', '{'))
                    clock = utc_now()
                    db.execute('INSERT INTO cognitive_receipts VALUES(?,?,?,?)', ('unknown-id', clock, clock, clock))
                    db.commit()
                    cognitive = memory._as_of(db, utc_now())
                assert set(cognitive) == {'models', 'predictions', 'outcomes', 'research_tasks', 'evaluations', 'hypotheses'}
                assert not any(cognitive.values())
                self.check('Existing six-kind cognition reader excludes source-context and unknown kinds before decoding their payloads')

                for case in ('partial-profile', 'altered-profile'):
                    invalid = self.case(case)
                    with closing(invalid.product.connect()) as db:
                        memory._schema(db)
                        if case == 'partial-profile':
                            db.execute('DROP TABLE cognitive_receipts')
                        else:
                            db.execute("CREATE TRIGGER SYNTHETIC_extra BEFORE INSERT ON cognitive_records BEGIN SELECT RAISE(ABORT,'extra'); END")
                        db.commit()
                    code = self.refused(lambda: migration.prepare(invalid.db_path, self.output / (case + '-prepared')))
                    self.report.setdefault('rejected_profiles', {})[case] = code
                self.check('Partial cognition profile and unaudited trigger extensions cannot produce an accepted preparation')

                preserved = {}
                if self.args.reuse_migration_fixture:
                    for directory in (self.args.preparation, self.args.sql):
                        for path in directory.rglob('*'):
                            if path.is_file():
                                preserved[str(path.resolve())] = digest(path)
                    prepared = migration.validate_bundle(self.args.preparation.resolve())
                    generated = mariadb_migration.validate_script(self.args.sql.resolve())
                else:
                    prepared = migration.prepare(fixture.db_path, self.args.preparation.resolve())
                    generated = mariadb_migration.build_script(self.args.preparation.resolve(), self.args.sql.resolve(),
                                                               'dragonhydra_migration_context_foundation_20261031')
                prep_manifest = read(self.args.preparation / 'manifest.json')
                sql_manifest = read(self.args.sql / 'manifest.json')
                assert prepared['table_count'] == generated['table_count'] == 18
                assert prep_manifest['bundle_version'] == 'dragonhydra-sqlite-preparation/2'
                assert sql_manifest['format_version'] == 'dragonhydra-mariadb-staging/2'
                assert prep_manifest['schema_profile'] == sql_manifest['schema_profile'] == 'core-context-1'
                assert generated['trigger_count'] == 14 and not generated['cutover'] and not generated['executed']
                mapping = {table['name']: table for table in sql_manifest['mapping']['tables']}
                records = mapping['cognitive_records']
                capacities = {column['name']: column['target_type'] for column in records['columns']}
                assert capacities['kind'] == 'VARBINARY(64)' and capacities['record_id'] == 'VARBINARY(128)' and capacities['natural_key'] == 'VARBINARY(64)'
                assert all(audit['with_primary_key_bytes'] <= 3072 and not audit['prefix_lengths_used'] for audit in records['key_audit'])
                assert mapping['cognitive_receipts']['foreign_keys'][0]['parent_table'] == 'cognitive_records'
                assert mariadb_migration.validate_script(self.args.sql)['valid']
                source_state = ROOT / prep_manifest['source']['path']
                with closing(sqlite3.connect(source_state.as_uri() + '?mode=ro', uri=True)) as source_db:
                    source_context._structure(json.loads(source_db.execute("SELECT payload FROM cognitive_records WHERE kind='source_context' LIMIT 1").fetchone()[0]))
                self.report['context_migration'] = {'source_state': str(source_state.parent.relative_to(ROOT)),
                                                    'fresh_semantic_test_state': str(fixture.state.relative_to(ROOT)),
                                                    'existing_migration_fixture_reused': bool(self.args.reuse_migration_fixture),
                                                    'preparation': prepared, 'sql': generated,
                                                    'source_tables': sql_state(source_state)['tables']}
                self.check('Persistent synthetic eighteen-table profile exports exact optional schema, fourteen triggers, bounded identity keys and receipt foreign key; offline SQL revalidates')
                php_command = [r'C:\xampp\php\php.exe', str(ROOT / 'tests/installation/mariadb_roundtrip.php'), '--validate-only',
                               '--bundle', str(self.args.sql.resolve()), '--schema', sql_manifest['schema'],
                               '--reviewed-manifest-sha256', digest(self.args.sql / 'manifest.json')]
                php = subprocess.run(php_command, capture_output=True, text=True, timeout=20)
                assert php.returncode == 0 and json.loads(php.stdout)['passed'] and not json.loads(php.stdout)['schema_created']
                self.report['php_offline_validation'] = {'command': php_command, 'exit_code': php.returncode,
                                                         'stdout': json.loads(php.stdout), 'stderr': php.stderr,
                                                         'database_apply_requested': False}
                assert all(digest(Path(path)) == sha for path, sha in preserved.items())
                self.check('Actual existing PHP validates the eighteen-table statement plan without database apply; all reused preparation and SQL artifact bytes remain identical')
                self.legacy()
                assert self.network_attempts == 0
                assert all(digest(ROOT / name) == sha for name, sha in self.report['source_files'].items()), 'Source changed during independent acceptance.'
                self.report['passed'] = True
        except Exception as error:
            self.report['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
        finally:
            self.report.update(finished_at=datetime.now(timezone.utc).isoformat(), network_attempts=self.network_attempts,
                               check_groups=len(self.checks))
            (self.output / 'verification.json').write_text(json.dumps(self.report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': self.report['passed'], 'groups': len(self.checks), 'network_attempts': self.network_attempts,
                          'error': self.report.get('error', {}).get('message'), 'report': str((self.output / 'verification.json').relative_to(ROOT))}))
        return 0 if self.report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--preparation', type=Path, required=True)
    parser.add_argument('--sql', type=Path, required=True)
    parser.add_argument('--reuse-migration-fixture', action='store_true', help='Revalidate existing reviewed preparation/SQL bytes rather than regenerate them')
    args = parser.parse_args()
    assert not sys.flags.optimize
    return Acceptance(args).run()


if __name__ == '__main__':
    raise SystemExit(main())
