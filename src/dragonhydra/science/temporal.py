"""Point-in-time contracts for scientific evaluation, independent of storage.

Capture timestamps always describe the actual acquisition. A historical
publication assumption can change reconstructed availability, never those clocks.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import math
import re
from typing import Iterable, Mapping


class TemporalMode(str, Enum):
    STRICT_PIT = "STRICT_PIT"
    RECONSTRUCTED_PIT = "RECONSTRUCTED_PIT"


def aware_utc(value: datetime, field: str = "timestamp") -> datetime:
    """Reject missing timezones; never guess a source's local timezone."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")


@dataclass(frozen=True, slots=True)
class Availability:
    availability_mode: TemporalMode
    available_at: datetime | None
    observed_at: datetime
    retrieved_at: datetime
    ingested_at: datetime
    availability_policy: str
    availability_policy_version: str
    assumption_reason: str
    confidence: float
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "availability_mode", TemporalMode(self.availability_mode))
        for field in ("observed_at", "retrieved_at", "ingested_at"):
            object.__setattr__(self, field, aware_utc(getattr(self, field), field))
        if self.available_at is not None:
            object.__setattr__(self, "available_at", aware_utc(self.available_at, "available_at"))
        if not self.observed_at <= self.retrieved_at <= self.ingested_at:
            raise ValueError("capture chronology must be observed_at <= retrieved_at <= ingested_at")
        for field in ("availability_policy", "availability_policy_version", "assumption_reason", "source"):
            _text(getattr(self, field), field)
        if (isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float))
                or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise ValueError("confidence must be finite and between zero and one")
        if (self.availability_mode is TemporalMode.STRICT_PIT
                and self.available_at is not None and self.available_at < self.ingested_at):
            raise ValueError("STRICT_PIT availability cannot precede genuine capture/ingestion")

    def eligible(self, target_as_of: datetime, mode: TemporalMode) -> bool:
        target = aware_utc(target_as_of, "target_as_of")
        mode = TemporalMode(mode)
        return (self.available_at is not None and self.available_at <= target
                and (mode is TemporalMode.RECONSTRUCTED_PIT
                     or self.availability_mode is TemporalMode.STRICT_PIT))

    def to_dict(self) -> dict:
        return {
            "availability_mode": self.availability_mode.value,
            "available_at": self.available_at.isoformat() if self.available_at is not None else None,
            "observed_at": self.observed_at.isoformat(),
            "retrieved_at": self.retrieved_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "availability_policy": self.availability_policy,
            "availability_policy_version": self.availability_policy_version,
            "assumption_reason": self.assumption_reason,
            "confidence": self.confidence,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: Mapping) -> "Availability":
        fields = dict(value)
        for field in ("available_at", "observed_at", "retrieved_at", "ingested_at"):
            if fields.get(field) is not None:
                fields[field] = datetime.fromisoformat(fields[field])
        return cls(**fields)


def result_final_availability(
    *, event_time: datetime, publication_delay: timedelta,
    observed_at: datetime, retrieved_at: datetime, ingested_at: datetime,
    availability_policy_version: str, assumption_reason: str, confidence: float, source: str,
) -> Availability:
    """Explicit RESULT_FINAL approximation; event_time is the final whistle.

    A delay greater than seven days is outside this small baseline policy and
    requires a separately declared policy. This helper does not infer full time
    from a kickoff, date-only record, or unknown timezone.
    """
    event = aware_utc(event_time, "event_time")
    _text(assumption_reason, "assumption_reason")
    if (not isinstance(publication_delay, timedelta)
            or not timedelta(0) < publication_delay <= timedelta(days=7)):
        raise ValueError("RESULT_FINAL publication_delay must be positive and no more than seven days")
    return Availability(
        TemporalMode.RECONSTRUCTED_PIT, event + publication_delay,
        observed_at, retrieved_at, ingested_at,
        "RESULT_FINAL", availability_policy_version,
        f"{assumption_reason}; final-whistle publication delay={publication_delay.total_seconds():g}s",
        confidence, source,
    )


def proven_publication_availability(
    *, published_at: datetime, timestamp_evidence: str, data_class: str,
    observed_at: datetime, retrieved_at: datetime, ingested_at: datetime,
    availability_policy_version: str, confidence: float, source: str,
) -> Availability:
    """Use an explicitly evidenced historical publication/snapshot timestamp.

    The caller retains the referenced proof. A kickoff alone is not publication
    proof and cannot establish closing-odds availability. This helper preserves
    RECONSTRUCTED_PIT because the system itself acquired the evidence later.
    """
    _text(timestamp_evidence, "timestamp_evidence")
    if data_class not in ("FIXTURE_SCHEDULE", "CLOSING_ODDS", "SOURCE_PUBLICATION"):
        raise ValueError("unsupported publication data class")
    published = aware_utc(published_at, "published_at")
    if published > aware_utc(observed_at, "observed_at"):
        raise ValueError("publication evidence cannot prove a timestamp after observation")
    return Availability(
        TemporalMode.RECONSTRUCTED_PIT, published, observed_at, retrieved_at, ingested_at,
        f"{data_class}_EVIDENCED_TIMESTAMP", availability_policy_version,
        f"Historical timestamp evidence: {timestamp_evidence}", confidence, source,
    )


def unknown_availability(
    *, observed_at: datetime, retrieved_at: datetime, ingested_at: datetime,
    assumption_reason: str, source: str,
) -> Availability:
    """Retain an import with unknown historical availability; exclude all horizons."""
    return Availability(
        TemporalMode.RECONSTRUCTED_PIT, None, observed_at, retrieved_at, ingested_at,
        "UNKNOWN", "1", assumption_reason, 0.0, source,
    )


_NAMED_HORIZONS = {
    "T_MINUS_24H": timedelta(hours=24),
    "T_MINUS_6H": timedelta(hours=6),
    "T_MINUS_1H": timedelta(hours=1),
    "T_MINUS_15M": timedelta(minutes=15),
    "KICKOFF": timedelta(0),
}


@dataclass(frozen=True, slots=True)
class DecisionHorizon:
    name: str
    offset_before_kickoff: timedelta | None = None
    target_at: datetime | None = None

    def __post_init__(self) -> None:
        _text(self.name, "name")
        if (self.offset_before_kickoff is None) == (self.target_at is None):
            raise ValueError("a horizon requires exactly one offset or absolute target")
        if self.offset_before_kickoff is not None:
            if not isinstance(self.offset_before_kickoff, timedelta) or self.offset_before_kickoff < timedelta(0):
                raise ValueError("offset_before_kickoff must be a nonnegative timedelta")
        if self.target_at is not None:
            object.__setattr__(self, "target_at", aware_utc(self.target_at, "target_at"))
        if self.name in _NAMED_HORIZONS and self.offset_before_kickoff != _NAMED_HORIZONS[self.name]:
            raise ValueError("named horizon offset cannot contradict its name")

    @classmethod
    def named(cls, name: str) -> "DecisionHorizon":
        if name not in _NAMED_HORIZONS:
            raise ValueError(f"unknown named decision horizon: {name}")
        return cls(name, offset_before_kickoff=_NAMED_HORIZONS[name])

    @classmethod
    def at(cls, timestamp: datetime) -> "DecisionHorizon":
        return cls("TIMESTAMP", target_at=timestamp)

    def target(self, kickoff: datetime) -> datetime:
        kickoff = aware_utc(kickoff, "kickoff")
        return self.target_at if self.target_at is not None else kickoff - self.offset_before_kickoff

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "offset_before_kickoff_seconds": (self.offset_before_kickoff.total_seconds()
                                               if self.offset_before_kickoff is not None else None),
            "target_at": self.target_at.isoformat() if self.target_at is not None else None,
        }

    @classmethod
    def from_dict(cls, value: Mapping) -> "DecisionHorizon":
        seconds = value["offset_before_kickoff_seconds"]
        return cls(value["name"], timedelta(seconds=seconds) if seconds is not None else None,
                   datetime.fromisoformat(value["target_at"]) if value["target_at"] is not None else None)


@dataclass(frozen=True, slots=True)
class TimedRevision:
    record_id: str
    entity_key: str
    version: int
    availability: Availability
    supersedes_id: str | None = None
    payload_hash: str | None = None

    def __post_init__(self) -> None:
        _text(self.record_id, "record_id")
        _text(self.entity_key, "entity_key")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.availability, Availability):
            raise ValueError("availability must be an Availability contract")
        if self.supersedes_id is not None:
            _text(self.supersedes_id, "supersedes_id")
            if self.supersedes_id == self.record_id:
                raise ValueError("a revision cannot supersede itself")
        if self.payload_hash is not None and (not isinstance(self.payload_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", self.payload_hash) is None):
            raise ValueError("payload_hash must be a lowercase SHA-256 hex digest")

    def to_dict(self) -> dict:
        return {"record_id": self.record_id, "entity_key": self.entity_key, "version": self.version,
                "availability": self.availability.to_dict(), "supersedes_id": self.supersedes_id,
                "payload_hash": self.payload_hash}


def as_of(revisions: Iterable[TimedRevision], target_as_of: datetime,
          mode: TemporalMode) -> tuple[TimedRevision, ...]:
    """Replay one linear revision chain per entity without hiding older knowledge.

    Chains must be complete from version one. Validate all supplied history, then
    select eligible versions. A future or UNKNOWN revision cannot hide a prior
    eligible revision. Results have deterministic entity-key order.
    """
    target = aware_utc(target_as_of, "target_as_of")
    mode = TemporalMode(mode)
    histories: dict[str, list[TimedRevision]] = {}
    seen: set[str] = set()
    for revision in revisions:
        if not isinstance(revision, TimedRevision):
            raise ValueError("all revisions must be TimedRevision contracts")
        if revision.record_id in seen:
            raise ValueError("record_id must be unique")
        seen.add(revision.record_id)
        histories.setdefault(revision.entity_key, []).append(revision)
    selected = []
    for entity_key in sorted(histories):
        history = sorted(histories[entity_key], key=lambda item: item.version)
        previous = None
        eligible = []
        for expected_version, revision in enumerate(history, start=1):
            if revision.version != expected_version:
                raise ValueError("revision chain must have unique consecutive versions from one")
            if revision.supersedes_id != (previous.record_id if previous is not None else None):
                raise ValueError("supersedes_id must name the preceding revision of this entity")
            if previous is not None:
                old, new = previous.availability, revision.availability
                if new.ingested_at < old.ingested_at:
                    raise ValueError("revision ingestion cannot move backwards")
                if old.available_at is not None and new.available_at is not None and new.available_at < old.available_at:
                    raise ValueError("revision availability cannot move backwards")
            if revision.availability.eligible(target, mode):
                eligible.append(revision)
            previous = revision
        if eligible:
            selected.append(eligible[-1])
    return tuple(selected)
