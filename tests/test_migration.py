"""Migration preparation preserves real SQLite state and refuses incomplete evidence."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from dragonhydra import migration
from dragonhydra.connectors.core import Document, utc_now
from dragonhydra.cognition import memory
from dragonhydra.jobs import Jobs
from dragonhydra.product import Product


ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime'/'scratch', prefix='migration-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = Product(self.root/'state')
        Jobs(self.product)
        self.output = self.root/'bundle'

    def manifest(self):
        return json.loads((self.output/'manifest.json').read_text(encoding='utf-8'))

    def prepare(self):
        return migration.prepare(self.product.db_path, self.output)

    def table(self, name):
        return next(table for table in self.manifest()['tables'] if table['name'] == name)

    def export_rows(self, name):
        table = self.table(name)
        return [json.loads(line) for line in (self.output/table['path']).read_text(encoding='utf-8').splitlines()]

    def raw_receipt(self, body=b'{"retained":"exact evidence"}'):
        digest = hashlib.sha256(body).hexdigest()
        directory = self.product.state/'raw'/'connectors'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory/(digest+'.payload')
        path.write_bytes(body)
        doc = Document('https://github.com/statsbomb/open-data', 'https://github.com/hudl/open-data', body,
                       utc_now(), digest, 'application/json', 'fixture-acquisition', path.name)
        self.product.connector_store.receipt('statsbomb', doc)
        return path, doc

    def rewrite_manifest(self, manifest):
        manifest.pop('manifest_sha256', None)
        manifest['manifest_sha256'] = hashlib.sha256(migration.canonical(manifest)).hexdigest()
        (self.output/'manifest.json').write_bytes(migration.canonical(manifest)+b'\n')

    def assert_code(self, code, operation):
        with self.assertRaises(migration.MigrationError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def test_wal_snapshot_includes_committed_rows_and_excludes_later_writer_commit(self):
        with closing(self.product.connect()) as writer:
            writer.execute("INSERT INTO connector_settings(provider,config) VALUES('committed','{}')")
            writer.commit()
            self.assertGreater(self.product.db_path.with_name('core.sqlite3-wal').stat().st_size, 0)
            writer.execute("INSERT INTO connector_settings(provider,config) VALUES('later-commit','{}')")
            calls = 0
            real_clock = time.monotonic

            def commit_during_backup():
                nonlocal calls
                calls += 1
                # First call establishes the deadline after BEGIN/read. The
                # second runs in backup's progress callback, with that snapshot.
                if calls == 2:
                    writer.commit()
                return real_clock()

            with patch('dragonhydra.migration.time.monotonic', side_effect=commit_during_backup):
                self.prepare()
            self.assertGreaterEqual(calls, 2)
            self.assertEqual(writer.execute('SELECT COUNT(*) FROM connector_settings').fetchone()[0], 2)
        rows = self.export_rows('connector_settings')
        self.assertEqual([row['values'][0] for row in rows], [['text', 'committed']])
        self.assertEqual(self.manifest()['source']['journal_mode'], 'wal')
        self.assertEqual(migration.validate_bundle(self.output)['status'], migration.STATUS)

    def test_dynamic_storage_types_and_primary_key_order_round_trip_exactly(self):
        values = [('z-blob', b'\x00\xff\x80\n'), ('a-int', 9223372036854775807),
                  ('c-text', 'Équipe 東京\x00literal'), ('b-float', 1.1)]
        with closing(self.product.connect()) as db:
            db.executemany('INSERT INTO raw_sources(source_hash,bytes) VALUES(?,?)', values)
            db.execute("INSERT INTO connector_attempts(id,provider,operation,started_at,status) VALUES('nullable','statsbomb','test','now','running')")
            db.commit()
        self.prepare()
        rows = self.export_rows('raw_sources')
        self.assertEqual([row['values'][0][1] for row in rows], ['a-int', 'b-float', 'c-text', 'z-blob'])
        self.assertEqual([row['values'][1] for row in rows], [
            ['int', '9223372036854775807'], ['float', (1.1).hex()],
            ['text', 'Équipe 東京\x00literal'], ['blob', 'AP+ACg==']])
        self.assertTrue(any(cell == ['null'] for cell in self.export_rows('connector_attempts')[0]['values']))
        for row in rows:
            self.assertEqual(hashlib.sha256(migration.canonical(row['values'])).hexdigest(), row['row_sha256'])
        self.assertEqual(self.table('raw_sources')['primary_key'], ['source_hash'])
        self.assertEqual(migration.validate_bundle(self.output)['table_count'], 16)

    def test_empty_table_has_explicit_zero_count_and_empty_content_hash(self):
        self.prepare()
        table = self.table('product_sessions')
        self.assertEqual((table['row_count'], table['bytes']), (0, 0))
        self.assertEqual(table['sha256'], hashlib.sha256(b'').hexdigest())
        self.assertEqual((self.output/table['path']).read_bytes(), b'')

    def test_sqlite_sequence_high_water_mark_survives_deleted_rows(self):
        with closing(self.product.connect()) as db:
            db.execute("INSERT INTO product_updates(topic,payload,committed_at) VALUES('test','{}','now')")
            db.execute('DELETE FROM product_updates')
            db.execute("UPDATE sqlite_sequence SET seq=700 WHERE name='product_updates'")
            db.commit()
        self.prepare()
        self.assertIn(['product_updates', 700], self.manifest()['sequences'])
        # A separate owned copy demonstrates the future rollback database will
        # allocate from the preserved high-water mark, despite an empty table.
        restored = self.root/'restored.sqlite3'
        shutil.copyfile(self.output/'core.sqlite3', restored)
        with closing(sqlite3.connect(restored)) as db:
            db.execute("INSERT INTO product_updates(topic,payload,committed_at) VALUES('test','{}','later')")
            self.assertEqual(db.execute('SELECT seq FROM product_updates').fetchone()[0], 701)

    def test_exact_schema_indexes_triggers_and_metadata_are_preserved(self):
        with closing(self.product.connect()) as db:
            db.execute('CREATE INDEX "fixture index" ON connector_settings(provider DESC)')
            db.execute("CREATE TRIGGER fixture_trigger BEFORE DELETE ON connector_settings BEGIN SELECT RAISE(ABORT, 'keep'); END")
            db.execute('PRAGMA user_version=41')
            db.execute('PRAGMA application_id=12450')
            db.commit()
            original = [{'type': kind, 'name': name, 'table': table, 'sql': sql}
                        for kind, name, table, sql in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        self.prepare()
        self.assertEqual(json.loads((self.output/'schema.json').read_text(encoding='utf-8')), original)
        self.assertEqual(self.manifest()['snapshot']['user_version'], 41)
        self.assertEqual(self.manifest()['snapshot']['application_id'], 12450)

    def test_raw_evidence_is_copied_hashed_and_sibling_secrets_are_excluded(self):
        path, doc = self.raw_receipt()
        (self.product.state/'vault').mkdir()
        (self.product.state/'vault'/'private.dpapi').write_bytes(b'sibling-vault-never-copy')
        (self.product.state/'local-session.json').write_text('{"token":"sibling-token-never-copy"}')
        with closing(self.product.connect()) as db:
            db.execute("INSERT INTO product_sessions VALUES('hashed-session','owner','[\"admin\"]',9000)")
            db.commit()
        result = self.prepare()
        self.assertEqual(result['raw_payload_count'], 1)
        copied = self.output/'raw'/'connectors'/path.name
        self.assertEqual(copied.read_bytes(), doc.body)
        self.assertEqual(hashlib.sha256(copied.read_bytes()).hexdigest(), doc.sha256)
        self.assertEqual(self.manifest()['raw_payloads'][0]['acquisition_ids'], ['fixture-acquisition'])
        self.assertEqual(self.table('product_sessions')['row_count'], 1)
        self.assertFalse((self.output/'vault').exists())
        self.assertFalse((self.output/'local-session.json').exists())
        self.assertFalse(self.manifest()['privacy']['vault_or_sibling_credential_files_copied'])
        if os.name == 'nt':
            acl = subprocess.check_output(['icacls', str(self.output/'core.sqlite3')])
            self.assertNotIn(b'(I)', acl)
        else:
            self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
            self.assertEqual(copied.stat().st_mode & 0o777, 0o600)

    def test_missing_raw_evidence_refuses_completion_and_source_is_unchanged(self):
        path, _ = self.raw_receipt()
        path.unlink()
        before = hashlib.sha256(self.product.db_path.read_bytes()).hexdigest()
        self.assert_code('RAW_EVIDENCE_MISSING', self.prepare)
        self.assertFalse((self.output/'manifest.json').exists())
        self.assertEqual(json.loads((self.output/'failure.json').read_text())['code'], 'RAW_EVIDENCE_MISSING')
        self.assertEqual(hashlib.sha256(self.product.db_path.read_bytes()).hexdigest(), before)
        self.assert_code('BUNDLE_INVALID', lambda: migration.validate_bundle(self.output))

    def test_corrupt_raw_evidence_refuses_completion(self):
        path, _ = self.raw_receipt()
        path.write_bytes(b'changed')
        self.assert_code('RAW_EVIDENCE_CORRUPT', self.prepare)
        self.assertFalse((self.output/'manifest.json').exists())

    def test_unsafe_raw_reference_cannot_escape_selected_state(self):
        self.raw_receipt()
        with closing(self.product.connect()) as db:
            db.execute("UPDATE connector_acquisitions SET raw_reference='../local-session.json'")
            db.commit()
        self.assert_code('RAW_REFERENCE_INVALID', self.prepare)

    def test_existing_output_and_outside_workspace_paths_are_refused(self):
        self.output.mkdir()
        sentinel = self.output/'keep.txt'
        sentinel.write_text('existing result')
        self.assert_code('OUTPUT_EXISTS', self.prepare)
        self.assertEqual(sentinel.read_text(), 'existing result')
        self.assert_code('PATH_OUTSIDE_WORKSPACE', lambda: migration.prepare(self.product.db_path, ROOT.parent/'unowned-migration-bundle'))
        self.assert_code('OUTPUT_INSIDE_SOURCE_STATE', lambda: migration.prepare(self.product.db_path, self.product.state/'bundle'))

    def test_unknown_table_and_invalid_foreign_keys_are_rejected(self):
        with closing(self.product.connect()) as db:
            db.execute('CREATE TABLE unsupported_new_authority(id INTEGER PRIMARY KEY)')
            db.commit()
        self.assert_code('UNSUPPORTED_TABLE', self.prepare)
        with closing(self.product.connect()) as db:
            db.execute('DROP TABLE unsupported_new_authority')
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute("INSERT INTO public_fixture_records VALUES('absent','capture',1,'fixture','{}')")
            db.commit()
        self.output = self.root/'broken-fk-bundle'
        self.assert_code('SQLITE_FOREIGN_KEY_FAILED', self.prepare)

    def test_validation_detects_artifact_and_manifest_drift(self):
        self.prepare()
        table = self.table('product_schema')
        (self.output/table['path']).write_bytes(b'changed')
        self.assert_code('ARTIFACT_HASH_MISMATCH', lambda: migration.validate_bundle(self.output))
        manifest = self.manifest()
        manifest['status'] = 'not-a-migration'
        (self.output/'manifest.json').write_text(json.dumps(manifest))
        self.assert_code('BUNDLE_VERSION_UNSUPPORTED', lambda: migration.validate_bundle(self.output))

    def test_validation_recomputes_rows_against_snapshot_after_export_hash_is_changed(self):
        self.prepare()
        manifest = self.manifest()
        table = next(item for item in manifest['tables'] if item['name'] == 'product_schema')
        cells = [['int', '999']]
        line = migration.canonical({'values': cells, 'row_sha256': hashlib.sha256(migration.canonical(cells)).hexdigest()})+b'\n'
        (self.output/table['path']).write_bytes(line)
        table.update(bytes=len(line), sha256=hashlib.sha256(line).hexdigest())
        self.rewrite_manifest(manifest)
        self.assert_code('TABLE_EXPORT_MISMATCH', lambda: migration.validate_bundle(self.output))

    def test_successful_prepare_leaves_source_database_byte_identical_and_runnable(self):
        self.raw_receipt()
        before = hashlib.sha256(self.product.db_path.read_bytes()).hexdigest()
        result = self.prepare()
        self.assertTrue(result['valid'])
        self.assertFalse(result['backend_changed'])
        self.assertEqual(result['source_access'], 'read_only')
        self.assertEqual(hashlib.sha256(self.product.db_path.read_bytes()).hexdigest(), before)
        with closing(self.product.connect()) as db:
            db.execute("INSERT INTO connector_settings(provider,config) VALUES('after-preparation','{}')")
            db.commit()
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_optional_context_profile_has_exact_two_tables_and_versioned_manifest(self):
        with closing(self.product.connect()) as db:
            memory._schema(db)
            db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)',
                       ('source_context', 'source_context:'+('a'*64), 'b'*64, 'c'*64,
                        migration.canonical({'synthetic': True, 'version': 'statsbomb-context/1'}).decode()))
            db.execute('INSERT INTO cognitive_receipts VALUES(?,?,?,?)',
                       ('source_context:'+('a'*64), 'received', 'persisted', 'usable'))
            db.commit()
        result = self.prepare()
        manifest = self.manifest()
        self.assertEqual(manifest['bundle_version'], migration.CONTEXT_VERSION)
        self.assertEqual(manifest['schema_profile'], migration.CONTEXT_PROFILE)
        self.assertEqual(result['schema_profile'], migration.CONTEXT_PROFILE)
        self.assertEqual(result['table_count'], 18)
        schema = json.loads((self.output/'schema.json').read_text())
        self.assertEqual(sum(item['type'] == 'trigger' for item in schema), 14)
        self.assertEqual(self.table('cognitive_records')['row_count'], 1)
        self.assertEqual(self.table('cognitive_receipts')['row_count'], 1)
        self.assertTrue(migration.validate_bundle(self.output)['valid'])

    def test_core_output_remains_v1_without_a_profile_field(self):
        self.prepare()
        self.assertEqual(self.manifest()['bundle_version'], migration.VERSION)
        self.assertNotIn('schema_profile', self.manifest())
        self.assertNotIn('schema_profile', migration.validate_bundle(self.output))

    def test_context_partial_or_altered_schema_is_rejected_during_preparation(self):
        changes = (
            'DROP TABLE cognitive_receipts',
            'DROP TRIGGER cognitive_records_no_update',
            'CREATE INDEX unaudited_context_index ON cognitive_records(fingerprint)',
            'DROP TABLE connector_settings',
        )
        for index, statement in enumerate(changes):
            with self.subTest(statement=statement):
                self.product = Product(self.root/('state-'+str(index)))
                Jobs(self.product)
                with closing(self.product.connect()) as db:
                    memory._schema(db)
                    db.execute(statement)
                    db.commit()
                self.output = self.root/('invalid-'+str(index))
                self.assert_code('UNSUPPORTED_SCHEMA_PROFILE', self.prepare)
                self.assertFalse((self.output/'manifest.json').exists())

    def test_context_manifest_version_and_profile_must_match_retained_schema(self):
        with closing(self.product.connect()) as db:
            memory._schema(db)
        self.prepare()
        original = self.manifest()
        for profile in (None, 'unknown-context-9'):
            with self.subTest(profile=profile):
                manifest = {**original}
                if profile is None:
                    manifest.pop('schema_profile')
                else:
                    manifest['schema_profile'] = profile
                self.rewrite_manifest(manifest)
                self.assert_code('BUNDLE_VERSION_UNSUPPORTED', lambda: migration.validate_bundle(self.output))
        manifest = {**original, 'bundle_version': migration.VERSION}
        manifest.pop('schema_profile')
        self.rewrite_manifest(manifest)
        self.assert_code('BUNDLE_PROFILE_MISMATCH', lambda: migration.validate_bundle(self.output))


if __name__ == '__main__':
    unittest.main()
