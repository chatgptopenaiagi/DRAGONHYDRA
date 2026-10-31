"""Deterministic football model tests with source-verified fictional observations."""
import hashlib
import json
import math
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from dragonhydra import public_results
from dragonhydra.cognition import models


class FootballModelsTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        today=datetime.now(timezone.utc).date()
        def day(offset): return (today+timedelta(days=offset)).isoformat()
        fixtures=[
          {'date':day(-12),'team1':'Team A','team2':'Team C','score':{'ft':[2,0]}},
          {'date':day(-11),'team1':'Team D','team2':'Team B','score':{'ft':[0,1]}},
          {'date':day(-10),'team1':'Team C','team2':'Team A','score':{'ft':[1,1]}},
          {'date':day(-9),'team1':'Team B','team2':'Team D','score':{'ft':[2,2]}},
          {'date':day(-8),'team1':'Team A','team2':'Team D','score':{'ft':[1,3]}},
          {'date':day(-7),'team1':'Team C','team2':'Team B','score':{'ft':[0,2]}},
          {'date':day(5),'team1':'Team A','team2':'Team B'}]
        raw=json.dumps({'name':'Fictional Model Test League','matches':fixtures}).encode()
        receipt=public_results.ingest_bytes(self.db,raw,source_id='fictional-test-only',
                    source_url='fictional:test-only',acquisition_id='fixture')
        self.cutoff=receipt['usable_at']
        self.rows=public_results.latest(self.db,self.cutoff)
        self.target=next(row for row in self.rows if row['result_state']=='unavailable')
        self.resolve=lambda h:self.db.execute('SELECT bytes FROM raw_sources WHERE source_hash=?',(h,)).fetchone()[0]

    def run_forecast(self, **kwargs):
        return models.forecast(self.rows,self.target,self.cutoff,self.resolve,**kwargs)

    def test_known_poisson_probability(self):
        probs,tail=models.poisson_distribution(1,40)
        self.assertAlmostEqual(probs[0],math.exp(-1),places=14)
        self.assertAlmostEqual(probs[1],math.exp(-1),places=14)
        self.assertAlmostEqual(probs[2],math.exp(-1)/2,places=14)
        self.assertAlmostEqual(sum(probs)+tail,1,places=14)
        for value in ('NaN','Infinity',-1):
            with self.subTest(value=value),self.assertRaises(ValueError):
                models.poisson_distribution(value)

    def test_model_outputs_are_normalized_and_evidence_linked(self):
        report=self.run_forecast()
        self.assertEqual(report['training_count'],6)
        self.assertFalse(report['abstained'])
        self.assertEqual(report['ensemble']['weight_mode'],'EQUAL_WEIGHTS_NO_ELIGIBLE_EVALUATION')
        ids={report['target']['evidence_id'],report['configuration']['evidence_id']} | {r['evidence_id'] for r in report['training_manifest']}
        for name,model in report['models'].items():
            self.assertTrue(model['available'],name)
            self.assertAlmostEqual(sum(m['value'] for m in model['probabilities'].values()),1,places=12)
            for metric in model['probabilities'].values():
                self.assertTrue(set(metric['evidence_ids']) <= ids)
                self.assertEqual(metric['transformation']['version'],models.VERSION)
        poisson=report['models']['poisson_goals']
        self.assertAlmostEqual(sum(x['value'] for x in poisson['totals_2_5'].values()),1,places=12)
        self.assertAlmostEqual(sum(x['value'] for x in poisson['both_teams_to_score'].values()),1,places=12)
        self.assertLessEqual(poisson['omitted_mass']['value'],report['configuration']['values']['max_omitted_mass'])
        self.assertAlmostEqual(sum(x['value'] for x in report['ensemble']['probabilities'].values()),1,places=12)
        self.assertIsNone(report['model_persisted_at'])
        from dragonhydra import research
        self.assertEqual(research._time(report['data_cutoff']),research._time(self.cutoff))
        self.assertEqual(research._time(report['decision_cutoff']),research._time(report['model_usable_at']))
        self.assertGreaterEqual(research._time(report['decision_cutoff']),research._time(report['data_cutoff']))
        self.assertGreaterEqual(research._time(report['decision_cutoff']),research._time(report['configuration']['recorded_at']))


    def test_scoreline_grid_is_complete_compact_and_recovers_markets(self):
        report=self.run_forecast()
        poisson=report['models']['poisson_goals']
        grid=poisson['scoreline_grid']
        cells=grid['probabilities']
        self.assertEqual(grid['axes']['home_goals'],list(range(41)))
        self.assertEqual(grid['axes']['away_goals'],list(range(41)))
        self.assertEqual(len(cells),41)
        self.assertTrue(all(len(row)==41 for row in cells))
        self.assertAlmostEqual(math.fsum(math.fsum(row) for row in cells),1,places=12)
        home=math.fsum(cells[h][a] for h in range(41) for a in range(41) if h>a)
        draw=math.fsum(cells[h][h] for h in range(41))
        away=math.fsum(cells[h][a] for h in range(41) for a in range(41) if h<a)
        for name,value in [('home',home),('draw',draw),('away',away)]:
            self.assertAlmostEqual(value,poisson['probabilities'][name]['value'],places=12)
        over=math.fsum(cells[h][a] for h in range(41) for a in range(41) if h+a>=3)
        self.assertAlmostEqual(over,poisson['totals_2_5']['over']['value'],places=12)
        for scoreline in poisson['scorelines']:
            self.assertAlmostEqual(cells[scoreline['home_goals']][scoreline['away_goals']],
                                   scoreline['probability']['value'],places=14)
        self.assertEqual(grid['transformation']['version'],models.VERSION)
        self.assertEqual(grid['evidence_ids'],poisson['probabilities']['home']['evidence_ids'])
        self.assertLess(len(json.dumps(grid).encode()),80000)

    def test_sparse_falls_back_and_truncated_poisson_abstains(self):
        sparse=self.run_forecast(config={'minimum_results':100})
        self.assertTrue(sparse['models']['frequency']['available'])
        self.assertFalse(sparse['models']['poisson_goals']['available'])
        self.assertFalse(sparse['models']['elo']['available'])
        self.assertFalse(sparse['models']['recency']['available'])
        self.assertEqual(sparse['ensemble']['weights'],{'frequency':1.0})
        truncated=self.run_forecast(config={'max_goals':2})
        self.assertFalse(truncated['models']['poisson_goals']['available'])
        self.assertEqual(truncated['models']['poisson_goals']['reason'],'POISSON_TAIL_EXCEEDS_TOLERANCE')

    def test_deterministic_and_future_input_does_not_change_payload(self):
        first=self.run_forecast()
        second=self.run_forecast()
        self.assertEqual(first['models'],second['models'])
        self.assertEqual(first['ensemble'],second['ensemble'])
        future=dict(self.rows[0],usable_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
                    source_hash='bad',outcome='impossible')
        after=models.forecast(self.rows+[future],self.target,self.cutoff,self.resolve)
        self.assertEqual(first['models'],after['models'])
        self.assertEqual(first['ensemble'],after['ensemble'])

    def test_raw_tamper_and_invalid_config_rejected(self):
        changed=[dict(r) for r in self.rows]
        changed[0]['home_goals']+=1
        with self.assertRaisesRegex(ValueError,'SOURCE_RECORD_MISMATCH'):
            models.forecast(changed,self.target,self.cutoff,self.resolve)
        for config in ({'smoothing':'NaN'}, {'max_goals':0}, {'unknown':1}):
            with self.subTest(config=config),self.assertRaises(ValueError):
                self.run_forecast(config=config)

    def test_verified_out_of_sample_losses_can_supply_weights(self):
        raw_input=json.dumps({'kind':'retained-prediction-and-outcome'},sort_keys=True)
        def ev(eid,raw):
            return {'evidence_id':eid,'source_id':'test-evaluation','source_hash':hashlib.sha256(raw.encode()).hexdigest(),
                    'source_raw':raw,'data_origin':'imported_historical' if eid=='evidence' else 'model_state','received_at':self.cutoff,
                    'persisted_at':self.cutoff,'usable_at':self.cutoff}
        saved={'evidence':ev('evidence',raw_input)}
        refs=[]
        scope={k:self.target[k] for k in ('source_id','competition','period','settlement')}
        for i,name in enumerate(models.NAMES,1):
            payload={'model':name,'model_version':models.VERSION,'evaluation_end':self.cutoff,
                     'evaluation_scope':scope,'metric':'brier','loss':str(i),'sample_size':10,
                     'supporting_evidence_ids':['evidence']}
            eid='evaluation-'+name
            saved[eid]=ev(eid,json.dumps(payload,sort_keys=True))
            refs.append({'evidence_id':eid,'usable_at':self.cutoff})
        result=self.run_forecast(performance_records=refs,performance_resolver=lambda eid:saved.get(eid))
        self.assertEqual(result['ensemble']['weight_mode'],'EVALUATION_WEIGHTS')
        self.assertAlmostEqual(sum(result['ensemble']['weights'].values()),1,places=12)
        self.assertGreater(result['ensemble']['weights']['frequency'],result['ensemble']['weights']['recency'])
        self.assertIn('evidence',{x['evidence_id'] for x in result['performance_evidence']})
        original_input=saved['evidence']
        saved['evidence']=dict(original_input,data_origin='synthetic')
        with self.assertRaisesRegex(ValueError,'SYNTHETIC_EVALUATION_FOR_REAL_TARGET'):
            self.run_forecast(performance_records=refs,performance_resolver=lambda eid:saved.get(eid))
        saved['evidence']=original_input
        invalid=dict(saved['evaluation-frequency'])
        invalid['source_raw']='tampered'
        saved['evaluation-frequency']=invalid
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):
            self.run_forecast(performance_records=refs,performance_resolver=lambda eid:saved.get(eid))

    def test_extreme_elo_expectations_do_not_overflow(self):
        self.assertLess(models._elo_expectation(0,100000,0),1e-200)
        self.assertEqual(models._elo_expectation(100000,0,0),1)

    def test_unverified_or_future_evaluation_cannot_change_weights(self):
        future={'usable_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(), 'evidence_id':'future'}
        ordinary=self.run_forecast()
        result=self.run_forecast(performance_records=[future])
        self.assertEqual(ordinary['ensemble'],result['ensemble'])
        pointer={'usable_at':self.cutoff,'evidence_id':'future'}
        future_record={'usable_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
                       'evidence_id':'future'}
        result=self.run_forecast(performance_records=[pointer],performance_resolver=lambda _:future_record)
        self.assertEqual(ordinary['ensemble'],result['ensemble'])

        future_time=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        forged={'evidence_id':'future','received_at':future_time,'persisted_at':future_time,'usable_at':self.cutoff}
        result=self.run_forecast(performance_records=[pointer],performance_resolver=lambda _:forged)
        self.assertEqual(ordinary['ensemble'],result['ensemble'])
        self.assertEqual(result['performance_evidence'],[])
        unresolved=self.run_forecast(performance_records=[pointer],performance_resolver=lambda _:None)
        self.assertEqual(ordinary['ensemble'],unresolved['ensemble'])
        self.assertEqual(unresolved['performance_evidence'],[])
        eligible={'usable_at':self.cutoff,'evidence_id':'unknown'}
        result=self.run_forecast(performance_records=[eligible])
        self.assertEqual(result['ensemble']['weight_mode'],'EQUAL_WEIGHTS_EVALUATION_UNVERIFIED')
        self.assertEqual(result['ensemble']['weights'],ordinary['ensemble']['weights'])


if __name__=='__main__':
    unittest.main()








