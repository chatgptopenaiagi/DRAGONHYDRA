"""Synthetic evidence cases; no network, external sports data or database writes."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from dragonhydra.medusa.evidence import (
    AsOfRequest, AvailabilityBoundary, ClaimKind, EntityIdentity, EvidenceConfidence, EvidenceConflict,
    EvidenceLedger, EvidenceStatus, EvidenceSupersession, HydraEvidencePacket,
    MedusaEvidenceVersion, SourceIdentity, TemporalEvidence,
)


BASE = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
SOURCE = SourceIdentity("synthetic-official", "Synthetic official source")
FIXTURE = EntityIdentity("fixture", "synthetic-fixture-1")


def at(minutes: int) -> datetime:
    return BASE + timedelta(minutes=minutes)


def version(version_id, available_minute, value, *, event_minute=0,
            observed_minute=None, updated_minute=None, expiry_minute=None,
            kind=ClaimKind.OBSERVED, predicate="home.goals", source=SOURCE,
            entity=FIXTURE, status=EvidenceStatus.KNOWN):
    return MedusaEvidenceVersion(
        version_id,
        HydraEvidencePacket(
            f"packet-{version_id}", source, entity, predicate, value, kind,
            TemporalEvidence(
                at(event_minute),
                at(available_minute if observed_minute is None else observed_minute),
                at(available_minute),
                at(available_minute if updated_minute is None else updated_minute),
                None if expiry_minute is None else at(expiry_minute),
                f"synthetic-receipt-{version_id}",
            ),
            EvidenceConfidence(0.9, "Synthetic confidence for contract testing"),
            (f"synthetic-artifact-{version_id}",),
        ),
        ("SYNTHETIC_VALIDATION",), status,
    )


def request(minute, predicate="home.goals", source_id=None):
    return AsOfRequest(FIXTURE, predicate, at(minute), source_id)


class SyntheticCasesTests(unittest.TestCase):
    def test_delayed_final_result_rejects_event_time_as_knowledge(self):
        result = version("delayed-final", 15, "2-1", event_minute=0,
                         observed_minute=12, updated_minute=1, predicate="final.score")
        ledger = EvidenceLedger((result,))
        before = ledger.select(request(14, "final.score"))
        self.assertEqual(before.status, EvidenceStatus.MISSING)
        self.assertFalse(before.usable)
        self.assertEqual(before.versions, ())
        self.assertIn("FUTURE_INFORMATION_REJECTED", before.reason_codes)
        self.assertEqual(ledger.select(request(15, "final.score")).versions, (result,))

    def test_corrected_match_event_preserves_historical_replay(self):
        original = version("goal-v1", 2, 1, event_minute=0)
        corrected = version("goal-v2", 8, 0, event_minute=0,
                            observed_minute=7, updated_minute=6)
        ledger = EvidenceLedger(
            (original, corrected),
            (EvidenceSupersession("goal-v1", "goal-v2", "Synthetic VAR disallowance"),),
        )
        for minute in (2, 5, 7):
            with self.subTest(minute=minute):
                self.assertEqual(ledger.select(request(minute)).versions, (original,))
        self.assertEqual(ledger.select(request(8)).versions, (corrected,))
        self.assertEqual(ledger.versions, (original, corrected))
        self.assertEqual(original.packet.value, 1)
        self.assertEqual(ledger.select(request(5)).versions, (original,))

    def test_expected_goalkeeper_becomes_confirmed_only_when_available(self):
        expected = version("keeper-expected", 0, "keeper-a", event_minute=60,
                           expiry_minute=60, kind=ClaimKind.EXPECTED,
                           predicate="home.goalkeeper")
        confirmed = version("keeper-confirmed", 30, "keeper-b", event_minute=60,
                            kind=ClaimKind.CONFIRMED, predicate="home.goalkeeper")
        ledger = EvidenceLedger(
            (expected, confirmed),
            (EvidenceSupersession(expected.version_id, confirmed.version_id, "Confirmed lineup"),),
        )
        before = ledger.select(request(29, "home.goalkeeper"))
        after = ledger.select(request(30, "home.goalkeeper"))
        self.assertEqual(before.versions, (expected,))
        self.assertEqual(before.versions[0].packet.claim_kind, ClaimKind.EXPECTED)
        self.assertEqual(after.versions, (confirmed,))
        self.assertEqual(after.versions[0].packet.claim_kind, ClaimKind.CONFIRMED)
        # An expected event may legitimately lie in the future relative to observation.
        self.assertGreater(expected.packet.temporal.event_at, before.request.target_as_of_at)


class TemporalContractTests(unittest.TestCase):
    def test_strict_feature_cutoff_excludes_exact_target_without_changing_default(self):
        item = version("exact-kickoff", 0, 1)
        ledger = EvidenceLedger((item,))
        self.assertTrue(ledger.select(request(0)).usable)
        strict = replace(request(0), availability_boundary=AvailabilityBoundary.STRICTLY_BEFORE)
        rejected = ledger.select(strict)
        self.assertEqual(rejected.status, EvidenceStatus.MISSING)
        self.assertEqual(rejected.versions, ())
        self.assertIn("EXACT_TARGET_AVAILABILITY_REJECTED", rejected.reason_codes)
        self.assertNotIn("FUTURE_INFORMATION_REJECTED", rejected.reason_codes)
        later = ledger.select(replace(strict, target_as_of_at=at(1)))
        self.assertTrue(later.usable)
        self.assertIn("AVAILABLE_STRICTLY_BEFORE_TARGET", later.reason_codes)

    def test_strict_cutoff_defers_supersession_at_exact_target(self):
        original, correction = version("original", 0, 1), version("correction", 5, 0)
        ledger = EvidenceLedger((original, correction),
                                (EvidenceSupersession("original", "correction", "Correction"),))
        strict = replace(request(5), availability_boundary=AvailabilityBoundary.STRICTLY_BEFORE)
        self.assertEqual(ledger.select(strict).versions, (original,))
        self.assertEqual(ledger.select(request(5)).versions, (correction,))

    def test_all_six_timestamp_contexts_require_timezones(self):
        temporal = version("aware", 0, 1, expiry_minute=10).packet.temporal
        for field in ("event_at", "observed_at", "available_at", "updated_at", "expires_at"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(temporal, **{field: at(0).replace(tzinfo=None)})
        with self.assertRaises(ValueError):
            replace(request(0), target_as_of_at=at(0).replace(tzinfo=None))

    def test_available_cannot_precede_observation_or_update(self):
        for field in ("observed_minute", "updated_minute"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                version("bad-availability", 0, 1, **{field: 1})

    def test_availability_requires_proof_reference(self):
        with self.assertRaises(ValueError):
            replace(version("v", 0, 1).packet.temporal, availability_proof=" ")

    def test_expiry_is_exclusive_and_distinct_from_missing(self):
        item = version("expiring", 0, 1, expiry_minute=10)
        ledger = EvidenceLedger((item,))
        self.assertTrue(ledger.select(request(0)).usable)
        self.assertTrue(ledger.select(request(9)).usable)
        selection = ledger.select(request(10))
        self.assertEqual(selection.status, EvidenceStatus.STALE)
        self.assertEqual(selection.versions, ())
        self.assertFalse(selection.usable)
        self.assertIn("EVIDENCE_EXPIRED", selection.reason_codes)
        self.assertEqual(ledger.select(request(-1)).status, EvidenceStatus.MISSING)

    def test_expiry_must_follow_availability(self):
        for expiry in (-1, 0):
            with self.subTest(expiry=expiry), self.assertRaises(ValueError):
                version("bad-expiry", 0, 1, expiry_minute=expiry)

    def test_timezone_offsets_compare_as_instants(self):
        item = version("offset", 0, 1)
        local_target = at(0).astimezone(timezone(timedelta(hours=2)))
        self.assertTrue(EvidenceLedger((item,)).select(replace(request(0), target_as_of_at=local_target)).usable)

    def test_confidence_must_be_finite_in_unit_interval(self):
        for score in (-0.01, 1.01, float("nan"), float("inf"), True, "0.5"):
            with self.subTest(score=score), self.assertRaises(ValueError):
                EvidenceConfidence(score, "test")
        self.assertEqual(EvidenceConfidence(0, "minimum").score, 0)
        self.assertEqual(EvidenceConfidence(1, "maximum").score, 1)

    def test_contracts_are_frozen_and_payloads_cannot_be_mutable(self):
        item = version("immutable", 0, 1)
        with self.assertRaises(FrozenInstanceError):
            item.packet.value = 2
        with self.assertRaises(ValueError):
            replace(item.packet, value={"goals": 1})
        with self.assertRaises(ValueError):
            replace(item.packet, provenance_ids=["mutable"])
        with self.assertRaises(ValueError):
            EvidenceLedger([item])

    def test_provenance_and_validation_reasons_are_required(self):
        item = version("provenance", 0, 1)
        with self.assertRaises(ValueError):
            replace(item.packet, provenance_ids=())
        with self.assertRaises(ValueError):
            replace(item, validation_reason_codes=())

    def test_contextual_state_cannot_be_written_as_version_status(self):
        for status in (EvidenceStatus.MISSING, EvidenceStatus.STALE, EvidenceStatus.CONFLICTING, "KNOWN"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                version("bad-state", 0, 1, status=status)


class SupersessionAndConflictTests(unittest.TestCase):
    def test_expired_replacement_never_revives_old_evidence(self):
        old = version("old", 0, 1)
        new = version("new", 5, 2, expiry_minute=10)
        ledger = EvidenceLedger((old, new), (EvidenceSupersession("old", "new", "Correction"),))
        self.assertEqual(ledger.select(request(11)).status, EvidenceStatus.STALE)
        self.assertEqual(ledger.select(request(11)).versions, ())
        self.assertEqual(ledger.select(request(4)).versions, (old,))

    def test_chain_replays_every_revision(self):
        versions = tuple(version(f"v{i}", i * 10, i) for i in range(3))
        ledger = EvidenceLedger(versions, (
            EvidenceSupersession("v0", "v1", "Correction 1"),
            EvidenceSupersession("v1", "v2", "Correction 2"),
        ))
        for index, minute in enumerate((9, 19, 20)):
            self.assertEqual(ledger.select(request(minute)).versions, (versions[index],))

    def test_cycles_and_nonadvancing_revisions_rejected(self):
        old, new = version("old", 0, 1), version("new", 5, 2)
        with self.assertRaises(ValueError):
            EvidenceLedger((old, new), (
                EvidenceSupersession("old", "new", "Forward"),
                EvidenceSupersession("new", "old", "Cycle"),
            ))
        with self.assertRaises(ValueError):
            EvidenceLedger((old, version("same-time", 0, 2)),
                           (EvidenceSupersession("old", "same-time", "Ambiguous timing"),))
        with self.assertRaises(ValueError):
            EvidenceSupersession("old", "old", "Self cycle")

    def test_missing_duplicate_branch_and_merge_links_rejected(self):
        items = tuple(version(f"v{i}", i, i) for i in range(3))
        for links in (
            (EvidenceSupersession("v0", "absent", "Missing"),),
            (EvidenceSupersession("v0", "v1", "A"), EvidenceSupersession("v0", "v2", "Branch")),
            (EvidenceSupersession("v0", "v2", "A"), EvidenceSupersession("v1", "v2", "Merge")),
        ):
            with self.subTest(links=links), self.assertRaises(ValueError):
                EvidenceLedger(items, links)
        with self.assertRaises(ValueError):
            EvidenceLedger((items[0], items[0]))

    def test_cross_entity_predicate_and_source_supersessions_rejected(self):
        old = version("old", 0, 1)
        alternatives = (
            version("new", 5, 2, entity=EntityIdentity("fixture", "other")),
            version("new", 5, 2, predicate="away.goals"),
            version("new", 5, 2, source=SourceIdentity("other", "Other source")),
        )
        for new in alternatives:
            with self.subTest(packet=new.packet), self.assertRaises(ValueError):
                EvidenceLedger((old, new), (EvidenceSupersession("old", "new", "Invalid scope"),))

    def test_independent_sources_disagree_without_silent_winner(self):
        first = version("first", 0, 1)
        second = version("second", 5, 2, source=SourceIdentity("other", "Other source"))
        ledger = EvidenceLedger((first, second))
        self.assertTrue(ledger.select(request(4)).usable)
        selection = ledger.select(request(5))
        self.assertEqual(selection.status, EvidenceStatus.CONFLICTING)
        self.assertEqual(selection.versions, (first, second))
        self.assertFalse(selection.usable)
        self.assertEqual(ledger.select(request(5, source_id=SOURCE.source_id)).versions, (first,))

    def test_explicit_conflict_respects_its_availability(self):
        first = version("first", 0, 1)
        second = version("second", 5, 1, source=SourceIdentity("other", "Other source"))
        conflict = EvidenceConflict("conflict-1", "first", "second", at(8),
                                    "synthetic-conflict-receipt", "Same value, conflicting provenance")
        ledger = EvidenceLedger((first, second), conflicts=(conflict,))
        self.assertTrue(ledger.select(request(7)).usable)
        self.assertEqual(ledger.select(request(8)).status, EvidenceStatus.CONFLICTING)
        with self.assertRaises(ValueError):
            EvidenceLedger((first, second), conflicts=(replace(conflict, available_at=at(4)),))

    def test_unknown_and_suspicious_evidence_are_not_usable(self):
        for status in (EvidenceStatus.UNKNOWN, EvidenceStatus.SUSPICIOUS):
            with self.subTest(status=status):
                selection = EvidenceLedger((version("v", 0, 1, status=status),)).select(request(0))
                self.assertEqual(selection.status, status)
                self.assertFalse(selection.usable)

    def test_unrelated_entities_and_predicates_are_not_selected(self):
        item = version("other", 0, 1, entity=EntityIdentity("fixture", "other"))
        selection = EvidenceLedger((item,)).select(request(0))
        self.assertEqual(selection.status, EvidenceStatus.MISSING)
        self.assertEqual(selection.versions, ())


if __name__ == "__main__":
    unittest.main()
