import copy
from datetime import date, timedelta
import hashlib
import json
import unittest

from dragonhydra import public_results
from dragonhydra.cognition import adaptation, models


class AdaptationTests(unittest.TestCase):
    def setUp(self):
        self.cutoff='2026-01-02T12:00:00Z'
        self.target={'source_id':'source','competition':'league','period':'full_time','settlement':'source_full_time'}
        scope={k:self.target[k] for k in ('source_id','competition','period','settlement')}
        self.blobs={}
        start=date(2024,12,1)
        games=[{'date':(start+timedelta(days=i)).isoformat(),'team1':f'Home {i}',
                'team2':f'Away {i}','score':{'ft':[1,0]}} for i in range(21)]
        all_rows=self.make_rows(games,'capture','2026-01-01T00:00:00Z')
        self.sources=all_rows[:20]
        self.extra=all_rows[20]
        self.keys=[r['fixture_key'] for r in self.sources]
        self.outcomes=[{'fixture_key':r['fixture_key'],'source_id':'source','record_id':'outcome-'+r['fixture_key'],
                        'source_evidence_id':r['evidence_id'],'usable_at':'2026-01-01T00:00:00Z',
                        'received_at':'2026-01-01T00:00:00Z','persisted_at':'2026-01-01T00:00:00Z',
                        'supersedes_record_id':None} for r in self.sources]
        self.records=[{'record_id':'evaluation-'+name,'model':name,'model_version':models.VERSION,
                       'metric':'brier','evaluation_scope':scope,'sample_size':20,'fixture_keys':self.keys[:],
                       'received_at':'2026-01-01T01:00:00Z','persisted_at':'2026-01-01T01:00:00Z',
                       'usable_at':'2026-01-01T01:00:00Z',
                       'cases':[{'fixture_key':k,'outcome_record_id':'outcome-'+k} for k in self.keys]}
                      for name in models.NAMES]

    def make_rows(self,games,acquisition,usable):
        doc={'name':'league','matches':games}
        raw=json.dumps(doc,sort_keys=True,separators=(',',':')).encode('utf-8')
        digest=hashlib.sha256(raw).hexdigest()
        self.blobs[digest]=raw
        rows=[]
        for i,game in enumerate(games):
            row=public_results._match(doc['name'],game,i)
            identity=json.dumps(['source',acquisition,i],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
            row.update(source_id='source',acquisition_id=acquisition,source_hash=digest,
                       evidence_id=hashlib.sha256(identity).hexdigest(),data_origin='imported_historical',
                       source_published_at=None,received_at=usable,persisted_at=usable,usable_at=usable)
            rows.append(row)
        return rows

    def select(self,view,sources=None,cutoff=None,**kwargs):
        return adaptation.select(view,self.sources if sources is None else sources,self.target,
                self.cutoff if cutoff is None else cutoff,raw_resolver=lambda h:self.blobs.get(h,b''),**kwargs)

    def test_requires_raw_verification_and_same_sufficient_cohort(self):
        view={'evaluations':self.records,'outcomes':self.outcomes}
        no_resolver=adaptation.select(view,self.sources,self.target,self.cutoff)
        self.assertEqual(no_resolver['reason'],'EVALUATION_SOURCE_VERIFICATION_UNAVAILABLE')
        self.assertEqual(len(self.select(view)['records']),4)
        differing=copy.deepcopy(self.records)
        extra_key=self.extra['fixture_key']
        differing[-1]['fixture_keys'][-1]=extra_key
        differing[-1]['cases'][-1]={'fixture_key':extra_key,'outcome_record_id':'outcome-'+extra_key}
        extra_outcome={'fixture_key':extra_key,'source_id':'source','record_id':'outcome-'+extra_key,
                       'source_evidence_id':self.extra['evidence_id'],'usable_at':'2026-01-01T00:00:00Z',
                       'received_at':'2026-01-01T00:00:00Z','persisted_at':'2026-01-01T00:00:00Z'}
        result=self.select({'evaluations':differing,'outcomes':self.outcomes+[extra_outcome]},self.sources+[self.extra])
        self.assertEqual(result['reason'],'EVALUATION_COHORTS_DIFFER')
        insufficient=copy.deepcopy(self.records)
        insufficient[0]['sample_size']=1
        self.assertFalse(self.select({'evaluations':insufficient,'outcomes':self.outcomes})['records'])

    def test_source_hash_tampering_is_rejected(self):
        bad=copy.deepcopy(self.sources)
        bad[0]['source_hash']='0'*64
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):
            self.select({'evaluations':self.records,'outcomes':self.outcomes},bad)

    def test_future_receipt_with_forged_old_usable_time_cannot_disrupt_selection(self):
        view={'evaluations':self.records,'outcomes':self.outcomes}
        before=self.select(view)
        fake=copy.deepcopy(self.records[0])
        fake.update(record_id='future-evaluation',received_at='2099-01-01T00:00:00Z',
                    persisted_at='2099-01-01T00:00:01Z',usable_at='2026-01-01T01:00:00Z',
                    fixture_keys=['bad'],cases=[{'fixture_key':'bad'}])
        after=self.select({'evaluations':self.records+[fake],'outcomes':self.outcomes})
        self.assertEqual(before,after)

    def test_correction_invalidates_old_weight_only_after_its_cutoff(self):
        correction={'fixture_key':self.keys[0],'source_id':'source','record_id':'revised',
                    'source_evidence_id':'source-revised','usable_at':'2026-01-03T00:00:00Z',
                    'received_at':'2026-01-03T00:00:00Z','persisted_at':'2026-01-03T00:00:00Z',
                    'supersedes_record_id':'outcome-'+self.keys[0]}
        view={'evaluations':self.records,'outcomes':self.outcomes+[correction]}
        self.assertEqual(len(self.select(view)['records']),4)
        new_sources=[row for row in self.sources if row['fixture_key']!=self.keys[0]] + [
            {'fixture_key':self.keys[0],'source_id':'source','evidence_id':'source-revised','usable_at':correction['usable_at']}]
        later=self.select(view,new_sources,'2026-01-04T00:00:00Z')
        self.assertFalse(later['records'])
        self.assertEqual(later['reason'],'INSUFFICIENT_COMPARABLE_OPERATIONAL_EVALUATIONS')

    def test_rescheduled_fixture_invalidates_weights_only_after_arrival(self):
        newer=self.make_rows([{'date':'2024-12-31','team1':'Home 0','team2':'Away 0',
                               'score':{'ft':[2,0]}}], 'reschedule','2026-01-03T00:00:00Z')[0]
        sources=self.sources+[newer]
        view={'evaluations':self.records,'outcomes':self.outcomes}
        self.assertEqual(len(self.select(view,sources)['records']),4)
        later=self.select(view,sources,'2026-01-04T00:00:00Z')
        self.assertEqual(later['records'],[])
        self.assertEqual(later['reason'],'INSUFFICIENT_COMPARABLE_OPERATIONAL_EVALUATIONS')
        target=dict(self.target,fixture_key=self.sources[0]['fixture_key'])
        blocked=adaptation.select(view,sources,target,'2026-01-04T00:00:00Z',raw_resolver=lambda h:self.blobs.get(h,b''))
        self.assertEqual(blocked['reason'],'AMBIGUOUS_TARGET_FIXTURE')


if __name__=='__main__': unittest.main()
