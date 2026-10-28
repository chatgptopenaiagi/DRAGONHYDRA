"""Tests for current imported-result prior; source contents are fictional test data."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import sqlite3
import unittest

from dragonhydra import public_results, research
from dragonhydra.cognition import models


class CurrentPriorTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        today = datetime.now(timezone.utc).date()
        def day(offset):
            return (today + timedelta(days=offset)).isoformat()
        doc = {'name':'Fictional Prior Test League','matches':[
            {'date':day(-10),'team1':'One','team2':'Two','score':{'ft':[1,0]}},
            {'date':day(-8),'team1':'Three','team2':'Four','score':{'ft':[0,0]}},
            {'date':day(5),'team1':'Five','team2':'Six'}]}
        self.doc=doc
        self.raw=json.dumps(doc).encode('utf-8')
        self.imported=public_results.ingest_bytes(self.db,self.raw,source_id='fictional-test-source',
             source_url='fictional:test-only',acquisition_id='sample')
        self.rows=public_results.as_of(self.db,self.imported['usable_at'])
        self.target=next(row for row in self.rows if row['result_state']=='unavailable')
        self.cutoff=self.imported['usable_at']
        self.resolve=lambda h:self.db.execute('SELECT bytes FROM raw_sources WHERE source_hash=?',(h,)).fetchone()[0]

    def prior(self,rows=None,target=None):
        return research.current_frequency_prior(self.rows if rows is None else rows,
                self.target if target is None else target,self.cutoff,self.resolve)

    def test_known_answer_and_input_provenance(self):
        out=self.prior()
        self.assertEqual(out['training_count'],2)
        self.assertEqual(out['counts']['home']['value'],'1')
        self.assertEqual(Decimal(out['probabilities']['home']['value']),Decimal('0.4'))
        self.assertEqual(Decimal(out['probabilities']['draw']['value']),Decimal('0.4'))
        self.assertEqual(Decimal(out['probabilities']['away']['value']),Decimal('0.2'))
        self.assertEqual(len(out['training_manifest']),2)
        self.assertIsNone(out['model_persisted_at'])
        self.assertGreaterEqual(research._time(out['model_usable_at']),research._time(self.cutoff))
        self.assertEqual(research._time(out['data_cutoff']),research._time(self.cutoff))
        self.assertEqual(research._time(out['decision_cutoff']),research._time(out['model_usable_at']))
        self.assertGreaterEqual(research._time(out['decision_cutoff']),research._time(out['configuration']['recorded_at']))

        self.assertIn(self.target['evidence_id'],out['probabilities']['home']['evidence_ids'])

    def test_future_ineligible_corruption_does_not_change_prior(self):
        earlier=self.prior()
        future=deepcopy(self.rows[0])
        future['usable_at']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        future['source_hash']='bad'
        future['outcome']='nonsense'
        later=self.prior(self.rows+[future])
        self.assertEqual(earlier['probabilities'],later['probabilities'])
        self.assertEqual(earlier['training_manifest'],later['training_manifest'])
        forged=deepcopy(self.rows[0])
        future_time=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        forged.update(received_at=future_time,persisted_at=future_time,usable_at=self.cutoff,
                      source_hash='bad',outcome='nonsense')
        after= self.prior(self.rows+[forged])
        self.assertEqual(earlier['probabilities'],after['probabilities'])
        self.assertEqual(earlier['training_manifest'],after['training_manifest'])
        future_published=deepcopy(self.rows[0])
        future_published.update(source_published_at=future_time,source_hash='bad',outcome='nonsense')
        after_published=self.prior(self.rows+[future_published])
        self.assertEqual(earlier['probabilities'],after_published['probabilities'])
        self.assertEqual(earlier['training_manifest'],after_published['training_manifest'])



    def test_target_date_ambiguity_abstains_without_backdating(self):
        before=self.prior()
        modified=deepcopy(self.doc)
        original_date=datetime.fromisoformat(modified['matches'][-1]['date']).date()
        modified['matches'][-1]['date']=(original_date+timedelta(days=1)).isoformat()
        captured=public_results.ingest_bytes(self.db,json.dumps(modified).encode(),
            source_id='fictional-test-source',source_url='fictional:test-only',acquisition_id='later')
        after=public_results.latest(self.db,captured['usable_at'])
        old=next(x for x in after if x['fixture_key']==self.target['fixture_key'])
        newer=next(x for x in after if x['home']=='Five' and x['event_date']==modified['matches'][-1]['date'])
        for candidate in (old,newer):
            with self.assertRaisesRegex(ValueError,'AMBIGUOUS_TARGET_FIXTURE'):
                research.current_frequency_prior(after,candidate,captured['usable_at'],self.resolve)
            with self.assertRaisesRegex(ValueError,'AMBIGUOUS_TARGET_FIXTURE'):
                models.forecast(after,candidate,captured['usable_at'],self.resolve)
        before_after=research.current_frequency_prior(public_results.latest(self.db,self.cutoff),
                                                      self.target,self.cutoff,self.resolve)
        self.assertEqual(before['probabilities'],before_after['probabilities'])
        self.assertEqual(before['training_manifest'],before_after['training_manifest'])

    def test_training_date_ambiguity_is_quarantined_and_reported(self):
        before=self.prior()
        modified=deepcopy(self.doc)
        original_date=datetime.fromisoformat(modified['matches'][0]['date']).date()
        modified['matches'][0]['date']=(original_date+timedelta(days=1)).isoformat()
        captured=public_results.ingest_bytes(self.db,json.dumps(modified).encode(),
            source_id='fictional-test-source',source_url='fictional:test-only',acquisition_id='later')
        after=public_results.latest(self.db,captured['usable_at'])
        target=next(x for x in after if x['fixture_key']==self.target['fixture_key'])
        result=research.current_frequency_prior(after,target,captured['usable_at'],self.resolve)
        self.assertEqual(result['training_count'],1)
        self.assertEqual(result['quality_flags'][0]['code'],'AMBIGUOUS_FIXTURE_DATE')
        self.assertEqual(len(result['quarantined_evidence']),2)
        self.assertEqual(result['research_tasks'][0]['gap'],'AMBIGUOUS_FIXTURE_DATE')
        self.assertEqual(set(result['quality_flags'][0]['evidence_ids']),
                         {row['evidence_id'] for row in result['quarantined_evidence']})
        forecast=models.forecast(after,target,captured['usable_at'],self.resolve)
        self.assertEqual(forecast['training_count'],1)
        self.assertEqual(forecast['quality_flags'][0]['code'],'AMBIGUOUS_FIXTURE_DATE')
        self.assertIn('AMBIGUOUS_FIXTURE_DATE',[task['gap'] for task in forecast['research_tasks']])
        self.assertEqual(before['probabilities'],self.prior()['probabilities'])

    def test_raw_hash_and_row_binding_are_required(self):
        changed=deepcopy(self.rows)
        changed[0]['outcome']='away'
        with self.assertRaisesRegex(ValueError,'SOURCE_RECORD_MISMATCH'):
            self.prior(changed)
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):
            research.current_frequency_prior(self.rows,self.target,self.cutoff,lambda _:b'wrong')

    def test_conflicting_duplicate_mapping_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_TRAINING_MAPPING'):
            self.prior(self.rows+[deepcopy(self.rows[0])])
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_TARGET_MAPPING'):
            self.prior(self.rows+[deepcopy(self.target)])

    def test_source_competition_and_date_boundaries(self):
        extra=deepcopy(self.rows[0])
        extra['source_id']='different-source'
        extra['competition']='Different League'
        out=self.prior(self.rows+[extra])
        self.assertEqual(out['training_count'],2)
        early=deepcopy(self.target)
        early['event_date']=datetime.now(timezone.utc).date().isoformat()
        with self.assertRaisesRegex(ValueError,'FUTURE_FIXTURE_TIME_UNCERTAIN'):
            self.prior(target=early)

    def test_insufficient_evidence_abstains(self):
        out=research.current_frequency_prior(self.rows,self.target,self.cutoff,self.resolve,minimum_training=3)
        self.assertTrue(out['abstained'])
        self.assertEqual(out['reason'],'INSUFFICIENT_ELIGIBLE_RESULTS')
        self.assertEqual(out['research_task']['gap'],'INSUFFICIENT_ELIGIBLE_RESULTS')
        self.assertEqual(research._time(out['data_cutoff']),research._time(self.cutoff))
        self.assertEqual(research._time(out['decision_cutoff']),research._time(out['model_usable_at']))
        self.assertGreaterEqual(research._time(out['decision_cutoff']),research._time(out['configuration']['recorded_at']))



if __name__=='__main__':
    unittest.main()




