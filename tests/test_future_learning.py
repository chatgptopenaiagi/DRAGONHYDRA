"""Ridge recovery, frozen-time and held-out fictional-policy tests."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import unittest
from unittest.mock import patch

from dragonhydra.future_relevance.environment import VirtualEpisode, TEST_FAMILIES
from dragonhydra.future_relevance.experiments import train_model, train_and_evaluate
from dragonhydra.future_relevance.forecast import CATEGORIES, canonical, instant
from dragonhydra.future_relevance.learning import FEATURES, feature_vector, fit_ridge, estimate, select_model, validate_model
from dragonhydra.future_relevance.policies import choose_action


def analytic_rows(split="TRAIN"):
    rows = []
    phase = 1000 if split == "TRAIN" else 201000
    for index in range(20):
        minute = 50 + (index % 8) * 5
        target = "GOAL_OCCURRENCE" if index < 10 else "NEXT_GOAL_SIDE"
        e = VirtualEpisode(seed=phase+index, minute=minute, target=target, horizon="FULL_TIME", budget=1)
        snapshot = e.public()
        # Invented analytic labels isolate whether ridge actually learns
        # conditional slopes, independent of the study's generative outcomes.
        for candidate in snapshot["candidates"]:
            candidate["cost"], candidate["computation_cost"] = .001, 0.0
        for category in CATEGORIES:
            features = feature_vector(snapshot, category)
            candidate = next(row for row in snapshot["candidates"] if row["category"] == category)
            acquisition_at = candidate["available_at"] if features["pending"] else snapshot["now"]
            occurred_at = (instant(snapshot["now"])+timedelta(minutes=90-minute)).isoformat()
            direction = 1 if category == "possession" else -1 if category == "shots" else 0
            value = direction * (.4 * (features["minute_fraction"] - .75)
                                 + (.06 if target == "GOAL_OCCURRENCE" else -.06))
            rows.append({"schema_version": "dragonhydra.future-training-row/1", "split": split,
                         "episode_id": snapshot["episode_id"], "group_id": snapshot["group_id"],
                         "decision_id": "virtual-analytic-"+split+"-"+str(index), "target": target,
                         "horizon": "FULL_TIME", "category": category, "cost": .001, "computation_cost": 0.,
                         "decision_at": snapshot["now"],
                         "label_available_at": (instant(occurred_at)+timedelta(seconds=2)).isoformat(),
                         "acquisition_at": acquisition_at, "evaluation_cutoff": acquisition_at,
                         "outcome_occurred_at": occurred_at,
                         "snapshot_sha256": hashlib.sha256(canonical(snapshot).encode()).hexdigest(),
                         "features": features, "label": value, "before_brier": .5, "after_brier": .5-value,
                         "outcome_id": "virtual-analytic-outcome-"+split+"-"+str(index)})
    return rows


def cheap_snapshot(minute=70, target="GOAL_OCCURRENCE"):
    snapshot = VirtualEpisode(seed=401042, minute=minute, target=target, horizon="FULL_TIME", budget=1).public()
    for candidate in snapshot["candidates"]:
        candidate["cost"], candidate["computation_cost"] = .001, 0.0
    return snapshot


class FutureLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = analytic_rows()
        cls.model = fit_ridge(cls.rows, regularization=.01)

    def test_genuine_ridge_recovers_known_conditional_slope(self):
        earlier = estimate(cheap_snapshot(55), "possession", self.model)["estimated_value"]
        later = estimate(cheap_snapshot(80), "possession", self.model)["estimated_value"]
        self.assertAlmostEqual(later - earlier, .4 * (80 - 55) / 90, places=3)
        self.assertTrue(any(abs(value) > 1e-5 for value in self.model["coefficients_by_category"]["possession"][1:]))

    def test_rankings_change_with_target_and_time(self):
        low = choose_action(cheap_snapshot(50), "learned", self.model, cost_weight=0)
        high = choose_action(cheap_snapshot(85), "learned", self.model, cost_weight=0)
        other_target = choose_action(cheap_snapshot(70, "NEXT_GOAL_SIDE"), "learned", self.model, cost_weight=0)
        self.assertEqual(low["category"], "shots")
        self.assertEqual(high["category"], "possession")
        self.assertEqual(other_target["category"], "shots")

    def test_feature_whitelist_excludes_family_identifiers_hidden_values_and_labels(self):
        snapshot = cheap_snapshot()
        changed = {**snapshot, "family": "possession_inverse", "seed": 999, "latent_rate": 100,
                   "outcome": "goal", "group_id": "virtual-root-different", "episode_id": "virtual-other"}
        self.assertEqual(feature_vector(snapshot, "possession"), feature_vector(changed, "possession"))
        self.assertEqual(set(feature_vector(snapshot, "possession")), set(FEATURES))
        corrupted = deepcopy(self.rows)
        corrupted[0]["features"]["family"] = 1
        with self.assertRaises(ValueError):
            fit_ridge(corrupted)

    def test_absolute_calendar_translation_does_not_change_features(self):
        original = cheap_snapshot()
        shifted = deepcopy(original)
        for key in ("now", "decision_at"):
            shifted[key] = (instant(shifted[key])+timedelta(days=30)).isoformat()
        for candidate in shifted["candidates"]:
            candidate["available_at"] = (instant(candidate["available_at"])+timedelta(days=30)).isoformat()
        self.assertEqual(feature_vector(original, "possession"), feature_vector(shifted, "possession"))

    def test_revealed_values_legal_only_after_receipt_availability(self):
        episode = VirtualEpisode(seed=401042, budget=1)
        before = feature_vector(episode.public(), "shots")
        episode.acquire("possession", "virtual-feature-observation")
        snapshot = episode.public()
        after = feature_vector(snapshot, "shots")
        self.assertEqual(before["acquired_possession"], 0)
        self.assertEqual(after["acquired_possession"], 1)
        self.assertEqual(after["visible_possession"], snapshot["acquired"]["possession"]["value"])
        snapshot["acquired"]["possession"]["received_at"] = (instant(snapshot["now"])+timedelta(minutes=1)).isoformat()
        with self.assertRaises(ValueError):
            feature_vector(snapshot, "shots")

    def test_frozen_content_hash_and_decision_time_are_enforced(self):
        self.assertEqual(validate_model(self.model)["content_sha256"], self.model["content_sha256"])
        corrupted = deepcopy(self.model)
        corrupted["coefficients_by_category"]["shots"][0] += .01
        with self.assertRaises(ValueError):
            estimate(cheap_snapshot(), "shots", corrupted)
        early = VirtualEpisode(seed=1000).public()
        with self.assertRaisesRegex(ValueError, "NOT_AVAILABLE"):
            estimate(early, "possession", self.model)
        with self.assertRaisesRegex(ValueError, "NOT_AVAILABLE"):
            choose_action(early, "learned", self.model)

    def test_validation_selects_without_fitting_validation_labels(self):
        validation = analytic_rows("VALIDATION")
        first = select_model(self.rows, validation, regularizations=(.1,), thresholds=(0.,))
        changed = deepcopy(validation)
        for row in changed:
            row["label"] *= -1
            row["after_brier"] = row["before_brier"] - row["label"]
        second = select_model(self.rows, changed, regularizations=(.1,), thresholds=(0.,))
        self.assertEqual(first["coefficients_by_category"], second["coefficients_by_category"])
        self.assertEqual(first["centers_by_category"], second["centers_by_category"])
        self.assertFalse(first["selection"]["final_test_used"])
        self.assertNotEqual(first["content_sha256"], second["content_sha256"])
        self.assertEqual(first["available_at"], max(row["label_available_at"] for row in validation))

    def test_group_and_temporal_split_leakage_rejected(self):
        validation = analytic_rows("VALIDATION")
        validation[0]["group_id"] = self.rows[0]["group_id"]
        with self.assertRaisesRegex(ValueError, "GROUP_LEAKAGE"):
            select_model(self.rows, validation)
        validation = analytic_rows("VALIDATION")
        corrupted = deepcopy(self.rows)
        corrupted[0]["label_available_at"] = "2036-01-10T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "TEMPORAL_LEAKAGE"):
            select_model(corrupted, validation)

    def test_label_integrity_nonfinite_and_category_guards(self):
        for key, value in (("label", float("nan")), ("after_brier", 1.9)):
            changed = deepcopy(self.rows)
            changed[0][key] = value
            with self.assertRaises(ValueError):
                fit_ridge(changed)
        with self.assertRaises(ValueError):
            fit_ridge([row for row in self.rows if row["category"] != "fatigue"])
        with self.assertRaises(ValueError):
            fit_ridge(self.rows, regularization=0)

    def test_cost_and_budget_can_reject_positive_predicted_information(self):
        snapshot = cheap_snapshot(85)
        cheap = choose_action(snapshot, "learned", self.model, cost_weight=0)
        self.assertEqual(cheap["action"], "ACQUIRE_NOW")
        costly = deepcopy(snapshot)
        for candidate in costly["candidates"]:
            candidate["cost"] = .5
        rejected = choose_action(costly, "learned", self.model, cost_weight=10)
        self.assertEqual(rejected["action"], "IGNORE")
        snapshot["budget_remaining"] = 0
        self.assertEqual(choose_action(snapshot, "acquire_all")["action"], "NO_ADDITIONAL_INFORMATION")

    def test_train_helper_never_constructs_final_test_families(self):
        original = VirtualEpisode.__init__
        def guarded(instance, family="constant", *args, **kwargs):
            if family in TEST_FAMILIES:
                raise AssertionError("final test world accessed during training")
            original(instance, family, *args, **kwargs)
        with patch.object(VirtualEpisode, "__init__", guarded):
            result = train_model(seed=7, cases=6)
        self.assertFalse(result["training_summary"]["final_test_constructed"])
        self.assertEqual(result["model"]["selection"]["method"], "VALIDATION_ONLY_NET_UTILITY_THEN_LABEL_MSE")

    def test_end_to_end_study_keeps_five_policies_same_outcomes_and_budget(self):
        result = train_and_evaluate(seed=42, cases=6)
        model, report = result["model"], result["report"]
        self.assertEqual(report["model_content_sha256"], validate_model(model)["content_sha256"])
        self.assertTrue(report["final_test_access_after_freeze"])
        self.assertTrue(report["group_splits_disjoint"])
        self.assertGreater(report["training_summary"]["prospective_pending_rows"], 0)
        self.assertGreater(report["prospective_pending_value"]["count"], 0)
        self.assertEqual(report["prospective_pending_value"]["count"], report["prospective_pending_value"]["decision_strictly_before_acquisition_count"])
        self.assertEqual({row["policy"] for row in report["policy_comparison"]}, {"acquire_all", "acquire_none", "random", "handcrafted", "learned"})
        for row in report["policy_comparison"]:
            self.assertEqual(row["episode_count"], 72)
            self.assertEqual(row["budget_violation_count"], 0)
            self.assertGreaterEqual(row["kernel_calls"], row["episode_count"])
            self.assertEqual(row["paired_vs_acquire_none"]["brier_improvement"]["root_group_count"], 6)
            self.assertEqual(row["experiment_budget_initial"], 100)
            self.assertLessEqual(row["experiment_acquisition_spent"], 100)
            self.assertEqual(row["hindsight_realized_counts"]["actual_marginal_not_estimated"], 0)
            self.assertEqual(row["hindsight_realized_counts"]["acquired_positive_realized_marginal"]
                             + row["hindsight_realized_counts"]["acquired_nonpositive_realized_marginal"], row["acquisition_count"])

    def test_independent_experiment_caps_are_enforced_across_episodes(self):
        from dragonhydra.future_relevance import experiments
        with patch.object(experiments, "EXPERIMENT_ACQUISITION_CAP", .025):
            result = train_and_evaluate(seed=42, cases=6)
        for row in result["report"]["policy_comparison"]:
            self.assertEqual(row["experiment_budget_initial"], .025)
            self.assertLessEqual(row["experiment_acquisition_spent"], .025 + 1e-12)
            self.assertAlmostEqual(row["experiment_acquisition_spent"] + row["experiment_acquisition_remaining"], .025)
        acquire_all = next(row for row in result["report"]["policy_comparison"] if row["policy"] == "acquire_all")
        self.assertGreater(acquire_all["experiment_budget_rejections"], 0)

    def test_prospective_row_timing_and_frozen_initial_features(self):
        from dragonhydra.future_relevance.experiments import make_rows
        rows = make_rows(seed=42, cases=6)
        pending = [row for row in rows if row["features"]["pending"]]
        self.assertTrue(pending)
        for row in pending:
            self.assertLess(instant(row["decision_at"]), instant(row["acquisition_at"]))
            self.assertEqual(row["acquisition_at"], row["evaluation_cutoff"])
            self.assertEqual(row["features"]["acquired_fatigue"], 0)
            self.assertEqual(row["features"]["visible_fatigue"], 0)
            self.assertLess(instant(row["evaluation_cutoff"]), instant(row["outcome_occurred_at"]))
            self.assertAlmostEqual(row["features"]["remaining_fraction"],
                (instant(row["outcome_occurred_at"])-instant(row["decision_at"])).total_seconds()/5400, places=12)
        corrupted = deepcopy(rows)
        index = next(i for i, row in enumerate(corrupted) if row["features"]["pending"])
        corrupted[index]["evaluation_cutoff"] = corrupted[index]["decision_at"]
        with self.assertRaisesRegex(ValueError, "NOT_PROSPECTIVE"):
            fit_ridge(corrupted)


if __name__ == "__main__":
    unittest.main()
