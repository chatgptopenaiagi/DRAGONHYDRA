"""Project-local CLI verification using retained public source data and bounded clock fakes."""
import contextlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

from dragonhydra import cli, market_store, public_results, research


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'raw' / 'openfootball-2026-27-en1.json'
RECEIPT = ROOT / 'data' / 'raw' / 'openfootball-2026-27-en1.json.receipt.json'


class ForecastCLITests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(DATA.is_file(), 'Project OpenFootball dataset is required')
        self.assertTrue(RECEIPT.is_file(), 'Project capture receipt is required')
        self.raw = DATA.read_bytes()
        self.capture = json.loads(RECEIPT.read_text(encoding='utf-8-sig'))
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), self.capture['sha256'])
        self.db = ROOT / 'runtime' / ('forecast-test-' + uuid.uuid4().hex + '.sqlite3')
        self.assertTrue(self.db.parent.is_dir(), 'Project runtime directory is required')
        self.assertFalse(self.db.exists())
        self.addCleanup(self.cleanup_owned_database)
        self.source_capture = datetime.fromisoformat(self.capture['captured_at'].replace('Z', '+00:00'))
        self.recorded = self.source_capture + timedelta(seconds=5)
        self.decision = self.recorded + timedelta(seconds=1)
        self.computed = self.decision + timedelta(seconds=1)
        self.recorded_string = market_store.utc(self.recorded)
        self.decision_string = market_store.utc(self.decision)

    def cleanup_owned_database(self):
        for path in (self.db, Path(str(self.db) + '-journal'), Path(str(self.db) + '-wal'), Path(str(self.db) + '-shm')):
            if path.exists():
                path.unlink()

    def forecast(self):
        # The fake is bounded to the capture receipt; it keeps this test runnable
        # after the saved season's fixtures have passed. It is never production data.
        computed = self.computed
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return computed if tz is not None else computed.replace(tzinfo=None)
        output = io.StringIO()
        with patch.object(public_results, '_now', return_value=self.recorded_string), \
             patch.object(cli, '_cutoff', return_value=self.decision_string), \
             patch.object(research, 'datetime', FixedDatetime), \
             contextlib.redirect_stdout(output):
            code = cli.main(['forecast', '--db', str(self.db), '--file', str(DATA),
                             '--receipt', str(RECEIPT), '--format', 'json'])
        self.assertEqual(code, 0)
        return json.loads(output.getvalue())

    def test_cli_prior_links_real_source_and_never_backdates(self):
        report = self.forecast()
        before = market_store.utc(self.source_capture - timedelta(microseconds=1))
        self.assertEqual(public_results.get_as_of(self.db, before), [])
        all_rows = public_results.latest_as_of(self.db, self.decision_string)
        self.assertEqual(len(all_rows), len(json.loads(self.raw)['matches']))
        self.assertEqual(report['target']['source_hash'], self.capture['sha256'])
        self.assertEqual(report['target']['source_id'], self.capture['source_id'])
        self.assertEqual(report['target']['data_origin'], 'imported_historical')
        self.assertIsNone(report['target']['event_at_utc'])
        target_date = datetime.fromisoformat(report['target']['event_date']).date()
        self.assertGreater(target_date, self.decision.date() + timedelta(days=1))
        self.assertGreater(report['training_count'], 0)
        self.assertEqual(report['training_count'], len(report['training_manifest']))
        self.assertTrue(all(row['source_id'] == report['target']['source_id'] and
                            row['source_hash'] == self.capture['sha256'] and
                            row['competition'] == report['target']['competition'] and
                            row['period'] == report['target']['period'] and
                            row['settlement'] == report['target']['settlement'] and
                            row['event_date'] < report['target']['event_date'] and
                            row['usable_at'] <= self.decision_string
                            for row in report['training_manifest']))
        self.assertEqual(market_store.raw_source(self.db, self.capture['sha256']), self.raw)
        self.assertEqual(report['model_status'], 'ephemeral_current_calculation')
        self.assertIsNone(report['model_persisted_at'])
        self.assertGreaterEqual(research._time(report['model_usable_at']), research._time(self.decision_string))
        probabilities = [Decimal(report['probabilities'][outcome]['value']) for outcome in ('home', 'draw', 'away')]
        self.assertLessEqual(abs(sum(probabilities) - 1), Decimal('1e-27'))
        allowed = {report['target']['evidence_id'], report['configuration']['evidence_id']} | {
            row['evidence_id'] for row in report['training_manifest']}
        for metric in report['probabilities'].values():
            self.assertTrue(set(metric['evidence_ids']) <= allowed)
            self.assertEqual(metric['transformation']['version'], research.VERSION)

    def test_results_scope_stays_separate_after_forecast_import(self):
        self.forecast()
        source25 = ROOT / 'data' / 'raw' / 'openfootball-2025-26-en1.json'
        receipt25 = ROOT / 'data' / 'raw' / 'openfootball-2025-26-en1.json.receipt.json'
        self.assertTrue(source25.is_file())
        source25_receipt = json.loads(receipt25.read_text(encoding='utf-8-sig'))
        self.assertEqual(hashlib.sha256(source25.read_bytes()).hexdigest(), source25_receipt['sha256'])
        output = io.StringIO()
        with patch.object(public_results, '_now', return_value=self.recorded_string), \
             patch.object(cli, '_cutoff', return_value=self.decision_string), \
             contextlib.redirect_stdout(output):
            code = cli.main(['results', '--db', str(self.db), '--file', str(source25),
                             '--receipt', str(receipt25), '--limit', '0', '--format', 'json'])
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['eligible_count'], 380)
        self.assertEqual(report['summary']['eligible_result_count']['value'], 380)
        self.assertEqual([report['summary']['counts'][outcome]['value'] for outcome in ('home','draw','away')],
                         [162, 104, 114])
        self.assertEqual({row['source_id'] for row in report['summary']['evidence_manifest']},
                         {source25_receipt['source_id']})
        self.assertEqual({row['competition'] for row in report['summary']['evidence_manifest']},
                         {'English Premier League 2025/26'})
        self.assertEqual(len(public_results.latest_as_of(self.db,self.decision_string)),760)

    def test_stored_source_remains_ineligible_before_capture(self):
        self.forecast()
        before = market_store.utc(self.source_capture - timedelta(microseconds=1))
        self.assertEqual(public_results.get_as_of(self.db, before), [])
        # The capture itself is absent at this earlier cutoff even though its
        # source event dates and contents are now stored in the local database.
        self.assertEqual(public_results.latest_as_of(self.db, before), [])


if __name__ == '__main__':
    unittest.main()


