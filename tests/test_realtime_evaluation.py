"""Deterministic synthetic scoring checks; no application or provider is opened."""
from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from dragonhydra.realtime.evaluation import evaluate_baseline_vs_assisted, evaluate_forecasts


def prediction(**updates):
    row = {'prediction_id': 'virtual-p1', 'match_id': 'virtual-m1',
           'forecast_target': 'next_goal_occurrence', 'horizon': 5,
           'probabilities': {'goal': .25, 'no_goal': .75},
           'decision_at': '2026-01-01T12:00:00Z', 'available_at': '2026-01-01T12:00:01Z',
           'source_mode': 'REPLAY', 'synthetic': True}
    return row | updates


def outcome(**updates):
    return {'match_id': 'virtual-m1', 'forecast_target': 'next_goal_occurrence', 'horizon': 5,
            'label': 'goal', 'occurred_at': '2026-01-01T12:05:00Z',
            'available_at': '2026-01-01T12:05:01Z', 'source_mode': 'REPLAY',
            'synthetic': True} | updates


class RealtimeEvaluationTests(unittest.TestCase):
    def setUp(self):
        network = patch('socket.socket', side_effect=AssertionError('All network forbidden'))
        network.start()
        self.addCleanup(network.stop)

    def score(self, predictions=None, outcomes=None, **options):
        return evaluate_forecasts(predictions if predictions is not None else [prediction()],
                                  outcomes if outcomes is not None else [outcome()],
                                  cutoff='2026-01-01T13:00:00Z', **options)

    def test_actual_math_and_explicit_synthetic_scope(self):
        result = self.score()
        self.assertAlmostEqual(result['brier_score'], 1.125)
        self.assertAlmostEqual(result['log_loss'], -math.log(.25))
        self.assertAlmostEqual(result['ece'], .75)
        self.assertEqual(result['sample_count'], 1)
        self.assertEqual(result['independent_match_count'], 1)
        self.assertFalse(result['real_calibration_claim'])
        self.assertEqual(result['calibration_state'], 'UNVERIFIED')

    def test_missing_and_future_labels_are_pending_not_zero_error(self):
        for outcomes in ([], [outcome(available_at='2026-01-02T12:00:00Z')]):
            result = self.score(outcomes=outcomes)
            self.assertEqual(result['status'], 'pending')
            for key in ('brier_score', 'log_loss', 'ece'):
                self.assertIsNone(result[key])

    def test_future_prediction_and_post_outcome_prediction_excluded(self):
        future = self.score([prediction(available_at='2026-01-02T12:00:00Z')])
        self.assertEqual(future['exclusions'], {'PREDICTION_NOT_AVAILABLE_AT_CUTOFF': 1})
        late = self.score([prediction(available_at='2026-01-01T12:05:00Z')])
        self.assertEqual(late['exclusions'], {'PREDICTION_NOT_PROSPECTIVE': 1})

    def test_horizon_target_and_label_exact_matching(self):
        self.assertEqual(self.score(outcomes=[outcome(horizon=10)])['sample_count'], 0)
        self.assertEqual(self.score(outcomes=[outcome(forecast_target='different')])['sample_count'], 0)
        with self.assertRaisesRegex(ValueError, 'HORIZON_MATURITY_MISMATCH'):
            self.score(outcomes=[outcome(occurred_at='2026-01-01T12:04:59Z')])
        paused = self.score(outcomes=[outcome(occurred_at='2026-01-01T12:10:00Z',
                                              available_at='2026-01-01T12:10:01Z')])
        self.assertEqual(paused['exclusions'], {'NOT_ELIGIBLE_PLAYING_CLOCK_MAPPING_UNAVAILABLE': 1})
        self.assertIsNone(paused['brier_score'])
        with self.assertRaisesRegex(ValueError, 'OUTCOME_LABEL_MISMATCH'):
            self.score(outcomes=[outcome(label='invented')])

    def test_zero_probability_is_not_silently_clipped(self):
        result = self.score([prediction(probabilities={'goal': 0., 'no_goal': 1.})])
        self.assertEqual(result['brier_score'], 2.)
        self.assertTrue(result['log_loss_infinite'])
        self.assertIsNone(result['log_loss'])
        self.assertEqual(result['zero_probability_events'], 1)
        self.assertEqual(result['reliability_bins'][-1]['count'], 1)
        self.assertTrue(result['reliability_bins'][-1]['upper_inclusive'])
        json.dumps(result, allow_nan=False)

    def test_certain_correct_forecast_has_zero_error(self):
        result = self.score([prediction(probabilities={'goal': 1., 'no_goal': 0.})])
        self.assertEqual((result['brier_score'], result['log_loss'], result['ece']), (0., 0., 0.))

    def test_bad_vectors_and_nonfinite_rejected(self):
        for vector in ({'goal': .5}, {'goal': .2, 'no_goal': .7},
                       {'goal': math.nan, 'no_goal': .5}, {'goal': math.inf, 'no_goal': 0},
                       {'goal': 10 ** 999, 'no_goal': 0},
                       {'goal': -1., 'no_goal': 2.}, {'goal': True, 'no_goal': False}):
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                self.score([prediction(probabilities=vector)])

    def test_strict_synthetic_modes_and_fields(self):
        for row in (prediction(synthetic=False), prediction(source_mode='LIVE'), prediction(extra=1)):
            with self.assertRaises(ValueError):
                self.score([row])
        with self.assertRaisesRegex(ValueError, 'SOURCE_MODE_MISMATCH'):
            self.score(outcomes=[outcome(source_mode='DEMONSTRATION')])

    def test_utc_ordering_and_horizon_types(self):
        for timestamp in ('2026-01-01T12:00:00', '2026-01-01T13:00:00+01:00', 'invalid'):
            with self.assertRaisesRegex(ValueError, 'UTC_TIMESTAMP_REQUIRED'):
                self.score([prediction(decision_at=timestamp)])
        with self.assertRaisesRegex(ValueError, 'PREDICTION_AVAILABLE_BEFORE_DECISION'):
            self.score([prediction(available_at='2026-01-01T11:59:59Z')])
        with self.assertRaisesRegex(ValueError, 'OUTCOME_AVAILABLE_BEFORE_MATURITY'):
            self.score(outcomes=[outcome(available_at='2026-01-01T12:04:59Z')])
        for horizon in (True, '5', 0, 121):
            with self.assertRaisesRegex(ValueError, 'INVALID_HORIZON'):
                self.score([prediction(horizon=horizon)])

    def test_ambiguous_duplicates_rejected_and_inputs_unchanged(self):
        rows, labels = [prediction()], [outcome()]
        before = deepcopy((rows, labels))
        self.score(rows, labels)
        self.assertEqual((rows, labels), before)
        for duplicate_rows, duplicate_labels in ((rows * 2, labels), (rows, labels * 2)):
            with self.assertRaisesRegex(ValueError, 'AMBIGUOUS_DUPLICATE_EPISODE'):
                self.score(duplicate_rows, duplicate_labels)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_PREDICTION_ID'):
            self.score([prediction(), prediction(match_id='virtual-other')], labels)

    def test_full_time_and_separate_horizon_cohorts(self):
        full = prediction(prediction_id='virtual-full-time', forecast_target='full_time_result', horizon='FULL_TIME',
                          probabilities={'home': .5, 'draw': .3, 'away': .2})
        label = outcome(forecast_target='full_time_result', horizon='FULL_TIME', label='home',
                        occurred_at='2026-01-01T12:45:00Z', available_at='2026-01-01T12:45:01Z')
        result = self.score([prediction(), full], [outcome(), label])
        self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['independent_match_count'], 1)
        self.assertTrue(result['mixed_target_horizon_aggregate'])
        filtered = self.score([prediction(), full], [outcome(), label], horizon='FULL_TIME')
        self.assertEqual(filtered['sample_count'], 1)

    def test_matched_assistant_cannot_claim_quality_gain(self):
        result = evaluate_baseline_vs_assisted([prediction()], [prediction(prediction_id='virtual-p2')],
                                               [outcome()], cutoff='2026-01-01T13:00:00Z')
        self.assertTrue(result['probability_vectors_unchanged'])
        self.assertFalse(result['quality_improvement_claim'])
        self.assertEqual((result['brier_delta'], result['log_loss_delta'], result['ece_delta']), (0., 0., 0.))
        with self.assertRaisesRegex(ValueError, 'AI_PROBABILITY_OVERRIDE_REJECTED'):
            evaluate_baseline_vs_assisted([prediction()],
                                         [prediction(probabilities={'goal': .3, 'no_goal': .7})], [outcome()])
        with self.assertRaisesRegex(ValueError, 'A_B_INPUTS_OR_CUTOFF_MISMATCH'):
            evaluate_baseline_vs_assisted([prediction()],
                                         [prediction(decision_at='2026-01-01T11:59:59Z')], [outcome()])
        with self.assertRaisesRegex(ValueError, 'A_B_COHORT_MISMATCH'):
            evaluate_baseline_vs_assisted([prediction()], [], [outcome()])


if __name__ == '__main__':
    unittest.main()
