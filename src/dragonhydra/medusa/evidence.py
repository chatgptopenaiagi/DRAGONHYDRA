"""Immutable, in-memory evidence contracts with availability-safe replay.

This is a prototype, not a complete Medusa implementation. ``event_at`` is when
the assertion concerns reality (possibly a future fixture). ``available_at`` is
the first *proven* time this system could use this exact revision. Observation
and update timestamps cannot establish earlier availability by themselves.
``target_as_of_at`` belongs to an evaluation request, never to mutable evidence.
Expiry uses a half-open validity interval: available_at <= T < expires_at.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")


def _ids(values: tuple[str, ...], name: str, *, required: bool = False) -> None:
    if not isinstance(values, tuple) or (required and not values):
        raise ValueError(f"{name} must be an immutable {'non-empty ' if required else ''}tuple")
    for value in values:
        _text(value, name)
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")


class EvidenceStatus(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    MISSING = "MISSING"
    SUSPICIOUS = "SUSPICIOUS"


class ClaimKind(StrEnum):
    EXPECTED = "EXPECTED"
    CONFIRMED = "CONFIRMED"
    OBSERVED = "OBSERVED"


class AvailabilityBoundary(StrEnum):
    AT_OR_BEFORE = "AT_OR_BEFORE"
    STRICTLY_BEFORE = "STRICTLY_BEFORE"


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    source_id: str
    name: str

    def __post_init__(self) -> None:
        _text(self.source_id, "source_id")
        _text(self.name, "source name")


@dataclass(frozen=True, slots=True)
class EntityIdentity:
    entity_type: str
    entity_id: str

    def __post_init__(self) -> None:
        _text(self.entity_type, "entity_type")
        _text(self.entity_id, "entity_id")


@dataclass(frozen=True, slots=True)
class TemporalEvidence:
    event_at: datetime
    observed_at: datetime
    available_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    availability_proof: str

    def __post_init__(self) -> None:
        for name in ("event_at", "observed_at", "available_at", "updated_at"):
            _aware(getattr(self, name), name)
        _text(self.availability_proof, "availability_proof")
        if self.available_at < max(self.observed_at, self.updated_at):
            raise ValueError("available_at cannot precede observation or revision update")
        if self.expires_at is not None:
            _aware(self.expires_at, "expires_at")
            if self.expires_at <= self.available_at:
                raise ValueError("expires_at must be later than available_at")


@dataclass(frozen=True, slots=True)
class EvidenceConfidence:
    score: float
    rationale: str

    def __post_init__(self) -> None:
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("confidence must be numeric")
        if not isfinite(self.score) or not 0 <= self.score <= 1:
            raise ValueError("confidence must be finite and within [0, 1]")
        _text(self.rationale, "confidence rationale")


@dataclass(frozen=True, slots=True)
class HydraEvidencePacket:
    packet_id: str
    source: SourceIdentity
    entity: EntityIdentity
    predicate: str
    value: str | int | float | bool | None
    claim_kind: ClaimKind
    temporal: TemporalEvidence
    confidence: EvidenceConfidence
    provenance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.packet_id, "packet_id")
        _text(self.predicate, "predicate")
        for name, expected in (("source", SourceIdentity), ("entity", EntityIdentity),
                               ("claim_kind", ClaimKind), ("temporal", TemporalEvidence),
                               ("confidence", EvidenceConfidence)):
            if not isinstance(getattr(self, name), expected):
                raise ValueError(f"{name} must be {expected.__name__}")
        if self.value is not None and type(self.value) not in (str, int, float, bool):
            raise ValueError("prototype values must be immutable JSON scalars")
        if isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("numeric evidence must be finite")
        _ids(self.provenance_ids, "provenance_ids", required=True)


@dataclass(frozen=True, slots=True)
class MedusaEvidenceVersion:
    version_id: str
    packet: HydraEvidencePacket
    validation_reason_codes: tuple[str, ...]
    status: EvidenceStatus = EvidenceStatus.KNOWN

    def __post_init__(self) -> None:
        _text(self.version_id, "version_id")
        if not isinstance(self.packet, HydraEvidencePacket):
            raise ValueError("packet must be HydraEvidencePacket")
        _ids(self.validation_reason_codes, "validation_reason_codes", required=True)
        if not isinstance(self.status, EvidenceStatus) or self.status not in (
            EvidenceStatus.KNOWN, EvidenceStatus.UNKNOWN, EvidenceStatus.SUSPICIOUS,
        ):
            raise ValueError("version status must be KNOWN, UNKNOWN or SUSPICIOUS; others are contextual")


@dataclass(frozen=True, slots=True)
class EvidenceSupersession:
    previous_version_id: str
    replacement_version_id: str
    reason: str

    def __post_init__(self) -> None:
        _text(self.previous_version_id, "previous_version_id")
        _text(self.replacement_version_id, "replacement_version_id")
        _text(self.reason, "supersession reason")
        if self.previous_version_id == self.replacement_version_id:
            raise ValueError("a version cannot supersede itself")


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    conflict_id: str
    left_version_id: str
    right_version_id: str
    available_at: datetime
    availability_proof: str
    reason: str

    def __post_init__(self) -> None:
        for name in ("conflict_id", "left_version_id", "right_version_id", "availability_proof", "reason"):
            _text(getattr(self, name), name)
        _aware(self.available_at, "conflict available_at")
        if self.left_version_id == self.right_version_id:
            raise ValueError("a conflict requires two distinct versions")


@dataclass(frozen=True, slots=True)
class AsOfRequest:
    """Evaluation context, with an optional stricter feature availability cutoff.

    Generic evidence permits availability at T. Score-derived kickoff features
    can require STRICTLY_BEFORE. Expiry is still evaluated at T in either mode.
    """

    entity: EntityIdentity
    predicate: str
    target_as_of_at: datetime
    source_id: str | None = None
    availability_boundary: AvailabilityBoundary = AvailabilityBoundary.AT_OR_BEFORE

    def __post_init__(self) -> None:
        if not isinstance(self.entity, EntityIdentity):
            raise ValueError("entity must be EntityIdentity")
        _text(self.predicate, "predicate")
        _aware(self.target_as_of_at, "target_as_of_at")
        if not isinstance(self.availability_boundary, AvailabilityBoundary):
            raise ValueError("availability_boundary must be AvailabilityBoundary")
        if self.source_id is not None:
            _text(self.source_id, "source_id")

    def permits_availability(self, available_at: datetime) -> bool:
        _aware(available_at, "available_at")
        if self.availability_boundary == AvailabilityBoundary.STRICTLY_BEFORE:
            return available_at < self.target_as_of_at
        return available_at <= self.target_as_of_at


@dataclass(frozen=True, slots=True)
class AsOfSelection:
    request: AsOfRequest
    status: EvidenceStatus
    versions: tuple[MedusaEvidenceVersion, ...]
    reason_codes: tuple[str, ...]
    rejected_version_ids: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return self.status == EvidenceStatus.KNOWN


@dataclass(frozen=True, slots=True)
class EvidenceLedger:
    """Small immutable ledger for replay tests, not a persistence implementation.

    Supersession is scoped to one source/entity/predicate. Other sources keep
    their independent claims for comparison. Expired replacements never revive
    superseded evidence. Conflicting outputs remain visible but unusable.
    """

    versions: tuple[MedusaEvidenceVersion, ...]
    supersessions: tuple[EvidenceSupersession, ...] = ()
    conflicts: tuple[EvidenceConflict, ...] = ()

    def __post_init__(self) -> None:
        for name, expected in (("versions", MedusaEvidenceVersion),
                               ("supersessions", EvidenceSupersession),
                               ("conflicts", EvidenceConflict)):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(item, expected) for item in values):
                raise ValueError(f"{name} must be an immutable tuple of {expected.__name__}")
        by_id = {v.version_id: v for v in self.versions}
        if len(by_id) != len(self.versions):
            raise ValueError("version IDs must be unique")
        replaced, replacements = set(), set()
        for link in self.supersessions:
            old, new = self._pair(by_id, link.previous_version_id, link.replacement_version_id)
            if old.packet.source.source_id != new.packet.source.source_id:
                raise ValueError("supersession cannot cross sources")
            if new.packet.temporal.available_at <= old.packet.temporal.available_at:
                raise ValueError("replacement availability must advance; cycles are forbidden")
            if old.version_id in replaced or new.version_id in replacements:
                raise ValueError("supersession chains cannot branch or merge")
            replaced.add(old.version_id)
            replacements.add(new.version_id)
        conflict_ids = set()
        for conflict in self.conflicts:
            if conflict.conflict_id in conflict_ids:
                raise ValueError("conflict IDs must be unique")
            conflict_ids.add(conflict.conflict_id)
            left, right = self._pair(by_id, conflict.left_version_id, conflict.right_version_id)
            if conflict.available_at < max(left.packet.temporal.available_at, right.packet.temporal.available_at):
                raise ValueError("conflict cannot be known before both versions are available")

    @staticmethod
    def _pair(by_id: dict[str, MedusaEvidenceVersion], left_id: str, right_id: str
              ) -> tuple[MedusaEvidenceVersion, MedusaEvidenceVersion]:
        if left_id not in by_id or right_id not in by_id:
            raise ValueError("linked version does not exist")
        left, right = by_id[left_id], by_id[right_id]
        if left.packet.entity != right.packet.entity or left.packet.predicate != right.packet.predicate:
            raise ValueError("linked versions must concern the same entity and predicate")
        return left, right

    def select(self, request: AsOfRequest) -> AsOfSelection:
        if not isinstance(request, AsOfRequest):
            raise ValueError("request must be AsOfRequest")
        target = request.target_as_of_at
        matching = tuple(v for v in self.versions if v.packet.entity == request.entity
                         and v.packet.predicate == request.predicate
                         and (request.source_id is None or v.packet.source.source_id == request.source_id))
        available = {v.version_id: v for v in matching
                     if request.permits_availability(v.packet.temporal.available_at)}
        superseded = {link.previous_version_id for link in self.supersessions
                      if link.replacement_version_id in available}
        active = tuple(v for v in available.values() if v.version_id not in superseded)
        current = tuple(v for v in active if v.packet.temporal.expires_at is None
                        or target < v.packet.temporal.expires_at)
        selected_ids = {v.version_id for v in current}
        rejected = tuple(v.version_id for v in matching if v.version_id not in selected_ids)
        reasons = []
        if any(v.packet.temporal.available_at > target for v in matching):
            reasons.append("FUTURE_INFORMATION_REJECTED")
        if request.availability_boundary == AvailabilityBoundary.STRICTLY_BEFORE and any(
            v.packet.temporal.available_at == target for v in matching
        ):
            reasons.append("EXACT_TARGET_AVAILABILITY_REJECTED")
        if superseded:
            reasons.append("SUPERSEDED_VERSIONS_RETAINED_FOR_REPLAY")
        if len(current) != len(active):
            reasons.append("EVIDENCE_EXPIRED")
        if not current:
            status = EvidenceStatus.STALE if active else EvidenceStatus.MISSING
            reasons.append("NO_USABLE_EVIDENCE")
        else:
            explicit_conflict = any(request.permits_availability(c.available_at)
                                    and c.left_version_id in selected_ids
                                    and c.right_version_id in selected_ids for c in self.conflicts)
            # Comparison is deliberately conservative; no source is silently authoritative.
            claims = {(type(v.packet.value), v.packet.value, v.packet.claim_kind) for v in current}
            if explicit_conflict or len(claims) > 1:
                status = EvidenceStatus.CONFLICTING
                reasons.append("ACTIVE_EVIDENCE_CONFLICT")
            elif any(v.status == EvidenceStatus.SUSPICIOUS for v in current):
                status = EvidenceStatus.SUSPICIOUS
                reasons.append("VALIDATION_SUSPICION")
            elif any(v.status == EvidenceStatus.UNKNOWN for v in current):
                status = EvidenceStatus.UNKNOWN
                reasons.append("UNRESOLVED_EVIDENCE")
            else:
                status = EvidenceStatus.KNOWN
                reasons.append("AVAILABLE_STRICTLY_BEFORE_TARGET"
                               if request.availability_boundary == AvailabilityBoundary.STRICTLY_BEFORE
                               else "AVAILABLE_AT_OR_BEFORE_TARGET")
        return AsOfSelection(request, status, current, tuple(reasons), rejected)
