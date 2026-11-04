"""Synthetic publication contract and real isolated SQLite archive acceptance.

No installed profile/database, SQLServer connection, provider or service is used.
"""
from contextlib import closing
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from dragonhydra.research_storage import configured_repository
from dragonhydra.research_storage.base import SCHEMA, StorageError, fingerprint, validate_bundle
from dragonhydra.research_storage.sqlite import SQLiteResearchRepository

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / 'runtime' / 'sqlserver-evidence' / 'unit-temp'


def synthetic_bundle(archive='a', match='b', run='SYNTHETIC-run-1', count=2):
    """Clearly synthetic complete publication; values are decimal text, not skill claims."""
    probabilities = {'home': '0.5', 'draw': '0.25', 'away': '0.25'}
    models, predictions = [], []
    for index in range(count):
        model_id = format(index + 1, '064x')
        models.append({'record_id': model_id, 'model': 'SYNTHETIC-model', 'version': 'unit/1',
                       'parameters': {'result': {'probabilities': {
                           key: {'value': value} for key, value in probabilities.items()}}}})
        predictions.append({'record_id': format(index + 101, '064x'), 'model_run_id': model_id,
                            'run_id': run, 'probabilities': dict(probabilities)})
    return {'schema_version': SCHEMA, 'archive_id': archive * 64, 'match_id': match * 64,
            'forecast_run_id': run, 'match': {'id': match * 64, 'label': 'SYNTHETIC fixture'},
            'models': models, 'predictions': predictions,
            'input_manifest': [{'record_id': 'SYNTHETIC-input-1', 'version': 'SYNTHETIC-v1'}],
            'evaluation_status': 'pending', 'source_build': {'kind': 'synthetic-unit-fixture'}}


def set_probabilities(bundle, values):
    for model in bundle['models']:
        model['parameters']['result']['probabilities'] = {k: {'value': v} for k, v in values.items()}
    for prediction in bundle['predictions']:
        prediction['probabilities'] = dict(values)
    return bundle


class ResearchStorage(unittest.TestCase):
    def test_json_numeric_model_matches_canonical_prediction_decimal_text(self):
        value = set_probabilities(synthetic_bundle(),
            {'home':'0.3584905660377358','draw':'0.32075471698113206','away':'0.32075471698113206'})
        for model in value['models']:
            for number in model['parameters']['result']['probabilities'].values():
                number['value'] = float(number['value'])
        self.assertEqual(validate_bundle(value), value)
        value['predictions'][0]['probabilities']['home'] = '0.3584905660377359'
        with self.assertRaisesRegex(StorageError,'RESEARCH_MODEL_PROBABILITY_MISMATCH'):
            validate_bundle(value)

    def setUp(self):
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='synthetic-', dir=TEMP_ROOT)
        self.root = Path(self.temporary.name).resolve()
        self.assertTrue(self.root.is_relative_to(TEMP_ROOT.resolve()))
        self.addCleanup(self.temporary.cleanup)
        self.repo = SQLiteResearchRepository(self.root / 'research.sqlite3', 'SYNTHETIC-scope-A')

    def initialized(self):
        self.repo.initialize()
        return self.repo

    def reject_bundle(self, value):
        with self.assertRaises(StorageError):
            validate_bundle(value)

    def test_01_complete_synthetic_publication_is_valid(self):
        value = synthetic_bundle()
        self.assertEqual(validate_bundle(value), value)

    def test_02_default_selection_is_passive_and_separate_from_canonical(self):
        canonical = self.root / 'core.sqlite3'
        with closing(sqlite3.connect(canonical)) as db:
            db.execute('CREATE TABLE retained(id TEXT PRIMARY KEY)')
            db.execute('INSERT INTO retained VALUES(?)', ('SYNTHETIC-canonical-record',))
            db.commit()
        before = hashlib.sha256(canonical.read_bytes()).hexdigest()
        repo = configured_repository(self.root, 'SYNTHETIC-scope-A')
        self.assertEqual(repo.provider, 'sqlite')
        self.assertFalse(repo.path.exists())
        repo.initialize(); repo.save(synthetic_bundle())
        self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), before)
        self.assertNotEqual(repo.path, canonical)

    def test_03_initialize_is_idempotent_and_preserves_archive(self):
        repo = self.initialized(); value = synthetic_bundle(); repo.save(value)
        repo.initialize()
        reopened = SQLiteResearchRepository(repo.path, repo.scope)
        self.assertTrue(reopened.health()['connected'])
        self.assertEqual(reopened.get(value['archive_id'])['archive'], value)

    def test_04_exact_decimal_payload_survives_close_and_reopen(self):
        values = {'home': '0.1234567890123456789012345678', 'draw': '0.3',
                  'away': '0.5765432109876543210987654322'}
        value = set_probabilities(synthetic_bundle(), values)
        result = self.initialized().save(value)
        found = SQLiteResearchRepository(self.repo.path, self.repo.scope).get(value['archive_id'])
        self.assertEqual(found['archive'], value)
        self.assertEqual(found['archive']['predictions'][0]['probabilities'], values)
        self.assertEqual(result['payload_sha256'], fingerprint(value))
        self.assertEqual(sum(Decimal(v) for v in values.values()), Decimal(1))

    def test_05_history_filters_match_and_remains_stable_after_reopen(self):
        repo = self.initialized()
        for value in (synthetic_bundle('a', 'b'), synthetic_bundle('c', 'b'), synthetic_bundle('d', 'e')):
            repo.save(value)
        before = repo.history('b' * 64)
        after = SQLiteResearchRepository(repo.path, repo.scope).history('b' * 64)
        self.assertEqual(before, after)
        self.assertEqual({r['archive']['archive_id'] for r in after}, {'a' * 64, 'c' * 64})
        self.assertEqual(len(repo.history('b' * 64, limit=1)), 1)

    def test_06_duplicate_is_idempotent_across_reopen_and_key_order(self):
        value = synthetic_bundle(); first = self.initialized().save(value)
        reordered = {key: value[key] for key in reversed(value)}
        second = SQLiteResearchRepository(self.repo.path, self.repo.scope).save(reordered)
        self.assertFalse(first['duplicate']); self.assertTrue(second['duplicate'])
        self.assertEqual(first['persisted_at'], second['persisted_at'])
        self.assertEqual(first['payload_sha256'], second['payload_sha256'])
        self.assertEqual(len(self.repo.history(value['match_id'])), 1)

    def test_07_conflicting_publication_never_replaces_original(self):
        value = synthetic_bundle(); self.initialized().save(value)
        conflict = deepcopy(value); conflict['source_build']['kind'] = 'SYNTHETIC-other-build'
        with self.assertRaises(StorageError) as caught: self.repo.save(conflict)
        self.assertEqual(caught.exception.code, 'RESEARCH_IDEMPOTENCY_CONFLICT')
        self.assertEqual(self.repo.get(value['archive_id'])['archive'], value)
        self.assertEqual(len(self.repo.history(value['match_id'])), 1)

    def test_08_publication_update_and_delete_are_rejected_by_store(self):
        value = synthetic_bundle(); self.initialized().save(value)
        for statement in ('UPDATE research_archives SET payload=payload WHERE scope=?',
                          'DELETE FROM research_archives WHERE scope=?'):
            with self.subTest(statement=statement), closing(sqlite3.connect(self.repo.path)) as db:
                with self.assertRaises(sqlite3.IntegrityError): db.execute(statement, (self.repo.scope,))
                db.rollback()
        self.assertEqual(self.repo.get(value['archive_id'])['archive'], value)

    def test_09_archive_identity_is_isolated_by_scope(self):
        value = synthetic_bundle(); self.initialized().save(value)
        other = SQLiteResearchRepository(self.repo.path, 'SYNTHETIC-scope-B')
        self.assertIsNone(other.get(value['archive_id'])); self.assertEqual(other.history(value['match_id']), [])
        alternate = deepcopy(value); alternate['source_build']['kind'] = 'SYNTHETIC-other-scope'
        other.save(alternate)
        self.assertEqual(other.get(value['archive_id'])['archive'], alternate)
        self.assertEqual(self.repo.get(value['archive_id'])['archive'], value)

    def test_10_explicit_transaction_rolls_back_all_writes(self):
        repo = self.initialized()
        with self.assertRaisesRegex(RuntimeError, 'SYNTHETIC-abort'):
            with repo.transaction() as db:
                db.execute('INSERT INTO research_notes VALUES(?,?,?,?,?,?)',
                           (repo.scope, 'SYNTHETIC-note', 'b' * 64, 'temporary', 1, 'SYNTHETIC-time'))
                raise RuntimeError('SYNTHETIC-abort')
        self.assertEqual(repo.notes(None), [])

    def test_11_note_revision_history_and_unicode_survive_reopen(self):
        repo = self.initialized(); text = "SYNTHETIC: Zürich 🐉 '); DROP TABLE research_archives; --"
        note = repo.create_note('b' * 64, text)
        updated = repo.update_note(note['note_id'], 'SYNTHETIC revised ✓', 1)
        reopened = SQLiteResearchRepository(repo.path, repo.scope)
        self.assertEqual(reopened.notes('b' * 64), [updated]); self.assertEqual(updated['revision'], 2)
        with closing(sqlite3.connect(repo.path)) as db:
            rows = db.execute('SELECT revision,content FROM research_note_revisions ORDER BY revision').fetchall()
        self.assertEqual(rows, [(1, text), (2, 'SYNTHETIC revised ✓')])

    def test_12_stale_note_revision_cannot_overwrite_current_text(self):
        repo = self.initialized(); note = repo.create_note('b' * 64, 'SYNTHETIC one')
        current = repo.update_note(note['note_id'], 'SYNTHETIC two', 1)
        with self.assertRaises(StorageError) as caught: repo.update_note(note['note_id'], 'SYNTHETIC stale', 1)
        self.assertEqual(caught.exception.code, 'RESEARCH_NOTE_REVISION_CONFLICT')
        self.assertEqual(repo.notes(None), [current])

    def test_13_failed_note_audit_insert_rolls_back_note_update(self):
        repo = self.initialized(); original = repo.create_note('b' * 64, 'SYNTHETIC before')
        with closing(sqlite3.connect(repo.path)) as db:
            db.execute("CREATE TRIGGER synthetic_revision_failure BEFORE INSERT ON research_note_revisions WHEN NEW.revision=2 BEGIN SELECT RAISE(ABORT,'SYNTHETIC revision failure'); END")
            db.commit()
        with self.assertRaises(sqlite3.IntegrityError): repo.update_note(original['note_id'], 'SYNTHETIC after', 1)
        self.assertEqual(repo.notes(None), [original])
        with closing(sqlite3.connect(repo.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM research_note_revisions').fetchone()[0], 1)

    def test_14_notes_cannot_be_read_or_updated_through_another_scope(self):
        repo = self.initialized(); note = repo.create_note('b' * 64, 'SYNTHETIC private scope')
        other = SQLiteResearchRepository(repo.path, 'SYNTHETIC-scope-B')
        self.assertEqual(other.notes(None), [])
        with self.assertRaises(StorageError): other.update_note(note['note_id'], 'SYNTHETIC forbidden', 1)
        self.assertEqual(repo.notes(None), [note])

    def test_15_absent_store_health_creates_no_directory_or_database(self):
        path = self.root / 'absent' / 'research.sqlite3'
        status = SQLiteResearchRepository(path, 'SYNTHETIC-scope-A').health()
        self.assertFalse(status['connected']); self.assertFalse(path.parent.exists())

    def test_16_health_never_initializes_an_existing_foreign_database(self):
        with closing(sqlite3.connect(self.repo.path)) as db:
            db.execute('CREATE TABLE synthetic_sentinel(value TEXT)'); db.commit()
        before = self.repo.path.read_bytes()
        self.assertFalse(self.repo.health()['connected'])
        self.assertEqual(self.repo.path.read_bytes(), before)
        with closing(sqlite3.connect(self.repo.path)) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [('synthetic_sentinel',)])

    def test_17_health_does_not_renew_success_or_mutate_a_healthy_store(self):
        repo = self.initialized(); repo.save(synthetic_bundle())
        stamp = repo.last_success_at; before = repo.path.read_bytes()
        self.assertTrue(repo.health()['connected']); self.assertTrue(repo.health()['connected'])
        self.assertEqual(repo.last_success_at, stamp); self.assertEqual(repo.path.read_bytes(), before)

    def test_18_invalid_storage_configuration_is_rejected_without_creation(self):
        cases = [[], {'schema_version': True, 'provider': 'sqlite'},
                 {'schema_version': 2, 'provider': 'sqlite'}, {'schema_version': 1, 'provider': 'unknown'},
                 {'schema_version': 1, 'provider': 'sqlite', 'unexpected': 'SYNTHETIC'},
                 {'schema_version': 1, 'provider': 'sqlite', 'sqlserver': {'server': 'SYNTHETIC'}}]
        for settings in cases:
            with self.subTest(settings=settings), self.assertRaises(StorageError):
                configured_repository(self.root, 'SYNTHETIC-scope-A', settings)
        self.assertFalse(self.repo.path.exists())

    def test_19_selected_sqlserver_error_never_silently_falls_back(self):
        fake = ModuleType('dragonhydra.research_storage.sqlserver')
        fake.SQLServerConfig = type('SyntheticConfig', (), {'from_dict': staticmethod(lambda value: object())})
        def unavailable(*args): raise StorageError('SYNTHETIC_SQLSERVER_UNAVAILABLE')
        fake.SQLServerResearchRepository = unavailable
        with patch.dict(sys.modules, {'dragonhydra.research_storage.sqlserver': fake}):
            with self.assertRaises(StorageError) as caught:
                configured_repository(self.root, 'SYNTHETIC-scope-A',
                                      {'schema_version': 1, 'provider': 'sqlserver', 'sqlserver': {}})
        self.assertEqual(caught.exception.code, 'SYNTHETIC_SQLSERVER_UNAVAILABLE')
        self.assertFalse(self.repo.path.exists())

    def test_20_match_archive_and_run_identity_bindings_are_required(self):
        for mutation in (lambda b: b.update(archive_id='SYNTHETIC-invalid'),
                         lambda b: b['match'].update(id='c' * 64),
                         lambda b: b['predictions'][0].update(run_id='SYNTHETIC-other-run')):
            value = synthetic_bundle(); mutation(value)
            self.reject_bundle(value)

    def test_21_malformed_models_raise_the_public_storage_error(self):
        for models in ([{}], [None], ['SYNTHETIC-invalid']):
            value = synthetic_bundle(count=1); value['models'] = models
            with self.subTest(models=models): self.reject_bundle(value)

    def test_22_each_model_requires_its_own_prediction(self):
        value = synthetic_bundle()
        value['predictions'][1]['model_run_id'] = value['models'][0]['record_id']
        self.reject_bundle(value)

    def test_23_nonfinite_and_out_of_range_probabilities_are_rejected(self):
        for bad in ('NaN', 'Infinity', '-Infinity', '-0.1', '1.1'):
            value = synthetic_bundle(); value['predictions'][0]['probabilities']['home'] = bad
            with self.subTest(value=bad): self.reject_bundle(value)

    def test_24_invalid_sum_and_lossy_precision_are_rejected(self):
        for values in ({'home': '0.2', 'draw': '0.2', 'away': '0.2'},
                       {'home': '0.12345678901234567890123456789', 'draw': '0.3',
                        'away': '0.57654321098765432109876543211'}):
            with self.subTest(values=values): self.reject_bundle(set_probabilities(synthetic_bundle(), values))

    def test_25_prediction_probabilities_require_decimal_strings(self):
        value = set_probabilities(synthetic_bundle(), {'home': 0.5, 'draw': 0.25, 'away': 0.25})
        self.reject_bundle(value)

    def test_26_nonfinite_json_and_missing_build_trace_are_rejected(self):
        for value in (float('nan'), float('inf')):
            bundle = synthetic_bundle(); bundle['source_build']['SYNTHETIC-nonfinite'] = value
            self.reject_bundle(bundle)
        for missing in (None, [], 'SYNTHETIC-invalid'):
            bundle = synthetic_bundle(); bundle['source_build'] = missing
            with self.subTest(source_build=missing): self.reject_bundle(bundle)
        bundle = synthetic_bundle(); del bundle['source_build']; self.reject_bundle(bundle)


if __name__ == '__main__':
    unittest.main()
