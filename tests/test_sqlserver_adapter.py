"""SQL adapter guards with in-memory driver doubles only; never connects to SQL."""
import copy
from decimal import Decimal
import hashlib
import importlib
import json
from unittest import TestCase, main
from unittest.mock import Mock, patch

from dragonhydra.research_storage.base import StorageError, canonical
from dragonhydra.research_storage import sqlserver as sql


STAMP = '2026-11-04T10:00:00.1234567Z'
MATCH = 'a' * 64
ARCHIVE = 'b' * 64
NOTE = 'd030fa58-50d1-4cfa-8f6c-f2a69efe4df9'


def bundle():
    model_id, prediction_id = 'model:' + 'c' * 64, 'prediction:' + 'd' * 64
    probabilities = {'home': '0.40000000000000001', 'draw': '0.29999999999999999', 'away': '0.3'}
    return {'schema_version': 'dragonhydra.research-archive/1', 'archive_id': ARCHIVE, 'match_id': MATCH,
        'forecast_run_id': 'own-run', 'match': {'id': MATCH, 'home': {'id': 'e' * 64, 'name': 'Équipe 🐉'},
            'away': {'id': 'f' * 64, 'name': 'Bournemouth'}, 'competition': 'League',
            'event_date': '2027-05-30', 'source_id': 'retained-source'},
        'models': [{'record_id': model_id, 'model_name': 'frequency', 'model_version': 'football-models/1',
            'data_cutoff': STAMP, 'parameters': {'result': {'probabilities': {
                k: {'value': v} for k, v in probabilities.items()}}}}],
        'predictions': [{'record_id': prediction_id, 'model_run_id': model_id, 'run_id': 'own-run',
            'probabilities': probabilities, 'decision_cutoff': STAMP, 'predicted_at': STAMP}],
        'input_manifest': [{'evidence_id': '1' * 64, 'source_id': 'retained-source',
            'source_hash': '2' * 64, 'usable_at': STAMP, 'data_origin': 'imported_historical'}],
        'evaluation_status': 'pending', 'source_build': {'source_sha': '3' * 40}}


class Rows:
    def __init__(self, rows=()): self.rows = list(rows)
    def fetchone(self): return self.rows[0] if self.rows else None
    def __iter__(self): return iter(self.rows)


class Connection:
    def __init__(self, handler=None, commit_error=None, rollback_error=None):
        self.handler, self.commit_error, self.rollback_error = handler, commit_error, rollback_error
        self.calls, self.commits, self.rollbacks, self.closed = [], 0, 0, 0
    def execute(self, statement, *parameters):
        self.calls.append((statement, parameters))
        return Rows(self.handler(statement, parameters) if self.handler else ())
    def commit(self):
        self.commits += 1
        if self.commit_error: raise self.commit_error
    def rollback(self):
        self.rollbacks += 1
        if self.rollback_error: raise self.rollback_error
    def close(self): self.closed += 1


def repository(connection=None, owned=True):
    repo = sql.Repo(sql.SQLServerConfig.from_dict({}), 'profile-a')
    if connection is not None: repo._connect = Mock(return_value=connection)
    if owned: repo._owned = Mock()
    return repo


def ownership_handler(repo, *, owner=True, missing_trigger=False, checksum=None):
    def handle(statement, parameters):
        if 'OBJECT_ID' in statement: return [(1 if owner else None,)]
        if 'SELECT product_id' in statement: return [(sql.PRODUCT, 1, checksum or repo._schema_hash())]
        if 'FROM sys.objects' in statement:
            rows = [('dh_research_' + n, 'U') for n in sql.TABLES]
            rows += [('dh_research_' + n, 'TR') for n in sql.TRIGGERS if not(missing_trigger and n == 'archives_immutable')]
            return rows
        if 'SELECT checksum' in statement: return [(repo._schema_hash(),)]
        if 'COUNT_BIG' in statement: return [(0,)]
        if 'SELECT SUSER_SNAME()' in statement:
            return [('NT AUTHORITY\\LOCAL SERVICE', 'NT SERVICE\\SyntheticCandidate',
                     'DRAGONHYDRA_CORE_NEXT_SQL_LAB', 'Shared memory', 'NTLM')]
        return []
    return handle


class SQLConfigurationTests(TestCase):
    def test_default_is_encrypted_integrated_and_does_not_trust_certificate(self):
        config = sql.SQLServerConfig.from_dict({})
        connection_string = config._connection_string(config.database)
        self.assertIn('Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=no;', connection_string)
        self.assertNotIn('PWD=', connection_string)
        self.assertNotIn('SERVER=', repr(config))

    def test_shared_memory_and_explicit_trust_are_supported(self):
        config = sql.SQLServerConfig.from_dict({'server': 'lpc:TEST-HOST', 'trust_server_certificate': True})
        self.assertIn('SERVER=lpc:TEST-HOST;', config._connection_string(config.database))
        self.assertIn('TrustServerCertificate=yes;', config._connection_string(config.database))

    def test_invalid_authentication_delimiters_system_databases_and_types_are_rejected(self):
        cases = [{'password': 'FAKE_CANARY'}, {'authentication': 'sql'}, {'encrypt': False}, {'encrypt': 'yes'},
            {'trust_server_certificate': 'true'}, {'server': 'localhost;PWD=FAKE_CANARY'}, {'server': '{localhost}'},
            {'server': 'localhost,70000'}, {'database': 'master'}, {'database': 'x] DROP DATABASE y'},
            {'driver': 'ODBC Driver 17 for SQL Server'}, {'connection_timeout_seconds': True},
            {'connection_timeout_seconds': 0}, {'connection_timeout_seconds': 16}, {'query_timeout_seconds': 31}]
        for value in cases:
            with self.subTest(fields=list(value)), self.assertRaises(StorageError): sql.SQLServerConfig.from_dict(value)

    def test_direct_config_construction_cannot_bypass_validation(self):
        with self.assertRaises(StorageError): sql.Repo(sql.SQLServerConfig(encrypt=False), 'profile-a')
        with self.assertRaises(StorageError): sql.Repo({}, 'profile;OTHER=secret')

    def test_constructing_repo_does_not_import_driver_or_connect(self):
        with patch.object(importlib, 'import_module') as loader:
            sql.Repo({}, 'profile-a')
        loader.assert_not_called()

    def test_driver_import_failure_is_optional_and_sanitized(self):
        repo = sql.Repo({}, 'profile-a')
        with patch.object(importlib, 'import_module', side_effect=ImportError('FAKE_CANARY')):
            with self.assertRaises(StorageError) as caught: repo._connect()
        self.assertEqual(caught.exception.code, 'SQLSERVER_DRIVER_UNAVAILABLE')
        self.assertNotIn('FAKE_CANARY', str(caught.exception))

    def test_actual_connection_uses_bounded_login_and_query_timeouts(self):
        connection = Connection()
        driver = Mock(); driver.connect.return_value = connection
        repo = sql.Repo({}, 'profile-a')
        with patch.object(importlib, 'import_module', return_value=driver):
            self.assertIs(repo._connect(), connection)
        self.assertEqual(driver.connect.call_args.kwargs, {'timeout': 5, 'autocommit': False})
        self.assertEqual(connection.timeout, 10)
        self.assertIn('LOCK_TIMEOUT 3000', connection.calls[0][0])


class ProjectionTests(TestCase):
    def test_projection_preserves_original_json_and_unicode_names(self):
        original = bundle(); snapshot = copy.deepcopy(original)
        projected, raw, names, event, models, predictions, inputs = sql.Repo._projection(original)
        self.assertEqual(original, snapshot); self.assertEqual(raw, canonical(snapshot)); self.assertIs(projected, original)
        self.assertEqual(names, ['Équipe 🐉', 'Bournemouth']); self.assertEqual(event, '2027-05-30')
        self.assertEqual(models[0][0], snapshot['models'][0]['record_id'])
        self.assertEqual(json.loads(predictions[0][-1]), snapshot['predictions'][0])
        self.assertEqual(inputs[0][3], bytes.fromhex('2' * 64))

    def test_decimal_conversion_is_exact_and_never_uses_float(self):
        for value in ['0.40000000000000001', '1e-28', '0', '1']:
            self.assertEqual(Decimal(sql._probability(value)), Decimal(value))
        for value in ['1e-29', 'NaN', 'Infinity', '-0.1', '1.1', 0.3, True]:
            with self.subTest(type=type(value).__name__), self.assertRaises(StorageError): sql._probability(value)

    def test_utc_seventh_fractional_digit_is_not_truncated(self):
        self.assertEqual(sql._timestamp(STAMP), '2026-11-04T10:00:00.1234567')
        self.assertEqual(sql._timestamp(STAMP[:-1] + '+00:00'), '2026-11-04T10:00:00.1234567')
        for bad in ['2026-11-04T10:00:00', '2026-11-04T10:00:00+01:00',
                    '2026-11-04T10:00:00.12345678Z', '2026-02-30T10:00:00Z']:
            with self.assertRaises(StorageError): sql._timestamp(bad)

    def test_team_names_must_use_actual_present_dictionary_shape(self):
        value = bundle(); value['match']['home'] = 'unexpected flat shape'
        with self.assertRaises(StorageError): sql.Repo._projection(value)

    def test_synthetic_or_unidentified_inputs_cannot_be_stored_as_real(self):
        for origin in ['synthetic', 'model_state', None]:
            value = bundle(); value['input_manifest'][0]['data_origin'] = origin
            with self.assertRaises(StorageError): sql.Repo._projection(value)

    def test_note_size_accounts_for_utf16_and_uuid_is_canonical(self):
        with self.assertRaises(StorageError): sql._text('🐉' * 2001, 4000, 'INVALID')
        self.assertEqual(sql._uuid(NOTE), NOTE)
        for value in ['bad', NOTE.upper(), '{' + NOTE + '}']:
            with self.assertRaises(StorageError): sql._uuid(value)


class OwnershipAndTransactions(TestCase):
    def test_existing_unowned_database_cannot_be_initialized(self):
        master = Connection(lambda *_: [(7,)])
        target = Connection(lambda *_: [(None,)])
        repo = repository(owned=False); repo._connect = Mock(side_effect=[master, target])
        with self.assertRaises(StorageError) as caught: repo.initialize()
        self.assertEqual(caught.exception.code, 'SQLSERVER_DATABASE_NOT_OWNED')
        self.assertFalse(any('CREATE ' in query for connection in [master, target] for query, _ in connection.calls))
        self.assertEqual(target.commits, 0)

    def test_existing_owned_database_verification_is_idempotent_and_has_no_ddl(self):
        master = Connection(lambda *_: [(7,)])
        repo = repository(owned=False); target = Connection(ownership_handler(repo))
        repo._connect = Mock(side_effect=[master, target]); result = repo.initialize()
        self.assertFalse(result['created_database']); self.assertTrue(result['initialized'])
        self.assertEqual(target.commits, 0)
        self.assertFalse(any('CREATE ' in statement or 'INSERT ' in statement for statement, _ in target.calls))

    def test_new_database_initialization_records_exact_migration_checksum_once(self):
        master = Connection(lambda *_: [(None,)])
        target = Connection(lambda statement, _: [(0,)] if 'COUNT(*)' in statement else [])
        repo = repository(); repo._connect = Mock(side_effect=[master, target]); result = repo.initialize()
        self.assertTrue(result['created_database']); self.assertEqual(target.commits, 1)
        self.assertEqual(sum('CREATE DATABASE' in statement for statement, _ in master.calls), 1)
        insertions = [(s, p) for s, p in target.calls if s.startswith('INSERT INTO dbo.dh_research_')]
        self.assertEqual(len(insertions), 2)
        self.assertIn(repo._schema_hash(), insertions[0][1]); self.assertIn(repo._schema_hash(), insertions[1][1])

    def test_health_is_read_only_owned_scoped_and_not_a_tls_certificate_claim(self):
        repo = repository(owned=False); connection = Connection(ownership_handler(repo)); repo._connect = Mock(return_value=connection)
        result = repo.health(); self.assertTrue(result['ready']); self.assertTrue(result['connected'])
        self.assertFalse(result['trust_server_certificate']); self.assertIn('not inferred', result['encryption_scope'])
        self.assertEqual(connection.commits, 0); self.assertEqual(connection.rollbacks, 1)
        self.assertTrue(all(s.startswith('SELECT') for s, _ in connection.calls))
        self.assertTrue(all(p == ('profile-a',) for s, p in connection.calls if 'COUNT_BIG' in s))
        self.assertIn('is_disabled=0', next(s for s, _ in connection.calls if 'sys.objects' in s))
        self.assertEqual(result['connection_identity']['login'], 'NT AUTHORITY\\LOCAL SERVICE')
        self.assertEqual(result['connection_identity']['database_user'], 'NT SERVICE\\SyntheticCandidate')
        self.assertEqual(result['connection_identity']['auth_scheme'], 'NTLM')
        self.assertFalse(any('sys.dm_' in s for s, _ in connection.calls))

    def test_connection_identity_is_actual_bounded_metadata_not_inferred_from_configuration(self):
        for identity in [None, ('user', 'dbo', 'database', 'Shared memory', 'SQL'),
                         ('FAKE_CANARY\nunsafe', 'dbo', 'database', 'Shared memory', 'NTLM')]:
            repo = repository(owned=False)
            normal = ownership_handler(repo)
            def handle(statement, parameters):
                if 'SELECT SUSER_SNAME()' in statement:
                    return [] if identity is None else [identity]
                return normal(statement, parameters)
            repo._connect = Mock(return_value=Connection(handle))
            result = repo.health()
            self.assertFalse(result['ready'])
            self.assertNotIn('connection_identity', result)
            self.assertNotIn('FAKE_CANARY', json.dumps(result))

    def test_missing_trigger_or_foreign_migration_fails_closed_without_ddl(self):
        for options in [{'missing_trigger': True}, {'checksum': bytes(32)}, {'owner': False}]:
            repo = repository(owned=False); connection = Connection(ownership_handler(repo, **options)); repo._connect = Mock(return_value=connection)
            result = repo.health(); self.assertFalse(result['ready']); self.assertTrue(result['connected'])
            self.assertFalse(any('CREATE ' in statement for statement, _ in connection.calls))

    def test_commit_and_rollback_are_real_explicit_driver_operations(self):
        connection = Connection(); repo = repository(connection)
        with repo.transaction() as actual: self.assertIs(actual, connection)
        self.assertEqual((connection.commits, connection.rollbacks, connection.closed), (1, 0, 1))
        connection = Connection(); repo = repository(connection)
        with self.assertRaises(StorageError):
            with repo.transaction(): raise StorageError('SYNTHETIC_ROLLBACK')
        self.assertEqual((connection.commits, connection.rollbacks, connection.closed), (0, 1, 1))

    def test_uncertain_commit_is_sanitized_and_never_retried(self):
        connection = Connection(commit_error=RuntimeError('08007', 'FAKE_CANARY private diagnostic'))
        repo = repository(connection)
        with self.assertRaises(StorageError) as caught:
            with repo.transaction(): pass
        self.assertTrue(caught.exception.uncertain_write); self.assertEqual(caught.exception.sqlstate, '08007')
        self.assertNotIn('FAKE_CANARY', str(caught.exception)); repo._connect.assert_called_once()
        self.assertEqual(connection.commits, 1)

    def test_uncertain_rollback_does_not_claim_known_failure(self):
        repo = repository(Connection(rollback_error=RuntimeError('08006', 'FAKE_CANARY')))
        with self.assertRaises(StorageError) as caught:
            with repo.transaction(): raise StorageError('SYNTHETIC_BODY_FAILURE')
        self.assertTrue(caught.exception.uncertain_write)

    def test_driver_read_failure_does_not_expose_raw_diagnostic(self):
        repo = repository(); repo._connect = Mock(side_effect=StorageError('SQLSERVER_CONNECTION_FAILED', sqlstate='08001'))
        result = repo.health(); self.assertFalse(result['connected']); self.assertFalse(result['ready'])
        self.assertEqual(result['sqlstate'], '08001'); self.assertEqual(result['last_error'], 'SQLSERVER_CONNECTION_FAILED')


class ArchiveOperations(TestCase):
    def test_save_binds_all_rows_and_exact_probabilities_in_one_transaction(self):
        value = bundle(); projected = []
        def handle(statement, parameters):
            if statement.startswith('INSERT INTO dbo.dh_research_predictions'):
                projected.append((parameters[2], *(Decimal(v) for v in parameters[4:7])))
            if statement.startswith('SELECT record_id,home_probability'): return projected
            if statement.startswith('SELECT CONVERT'): return [(STAMP,)]
            return []
        connection = Connection(handle); repo = repository(connection); result = repo.save(value)
        self.assertFalse(result['duplicate']); self.assertEqual(result['payload_sha256'], hashlib.sha256(canonical(value)).hexdigest())
        self.assertEqual(connection.commits, 1); self.assertEqual(connection.rollbacks, 0)
        archive = next(p for s, p in connection.calls if s.startswith('INSERT INTO dbo.dh_research_archives'))
        self.assertEqual(archive[9], canonical(value).decode('utf-8')); self.assertEqual(archive[4], 'Équipe 🐉')
        self.assertTrue(all(p[:2] == ('profile-a', ARCHIVE) for s, p in connection.calls if s.startswith('INSERT INTO dbo.dh_research_')))

    def test_probability_roundtrip_failure_rolls_back_entire_publication(self):
        value = bundle()
        def handle(statement, parameters):
            if statement.startswith('SELECT record_id,home_probability'):
                return [(value['predictions'][0]['record_id'], Decimal('.5'), Decimal('.2'), Decimal('.3'))]
            return []
        connection = Connection(handle); repo = repository(connection)
        with self.assertRaises(StorageError) as caught: repo.save(value)
        self.assertEqual(caught.exception.code, 'SQLSERVER_PROBABILITY_ROUNDTRIP_FAILED')
        self.assertEqual((connection.commits, connection.rollbacks), (0, 1))

    def test_same_archive_id_requires_exact_payload_hash_and_keeps_original_receipt(self):
        value = bundle(); expected = hashlib.sha256(canonical(value)).digest()
        connection = Connection(lambda *_: [(expected, STAMP)]); repo = repository(connection)
        result = repo.save(value); self.assertTrue(result['duplicate']); self.assertEqual(result['persisted_at'], STAMP)
        self.assertFalse(any(s.startswith('INSERT') for s, _ in connection.calls))
        changed = copy.deepcopy(value); changed['evaluation_status'] = 'available'
        with self.assertRaises(StorageError) as caught: repo.save(changed)
        self.assertEqual(caught.exception.code, 'SQLSERVER_ARCHIVE_IDEMPOTENCY_CONFLICT')

    def test_reads_bind_scope_and_verify_canonical_payload_content_hash(self):
        value = bundle(); raw = canonical(value); row = (ARCHIVE, raw.decode('utf-8'), hashlib.sha256(raw).digest(), STAMP)
        connection = Connection(lambda statement, p: [row] if p[0] == 'profile-a' else [])
        repo = repository(connection); self.assertEqual(repo.get(ARCHIVE)['archive'], value)
        self.assertEqual(connection.calls[0][1], ('profile-a', ARCHIVE)); self.assertEqual(connection.commits, 0)
        self.assertIsNone(repository(Connection()).get(ARCHIVE))
        bad = (ARCHIVE, row[1], bytes(32), STAMP)
        with self.assertRaises(StorageError): repository(Connection(lambda *_: [bad])).get(ARCHIVE)

    def test_history_limit_is_bounded_and_parameterized(self):
        connection = Connection(); repo = repository(connection)
        self.assertEqual(repo.history(MATCH, 2), [])
        self.assertEqual(connection.calls[0][1], (2, 'profile-a', MATCH))
        self.assertIn('TOP (?)', connection.calls[0][0])
        for limit in [0, 101, True, '2']:
            with self.assertRaises(StorageError): repo.history(MATCH, limit)

    def test_note_stale_revision_has_no_update(self):
        row = (NOTE, MATCH, 'old', 2, STAMP, STAMP)
        connection = Connection(lambda *_: [row]); repo = repository(connection)
        with self.assertRaises(StorageError) as caught: repo.update_note(NOTE, 'new', 1)
        self.assertEqual(caught.exception.code, 'SQLSERVER_NOTE_REVISION_CONFLICT')
        self.assertFalse(any('UPDATE dbo' in s for s, _ in connection.calls))

    def test_note_compare_and_swap_detects_concurrent_change_even_with_same_text(self):
        row = (NOTE, MATCH, 'old', 1, STAMP, STAMP)
        connection = Connection(lambda statement, _: [] if statement.startswith('DECLARE') else [row])
        repo = repository(connection)
        with self.assertRaises(StorageError) as caught: repo.update_note(NOTE, 'new', 1)
        self.assertEqual(caught.exception.code, 'SQLSERVER_NOTE_REVISION_CONFLICT')
        update = next((s, p) for s, p in connection.calls if s.startswith('DECLARE'))
        self.assertIn('OUTPUT inserted.revision INTO @changed', update[0])
        self.assertEqual(update[1][-3:], ('profile-a', NOTE, 1))

    def test_create_note_duplicate_requires_same_match_and_text(self):
        row = (NOTE, MATCH, 'read-only fixture', 1, STAMP, STAMP)
        connection = Connection(lambda *_: [row]); repo = repository(connection)
        self.assertEqual(repo.create_note(MATCH, 'read-only fixture', NOTE)['revision'], 1)
        self.assertIn('WITH(UPDLOCK,HOLDLOCK)', connection.calls[0][0])
        with self.assertRaises(StorageError): repo.create_note(MATCH, 'changed', NOTE)
        self.assertFalse(any(s.startswith('INSERT') for s, _ in connection.calls))


if __name__ == '__main__': main()
