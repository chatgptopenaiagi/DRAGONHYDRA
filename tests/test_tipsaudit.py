from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv
import hashlib
import unittest
from uuid import uuid4

from dragonhydra import market_signals, market_store, tipsaudit

ROOT = Path(__file__).resolve().parents[1]


class TipsAuditAdapterTests(unittest.TestCase):
    def setUp(self):
        self.runtime = ROOT / 'runtime'
        self.runtime.mkdir(exist_ok=True)
        prefix = 'test-tipsaudit-' + uuid4().hex
        self.source = self.runtime / (prefix + '.csv')
        self.db = self.runtime / (prefix + '.sqlite')
        self.addCleanup(self.source.unlink, missing_ok=True)
        self.addCleanup(self.db.unlink, missing_ok=True)
        self.row = {'id':'42', 'kickoff_utc':'2025-01-01T12:00:00+00:00', 'league':'Example League',
                    'home':'Example Home', 'away':'Example Away', 'record_hash':'example-record', 'result':'X', 'void_reason':'',
                    'pin_open_home':'2.100','pin_open_draw':'3.200','pin_open_away':'3.400',
                    'pin_close_home':'2.000','pin_close_draw':'3.300','pin_close_away':'3.500'}
        with self.source.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.row))
            writer.writeheader()
            writer.writerow(self.row)

    def test_import_archival_claims_uses_actual_knowledge_time(self):
        raw = self.source.read_bytes()
        receipt = tipsaudit.import_event(self.db, self.source, '42')
        self.assertEqual(receipt['inserted'], 6)
        self.assertEqual(receipt['source_hash'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(market_store.raw_source(self.db, receipt['source_hash']), raw)
        self.assertEqual(market_store.get_as_of(self.db, '2025-01-02T00:00:00Z'), [])
        future = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        rows = market_store.get_as_of(self.db, future)
        self.assertEqual(len(rows), 6)
        self.assertEqual({r['data_origin'] for r in rows}, {'imported_historical'})
        self.assertEqual({r['quote_phase'] for r in rows}, {'source_open','source_close'})
        self.assertTrue(all(r['source_result'] == 'X' and r['result_time_known'] is False for r in rows))
        self.assertTrue(all(r['quote_time_known'] is False for r in rows))
        self.assertTrue(all(r['synchronization_proven'] is False for r in rows))
        self.assertTrue(all(r['source_published_at'] is None for r in rows))
        self.assertTrue(all(r['period']=='unknown' and r['settlement']=='unknown' and r['status']=='unknown' for r in rows))
        self.assertEqual({r['odds_original'] for r in rows}, {'2.100','3.200','3.400','2.000','3.300','3.500'})
        self.assertEqual(len({r['snapshot_id'] for r in rows}), 6)
        self.assertEqual(tipsaudit.import_event(self.db, self.source, '42')['duplicates'], 6)

    def test_best_soft_provider_labels_are_not_normalized_or_assumed_synchronized(self):
        self.row.update(best_soft_home='2.200', best_soft_book_home='Betfair',
                        best_soft_draw='3.400', best_soft_book_draw='Matchbook',
                        best_soft_away='3.600', best_soft_book_away='')
        with self.source.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(self.row)); writer.writeheader(); writer.writerow(self.row)
        imported=tipsaudit.import_event(self.db,self.source,'42')
        self.assertEqual(imported['inserted'],8)
        self.assertEqual(imported['skipped_unlabelled_best_soft_outcomes'],['away'])
        cutoff=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        rows=market_store.get_as_of(self.db,cutoff)
        soft=[r for r in rows if r['quote_phase']=='source_best_soft']
        self.assertEqual({r['source_provider_label'] for r in soft},{'Betfair','Matchbook'})
        self.assertEqual({r['provider_id'] for r in soft},{'unverified-source-label:Betfair','unverified-source-label:Matchbook'})
        self.assertTrue(all(r['provider_mapping_verified'] is False and r['quote_time_known'] is False for r in soft))
        self.assertTrue(all('exchange status unverified' in r['provider_mapping_basis'] for r in soft))
        signals=market_signals.compute_signals(rows,cutoff)
        self.assertTrue(all(x['decimal_odds_difference']['value'] is None for x in signals['provider_divergences']))
        self.assertFalse(signals['best_price_discrepancies'])

    def test_event_list_and_bad_id(self):
        result = tipsaudit.list_events(self.source, limit=1)
        self.assertEqual(result['events'][0]['source_event_id'], '42')
        self.assertIn('quote timestamps', result['timing_limit'])
        with self.assertRaisesRegex(ValueError, 'absent or ambiguous'):
            tipsaudit.import_event(self.db, self.source, '404')
        with self.assertRaises(ValueError):
            tipsaudit.list_events(self.source, limit=101)


if __name__ == '__main__':
    unittest.main()
