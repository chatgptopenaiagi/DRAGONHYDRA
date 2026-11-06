"""Analytic and boundary tests using invented match state only."""
from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from dragonhydra.realtime.models import predict, compare_models, bounded_counterfactual


def state(**updates):
    return {"match_id": "virtual-math-fixture", "synthetic": True, "source_mode": "DEMONSTRATION",
            "revision": 1, "minute": 60.0, "period": 2, "status": "IN_PLAY",
            "score": {"home": 1, "away": 0}, "red_cards": {"home": 0, "away": 0},
            "duration_minutes": 90.0, "period_end_minute": 90.0, "end_time_known": True,
            **updates}


class RealtimeModelTests(unittest.TestCase):
    def test_analytic_next_goal_hazards(self):
        h = predict(state(), {"home_rate": 1.8, "away_rate": 0.9})["horizons"]["10"]
        occurrence = 1 - math.exp(-0.3)
        self.assertAlmostEqual(h["next_goal_occurrence"], occurrence, places=14)
        self.assertAlmostEqual(h["next_goal_side"]["home"], occurrence * 2 / 3, places=14)
        self.assertAlmostEqual(h["next_goal_side"]["away"], occurrence / 3, places=14)
        self.assertAlmostEqual(h["remaining_goals"]["mean"], 0.3, places=14)

    def test_all_probability_views_are_coherent(self):
        result = predict(state())
        self.assertAlmostEqual(sum(result["full_time_result"].values()), 1, places=12)
        for h in result["horizons"].values():
            self.assertTrue(h["availability"])
            self.assertAlmostEqual(math.fsum(row["probability"] for row in h["score_distribution"]), 1, places=12)
            self.assertAlmostEqual(math.fsum(h["remaining_goals"]["distribution"]) + h["remaining_goals"]["tail_bucket"]["probability"], 1, places=12)
            self.assertAlmostEqual(sum(h["next_goal_side"][key] for key in ("home", "away", "no_goal")), 1, places=12)
            self.assertLessEqual(h["tail_mass"], 1e-12)
            grouped = {"home": 0.0, "draw": 0.0, "away": 0.0}
            for row in h["score_distribution"]:
                key = "home" if row["home"] > row["away"] else "away" if row["home"] < row["away"] else "draw"
                grouped[key] += row["probability"]
            for key in grouped:
                self.assertAlmostEqual(grouped[key], h["result"][key], places=12)

    def test_symmetric_rates_equal_home_away_at_tied_score(self):
        result = predict(state(score={"home": 0, "away": 0}), {"home_rate": 1.5, "away_rate": 1.5})
        self.assertAlmostEqual(result["full_time_result"]["home"], result["full_time_result"]["away"], places=14)

    def test_current_score_shifts_grid_without_spending_future_rate(self):
        a, b = predict(state()), predict(state(score={"home": 2, "away": 0}))
        self.assertEqual(a["horizons"]["10"]["remaining_goals"], b["horizons"]["10"]["remaining_goals"])
        self.assertGreater(b["full_time_result"]["home"], a["full_time_result"]["home"])
        self.assertEqual(b["horizons"]["10"]["score_distribution"][0]["home"], 2)

    def test_zero_rates_have_no_next_scorer(self):
        result = predict(state(), {"home_rate": 0, "away_rate": 0})
        self.assertEqual(result["full_time_result"], {"home": 1, "draw": 0, "away": 0})
        h = result["horizons"]["10"]
        self.assertEqual(h["remaining_goals"]["distribution"], [1.0])
        self.assertEqual(h["next_goal_occurrence"], 0)
        self.assertIsNone(h["next_goal_side"]["conditional_home"])

    def test_one_side_zero_hazard(self):
        side = predict(state(), {"home_rate": 0})["horizons"]["10"]["next_goal_side"]
        self.assertEqual(side["home"], 0)
        self.assertEqual(side["conditional_away"], 1)

    def test_horizons_monotonic_and_clipped_at_period(self):
        result = predict(state(minute=44, period=1, period_end_minute=45))
        for key in ("1", "5", "10", "30"):
            self.assertEqual(result["horizons"][key]["effective_minutes"], 1)
        self.assertEqual(result["horizons"]["FULL_TIME"]["effective_minutes"], 46)
        result = predict(state(minute=70))
        values = [result["horizons"][key]["next_goal_occurrence"] for key in ("1", "5", "10", "30", "FULL_TIME")]
        self.assertEqual(values, sorted(values))
        self.assertEqual(result["horizons"]["30"]["effective_minutes"], 20)

    def test_explicit_stoppage_end_is_used(self):
        result = predict(state(minute=91, period_end_minute=95))
        self.assertEqual(result["horizons"]["FULL_TIME"]["effective_minutes"], 4)
        self.assertEqual(result["horizons"]["10"]["effective_minutes"], 4)

    def test_first_half_stoppage_does_not_remove_second_half(self):
        result = predict(state(minute=46, period=1, period_end_minute=48))
        self.assertEqual(result["horizons"]["FULL_TIME"]["effective_minutes"], 47)
        self.assertEqual(result["horizons"]["10"]["effective_minutes"], 2)

    def test_half_time_is_explicitly_conditional_playing_time(self):
        result = predict(state(minute=47, period=1, period_end_minute=47, status="HALF_TIME"))
        self.assertEqual(result["horizons"]["FULL_TIME"]["effective_minutes"], 45)
        self.assertEqual(result["horizons"]["10"]["reason"], "CONDITIONAL_ON_SECOND_HALF_RESUMPTION")

    def test_scheduled_is_conditional_on_kickoff(self):
        result = predict(state(minute=0, period=1, period_end_minute=45, status="SCHEDULED", score={"home": 0, "away": 0}))
        self.assertEqual(result["horizons"]["FULL_TIME"]["effective_minutes"], 90)
        self.assertEqual(result["horizons"]["30"]["reason"], "CONDITIONAL_ON_KICKOFF")
        invalid = predict(state(minute=0, period=1, period_end_minute=1, status="SCHEDULED", score={"home": 0, "away": 0}))
        self.assertFalse(invalid["horizons"]["FULL_TIME"]["availability"])

    def test_clock_never_infers_finished(self):
        for minute in (90, 92):
            result = predict(state(minute=minute))
            self.assertIsNone(result["full_time_result"])
            self.assertFalse(result["horizons"]["1"]["availability"])
            self.assertIn("AUTHORITATIVE", result["horizons"]["1"]["reason"])

    def test_unknown_suspension_and_extra_time_withhold(self):
        for updates in ({"end_time_known": False}, {"status": "SUSPENDED"}, {"period": 3}, {"duration_minutes": 120}):
            result = predict(state(**updates))
            self.assertIsNone(result["full_time_result"])
            self.assertTrue(all(not h["availability"] for h in result["horizons"].values()))

    def test_finished_is_observed_point_mass_even_unknown_end(self):
        for score, winner in (({"home": 2, "away": 1}, "home"), ({"home": 1, "away": 1}, "draw"), ({"home": 0, "away": 2}, "away")):
            result = predict(state(status="FINISHED", minute=94, end_time_known=False, score=score))
            self.assertEqual(result["full_time_result"][winner], 1)
            for h in result["horizons"].values():
                self.assertEqual(h["effective_minutes"], 0)
                self.assertEqual(h["score_distribution"], [{**score, "probability": 1.0}])
                self.assertEqual(h["next_goal_occurrence"], 0)
                self.assertEqual(h["uncertainty"]["outcome_entropy"], 0)

    def test_red_card_changes_rates_only_by_documented_configuration(self):
        a, b = predict(state()), predict(state(red_cards={"home": 1, "away": 0}))
        ah, bh = a["horizons"]["10"]["remaining_goals"], b["horizons"]["10"]["remaining_goals"]
        self.assertAlmostEqual(bh["home_mean"] / ah["home_mean"], .75)
        self.assertAlmostEqual(bh["away_mean"] / ah["away_mean"], 1.1)
        neutral = predict(state(red_cards={"home": 1, "away": 0}), {"own_red_card_multiplier": 1, "opponent_red_card_multiplier": 1})
        self.assertEqual(neutral["full_time_result"], a["full_time_result"])

    def test_tail_failure_abstains_instead_of_silent_renormalization(self):
        result = predict(state(), {"max_goals": 1})
        self.assertIsNone(result["full_time_result"])
        self.assertEqual(result["horizons"]["FULL_TIME"]["reason"], "TRUNCATION_BOUND_EXCEEDED")
        self.assertGreater(result["horizons"]["FULL_TIME"]["tail_mass"], 1e-12)

    def test_out_of_supported_mean_withholds_without_clamping(self):
        result = predict(state(minute=0, period=1, period_end_minute=45, score={"home": 0, "away": 0}, red_cards={"home": 0, "away": 4}),
                         {"home_rate": 5, "away_rate": 5, "rate_basis_minutes": 45, "opponent_red_card_multiplier": 1.5})
        self.assertFalse(result["horizons"]["FULL_TIME"]["availability"])
        self.assertEqual(result["horizons"]["FULL_TIME"]["reason"], "RATE_OUTSIDE_IMPLEMENTED_RANGE")

    def test_comparison_is_recomputed_and_not_independent_training(self):
        result = compare_models(state())
        models = result["models"]
        self.assertEqual(len(models), 3)
        low, base, high = (models[i]["horizons"]["10"]["next_goal_occurrence"] for i in (1, 0, 2))
        self.assertLess(low, base)
        self.assertLess(base, high)
        self.assertAlmostEqual(high, -math.expm1(-2.8 * 1.2 * 10 / 90))
        self.assertTrue(any("not independent" in text for text in result["limitations"]))
        equal = compare_models(state(), {"comparison_low_scale": 1, "comparison_high_scale": 1})
        self.assertEqual(equal["spread"]["horizon_occurrence"]["10"]["range"], 0)

    def test_entropy_is_information_not_accuracy(self):
        result = predict(state(score={"home": 0, "away": 0}))
        self.assertEqual(result["calibration_state"], "UNVERIFIED")
        self.assertEqual(result["model_status"], "EXPERIMENTAL")
        for h in result["horizons"].values():
            self.assertGreaterEqual(h["uncertainty"]["normalized_outcome_entropy"], 0)
            self.assertLessEqual(h["uncertainty"]["normalized_outcome_entropy"], 1)

    def test_future_or_irrelevant_metadata_cannot_leak_into_probabilities(self):
        a = state()
        b = {**a, "future_outcome": {"home": 7, "away": 2}, "possession": 99, "market": {"home": 1.01},
             "teams": {"home": "Imagined", "away": "Fiction"}, "received_at": "2099-01-01T00:00:00Z"}
        self.assertEqual(predict(a), predict(b))

    def test_no_input_mutation_or_cache_poisoning(self):
        original = state()
        before = deepcopy(original)
        first = predict(original)
        expected = deepcopy(first)
        first["horizons"]["10"]["score_distribution"][0]["probability"] = 999
        first["assumptions"].clear()
        self.assertEqual(predict(original), expected)
        self.assertEqual(original, before)

    def test_rejects_real_modes_unmarked_synthetic_and_nonvirtual_identity(self):
        for updates in ({"synthetic": False}, {"synthetic": None}, {"source_mode": "LIVE"}, {"match_id": "actual-123"}):
            with self.assertRaises(ValueError):
                predict(state(**updates))

    def test_numeric_and_configuration_guards(self):
        for config in ({"home_rate": float("nan")}, {"home_rate": True}, {"home_rate": -1}, {"home_rate": "1.6"},
                       {"max_goals": 2.0}, {"max_goals": 101}, {"tail_tolerance": 0}, {"unknown": 1},
                       {"home_rate": 10**1000}, [], {"comparison_low_scale": 2}):
            with self.assertRaises(ValueError):
                predict(state(), config)
        for updates in ({"minute": float("inf")}, {"revision": True}, {"score": {"home": -1, "away": 0}},
                        {"red_cards": {"home": 5, "away": 0}}, {"end_time_known": 1}, {"period": 2.0}):
            with self.assertRaises(ValueError):
                predict(state(**updates))

    def test_counterfactual_is_bounded_pure_and_effective(self):
        original = state()
        before = deepcopy(original)
        result = bounded_counterfactual(original, {"score": {"home": 2}, "red_cards": {"away": 1}, "minute": 65})
        self.assertEqual(original, before)
        self.assertEqual(result["changed_state"]["minute"], 65)
        self.assertGreater(result["full_time_result_delta"]["home"], 0)
        self.assertAlmostEqual(sum(result["full_time_result_delta"].values()), 0, places=12)
        self.assertNotIn("score_distribution", result["counterfactual"]["horizons"]["10"])

    def test_counterfactual_rejects_boundary_identity_and_large_changes(self):
        for change in ({}, {"status": "FINISHED"}, {"match_id": "virtual-other"}, {"minute": 59}, {"minute": 71},
                       {"score": {"home": 3}}, {"red_cards": {"away": 2}}, {"score": {}}, {"score": {"other": 1}},
                       {"minute": True}, {"score": {"home": 2.0}}):
            with self.assertRaises(ValueError):
                bounded_counterfactual(state(), change)
        with self.assertRaises(ValueError):
            bounded_counterfactual(state(minute=89), {"minute": 91})
        with self.assertRaises(ValueError):
            bounded_counterfactual(state(status="FINISHED"), {"score": {"home": 2}})

    def test_model_does_not_call_legacy_forecast_or_acquire_data(self):
        with patch("dragonhydra.cognition.models.forecast", side_effect=AssertionError("legacy workflow called")):
            result = predict(state())
            compare_models(state())
            bounded_counterfactual(state(), {"minute": 61})
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
