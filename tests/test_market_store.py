from contextlib import closing
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from uuid import uuid4

from dragonhydra import market_store as store

ROOT = Path(__file__).resolve().parents[1]


class MarketStoreTests(unittest.TestCase):
    def setUp(self):
        self.runtime = ROOT / 'runtime'
        self.runtime.mkdir(exist_ok=True)
        self.name = 'test-market-store-' + uuid4().hex
        self.db = self.runtime / (self.name + '.sqlite')
        self.source = self.runtime / (self.name + '.json')
        self.csv = self.runtime / (self.name + '.csv')
        for p in (self.db, self.source, self.csv):
            self.addCleanup(p.unlink, missing_ok=True)

    def snapshot(self, acq='a1', received='2026-01-01T12:00:00Z', persisted='2026-01-01T12:01:00Z', **overrides):
        row = {'source_id':'source-a', 'provider_id':'book-a', 'feed_id':'feed-a', 'adapter_version':'fixture-v1',
               'acquisition_id':acq, 'data_origin':'synthetic', 'source_published_at':'2026-01-01T11:00:00Z',
               'received_at':received, 'persisted_at':persisted, 'event_id':'event-1', 'competition':'league',
               'home':'North', 'away':'South', 'market_type':'1x2', 'period':'full_time', 'status':'pregame',
               'settlement':'regulation_only', 'line':None,
               'quotes':[{'outcome':'home','odds_original':'2.00','odds_format':'decimal'},
                         {'outcome':'draw','odds_original':'+250','odds_format':'american'},
                         {'outcome':'away','odds_original':'5/2','odds_format':'fractional'}]}
        row.update(overrides)
        return row

    def write(self, *items):
        self.source.write_text(json.dumps({'snapshots':list(items)}, indent=2), encoding='utf-8')

    def test_inclusive_cutoff_raw_retention_and_idempotence(self):
        self.write(self.snapshot())
        raw = self.source.read_bytes()
        first = store.import_file(self.db, self.source, simulated=True)
        self.assertEqual(first['inserted'], 1)
        self.assertEqual(store.get_as_of(self.db, '2026-01-01T12:00:59Z', clock_mode='synthetic_simulated'), [])
        rows = store.get_as_of(self.db, '2026-01-01T12:01:00Z', clock_mode='synthetic_simulated')
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(x['source_hash'] == hashlib.sha256(raw).hexdigest() for x in rows))
        self.assertEqual(store.raw_source(self.db, rows[0]['source_hash']), raw)
        self.assertEqual({x['odds_original'] for x in rows}, {'2.00', '+250', '5/2'})
        self.assertEqual(store.import_file(self.db, self.source, simulated=True)['duplicates'], 1)
        self.assertEqual(store.get_as_of(self.db, '2026-01-01T12:01:00Z', clock_mode='synthetic_simulated'), rows)

    def test_late_arrival_and_correction_do_not_change_earlier_replay(self):
        old = self.snapshot()
        future = self.snapshot('a2', '2026-01-01T12:02:00Z', '2026-01-01T12:03:00Z')
        corrected = self.snapshot('a3', '2026-01-01T12:05:00Z', '2026-01-01T12:06:00Z', supersedes_acquisition_id='a1')
        corrected['quotes'][0]['odds_original'] = '2.50'
        self.write(old, future)
        store.import_file(self.db, self.source, simulated=True)
        before = store.get_as_of(self.db, '2026-01-01T12:04:00Z', clock_mode='synthetic_simulated')
        self.write(corrected)
        store.import_file(self.db, self.source, simulated=True)
        self.assertEqual(before, store.get_as_of(self.db, '2026-01-01T12:04:00Z', clock_mode='synthetic_simulated'))
        current = store.get_as_of(self.db, '2026-01-01T12:06:00Z', clock_mode='synthetic_simulated')
        self.assertEqual({x['acquisition_id'] for x in current}, {'a2', 'a3'})
        revised = next(x for x in current if x['acquisition_id']=='a3' and x['outcome']=='home')
        self.assertEqual(revised['effective_market_received_at'], '2026-01-01T12:00:00.000000Z')
        self.assertEqual(revised['revision_lineage'][0]['acquisition_id'], 'a1')

    def test_real_input_times_cannot_backdate_system_receipt(self):
        real = self.snapshot(data_origin='imported_historical')
        self.write(real)
        result = store.import_file(self.db, self.source)
        self.assertEqual(result['clock_mode'], 'operational')
        self.assertEqual(store.get_as_of(self.db, '2026-01-01T12:01:00Z'), [])
        after = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        rows = store.get_as_of(self.db, after)
        self.assertEqual(len(rows), 3)
        self.assertGreater(rows[0]['received_at'], '2026-01-01')
        self.assertGreaterEqual(rows[0]['persisted_at'], rows[0]['received_at'])
        self.assertEqual(rows[0]['usable_at'], rows[0]['persisted_at'])
        self.assertEqual(rows[0]['data_origin'], 'imported_historical')
        with self.assertRaises(ValueError):
            store.import_file(self.db, self.source, simulated=True)

    def test_collision_and_ambiguous_mapping_quarantine_without_overwrite(self):
        self.write(self.snapshot())
        store.import_file(self.db, self.source, simulated=True)
        altered = self.snapshot()
        altered['quotes'][0]['odds_original'] = '2.01'
        ambiguous = self.snapshot('a2', ambiguous_mapping=True)
        self.write(altered, ambiguous)
        counts = store.import_file(self.db, self.source, simulated=True)
        self.assertEqual(counts['quarantined'], 2)
        self.assertEqual(len(store.get_as_of(self.db, '2026-01-01T12:01:00Z', clock_mode='synthetic_simulated')), 3)
        issues = store.get_quarantine(self.db, '2026-01-01T12:01:00Z', clock_mode='synthetic_simulated')
        self.assertEqual(len(issues), 2)
        with closing(sqlite3.connect(self.db)) as connection:
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute('UPDATE acquisitions SET payload=?', ('{}',))

    def test_cross_clock_corrections_cannot_supersede_operational_data(self):
        # Synthetic data imported with the real clock is operational evidence.
        first = self.snapshot('original')
        self.write(first)
        store.import_file(self.db, self.source)
        after = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        before = store.get_as_of(self.db, after)
        correction = self.snapshot('correction', '2026-01-01T12:05:00Z', '2026-01-01T12:06:00Z', supersedes_acquisition_id='original')
        self.write(correction)
        counts = store.import_file(self.db, self.source, simulated=True)
        self.assertEqual(counts['quarantined'], 1)
        self.assertEqual(store.get_as_of(self.db, after), before)
        self.assertEqual(store.get_as_of(self.db, after, clock_mode='synthetic_simulated'), [])
        self.assertEqual(len(store.get_quarantine(self.db, after, clock_mode='synthetic_simulated')), 1)
        self.assertEqual(store.get_quarantine(self.db, after), [])

    def test_separate_clock_modes_are_never_mixed(self):
        self.write(self.snapshot('operational'))
        store.import_file(self.db, self.source)
        self.write(self.snapshot('simulated'))
        store.import_file(self.db, self.source, simulated=True)
        after = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        self.assertEqual({x['acquisition_id'] for x in store.get_as_of(self.db, after)}, {'operational'})
        self.assertEqual({x['acquisition_id'] for x in store.get_as_of(self.db, after, clock_mode='synthetic_simulated')}, {'simulated'})
        with self.assertRaises(ValueError):
            store.get_as_of(self.db, after, clock_mode='unknown')

    def test_csv_import_keeps_original_values(self):
        row = self.snapshot()
        quotes = row.pop('quotes')
        with self.csv.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=[*row.keys(), 'outcome', 'odds_original', 'odds_format'])
            writer.writeheader()
            writer.writerows([{**row, **quote} for quote in quotes])
        self.assertEqual(store.import_file(self.db, self.csv, simulated=True)['inserted'], 1)
        self.assertEqual({x['odds_original'] for x in store.get_as_of(self.db, '2026-01-01T12:01:00Z', clock_mode='synthetic_simulated')}, {'2.00', '+250', '5/2'})


if __name__ == '__main__':
    unittest.main()

