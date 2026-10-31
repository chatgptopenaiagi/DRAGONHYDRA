import csv
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import unittest
from uuid import uuid4

from dragonhydra import football_data, market_signals, market_store

ROOT = Path(__file__).resolve().parents[1]


class FootballDataAdapterTests(unittest.TestCase):
    def setUp(self):
        runtime = ROOT / 'runtime'
        runtime.mkdir(exist_ok=True)
        name = 'test-football-data-' + uuid4().hex
        self.source = runtime / (name + '.csv')
        self.db = runtime / (name + '.sqlite')
        self.addCleanup(self.source.unlink, missing_ok=True)
        self.addCleanup(self.db.unlink, missing_ok=True)
        self.row = {'Div':'E0', 'Date':'15/08/2025', 'Time':'20:00', 'HomeTeam':'Home FC',
                    'AwayTeam':'Away FC', 'FTHG':'4', 'FTAG':'2', 'FTR':'H',
                    'B365H':'1.30','B365D':'6.00','B365A':'8.50',
                    'B365CH':'1.29','B365CD':'6.25','B365CA':'9.00',
                    'PSH':'1.28','PSD':'6.56','PSA':'9.07',
                    'PSCH':'1.29','PSCD':'6.55','PSCA':'9.75'}
        self.write_rows(self.row)

    def write_rows(self, *rows):
        with self.source.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(self.row)); writer.writeheader(); writer.writerows(rows)

    def test_source_labels_raw_receipt_and_cutoff(self):
        raw = self.source.read_bytes()
        listing = football_data.list_events(self.source,limit=1)
        event = listing['events'][0]
        self.assertEqual((event['home'],event['away']),('Home FC','Away FC'))
        result=football_data.import_event(self.db,self.source,event['source_event_id'])
        self.assertEqual(result['inserted'],12)
        self.assertEqual(result['source_hash'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(market_store.raw_source(self.db,result['source_hash']),raw)
        self.assertEqual(market_store.get_as_of(self.db,'2025-08-15T20:00:00Z'),[])
        cutoff=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        rows=market_store.get_as_of(self.db,cutoff)
        self.assertEqual(len(rows),12)
        self.assertEqual({r['source_provider_label'] for r in rows},{'B365','PS'})
        self.assertEqual({r['feed_id'] for r in rows},{'football-data-shared-archive'})
        self.assertEqual({r['quote_phase'] for r in rows},{'source_recorded','source_close'})
        self.assertTrue(all(r['provider_mapping_verified'] is False and r['quote_time_known'] is False for r in rows))
        self.assertTrue(all(r['synchronization_proven'] is False and r['result_time_known'] is False for r in rows))
        self.assertTrue(all(r['source_match_date']=='15/08/2025' and r['source_match_time']=='20:00' for r in rows))
        self.assertTrue(all(r['source_result']=='H' and r['source_score_home']=='4' for r in rows))
        self.assertTrue(all(r['period']=='unknown' and r['status']=='unknown' and r['settlement']=='unknown' for r in rows))
        self.assertEqual({r['source_column'] for r in rows}, set(football_data.FIELDS['B365']['source_recorded'] +
            football_data.FIELDS['B365']['source_close'] + football_data.FIELDS['PS']['source_recorded'] + football_data.FIELDS['PS']['source_close']))
        self.assertEqual(football_data.import_event(self.db,self.source,event['source_event_id'])['duplicates'],12)
        signals=market_signals.compute_signals(rows,cutoff)
        self.assertEqual(len(signals['quote_metrics']),12)
        self.assertTrue(all(q['quote_age']['value'] is None for q in signals['quote_metrics']))
        self.assertTrue(all(m['overround']['value'] is None for m in signals['overrounds']))
        self.assertTrue(all(d['decimal_odds_difference']['value'] is None for d in signals['provider_divergences']))
        self.assertFalse(signals['best_price_discrepancies'])

    def test_duplicate_fixture_is_quarantined_from_identity_mapping(self):
        self.write_rows(self.row,self.row)
        event=football_data.list_events(self.source,limit=1)['events'][0]['source_event_id']
        with self.assertRaisesRegex(ValueError,'absent or ambiguous'):
            football_data.import_event(self.db,self.source,event)

    def test_blank_and_invalid_prices_do_not_become_fabricated_quotes(self):
        self.row['B365H']=''
        self.row['B365D']='NaN'
        self.write_rows(self.row)
        event=football_data.list_events(self.source,limit=1)['events'][0]['source_event_id']
        result=football_data.import_event(self.db,self.source,event)
        self.assertEqual(result['inserted'],10)
        self.assertEqual(result['quarantined'],1)
        cutoff=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        rows=market_store.get_as_of(self.db,cutoff)
        self.assertNotIn('B365H',{r['source_column'] for r in rows})
        self.assertNotIn('B365D',{r['source_column'] for r in rows})
        self.assertEqual(len(market_store.get_quarantine(self.db,cutoff)),1)


if __name__=='__main__':
    unittest.main()
