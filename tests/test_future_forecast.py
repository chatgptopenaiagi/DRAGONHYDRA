"""Observable-only requested-horizon Poisson adapter tests."""
from copy import deepcopy
from datetime import timedelta
import math
import unittest
from unittest.mock import patch

from dragonhydra.future_relevance.environment import VirtualEpisode
from dragonhydra.future_relevance.forecast import forecast, instant
from dragonhydra.realtime import models


class FutureForecastTests(unittest.TestCase):
    def test_all_supported_targets_and_horizons_normalize(self):
        for target in ("GOAL_OCCURRENCE", "FULL_TIME_RESULT", "NEXT_GOAL_SIDE", "REMAINING_GOALS"):
            for horizon in ("1", "5", "10", "30", "FULL_TIME"):
                if target == "FULL_TIME_RESULT" and horizon != "FULL_TIME":
                    continue
                result = forecast(VirtualEpisode(seed=400042, target=target, horizon=horizon).public())
                self.assertTrue(result["availability"])
                self.assertAlmostEqual(math.fsum(result["probabilities"].values()), 1, places=12)
                self.assertTrue(all(math.isfinite(p) and 0 <= p <= 1 for p in result["probabilities"].values()))
                self.assertEqual(result["computation_units"], 1)

    def test_baseline_goal_occurrence_matches_analytic_hazard(self):
        result = forecast(VirtualEpisode(seed=400042).public())
        self.assertAlmostEqual(result["probabilities"]["goal"], -math.expm1(-2.8 * 10 / 90), places=14)

    def test_exactly_one_requested_horizon_kernel_call(self):
        with patch.object(models, "_horizon", wraps=models._horizon) as kernel:
            forecast(VirtualEpisode(seed=400042).public())
        self.assertEqual(kernel.call_count, 1)

    def test_acquired_proxies_fuse_instead_of_multiplying_redundant_evidence(self):
        e = VirtualEpisode(seed=400042, budget=1)
        initial = e.public()["now"]
        e.acquire("possession", "virtual-possession")
        e.acquire("shots", "virtual-shots")
        snapshot = e.public()
        pos = 1.8 if snapshot["acquired"]["possession"]["value"] >= .5 else .65
        shot = 1.3 if snapshot["acquired"]["shots"]["value"] >= .5 else .8
        result = forecast(snapshot)
        self.assertEqual(result["cutoff"], initial)
        self.assertAlmostEqual(result["probabilities"]["goal"], -math.expm1(-2.8 * ((pos+shot)/2) * 10/90), places=14)

    def test_delayed_observation_needs_availability_and_remaining_window_decreases(self):
        e = VirtualEpisode(seed=400042, budget=1)
        with self.assertRaises(ValueError):
            e.acquire("fatigue", "virtual-too-early")
        e.advance(2)
        e.acquire("fatigue", "virtual-eligible")
        result = forecast(e.public())
        self.assertEqual(result["effective_minutes"], 8)
        self.assertEqual(result["cutoff"], e.public()["now"])

    def test_future_receipt_and_unacquired_card_injection_rejected(self):
        e = VirtualEpisode(seed=400042, budget=1)
        e.acquire("possession", "virtual-possession")
        snapshot = e.public()
        snapshot["acquired"]["possession"]["available_at"] = (instant(snapshot["now"]) + timedelta(minutes=1)).isoformat()
        with self.assertRaises(ValueError):
            forecast(snapshot)
        snapshot = VirtualEpisode(seed=400042).public()
        snapshot["observed_state"]["red_cards"]["home"] = 1
        with self.assertRaises(ValueError):
            forecast(snapshot)

    def test_hidden_metadata_and_outcomes_do_not_affect_forecast(self):
        snapshot = VirtualEpisode(seed=400042).public()
        changed = {**snapshot, "family": "private-hidden", "seed": 999, "latent_rate": 100, "outcome": "goal"}
        self.assertEqual(forecast(snapshot), forecast(changed))

    def test_accepted_goal_makes_occurrence_and_first_side_observed(self):
        for target in ("GOAL_OCCURRENCE", "NEXT_GOAL_SIDE"):
            snapshot = VirtualEpisode(seed=400042, target=target).public()
            snapshot["observed_goal_count_since_origin"], snapshot["first_observed_goal_side"] = 1, "home"
            snapshot["observed_state"]["score"]["home"] += 1
            result = forecast(snapshot)
            key = "goal" if target == "GOAL_OCCURRENCE" else "home"
            self.assertEqual(result["probabilities"][key], 1)

    def test_remaining_goals_shift_into_fixed_bins_with_explicit_tail(self):
        snapshot = VirtualEpisode(seed=400042, target="REMAINING_GOALS").public()
        snapshot["observed_goal_count_since_origin"], snapshot["first_observed_goal_side"] = 2, "away"
        snapshot["observed_state"]["score"]["away"] += 2
        result = forecast(snapshot)
        self.assertEqual(set(result["probabilities"]), {str(i) for i in range(13)} | {"13PLUS"})
        self.assertEqual(result["probabilities"]["0"], 0)
        self.assertEqual(result["probabilities"]["1"], 0)
        self.assertAlmostEqual(result["probabilities"]["2"], math.exp(-2.8 * 10 / 90), places=14)
        self.assertGreater(result["probabilities"]["13PLUS"], 0)

    def test_finished_after_receipt_delay_is_observed_without_clock_mismatch(self):
        e = VirtualEpisode(seed=400042, target="FULL_TIME_RESULT", horizon="FULL_TIME")
        e.advance(30.04)
        snapshot = e.public()
        self.assertGreater(snapshot["now_minute"], snapshot["observed_state"]["minute"])
        result = forecast(snapshot)
        self.assertEqual(result["effective_minutes"], 0)
        self.assertEqual(max(result["probabilities"].values()), 1)

    def test_unsupported_and_out_of_range_configuration_withholds(self):
        snapshot = VirtualEpisode(seed=400042).public()
        snapshot["horizon"] = "EXTRA_TIME"
        self.assertFalse(forecast(snapshot)["availability"])
        e = VirtualEpisode(seed=400042, budget=1)
        e.acquire("possession", "virtual-possession")
        snapshot = e.public()
        snapshot["acquired"]["possession"]["value"] = .8
        with patch.dict(models.DEFAULTS, {"home_rate": 5}):
            result = forecast(snapshot)
        self.assertFalse(result["availability"])
        self.assertIn("OUTSIDE_SUPPORTED_RANGE", result["reason"])

    def test_inputs_are_not_mutated(self):
        snapshot = VirtualEpisode(seed=400042).public()
        before = deepcopy(snapshot)
        forecast(snapshot)
        self.assertEqual(snapshot, before)


if __name__ == "__main__":
    unittest.main()
