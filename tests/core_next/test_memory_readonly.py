"""Fail-closed memory observation/read regressions in task-owned LAB state."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dragonhydra.cognition import memory
from dragonhydra.kernel.engines import MemoryEngine
from dragonhydra.kernel.ports import ApplicationContext, StoragePort


LAB = Path('C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB')


class ReadonlyMemoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=LAB/'tests', prefix='readonly-memory-')
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        self.database = self.state/'core.sqlite3'
        def forbidden():
            raise AssertionError('Readonly engine must not use a writable storage connection')
        self.engine = MemoryEngine(ApplicationContext(StoragePort(self.state, self.database,
            self.state, self.state/'exports', forbidden), object(),
            lambda: datetime.now(timezone.utc).isoformat()), memory)

    def schema(self):
        with closing(sqlite3.connect(self.database.as_uri()+'?mode=ro', uri=True)) as db:
            return list(db.execute("SELECT name,type,sql FROM sqlite_master ORDER BY name"))

    def initialize(self, *, complete=False, record=False):
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript(memory.SCHEMA_SQL if complete else memory.SCHEMA_SQL.split(';', 1)[0]+';')
            if record:
                db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)',
                           ('model', 'SYNTHETIC-ROW', 'SYNTHETIC-NATURAL', '0'*64, '{}'))
            db.commit()

    def test_partial_records_table_cannot_report_immutable_memory_ready(self):
        self.initialize(record=True)
        before = self.schema()
        result = self.engine.observe()
        self.assertEqual(result['state'], 'UNAVAILABLE')
        self.assertEqual(result['reason'], 'COGNITIVE_STORE_INCOMPLETE')
        self.assertEqual(result['metrics'], {'schema_complete': False})
        self.assertEqual(self.schema(), before)

    def test_initial_history_read_does_not_initialize_memory(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('CREATE TABLE preserved(value TEXT)')
        before = self.schema()
        result = self.engine.view(datetime.now(timezone.utc).isoformat())
        self.assertTrue(all(value == [] for value in result.values()))
        self.assertEqual(self.schema(), before)
        observation = self.engine.observe()
        self.assertEqual(observation['state'], 'NOT_CONFIGURED')
        self.assertEqual(observation['metrics'], {'configured': False, 'schema_complete': False})

    def test_each_missing_immutable_trigger_fails_closed_without_repair(self):
        self.initialize(complete=True)
        for name in ('cognitive_records_no_update', 'cognitive_records_no_delete',
                     'cognitive_receipts_no_update', 'cognitive_receipts_no_delete'):
            with self.subTest(trigger=name):
                with closing(sqlite3.connect(self.database)) as db:
                    db.execute('DROP TRIGGER '+name)
                before = self.schema()
                self.assertEqual(self.engine.observe()['reason'], 'COGNITIVE_STORE_INCOMPLETE')
                with self.assertRaisesRegex(ValueError, 'COGNITIVE_STORE_INCOMPLETE'):
                    self.engine.view(datetime.now(timezone.utc).isoformat())
                self.assertEqual(self.schema(), before)
                with closing(sqlite3.connect(self.database)) as db:
                    db.executescript(memory.SCHEMA_SQL)

    def test_explicit_readonly_memory_api_does_not_write_complete_or_partial_schema(self):
        self.initialize(complete=True)
        before = self.database.read_bytes()
        result = memory.as_of(self.database, datetime.now(timezone.utc).isoformat(), readonly=True)
        self.assertTrue(all(value == [] for value in result.values()))
        self.assertEqual(self.database.read_bytes(), before)
        observation = self.engine.observe()
        self.assertTrue(observation['metrics']['configured'])
        self.assertTrue(observation['metrics']['schema_complete'])
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('DROP TABLE cognitive_receipts')
        before = self.schema()
        with self.assertRaisesRegex(ValueError, 'COGNITIVE_STORE_INCOMPLETE'):
            memory.as_of(self.database, datetime.now(timezone.utc).isoformat(), readonly=True)
        self.assertEqual(self.schema(), before)

    def test_unavailable_store_does_not_create_file_or_infer_empty_memory(self):
        self.assertFalse(self.database.exists())
        self.assertEqual(self.engine.observe()['state'], 'UNAVAILABLE')
        with self.assertRaisesRegex(ValueError, 'COGNITIVE_STORE_UNAVAILABLE'):
            self.engine.view(datetime.now(timezone.utc).isoformat())
        self.assertFalse(self.database.exists())
        self.database.write_bytes(b'SYNTHETIC invalid SQLite file')
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        result = self.engine.observe()
        self.assertEqual(result['state'], 'UNAVAILABLE')
        self.assertEqual(result['metrics'], {})
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
