"""Seeded fictional-world and train/test separation tests, without external data."""
from copy import deepcopy
import json
import math
import random
import unittest
from unittest.mock import patch

from dragonhydra.realtime.events import FIELDS, instant, reduce_events, validate_event
from dragonhydra.realtime import worlds


class VirtualWorldTests(unittest.TestCase):
    def test_deterministic_generation_and_distinct_seed(self):
        self.assertEqual(worlds.generate_match(), worlds.generate_match())
        self.assertNotEqual(worlds.generate_match(seed=42), worlds.generate_match(seed=43))

    def test_canonical_virtual_events_for_all_families(self):
        for family in worlds.UNIVERSES:
            fixture = worlds.generate_match(family)
            self.assertTrue(fixture["descriptor"]["synthetic"])
            self.assertEqual(fixture["descriptor"]["status"], "RESEARCH_ONLY")
            self.assertEqual(fixture["descriptor"]["event_count"], len(fixture["events"]))
            for event in fixture["events"]:
                self.assertEqual(set(event), FIELDS)
                self.assertEqual(event, validate_event(event))
                self.assertEqual(event["source_mode"], "DEMONSTRATION")
                self.assertTrue(event["match_id"].startswith("virtual-"))
                self.assertTrue(event["source_id"].startswith("virtual-"))
                self.assertEqual(instant(event["event_time"]).year, 2035)
            self.assertEqual([e["sequence"] for e in fixture["events"]], list(range(1, len(fixture["events"]) + 1)))
            times = [instant(e["event_time"]) for e in fixture["events"]]
            self.assertTrue(all(a < b for a, b in zip(times, times[1:])))

    def test_reduction_final_score_matches_actual_generated_goals(self):
        for family in worlds.UNIVERSES:
            fixture = worlds.generate_match(family)
            events = fixture["events"]
            state = reduce_events(events, "virtual-universe-match", "DEMONSTRATION")
            self.assertEqual(state["status"], "FINISHED")
            for side in ("home", "away"):
                goals = sum(e["event_type"] == "GOAL" and e["participant"] == side.upper() for e in events)
                self.assertEqual(state["score"][side], goals)
            self.assertEqual(state["duration_minutes"], 90)
            self.assertEqual(events[0]["event_type"], "KICKOFF")
            self.assertEqual(events[-1]["event_type"], "FULL_TIME")

    def test_half_time_precedes_resume_at_same_playing_minute(self):
        events = worlds.generate_match()["events"]
        half = next(i for i, e in enumerate(events) if e["event_type"] == "HALF_TIME")
        self.assertEqual(events[half + 1]["event_type"], "RESUME")
        self.assertEqual(events[half]["attributes"]["minute"], 45)
        self.assertEqual(events[half + 1]["attributes"], {"minute": 45, "period": 2, "period_end_minute": 90})
        self.assertLess(instant(events[half]["event_time"]), instant(events[half + 1]["event_time"]))

    def test_generative_assumptions_are_actually_different(self):
        base = worlds._hazards("constant", 70, True, True, True, False)
        self.assertEqual(base, worlds._hazards("constant", 70, False, True, False, True))
        card = worlds._hazards("card_sensitive", 70, True, True, True, False)
        self.assertNotEqual(base, card)
        high = worlds._hazards("tempo_signal", 20, False, True, True, False)
        low = worlds._hazards("tempo_signal", 20, False, True, False, False)
        self.assertAlmostEqual(sum(high) / sum(low), 12)
        self.assertEqual(worlds._hazards("noisy_signal", 20, False, True, True, False),
                         worlds._hazards("noisy_signal", 20, False, True, False, False))
        self.assertNotEqual(worlds._hazards("clock_sensitive", 70, False, True, False, False),
                            worlds._hazards("clock_sensitive", 20, False, True, False, False))

    def test_local_randomness_does_not_change_global_rng(self):
        before = random.getstate()
        worlds.generate_match()
        worlds.relevance_experiment(cases=100)
        self.assertEqual(before, random.getstate())

    def test_generation_validation_and_hard_bounds(self):
        for args in ({"universe": "actual"}, {"seed": True}, {"seed": -1}, {"seed": 2**32}, {"match_id": "real-team"}):
            with self.assertRaises(ValueError):
                worlds.generate_match(**args)
        for args in ({"cases": 99}, {"cases": 2001}, {"cases": 100.0}, {"seed": False}):
            with self.assertRaises(ValueError):
                worlds.relevance_experiment(**args)

    def test_experiment_forward_disjoint_cohorts_and_metrics(self):
        report = worlds.relevance_experiment(cases=100)
        self.assertTrue(report["synthetic"])
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertEqual(report["total_episode_count"], 500)
        self.assertEqual(report["calibration_state"], "UNVERIFIED_FOR_REAL_WORLD")
        for family in report["universes"]:
            self.assertLess(family["train"]["order_maximum"], family["test"]["order_minimum"])
            self.assertEqual(family["train"]["count"], 70)
            self.assertEqual(family["test"]["count"], 30)
            self.assertNotIn(family["train"]["cutoff_episode_id"], family["test"]["episode_ids"])
            self.assertEqual(len(set(family["test"]["episode_ids"])), 30)
            for model in family["models"].values():
                self.assertEqual(model["fitted_on"], "TRAIN_ONLY")
                self.assertEqual(model["training_episode_count"], 70)
                for rate in model["rates"].values():
                    self.assertTrue(1e-6 <= rate <= .3)
                for metrics in model["test_metrics"].values():
                    self.assertTrue(0 <= metrics["brier"] <= 1)
                    self.assertGreaterEqual(metrics["log_loss"], 0)
                    self.assertTrue(math.isfinite(metrics["log_loss"]))
        json.dumps(report, allow_nan=False)

    def test_episode_labels_are_not_model_features_and_are_monotonic(self):
        for row in worlds._episodes("tempo_signal", 42, 100):
            self.assertEqual(set(row["features"]), {"card_active", "possession_high", "clock_late"})
            self.assertNotIn("labels", row["features"])
            labels = [row["labels"][key] for key in worlds.HORIZONS]
            self.assertEqual(labels, sorted(labels))
            self.assertLessEqual(row["exposures"]["30"], 90 - row["minute"])

    def test_changing_only_test_labels_never_changes_learned_rates(self):
        baseline = worlds.relevance_experiment(cases=100)
        original_episodes = worlds._episodes

        def changed_labels(universe, seed, cases):
            rows = original_episodes(universe, seed, cases)
            for row in rows[cases * 7 // 10:]:
                row["labels"] = {key: 1 - value for key, value in row["labels"].items()}
            return rows

        with patch.object(worlds, "_episodes", side_effect=changed_labels):
            changed = worlds.relevance_experiment(cases=100)
        for first, second in zip(baseline["universes"], changed["universes"]):
            for name in first["models"]:
                for field in ("rates", "fallback_rate", "feature_keys", "training_episode_count"):
                    self.assertEqual(first["models"][name][field], second["models"][name][field])
            self.assertNotEqual(first["cohort_sha256"], second["cohort_sha256"])

    def test_worlds_share_initial_conditions_but_have_different_hazards_and_possible_outcomes(self):
        cohorts = [worlds._episodes(name, 42, 100) for name in worlds.UNIVERSES]
        for index in range(100):
            initial = cohorts[0][index]
            for rows in cohorts[1:]:
                row = rows[index]
                for key in ("order", "minute", "features", "exposures"):
                    self.assertEqual(row[key], initial[key])
                for key in ("card_home", "hidden_uniform", "outcome_uniform", "unit_exponential"):
                    self.assertEqual(row["generation"][key], initial["generation"][key])
        self.assertTrue(any(cohorts[0][i]["generation"]["home_hazard"] != cohorts[1][i]["generation"]["home_hazard"] for i in range(100)))
        self.assertTrue(any(cohorts[0][i]["labels"] != cohorts[2][i]["labels"] for i in range(100)))
        report = worlds.relevance_experiment(cases=100)
        self.assertEqual(len({row["initial_conditions_sha256"] for row in report["universes"]}), 1)

    def test_virtual_relevance_has_no_unseen_transfer_or_causal_information_claim(self):
        report = worlds.relevance_experiment()
        self.assertEqual(report["research_target"]["notation"], "R(X,Y,T)")
        self.assertFalse(report["research_target"]["mutual_information_estimate"])
        self.assertFalse(report["research_target"]["causal_claim"])
        self.assertEqual(report["unseen_universe_generalization"], "NOT_ESTABLISHED")
        self.assertIn("nats", report["metric_definitions"]["log_loss"])
        self.assertAlmostEqual(worlds._paired([-.1, -.2])["mean_improvement"], -.15)

    def test_paired_uncertainty_and_loss_improvement_arithmetic(self):
        report = worlds.relevance_experiment(cases=100)
        for family in report["universes"]:
            baseline = family["models"]["constant_past_only"]["test_metrics"]["10"]
            for feature in ("card", "possession", "clock", "combined"):
                candidate = family["models"][feature]["test_metrics"]["10"]
                for metric in ("brier", "log_loss"):
                    estimate = family["feature_utility_vs_constant_past_only"][feature.upper()]["10"][metric]
                    self.assertAlmostEqual(estimate["mean_improvement"], baseline[metric] - candidate[metric], places=13)
                    low, high = estimate["approximate_95_percent_interval"]
                    self.assertLessEqual(low, estimate["mean_improvement"])
                    self.assertGreaterEqual(high, estimate["mean_improvement"])
                    self.assertGreaterEqual(estimate["standard_error"], 0)

    def test_pure_seeded_experiment_is_reproducible(self):
        self.assertEqual(worlds.relevance_experiment(seed=9, cases=100), worlds.relevance_experiment(seed=9, cases=100))


if __name__ == "__main__":
    unittest.main()
