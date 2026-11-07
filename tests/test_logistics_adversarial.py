"""Adversarial checks use invented stock and newly owned disposable journals only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from dragonhydra.cognitive_logistics.computation import ForecastCache
from dragonhydra.cognitive_logistics.contracts import CATEGORIES, LOCATIONS, SKU, digest
from dragonhydra.cognitive_logistics.costs import CostLedger
from dragonhydra.cognitive_logistics.forecast import forecast_demand, validate_demand, validate_lead
from dragonhydra.cognitive_logistics.relevance import features, fit, select, estimate
from dragonhydra.cognitive_logistics.service import LogisticsService
from dragonhydra.cognitive_logistics.state import InventoryState
from dragonhydra.cognitive_logistics.world import World


def stock():
    return InventoryState({'nodes': {'s': {'kind': 'supplier', 'capacity': 30},
                                     'r': {'kind': 'retail', 'capacity': 5}},
                           'initial': {'s': {'X': 20}, 'r': {'X': 2}}, 'shelf_life': 14})


def rows(split='TRAIN', groups=('g1', 'g2', 'g3'), clock=10):
    snapshot = World(seed=400042).snapshot()
    return [{'split': split, 'category': category, 'group_id': group,
             'features': features(snapshot, category), 'decision_clock': clock,
             'acquisition_clock': clock, 'feature_cutoff': clock,
             'label_available_clock': clock+1, 'label': float(index)/10}
            for index, group in enumerate(groups) for category in CATEGORIES]


class PhysicalAdversarialTests(unittest.TestCase):
    def test_duplicate_exact_operation_is_idempotent_conflict_is_atomic(self):
        state = stock()
        receipt = state.demand('r', 'X', 1, 0, operation_id='once')
        after = state.to_dict()
        self.assertEqual(receipt, state.demand('r', 'X', 1, 0, operation_id='once'))
        self.assertEqual(after, state.to_dict())
        with self.assertRaises(ValueError):
            state.demand('r', 'X', 2, 0, operation_id='once')
        self.assertEqual(after, state.to_dict())

    def test_negative_and_insufficient_reservation_never_create_negative_stock(self):
        state = stock(); before = state.to_dict()
        for qty in (-1, 3, True, 10**1000):
            with self.subTest(qty_type=type(qty).__name__), self.assertRaises(ValueError):
                state.reserve('bad', 'r', 'X', qty, 0)
            self.assertEqual(before, state.to_dict())
        state.verify_conservation()

    def test_capacity_receive_failure_preserves_single_transit_owner(self):
        state = stock(); state.place_order('o', 's', 'r', 'X', 4, 0, 1); state.dispatch('o', 0)
        before = state.to_dict()
        with self.assertRaisesRegex(ValueError, 'CAPACITY'):
            state.receive('o', 1)
        self.assertEqual(before, state.to_dict())
        self.assertEqual(state.summary()['by_location']['r']['X']['in_transit'], 4)
        state.verify_conservation()

    def test_forged_negative_serialized_stock_is_rejected(self):
        raw = stock().to_dict(); raw['lots'][0]['qty'] = -1
        with self.assertRaises(ValueError):
            InventoryState.from_dict(raw)

    def test_nonfinite_negative_and_boolean_costs_fail_without_records(self):
        costs = CostLedger()
        for value in (float('nan'), float('inf'), -1., True, 10**1000):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                costs.record('bad', 'computation', value, 0)
        self.assertEqual(costs.summary()['total'], 0)
        self.assertEqual(costs.summary()['record_count'], 0)


class InformationAdversarialTests(unittest.TestCase):
    def test_zero_budget_never_acquires_or_spends(self):
        world = World(budget=0)
        receipt = world.execute(acquisition='all')
        self.assertEqual(receipt['acquisitions'], [])
        self.assertEqual(world.spent, 0)
        self.assertEqual(world.costs.summary()['acquisition'], 0)

    def test_pending_category_cannot_be_acquired_before_availability(self):
        world = World()
        self.assertEqual(next(c for c in world.candidates() if c['category']=='downstream_intent')['availability'], 'PENDING')
        before = world.to_dict()
        with self.assertRaises(ValueError):
            world.acquire('downstream_intent', 'virtual-too-early')
        self.assertEqual(before, world.to_dict())
        receipt = world.execute(acquisition='all')
        self.assertTrue(any(a['action']=='DEFER' and a['category']=='downstream_intent' for a in receipt['actions']))
        self.assertNotIn('downstream_intent', world.acquired)

    def test_future_or_reversed_observation_timestamps_rejected_everywhere(self):
        snapshot = World().snapshot(); day = snapshot['day']
        for observed, available, received in ((day+1,day,day), (day,day+1,day), (day,day,day+1)):
            for category, value in (('demand_signal',dict.fromkeys(LOCATIONS,.8)),
                                    ('supplier_status',{'delay_band':'CONGESTED'})):
                bad = deepcopy(snapshot)
                bad['acquired'][category] = {'acquisition_id':'virtual-invalid', 'category':category,
                    'observed_day':observed,'available_day':available,'received_day':received,
                    'value':value,'synthetic':True}
                with self.subTest(times=(observed,available,received),category=category):
                    for run in (lambda: ForecastCache().demand(bad,LOCATIONS[0]),
                                lambda: ForecastCache().lead(bad), lambda: features(bad,category)):
                        with self.assertRaisesRegex(ValueError,'TIME_LEAKAGE'):
                            run()

    def test_hidden_metadata_is_not_a_forecast_or_learned_feature(self):
        snapshot = World().snapshot(); decorated = deepcopy(snapshot)
        decorated.update({'family':'hidden-family', 'seed':999, 'latent_rate':999.,
                          'actual_future_arrivals':{'o':1}, 'outcome':999,
                          'episode_id':'virtual-other', 'group_id':'virtual-other-root'})
        self.assertEqual(features(snapshot,'demand_signal'), features(decorated,'demand_signal'))
        self.assertEqual(ForecastCache().demand(snapshot,LOCATIONS[0]), ForecastCache().demand(decorated,LOCATIONS[0]))

    def test_lost_sales_public_history_never_contains_hidden_actual_demand(self):
        world = World(demand_mode='lost_sales')
        with patch.object(world, '_demand', return_value=1000):
            world.step()
        snapshot = world.snapshot()
        self.assertTrue(all(snapshot['history'][loc][-1]['censored'] for loc in LOCATIONS))
        self.assertTrue(all(snapshot['history'][loc][-1]['sales'] < 1000 for loc in LOCATIONS))
        self.assertNotIn('lost_sales', snapshot['inventory']['conservation'])
        self.assertNotIn('demanded', snapshot['inventory']['conservation'])
        self.assertNotIn('outcomes', snapshot)
        self.assertNotIn('private_arrivals', snapshot)

    def test_future_history_excluded_and_feature_injection_rejected(self):
        snapshot = World().snapshot(); history = snapshot['history'][LOCATIONS[0]]
        base = forecast_demand(history,cutoff=snapshot['day'])
        future = {'day':snapshot['day']+1,'available_day':snapshot['day']+1,'sales':999,'censored':False}
        changed = forecast_demand(history+[future],cutoff=snapshot['day'])
        self.assertEqual(base['distribution'],changed['distribution'])
        snapshot['history'][LOCATIONS[0]].append(future)
        with self.assertRaisesRegex(ValueError,'FUTURE_FEATURE_LEAKAGE'):
            features(snapshot,'demand_signal')

    def test_probability_nan_infinity_and_unormalized_mass_rejected(self):
        snapshot = World().snapshot(); base = ForecastCache().demand(snapshot,LOCATIONS[0])
        for value in (float('nan'),float('inf'),-1.,2.):
            bad = deepcopy(base); bad['distribution']['probabilities'][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_demand(bad)
        bad = ForecastCache().lead(snapshot); bad['pmf'][0]['probability']=float('nan')
        with self.assertRaises(ValueError):
            validate_lead(bad)

    def test_model_group_overlap_and_temporal_label_leakage_rejected(self):
        train = rows(); validation = rows('VALIDATION',('g1','v2','v3'),20)
        with self.assertRaisesRegex(ValueError,'SHARED_PREFIX_SPLIT_LEAKAGE'):
            select(train,validation)
        bad = deepcopy(train); bad[0]['label_available_clock']=bad[0]['acquisition_clock']
        with self.assertRaisesRegex(ValueError,'LABEL_TEMPORAL_LEAKAGE'):
            fit(bad)
        bad = deepcopy(train); bad[0]['feature_cutoff']+=1
        with self.assertRaisesRegex(ValueError,'FEATURE_CUTOFF_LEAKAGE'):
            fit(bad)

    def test_frozen_model_not_available_before_training_labels(self):
        model = fit(rows(clock=5000000)); snapshot = World(seed=400042).snapshot()
        with self.assertRaisesRegex(ValueError,'MODEL_NOT_AVAILABLE'):
            estimate(snapshot,'demand_signal',model)

    def test_serialization_and_cache_returns_do_not_alias_live_history(self):
        world = World(); snapshot = world.snapshot(); cache = ForecastCache()
        base = cache.demand(snapshot,LOCATIONS[0]); raw = cache.to_dict()
        raw['entries'][0]['value']['mean'] = 999
        base['mean'] = 777
        self.assertNotEqual(cache.demand(snapshot,LOCATIONS[0])['mean'],999)
        self.assertNotEqual(cache.demand(snapshot,LOCATIONS[0])['mean'],777)
        before = digest(world.snapshot()); dump = world.to_dict()
        dump['history'][LOCATIONS[0]][0]['sales'] = 777
        dump['network_config']['nodes']['warehouse']['capacity'] = 1
        self.assertEqual(before,digest(world.snapshot()))
        snapshot['history'][LOCATIONS[0]][0]['sales'] = 666
        self.assertEqual(before,digest(world.snapshot()))


class TransactionAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='virtual-logistics-adversarial-')
        self.service = LogisticsService(self.temp.name)
        self.eid = self.service.create_episode(days=10)['episode_id']

    def tearDown(self):
        self.service.close(); self.temp.cleanup()

    def revision(self):
        return self.service.episode(self.eid)['snapshot']['revision']

    def test_two_real_concurrent_revision_requests_commit_exactly_once(self):
        revision = self.revision(); barrier = threading.Barrier(2)
        other = LogisticsService(self.temp.name)
        def invoke(index):
            barrier.wait(timeout=10)
            try:
                service = self.service if index==1 else other
                return ('committed',service.decide(self.eid,request_id=f'virtual-concurrent-{index}',expected_revision=revision))
            except ValueError as exc:
                return ('rejected',str(exc))
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(invoke,(1,2)))
        finally:
            other.close()
        self.assertEqual([r[0] for r in results].count('committed'),1)
        self.assertEqual([r[1] for r in results if r[0]=='rejected'],['LOGISTICS_STALE_REVISION'])
        self.assertEqual(self.service.status()['decisions'],1)

    def test_service_idempotency_conflict_and_restart_preserve_receipts(self):
        rev = self.revision(); receipt = self.service.decide(self.eid,request_id='virtual-once',expected_revision=rev)
        view = self.service.episode(self.eid)
        self.assertEqual(receipt,self.service.decide(self.eid,request_id='virtual-once',expected_revision=rev))
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):
            self.service.decide(self.eid,policy='base_stock',request_id='virtual-once',expected_revision=rev)
        self.service.close(); self.service=LogisticsService(self.temp.name)
        self.assertEqual(view,self.service.episode(self.eid))
        self.assertEqual(receipt,self.service.decide(self.eid,request_id='virtual-once',expected_revision=rev))
        self.assertEqual(self.service.status()['decisions'],1)

    def test_journal_update_delete_and_conflicting_receipt_are_rejected(self):
        self.service.decide(self.eid,request_id='virtual-evidence',expected_revision=self.revision())
        before=self.service.episode(self.eid)
        for statement in ('UPDATE decisions SET payload=payload','DELETE FROM decisions'):
            with self.service.journal.connect() as db, self.assertRaisesRegex(sqlite3.IntegrityError,'IMMUTABLE'):
                db.execute(statement)
        self.assertEqual(before,self.service.episode(self.eid))

    def test_mid_transaction_failure_rolls_back_world_budget_and_request(self):
        before=self.service.episode(self.eid); status=self.service.status(); rev=self.revision()
        original_save = self.service._save
        def save_then_abort(*args,**kwargs):
            original_save(*args,**kwargs)
            raise RuntimeError('virtual-abort')
        with patch.object(self.service,'_save',side_effect=save_then_abort):
            with self.assertRaisesRegex(RuntimeError,'virtual-abort'):
                self.service.decide(self.eid,acquisition='all',request_id='virtual-abort',expected_revision=rev)
        self.assertEqual(before,self.service.episode(self.eid))
        self.assertEqual(status,self.service.status())
        with self.service.journal.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM requests').fetchone()[0],0)

    def test_public_reads_do_not_compute_or_mutate_owned_journal(self):
        before=self.service.episode(self.eid); status=self.service.status()
        with patch('dragonhydra.cognitive_logistics.forecast.forecast_demand',side_effect=AssertionError('READ_RAN_FORECAST')):
            for _ in range(3):
                self.assertEqual(before,self.service.episode(self.eid))
                self.assertEqual(status,self.service.status())
                self.assertEqual(self.service.episodes()['items'][0]['snapshot'],before['snapshot'])

    def test_service_global_zero_budget_survives_restart(self):
        self.service.close(); self.service=LogisticsService(self.temp.name,{'acquisition_budget':0})
        receipt=self.service.decide(self.eid,acquisition='all',request_id='virtual-global-zero',expected_revision=self.revision())
        self.assertEqual(receipt['acquisitions'],[])
        self.assertEqual(self.service.status()['acquisition_spent'],0)
        self.service.close(); self.service=LogisticsService(self.temp.name,{'acquisition_budget':0})
        self.assertEqual(self.service.status()['acquisition_remaining'],0)


if __name__=='__main__':
    unittest.main()
