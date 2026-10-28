import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import unittest

from dragonhydra import public_results
from dragonhydra.cognition import evaluation


def fixture_set(count=12):
    games=[]
    for i in range(count):
        day=(datetime(2020,1,1)+timedelta(days=i)).date().isoformat()
        score=((2,1),(1,1),(0,1))[i%3]
        games.append({'date':day, 'team1':f'Home {i}', 'team2':f'Away {i}', 'score':{'ft':list(score)}})
    doc={'name':'Test League','matches':games}
    raw=json.dumps(doc,sort_keys=True,separators=(',',':')).encode()
    digest=hashlib.sha256(raw).hexdigest()
    rows=[]
    for i,game in enumerate(games):
        item=public_results._match(doc['name'],game,i)
        identity=json.dumps(['test-source','one',i],sort_keys=True,separators=(',',':')).encode()
        item.update(source_id='test-source',acquisition_id='one',source_hash=digest,
                    evidence_id=hashlib.sha256(identity).hexdigest(),data_origin='imported_historical',
                    source_published_at=None,received_at='2021-01-01T00:00:00Z',
                    persisted_at='2021-01-01T00:00:01Z',usable_at='2021-01-01T00:00:02Z')
        rows.append(item)
    return rows,raw


class ChronologicalHoldoutTests(unittest.TestCase):
    cutoff='2026-01-01T00:00:00Z'

    def test_known_scores(self):
        probs,brier,loss=evaluation._score({'home':'0.5','draw':'0.3','away':'0.2'},'home')
        self.assertAlmostEqual(brier,0.38)
        self.assertAlmostEqual(loss,-math.log(.5))
        with self.assertRaises(ValueError): evaluation._score({'home':'0.7','draw':'0.3','away':'0.3'},'home')
        with self.assertRaises(ValueError): evaluation._score({'home':'NaN','draw':'0.3','away':'0.7'},'home')

    def test_real_provenance_holdout_is_present_knowledge(self):
        rows,raw=fixture_set()
        x=evaluation.chronological_holdout(rows,self.cutoff,lambda _:raw,source_id='test-source',
                                            holdout_fraction='0.25',minimum_training=3)
        self.assertEqual(x['mode'],'PRESENT_KNOWLEDGE_CHRONOLOGICAL_HOLDOUT')
        self.assertEqual(x['dataset_count'],12)
        self.assertEqual(x['metrics']['brier']['sample_size'],3)
        self.assertEqual(x['coverage']['fraction'],1.0)
        self.assertTrue(all(c['training_latest_event_date'] < c['event_date'] for c in x['cases']))
        self.assertTrue(all(c['target_evidence_id'] in c['evidence_ids'] for c in x['cases']))
        self.assertTrue(any('not a historical STRICT_PIT' in a for a in x['assumptions']))
        for case in x['cases']:
            self.assertAlmostEqual(sum(case['probabilities'].values()),1.0)
        bins=[b for b in x['calibration_bins'] if b['outcome']=='home']
        self.assertEqual(sum(b['sample_size'] for b in bins),3)

    def test_later_evidence_cannot_change_cutoff(self):
        rows,raw=fixture_set()
        before=evaluation.chronological_holdout(rows,self.cutoff,lambda _:raw,minimum_training=3)
        future=copy.deepcopy(rows[-1])
        future.update(usable_at='2099-01-01T00:00:00Z',source_hash='x',outcome='fabricated')
        after=evaluation.chronological_holdout(rows+[future],self.cutoff,lambda _:raw,minimum_training=3)
        self.assertEqual(before['cases'],after['cases'])
        self.assertEqual(before['metrics'],after['metrics'])
        self.assertEqual(before['calibration_bins'],after['calibration_bins'])

    def test_future_receipt_with_forged_old_usable_time_is_not_historical_evidence(self):
        rows,raw=fixture_set()
        before=evaluation.chronological_holdout(rows,self.cutoff,lambda _:raw,minimum_training=3)
        future=copy.deepcopy(rows[-1])
        future.update(received_at='2099-01-01T00:00:00Z',persisted_at='2099-01-01T00:00:01Z',
                      usable_at='2021-01-01T00:00:02Z',source_hash='bad',outcome='fabricated')
        after=evaluation.chronological_holdout(rows+[future],self.cutoff,lambda _:raw,minimum_training=3)
        self.assertEqual(before['cases'],after['cases'])
        self.assertEqual(before['metrics'],after['metrics'])

    def test_rescheduled_fixture_quarantines_both_dates_only_after_arrival(self):
        rows,raw=fixture_set()
        later_doc={'name':'Test League','matches':[{'date':'2020-12-31','team1':'Home 0','team2':'Away 0'}]}
        later_raw=json.dumps(later_doc,sort_keys=True,separators=(',',':')).encode()
        changed=public_results._match(later_doc['name'],later_doc['matches'][0],0)
        identity=json.dumps(['test-source','reschedule',0],sort_keys=True,separators=(',',':')).encode()
        changed.update(source_id='test-source',acquisition_id='reschedule',
            source_hash=hashlib.sha256(later_raw).hexdigest(),evidence_id=hashlib.sha256(identity).hexdigest(),
            data_origin='imported_historical',source_published_at=None,
            received_at='2025-01-01T00:00:00Z',persisted_at='2025-01-01T00:00:01Z',usable_at='2025-01-01T00:00:02Z')
        sources={hashlib.sha256(raw).hexdigest():raw,hashlib.sha256(later_raw).hexdigest():later_raw}
        resolve=lambda digest:sources[digest]
        earlier=evaluation.chronological_holdout(rows,'2024-01-01T00:00:00Z',resolve,minimum_training=3)
        prior=evaluation.chronological_holdout(rows+[changed],'2024-01-01T00:00:00Z',resolve,minimum_training=3)
        self.assertEqual(earlier['cases'],prior['cases'])
        self.assertEqual(prior['quality_flags'],[])
        after=evaluation.chronological_holdout(rows+[changed],self.cutoff,resolve,minimum_training=3)
        self.assertEqual(after['dataset_count'],11)
        self.assertEqual({rows[0]['evidence_id'],changed['evidence_id']},set(after['excluded_ambiguous_evidence_ids']))
        self.assertEqual(after['quality_flags'][0]['code'],'AMBIGUOUS_FIXTURE_DATE')

    def test_tampered_source_or_mapping_rejected(self):
        rows,raw=fixture_set()
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):
            evaluation.chronological_holdout(rows,self.cutoff,lambda _:raw+b'x',minimum_training=3)
        changed=copy.deepcopy(rows)
        changed[0]['outcome']='away'
        with self.assertRaisesRegex(ValueError,'SOURCE_RECORD_MISMATCH'):
            evaluation.chronological_holdout(changed,self.cutoff,lambda _:raw,minimum_training=3)

    def test_unknown_or_insufficient_data_abstains(self):
        rows,raw=fixture_set(2)
        result=evaluation.chronological_holdout(rows,self.cutoff,lambda _:raw,minimum_training=20)
        self.assertEqual(result['metrics']['brier']['sample_size'],0)
        self.assertIsNone(result['metrics']['brier']['value'])
        self.assertEqual(result['coverage']['evaluated'],0)

    def test_requires_single_source_competition_scope(self):
        rows,raw=fixture_set()
        other=copy.deepcopy(rows[0]); other['source_id']='other-source'
        identity=json.dumps(['other-source','one',0],sort_keys=True,separators=(',',':')).encode()
        other['evidence_id']=hashlib.sha256(identity).hexdigest()
        with self.assertRaisesRegex(ValueError,'MULTIPLE_COMPETITION_SCOPES'):
            evaluation.chronological_holdout(rows+[other],self.cutoff,lambda _:raw,minimum_training=3)

class OperationalEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.pred={'record_id':'prediction-1','fixture_key':'fixture-1', 'competition':'League',
                   'home':'Home','away':'Away','event_date':'2025-01-04',
                   'market_type':'1x2','period':'full_time','settlement':'source_full_time',
                   'model_name':'frequency','model_version':'v1',
                   'predicted_at':'2025-01-01T12:00:00Z','decision_cutoff':'2025-01-01T11:00:00Z',
                   'received_at':'2025-01-01T12:00:00Z','persisted_at':'2025-01-01T12:00:00Z',
                   'usable_at':'2025-01-01T12:00:00Z','target_evidence_id':'target', 'target_evidence':{'source_id':'unit-source'},
                   'input_evidence_ids':['training-1'],'probabilities':{'home':'0.5','draw':'0.3','away':'0.2'}}
        self.outcome={'record_id':'outcome-1','fixture_key':'fixture-1','competition':'League',
                      'home':'Home','away':'Away','event_date':'2025-01-04','outcome':'home',
                      'market_type':'1x2','period':'full_time','settlement':'source_full_time','source_id':'unit-source',
                      'source_evidence_id':'source-result-1','source_usable_at':'2025-01-04T20:00:00Z',
                      'received_at':'2025-01-04T20:01:00Z','persisted_at':'2025-01-04T20:02:00Z',
                      'usable_at':'2025-01-04T20:03:00Z'}

    def evaluate(self,predictions=None,outcomes=None,cutoff='2025-02-01T00:00:00Z'):
        return evaluation.evaluate_observed({'predictions':predictions if predictions is not None else [self.pred],
                                             'outcomes':outcomes if outcomes is not None else [self.outcome]},cutoff)

    def test_future_memory_receipt_cannot_disrupt_earlier_evaluation(self):
        before=self.evaluate()
        future=copy.deepcopy(self.pred)
        future.update(record_id='future-prediction',received_at='2026-01-01T00:00:00Z',
                      persisted_at='2026-01-01T00:00:01Z',usable_at='2025-01-01T12:00:00Z',
                      probabilities={'home':'invalid'})
        after=self.evaluate(predictions=[self.pred,future])
        self.assertEqual(before['groups'],after['groups'])

    def test_persisted_prediction_scores_only_after_outcome(self):
        early=self.evaluate(cutoff='2025-01-04T20:02:59Z')
        self.assertEqual(early['groups'][0]['metrics']['brier']['sample_size'],0)
        self.assertEqual(early['unscored'][0]['reason'],'OUTCOME_UNAVAILABLE')
        at=self.evaluate(cutoff='2025-01-04T20:03:00Z')
        self.assertEqual(at['groups'][0]['metrics']['brier']['sample_size'],1)
        self.assertAlmostEqual(at['groups'][0]['metrics']['brier']['value'],0.38)
        self.assertEqual(at['groups'][0]['metrics']['accuracy']['value'],1.0)
        self.assertIn('source-result-1',at['groups'][0]['cases'][0]['evidence_ids'])

    def test_correction_does_not_rewrite_earlier_evaluation(self):
        correction=copy.deepcopy(self.outcome)
        correction.update(record_id='outcome-2',outcome='away',source_evidence_id='source-result-2',
                          supersedes_record_id='outcome-1',source_usable_at='2025-01-10T00:00:00Z',
                          received_at='2025-01-10T00:00:00Z',persisted_at='2025-01-10T00:00:00Z',
                          usable_at='2025-01-10T00:00:00Z')
        before=self.evaluate(outcomes=[self.outcome,correction],cutoff='2025-01-09T00:00:00Z')
        after=self.evaluate(outcomes=[self.outcome,correction],cutoff='2025-01-10T00:00:00Z')
        self.assertEqual(before['groups'][0]['cases'][0]['actual_outcome'],'home')
        self.assertEqual(after['groups'][0]['cases'][0]['actual_outcome'],'away')
        self.assertNotEqual(before['groups'][0]['metrics']['brier']['value'],after['groups'][0]['metrics']['brier']['value'])

    def test_outcome_known_before_prediction_never_scores_even_after_correction(self):
        old=copy.deepcopy(self.outcome)
        old.update(source_usable_at='2025-01-01T10:00:00Z')
        later=copy.deepcopy(self.outcome)
        later.update(record_id='outcome-2',supersedes_record_id='outcome-1',
                     source_evidence_id='source-result-2',source_usable_at='2025-01-10T00:00:00Z',
                     received_at='2025-01-10T00:00:00Z',persisted_at='2025-01-10T00:00:00Z',usable_at='2025-01-10T00:00:00Z')
        result=self.evaluate(outcomes=[old,later])
        self.assertEqual(result['unscored'][0]['reason'],'OUTCOME_KNOWN_AT_PREDICTION')

    def test_ambiguous_and_mismatched_outcomes_abstain(self):
        conflicting=copy.deepcopy(self.outcome); conflicting['record_id']='different-source-outcome'
        result=self.evaluate(outcomes=[self.outcome,conflicting])
        self.assertEqual(result['unscored'][0]['reason'],'AMBIGUOUS_OUTCOME_REVISIONS')
        conflicting['away']='Different'
        result=self.evaluate(outcomes=[conflicting])
        self.assertEqual(result['unscored'][0]['reason'],'FIXTURE_MAPPING_CONFLICT')

    def test_prediction_missing_pre_game_time_abstains(self):
        late=copy.deepcopy(self.pred)
        for key in ('predicted_at','received_at','persisted_at','usable_at'):
            late[key]='2025-01-03T13:00:00Z'
        result=self.evaluate(predictions=[late])
        self.assertEqual(result['unscored'][0]['reason'],'PREGAME_TIMING_UNPROVEN')

    def test_model_groups_and_unscored_coverage_have_provenance(self):
        another=copy.deepcopy(self.pred)
        another.update(record_id='prediction-2',model_name='poisson',model_version='v2')
        result=self.evaluate(predictions=[self.pred,another])
        self.assertEqual({group['model_name'] for group in result['groups']},{'frequency','poisson'})
        no_result=self.evaluate(predictions=[self.pred,another],outcomes=[])
        for group in no_result['groups']:
            self.assertEqual(group['coverage']['eligible_candidates'],1)
            self.assertTrue(group['coverage']['evidence_ids'])

    def test_performance_groups_preserve_source_and_settlement_scope(self):
        other_prediction=copy.deepcopy(self.pred)
        other_prediction.update(record_id='prediction-2',fixture_key='fixture-2',target_evidence={'source_id':'second-source'})
        other_outcome=copy.deepcopy(self.outcome)
        other_outcome.update(record_id='outcome-2',fixture_key='fixture-2',source_id='second-source',
                             source_evidence_id='source-result-2')
        result=self.evaluate(predictions=[self.pred,other_prediction],outcomes=[self.outcome,other_outcome])
        scopes=[group['evaluation_scope'] for group in result['groups']]
        self.assertEqual({scope['source_id'] for scope in scopes},{'unit-source','second-source'})
        self.assertTrue(all(scope['settlement']=='source_full_time' for scope in scopes))
        self.assertTrue(all(group['metrics']['brier']['sample_size']==1 for group in result['groups']))

    def test_same_fixture_from_separate_sources_scores_each_only_against_its_source(self):
        other_prediction=copy.deepcopy(self.pred)
        other_prediction.update(record_id='prediction-source-2',target_evidence={'source_id':'second-source'})
        other_outcome=copy.deepcopy(self.outcome)
        other_outcome.update(record_id='outcome-source-2',source_id='second-source',
                             source_evidence_id='result-source-2',outcome='away')
        result=self.evaluate(predictions=[self.pred,other_prediction],outcomes=[self.outcome,other_outcome])
        self.assertEqual(len(result['groups']),2)
        self.assertEqual(result['unscored'],[])
        by_source={group['evaluation_scope']['source_id']:group for group in result['groups']}
        self.assertEqual(by_source['unit-source']['cases'][0]['actual_outcome'],'home')
        self.assertEqual(by_source['second-source']['cases'][0]['actual_outcome'],'away')

    def test_earliest_prediction_per_fixture_is_scored_once(self):
        later=copy.deepcopy(self.pred)
        later.update(record_id='prediction-later',probabilities={'home':'0.2','draw':'0.3','away':'0.5'})
        for key in ('predicted_at','decision_cutoff','received_at','persisted_at','usable_at'):
            later[key]='2025-01-02T12:00:00Z'
        # Reverse input order to prove the cohort uses time, not list order.
        result=self.evaluate(predictions=[later,self.pred])
        group=result['groups'][0]
        self.assertEqual(result['eligible_prediction_count'],2)
        self.assertEqual(result['cohort_prediction_count'],1)
        self.assertEqual(group['coverage']['eligible_candidates'],1)
        self.assertEqual(group['metrics']['brier']['sample_size'],1)
        self.assertAlmostEqual(group['metrics']['brier']['value'],0.38)
        self.assertEqual(group['cases'][0]['prediction_record_id'],'prediction-1')
        self.assertIn({'prediction_id':'prediction-later','reason':'DUPLICATE_FIXTURE_PREDICTION',
                       'retained_prediction_id':'prediction-1'},result['unscored'])
        before=self.evaluate(predictions=[later,self.pred],outcomes=[],cutoff='2025-01-02T11:59:59Z')
        self.assertEqual(before['cohort_prediction_count'],1)
        self.assertFalse(any(item['reason']=='DUPLICATE_FIXTURE_PREDICTION' for item in before['unscored']))

    def test_equal_receipt_times_use_stable_record_id_tiebreak(self):
        earlier_id=copy.deepcopy(self.pred)
        earlier_id.update(record_id='prediction-0',probabilities={'home':'0.2','draw':'0.3','away':'0.5'})
        a=self.evaluate(predictions=[self.pred,earlier_id])
        b=self.evaluate(predictions=[earlier_id,self.pred])
        self.assertEqual(a['groups'],b['groups'])
        self.assertEqual(a['groups'][0]['cases'][0]['prediction_record_id'],'prediction-0')
        self.assertEqual(a['groups'][0]['metrics']['brier']['sample_size'],1)


class MemoryEvaluationIntegrationTests(unittest.TestCase):
    def test_attach_ignores_source_outcome_already_known_before_prediction(self):
        """Exercise the defensive SQLite scan even with an invalid injected record.

        The public memory API prevents such a prediction in normal operation; the
        test deliberately injects one to verify attachment independently fails closed.
        """
        from pathlib import Path
        import sqlite3
        from contextlib import closing
        from unittest.mock import patch
        from uuid import uuid4
        from dragonhydra.cognition import memory, runtime
        root=Path(__file__).resolve().parents[1]
        db_path=root/'runtime'/('test-evaluation-known-'+uuid4().hex+'.sqlite')
        self.addCleanup(db_path.unlink,missing_ok=True)
        for suffix in ('-journal','-wal','-shm'):
            self.addCleanup(Path(str(db_path)+suffix).unlink,missing_ok=True)
        doc={'name':'League','matches':[{'date':'2025-01-10','team1':'Home','team2':'Away','score':{'ft':[1,0]}}]}
        payload=json.dumps(doc,sort_keys=True,separators=(',',':')).encode()
        with closing(sqlite3.connect(db_path)) as db, patch.object(public_results,'_now',return_value='2025-01-13T00:00:00.000000Z'):
            public_results.ingest_bytes(db,payload,source_id='unit-source',source_url='unit-test',acquisition_id='known-result')
        outcome=public_results.get_as_of(db_path,'2025-01-13T00:00:00Z')[0]
        # Intentionally bypass record_prediction only to create adversarial test
        # input; production callers cannot persist this post-result forecast.
        fake={'run_id':'adversarial','fixture_key':outcome['fixture_key'],
              'competition':outcome['competition'],'home':outcome['home'],'away':outcome['away'],
              'event_date':outcome['event_date'],'market_type':outcome['market_type'],
              'period':outcome['period'],'settlement':outcome['settlement'],
              'target_evidence':{'source_id':'unit-source'},'model_name':'frequency',
              'model_version':'test','probabilities':{'home':'0.5','draw':'0.3','away':'0.2'}}
        with closing(sqlite3.connect(db_path)) as db, patch.object(memory,'_now',return_value='2025-01-14T00:00:00.000000Z'):
            memory._append(db,'prediction','adversarial:frequency',fake,'2025-01-14T00:00:00.000000Z')
        with patch.object(runtime,'now',return_value='2025-01-15T00:00:00.000000Z'), \
             patch.object(memory,'_now',return_value='2025-01-15T00:00:00.000000Z'):
            result=runtime.attach_later_outcomes(db_path)
        self.assertEqual(result['attached'],[])
        self.assertEqual([item['reason'] for item in result['pending']],['NO_EARLIER_ELIGIBLE_PREDICTION'])
        self.assertEqual(memory.as_of(db_path,'2025-01-15T00:00:00Z')['outcomes'],[])

    def test_memory_prediction_and_later_outcome_are_scored_at_actual_receipt_boundaries(self):
        from pathlib import Path
        import sqlite3
        from unittest.mock import patch
        from contextlib import closing
        from uuid import uuid4
        from dragonhydra.cognition import memory, models, runtime
        root=Path(__file__).resolve().parents[1]
        db_path=root/'runtime'/('test-evaluation-'+uuid4().hex+'.sqlite')
        self.addCleanup(db_path.unlink,missing_ok=True)
        for suffix in ('-journal','-wal','-shm'):
            self.addCleanup(Path(str(db_path)+suffix).unlink,missing_ok=True)
        training={'date':'2024-12-01','team1':'Old Home','team2':'Old Away','score':{'ft':[2,1]}}
        target={'date':'2025-01-10','team1':'Home','team2':'Away'}
        def raw(match):
            return json.dumps({'name':'League','matches':[training,match]},sort_keys=True,separators=(',',':')).encode()
        def ingest(payload, acquisition, stamp):
            with closing(sqlite3.connect(db_path)) as db, patch.object(public_results,'_now',return_value=stamp):
                return public_results.ingest_bytes(db,payload,source_id='unit-source',source_url='unit-test',acquisition_id=acquisition)
        ingest(raw(target),'first','2025-01-01T00:00:00.000000Z')
        source=public_results.get_as_of(db_path,'2025-01-02T00:00:00.000000Z')
        train=next(x for x in source if x['home']=='Old Home')
        fixture=next(x for x in source if x['home']=='Home')
        with patch.object(memory,'_now',return_value='2025-01-02T00:00:00.000000Z'):
            model=memory.record_model_run(db_path,{'run_id':'unit-run','model_name':'frequency','model_version':models.VERSION,
                'data_cutoff':'2025-01-01T00:00:00.000000Z','input_evidence_ids':[train['evidence_id']],
                'parameters':{'smoothing':'1','target_evidence_id':fixture['evidence_id'],
                              'result':{'probabilities':{'home':'0.5','draw':'0.3','away':'0.2'}}},
                'configuration':{},'transformation':'unit test model'})
            prediction=memory.record_prediction(db_path,{'run_id':'unit-run','model_run_id':model['record_id'],
                'target_evidence_id':fixture['evidence_id'],'probabilities':{'home':'0.5','draw':'0.3','away':'0.2'},
                'transformation':'unit test prediction'})
        with patch.object(memory,'_now',return_value='2025-01-03T00:00:00.000000Z'):
            second_model=memory.record_model_run(db_path,{'run_id':'unit-run-2','model_name':'frequency','model_version':models.VERSION,
                'data_cutoff':'2025-01-01T00:00:00.000000Z','input_evidence_ids':[train['evidence_id']],
                'parameters':{'smoothing':'1','target_evidence_id':fixture['evidence_id'],
                              'result':{'probabilities':{'home':'0.5','draw':'0.3','away':'0.2'}}},
                'configuration':{},'transformation':'unit test model'})
            second_prediction=memory.record_prediction(db_path,{'run_id':'unit-run-2','model_run_id':second_model['record_id'],
                'target_evidence_id':fixture['evidence_id'],'probabilities':{'home':'0.5','draw':'0.3','away':'0.2'},
                'transformation':'unit test prediction'})
        earlier=memory.as_of(db_path,'2025-01-05T00:00:00Z')
        before=evaluation.evaluate_observed(earlier,'2025-01-05T00:00:00Z')
        self.assertEqual(before['groups'][0]['metrics']['brier']['sample_size'],0)
        self.assertEqual(before['cohort_prediction_count'],1)
        self.assertIn('DUPLICATE_FIXTURE_PREDICTION',{item['reason'] for item in before['unscored']})
        finished=dict(target,score={'ft':[1,0]})
        # Unit-only adversarial clocks simulate an illicit early outcome claim.
        # The source claims knowledge before the event or prediction; the real
        # memory path refuses it and does not attach an outcome.
        ingest(raw(finished),'adversarial-early','2025-01-01T12:00:00.000000Z')
        with patch.object(runtime,'now',return_value='2025-01-05T00:00:00.000000Z'), \
             patch.object(memory,'_now',return_value='2025-01-05T00:00:00.000000Z'):
            rejected=runtime.attach_later_outcomes(db_path)
        self.assertEqual(rejected['attached'],[])
        self.assertIn('OUTCOME_TIME_NOT_PROVABLY_POST_EVENT',{item['reason'] for item in rejected['pending']})
        self.assertEqual(memory.as_of(db_path,'2025-01-05T00:00:00Z')['outcomes'],[])
        ingest(raw(finished),'second','2025-01-13T00:00:00.000000Z')
        updated=public_results.get_as_of(db_path,'2025-01-13T00:00:00.000000Z')
        outcome=next(x for x in updated if x['home']=='Home' and x['outcome']=='home' and x['acquisition_id']=='second')
        # The later, physically present result must remain invisible at an
        # earlier cutoff even when the scan is run after it was imported.
        with patch.object(runtime,'now',return_value='2025-01-12T00:00:00.000000Z'), \
             patch.object(memory,'_now',return_value='2025-01-12T00:00:00.000000Z'):
            isolated=runtime.attach_later_outcomes(db_path)
        self.assertEqual(isolated['attached'],[])
        with patch.object(runtime,'now',return_value='2025-01-14T00:00:00.000000Z'), \
             patch.object(memory,'_now',return_value='2025-01-14T00:00:00.000000Z'):
            attached=runtime.attach_later_outcomes(db_path)
            repeated=runtime.attach_later_outcomes(db_path)
        self.assertEqual(len(attached['attached']),1)
        receipt=attached['attached'][0]
        self.assertEqual(receipt['source_evidence_id'],outcome['evidence_id'])
        self.assertFalse(receipt['duplicate'])
        self.assertEqual(len(repeated['attached']),1)
        self.assertTrue(repeated['attached'][0]['duplicate'])
        later=memory.as_of(db_path,'2025-01-14T00:00:00.000000Z')
        self.assertEqual(len(later['outcomes']),1)
        report=evaluation.evaluate_observed(later,'2025-01-14T00:00:00.000000Z')
        self.assertEqual(report['groups'][0]['metrics']['brier']['sample_size'],1)
        self.assertEqual(report['cohort_prediction_count'],1)
        self.assertAlmostEqual(report['groups'][0]['metrics']['brier']['value'],0.38)
        self.assertEqual(report['groups'][0]['cases'][0]['prediction_record_id'],prediction['record_id'])
        self.assertEqual(report['groups'][0]['cases'][0]['outcome_record_id'],receipt['record_id'])
        self.assertEqual(memory.as_of(db_path,'2025-01-05T00:00:00Z'),earlier)
        draft={'run_id':'unit-evaluation','model_name':'frequency','model_version':models.VERSION,
               'metric':'brier','evaluation_cutoff':'2025-01-14T00:00:00Z',
               'source_id':'unit-source','competition':'League','period':'full_time',
               'settlement':'source_full_time','loss':0,'sample_size':999999}
        with patch.object(memory,'_now',return_value='2025-01-15T00:00:00.000000Z'):
            measurement=memory.record_evaluation(db_path,draft)
        self.assertIsNone(memory.resolve_evidence(db_path,measurement['record_id'],'2025-01-14T23:59:59Z'))
        evidence=memory.resolve_evidence(db_path,measurement['record_id'],'2025-01-15T00:00:00Z')
        content=json.loads(evidence['source_raw'])
        self.assertAlmostEqual(content['loss'],0.38)
        self.assertEqual(content['sample_size'],1)
        self.assertIn(prediction['record_id'],content['supporting_evidence_ids'])
        self.assertNotIn(second_prediction['record_id'],content['supporting_evidence_ids'])
        available={name:{'available':name=='frequency'} for name in models.NAMES}
        target={'source_id':'unit-source','competition':'League','period':'full_time',
                'settlement':'source_full_time','data_origin':'imported_historical'}
        lookup=lambda eid: memory.resolve_evidence(db_path,eid,'2025-01-16T00:00:00Z')
        weights,method,retained=models._weights(available,target,'2025-01-16T00:00:00Z',[evidence],lookup)
        self.assertEqual(weights,{'frequency':1.0})
        self.assertEqual(method,'EVALUATION_WEIGHTS')
        self.assertTrue(any(item['evidence_id']==measurement['record_id'] for item in retained))


if __name__=='__main__':
    unittest.main()

