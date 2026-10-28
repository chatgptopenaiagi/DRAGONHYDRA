from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
import uuid

from dragonhydra import public_results as p


class PublicResultsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.doc = {'name': 'Example League', 'matches': [
            {'date':'2025-01-01','time':'12:00','team1':'A','team2':'B','score':{'ft':[2,1]}},
            {'date':'2025-01-02','team1':'C','team2':'D','score':[0,0]},
            {'date':'2025-01-03','team1':'E','team2':'F'}]}
        self.raw = json.dumps(self.doc).encode('utf-8')
        self.source = 'public-source'
        self.url = 'https://example.invalid/results.json'

    def put(self, raw=None, **kw):
        return p.ingest_bytes(self.db, self.raw if raw is None else raw, source_id=self.source,
                              source_url=self.url, acquisition_id=kw.pop('acquisition_id','a-1'), **kw)

    def test_actual_availability_raw_and_identity(self):
        imported = self.put()
        self.assertEqual(imported['inserted'], 3)
        self.assertEqual(imported['result_count'], 2)
        self.assertEqual(p.as_of(self.db,'2025-01-01T00:00:00Z'), [])
        rows = p.as_of(self.db, imported['usable_at'])
        self.assertEqual(len(rows), 3)
        self.assertEqual([x['outcome'] for x in rows], ['home','draw',None])
        self.assertEqual(rows[0]['event_date'],'2025-01-01')
        self.assertIsNone(rows[0]['event_at_utc'])
        self.assertIsNone(rows[0]['source_published_at'])
        self.assertEqual(rows[0]['source_local_time'],'12:00')
        self.assertEqual(rows[0]['source_hash'], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(rows[0]['data_origin'],'imported_historical')
        self.assertEqual(self.db.execute('SELECT bytes FROM raw_sources').fetchone()[0],self.raw)
        self.assertGreater(rows[0]['received_at'], '2025-01-01T00:00:00Z')
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("UPDATE public_fixture_records SET payload='{}'")

    def test_idempotence_collision_and_genuinely_later_capture(self):
        first = self.put()
        self.assertTrue(self.put()['duplicate'])
        with self.assertRaisesRegex(ValueError,'ACQUISITION_ID_COLLISION'):
            self.put(self.raw+b' ')
        second = self.put(acquisition_id='a-2')
        self.assertEqual(len(p.as_of(self.db, first['usable_at'])),3)
        self.assertEqual(len(p.as_of(self.db, second['usable_at'])),6)

    def test_later_correction_preserves_earlier_replay(self):
        first = self.put()
        before = p.latest(self.db,first['usable_at'])
        self.doc['matches'][0]['score']['ft'] = [1,2]
        second = self.put(json.dumps(self.doc).encode(),acquisition_id='correction')
        self.assertEqual(before,p.latest(self.db,first['usable_at']))
        rows = p.latest(self.db,second['usable_at'])
        corrected = next(x for x in rows if x['home']=='A')
        self.assertEqual(corrected['outcome'],'away')
        self.assertEqual(len(p.as_of(self.db,second['usable_at'])),6)

    def test_descriptive_distribution_has_evidence_and_respects_cutoff(self):
        imported = self.put()
        early = p.summarize(self.db,'2025-01-01T00:00:00Z')
        self.assertEqual(early['eligible_result_count']['value'],0)
        self.assertIsNone(early['proportions']['home']['value'])
        summary = p.summarize(self.db,imported['usable_at'])
        self.assertEqual(summary['eligible_result_count']['value'],2)
        self.assertEqual(summary['counts']['home']['value'],1)
        self.assertEqual(summary['counts']['draw']['value'],1)
        self.assertEqual(summary['proportions']['home']['value'],'0.5')
        self.assertEqual(len(summary['proportions']['home']['evidence_ids']),2)

    def test_unresolved_cross_source_identity_is_not_double_counted(self):
        self.put()
        second = p.ingest_bytes(self.db,self.raw,source_id='second-source',source_url=self.url,acquisition_id='b-1')
        summary = p.summarize(self.db,second['usable_at'])
        self.assertEqual(summary['eligible_result_count']['value'],0)
        self.assertEqual(len(summary['quality_flags']),2)
        self.assertTrue(all(x['code']=='AMBIGUOUS_CROSS_SOURCE_FIXTURE' for x in summary['quality_flags']))

    def test_summarize_as_of_restricts_selected_source_across_competitions(self):
        path = Path(__file__).resolve().parents[1] / 'runtime' / ('source-filter-test-' + uuid.uuid4().hex + '.sqlite3')
        self.assertFalse(path.exists())
        def cleanup():
            for owned in (path, Path(str(path)+'-journal'), Path(str(path)+'-wal'), Path(str(path)+'-shm')):
                if owned.exists():
                    owned.unlink()
        self.addCleanup(cleanup)
        with closing(sqlite3.connect(str(path))) as db:
            p.ingest_bytes(db,self.raw,source_id=self.source,source_url=self.url,acquisition_id='first')
            p.ingest_bytes(db,self.raw,source_id='same-competition',source_url=self.url,acquisition_id='second')
            other = dict(self.doc,name='Different League')
            last = p.ingest_bytes(db,json.dumps(other).encode(),source_id='different-competition',
                                  source_url=self.url,acquisition_id='third')
        chosen = p.summarize_as_of(path,last['usable_at'],source_id=self.source)
        self.assertEqual(chosen['eligible_result_count']['value'],2)
        self.assertEqual(chosen['counts']['home']['value'],1)
        self.assertEqual(chosen['counts']['draw']['value'],1)
        self.assertEqual({row['source_id'] for row in chosen['evidence_manifest']},{self.source})
        self.assertEqual(chosen['quality_flags'],[])
        all_sources = p.summarize_as_of(path,last['usable_at'])
        self.assertEqual(all_sources['eligible_result_count']['value'],2)
        self.assertEqual(len(all_sources['quality_flags']),2)

    def test_reschedule_or_repeat_is_quarantined_without_backdating(self):
        times=[p._utc(x) for x in ('2026-01-01T00:00:00Z','2026-01-01T00:00:01Z',
                                   '2026-01-01T00:00:02Z','2026-01-01T00:00:03Z')]
        with patch.object(p,'_now',side_effect=times):
            first=self.put()
            self.doc['matches'][0]['date']='2025-01-04'
            second=self.put(json.dumps(self.doc).encode(),acquisition_id='later-capture')
        before=p.latest(self.db,first['usable_at'])
        after=p.latest(self.db,second['usable_at'])
        self.assertEqual(p.find_ambiguous_fixtures(after,first['usable_at']),[])
        forged=dict(before[0],event_date='2025-01-09',fixture_key='fake-fixture',evidence_id='fake-evidence',
                    source_published_at='2026-01-02T00:00:00Z')
        self.assertEqual(p.find_ambiguous_fixtures(before+[forged],first['usable_at']),[])

        flags=p.find_ambiguous_fixtures(after,second['usable_at'])
        self.assertEqual(len(flags),1)
        self.assertEqual(flags[0]['code'],'AMBIGUOUS_FIXTURE_DATE')
        self.assertEqual(flags[0]['event_dates'],['2025-01-01','2025-01-04'])
        self.assertEqual(flags[0]['source_id'],self.source)
        self.assertEqual(len(flags[0]['evidence_ids']),2)
        self.assertEqual(p.summarize(self.db,first['usable_at'])['eligible_result_count']['value'],2)
        summary=p.summarize(self.db,second['usable_at'])
        self.assertEqual(summary['eligible_result_count']['value'],1)
        self.assertIn('AMBIGUOUS_FIXTURE_DATE',[flag['code'] for flag in summary['quality_flags']])
        self.assertEqual(len(p.as_of(self.db,second['usable_at'])),6)
        self.assertEqual(len(before),3)

    def test_repeated_same_pair_in_single_source_is_also_ambiguous(self):
        self.doc['matches'].append({'date':'2025-01-08','team1':'A','team2':'B','score':[0,1]})
        result=self.put(json.dumps(self.doc).encode())
        flags=p.find_ambiguous_fixtures(p.latest(self.db,result['usable_at']),result['usable_at'])
        self.assertEqual(len(flags),1)
        self.assertEqual(len(flags[0]['acquisition_ids']),1)
        self.assertEqual(len(flags[0]['event_dates']),2)
        self.assertEqual(p.summarize(self.db,result['usable_at'])['eligible_result_count']['value'],1)

    def test_quarantine_malformed_and_ambiguous_rows(self):
        self.doc['matches'].append(dict(self.doc['matches'][0]))
        self.doc['matches'].append({'date':'2025-01-04','team1':'G','team2':'H','score':[-1,0]})
        result = self.put(json.dumps(self.doc).encode())
        self.assertEqual(result['quarantined'],2)
        self.assertEqual(result['inserted'],3)

    def test_receipt_hash_is_verified_without_backdating(self):
        captured='2025-01-01T00:00:00Z'
        receipt={'source_id':self.source,'source_url':self.url,'sha256':hashlib.sha256(self.raw).hexdigest(),
                 'bytes':len(self.raw),'captured_at':captured,'usable_at':captured}
        result=self.put(source_receipt=receipt)
        rows=p.as_of(self.db,result['usable_at'])
        self.assertEqual(rows[0]['source_capture_at'],'2025-01-01T00:00:00.000000Z')
        self.assertNotEqual(rows[0]['usable_at'],captured)
        receipt['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'CAPTURE_RECEIPT_MISMATCH'):
            self.put(source_receipt=receipt,acquisition_id='bad')


if __name__ == '__main__':
    unittest.main()








