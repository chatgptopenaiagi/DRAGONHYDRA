"""Generated past-only training, frozen value estimation and retention regressions."""
from copy import deepcopy
from pathlib import Path
import tempfile,unittest,subprocess,sys,os,json
from dragonhydra.cognitive_logistics.contracts import canonical,digest,LOCATIONS,SKU
from dragonhydra.cognitive_logistics.experiments import train_model,groups
from dragonhydra.cognitive_logistics.relevance import validate,choose,features,_validate_rows,select
from dragonhydra.cognitive_logistics.service import LogisticsService
from dragonhydra.cognitive_logistics.world import World

class LogisticsLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.trained=train_model(seed=42,cases=3)
    def test_actual_training_has_prospective_examples_and_frozen_identity(self):
        model=validate(self.trained['model']);summary=self.trained['training_summary']
        self.assertGreater(summary['pending_train_rows'],0)
        self.assertTrue(summary['feature_provenance_verified'])
        self.assertEqual(summary['train_root_groups'],3)
        self.assertFalse(set(model['training_group_ids'])&set(model['selection']['validation_group_ids']))
        self.assertGreaterEqual(model['available_clock'],model['training_label_cutoff'])
        self.assertTrue(all(r['decision_clock']<=r['acquisition_clock']<r['label_available_clock'] for r in self.trained['training_rows']))
    def test_corrupted_training_features_cannot_hide_behind_valid_clock(self):
        row=deepcopy(self.trained['training_rows'][0]);row['features']['stock_fraction']+=.1
        with self.assertRaisesRegex(ValueError,'FEATURE_PROVENANCE'):_validate_rows([row],'TRAIN')
    def test_training_outcomes_cannot_arrive_after_validation_predictions(self):
        train=deepcopy(self.trained['training_rows']);validation=self.trained['validation_rows']
        train[0]['label_available_clock']=min(r['decision_clock'] for r in validation)+1000
        with self.assertRaisesRegex(ValueError,'TRAIN_LABELS_AFTER_VALIDATION'):select(train,validation)
    def test_trained_acquisition_is_not_silently_transferred_to_another_policy(self):
        world=World(seed=400042);before=digest(world.to_dict())
        with self.assertRaisesRegex(ValueError,'REQUIRES_ORDER_UP_TO'):world.execute('base_stock','learned',self.trained['model'])
        self.assertEqual(before,digest(world.to_dict()))
    def test_model_and_feature_identity_not_simulator_rule_identity(self):
        snapshot=World('multi_location',400042).snapshot();before=features(snapshot,'demand_signal')
        snapshot.update(universe='private-law',seed=7,hidden_demand=100000,future_lead_times=[99])
        self.assertEqual(before,features(snapshot,'demand_signal'))
        altered=deepcopy(self.trained['model']);altered['parameters']['demand_signal']['coefficients'][0]+=1
        with self.assertRaisesRegex(ValueError,'MODEL_CONTENT'):validate(altered)
    def test_acquired_categories_are_ignored_without_none_numeric_comparison(self):
        world=World(seed=400042);world.acquire('demand_signal','virtual-known-before-decision')
        choices=choose(world.snapshot(),'learned',self.trained['model'])
        self.assertEqual(next(a['action'] for a in choices if a['category']=='demand_signal'),'IGNORE')
    def test_acquisition_changes_observations_not_hidden_demand(self):
        baseline=World(seed=400073,days=10);enhanced=baseline.clone()
        enhanced.acquire('demand_signal','virtual-coupled-experiment')
        baseline.run(5);enhanced.run(5)
        self.assertEqual([r['actual_demand_id'] for r in baseline.outcomes],[r['actual_demand_id'] for r in enhanced.outcomes])
        self.assertTrue(baseline.inventory.verify_conservation()['valid']);self.assertTrue(enhanced.inventory.verify_conservation()['valid'])
    def test_empty_stock_censor_flag_does_not_reveal_invisible_lost_demand(self):
        empty=World(seed=400042,days=10)
        for loc in LOCATIONS:empty.inventory.demand(loc,SKU,12,empty.day,operation_id='virtual-empty-'+loc)
        zero,positive=empty.clone(),empty.clone()
        zero._demand=lambda location,day:0
        positive._demand=lambda location,day:3
        zero.step();positive.step()
        self.assertEqual(zero.snapshot(),positive.snapshot())
        self.assertTrue(all(zero.history[loc][-1]['censored'] for loc in LOCATIONS))
        self.assertFalse(zero.outcomes[-1]['stockout']);self.assertTrue(positive.outcomes[-1]['stockout'])
    def test_manual_and_automatic_first_period_costs_are_accounted_once(self):
        manual=World(seed=400042,days=10);automatic=manual.clone()
        manual.execute();manual.step();automatic.step()
        self.assertEqual(manual.inventory.to_dict(),automatic.inventory.to_dict())
        self.assertEqual(manual.costs.summary(),automatic.costs.summary())
        self.assertAlmostEqual(sum(manual.outcomes[0]['costs'].values()),manual.costs.summary()['total'])
    def test_every_supported_mature_receipt_is_evaluated_beyond_old_limit(self):
        with tempfile.TemporaryDirectory(prefix='genesis62-retention-') as directory:
            service=LogisticsService(Path(directory));eid=service.create_episode(days=10)['episode_id']
            original=service.decide(eid,request_id='virtual-retention-base',expected_revision=0)
            # Complete schema fixtures exercise accepted journal cardinality;
            # they do not pretend to be 1001 executed business operations.
            with service.journal.connect() as db:
                for n in range(1001):
                    row={**deepcopy(original),'decision_id':'virtual-retention-'+str(n)}
                    service.journal.insert(db,'decisions',row['decision_id'],row,eid)
                db.commit()
            view=service.episode(eid);service.advance(eid,5,view['snapshot']['revision'])
            with service.journal.connect() as db:
                row=db.execute("SELECT 1 FROM evaluations WHERE json_extract(payload,'$.decision_id')='virtual-retention-0'").fetchone()
                self.assertIsNotNone(row)
                self.assertGreaterEqual(db.execute('SELECT count(*) FROM evaluations').fetchone()[0],1002)
            service.close()
    def test_root_group_uncertainty_keeps_negative_results_and_dependence(self):
        result=groups([('same-root',-1.),('same-root',-3.),('second-root',-4.)])
        self.assertEqual(result['groups'],2);self.assertEqual(result['mean'],-3.)
        self.assertIsNotNone(result['interval95']);self.assertLess(result['mean'],0)
    def test_actual_process_exit_before_commit_rolls_back_and_retry_charges_once(self):
        with tempfile.TemporaryDirectory(prefix='genesis62-crash-') as directory:
            service=LogisticsService(Path(directory));eid=service.create_episode(days=10)['episode_id'];initial=service.episode(eid)
            service.close()
            code='''import os,sys,json
from pathlib import Path
from dragonhydra.cognitive_logistics.service import LogisticsService
s=LogisticsService(Path(sys.argv[1]));original=s._save
def crash(db,*args,**kwargs):
 original(db,*args,**kwargs)
 print(json.dumps({'uncommitted_decisions':db.execute('SELECT count(*) FROM decisions').fetchone()[0]}),flush=True)
 os._exit(37)
s._save=crash
s.decide(sys.argv[2],acquisition='all',request_id='virtual-crash-then-reconcile',expected_revision=0)
'''
            env={**os.environ,'PYTHONPATH':str(Path(__file__).absolute().parents[1]/'src'),'PYTHONDONTWRITEBYTECODE':'1'}
            child=subprocess.run([sys.executable,'-B','-c',code,directory,eid],env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(child.returncode,37,child.stderr);self.assertEqual(json.loads(child.stdout)['uncommitted_decisions'],1)
            service=LogisticsService(Path(directory))
            self.assertEqual(service.episode(eid),initial)
            self.assertEqual(service.status()['acquisition_spent'],0)
            receipt=service.decide(eid,acquisition='all',request_id='virtual-crash-then-reconcile',expected_revision=0)
            duplicate=service.decide(eid,acquisition='all',request_id='virtual-crash-then-reconcile',expected_revision=0)
            self.assertEqual(receipt,duplicate);self.assertEqual(service.status()['decisions'],1)
            self.assertAlmostEqual(service.status()['acquisition_spent'],sum(r['actual_cost'] for r in receipt['acquisitions']))
            service.close()

if __name__=='__main__':unittest.main()
