"""Synthetic identity, ambiguity and temporal revision tests; no external data."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
import unittest

from dragonhydra.science.entities import (
    Competition, CrosswalkRecord, EntityRegistry, EntityType, Fixture,
    FixtureScheduleRevision, ResolutionMethod, ReviewState, Team,
    competition_id, fixture_id, team_id,
)


BASE = datetime(2026, 9, 24, tzinfo=timezone.utc)


def at(hours):
    return BASE + timedelta(hours=hours)


def registry_with_fixture():
    registry = EntityRegistry()
    competition = Competition(competition_id("synthetic", "league-a"), "Synthetic League")
    home = Team(team_id("synthetic:league-a", "team-a"), "Synthetic Home")
    away = Team(team_id("synthetic:league-a", "team-b"), "Synthetic Away")
    for entity in (competition, home, away):
        registry.register(entity)
    fixture = Fixture(fixture_id("synthetic", competition.canonical_id, "2026-27", "round-1:a:b"),
                      competition.canonical_id, "2026-27", home.canonical_id, away.canonical_id)
    registry.register(fixture)
    return registry, competition, home, away, fixture


def mapping(team, *, key="a", name="Synthetic Home", method=ResolutionMethod.EXACT_PROVIDER_ID,
            reviewed=ReviewState.CONFIRMED, revision=1, recorded=BASE):
    return CrosswalkRecord("synthetic", key, name, EntityType.TEAM,
                           team.canonical_id if team else None, BASE, None, recorded,
                           method, 1.0 if team else 0.0, reviewed, revision)


class EntityIdentityTests(unittest.TestCase):
    def test_deterministic_scoped_ids_and_delimiter_collision_resistance(self):
        competition = competition_id("synthetic", "league")
        self.assertEqual(competition, competition_id("synthetic", "league"))
        self.assertNotEqual(team_id("provider:a", "b"), team_id("provider", "a:b"))
        self.assertNotEqual(team_id("provider-a", "1"), team_id("provider-b", "1"))
        self.assertNotEqual(competition, team_id("synthetic", "league"))
        reference = fixture_id("provider-a", competition, "2025-26", "1")
        self.assertNotEqual(reference, fixture_id("provider-b", competition, "2025-26", "1"))
        self.assertNotEqual(reference, fixture_id("provider-a", competition, "2026-27", "1"))
        self.assertNotEqual(reference, fixture_id("provider-a", competition_id("synthetic", "other"),
                                                 "2025-26", "1"))

    def test_immutable_entities_and_collision_rejection(self):
        registry, _, home, _, fixture = registry_with_fixture()
        with self.assertRaises(FrozenInstanceError):
            home.name = "Changed"
        with self.assertRaises(ValueError):
            registry.register(replace(home, name="Colliding identity"))
        with self.assertRaises(ValueError):
            replace(fixture, away_team_id=fixture.home_team_id)
        with self.assertRaises(ValueError):
            replace(fixture, home_team_id=fixture.competition_id)
        empty = EntityRegistry()
        with self.assertRaises(ValueError):
            empty.register(fixture)

    def test_json_roundtrip_is_exact_deterministic_replay(self):
        registry, _, home, _, fixture = registry_with_fixture()
        registry.append_crosswalk(mapping(home))
        registry.append_schedule(FixtureScheduleRevision(fixture.canonical_id, 1, BASE, at(24),
                                                        "SCHEDULED", "synthetic"))
        payload = json.loads(json.dumps(registry.to_dict(), sort_keys=True))
        replayed = EntityRegistry.from_dict(payload)
        self.assertEqual(registry.to_dict(), replayed.to_dict())
        self.assertEqual(registry.entities, replayed.entities)
        self.assertEqual(registry.crosswalks, replayed.crosswalks)
        self.assertEqual(registry.schedule_at(fixture.canonical_id, at(1)),
                         replayed.schedule_at(fixture.canonical_id, at(1)))
        with self.assertRaises(ValueError):
            EntityRegistry.from_dict({**payload, "schema_version": "unknown"})


class CrosswalkTests(unittest.TestCase):
    def test_ambiguous_normalized_name_and_unresolved_candidates_are_never_guessed(self):
        registry, _, home, away, _ = registry_with_fixture()
        registry.append_crosswalk(mapping(home, name="  FC   SAME "))
        first = registry.resolve_name("synthetic", EntityType.TEAM, "fc same", valid_at=BASE, known_at=BASE)
        self.assertEqual(first.canonical_id, home.canonical_id)
        registry.append_crosswalk(mapping(away, key="b", name="fc same"))
        ambiguous = registry.resolve_name("synthetic", EntityType.TEAM, "fc same", valid_at=BASE, known_at=BASE)
        self.assertFalse(ambiguous.resolved)
        self.assertEqual(ambiguous.reason_code, "AMBIGUOUS_NAME")
        registry.append_crosswalk(mapping(None, key="c", name="fc same", method=ResolutionMethod.UNRESOLVED,
                                         reviewed=ReviewState.PENDING))
        unresolved = registry.resolve_name("synthetic", EntityType.TEAM, "fc same", valid_at=BASE, known_at=BASE)
        self.assertFalse(unresolved.resolved)
        self.assertEqual(unresolved.reason_code, "UNREVIEWED_NAME_CANDIDATE")

    def test_declared_alias_only_no_fuzzy_name_guess_and_provider_isolation(self):
        registry, _, home, _, _ = registry_with_fixture()
        registry.append_crosswalk(mapping(home, key="declared-alias:home", name="Synthetic FC",
                                         method=ResolutionMethod.DECLARED_ALIAS))
        self.assertTrue(registry.resolve_name("synthetic", EntityType.TEAM, " synthetic fc ",
                                             valid_at=BASE, known_at=BASE).resolved)
        self.assertFalse(registry.resolve_name("synthetic", EntityType.TEAM, "Synthetic",
                                              valid_at=BASE, known_at=BASE).resolved)
        self.assertFalse(registry.resolve("different-provider", EntityType.TEAM, "declared-alias:home",
                                         valid_at=BASE, known_at=BASE).resolved)

    def test_unresolved_record_and_pending_mapping_are_first_class(self):
        registry, _, home, _, _ = registry_with_fixture()
        unresolved = mapping(None, method=ResolutionMethod.UNRESOLVED, reviewed=ReviewState.PENDING)
        registry.append_crosswalk(unresolved)
        result = registry.resolve("synthetic", EntityType.TEAM, "a", valid_at=BASE, known_at=BASE)
        self.assertEqual(result.mappings, (unresolved,))
        self.assertFalse(result.resolved)
        registry.append_crosswalk(mapping(home, revision=2, recorded=at(1), reviewed=ReviewState.PENDING))
        self.assertFalse(registry.resolve("synthetic", EntityType.TEAM, "a", valid_at=at(1), known_at=at(1)).resolved)
        with self.assertRaises(ValueError):
            replace(unresolved, canonical_id=home.canonical_id)

    def test_later_correction_and_backfilled_map_cannot_change_earlier_knowledge(self):
        registry, _, home, away, _ = registry_with_fixture()
        original = mapping(home, recorded=at(1))
        registry.append_crosswalk(original)
        corrected = mapping(away, revision=2, recorded=at(3), method=ResolutionMethod.MANUAL)
        registry.append_crosswalk(corrected)
        for hour in range(5):
            result = registry.resolve("synthetic", EntityType.TEAM, "a", valid_at=at(hour), known_at=at(hour))
            expected = None if hour < 1 else home.canonical_id if hour < 3 else away.canonical_id
            self.assertEqual(result.canonical_id, expected)
            self.assertTrue(all(row.recorded_at <= at(hour) for row in result.mappings))
        self.assertEqual(registry.crosswalks, (original, corrected))
        registry.append_crosswalk(corrected)  # Idempotent identical replay, never a mutation.
        self.assertEqual(len(registry.crosswalks), 2)
        with self.assertRaises(ValueError):
            registry.append_crosswalk(replace(corrected, provider_name="changed revision bytes"))
        with self.assertRaises(ValueError):
            registry.append_crosswalk(replace(corrected, revision=3, recorded_at=at(2)))

    def test_effective_validity_is_separate_from_knowledge_and_is_half_open(self):
        registry, _, home, _, _ = registry_with_fixture()
        registry.append_crosswalk(mapping(home))
        registry.append_crosswalk(replace(mapping(home, revision=2, recorded=at(3)), valid_to=at(2)))
        self.assertTrue(registry.resolve("synthetic", EntityType.TEAM, "a", valid_at=at(2), known_at=at(2)).resolved)
        self.assertFalse(registry.resolve("synthetic", EntityType.TEAM, "a", valid_at=at(2), known_at=at(3)).resolved)
        self.assertTrue(registry.resolve("synthetic", EntityType.TEAM, "a", valid_at=at(1), known_at=at(3)).resolved)

    def test_crosswalk_rejects_invalid_contract_values_and_unknown_references(self):
        registry, competition, home, _, _ = registry_with_fixture()
        good = mapping(home)
        for change in ({"confidence": float("nan")}, {"confidence": 1.1}, {"confidence": True},
                       {"valid_from": BASE.replace(tzinfo=None)}, {"valid_to": BASE},
                       {"recorded_at": BASE.replace(tzinfo=None)}, {"canonical_id": competition.canonical_id},
                       {"revision": 0}, {"resolution_method": "MANUAL"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(good, **change)
        with self.assertRaises(ValueError):
            registry.append_crosswalk(replace(good, canonical_id=team_id("unknown", "team")))


class FixtureScheduleTests(unittest.TestCase):
    def test_postponement_changes_schedule_history_not_fixture_identity(self):
        registry, competition, home, away, fixture = registry_with_fixture()
        initial = FixtureScheduleRevision(fixture.canonical_id, 1, BASE, at(24), "SCHEDULED", "synthetic")
        postponed = FixtureScheduleRevision(fixture.canonical_id, 2, at(2), None, "POSTPONED", "synthetic")
        rescheduled = FixtureScheduleRevision(fixture.canonical_id, 3, at(4), at(72), "RESCHEDULED", "synthetic")
        for row in (initial, postponed, rescheduled):
            registry.append_schedule(row)
        self.assertIsNone(registry.schedule_at(fixture.canonical_id, at(-1)))
        self.assertEqual(registry.schedule_at(fixture.canonical_id, at(1)), initial)
        self.assertEqual(registry.schedule_at(fixture.canonical_id, at(3)), postponed)
        self.assertEqual(registry.schedule_at(fixture.canonical_id, at(4)), rescheduled)
        self.assertEqual(registry.entities, (competition, home, away, fixture))
        for hour in range(8):
            self.assertLessEqual(registry.schedule_at(fixture.canonical_id, at(hour)).available_at, at(hour))
        self.assertEqual(registry.schedules, (initial, postponed, rescheduled))

    def test_schedule_revisions_reject_overwrite_backdated_knowledge_and_unknown_fixture(self):
        registry, competition, _, _, fixture = registry_with_fixture()
        row = FixtureScheduleRevision(fixture.canonical_id, 1, BASE, at(24), "SCHEDULED", "synthetic")
        registry.append_schedule(row)
        registry.append_schedule(row)
        self.assertEqual(len(registry.schedules), 1)
        for bad in (replace(row, scheduled_at=at(48)), replace(row, revision=2, available_at=at(-1)),
                    replace(row, fixture_id=fixture_id("other", competition.canonical_id, "2026-27", "1"))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                registry.append_schedule(bad)
        with self.assertRaises(ValueError):
            replace(row, available_at=BASE.replace(tzinfo=None))


if __name__ == "__main__":
    unittest.main()
