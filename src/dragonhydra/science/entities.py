"""Small immutable identity core; schedules are evidence, never fixture identity.

This registry is a derived experiment artifact, not a replacement for SQL Server.
Provider keys and aliases are declared by the caller; ambiguous names stay unresolved.
Knowledge time applies to crosswalks as well as sports observations.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import json
import math
import unicodedata
from uuid import UUID, uuid5


_NAMESPACE = UUID("ba1d50eb-87a6-5d25-9c90-f86e8501d91f")


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")


def _time(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


class EntityType(StrEnum):
    COMPETITION = "competition"
    TEAM = "team"
    FIXTURE = "fixture"


class ResolutionMethod(StrEnum):
    EXACT_PROVIDER_ID = "EXACT_PROVIDER_ID"
    EXACT_NORMALIZED_NAME = "EXACT_NORMALIZED_NAME"
    DECLARED_ALIAS = "DECLARED_ALIAS"
    MANUAL = "MANUAL"
    UNRESOLVED = "UNRESOLVED"


class ReviewState(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class CanonicalId:
    value: str

    def __post_init__(self) -> None:
        if str(UUID(self.value)) != self.value:
            raise ValueError("Canonical ID must be a normalized UUID")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CompetitionId(CanonicalId):
    pass


@dataclass(frozen=True)
class TeamId(CanonicalId):
    pass


@dataclass(frozen=True)
class FixtureId(CanonicalId):
    pass


_ID_TYPES = {EntityType.COMPETITION: CompetitionId, EntityType.TEAM: TeamId,
             EntityType.FIXTURE: FixtureId}


def _id(kind: EntityType, *parts: str) -> CanonicalId:
    for part in parts:
        _text(part, "identity key")
    # JSON arrays avoid delimiter collisions; names are never silently normalized.
    payload = json.dumps([kind.value, *parts], ensure_ascii=False, separators=(",", ":"))
    return _ID_TYPES[kind](str(uuid5(_NAMESPACE, payload)))


def competition_id(namespace: str, explicit_key: str) -> CompetitionId:
    return _id(EntityType.COMPETITION, namespace, explicit_key)


def team_id(namespace: str, explicit_key: str) -> TeamId:
    return _id(EntityType.TEAM, namespace, explicit_key)


def fixture_id(provider: str, competition: CompetitionId, season: str,
               explicit_fixture_key: str) -> FixtureId:
    """A provider key or explicitly declared round/team key; never a kickoff time.

    For providers without stable IDs, the caller owns key uniqueness and documents
    its policy. Rematches need distinct declared keys, not inferred dates.
    """
    if not isinstance(competition, CompetitionId):
        raise ValueError("Fixture identity requires a typed competition ID")
    return _id(EntityType.FIXTURE, provider, str(competition), season, explicit_fixture_key)


@dataclass(frozen=True)
class Competition:
    canonical_id: CompetitionId
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_id, CompetitionId):
            raise ValueError("Competition requires CompetitionId")
        _text(self.name, "name")


@dataclass(frozen=True)
class Team:
    canonical_id: TeamId
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_id, TeamId):
            raise ValueError("Team requires TeamId")
        _text(self.name, "name")


@dataclass(frozen=True)
class Fixture:
    canonical_id: FixtureId
    competition_id: CompetitionId
    season: str
    home_team_id: TeamId
    away_team_id: TeamId

    def __post_init__(self) -> None:
        if (not isinstance(self.canonical_id, FixtureId)
                or not isinstance(self.competition_id, CompetitionId)
                or not isinstance(self.home_team_id, TeamId)
                or not isinstance(self.away_team_id, TeamId)):
            raise ValueError("Fixture requires typed canonical IDs")
        _text(self.season, "season")
        if self.home_team_id == self.away_team_id:
            raise ValueError("Fixture teams must be distinct")


@dataclass(frozen=True)
class CrosswalkRecord:
    provider: str
    provider_entity_id: str
    provider_name: str
    entity_type: EntityType
    canonical_id: CanonicalId | None
    valid_from: datetime
    valid_to: datetime | None
    recorded_at: datetime
    resolution_method: ResolutionMethod
    confidence: float
    review_state: ReviewState
    revision: int = 1

    def __post_init__(self) -> None:
        for field in ("provider", "provider_entity_id", "provider_name"):
            _text(getattr(self, field), field)
        if not isinstance(self.entity_type, EntityType):
            raise ValueError("entity_type must be an EntityType")
        if not isinstance(self.resolution_method, ResolutionMethod):
            raise ValueError("resolution_method must be a ResolutionMethod")
        if not isinstance(self.review_state, ReviewState):
            raise ValueError("review_state must be a ReviewState")
        _time(self.valid_from, "valid_from")
        _time(self.recorded_at, "recorded_at")
        if self.valid_to is not None:
            _time(self.valid_to, "valid_to")
            if self.valid_to <= self.valid_from:
                raise ValueError("Validity intervals are nonempty and half-open")
        if (isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float))
                or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise ValueError("confidence must be finite and between zero and one")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("revision must be a positive integer")
        if self.resolution_method == ResolutionMethod.UNRESOLVED:
            if self.canonical_id is not None:
                raise ValueError("UNRESOLVED must not claim a canonical ID")
        elif not isinstance(self.canonical_id, _ID_TYPES[self.entity_type]):
            raise ValueError("Resolved mapping requires a canonical ID of the correct type")


@dataclass(frozen=True)
class EntityResolution:
    canonical_id: CanonicalId | None
    resolution_method: ResolutionMethod
    reason_code: str
    mappings: tuple[CrosswalkRecord, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.canonical_id is not None


@dataclass(frozen=True)
class FixtureScheduleRevision:
    fixture_id: FixtureId
    revision: int
    available_at: datetime
    scheduled_at: datetime | None
    status: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.fixture_id, FixtureId):
            raise ValueError("Schedule revision requires FixtureId")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("revision must be a positive integer")
        _time(self.available_at, "available_at")
        if self.scheduled_at is not None:
            _time(self.scheduled_at, "scheduled_at")
        _text(self.status, "status")
        _text(self.source, "source")


def normalize_name(name: str) -> str:
    """Only Unicode/whitespace/case normalization; no fuzzy or suffix guesses."""
    _text(name, "name")
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


class EntityRegistry:
    """Append-only in-memory registry with deterministic JSON-ready replay.

    A crosswalk correction is another revision. Knowledge cutoffs filter before
    effective-validity selection; later corrections never rewrite earlier views.
    Records made in 2026 do not establish known identities in 2019: historical
    experiments must explicitly disclose use of a reconstructed identity map.
    """

    def __init__(self) -> None:
        self._entities: dict[CanonicalId, Competition | Team | Fixture] = {}
        self._crosswalks: list[CrosswalkRecord] = []
        self._schedules: list[FixtureScheduleRevision] = []

    @property
    def entities(self) -> tuple[Competition | Team | Fixture, ...]:
        return tuple(self._entities.values())

    @property
    def crosswalks(self) -> tuple[CrosswalkRecord, ...]:
        return tuple(self._crosswalks)

    @property
    def schedules(self) -> tuple[FixtureScheduleRevision, ...]:
        return tuple(self._schedules)

    def register(self, entity: Competition | Team | Fixture) -> None:
        if not isinstance(entity, (Competition, Team, Fixture)):
            raise ValueError("Only competition, team and fixture entities are supported")
        previous = self._entities.get(entity.canonical_id)
        if previous is not None and previous != entity:
            raise ValueError("Canonical identity collision; explicit review required")
        if isinstance(entity, Fixture):
            for reference in (entity.competition_id, entity.home_team_id, entity.away_team_id):
                if reference not in self._entities:
                    raise ValueError("Register referenced competition and teams before fixture")
        self._entities[entity.canonical_id] = entity

    def append_crosswalk(self, record: CrosswalkRecord) -> None:
        if record.canonical_id is not None and record.canonical_id not in self._entities:
            raise ValueError("Crosswalk references an unregistered canonical entity")
        history = [old for old in self._crosswalks if
                   (old.provider, old.entity_type, old.provider_entity_id)
                   == (record.provider, record.entity_type, record.provider_entity_id)]
        if record in history:
            return
        if record.revision != len(history) + 1:
            raise ValueError("Crosswalk revisions must be consecutive and append-only")
        if history and record.recorded_at < history[-1].recorded_at:
            raise ValueError("Crosswalk revision knowledge time cannot move backwards")
        self._crosswalks.append(record)

    def _mapping_at(self, provider: str, entity_type: EntityType, provider_entity_id: str,
                    valid_at: datetime, known_at: datetime) -> CrosswalkRecord | None:
        _time(valid_at, "valid_at")
        _time(known_at, "known_at")
        history = [row for row in self._crosswalks if row.provider == provider
                   and row.entity_type == entity_type and row.provider_entity_id == provider_entity_id
                   and row.recorded_at <= known_at and row.valid_from <= valid_at]
        if not history:
            return None
        latest = max(history, key=lambda row: row.revision)
        # A closed correction must not fall back to a superseded open interval.
        if latest.valid_to is not None and valid_at >= latest.valid_to:
            return None
        return latest

    def resolve(self, provider: str, entity_type: EntityType, provider_entity_id: str,
                *, valid_at: datetime, known_at: datetime) -> EntityResolution:
        record = self._mapping_at(provider, entity_type, provider_entity_id, valid_at, known_at)
        if record is None:
            return EntityResolution(None, ResolutionMethod.UNRESOLVED, "NO_VALID_KNOWN_MAPPING")
        if record.canonical_id is None or record.review_state != ReviewState.CONFIRMED:
            return EntityResolution(None, ResolutionMethod.UNRESOLVED,
                                    "UNRESOLVED_OR_UNCONFIRMED", (record,))
        return EntityResolution(record.canonical_id, record.resolution_method, "RESOLVED", (record,))

    def resolve_name(self, provider: str, entity_type: EntityType, name: str,
                     *, valid_at: datetime, known_at: datetime) -> EntityResolution:
        normalized = normalize_name(name)
        _time(valid_at, "valid_at")
        _time(known_at, "known_at")
        keys = sorted({row.provider_entity_id for row in self._crosswalks
                       if row.provider == provider and row.entity_type == entity_type})
        records = tuple(row for key in keys
                        if (row := self._mapping_at(provider, entity_type, key, valid_at, known_at))
                        and normalize_name(row.provider_name) == normalized)
        # An unresolved same-name candidate is ambiguity, not permission to guess.
        if any(row.canonical_id is None or row.review_state != ReviewState.CONFIRMED for row in records):
            return EntityResolution(None, ResolutionMethod.UNRESOLVED, "UNREVIEWED_NAME_CANDIDATE", records)
        ids = {row.canonical_id for row in records}
        if len(ids) != 1:
            return EntityResolution(None, ResolutionMethod.UNRESOLVED,
                                    "AMBIGUOUS_NAME" if ids else "NAME_NOT_FOUND", records)
        return EntityResolution(next(iter(ids)), ResolutionMethod.EXACT_NORMALIZED_NAME,
                                "UNIQUE_CONFIRMED_NAME", records)

    def append_schedule(self, record: FixtureScheduleRevision) -> None:
        if record.fixture_id not in self._entities:
            raise ValueError("Schedule references an unregistered fixture")
        history = [old for old in self._schedules if old.fixture_id == record.fixture_id]
        if record in history:
            return
        if record.revision != len(history) + 1:
            raise ValueError("Schedule revisions must be consecutive and append-only")
        if history and record.available_at < history[-1].available_at:
            raise ValueError("Schedule revision availability cannot move backwards")
        self._schedules.append(record)

    def schedule_at(self, fixture: FixtureId, target_as_of: datetime) -> FixtureScheduleRevision | None:
        _time(target_as_of, "target_as_of")
        eligible = [row for row in self._schedules if row.fixture_id == fixture
                    and row.available_at <= target_as_of]
        return max(eligible, key=lambda row: row.revision, default=None)

    def to_dict(self) -> dict:
        def entity_record(entity):
            if isinstance(entity, Fixture):
                return {"entity_type": "fixture", "canonical_id": str(entity.canonical_id),
                        "competition_id": str(entity.competition_id), "season": entity.season,
                        "home_team_id": str(entity.home_team_id), "away_team_id": str(entity.away_team_id)}
            return {"entity_type": "competition" if isinstance(entity, Competition) else "team",
                    "canonical_id": str(entity.canonical_id), "name": entity.name}

        return {"schema_version": "1", "entities": [entity_record(row) for row in self.entities],
                "crosswalks": [{"provider": row.provider, "provider_entity_id": row.provider_entity_id,
                                "provider_name": row.provider_name, "entity_type": row.entity_type.value,
                                "canonical_id": str(row.canonical_id) if row.canonical_id else None,
                                "valid_from": row.valid_from.isoformat(),
                                "valid_to": row.valid_to.isoformat() if row.valid_to else None,
                                "recorded_at": row.recorded_at.isoformat(),
                                "resolution_method": row.resolution_method.value,
                                "confidence": row.confidence, "review_state": row.review_state.value,
                                "revision": row.revision} for row in self.crosswalks],
                "schedules": [{"fixture_id": str(row.fixture_id), "revision": row.revision,
                               "available_at": row.available_at.isoformat(),
                               "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
                               "status": row.status, "source": row.source} for row in self.schedules]}

    @classmethod
    def from_dict(cls, payload: dict) -> "EntityRegistry":
        if payload["schema_version"] != "1":
            raise ValueError("Unknown entity registry schema")
        registry = cls()
        for row in payload["entities"]:
            kind = EntityType(row["entity_type"])
            if kind == EntityType.FIXTURE:
                entity = Fixture(FixtureId(row["canonical_id"]), CompetitionId(row["competition_id"]),
                                 row["season"], TeamId(row["home_team_id"]), TeamId(row["away_team_id"]))
            else:
                entity = (Competition if kind == EntityType.COMPETITION else Team)(
                    _ID_TYPES[kind](row["canonical_id"]), row["name"])
            registry.register(entity)
        for row in payload["crosswalks"]:
            kind = EntityType(row["entity_type"])
            registry.append_crosswalk(CrosswalkRecord(
                row["provider"], row["provider_entity_id"], row["provider_name"], kind,
                _ID_TYPES[kind](row["canonical_id"]) if row["canonical_id"] else None,
                datetime.fromisoformat(row["valid_from"]),
                datetime.fromisoformat(row["valid_to"]) if row["valid_to"] else None,
                datetime.fromisoformat(row["recorded_at"]), ResolutionMethod(row["resolution_method"]),
                row["confidence"], ReviewState(row["review_state"]), row["revision"]))
        for row in payload["schedules"]:
            registry.append_schedule(FixtureScheduleRevision(
                FixtureId(row["fixture_id"]), row["revision"], datetime.fromisoformat(row["available_at"]),
                datetime.fromisoformat(row["scheduled_at"]) if row["scheduled_at"] else None,
                row["status"], row["source"]))
        return registry
