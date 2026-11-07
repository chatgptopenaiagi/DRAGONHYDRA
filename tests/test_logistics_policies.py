from copy import deepcopy
import math
import socket
import unittest
from unittest.mock import patch

from dragonhydra.cognitive_logistics.forecast import forecast_demand, forecast_leadtime
from dragonhydra.cognitive_logistics.metrics import evaluate_outcomes
from dragonhydra.cognitive_logistics.policies import COSTS, DEFAULT_COSTS, POLICIES, recommend


def forecasts(rate=3):
    demand = forecast_demand([{'day': i, 'sales': rate, 'censored': False, 'available_day': i} for i in range(7)], 'moving_average', cutoff=6)
    return demand, forecast_leadtime([], cutoff=6)


def inventory(on_hand=2, on_order=1, backorder=0, capacity=30, reserved=0):
    return {'on_hand': on_hand, 'on_order': on_order, 'backorder': backorder,
            'inventory_position': on_hand+on_order-backorder, 'capacity': capacity,
            'reserved': reserved, 'atp': on_hand-reserved, 'in_transit': on_order}


def outcome(day, demand=10, fulfilled=10, on_hand=5, stockout=False, cycle_complete=True):
    return {'day': day, 'available_day': day, 'demand': demand, 'fulfilled': fulfilled,
            'backordered': demand-fulfilled, 'lost_sales': 0, 'on_hand': on_hand, 'stockout': stockout,
            'cycle_complete': cycle_complete, 'deliveries': [], 'costs': {key: 1. for key in COSTS},
            'forecast': {'mean': 10., 'quantiles': {'0.1': 6, '0.5': 10, '0.9': 14},
                         'interval90': [4, 16], 'horizon': 1, 'cutoff': day-1}}


class LogisticsPolicyTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(socket, 'socket', side_effect=AssertionError('NETWORK_FORBIDDEN'))
        guard.start(); self.addCleanup(guard.stop)

    def test_all_policies_are_actual_finite_bounded_integer_decisions_without_mutation(self):
        demand, lead = forecasts()
        stock = inventory()
        before = deepcopy((stock, demand, lead))
        for policy in POLICIES:
            result = recommend(stock, demand, lead, policy)
            self.assertIs(type(result['quantity']), int)
            self.assertGreaterEqual(result['quantity'], 0)
            self.assertLessEqual(stock['on_hand']+stock['on_order']+result['quantity'], stock['capacity'])
            self.assertTrue(math.isfinite(result['expected_cost']['total']))
        self.assertEqual(before, (stock, demand, lead))

    def test_inventory_position_does_not_double_subtract_reservations_or_transit(self):
        demand, lead = forecasts()
        a = recommend(inventory(10, 2, reserved=0), demand, lead)
        b = recommend(inventory(10, 2, reserved=7), demand, lead)
        self.assertEqual(a['quantity'], b['quantity'])
        self.assertEqual(a['inventory_position'], 12)
        bad = inventory(); bad['inventory_position'] -= 1
        with self.assertRaisesRegex(ValueError, 'IDENTITY'): recommend(bad, demand, lead)
        bad = inventory(); bad['in_transit'] += 1
        with self.assertRaisesRegex(ValueError, 'TRANSIT'): recommend(bad, demand, lead)
        with self.assertRaises(ValueError): recommend(inventory(10, capacity=9), demand, lead)

    def test_moq_multiples_and_committed_capacity_take_priority_over_target(self):
        demand, lead = forecasts()
        result = recommend(inventory(1, 3, capacity=11), demand, lead,
                           params={'order_up_to': 100, 'min_order': 5, 'order_multiple': 3})
        self.assertEqual(result['quantity'], 6)
        self.assertTrue(result['evidence']['capacity_or_parameter_limited'])
        result = recommend(inventory(1, 3, capacity=8), demand, lead,
                           params={'order_up_to': 100, 'min_order': 5})
        self.assertEqual(result['quantity'], 0)

    def test_real_reorder_base_stock_and_s_s_rules(self):
        demand, lead = forecasts()
        stock = inventory(5, 0)
        self.assertEqual(recommend(stock, demand, lead, 'reorder_point', {'reorder_point': 5, 'fixed_quantity': 7})['quantity'], 7)
        self.assertEqual(recommend(stock, demand, lead, 'reorder_point', {'reorder_point': 4, 'fixed_quantity': 7})['quantity'], 0)
        self.assertEqual(recommend(stock, demand, lead, 'base_stock', {'base_stock': 9})['quantity'], 4)
        self.assertEqual(recommend(stock, demand, lead, 's_S', {'s': 5, 'S': 12})['quantity'], 7)
        self.assertEqual(recommend(stock, demand, lead, 's_S', {'s': 4, 'S': 12})['quantity'], 0)
        with self.assertRaises(ValueError): recommend(stock, demand, lead, 's_S', {'s': 10, 'S': 9})

    def test_probabilistic_cost_search_selects_real_minimum_and_can_order_nothing(self):
        demand, lead = forecasts(5)
        costs = {**DEFAULT_COSTS, 'shortage': 100., 'holding': 0., 'ordering': 0., 'transport': 0.}
        result = recommend(inventory(0, 0, capacity=4), demand, lead, 'probabilistic_cost', {'costs': costs})
        self.assertEqual(result['quantity'], 4)
        self.assertEqual(result['expected_cost']['total'], min(item['total_cost'] for item in result['candidates']))
        costs = {**DEFAULT_COSTS, 'shortage': 0., 'ordering': 10.}
        self.assertEqual(recommend(inventory(100, 0, capacity=120), demand, lead, 'probabilistic_cost', {'costs': costs})['quantity'], 0)
        self.assertEqual(recommend(inventory(0, 0), *forecasts(0), 'probabilistic_cost')['quantity'], 0)

    def test_service_constrained_cost_search_uses_csl_or_fill_feasible_set(self):
        demand, _ = forecasts(2)
        prior = {name: [{'days': day, 'probability': 1.}] for name, day in
                 {'processing': 1, 'transport': 1, 'receiving': 0, 'disruption': 0}.items()}
        lead = forecast_leadtime([], cutoff=6, prior=prior)
        costs = {**DEFAULT_COSTS, 'holding': 1., 'ordering': 100., 'shortage': 0., 'transport': 1.}
        # Protection demand is Poisson(4): 95% CSL requires8 units; 95%fill requires6.
        for objective, expected in (('cycle_service_level', 8), ('fill_rate', 6)):
            with self.subTest(objective=objective):
                result = recommend(inventory(0, 0), demand, lead, 'probabilistic_cost',
                                   {'costs': costs, 'review_period': 0, 'objective': objective})
                self.assertEqual(result['quantity'], expected)
                self.assertTrue(result['service_target_feasible'])
                self.assertTrue(result['service_target_met'])
                constrained = [row for row in result['candidates'] if row['service_target_met']]
                self.assertEqual(result['expected_cost']['total'], min(row['total_cost'] for row in constrained))
                self.assertEqual(result['candidates'][0]['quantity'], 0)
                self.assertLess(result['candidates'][0]['total_cost'], result['expected_cost']['total'])

    def test_infeasible_service_target_chooses_best_service_and_never_claims_success(self):
        demand, lead = forecasts(5)
        costs = {**DEFAULT_COSTS, 'holding': 1., 'shortage': 0., 'ordering': 100.}
        for objective in ('cycle_service_level', 'fill_rate'):
            with self.subTest(objective=objective):
                result = recommend(inventory(0, 0, capacity=3), demand, lead, 'probabilistic_cost',
                                   {'costs': costs, 'objective': objective})
                self.assertEqual(result['quantity'], 3)
                self.assertFalse(result['service_target_feasible'])
                self.assertFalse(result['service_target_met'])
                self.assertLess(result['achieved_CSL'], .95)
                self.assertLess(result['expected_fill_rate'], .95)
                self.assertEqual(result['objective_service_value'], max(row['objective_service_value'] for row in result['candidates']))
                self.assertEqual(result['evidence']['selection_rule'], 'HIGHEST_ACHIEVABLE_SERVICE_THEN_MINIMUM_COST')

    def test_heuristics_disclose_target_possible_but_unmet_by_their_rule(self):
        demand, lead = forecasts()
        result = recommend(inventory(0, 0, capacity=100), demand, lead, 'base_stock', {'base_stock': 0})
        self.assertEqual(result['quantity'], 0)
        self.assertTrue(result['service_target_feasible'])
        self.assertFalse(result['service_target_met'])
        self.assertEqual(result['requested_service_level'], .95)
        self.assertEqual(result['requested_service_objective'], 'cycle_service_level')
        self.assertGreaterEqual(result['expected_fill_rate'], 0.)

    def test_zero_demand_fill_objective_is_undefined_not_fabricated_perfect_service(self):
        result = recommend(inventory(0, 0), *forecasts(0), 'probabilistic_cost', {'objective': 'fill_rate'})
        self.assertEqual(result['quantity'], 0)
        self.assertIsNone(result['expected_fill_rate'])
        self.assertIsNone(result['service_target_feasible'])
        self.assertIsNone(result['service_target_met'])
        self.assertFalse(result['service_objective_applicable'])

    def test_wrong_or_nonfinite_inputs_cannot_create_a_recommendation(self):
        demand, lead = forecasts()
        for params in ({'max_order': True}, {'service_level': math.nan}, {'order_multiple': 0}, {'costs': {'holding': 1}}, {'oracle': 1}):
            with self.subTest(params=params), self.assertRaises(ValueError): recommend(inventory(), demand, lead, params=params)
        with self.assertRaises(ValueError): recommend(inventory(), demand, lead, 'perfect_future')
        bad = deepcopy(lead); bad['pmf'][0]['probability'] = 2.
        with self.assertRaises(ValueError): recommend(inventory(), demand, bad)

    def test_metrics_immediate_fill_cycle_service_costs_and_delivery_reliability_are_distinct(self):
        a, b, c = outcome(1, fulfilled=8, stockout=True, cycle_complete=False), outcome(2, demand=0, fulfilled=0, on_hand=7), outcome(3, on_hand=3)
        a['deliveries'] = [{'promised_day': 1, 'received_day': 1, 'lead_time': 1}]
        c['deliveries'] = [{'promised_day': 2, 'received_day': 3, 'lead_time': 2}]
        b['forecast'] = {'mean': 1, 'quantiles': {'0.1': 0, '0.5': 1, '0.9': 2}, 'interval90': [0, 3], 'cutoff': 1, 'horizon': 1}
        c['forecast'] = {'mean': 8, 'quantiles': {'0.1': 4, '0.5': 8, '0.9': 12}, 'interval90': [2, 14], 'cutoff': 2, 'horizon': 1}
        result = evaluate_outcomes([c, a, b], cutoff=3, naive_scale=2)
        self.assertEqual(result['fill_rate'], .9)
        self.assertEqual(result['cycle_service_level'], .5)
        self.assertEqual(result['completed_cycles'], 2)
        self.assertEqual(result['backordered_units'], 2)
        self.assertEqual(result['total_cost'], 21.)
        self.assertEqual(result['average_on_hand'], 5.)
        self.assertEqual(result['inventory_turns'], 18/5)
        self.assertEqual(result['on_time_rate'], .5)
        self.assertEqual(result['lead_time_variance'], .25)
        self.assertEqual(result['forecast_mae'], 1.)
        self.assertAlmostEqual(result['forecast_bias'], -1/3)
        self.assertEqual(result['forecast_mase'], .5)
        self.assertEqual(result['interval90_coverage'], 1.)

    def test_metrics_future_outcomes_and_incomplete_cycles_are_not_successes(self):
        a = outcome(1, demand=0, fulfilled=0, stockout=True, cycle_complete=False)
        a['forecast'] = None
        b = outcome(2); b['available_day'] = 9
        result = evaluate_outcomes([a, b], cutoff=3, naive_scale=0)
        self.assertIsNone(result['fill_rate'])
        self.assertIsNone(result['cycle_service_level'])
        self.assertIsNone(result['forecast_mase'])
        self.assertEqual(result['eligible_days'], 1)
        self.assertEqual(result['excluded_future_outcomes'], 1)
        self.assertEqual(result['total_cost'], 7.)
        self.assertIsNone(evaluate_outcomes([], cutoff=0)['average_on_hand'])

    def test_metrics_reject_wrong_horizon_leaked_forecast_and_broken_demand_balance(self):
        for alteration in ('horizon', 'cutoff', 'balance', 'quantile', 'cost', 'stockout_flag'):
            row = outcome(1)
            if alteration == 'horizon': row['forecast']['horizon'] = 5
            if alteration == 'cutoff': row['forecast']['cutoff'] = 1
            if alteration == 'balance': row['fulfilled'] = 11
            if alteration == 'quantile': row['forecast']['quantiles']['0.1'] = 50
            if alteration == 'cost': row['costs']['holding'] = 10**999
            if alteration == 'stockout_flag': row.update(fulfilled=9, backordered=1, stockout=False)
            with self.subTest(alteration=alteration), self.assertRaises(ValueError): evaluate_outcomes([row], cutoff=1)


if __name__ == '__main__': unittest.main()
