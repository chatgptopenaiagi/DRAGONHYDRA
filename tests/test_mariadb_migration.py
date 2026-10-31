"""Offline SQL checks: audited schema, exact identity bytes and lossless literals.

These tests inspect and independently regenerate SQL. They never execute it on
MariaDB and therefore do not claim runtime dialect or backend compatibility.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra import mariadb_migration as writer, migration
from dragonhydra.cognition import memory
from dragonhydra.jobs import Jobs
from dragonhydra.product import Product


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'dragonhydra_migration_fixture'


class MariaDBSQLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime'/'scratch', prefix='mariadb-sql-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = Product(self.root/'state')
        self.jobs = Jobs(self.product)
        self.bundle, self.output = self.root/'prepared', self.root/'sql'

    def prepare(self):
        migration.prepare(self.product.db_path, self.bundle)

    def build(self):
        return writer.build_script(self.bundle, self.output, SCHEMA)

    def manifest(self):
        return json.loads((self.output/'manifest.json').read_text(encoding='utf-8'))

    def sql(self):
        return (self.output/'migration.sql').read_text(encoding='utf-8')

    def table(self, name):
        return next(table for table in self.manifest()['mapping']['tables'] if table['name'] == name)

    def assert_code(self, code, operation):
        with self.assertRaises(writer.MariaDBMigrationError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def test_full_core_schema_fks_indexes_and_audited_key_budgets(self):
        self.prepare()
        result = self.build()
        manifest = self.manifest()
        self.assertEqual(result['table_count'], 16)
        self.assertFalse(result['executed'])
        self.assertFalse(result['cutover'])
        self.assertFalse(result['backend_changed'])
        order = manifest['mapping']['creation_order']
        sql = self.sql()
        for table in manifest['mapping']['tables']:
            self.assertIn('CREATE TABLE `'+table['name']+'`', sql)
            for foreign in table['foreign_keys']:
                self.assertLess(order.index(foreign['parent_table']), order.index(table['name']))
                self.assertIn('CONSTRAINT `'+foreign['name']+'` FOREIGN KEY', sql)
            for index in table['indexes']:
                self.assertIn('KEY `'+index['name']+'` USING BTREE', sql)
            for audit in table['key_audit']:
                self.assertLessEqual(audit['declared_bytes'], 3072)
                self.assertLessEqual(audit['with_primary_key_bytes'], 3072)
                self.assertFalse(audit['prefix_lengths_used'])
        self.assertIn('ROW_FORMAT=DYNAMIC', sql)
        self.assertIn('SET SESSION foreign_key_checks=1;', sql)
        self.assertEqual(manifest['target_requirements']['innodb_page_size_minimum'], 16384)
        self.assertTrue(writer.validate_script(self.output)['valid'])

    def test_malicious_unicode_nul_quotes_and_backslashes_are_only_hex_data(self):
        hostile = "'; DROP TABLE dragonhydra_admin.users; -- \\\x00 Équipe 😀"
        with closing(self.product.connect()) as db:
            db.execute('INSERT INTO connector_settings(provider,config) VALUES(?,?)', ('case', hostile))
            db.commit()
        self.prepare()
        self.build()
        sql = self.sql()
        self.assertNotIn(hostile, sql)
        self.assertNotIn('DROP TABLE', sql)
        self.assertIn("CONVERT(X'"+hostile.encode('utf-8').hex()+"' USING utf8mb4)", sql)
        self.assertIn("X'63617365'", sql)
        self.assertIn('`config` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin', sql)

    def test_case_trailing_spaces_empty_keys_and_nullable_unique_values_are_preserved(self):
        for owner in ('Owner', 'owner', 'owner '):
            self.jobs.submit('explanation', {'match_id': 'fixture'}, owner, 'same')
        self.jobs.submit('explanation', {'match_id': 'fixture'}, 'nullable')
        self.jobs.submit('explanation', {'match_id': 'fixture'}, 'nullable')
        with closing(self.product.connect()) as db:
            db.execute("INSERT INTO connector_settings(provider) VALUES('')")
            db.commit()
        self.prepare()
        self.build()
        table = self.table('product_jobs')
        columns = {column['name']: column for column in table['columns']}
        self.assertEqual(table['row_count'], 5)
        self.assertEqual(columns['owner']['target_type'], 'VARBINARY(512)')
        self.assertEqual(columns['idempotency_key']['target_type'], 'VARBINARY(512)')
        self.assertTrue(columns['idempotency_key']['nullable'])
        self.assertEqual(columns['idempotency_key']['null_count'], 2)
        sql = self.sql()
        for owner in ('Owner', 'owner', 'owner '):
            self.assertIn("X'"+owner.encode('utf-8').hex()+"'", sql)
        self.assertIn("VALUES (X'',", sql)
        self.assertIn('UNIQUE KEY `sqlite_autoindex_product_jobs_2` USING BTREE (`owner` ASC,`idempotency_key` ASC)', sql)

    def test_integer_blob_and_real_literals_preserve_source_values(self):
        binary = b'\x00\xff\x80\n'
        with closing(self.product.connect()) as db:
            db.execute('INSERT INTO raw_sources VALUES(?,?)', (hashlib.sha256(binary).hexdigest(), binary))
            db.execute('INSERT INTO connector_settings(provider,interval_seconds,next_due) VALUES(?,?,?)',
                       ('numbers', 9223372036854775807, 1.1))
            db.commit()
        self.prepare()
        self.build()
        sql = self.sql()
        self.assertIn("X'00ff800a'", sql)
        self.assertIn('9223372036854775807,1.1000000000000001e0', sql)
        self.assertIn('`bytes` LONGBLOB NOT NULL', sql)
        self.assertIn('`interval_seconds` BIGINT NOT NULL DEFAULT 0', sql)
        self.assertIn('`next_due` DOUBLE NOT NULL DEFAULT 0e0', sql)
        column = {'source_declared_type': 'REAL', 'nullable': False}
        for value in (-0.0, 0.1, 5e-324, 1.7976931348623157e308):
            literal = writer._literal(value, column)
            self.assertEqual(float(literal).hex(), value.hex())

    def test_sequence_high_water_is_restored_after_rows_are_loaded(self):
        with closing(self.product.connect()) as db:
            db.execute("INSERT INTO product_updates(topic,payload,committed_at) VALUES('test','{}','now')")
            db.execute('DELETE FROM product_updates')
            db.execute("UPDATE sqlite_sequence SET seq=700 WHERE name='product_updates'")
            db.commit()
        self.prepare()
        self.build()
        self.assertEqual(self.table('product_updates')['auto_increment']['next_value'], 701)
        sql = self.sql()
        self.assertIn('ALTER TABLE `product_updates` AUTO_INCREMENT = 701;', sql)
        self.assertGreater(sql.index('ALTER TABLE `product_updates` AUTO_INCREMENT'), sql.index('COMMIT;'))
        self.assertIn('NO_AUTO_VALUE_ON_ZERO', sql)

    def test_ten_source_immutability_triggers_become_single_signal_statements(self):
        self.prepare()
        self.build()
        statements = json.loads((self.output/'statements.json').read_text(encoding='utf-8'))
        triggers = [statement for statement in statements if statement.startswith('CREATE TRIGGER')]
        self.assertEqual(len(triggers), 10)
        self.assertEqual(len(self.manifest()['mapping']['triggers']), 10)
        for statement in triggers:
            self.assertIn("FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='immutable';", statement)
            self.assertNotIn('DELIMITER', statement)
            self.assertNotIn('BEGIN', statement)
        self.assertNotIn('INSERT IGNORE', self.sql())
        self.assertNotIn('REPLACE INTO', self.sql())
        self.assertNotIn('DROP ', self.sql())

    def test_ordered_statement_array_exactly_matches_hashed_cli_sql(self):
        self.prepare()
        result = self.build()
        statements = json.loads((self.output/'statements.json').read_text(encoding='utf-8'))
        self.assertTrue(all(isinstance(statement, str) for statement in statements))
        self.assertEqual(''.join(statements), self.sql())
        manifest = self.manifest()
        self.assertEqual(manifest['statements']['count'], len(statements))
        self.assertLessEqual(max(len(statement.encode('utf-8')) for statement in statements),
                             manifest['mapping']['maximum_statement_bytes'])
        self.assertEqual(hashlib.sha256((self.output/'statements.json').read_bytes()).hexdigest(), manifest['statements']['sha256'])
        self.assertEqual(hashlib.sha256(self.sql().encode('utf-8')).hexdigest(), result['sql_sha256'])

    def test_declared_type_mismatches_and_nonfinite_reals_fail_before_output(self):
        cases = [('raw_sources', 'bytes', 'not-binary'), ('connector_settings', 'config', sqlite3.Binary(b'not-text')),
                 ('connector_settings', 'interval_seconds', 2.5), ('connector_settings', 'next_due', float('inf'))]
        for number, (table, column, value) in enumerate(cases):
            with self.subTest(table=table, column=column):
                with closing(self.product.connect()) as db:
                    if table == 'raw_sources':
                        db.execute('INSERT INTO raw_sources VALUES(?,?)', ('typed-source', value))
                    else:
                        db.execute('INSERT INTO connector_settings(provider,'+column+') VALUES(?,?)', ('typed-provider', value))
                    db.commit()
                self.bundle, self.output = self.root/('prepared-'+str(number)), self.root/('sql-'+str(number))
                self.prepare()
                self.assert_code('SOURCE_TYPE_MISMATCH', self.build)
                self.assertFalse(self.output.exists())
                with closing(self.product.connect()) as db:
                    if table == 'raw_sources':
                        db.execute('DROP TRIGGER public_raw_immutable_delete')
                        db.execute("DELETE FROM raw_sources WHERE source_hash='typed-source'")
                        db.execute("CREATE TRIGGER public_raw_immutable_delete BEFORE DELETE ON raw_sources BEGIN SELECT RAISE(ABORT,'immutable'); END")
                    else:
                        db.execute("DELETE FROM connector_settings WHERE provider='typed-provider'")
                    db.commit()

    def test_identity_capacity_is_measured_in_utf8_bytes(self):
        with closing(self.product.connect()) as db:
            db.execute('INSERT INTO connector_settings(provider) VALUES(?)', ('é'*65,))
            db.commit()
        self.prepare()
        self.assert_code('KEY_VALUE_TOO_LONG', self.build)
        self.assertFalse(self.output.exists())

    def test_composite_key_budget_never_falls_back_to_prefix_or_hash_indexes(self):
        self.prepare()
        with patch.dict(writer.TEXT_CAPACITIES['product_jobs'], {'owner': 2000, 'idempotency_key': 1500}):
            self.assert_code('INDEX_BUDGET_EXCEEDED', self.build)
        self.assertFalse(self.output.exists())

    def test_exhausted_autoincrement_is_rejected(self):
        with closing(self.product.connect()) as db:
            db.execute("INSERT INTO product_updates(topic,payload,committed_at) VALUES('test','{}','now')")
            db.execute("UPDATE sqlite_sequence SET seq=9223372036854775807 WHERE name='product_updates'")
            db.commit()
        self.prepare()
        self.assert_code('SEQUENCE_EXHAUSTED', self.build)
        self.assertFalse(self.output.exists())

    def test_new_schema_and_exclusive_output_are_required(self):
        self.prepare()
        for schema in ('dragonhydra_admin', 'dragonhydra_core', 'dragonhydra_migration_x; SELECT 1',
                       'dragonhydra_migration_', 'dragonhydra_migration_'+'x'*44):
            with self.subTest(schema=schema):
                self.assert_code('STAGING_SCHEMA_REQUIRED', lambda: writer.build_script(self.bundle, self.output, schema))
        self.build()
        original = (self.output/'migration.sql').read_bytes()
        self.assert_code('OUTPUT_EXISTS', self.build)
        self.assertEqual((self.output/'migration.sql').read_bytes(), original)
        self.assert_code('OUTPUT_INSIDE_SOURCE_BUNDLE', lambda: writer.build_script(self.bundle, self.bundle/'sql', SCHEMA))

    def test_unaudited_schema_objects_are_refused(self):
        with closing(self.product.connect()) as db:
            db.execute("CREATE TRIGGER extra_behavior BEFORE INSERT ON connector_settings BEGIN SELECT RAISE(ABORT,'unexpected'); END")
            db.commit()
        self.prepare()
        self.assert_code('SOURCE_SCHEMA_UNSUPPORTED', self.build)
        self.assertFalse(self.output.exists())

    def test_changed_sql_is_rejected_even_when_its_declared_file_hash_is_recomputed(self):
        self.prepare()
        self.build()
        path = self.output/'migration.sql'
        with path.open('ab') as stream:
            stream.write(b'SELECT 999;\n')
        self.assert_code('SQL_ARTIFACT_CHANGED', lambda: writer.validate_script(self.output))
        manifest = self.manifest()
        manifest['sql'].update(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        manifest.pop('manifest_sha256')
        manifest['manifest_sha256'] = hashlib.sha256(migration.canonical(manifest)).hexdigest()
        (self.output/'manifest.json').write_bytes(migration.canonical(manifest)+b'\n')
        self.assert_code('SQL_CONTENT_MISMATCH', lambda: writer.validate_script(self.output))

    def context(self, *, kind='source_context', record_id=None, natural_key=None):
        record_id = record_id or 'source_context:'+('a'*64)
        natural_key = natural_key or 'b'*64
        with closing(self.product.connect()) as db:
            memory._schema(db)
            db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)',
                       (kind, record_id, natural_key, 'c'*64, '{"synthetic":true,"label":"Équipe 😀"}'))
            db.execute('INSERT INTO cognitive_receipts VALUES(?,?,?,?)',
                       (record_id, 'received', 'persisted', 'usable'))
            db.commit()

    def rewrite_manifest(self, manifest):
        manifest.pop('manifest_sha256', None)
        manifest['manifest_sha256'] = hashlib.sha256(migration.canonical(manifest)).hexdigest()
        (self.output/'manifest.json').write_bytes(migration.canonical(manifest)+b'\n')

    def test_context_v2_preserves_receipt_fk_complete_keys_and_original_trigger_messages(self):
        self.context()
        self.prepare()
        result = self.build()
        manifest = self.manifest()
        self.assertEqual(manifest['format_version'], writer.CONTEXT_VERSION)
        self.assertEqual(manifest['schema_profile'], migration.CONTEXT_PROFILE)
        self.assertEqual(result['table_count'], 18)
        self.assertEqual(result['trigger_count'], 14)
        self.assertFalse(result['cutover'])
        self.assertEqual(manifest['mapping']['key_capacity_policy']['cognitive_records'],
                         {'kind': 64, 'record_id': 128, 'natural_key': 64})
        record = self.table('cognitive_records')
        columns = {item['name']: item for item in record['columns']}
        for name, capacity in (('kind', 64), ('record_id', 128), ('natural_key', 64)):
            self.assertEqual(columns[name]['target_type'], 'VARBINARY('+str(capacity)+')')
        unique = next(item for item in record['key_audit'] if item['name'] == 'sqlite_autoindex_cognitive_records_2')
        self.assertEqual(unique['declared_bytes'], 128)
        self.assertEqual(unique['with_primary_key_bytes'], 256)
        receipt = self.table('cognitive_receipts')
        self.assertEqual(receipt['foreign_keys'][0]['parent_table'], 'cognitive_records')
        self.assertEqual(receipt['columns'][0]['target_type'], 'VARBINARY(128)')
        self.assertIn("MESSAGE_TEXT='immutable cognitive record'", self.sql())
        self.assertIn("MESSAGE_TEXT='immutable cognitive receipt'", self.sql())
        self.assertTrue(writer.validate_script(self.output)['valid'])

    def test_context_utf8_key_capacity_accepts_exact_boundary_and_rejects_overflow(self):
        self.context(kind='é'*32, record_id='é'*64, natural_key='n'*64)
        self.prepare()
        self.build()
        self.assertIn("X'"+('é'*64).encode().hex()+"'", self.sql())
        for index, change in enumerate(({'kind':'é'*33}, {'record_id':'r'*129}, {'natural_key':'n'*65})):
            with self.subTest(change=change):
                self.product = Product(self.root/('state-'+str(index)))
                Jobs(self.product)
                self.bundle, self.output = self.root/('prepared-'+str(index)), self.root/('sql-'+str(index))
                self.context(**change)
                self.prepare()
                self.assert_code('KEY_VALUE_TOO_LONG', self.build)
                self.assertFalse(self.output.exists())

    def test_context_staging_profile_cannot_be_unknown_missing_or_downgraded(self):
        self.context()
        self.prepare()
        self.build()
        original = self.manifest()
        for profile in (None, 'unknown-context-9'):
            with self.subTest(profile=profile):
                candidate = {**original}
                if profile is None:
                    candidate.pop('schema_profile')
                else:
                    candidate['schema_profile'] = profile
                self.rewrite_manifest(candidate)
                self.assert_code('SQL_MANIFEST_UNSUPPORTED', lambda: writer.validate_script(self.output))
        candidate = {**original, 'format_version': writer.VERSION}
        candidate.pop('schema_profile')
        self.rewrite_manifest(candidate)
        self.assert_code('SQL_SOURCE_PROFILE_MISMATCH', lambda: writer.validate_script(self.output))

    @unittest.skipUnless(Path(r'C:\xampp\php\php.exe').is_file(), 'Existing verified Windows PHP CLI is unavailable')
    def test_php_offline_profile_dispatch_accepts_both_and_rejects_context_scope_drift(self):
        php = str(Path(r'C:\xampp\php\php.exe'))

        def validate():
            return subprocess.run([php, str(ROOT/'tests/installation/mariadb_roundtrip.php'), '--validate-only',
                                   '--bundle', str(self.output), '--schema', SCHEMA, '--reviewed-manifest-sha256',
                                   hashlib.sha256((self.output/'manifest.json').read_bytes()).hexdigest()],
                                  capture_output=True, text=True, timeout=20)

        self.prepare()
        self.build()
        result = validate()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
        self.context()
        self.bundle, self.output = self.root/'context-prepared', self.root/'context-sql'
        self.prepare()
        self.build()
        original = self.manifest()
        result = validate()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
        for field in ('capacity', 'message', 'partial'):
            with self.subTest(field=field):
                candidate = json.loads(json.dumps(original))
                if field == 'capacity':
                    next(table for table in candidate['mapping']['tables'] if table['name']=='cognitive_records')['columns'][0]['capacity_bytes'] = 65
                elif field == 'message':
                    candidate['mapping']['triggers'][0]['message'] = 'changed'
                else:
                    candidate['mapping']['tables'] = [table for table in candidate['mapping']['tables'] if table['name']!='cognitive_receipts']
                self.rewrite_manifest(candidate)
                result = validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(json.loads(result.stdout)['passed'])


if __name__ == '__main__':
    unittest.main()
