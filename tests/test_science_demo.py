"""Portable synthetic checks for the bounded retained-source demonstration."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import unittest

from dragonhydra.science.demo import (CaptureMetadata, build_historical_inputs,
                                      evaluate_historical, parse_historical_rows)
from dragonhydra.science.entities import EntityType
from dragonhydra.science.temporal import TemporalMode


CAPTURED = datetime(2026, 9, 24, tzinfo=timezone.utc)
COMPUTED = CAPTURED + timedelta(hours=1)


def raw_fixture(matches=None):
    if matches is None:
        matches = [{"round": f"Matchday {i + 1}", "date": f"2023-08-{11 + i * 4:02d}",
                    "team1": "Synthetic A" if i % 2 == 0 else "Synthetic B",
                    "team2": "Synthetic B" if i % 2 == 0 else "Synthetic A",
                    "score": {"ft": [i % 3, 1]}} for i in range(4)]
    return json.dumps({"name": "English Premier League 2023/24", "matches": matches}).encode()


def metadata(raw):
    return CaptureMetadata("openfootball", "https://example.invalid/synthetic.json", sha256(raw).hexdigest(),
                           CAPTURED, CAPTURED, CAPTURED, "SYNTHETIC_TEST_FIXTURE")


class HistoricalDemoTests(unittest.TestCase):
    def test_historical_assumptions_keep_real_capture_clocks_and_strict_exclusion(self):
        raw = raw_fixture()
        inputs = build_historical_inputs(raw, metadata(raw), computed_at=COMPUTED, min_training_matches=1)
        self.assertEqual(len(inputs.fixtures), 4)
        self.assertEqual(len(inputs.registry.crosswalks), 7)
        self.assertTrue(all(row.recorded_at == COMPUTED for row in inputs.registry.crosswalks))
        self.assertEqual(inputs.registry.schedules, ())  # No bare schedule can shed assumption labels.
        for target, result in zip(inputs.fixtures, inputs.results):
            self.assertEqual(target.schedule_availability.available_at, target.kickoff_at - timedelta(days=1))
            self.assertEqual(result.event_completed_at, target.kickoff_at + timedelta(days=1))
            self.assertEqual(result.availability.available_at, target.kickoff_at + timedelta(days=2))
            self.assertEqual(result.availability.observed_at, CAPTURED)
            self.assertEqual(result.availability.retrieved_at, CAPTURED)
            self.assertEqual(result.availability.ingested_at, CAPTURED)
            self.assertFalse(target.schedule_availability.eligible(target.kickoff_at, TemporalMode.STRICT_PIT))
            self.assertFalse(result.availability.eligible(result.availability.available_at, TemporalMode.STRICT_PIT))
            self.assertIn("not a measured delay", result.availability.assumption_reason)
            self.assertLessEqual(result.availability.confidence, 0.2)
        self.assertEqual(inputs.protocol.decision_horizon.name, "DAY_START_UTC_PROXY")

    def test_declared_fixture_identity_survives_rescheduled_date(self):
        raw = raw_fixture()
        original = build_historical_inputs(raw, metadata(raw), computed_at=COMPUTED)
        document = json.loads(raw)
        document["matches"][0]["date"] = "2023-09-01"
        revised_raw = json.dumps(document).encode()
        revised = build_historical_inputs(revised_raw, metadata(revised_raw), computed_at=COMPUTED)
        self.assertEqual({row.fixture_id for row in original.fixtures}, {row.fixture_id for row in revised.fixtures})
        self.assertEqual({row.canonical_id for row in original.registry.crosswalks if row.entity_type == EntityType.FIXTURE},
                         {row.canonical_id for row in revised.registry.crosswalks if row.entity_type == EntityType.FIXTURE})

    def test_evaluation_retains_labels_computation_time_and_replay_determinism(self):
        raw = raw_fixture()
        first = evaluate_historical(raw, metadata(raw), computed_at=COMPUTED, min_training_matches=1)
        self.assertEqual(first, evaluate_historical(raw, metadata(raw), computed_at=COMPUTED, min_training_matches=1))
        self.assertEqual(first["summary"]["historical_strict_pit_eligible_records"], 0)
        self.assertEqual(first["summary"]["evaluation_fixture_count"], 3)
        self.assertEqual(first["summary"]["prediction_count"], 9)
        self.assertIn("DEMONSTRATION_ONLY", first["summary"]["inference_status"])
        for prediction in first["report"]["predictions"]:
            self.assertEqual(prediction["computed_at"], COMPUTED.isoformat())
            self.assertEqual(prediction["temporal_mode"], "RECONSTRUCTED_PIT")
            self.assertEqual(prediction["issuance_kind"], "HISTORICAL_REPLAY")
            self.assertNotEqual(prediction["prediction_issued_at"], prediction["computed_at"])
        for evidence in first["report"]["evidence_registry"].values():
            self.assertEqual(evidence["availability"]["availability_mode"], "RECONSTRUCTED_PIT")
            self.assertTrue(evidence["availability"]["assumption_reason"])

    def test_rejects_hash_mismatch_ambiguous_identity_bad_scores_and_invalid_capture(self):
        raw = raw_fixture()
        with self.assertRaises(ValueError):
            build_historical_inputs(raw, replace(metadata(raw), content_hash="0" * 64), computed_at=COMPUTED)
        with self.assertRaises(ValueError):
            build_historical_inputs(raw, metadata(raw), computed_at=CAPTURED - timedelta(hours=1))
        document = json.loads(raw)
        document["matches"].append(dict(document["matches"][0], date="2023-09-01"))
        with self.assertRaises(ValueError):
            parse_historical_rows(json.dumps(document).encode())
        for score in ([True, 0], [-1, 0], [1], None):
            document = json.loads(raw)
            document["matches"][0]["score"]["ft"] = score
            with self.subTest(score=score), self.assertRaises(ValueError):
                parse_historical_rows(json.dumps(document).encode())
        with self.assertRaises(ValueError):
            replace(metadata(raw), retrieved_at=CAPTURED - timedelta(hours=1))
        self.assertEqual(CaptureMetadata.from_dict(metadata(raw).to_dict()), metadata(raw))


if __name__ == "__main__":
    unittest.main()
