import json
import sqlite3
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from dragonhydra import market_store, public_results
from dragonhydra.cognition import evaluation, memory, models


class CognitiveMemoryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.t0 = datetime.now(timezone.utc).replace(microsecond=0)
        self.clock = self.t0
        self.event_day = (self.t0 + timedelta(days=5)).date()
        train_day = (self.t0 - timedelta(days=10)).date()
        self.doc = {'name':'Memory Test League','matches':[
            {'date':str(train_day),'team1':'Alpha','team2':'Beta','score':{'ft':[2,1]}},
            {'date':str(self.event_day),'team1':'Gamma','team2':'Delta'}]}
        self.now_patch = patch.object(memory,'_now',side_effect=lambda:self.iso(self.clock))
        self.pub_patch = patch.object(public_results,'_now',side_effect=lambda:self.iso(self.clock))
        self.now_patch.start(); self.pub_patch.start()
        self.addCleanup(self.now_patch.stop); self.addCleanup(self.pub_patch.stop)
        self.raw = json.dumps(self.doc).encode()
        first = public_results.ingest_bytes(self.db,self.raw,source_id='source',source_url='https://example.invalid',acquisition_id='source-1')
        rows = public_results.as_of(self.db,first['usable_at'])
        self.training = next(r for r in rows if r['outcome']=='home')
        self.target = next(r for r in rows if r['outcome'] is None)
        self.clock += timedelta(seconds=5)
        self.model_draft = {'run_id':'model-run-1','model_name':'frequency','model_version':'v1',
            'data_cutoff':first['usable_at'],'input_evidence_ids':[self.training['evidence_id']],
            'parameters':{'alpha':'1','target_evidence_id':self.target['evidence_id'],
                'result':{'probabilities':{'home':{'value':'0.5'},'draw':{'value':'0.25'},'away':{'value':'0.25'}}}},
            'configuration':{'source':'fixture'},'transformation':'smoothed frequency/1'}

    @staticmethod
    def iso(value):
        return value.isoformat(timespec='microseconds').replace('+00:00','Z')

    def model(self):
        return memory._record_model_run(self.db,self.model_draft)

    def prediction(self,model):
        self.clock += timedelta(seconds=5)
        return memory._record_prediction(self.db, {'run_id':'prediction-run-1','model_run_id':model['record_id'],
             'target_evidence_id':self.target['evidence_id'], 'probabilities':{'home':'0.5','draw':'0.25','away':'0.25'},
             'transformation':'frequency model output/1'})

    def later_source(self,home=1,away=0,acquisition='source-2'):
        self.clock = self.t0 + timedelta(days=8)
        self.doc['matches'][1]['score'] = {'ft':[home,away]}
        imported=public_results.ingest_bytes(self.db,json.dumps(self.doc).encode(),source_id='source',
                       source_url='https://example.invalid',acquisition_id=acquisition)
        row=next(r for r in public_results.as_of(self.db,imported['usable_at'])
                 if r['acquisition_id']==acquisition and r['home']=='Gamma')
        return imported,row

    def test_model_prediction_are_immutable_and_provenance_bound(self):
        first=self.model()
        self.assertTrue(memory._record_model_run(self.db,self.model_draft)['duplicate'])
        predicted=self.prediction(first)
        records=memory._as_of(self.db,predicted['usable_at'])
        self.assertEqual(len(records['models']),1)
        self.assertEqual(len(records['predictions']),1)
        prediction=records['predictions'][0]
        self.assertEqual(prediction['target_evidence_id'],self.target['evidence_id'])
        self.assertEqual(prediction['input_evidence_ids'],[self.training['evidence_id']])
        self.assertEqual(prediction['predicted_at'],predicted['usable_at'])
        self.assertEqual(prediction['decision_cutoff'],predicted['usable_at'])
        self.assertEqual(prediction['probabilities']['home'],'0.5')
        self.assertEqual(prediction['availability_mode'],'OPERATIONAL_AS_OF_RECEIPT')
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("UPDATE cognitive_records SET payload='{}'")

    def test_unknown_evidence_or_future_model_cutoff_rejected(self):
        bad=dict(self.model_draft,input_evidence_ids=['fabricated'])
        with self.assertRaisesRegex(ValueError,'MODEL_INPUT_NOT_ELIGIBLE'):
            memory._record_model_run(self.db,bad)
        future=dict(self.model_draft,data_cutoff=self.iso(self.clock+timedelta(days=1)))
        with self.assertRaisesRegex(ValueError,'MODEL_DATA_CUTOFF_IN_FUTURE'):
            memory._record_model_run(self.db,future)

    def test_prediction_cannot_misstate_stored_model_probabilities(self):
        model=self.model()
        self.clock += timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError,'MODEL_OUTPUT_PROBABILITY_MISMATCH'):
            memory._record_prediction(self.db, {'run_id':'bad-prediction','model_run_id':model['record_id'],
                'target_evidence_id':self.target['evidence_id'],
                'probabilities':{'home':'0.6','draw':'0.2','away':'0.2'},'transformation':'submitted'})

    def test_model_rejects_fabricated_target_and_embedded_evidence(self):
        bad=dict(self.model_draft)
        bad['parameters']=dict(self.model_draft['parameters'],target_evidence_id='fabricated-target')
        with self.assertRaisesRegex(ValueError,'MODEL_TARGET_NOT_ELIGIBLE'):
            memory._record_model_run(self.db,bad)
        bad=dict(self.model_draft)
        bad['parameters']=json.loads(json.dumps(self.model_draft['parameters']))
        bad['parameters']['result']['probabilities']['home']['evidence_ids']=['fabricated-evidence']
        with self.assertRaisesRegex(ValueError,'UNKNOWN_MODEL_EVIDENCE_REFERENCE'):
            memory._record_model_run(self.db,bad)

    def test_model_requires_exact_configuration_hash_and_eligible_inputs(self):
        values={'smoothing':1,'language':'équipes'}
        raw=json.dumps(values,sort_keys=True,separators=(',', ':'),allow_nan=False).encode('utf-8')
        digest=__import__('hashlib').sha256(raw).hexdigest()
        config={'evidence_id':'config:'+digest,'source_hash':digest,'source_id':'model_configuration',
                'data_origin':'configuration','recorded_at':self.iso(self.clock),'values':values}
        draft=dict(self.model_draft,configuration=config)
        draft['parameters']=json.loads(json.dumps(self.model_draft['parameters']))
        draft['parameters']['result']['probabilities']['home']['evidence_ids']=[
            config['evidence_id'],self.training['evidence_id'],self.target['evidence_id']]
        result=memory._record_model_run(self.db,draft)
        self.assertFalse(result['duplicate'])
        bad=dict(draft,run_id='bad-config')
        bad['configuration']=dict(config,source_hash='0'*64)
        with self.assertRaisesRegex(ValueError,'INVALID_CONFIGURATION_EVIDENCE'):
            memory._record_model_run(self.db,bad)

    def test_hypothesis_cannot_become_model_evidence(self):
        hypothesis={'hypothesis_id':'non-authoritative','revision':1,'claim':'An untested explanation.',
                    'supporting_evidence_ids':[self.training['evidence_id']], 'contradicting_evidence_ids':[],
                    'assumptions':[],'missing_information':['validation'],'next_question':'Is this true?'}
        saved=memory._record_hypothesis(self.db,hypothesis)
        self.clock += timedelta(seconds=1)
        draft=json.loads(json.dumps(self.model_draft))
        draft['data_cutoff']=saved['usable_at']
        draft['parameters']['result']['probabilities']['home']['evidence_ids']=[saved['record_id']]
        with self.assertRaisesRegex(ValueError,'MODEL_NON_EVIDENCE_REFERENCE'):
            memory._record_model_run(self.db,draft)

    def test_model_does_not_use_superseded_training_revision(self):
        self.clock += timedelta(seconds=1)
        self.doc['matches'][0]['score']={'ft':[0,1]}
        revised=public_results.ingest_bytes(self.db,json.dumps(self.doc).encode(),source_id='source',
                                             source_url='https://example.invalid',acquisition_id='revision')
        self.clock += timedelta(seconds=1)
        stale=dict(self.model_draft,data_cutoff=revised['usable_at'])
        with self.assertRaisesRegex(ValueError,'MODEL_INPUT_NOT_ELIGIBLE'):
            memory._record_model_run(self.db,stale)

    def test_model_rejects_ambiguous_rescheduled_target_as_of_new_capture(self):
        self.clock += timedelta(seconds=1)
        self.doc['matches'].append({'date':str(self.event_day+timedelta(days=1)),
                                    'team1':'Gamma','team2':'Delta'})
        changed=public_results.ingest_bytes(self.db,json.dumps(self.doc).encode(),source_id='source',
                                             source_url='https://example.invalid',acquisition_id='rescheduled')
        rows=public_results.latest(self.db,changed['usable_at'])
        training=next(r for r in rows if r['home']=='Alpha')
        target=next(r for r in rows if r['home']=='Gamma' and r['event_date']==str(self.event_day))
        draft=json.loads(json.dumps(self.model_draft))
        draft['data_cutoff']=changed['usable_at']
        draft['input_evidence_ids']=[training['evidence_id']]
        draft['parameters']['target_evidence_id']=target['evidence_id']
        self.clock += timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_MODEL_TARGET_FIXTURE'):
            memory._record_model_run(self.db,draft)

    def test_outcome_only_after_later_source_and_isolation(self):
        model=self.model(); pred=self.prediction(model)
        before=memory._as_of(self.db,pred['usable_at'])
        imported,row=self.later_source()
        self.clock += timedelta(seconds=3)
        outcome=memory._record_outcome(self.db,row['evidence_id'])
        self.assertEqual(memory._as_of(self.db,pred['usable_at']),before)
        at=memory._as_of(self.db,outcome['usable_at'])
        self.assertEqual(len(at['outcomes']),1)
        self.assertEqual(at['outcomes'][0]['outcome'],'home')
        self.assertEqual(at['outcomes'][0]['source_evidence_id'],row['evidence_id'])
        self.assertGreater(at['outcomes'][0]['source_usable_at'],pred['usable_at'])
        self.assertTrue(memory._record_outcome(self.db,row['evidence_id'])['duplicate'])

    def test_outcome_revision_does_not_mutate_earlier_result(self):
        model=self.model(); self.prediction(model)
        _,old=self.later_source()
        self.clock += timedelta(seconds=2)
        oldrec=memory._record_outcome(self.db,old['evidence_id'])
        old_view=memory._as_of(self.db,oldrec['usable_at'])
        self.clock += timedelta(seconds=5)
        self.doc['matches'][1]['score']={'ft':[0,1]}
        second=public_results.ingest_bytes(self.db,json.dumps(self.doc).encode(),source_id='source',
                                            source_url='https://example.invalid',acquisition_id='correction')
        row=next(x for x in public_results.as_of(self.db,second['usable_at']) if x['acquisition_id']=='correction' and x['home']=='Gamma')
        self.clock += timedelta(seconds=2)
        newrec=memory._record_outcome(self.db,row['evidence_id'])
        self.assertEqual(memory._as_of(self.db,oldrec['usable_at']),old_view)
        latest=memory._as_of(self.db,newrec['usable_at'])['outcomes']
        self.assertEqual(len(latest),2)
        self.assertEqual(latest[-1]['outcome'],'away')
        self.assertEqual(latest[-1]['supersedes_record_id'],oldrec['record_id'])
        self.assertTrue(memory._record_outcome(self.db,old['evidence_id'])['duplicate'])
        duplicate = memory._record_prediction(self.db, {'run_id':'prediction-run-1','model_run_id':model['record_id'],
            'target_evidence_id':self.target['evidence_id'],'probabilities':{'home':'0.5','draw':'0.25','away':'0.25'},
            'transformation':'frequency model output/1'})
        self.assertTrue(duplicate['duplicate'])

    def test_outcome_requires_earlier_prediction(self):
        _,row=self.later_source()
        with self.assertRaisesRegex(ValueError,'NO_EARLIER_ELIGIBLE_PREDICTION'):
            memory._record_outcome(self.db,row['evidence_id'])

    def test_ambiguous_reschedule_cannot_attach_outcome_or_change_earlier_memory(self):
        model=self.model(); pred=self.prediction(model)
        before=memory._as_of(self.db,pred['usable_at'])
        self.clock=self.t0+timedelta(days=8)
        self.doc['matches'][1]['score']={'ft':[2,0]}
        self.doc['matches'].append({'date':str(self.event_day+timedelta(days=1)),
                                    'team1':'Gamma','team2':'Delta'})
        changed=public_results.ingest_bytes(self.db,json.dumps(self.doc).encode(),source_id='source',
                                            source_url='https://example.invalid',acquisition_id='ambiguous')
        row=next(r for r in public_results.as_of(self.db,changed['usable_at'])
                 if r['acquisition_id']=='ambiguous' and r['outcome']=='home' and r['home']=='Gamma')
        self.clock += timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_OUTCOME_FIXTURE'):
            memory._record_outcome(self.db,row['evidence_id'])
        self.assertEqual(memory._as_of(self.db,pred['usable_at']),before)

    def test_research_tasks_validate_references_and_cutoff(self):
        draft={'gap':'missing_odds','question':'Can quotes be captured?', 'permitted_source':'local feed',
               'priority_rationale':'market coverage is missing', 'expected_evidence':'quote snapshot',
               'budget':'one source check', 'stopping_condition':'snapshot captured or unavailable',
               'evidence_ids':['fabricated']}
        with self.assertRaisesRegex(ValueError,'UNKNOWN_TASK_EVIDENCE'):
            memory._record_research_task(self.db,draft)
        draft['evidence_ids']=[self.training['evidence_id']]
        before=self.iso(self.clock-timedelta(seconds=1))
        task=memory._record_research_task(self.db,draft)
        self.assertEqual(memory._as_of(self.db,before)['research_tasks'],[])
        self.assertEqual(memory._as_of(self.db,task['usable_at'])['research_tasks'][0]['gap'],'missing_odds')
        self.assertTrue(memory._record_research_task(self.db,draft)['duplicate'])

    def test_hypothesis_rejects_fabricated_evidence_and_out_of_order_revision(self):
        draft={'hypothesis_id':'h1','revision':1,'claim':'The pattern may persist.',
               'supporting_evidence_ids':['fabricated'],'contradicting_evidence_ids':[],
               'assumptions':['Source identity is correct.'],'missing_information':['Another observation'],
               'next_question':'Does the pattern persist?'}
        with self.assertRaisesRegex(ValueError,'UNKNOWN_HYPOTHESIS_EVIDENCE'):
            memory._record_hypothesis(self.db,draft)
        draft['supporting_evidence_ids']=[self.training['evidence_id']]
        draft['revision']=2
        with self.assertRaisesRegex(ValueError,'HYPOTHESIS_REVISION_OUT_OF_ORDER'):
            memory._record_hypothesis(self.db,draft)
        draft['revision']=1
        draft['contradicting_evidence_ids']=[self.training['evidence_id']]
        with self.assertRaisesRegex(ValueError,'CONFLICTING_HYPOTHESIS_EVIDENCE_LINK'):
            memory._record_hypothesis(self.db,draft)

    def test_hypothesis_revisions_are_append_only_and_cutoff_isolated(self):
        draft={'hypothesis_id':'h1','revision':1,'claim':'The initial claim is uncertain.',
               'supporting_evidence_ids':[self.training['evidence_id']], 'contradicting_evidence_ids':[],
               'assumptions':['Source identity is correct.'], 'missing_information':['Further observation'],
               'next_question':'What does the next observation show?','source_id':'cognitive-research'}
        first=memory._record_hypothesis(self.db,draft)
        before=memory._as_of(self.db,first['usable_at'])['hypotheses']
        self.clock += timedelta(seconds=3)
        revision=dict(draft,revision=2,claim='A competing interpretation remains possible.',
                      contradicting_evidence_ids=[self.target['evidence_id']])
        second=memory._record_hypothesis(self.db,revision)
        self.assertEqual(memory._as_of(self.db,first['usable_at'])['hypotheses'],before)
        versions=memory._as_of(self.db,second['usable_at'])['hypotheses']
        self.assertEqual([item['revision'] for item in versions],[1,2])
        self.assertEqual(versions[1]['supersedes_record_id'],first['record_id'])
        self.assertEqual(versions[1]['source_id'],'cognitive-research')
        self.assertEqual(memory._resolve_evidence(self.db,first['record_id'],second['usable_at'])['evidence_id'],first['record_id'])
        self.assertTrue(memory._record_hypothesis(self.db,draft)['duplicate'])
        with self.assertRaisesRegex(ValueError,'MEMORY_IDENTITY_COLLISION'):
            memory._record_hypothesis(self.db,dict(draft,claim='Changed without a revision.'))
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("DELETE FROM cognitive_records WHERE kind='hypothesis'")

    def test_hypothesis_marks_unsupported_claim(self):
        draft={'hypothesis_id':'unproven','revision':1,'claim':'A possible explanation.',
               'supporting_evidence_ids':[],'contradicting_evidence_ids':[],'assumptions':[],
               'missing_information':['Independent corroboration'],'next_question':'What evidence supports this?'}
        saved=memory._record_hypothesis(self.db,draft)
        item=memory._as_of(self.db,saved['usable_at'])['hypotheses'][0]
        self.assertTrue(item['unsupported_claim'])

    def test_hypothesis_cannot_reference_a_later_memory_record(self):
        early=self.clock
        self.clock += timedelta(seconds=5)
        task=memory._record_research_task(self.db,{'gap':'missing','question':'What is missing?',
             'permitted_source':'source','priority_rationale':'coverage','expected_evidence':'record',
             'budget':'one check','stopping_condition':'resolved','evidence_ids':[]})
        hypothesis={'hypothesis_id':'future-link','revision':1,'claim':'Later information exists.',
                    'supporting_evidence_ids':[task['record_id']],'contradicting_evidence_ids':[],
                    'assumptions':[],'missing_information':[],'next_question':'Can this be checked?'}
        self.clock=early
        with self.assertRaisesRegex(ValueError,'UNKNOWN_HYPOTHESIS_EVIDENCE'):
            memory._record_hypothesis(self.db,hypothesis)
        self.clock=early+timedelta(seconds=6)
        self.assertFalse(memory._record_hypothesis(self.db,hypothesis)['duplicate'])

    def test_ambiguous_source_evidence_is_flagged_for_research_and_not_asserted(self):
        self.clock += timedelta(seconds=1)
        self.doc['matches'].append({'date':str(self.event_day+timedelta(days=1)),
                                    'team1':'Gamma','team2':'Delta'})
        changed=public_results.ingest_bytes(self.db,json.dumps(self.doc).encode(),source_id='source',
                                             source_url='https://example.invalid',acquisition_id='ambiguous-task')
        target=next(r for r in public_results.latest(self.db,changed['usable_at'])
                    if r['home']=='Gamma' and r['event_date']==str(self.event_day))
        self.clock += timedelta(seconds=1)
        evidence_id=target['evidence_id']
        task={'gap':'AMBIGUOUS_FIXTURE_DATE','question':'Are these two separate fixtures?',
              'permitted_source':'source schedule','priority_rationale':'identity needs proof',
              'expected_evidence':'verified fixture mapping','budget':'one source check',
              'stopping_condition':'mapping verified or unavailable','evidence_ids':[evidence_id]}
        saved=memory._record_research_task(self.db,task)
        stored=memory._as_of(self.db,saved['usable_at'])['research_tasks'][0]
        self.assertEqual(stored['quality_flags'][0]['code'],'AMBIGUOUS_FIXTURE_EVIDENCE')
        hypothesis={'hypothesis_id':'ambiguous','revision':1,'claim':'This fixture is known.',
                    'supporting_evidence_ids':[evidence_id],'contradicting_evidence_ids':[],
                    'assumptions':[],'missing_information':['identity resolution'],'next_question':'Which date is correct?'}
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_HYPOTHESIS_EVIDENCE'):
            memory._record_hypothesis(self.db,hypothesis)

    def test_evaluation_is_recomputed_from_observed_outcomes_and_resolvable(self):
        self.model_draft['model_version']=models.VERSION
        model=self.model(); prediction=self.prediction(model)
        self.clock += timedelta(seconds=1)
        draft={'run_id':'evaluation-1','model_name':'frequency','model_version':models.VERSION,
               'competition':'Memory Test League','source_id':'source','period':'full_time',
               'settlement':'source_full_time','metric':'brier','evaluation_cutoff':self.iso(self.clock),
               'loss':999,'sample_size':999}
        with patch.object(evaluation,'_bound',side_effect=evaluation._utc):
            with self.assertRaisesRegex(ValueError,'NO_SCORED_OPERATIONAL_PREDICTIONS'):
                memory._record_evaluation(self.db,draft)
            _,source=self.later_source()
            self.clock += timedelta(seconds=2)
            outcome=memory._record_outcome(self.db,source['evidence_id'])
            cutoff=outcome['usable_at']
            self.clock += timedelta(seconds=3)
            draft['evaluation_cutoff']=cutoff
            saved=memory._record_evaluation(self.db,draft)
        self.assertGreater(saved['usable_at'],cutoff)
        self.assertIsNone(memory._resolve_evidence(self.db,saved['record_id'],cutoff))
        evidence=memory._resolve_evidence(self.db,saved['record_id'],saved['usable_at'])
        self.assertEqual(evidence['source_hash'],saved['record_content_hash'])
        payload=json.loads(evidence['source_raw'])
        self.assertEqual(payload['sample_size'],1)
        self.assertAlmostEqual(payload['loss'],0.375)
        self.assertEqual(payload['fixture_keys'],[self.target['fixture_key']])
        self.assertEqual(payload['coverage']['evaluated'],1)
        self.assertEqual(len(payload['calibration_bins']),15)
        self.assertIn(prediction['record_id'],payload['supporting_evidence_ids'])
        self.assertIn(outcome['record_id'],payload['supporting_evidence_ids'])
        for eid in payload['supporting_evidence_ids']:
            self.assertIsNotNone(memory._resolve_evidence(self.db,eid,payload['evaluation_end']))
        with patch.object(evaluation,'_bound',side_effect=evaluation._utc):
            self.assertTrue(memory._record_evaluation(self.db,draft)['duplicate'])
            earlier=memory._as_of(self.db,saved['usable_at'])['evaluations']
            self.clock += timedelta(seconds=2)
            self.doc['matches'].append({'date':str(self.event_day+timedelta(days=1)),
                                        'team1':'Gamma','team2':'Delta'})
            changed=public_results.ingest_bytes(self.db,json.dumps(self.doc).encode(),source_id='source',
                                                source_url='https://example.invalid',acquisition_id='ambiguous-after-outcome')
            self.clock += timedelta(seconds=2)
            next_draft=dict(draft,run_id='evaluation-after-conflict',evaluation_cutoff=changed['usable_at'])
            with self.assertRaisesRegex(ValueError,'EVALUATION_FIXTURE_MAPPING_AMBIGUOUS'):
                memory._record_evaluation(self.db,next_draft)
            self.assertEqual(memory._as_of(self.db,saved['usable_at'])['evaluations'],earlier)


class MarketEvidenceHypothesisTests(unittest.TestCase):
    def test_hypothesis_resolves_retained_operational_market_quote(self):
        root=Path(__file__).resolve().parents[1]
        db=root/'runtime'/('hypothesis-test-'+uuid4().hex+'.sqlite3')
        for path in (db,Path(str(db)+'-journal'),Path(str(db)+'-wal'),Path(str(db)+'-shm')):
            self.addCleanup(path.unlink,missing_ok=True)
        market_store.import_file(db,root/'examples'/'synthetic-market.json',simulated=False)
        cutoff=memory._now()
        quote=market_store.get_as_of(db,cutoff,clock_mode='operational')[0]
        draft={'hypothesis_id':'market-h1','revision':1,'claim':'A quoted price was observed.',
               'supporting_evidence_ids':[quote['evidence_id']],'contradicting_evidence_ids':[],
               'assumptions':['The source preserves the quotation.'],'missing_information':['Independent confirmation'],
               'next_question':'Can another quote be captured?'}
        saved=memory.record_hypothesis(db,draft)
        resolved=memory.resolve_evidence(db,quote['evidence_id'],saved['usable_at'])
        self.assertEqual(resolved['source_hash'],quote['source_hash'])
        self.assertEqual(resolved['odds_original'],quote['odds_original'])
        self.assertIsNone(memory.resolve_evidence(db,quote['evidence_id'],'2020-01-01T00:00:00Z'))

    def test_quote_with_valid_hash_but_fabricated_price_is_rejected(self):
        root=Path(__file__).resolve().parents[1]
        db=root/'runtime'/('hypothesis-tamper-test-'+uuid4().hex+'.sqlite3')
        for path in (db,Path(str(db)+'-journal'),Path(str(db)+'-wal'),Path(str(db)+'-shm')):
            self.addCleanup(path.unlink,missing_ok=True)
        raw=(root/'examples'/'synthetic-market.json').read_bytes()
        fabricated=json.loads(raw)['snapshots'][0]
        fabricated['quotes'][0]['odds_original']='99.99'
        market_store._import_records(db,raw,[fabricated],captured_at=memory._now())
        cutoff=memory._now()
        quote=market_store.get_as_of(db,cutoff,clock_mode='operational')[0]
        with self.assertRaisesRegex(ValueError,'MARKET_SOURCE_BINDING_UNPROVED'):
            memory.resolve_evidence(db,quote['evidence_id'],cutoff)


if __name__ == '__main__':
    unittest.main()
