"""Synthetic scientific clocks: generated invariants, backfills and revision replay."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
import random
import unittest

from dragonhydra.science.temporal import (
    Availability, DecisionHorizon, TemporalMode, TimedRevision, as_of,
    proven_publication_availability, result_final_availability, unknown_availability,
)


BASE = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
HISTORICAL = datetime(2019, 4, 5, 16, tzinfo=timezone.utc)


def capture(at=BASE, **changes):
    fields = dict(availability_mode=TemporalMode.STRICT_PIT, available_at=at,
                  observed_at=at, retrieved_at=at, ingested_at=at,
                  availability_policy="ACTUAL_CAPTURE", availability_policy_version="1",
                  assumption_reason="Synthetic genuine clock contract", confidence=1.0,
                  source="synthetic:test")
    fields.update(changes)
    return Availability(**fields)


def backfill(at=HISTORICAL, **changes):
    fields = dict(availability_mode=TemporalMode.RECONSTRUCTED_PIT, available_at=at,
                  availability_policy="SYNTHETIC_RECONSTRUCTION", availability_policy_version="1",
                  assumption_reason="Explicit synthetic historical assumption", confidence=0.5)
    fields.update(changes)
    return capture(**fields)


class ScienceAvailabilityTests(unittest.TestCase):
    def test_backfill_never_becomes_strict_historical_knowledge(self):
        original = capture()
        self.assertFalse(original.eligible(HISTORICAL, TemporalMode.STRICT_PIT))
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            replace(original, available_at=HISTORICAL)
        reconstructed = backfill()
        self.assertFalse(reconstructed.eligible(HISTORICAL, TemporalMode.STRICT_PIT))
        self.assertTrue(reconstructed.eligible(HISTORICAL, TemporalMode.RECONSTRUCTED_PIT))
        self.assertEqual(reconstructed.observed_at, BASE)

    def test_capture_and_ingestion_must_all_precede_strict_target(self):
        arrival = BASE + timedelta(minutes=5)
        data = capture(available_at=arrival, ingested_at=arrival)
        self.assertFalse(data.eligible(BASE, TemporalMode.STRICT_PIT))
        self.assertTrue(data.eligible(arrival, TemporalMode.STRICT_PIT))
        self.assertTrue(data.eligible(arrival, TemporalMode.RECONSTRUCTED_PIT))

    def test_unknown_excluded_even_for_later_reconstructed_horizons(self):
        data = unknown_availability(observed_at=BASE, retrieved_at=BASE, ingested_at=BASE,
                                    assumption_reason="No defensible publication proof", source="synthetic")
        for mode in TemporalMode:
            for target in (HISTORICAL, BASE, BASE + timedelta(days=365)):
                self.assertFalse(data.eligible(target, mode))
        self.assertEqual(data.to_dict()["available_at"], None)
        self.assertEqual(data.availability_policy, "UNKNOWN")

    def test_all_reconstruction_labels_survive_json_round_trip(self):
        original = backfill()
        serialized = json.loads(json.dumps(original.to_dict()))
        copied = Availability.from_dict(serialized)
        self.assertEqual(copied, original)
        self.assertEqual(serialized["availability_mode"], "RECONSTRUCTED_PIT")
        for key in ("availability_policy", "availability_policy_version", "assumption_reason", "source"):
            self.assertTrue(serialized[key])
        self.assertEqual(serialized["confidence"], 0.5)
        with self.assertRaises(FrozenInstanceError):
            copied.available_at = BASE

    def test_empty_assumptions_and_invalid_confidence_rejected(self):
        for name in ("availability_policy", "availability_policy_version", "assumption_reason", "source"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                backfill(**{name: " "})
        for confidence in (-0.1, 1.1, float("nan"), float("inf"), True, "0.5"):
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                backfill(confidence=confidence)

    def test_naive_clocks_and_reversed_capture_chronology_rejected(self):
        for name in ("available_at", "observed_at", "retrieved_at", "ingested_at"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                capture(**{name: BASE.replace(tzinfo=None)})
        for change in ({"observed_at": BASE + timedelta(seconds=1)},
                       {"retrieved_at": BASE + timedelta(seconds=1)}):
            with self.assertRaisesRegex(ValueError, "capture chronology"):
                capture(**change)
        with self.assertRaises(ValueError):
            capture().eligible(BASE.replace(tzinfo=None), TemporalMode.STRICT_PIT)

    def test_equal_instants_normalize_to_utc(self):
        instant = BASE.astimezone(timezone(timedelta(hours=5, minutes=30)))
        data = capture(at=instant)
        self.assertEqual(data.available_at.tzinfo, timezone.utc)
        self.assertEqual(data, capture())

    def test_result_final_requires_explicit_positive_bounded_delay(self):
        arguments = dict(event_time=HISTORICAL, observed_at=BASE, retrieved_at=BASE, ingested_at=BASE,
                         availability_policy_version="final-whistle-v1", assumption_reason="Demonstration only",
                         confidence=0.4, source="synthetic:results")
        data = result_final_availability(publication_delay=timedelta(hours=2), **arguments)
        self.assertEqual(data.available_at, HISTORICAL + timedelta(hours=2))
        self.assertEqual(data.availability_mode, TemporalMode.RECONSTRUCTED_PIT)
        self.assertIn("7200s", data.assumption_reason)
        for delay in (timedelta(0), timedelta(seconds=-1), timedelta(days=8), 120):
            with self.subTest(delay=delay), self.assertRaises(ValueError):
                result_final_availability(publication_delay=delay, **arguments)
        with self.assertRaises(ValueError):
            result_final_availability(publication_delay=timedelta(hours=2),
                                      **{**arguments, "assumption_reason": ""})

    def test_historical_publication_proof_does_not_rewrite_capture_time(self):
        arguments = dict(published_at=HISTORICAL, timestamp_evidence="synthetic:archive:sha256-reference",
                         data_class="FIXTURE_SCHEDULE", observed_at=BASE, retrieved_at=BASE, ingested_at=BASE,
                         availability_policy_version="publication-v1", confidence=0.8, source="synthetic")
        data = proven_publication_availability(**arguments)
        self.assertEqual(data.available_at, HISTORICAL)
        self.assertEqual(data.ingested_at, BASE)
        self.assertEqual(data.availability_mode, TemporalMode.RECONSTRUCTED_PIT)
        with self.assertRaises(ValueError):
            proven_publication_availability(**{**arguments, "timestamp_evidence": ""})
        with self.assertRaises(ValueError):
            proven_publication_availability(**{**arguments, "published_at": BASE + timedelta(seconds=1)})
        with self.assertRaises(ValueError):
            proven_publication_availability(**{**arguments, "data_class": "UNSUPPORTED"})

    def test_generated_eligibility_never_exceeds_target_and_preserves_mode(self):
        rng = random.Random(20260924)
        for _ in range(200):
            capture_at = BASE + timedelta(seconds=rng.randrange(-5000, 5000))
            target = BASE + timedelta(seconds=rng.randrange(-5000, 5000))
            strict = capture(at=capture_at)
            reconstructed = backfill(at=capture_at - timedelta(days=365))
            for mode in TemporalMode:
                for value in (strict, reconstructed):
                    if value.eligible(target, mode):
                        self.assertLessEqual(value.available_at, target)
                        if mode is TemporalMode.STRICT_PIT:
                            self.assertEqual(value.availability_mode, TemporalMode.STRICT_PIT)
                            self.assertLessEqual(value.ingested_at, target)


class ScienceHorizonTests(unittest.TestCase):
    def test_named_horizons_and_generic_timestamp(self):
        offsets = {"T_MINUS_24H": 1440, "T_MINUS_6H": 360, "T_MINUS_1H": 60,
                   "T_MINUS_15M": 15, "KICKOFF": 0}
        for name, minutes in offsets.items():
            with self.subTest(name=name):
                horizon = DecisionHorizon.named(name)
                self.assertEqual(horizon.target(BASE), BASE - timedelta(minutes=minutes))
                self.assertEqual(DecisionHorizon.from_dict(horizon.to_dict()), horizon)
        custom = DecisionHorizon.at(BASE - timedelta(minutes=37))
        self.assertEqual(custom.target(BASE), BASE - timedelta(minutes=37))
        self.assertEqual(DecisionHorizon.from_dict(custom.to_dict()), custom)
        relative = DecisionHorizon("CUSTOM_37M", offset_before_kickoff=timedelta(minutes=37))
        self.assertEqual(relative.target(BASE), custom.target(BASE))

    def test_ambiguous_or_mislabelled_horizon_rejected(self):
        for arguments in (("unknown",), ("KICKOFF", timedelta(hours=1)),
                          ("custom", timedelta(minutes=-1)), ("custom", timedelta(0), BASE)):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                DecisionHorizon(*arguments)
        with self.assertRaises(ValueError):
            DecisionHorizon.named("T_MINUS_FUTURE")
        with self.assertRaises(ValueError):
            DecisionHorizon.at(BASE.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            DecisionHorizon.named("KICKOFF").target(BASE.replace(tzinfo=None))


class ScienceRevisionTests(unittest.TestCase):
    def test_revision_replay_and_future_leakage_canary(self):
        first = TimedRevision("fixture-1-v1", "fixture-1", 1, capture())
        later = TimedRevision("fixture-1-v2", "fixture-1", 2,
                              capture(at=BASE + timedelta(hours=2)), first.record_id)
        target = BASE + timedelta(hours=1)
        before = as_of((first,), target, TemporalMode.STRICT_PIT)
        self.assertEqual(as_of((later, first), target, TemporalMode.STRICT_PIT), before)
        self.assertEqual(before, (first,))
        self.assertEqual(as_of((first, later), later.availability.available_at, TemporalMode.STRICT_PIT), (later,))
        self.assertEqual(as_of((first, later), target, TemporalMode.STRICT_PIT), (first,))
        self.assertEqual(first.version, 1)
        with self.assertRaises(FrozenInstanceError):
            first.version = 2

    def test_unknown_revision_does_not_erase_known_version(self):
        first = TimedRevision("known", "fixture", 1, backfill())
        later = TimedRevision("unknown", "fixture", 2, replace(backfill(), available_at=None), "known")
        self.assertEqual(as_of((first, later), BASE, TemporalMode.RECONSTRUCTED_PIT), (first,))

    def test_reconstructed_labels_survive_revision_output(self):
        record = TimedRevision("historical", "fixture", 1, backfill(), payload_hash="a" * 64)
        self.assertEqual(as_of((record,), HISTORICAL, TemporalMode.STRICT_PIT), ())
        result = as_of((record,), HISTORICAL, TemporalMode.RECONSTRUCTED_PIT)[0]
        self.assertEqual(result.to_dict()["availability"], backfill().to_dict())

    def test_invalid_revision_chains_fail_instead_of_selecting_arbitrarily(self):
        first = TimedRevision("a", "fixture", 1, capture())
        second = TimedRevision("b", "fixture", 2, capture(), "a")
        cases = ((first, first), (second,), (first, replace(second, version=1)),
                 (first, replace(second, supersedes_id="missing")),
                 (first, replace(second, entity_key="other")),
                 (first, replace(second, availability=capture(at=BASE - timedelta(seconds=1)))))
        for history in cases:
            with self.subTest(history=history), self.assertRaises(ValueError):
                as_of(history, BASE, TemporalMode.STRICT_PIT)
        for changes in ({"version": True}, {"version": 0}, {"supersedes_id": "a"},
                        {"payload_hash": "not-a-sha256"}, {"availability": {}}, {"record_id": ""}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(first, **changes)

    def test_generated_revision_replay_is_deterministic_and_cutoff_correct(self):
        rng = random.Random(771)
        records = []
        for entity in range(12):
            previous_id = None
            for version in range(1, 5):
                instant = BASE + timedelta(minutes=entity + version * 10)
                record_id = f"fixture-{entity}-v{version}"
                records.append(TimedRevision(record_id, f"fixture-{entity}", version,
                                             capture(at=instant), previous_id))
                previous_id = record_id
        for minutes in range(0, 60, 2):
            target = BASE + timedelta(minutes=minutes)
            original = as_of(records, target, TemporalMode.STRICT_PIT)
            shuffled = list(records)
            rng.shuffle(shuffled)
            self.assertEqual(as_of(shuffled, target, TemporalMode.STRICT_PIT), original)
            for revision in original:
                self.assertLessEqual(revision.availability.available_at, target)
                later_eligible = [item for item in records if item.entity_key == revision.entity_key
                                  and item.version > revision.version and item.availability.available_at <= target]
                self.assertEqual(later_eligible, [])


if __name__ == "__main__":
    unittest.main()
