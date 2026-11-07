from copy import deepcopy
import json
import socket
import unittest
from unittest.mock import patch

from dragonhydra.cognitive_logistics import analytics
from dragonhydra.cognitive_logistics.contracts import digest
from dragonhydra.cognitive_logistics.world import World


class LogisticsAnalyticsTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(socket, 'socket', side_effect=AssertionError('NETWORK_FORBIDDEN'))
        guard.start(); self.addCleanup(guard.stop)

    def world(self):
        return World('stable', 400042, days=10)

    def test_eight_actual_methods_score_past_only_origins_and_preserve_original(self):
        world = self.world()
        before = digest(world.to_dict())
        with patch.object(analytics, 'forecast_demand', wraps=analytics.forecast_demand) as actual:
            result = analytics.analyze(world, 'compare_methods')
        self.assertEqual(len(result['candidates']), 8)
        self.assertEqual(result['actual_computations']['forecast_calls'], actual.call_count)
        self.assertEqual(actual.call_count, 80)
        for call in actual.call_args_list:
            self.assertEqual(call.kwargs['horizon'], 1)
            self.assertLess(call.kwargs['cutoff'], world.day)
        origins = result['mathematical_results']['evaluation_targets']
        train = [row['target_day'] for row in origins if row['split'] == 'TRAIN']
        validation = [row['target_day'] for row in origins if row['split'] == 'VALIDATION']
        self.assertLess(max(train), min(validation))
        self.assertTrue(all(row['forecast_cutoff'] == row['target_day']-1 and row['label_available_day'] <= world.day for row in origins))
        self.assertFalse(result['mathematical_results']['adopted'])
        self.assertEqual(digest(world.to_dict()), before)
        json.dumps(result, allow_nan=False)

    def test_future_or_unavailable_sales_do_not_change_numeric_method_selection(self):
        world = self.world()
        original = analytics.analyze(world, 'compare_methods')
        world.history['retail_a'].append({'day': world.day+1, 'available_day': world.day+1, 'sales': 999, 'censored': False})
        world.history['retail_b'].append({'day': world.day, 'available_day': world.day+5, 'sales': 999, 'censored': False})
        later = analytics.analyze(world, 'compare_methods')
        self.assertEqual(original['candidates'], later['candidates'])
        self.assertEqual(original['selected_next_experiment'], later['selected_next_experiment'])
        self.assertEqual(original['mathematical_results'], later['mathematical_results'])

    def test_censored_target_is_not_privileged_true_demand_or_an_implicit_zero_label(self):
        world = self.world()
        for location in ('retail_a', 'retail_b'):
            for row in world.history[location]:
                row['censored'] = True
        with patch.object(World, '_demand', side_effect=AssertionError('HIDDEN_DEMAND_ACCESS')):
            result = analytics.analyze(world, 'bounded_method_search')
        self.assertEqual(result['mathematical_results']['eligible_cases'], 0)
        self.assertIsNone(result['mathematical_results']['selected_configuration'])
        self.assertTrue(all(row['status'] == 'NOT_ELIGIBLE' for row in result['candidates']))
        self.assertEqual(result['actual_computations']['forecast_calls'], 0)

    def test_bounded_method_invention_retains_all_configs_nonimprovement_and_real_work(self):
        world = self.world()
        with patch.object(analytics, 'forecast_demand', wraps=analytics.forecast_demand) as actual:
            result = analytics.analyze(world, 'bounded_method_search')
        self.assertEqual(len(result['candidates']), 13)
        self.assertEqual(len({row['configuration']['configuration_id'] for row in result['candidates']}), 13)
        counts = result['actual_computations']
        self.assertEqual(actual.call_count, counts['forecast_calls'])
        self.assertEqual(counts['forecast_calls'], 80)
        self.assertEqual(counts['probability_rebuilds'], 110)
        self.assertLessEqual(counts['forecast_calls']+counts['probability_rebuilds'], 200)
        self.assertEqual(counts['candidate_evaluations'], 130)
        self.assertTrue(any(row['nonimproving_vs_sba_validation'] is True for row in result['candidates']))
        self.assertEqual(result['computation_units'], sum(counts.values()))
        registry = analytics.registered_methods(); registry[0]['method'] = 'generated_shell'
        self.assertNotEqual(analytics.registered_methods()[0]['method'], 'generated_shell')

    def test_failed_registered_candidate_remains_failed_without_a_fabricated_best_score(self):
        world = self.world()
        real = analytics.forecast_demand
        def fail_one(*args, **kwargs):
            if kwargs['method'] == 'tsb':
                raise ValueError('DISPOSABLE_NUMERICAL_FAILURE')
            return real(*args, **kwargs)
        with patch.object(analytics, 'forecast_demand', side_effect=fail_one):
            result = analytics.analyze(world)
        candidate = next(row for row in result['candidates'] if row['configuration'].get('method') == 'tsb')
        self.assertEqual(candidate['status'], 'FAILED')
        self.assertEqual(len(candidate['failures']), 10)
        self.assertIsNone(candidate['splits']['VALIDATION']['mae'])
        self.assertNotEqual(result['mathematical_results']['selected_configuration']['method'], 'tsb')

    def test_real_five_registered_counterfactuals_pair_group_and_keep_the_original(self):
        world = self.world()
        before = digest(world.to_dict())
        result = analytics.analyze(world, 'counterfactual')
        self.assertEqual({row['intervention']['kind'] for row in result['counterfactuals']}, {row[0] for row in analytics.INTERVENTIONS})
        self.assertTrue(all(row['status'] == 'TESTED' for row in result['counterfactuals']))
        for row in result['counterfactuals']:
            self.assertEqual(row['intervention_receipt']['group_id'], world.group_id)
            self.assertEqual(row['horizon_days'], 5)
            self.assertIn('virtual mechanism', row['causal_scope'])
            self.assertEqual(row['metrics']['supplier_reliability_scope'], 'COMPLETED_WINDOW_DELIVERIES_ONLY_NOT_ALL_DUE_ORDERS')
            self.assertEqual(row['metrics']['completed_delivery_on_time_rate'], row['metrics']['on_time_rate'])
        self.assertEqual(result['actual_computations']['world_steps'], 30)
        self.assertEqual(result['actual_computations']['world_step_attempts'], 30)
        self.assertNotIn('world_steps', result['priced_work_counters'])
        self.assertEqual(result['computation_units'], sum(result['actual_computations'][key] for key in result['priced_work_counters']))
        self.assertGreater(result['actual_computations']['world_forecast_cache_misses'], 0)
        self.assertEqual(digest(world.to_dict()), before)
        self.assertTrue(result['original_unchanged'])

    def test_capacity_intervention_rejection_is_retained_not_reported_as_success(self):
        world = self.world()
        world.intervene('capacity_reduction', .25)  # warehouse40 on hand; capacity now50.
        before = digest(world.to_dict())
        result = analytics.analyze(world, 'counterfactual')
        capacity = next(row for row in result['counterfactuals'] if row['intervention']['kind'] == 'capacity_reduction')
        self.assertEqual(capacity['status'], 'REJECTED_OR_FAILED')
        self.assertIn('CAPACITY', capacity['reason'])
        self.assertEqual(result['actual_computations']['world_steps'], 25)
        self.assertEqual(digest(world.to_dict()), before)

    def test_experiment_selection_is_past_only_and_does_not_claim_information_gain(self):
        world = self.world()
        snapshot = world.snapshot()
        selected = analytics.select_next_experiment(snapshot)
        hidden = deepcopy(snapshot)
        hidden['family'] = 'private_future_family'
        hidden['seed'] = 123456
        hidden['future_outcome'] = 999
        hidden['completed_leadtimes'].append({'ordered_day': 10, 'received_day': 90, 'available_day': 90})
        self.assertEqual(selected, analytics.select_next_experiment(hidden))
        self.assertEqual(selected['status'], 'PROPOSED_NOT_EXECUTED')
        self.assertIsNone(selected['calibrated_information_gain'])
        self.assertFalse(selected['automatic_acquisition_or_adoption'])

    def test_unregistered_analysis_and_closed_future_window_cannot_execute_hidden_work(self):
        world = self.world()
        before = digest(world.to_dict())
        with self.assertRaisesRegex(ValueError, 'REGISTERED'):
            analytics.analyze(world, "__import__('os').system('forbidden')")
        self.assertEqual(digest(world.to_dict()), before)
        world.run(count=10)
        result = analytics.analyze(world, 'counterfactual')
        self.assertEqual(result['mathematical_results']['status'], 'NOT_ELIGIBLE')
        self.assertEqual(result['actual_computations']['world_steps'], 0)
        self.assertEqual(result['counterfactuals'], [])


if __name__ == '__main__': unittest.main()
