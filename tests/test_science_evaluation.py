"""Known-answer scoring and adversarial time/revision replay contracts."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from math import log
import unittest

from dragonhydra.science.evaluation import (
    Baseline, EvaluationPeriod, FixtureTarget, Outcome, Probabilities,
    ResultObservation, WalkForwardProtocol, baseline_probabilities,
    run_walk_forward, score_prediction,
)
from dragonhydra.science.temporal import Availability, DecisionHorizon, TemporalMode


START = datetime(2020, 1, 1, tzinfo=timezone.utc)
COMPUTED = datetime(2026, 9, 24, tzinfo=timezone.utc)


def availability(at, mode=TemporalMode.RECONSTRUCTED_PIT):
    capture = COMPUTED if mode is TemporalMode.RECONSTRUCTED_PIT else at
    return Availability(mode, at, capture, capture, capture,
                        "SYNTHETIC_EXPLICIT_AVAILABILITY", "1", "Synthetic test assumption", 0.5, "test-fixture")


def fixture(name, day, *, home="team-a", away="team-b", mode=TemporalMode.RECONSTRUCTED_PIT):
    kickoff = START + timedelta(days=day, hours=12)
    return FixtureTarget(name, "league-a", home, away, kickoff,
                         availability(kickoff - timedelta(days=1), mode), f"schedule-{name}")


def result(target, outcome, *, lag=timedelta(hours=1), record_id=None, revision=1, supersedes_id=None,
           mode=TemporalMode.RECONSTRUCTED_PIT):
    completed = target.kickoff_at + timedelta(hours=2)
    return ResultObservation(record_id or f"result-{target.fixture_id}", target.fixture_id,
                             target.competition_id, target.home_team_id, target.away_team_id,
                             completed, outcome, availability(completed + lag, mode), revision, supersedes_id)


def protocol(**changes):
    base = WalkForwardProtocol("synthetic-fixed", "1", "league-a", TemporalMode.RECONSTRUCTED_PIT,
                               DecisionHorizon.named("T_MINUS_1H"),
                               EvaluationPeriod(START, START + timedelta(days=100)), min_training_matches=1)
    return replace(base, **changes)


class EvaluationSpineTests(unittest.TestCase):
    def test_probability_contract_rejects_nonfinite_unnormalized_and_negative(self):
        for values in ((0.3, 0.3, 0.3), (-0.1, 0.5, 0.6), (float("nan"), 0, 1),
                       (float("inf"), 0, 0), (True, 0, 0)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Probabilities(*values)

    def test_uniform_known_answer_scores_and_components(self):
        scored = score_prediction(Probabilities(1 / 3, 1 / 3, 1 / 3), Outcome.HOME)
        self.assertAlmostEqual(scored.log_loss, log(3))
        self.assertAlmostEqual(scored.rps, 5 / 18)
        self.assertAlmostEqual(scored.brier, 2 / 3)
        for actual, expected in zip(scored.brier_components, (4 / 9, 1 / 9, 1 / 9)):
            self.assertAlmostEqual(actual, expected)
        draw = score_prediction(Probabilities(1 / 3, 1 / 3, 1 / 3), Outcome.DRAW)
        self.assertAlmostEqual(draw.rps, 1 / 9)

    def test_perfect_and_impossible_predictions_have_explicit_scores(self):
        perfect = score_prediction(Probabilities(1, 0, 0), Outcome.HOME)
        self.assertEqual((perfect.log_loss, perfect.rps, perfect.brier), (0, 0, 0))
        impossible = score_prediction(Probabilities(1, 0, 0), Outcome.AWAY)
        self.assertIsNone(impossible.log_loss)
        self.assertTrue(impossible.log_loss_infinite)
        self.assertEqual((impossible.rps, impossible.brier), (1, 2))

    def test_laplace_league_rates_known_answer(self):
        rows = tuple(result(fixture(str(i), i), outcome) for i, outcome in enumerate((Outcome.HOME, Outcome.HOME, Outcome.DRAW)))
        probabilities = baseline_probabilities(Baseline.LEAGUE_EMPIRICAL, rows, fixture("target", 5))
        self.assertEqual(probabilities, Probabilities(3 / 6, 2 / 6, 1 / 6))

    def test_home_away_model_uses_venue_and_shrinks_unseen_teams(self):
        rows = (result(fixture("one", 0, home="team-a", away="team-c"), Outcome.HOME),
                result(fixture("two", 1, home="team-c", away="team-b"), Outcome.HOME),
                result(fixture("three", 2, home="team-d", away="team-e"), Outcome.AWAY))
        target = fixture("target", 4)
        league = baseline_probabilities(Baseline.LEAGUE_EMPIRICAL, rows, target)
        aware = baseline_probabilities(Baseline.HOME_AWAY_EMPIRICAL, rows, target, prior_strength=2)
        self.assertEqual(league, Probabilities(3 / 6, 1 / 6, 2 / 6))
        self.assertAlmostEqual(aware.home, 2 / 3)
        self.assertAlmostEqual(aware.draw, 1 / 9)
        self.assertAlmostEqual(aware.away, 2 / 9)
        self.assertNotEqual(aware, league)
        unseen = fixture("unseen", 4, home="new-home", away="new-away")
        self.assertEqual(baseline_probabilities(Baseline.HOME_AWAY_EMPIRICAL, rows, unseen), league)

    def test_model_rejects_target_outcome_and_duplicate_training_fixture(self):
        target = fixture("one", 0)
        row = result(target, Outcome.HOME)
        with self.assertRaises(ValueError):
            baseline_probabilities(Baseline.LEAGUE_EMPIRICAL, (row,), target)
        with self.assertRaises(ValueError):
            baseline_probabilities(Baseline.LEAGUE_EMPIRICAL, (row, row), fixture("later", 3))

    def test_chronological_walk_forward_uses_only_completed_available_history(self):
        fixtures = tuple(fixture(str(i), i) for i in range(4))
        results = tuple(result(target, Outcome.HOME if i % 2 else Outcome.AWAY) for i, target in enumerate(fixtures))
        report = run_walk_forward(fixtures, results, protocol(), computed_at=COMPUTED)
        self.assertEqual(len(report.predictions), 9)
        self.assertEqual(len(report.evaluations), 9)
        self.assertIn(("0", "INSUFFICIENT_TRAINING_HISTORY"), report.skipped)
        by_id = {row.record_id: row for row in results}
        for prediction in report.predictions:
            for item in prediction.input_evidence:
                self.assertLessEqual(item.availability.available_at, prediction.prediction_issued_at)
                if item.role == "TRAINING_RESULT":
                    self.assertLess(by_id[item.record_id].event_completed_at, prediction.prediction_issued_at)
                    self.assertNotEqual(by_id[item.record_id].fixture_id, prediction.fixture_id)

    def test_future_result_leakage_canary_cannot_change_earlier_predictions(self):
        history, target = fixture("history", 0), fixture("target", 3)
        original = (result(history, Outcome.HOME), result(target, Outcome.DRAW))
        clean = run_walk_forward((target,), original, protocol(), computed_at=COMPUTED)
        future = result(fixture("future", 6), Outcome.AWAY)
        poisoned = run_walk_forward((target,), original + (future,), protocol(), computed_at=COMPUTED)
        self.assertEqual(clean.predictions, poisoned.predictions)

    def test_scoring_label_change_does_not_change_own_prediction(self):
        history, target = fixture("history", 0), fixture("target", 3)
        rows = (result(history, Outcome.HOME), result(target, Outcome.DRAW))
        first = run_walk_forward((target,), rows, protocol(), computed_at=COMPUTED)
        changed = run_walk_forward((target,), (rows[0], replace(rows[1], outcome=Outcome.AWAY)), protocol(), computed_at=COMPUTED)
        self.assertEqual(first.predictions, changed.predictions)
        self.assertNotEqual(first.evaluations[0].score, changed.evaluations[0].score)

    def test_revision_replay_uses_old_then_new_version(self):
        historic, early, late = fixture("historic", 0), fixture("early", 2), fixture("late", 5)
        v1 = result(historic, Outcome.HOME)
        v2 = replace(v1, record_id="corrected", revision=2, supersedes_id=v1.record_id, outcome=Outcome.AWAY,
                     availability=availability(START + timedelta(days=4)))
        report = run_walk_forward((early, late), (v2, v1), protocol(), computed_at=COMPUTED)
        early_prediction, late_prediction = report.predictions[0], report.predictions[3]
        self.assertEqual(early_prediction.input_evidence[1].record_id, v1.record_id)
        self.assertEqual(late_prediction.input_evidence[1].record_id, v2.record_id)
        self.assertGreater(early_prediction.probabilities.home, late_prediction.probabilities.home)

    def test_same_timestamp_event_completion_cannot_enter_training(self):
        history, target = fixture("history", 0), fixture("target", 4)
        at_horizon = result(fixture("simultaneous", 1), Outcome.AWAY)
        cutoff = protocol().decision_horizon.target(target.kickoff_at)
        at_horizon = replace(at_horizon, event_completed_at=cutoff, availability=availability(cutoff))
        report = run_walk_forward((target,), (result(history, Outcome.HOME), at_horizon), protocol(), computed_at=COMPUTED)
        self.assertTrue(all(len(row.input_evidence) == 2 for row in report.predictions))

    def test_unavailable_and_unknown_records_never_enter_training(self):
        known, unknown, late, target = tuple(fixture(name, day) for name, day in (("known", 0), ("unknown", 1), ("late", 2), ("target", 5)))
        rows = (result(known, Outcome.HOME),
                replace(result(unknown, Outcome.AWAY), availability=replace(availability(START), available_at=None)),
                replace(result(late, Outcome.AWAY), availability=availability(COMPUTED)))
        report = run_walk_forward((target,), rows, protocol(), computed_at=COMPUTED)
        self.assertEqual({item.record_id for item in report.predictions[0].input_evidence},
                         {"schedule-target", "result-known"})

    def test_strict_mode_rejects_reconstructed_inputs_but_accepts_genuine_capture(self):
        history, target = fixture("history", 0), fixture("target", 3)
        strict_protocol = protocol(temporal_mode=TemporalMode.STRICT_PIT)
        denied = run_walk_forward((target,), (result(history, Outcome.HOME),), strict_protocol, computed_at=COMPUTED)
        self.assertFalse(denied.predictions)
        strict_history, strict_target = fixture("history", 0, mode=TemporalMode.STRICT_PIT), fixture("target", 3, mode=TemporalMode.STRICT_PIT)
        accepted = run_walk_forward((strict_target,), (result(strict_history, Outcome.HOME, mode=TemporalMode.STRICT_PIT),),
                                    strict_protocol, computed_at=COMPUTED)
        self.assertEqual(len(accepted.predictions), 3)
        self.assertTrue(all(item.availability.availability_mode is TemporalMode.STRICT_PIT
                            for item in accepted.predictions[0].input_evidence))

    def test_assumptions_survive_prediction_and_evaluation_serialization(self):
        history, target = fixture("history", 0), fixture("target", 3)
        report = run_walk_forward((target,), (result(history, Outcome.HOME), result(target, Outcome.DRAW)), protocol(), computed_at=COMPUTED)
        prediction = report.predictions[0].to_dict()
        document = json.loads(json.dumps(report.to_dict(), allow_nan=False))
        self.assertEqual(prediction["issuance_kind"], "HISTORICAL_REPLAY")
        self.assertNotEqual(prediction["computed_at"], prediction["prediction_issued_at"])
        self.assertEqual(document["temporal_mode"], "RECONSTRUCTED_PIT")
        for item in prediction["input_evidence"]:
            expected = item["availability"]
            retained = document["evidence_registry"][item["record_id"]]["availability"]
            self.assertEqual(retained, expected)
            for field in ("availability_mode", "availability_policy", "availability_policy_version", "assumption_reason", "confidence", "source"):
                self.assertIn(field, retained)
        self.assertIn("result-target", document["evidence_registry"])

    def test_replay_determinism_independent_of_input_order(self):
        fixtures = tuple(fixture(str(i), i) for i in range(6))
        rows = tuple(result(target, CATEGORY) for target, CATEGORY in zip(fixtures, (Outcome.HOME, Outcome.DRAW, Outcome.AWAY) * 2))
        first = run_walk_forward(fixtures, rows, protocol(), computed_at=COMPUTED).to_dict()
        second = run_walk_forward(tuple(reversed(fixtures)), tuple(reversed(rows)), protocol(), computed_at=COMPUTED).to_dict()
        self.assertEqual(first, second)

    def test_calibration_counts_and_no_empty_bucket_fabrication(self):
        history, target = fixture("history", 0), fixture("target", 3)
        report = run_walk_forward((target,), (result(history, Outcome.HOME), result(target, Outcome.DRAW)), protocol(), computed_at=COMPUTED).to_dict()
        uniform = report["model_results"][2]
        self.assertAlmostEqual(uniform["metrics"]["LOG_LOSS"], log(3))
        self.assertAlmostEqual(uniform["metrics"]["RPS"], 1 / 9)
        occupied = [row for row in uniform["calibration"] if row["count"]]
        self.assertEqual(len(occupied), 3)
        self.assertEqual([row["observed_frequency"] for row in occupied], [0, 1, 0])
        self.assertTrue(all(row["mean_probability"] is None for row in uniform["calibration"] if not row["count"]))

    def test_unscored_prediction_remains_distinct_from_evaluated_match(self):
        history, target = fixture("history", 0), fixture("target", 3)
        report = run_walk_forward((target,), (result(history, Outcome.HOME),), protocol(), computed_at=COMPUTED)
        self.assertEqual(len(report.predictions), 3)
        self.assertEqual(len(report.evaluations), 0)
        self.assertTrue(all(row["evaluation_matches"] == 0 for row in report.to_dict()["model_results"]))

    def test_protocol_uses_half_open_period_and_rejects_future_replay(self):
        history, target = fixture("history", 0), fixture("target", 3)
        cutoff = protocol().decision_horizon.target(target.kickoff_at)
        excluded = protocol(evaluation_period=EvaluationPeriod(START, cutoff))
        report = run_walk_forward((target,), (result(history, Outcome.HOME),), excluded, computed_at=COMPUTED)
        self.assertEqual(report.skipped, (("target", "OUTSIDE_EVALUATION_PERIOD"),))
        with self.assertRaises(ValueError):
            run_walk_forward((target,), (result(history, Outcome.HOME),), protocol(), computed_at=START)

    def test_canonical_fixture_and_evidence_identity_ambiguity_rejected(self):
        history, target = fixture("history", 0), fixture("target", 3)
        rows = (result(history, Outcome.HOME),)
        with self.assertRaises(ValueError):
            run_walk_forward((target, target), rows, protocol(), computed_at=COMPUTED)
        with self.assertRaises(ValueError):
            run_walk_forward((replace(target, schedule_record_id=rows[0].record_id),), rows, protocol(), computed_at=COMPUTED)
        with self.assertRaises(ValueError):
            run_walk_forward((replace(target, competition_id="other-league"),), rows, protocol(), computed_at=COMPUTED)

    def test_final_outcome_cannot_be_available_before_completion(self):
        target = fixture("target", 0)
        with self.assertRaises(ValueError):
            replace(result(target, Outcome.HOME), availability=availability(target.kickoff_at))

    def test_reconstruction_does_not_erase_actual_replay_capture_clock(self):
        history, target = fixture("history", 0), fixture("target", 3)
        with self.assertRaises(ValueError):
            run_walk_forward((target,), (result(history, Outcome.HOME),), protocol(),
                             computed_at=COMPUTED - timedelta(days=1))
        report = run_walk_forward((target,), (result(history, Outcome.HOME),), protocol(), computed_at=COMPUTED)
        with self.assertRaises(ValueError):
            replace(report.predictions[0], computed_at=COMPUTED - timedelta(days=1))
        with self.assertRaises(ValueError):
            replace(report.predictions[0], decision_horizon=DecisionHorizon.at(START))


if __name__ == "__main__":
    unittest.main()
