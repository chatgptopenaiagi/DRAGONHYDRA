from copy import deepcopy
import json
import math
import socket
import unittest
from unittest.mock import patch

from dragonhydra.cognitive_logistics.forecast import (
    METHODS, censored_log_likelihood, combine_demand, forecast_demand, forecast_leadtime,
    protection_distribution, rescale_demand, safety_stock, validate_demand, validate_lead)


def history(values):
    return [{'day': day, 'sales': value, 'censored': False, 'available_day': day} for day, value in enumerate(values)]


def deterministic_prior(processing=1, transport=1):
    return {key: [{'days': value, 'probability': 1.}] for key, value in
            {'processing': processing, 'transport': transport, 'receiving': 0, 'disruption': 0}.items()}


class LogisticsForecastTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(socket, 'socket', side_effect=AssertionError('NETWORK_FORBIDDEN'))
        guard.start(); self.addCleanup(guard.stop)

    def test_all_methods_have_coherent_finite_count_distributions_and_intervals(self):
        rows = history([0, 0, 5, 0, 1, 0, 0, 3, 0, 2])
        original = deepcopy(rows)
        for method in METHODS:
            with self.subTest(method=method):
                result = forecast_demand(rows, method, horizon=5, cutoff=9)
                validate_demand(result)
                json.dumps(result, allow_nan=False)
                self.assertAlmostEqual(result['mean'], 5*result['daily_mean'])
                self.assertAlmostEqual(sum(result['distribution']['probabilities']), 1.)
                self.assertLessEqual(result['interval90'][0], result['quantiles']['0.1'])
                self.assertLessEqual(result['quantiles']['0.9'], result['interval90'][1])
        self.assertEqual(rows, original)

    def test_naive_moving_average_ses_and_seasonal_are_real_distinct_estimators(self):
        rows = history([1, 3, 5, 7])
        self.assertEqual(forecast_demand(rows, 'naive', horizon=1, cutoff=3)['mean'], 7.)
        self.assertEqual(forecast_demand(rows, 'moving_average', horizon=1, cutoff=3, window=3)['mean'], 5.)
        self.assertEqual(forecast_demand(rows, 'ses', horizon=1, cutoff=3, alpha=.5)['mean'], 5.25)
        seasonal = forecast_demand(history([1, 2, 3, 4, 5, 6, 7]), 'seasonal_naive', horizon=2, cutoff=6)
        self.assertEqual(seasonal['mean'], 3.)
        self.assertEqual(seasonal['state']['next_daily_means'], [1, 2])

    def test_croston_sba_intervals_and_tsb_obsolescence(self):
        rows = history([0, 4, 0, 0, 2, 0])
        croston = forecast_demand(rows, 'croston', horizon=1, cutoff=5, alpha=.2)
        self.assertAlmostEqual(croston['daily_mean'], 3.6/2.2)
        self.assertAlmostEqual(forecast_demand(rows, 'sba', horizon=1, cutoff=5)['daily_mean'], .9*3.6/2.2)
        self.assertAlmostEqual(forecast_demand(rows, 'tsb', horizon=1, cutoff=5)['daily_mean'], .870912)
        before = forecast_demand(history([4]), 'tsb', cutoff=0)['daily_mean']
        after = forecast_demand(history([4]+[0]*10), 'tsb', cutoff=10)['daily_mean']
        self.assertLess(after, before)
        self.assertEqual(forecast_demand(history([4]+[0]*10), 'croston', cutoff=10)['daily_mean'], 4.)

    def test_standard_censoring_does_not_impute_a_stockout_as_zero(self):
        clean = history([4, 4])
        censored = {'day': 2, 'sales': 0, 'censored': True, 'available_day': 2}
        for method in METHODS[:-1]:
            a = forecast_demand(clean, method, cutoff=2)
            b = forecast_demand(clean+[censored], method, cutoff=2)
            self.assertEqual(a['mean'], b['mean'])
            self.assertEqual(b['state']['censored_observations'], 1)
        self.assertEqual(forecast_demand([censored], cutoff=2)['daily_mean'], .5)

    def test_censored_poisson_survival_fit_has_known_nonzero_likelihood_optimum(self):
        # P(D=0) P(D>=1) is maximal at lambda=log(2); grid step .05 chooses .7.
        rows = history([0])+[{'day': 1, 'sales': 1, 'censored': True, 'available_day': 1}]
        fitted = forecast_demand(rows, 'censored_poisson', horizon=1, cutoff=1)
        self.assertAlmostEqual(fitted['mean'], .7)
        self.assertAlmostEqual(censored_log_likelihood(rows, .7), math.log(math.exp(-.7)*(1-math.exp(-.7))))
        self.assertEqual(censored_log_likelihood(rows, 0), -math.inf)
        self.assertGreater(fitted['mean'], forecast_demand(history([0, 0]), 'naive', horizon=1, cutoff=1)['mean'])
        zero_bound = [{'day': 1, 'sales': 0, 'censored': True, 'available_day': 1}]
        for rate in (0., .7, 9.):
            self.assertEqual(censored_log_likelihood(zero_bound, rate), 0.)
        self.assertTrue(forecast_demand([rows[1]], 'censored_poisson', cutoff=1)['state']['no_finite_unbounded_mle'])

    def test_future_values_are_excluded_and_impossible_early_availability_rejected(self):
        past = history([2, 3, 1])
        future = {'day': 3, 'sales': 999, 'censored': False, 'available_day': 3}
        delayed = {'day': 1, 'sales': 999, 'censored': False, 'available_day': 9}
        a = forecast_demand(past, cutoff=2)
        b = forecast_demand(past+[future], cutoff=2)
        self.assertEqual(a['mean'], b['mean'])
        self.assertEqual(b['state']['excluded_future_observations'], 1)
        self.assertEqual(forecast_demand([past[0], delayed], 'naive', cutoff=2)['mean'], 10.)
        with self.assertRaisesRegex(ValueError, 'CHRONOLOGY'):
            forecast_demand([dict(future, available_day=2)], cutoff=2)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            forecast_demand(past+[past[0]], cutoff=2)

    def test_cold_start_and_nonfinite_or_unsupported_inputs_are_explicit(self):
        for method in METHODS:
            result = forecast_demand([], method, cutoff=0)
            self.assertTrue(result['state']['cold_start'])
            self.assertEqual(result['daily_mean'], .5)
        for value in (math.nan, math.inf, -math.inf, 10**999, True):
            with self.subTest(value=str(value)[:10]), self.assertRaises(ValueError):
                forecast_demand(history([value]), cutoff=0)
        for kwargs in ({'method': 'oracle'}, {'horizon': 0}, {'alpha': 0}, {'season': True}):
            with self.assertRaises(ValueError):
                forecast_demand([], cutoff=0, **kwargs)

    def test_lead_components_preserve_joint_empirical_variance_and_future_exclusion(self):
        rows = [{'ordered_day': 0, 'received_day': 2, 'available_day': 2, 'processing': 1, 'transport': 1, 'receiving': 0, 'disruption': 0},
                {'ordered_day': 0, 'received_day': 6, 'available_day': 6, 'processing': 3, 'transport': 3, 'receiving': 0, 'disruption': 0}]
        lead = forecast_leadtime(rows, cutoff=6, prior=deterministic_prior())
        validate_lead(lead)
        self.assertAlmostEqual(lead['mean'], 3.)
        self.assertAlmostEqual(lead['variance'], 3.)
        self.assertGreater(lead['variance'], sum(value['variance'] for value in lead['components'].values()))
        future = dict(rows[1], ordered_day=7, received_day=13, available_day=13)
        result = forecast_leadtime(rows+[future], cutoff=6, prior=deterministic_prior())
        self.assertEqual(result['pmf'], lead['pmf'])
        with self.assertRaisesRegex(ValueError, 'CHRONOLOGY'):
            forecast_leadtime([dict(future, available_day=6)], cutoff=6)
        with self.assertRaises(ValueError):
            forecast_leadtime([dict(rows[0], receiving=2)], cutoff=6)

    def test_csl_and_fill_rate_have_distinct_inventory_targets(self):
        demand = forecast_demand(history([2]*8), 'moving_average', cutoff=7)
        lead = forecast_leadtime([], cutoff=7, prior=deterministic_prior())
        csl = safety_stock(demand, lead, .95, 'cycle_service_level')
        fill = safety_stock(demand, lead, .95, 'fill_rate')
        self.assertGreaterEqual(csl['achieved_cycle_service_level'], .95)
        self.assertGreaterEqual(fill['implied_fill_rate'], .95)
        self.assertLess(fill['target_level'], csl['target_level'])
        self.assertAlmostEqual(csl['protection_mean'], 4.)
        with self.assertRaises(ValueError): safety_stock(demand, lead, objective='accuracy')

    def test_rescaling_rebuilds_distribution_and_corrupt_or_mismatched_forecasts_fail(self):
        demand = forecast_demand(history([2, 4]), cutoff=1)
        original = deepcopy(demand)
        scaled = rescale_demand(demand, 1.3, ['virtual-signal-1'])
        validate_demand(scaled)
        self.assertAlmostEqual(scaled['mean'], demand['mean']*1.3)
        self.assertEqual(original, demand)
        bad = deepcopy(demand); bad['distribution']['probabilities'][0] = math.nan
        with self.assertRaises(ValueError): validate_demand(bad)
        bad = deepcopy(demand); bad['quantiles']['0.9'] = 0
        with self.assertRaises(ValueError): validate_demand(bad)
        with self.assertRaisesRegex(ValueError, 'CUTOFF'):
            protection_distribution(demand, forecast_leadtime([], cutoff=2))
        seasonal = forecast_demand(history([1, 2, 3, 4, 5, 6, 7]), 'seasonal_naive', cutoff=6)
        scaled = rescale_demand(seasonal, 1.3)
        self.assertAlmostEqual(sum(scaled['state']['next_daily_means'])/scaled['horizon'], scaled['daily_mean'])
        with self.assertRaises(ValueError): rescale_demand(demand, 1., {'invalid': math.nan})

    def test_normalized_but_false_variance_and_boolean_quantiles_are_rejected(self):
        demand = forecast_demand(history([2, 2]), 'naive', horizon=1, cutoff=1)
        bad = deepcopy(demand)
        bad['distribution']['support'] = [0, 1, 2]
        bad['distribution']['probabilities'] = [0., 0., 1.]
        bad['quantiles'] = {'0.1': 2, '0.5': 2, '0.9': 2}
        bad['interval90'] = [2, 2]
        with self.assertRaisesRegex(ValueError, 'VARIANCE'): validate_demand(bad)
        zero = forecast_demand(history([0]), horizon=1, cutoff=0)
        zero['quantiles']['0.1'] = False
        with self.assertRaises(ValueError): validate_demand(zero)

    def test_aggregation_sums_matching_targets_with_provenance_and_rejects_wrong_windows(self):
        a = forecast_demand(history([0, 0]), horizon=1, cutoff=1)
        b = forecast_demand(history([20, 20]), horizon=1, cutoff=1)
        combined = combine_demand([a, b])
        validate_demand(combined)
        self.assertEqual(combined['mean'], a['mean']+b['mean'])
        self.assertEqual(combined['state']['source_model_ids'], [a['model_id'], b['model_id']])
        with self.assertRaisesRegex(ValueError, 'TARGET_MISMATCH'):
            combine_demand([a, forecast_demand(history([1]), horizon=5, cutoff=1)])
        with self.assertRaises(ValueError): combine_demand([])
        prior = deterministic_prior()
        prior['processing'].insert(0, {'days': 0, 'probability': 0.})
        validate_lead(forecast_leadtime([], cutoff=1, prior=prior))


if __name__ == '__main__': unittest.main()
