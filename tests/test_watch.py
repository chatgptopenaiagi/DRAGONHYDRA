"""Live-style polling tests use workspace-owned files and no network."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import unittest
from uuid import uuid4

from dragonhydra import market_store, watch

ROOT = Path(__file__).resolve().parents[1]


class WatchTests(unittest.TestCase):
    def setUp(self):
        runtime=ROOT/'runtime'
        runtime.mkdir(exist_ok=True)
        stem='test-watch-'+uuid4().hex
        self.db=runtime/(stem+'.sqlite')
        self.source=runtime/(stem+'.json')
        for path in (self.db,self.source,Path(str(self.db)+'-journal'),Path(str(self.db)+'-wal'),Path(str(self.db)+'-shm')):
            self.addCleanup(path.unlink,missing_ok=True)
        self.item={'source_id':'local-feed', 'provider_id':'source-provider', 'feed_id':'feed-1',
                   'adapter_version':'watch-test/1', 'acquisition_id':'quote-1',
                   'data_origin':'captured_real','source_published_at':None,
                   'received_at':'2020-01-01T00:00:00Z','persisted_at':'2020-01-01T00:00:00Z',
                   'event_id':'watch-event','competition':'test-league', 'home':'Home','away':'Away',
                   'market_type':'1x2','period':'full_time','status':'pregame','settlement':'regulation_only','line':None,
                   'quotes':[{'outcome':'home','odds_original':'2.00','odds_format':'decimal'}]}
        self.put(self.item)

    def put(self,item):
        self.source.write_text(json.dumps({'snapshots':[item]}),encoding='utf-8')

    def test_bounded_change_detection_and_real_clocks(self):
        sleeps=[]
        def sleeper(interval):
            sleeps.append(interval)
            if len(sleeps)==2:
                newer=dict(self.item,acquisition_id='quote-2')
                newer['quotes']=[{'outcome':'home','odds_original':'2.10','odds_format':'decimal'}]
                self.put(newer)
        result=watch.watch_file(self.db,self.source,iterations=3,interval_seconds=0.1,sleeper=sleeper)
        self.assertEqual([e['status'] for e in result['events']],['IMPORTED','UNCHANGED','IMPORTED'])
        self.assertEqual(sleeps,[0.1,0.1])
        self.assertEqual(result['clock_mode'],'operational')
        self.assertEqual(result['stop_reason'],'ITERATION_LIMIT')
        self.assertEqual(result['iterations_completed'],3)
        for event in (result['events'][0],result['events'][2]):
            self.assertGreaterEqual(event['import']['data_commit_acknowledged_at'],event['observed_at'])
            self.assertGreaterEqual(event['import']['receipt_commit_acknowledged_at'],event['import']['data_commit_acknowledged_at'])
        cutoff=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        rows=market_store.get_as_of(self.db,cutoff)
        self.assertEqual({r['acquisition_id'] for r in rows},{'quote-1','quote-2'})
        self.assertTrue(all(r['received_at']>'2020-01-01' and r['usable_at']>=r['received_at'] for r in rows))
        self.assertEqual(market_store.get_as_of(self.db,'2020-01-02T00:00:00Z'),[])
        self.assertEqual(market_store.get_as_of(self.db,cutoff,clock_mode='synthetic_simulated'),[])

    def test_restart_same_file_is_idempotent(self):
        first=watch.watch_file(self.db,self.source,iterations=1)
        second=watch.watch_file(self.db,self.source,iterations=1)
        self.assertEqual(first['events'][0]['status'],'IMPORTED')
        self.assertEqual(second['events'][0]['status'],'DUPLICATE')
        self.assertEqual(second['events'][0]['import']['duplicates'],1)

    def test_conflicting_reused_acquisition_is_quarantined(self):
        watch.watch_file(self.db,self.source,iterations=1)
        changed=dict(self.item)
        changed['quotes']=[{'outcome':'home','odds_original':'2.50','odds_format':'decimal'}]
        self.put(changed)
        result=watch.watch_file(self.db,self.source,iterations=1)
        self.assertEqual(result['events'][0]['status'],'QUARANTINED')
        self.assertEqual(result['events'][0]['import']['quarantined'],1)
        self.assertEqual(result['research_tasks'][0]['gap'],'QUARANTINED_SNAPSHOT_RECORD')
        cutoff=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        rows=market_store.get_as_of(self.db,cutoff)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['odds_original'],'2.00')

    def test_invalid_and_missing_sources_generate_research_tasks(self):
        self.source.write_bytes(b'{invalid json')
        bad=watch.watch_file(self.db,self.source,iterations=1)
        event=bad['events'][0]
        self.assertEqual(event['status'],'INVALID_SNAPSHOT')
        self.assertEqual(bad['research_tasks'][0]['gap'],'INVALID_SNAPSHOT')
        self.assertEqual(market_store.raw_source(self.db,event['source_hash']),b'{invalid json')
        self.source.unlink()
        missing=watch.watch_file(self.db,self.source,iterations=1)
        self.assertEqual(missing['events'][0]['status'],'SOURCE_UNAVAILABLE')
        self.assertEqual(missing['research_tasks'][0]['gap'],'SNAPSHOT_SOURCE_UNAVAILABLE')

    def test_read_once_avoids_changed_file_race(self):
        old=self.source.read_bytes()
        changed=dict(self.item,acquisition_id='later')
        def reader(source):
            source.write_text(json.dumps({'snapshots':[changed]}),encoding='utf-8')
            return old
        report=watch.watch_file(self.db,self.source,iterations=1,reader=reader)
        self.assertEqual(report['events'][0]['source_hash'],hashlib.sha256(old).hexdigest())
        self.assertEqual(market_store.raw_source(self.db,report['events'][0]['source_hash']),old)
        cutoff=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        self.assertEqual(market_store.get_as_of(self.db,cutoff)[0]['acquisition_id'],'quote-1')

    def test_rejects_unbounded_invalid_and_outside_paths(self):
        for args in ({'iterations':0},{'iterations':1001},{'interval_seconds':-1},
                     {'interval_seconds':float('nan')},{'interval_seconds':10**500},{'iterations':1000,'interval_seconds':60}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                watch.watch_file(self.db,self.source,**args)
        with self.assertRaises(ValueError):
            watch.watch_file(self.db,self.source.with_suffix('.txt'))


if __name__=='__main__':
    unittest.main()
