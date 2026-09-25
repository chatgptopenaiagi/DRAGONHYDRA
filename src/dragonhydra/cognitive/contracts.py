"""Closed, immutable cognitive artifacts; conclusions never become evidence.

These contracts describe a bounded project handoff, not an AI execution engine.
Only structured conclusions and short rationale summaries can be serialized.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
import re
import types
from typing import get_args, get_origin, get_type_hints

from dragonhydra.science.temporal import TemporalMode, aware_utc


class ActorRole(str, Enum):
    SYSTEM = "SYSTEM"
    QWEN = "QWEN"
    CODEX = "CODEX"
    HYDRA = "HYDRA"
    MEDUSA = "MEDUSA"
    MATH = "MATH"
    HUMAN = "HUMAN"


class EpistemicState(str, Enum):
    OBSERVATION = "OBSERVATION"
    PREDICTION = "PREDICTION"
    SIMULATION = "SIMULATION"
    SYNTHETIC = "SYNTHETIC"
    HYPOTHESIS = "HYPOTHESIS"
    INTERPRETATION = "INTERPRETATION"
    CRITIQUE = "CRITIQUE"
    RESEARCH_PROPOSAL = "RESEARCH_PROPOSAL"
    FEATURE_PROPOSAL = "FEATURE_PROPOSAL"
    ANOMALY_REPORT = "ANOMALY_REPORT"
    OPERATION = "OPERATION"


class ResultStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    NOT_STARTED = "NOT_STARTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class ActionClass(str, Enum):
    NO_ACTION = "NO_ACTION"
    REQUEST_QWEN_ANALYSIS = "REQUEST_QWEN_ANALYSIS"
    REQUEST_CALCULATION = "REQUEST_CALCULATION"
    REQUEST_SIMULATION = "REQUEST_SIMULATION"
    REQUEST_RESEARCH = "REQUEST_RESEARCH"
    REQUEST_SOURCE_REFRESH = "REQUEST_SOURCE_REFRESH"
    REQUEST_HUMAN_REVIEW = "REQUEST_HUMAN_REVIEW"


class TaskKind(str, Enum):
    ANALYZE_UNCERTAINTY = "ANALYZE_UNCERTAINTY"
    COMPARE_MODELS = "COMPARE_MODELS"
    REVIEW_EVIDENCE = "REVIEW_EVIDENCE"
    REVIEW_ACTIONS = "REVIEW_ACTIONS"


class AgreementState(str, Enum):
    AGREEMENT = "AGREEMENT"
    PARTIAL_AGREEMENT = "PARTIAL_AGREEMENT"
    DISAGREEMENT = "DISAGREEMENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class Outcome(str, Enum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"


_AI_ROLES = frozenset((ActorRole.QWEN, ActorRole.CODEX))
_AI_STATES = frozenset((EpistemicState.HYPOTHESIS, EpistemicState.INTERPRETATION,
                        EpistemicState.CRITIQUE, EpistemicState.RESEARCH_PROPOSAL,
                        EpistemicState.FEATURE_PROPOSAL, EpistemicState.ANOMALY_REPORT))
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_SECRET = re.compile(
    r"(?i)(?:\b(?:password|passwd|pwd|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|authorization|cookie)\s*[:=]\s*\S+|"
    r"\bbearer\s+\S+|\b(?:sk-proj-|ghp_|github_pat_)[A-Za-z0-9_-]+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|://[^/\s:@]+:[^/\s@]+@)"
)


def _safe_text(value: str, name: str) -> None:
    limit = 400 if name in ("summary", "rationale_summary", "question") else 1024
    if not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f"{name}: bounded nonempty single-line text required")
    if _SECRET.search(value):
        raise ValueError(f"{name}: secret-like text rejected")
    if name.endswith("hash") or name == "input_hashes" or name.endswith("_hashes"):
        if not _HASH.fullmatch(value):
            raise ValueError(f"{name}: lowercase SHA-256 required")
    if name.endswith("reason_codes") or name in ("failure_state", "chain_breaks"):
        if not _CODE.fullmatch(value):
            raise ValueError(f"{name}: uppercase reason code required")


def _typed(value, annotation, name: str, *, decode: bool):
    origin, arguments = get_origin(annotation), get_args(annotation)
    if origin is types.UnionType:
        for choice in arguments:
            try:
                return _typed(value, choice, name, decode=decode)
            except (TypeError, ValueError):
                pass
        raise ValueError(f"{name}: wrong optional/union type")
    if annotation is type(None):
        if value is not None:
            raise ValueError(f"{name}: expected null")
        return None
    if origin is tuple:
        if type(value) not in ((tuple, list) if decode else (tuple,)) or len(value) > 256:
            raise ValueError(f"{name}: bounded immutable tuple required")
        return tuple(_typed(item, arguments[0], name, decode=decode) for item in value)
    if annotation is datetime:
        if decode:
            if type(value) is not str or len(value) > 64:
                raise ValueError(f"{name}: ISO timestamp required")
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                raise ValueError(f"{name}: invalid ISO timestamp") from None
        return aware_utc(value, name)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if decode and type(value) is str:
            try:
                value = annotation(value)
            except ValueError:
                raise ValueError(f"{name}: unknown enum value") from None
        if type(value) is not annotation:
            raise ValueError(f"{name}: expected {annotation.__name__}")
        return value
    if isinstance(annotation, type) and issubclass(annotation, Contract):
        if decode:
            return annotation.from_dict(value)
        if type(value) is not annotation:
            raise ValueError(f"{name}: expected {annotation.__name__}")
        return value
    if annotation is float:
        if type(value) not in (float, int):
            raise ValueError(f"{name}: finite number required")
        try:
            converted = float(value)
        except OverflowError:
            raise ValueError(f"{name}: finite number required") from None
        if not math.isfinite(converted):
            raise ValueError(f"{name}: finite number required")
        return converted
    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ValueError(f"{name}: expected {annotation.__name__}")
        if annotation is str:
            _safe_text(value, name)
        return value
    raise ValueError(f"{name}: unsupported contract type")


def _encode(value):
    if isinstance(value, Contract):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return aware_utc(value).isoformat()
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def canonical_hash(value) -> str:
    """Hash canonical JSON; no platform timestamps or runtime paths are added."""
    data = _encode(value)
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("nonfinite JSON number")


class Contract:
    __slots__ = ()

    def __post_init__(self) -> None:
        hints = get_type_hints(type(self))
        for field in fields(self):
            object.__setattr__(self, field.name,
                               _typed(getattr(self, field.name), hints[field.name],
                                      field.name, decode=False))
        metadata = getattr(self, "metadata", None)
        state = getattr(self, "epistemic_state", None)
        if metadata is not None and metadata.actor.role in _AI_ROLES:
            if state is not None and state not in _AI_STATES and state is not EpistemicState.OPERATION:
                raise ValueError("AI conclusions cannot be external evidence")

    def to_dict(self) -> dict:
        return {field.name: _encode(getattr(self, field.name)) for field in fields(self)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)

    def digest(self) -> str:
        return canonical_hash(self)

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict:
            raise ValueError(f"{cls.__name__}: object required")
        known = {field.name for field in fields(cls)}
        if set(value) - known:
            raise ValueError(f"{cls.__name__}: unknown fields rejected")
        hints = get_type_hints(cls)
        decoded = {key: _typed(item, hints[key], key, decode=True) for key, item in value.items()}
        try:
            return cls(**decoded)
        except TypeError:
            raise ValueError(f"{cls.__name__}: missing required fields") from None

    @classmethod
    def from_json(cls, value: str | bytes):
        if type(value) not in (str, bytes) or len(value) > 262144:
            raise ValueError("bounded JSON artifact required")
        try:
            parsed = json.loads(value, object_pairs_hook=_unique_json, parse_constant=_nonfinite)
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
            raise ValueError("invalid cognitive JSON") from None
        return cls.from_dict(parsed)


def _probability(value: float | None, name: str) -> None:
    if value is not None and not 0 <= value <= 1:
        raise ValueError(f"{name}: probability must lie in [0, 1]")


def _distribution(values: tuple[float, ...], *, optional: bool = False) -> None:
    if optional and not values:
        return
    if len(values) != 3 or any(v < 0 or v > 1 for v in values) or not math.isclose(sum(values), 1, abs_tol=1e-9):
        raise ValueError("probabilities require HOME/DRAW/AWAY distribution summing to one")


@dataclass(frozen=True, slots=True, kw_only=True)
class ActorIdentity(Contract):
    actor_id: str
    role: ActorRole
    model_id: str = "NOT_APPLICABLE"
    model_version: str = "UNKNOWN"
    runtime_id: str = "NOT_APPLICABLE"
    runtime_version: str = "UNKNOWN"

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.role is ActorRole.QWEN and (self.model_id == "NOT_APPLICABLE" or self.runtime_id == "NOT_APPLICABLE"):
            raise ValueError("Qwen must identify its model and runtime")


@dataclass(frozen=True, slots=True, kw_only=True)
class Metadata(Contract):
    created_at: datetime
    as_of_at: datetime
    temporal_mode: TemporalMode
    actor: ActorIdentity
    source_refs: tuple[str, ...] = ()
    input_hashes: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    schema_version: str = "1"

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.schema_version != "1":
            raise ValueError("unsupported cognitive schema version")
        if self.as_of_at > self.created_at:
            raise ValueError("as-of cursor cannot be after artifact creation")


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceSummary(Contract):
    evidence_id: str
    source_id: str
    content_hash: str
    available_at: datetime
    observed_at: datetime
    event_at: datetime | None
    epistemic_state: EpistemicState
    validation_ref: str
    provenance_refs: tuple[str, ...]
    numeric_value: float | None = None
    temporal_mode: TemporalMode = TemporalMode.STRICT_PIT
    validation_reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        Contract.__post_init__(self)
        if not self.provenance_refs:
            raise ValueError("evidence requires retained provenance references")
        if self.epistemic_state not in (EpistemicState.OBSERVATION, EpistemicState.PREDICTION,
                                       EpistemicState.SIMULATION, EpistemicState.SYNTHETIC,
                                       EpistemicState.HYPOTHESIS):
            raise ValueError("unsupported evidence-summary epistemic state")
        if self.temporal_mode is TemporalMode.STRICT_PIT and self.available_at < self.observed_at:
            raise ValueError("STRICT_PIT availability cannot precede observation")
        if self.epistemic_state is EpistemicState.OBSERVATION and (
                self.event_at is None or self.event_at > self.observed_at):
            raise ValueError("a future or undated event is not an observed outcome")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceSummary(Contract):
    source_id: str
    status: ResultStatus
    reason_codes: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelSummary(Contract):
    model_id: str
    forecast_hash: str
    epistemic_state: EpistemicState = EpistemicState.PREDICTION
    probabilities: tuple[float, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.epistemic_state not in (EpistemicState.PREDICTION, EpistemicState.SIMULATION, EpistemicState.SYNTHETIC):
            raise ValueError("model forecasts cannot be observations")
        _distribution(self.probabilities, optional=True)


@dataclass(frozen=True, slots=True, kw_only=True)
class UncertaintySummary(Contract):
    uncertainty_id: str
    score: float | None
    reason_codes: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self):
        Contract.__post_init__(self)
        _probability(self.score, "score")


@dataclass(frozen=True, slots=True, kw_only=True)
class StatusSummary(Contract):
    component: str
    status: ResultStatus
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityDescriptor(Contract):
    capability_id: str
    action: ActionClass
    enabled: bool
    requires_medusa: bool = True
    requires_source_policy: bool = True

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.action in (ActionClass.REQUEST_RESEARCH, ActionClass.REQUEST_SOURCE_REFRESH) and (
                not self.requires_medusa or not self.requires_source_policy):
            raise ValueError("acquisition cannot bypass source policy or MEDUSA")


@dataclass(frozen=True, slots=True, kw_only=True)
class Hypothesis(Contract):
    metadata: Metadata
    hypothesis_id: str
    summary: str
    confidence: float | None = None
    epistemic_state: EpistemicState = EpistemicState.HYPOTHESIS

    def __post_init__(self):
        Contract.__post_init__(self)
        _probability(self.confidence, "confidence")
        if self.epistemic_state not in _AI_STATES:
            raise ValueError("cognitive conclusion must preserve a non-evidence type")


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchNeed(Contract):
    metadata: Metadata
    need_id: str
    state_hash: str
    question: str
    hypothesis_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    requested_capability: str
    epistemic_state: EpistemicState = EpistemicState.RESEARCH_PROPOSAL

    def __post_init__(self):
        Contract.__post_init__(self)
        if not self.provenance_refs or self.epistemic_state is not EpistemicState.RESEARCH_PROPOSAL:
            raise ValueError("ResearchNeed requires provenance and RESEARCH_PROPOSAL state")


@dataclass(frozen=True, slots=True, kw_only=True)
class CalculationRequest(Contract):
    metadata: Metadata
    request_id: str
    state_hash: str
    requested_capability: str
    input_hashes: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    epistemic_state: EpistemicState = EpistemicState.RESEARCH_PROPOSAL

    def __post_init__(self):
        Contract.__post_init__(self)
        if not self.input_hashes or self.epistemic_state is not EpistemicState.RESEARCH_PROPOSAL:
            raise ValueError("calculation request requires inputs and non-evidence state")


@dataclass(frozen=True, slots=True, kw_only=True)
class AcquisitionRequest(Contract):
    metadata: Metadata
    request_id: str
    state_hash: str
    research_need_id: str
    requested_capability: str
    source_id: str
    source_policy_ref: str
    provenance_refs: tuple[str, ...]
    acquisition_actor: ActorRole = ActorRole.HYDRA
    validation_actor: ActorRole = ActorRole.MEDUSA
    epistemic_state: EpistemicState = EpistemicState.RESEARCH_PROPOSAL

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.acquisition_actor is not ActorRole.HYDRA or self.validation_actor is not ActorRole.MEDUSA:
            raise ValueError("required acquisition path is HYDRA then MEDUSA")
        if not self.provenance_refs or self.epistemic_state is not EpistemicState.RESEARCH_PROPOSAL:
            raise ValueError("acquisition requires provenance and non-evidence state")


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionProposal(Contract):
    metadata: Metadata
    proposal_id: str
    state_hash: str
    action: ActionClass
    requested_capability: str
    rationale_summary: str
    research_need_id: str | None = None
    epistemic_state: EpistemicState = EpistemicState.RESEARCH_PROPOSAL

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.epistemic_state not in _AI_STATES:
            raise ValueError("an action proposal is not evidence")


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionDecision(Contract):
    metadata: Metadata
    proposal_id: str
    state_hash: str
    action: ActionClass
    requested_capability: str
    permitted: bool
    result_status: ResultStatus
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.metadata.actor.role in _AI_ROLES:
            raise ValueError("AI proposal cannot authorize itself")
        if self.permitted and self.result_status is not ResultStatus.COMPLETE:
            raise ValueError("permission requires a complete deterministic decision")
        if not self.permitted and self.result_status is ResultStatus.COMPLETE:
            raise ValueError("denied action cannot claim complete permission")


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionResult(Contract):
    metadata: Metadata
    proposal_id: str
    state_hash: str
    action: ActionClass
    result_status: ResultStatus
    provenance_refs: tuple[str, ...] = ()
    failure_state: str | None = None
    epistemic_state: EpistemicState = EpistemicState.OPERATION

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.epistemic_state is not EpistemicState.OPERATION:
            raise ValueError("an action result records an operation, not external evidence")
        _failure(self.result_status, self.failure_state)


def _failure(status: ResultStatus, failure_state: str | None) -> None:
    if status in (ResultStatus.BLOCKED, ResultStatus.FAILED) and failure_state is None:
        raise ValueError("failed/blocked operation requires a failure code")
    if status is ResultStatus.COMPLETE and failure_state is not None:
        raise ValueError("complete operation cannot carry a failure")


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemStateSnapshot(Contract):
    metadata: Metadata
    fixture_id: str | None = None
    evidence: tuple[EvidenceSummary, ...] = ()
    sources: tuple[SourceSummary, ...] = ()
    models: tuple[ModelSummary, ...] = ()
    uncertainties: tuple[UncertaintySummary, ...] = ()
    research_needs: tuple[ResearchNeed, ...] = ()
    recent_actions: tuple[ActionResult, ...] = ()
    capabilities: tuple[CapabilityDescriptor, ...] = ()
    health: tuple[StatusSummary, ...] = ()
    stage_status: tuple[StatusSummary, ...] = ()
    goals: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    chain_breaks: tuple[str, ...] = ()

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.metadata.actor.role is not ActorRole.SYSTEM:
            raise ValueError("only the controlled system builder creates snapshots")
        for item in self.evidence:
            if item.available_at > self.metadata.as_of_at or item.observed_at > self.metadata.created_at:
                raise ValueError("evidence is not available at the selected cursor")
            if self.metadata.temporal_mode is TemporalMode.STRICT_PIT and item.temporal_mode is not TemporalMode.STRICT_PIT:
                raise ValueError("reconstructed evidence is ineligible for STRICT_PIT")
            if item.epistemic_state is EpistemicState.OBSERVATION and item.event_at > self.metadata.as_of_at:
                raise ValueError("future events cannot be observations")
        for collection, key in ((self.evidence, "evidence_id"), (self.sources, "source_id"),
                                (self.models, "model_id"), (self.uncertainties, "uncertainty_id"),
                                (self.capabilities, "capability_id")):
            if len({getattr(item, key) for item in collection}) != len(collection):
                raise ValueError(f"duplicate {key}")

    @property
    def state_hash(self) -> str:
        return self.digest()


@dataclass(frozen=True, slots=True, kw_only=True)
class CognitiveRequest(Contract):
    metadata: Metadata
    request_id: str
    state_hash: str
    task: TaskKind
    allowed_actions: tuple[ActionClass, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CognitiveResponse(Contract):
    metadata: Metadata
    request_id: str
    state_hash: str
    input_hash: str
    result_status: ResultStatus
    conclusions: tuple[Hypothesis, ...] = ()
    failure_state: str | None = None
    epistemic_state: EpistemicState = EpistemicState.INTERPRETATION

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.metadata.actor.role not in _AI_ROLES or self.epistemic_state not in _AI_STATES:
            raise ValueError("cognitive response requires an identified AI and non-evidence state")
        _failure(self.result_status, self.failure_state)
        if self.result_status in (ResultStatus.BLOCKED, ResultStatus.FAILED) and self.conclusions:
            raise ValueError("failed analysis cannot invent conclusions")
        for item in self.conclusions:
            if item.metadata.actor != self.metadata.actor or item.metadata.as_of_at != self.metadata.as_of_at or item.metadata.temporal_mode != self.metadata.temporal_mode:
                raise ValueError("conclusion identity and temporal cursor must match response")

    @property
    def output_hash(self) -> str:
        return self.digest()


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceDelta(Contract):
    metadata: Metadata
    before_state_hash: str
    after_state_hash: str
    added: tuple[EvidenceSummary, ...] = ()
    removed_ids: tuple[str, ...] = ()
    changed_ids: tuple[str, ...] = ()

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.metadata.actor.role is not ActorRole.SYSTEM:
            raise ValueError("only the controlled system builder creates evidence deltas")
        for item in self.added:
            if item.available_at > self.metadata.as_of_at or item.observed_at > self.metadata.created_at:
                raise ValueError("delta evidence is not available at the selected cursor")
            if self.metadata.temporal_mode is TemporalMode.STRICT_PIT and item.temporal_mode is not TemporalMode.STRICT_PIT:
                raise ValueError("reconstructed delta evidence is ineligible for STRICT_PIT")
            if item.epistemic_state is EpistemicState.OBSERVATION and item.event_at > self.metadata.as_of_at:
                raise ValueError("future delta events cannot be observations")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelDelta(Contract):
    metadata: Metadata
    model_id: str
    before_forecast_hash: str | None
    after_forecast_hash: str | None
    before_probabilities: tuple[float, ...] = ()
    after_probabilities: tuple[float, ...] = ()

    def __post_init__(self):
        Contract.__post_init__(self)
        _distribution(self.before_probabilities, optional=True)
        _distribution(self.after_probabilities, optional=True)


@dataclass(frozen=True, slots=True, kw_only=True)
class UncertaintyDelta(Contract):
    metadata: Metadata
    uncertainty_id: str
    before: float | None
    after: float | None

    def __post_init__(self):
        Contract.__post_init__(self)
        _probability(self.before, "before")
        _probability(self.after, "after")


@dataclass(frozen=True, slots=True, kw_only=True)
class StateDelta(Contract):
    metadata: Metadata
    before_state_hash: str
    after_state_hash: str
    evidence: EvidenceDelta
    models: tuple[ModelDelta, ...] = ()
    uncertainties: tuple[UncertaintyDelta, ...] = ()
    changed_sections: tuple[str, ...] = ()

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.metadata.actor.role is not ActorRole.SYSTEM:
            raise ValueError("only the controlled system builder creates state deltas")
        if (self.evidence.before_state_hash, self.evidence.after_state_hash) != (self.before_state_hash, self.after_state_hash):
            raise ValueError("delta input hashes must match")
        for item in (self.evidence, *self.models, *self.uncertainties):
            if item.metadata.actor.role is not ActorRole.SYSTEM:
                raise ValueError("state delta components require the controlled system builder")
            if (item.metadata.created_at, item.metadata.as_of_at, item.metadata.temporal_mode) != (
                    self.metadata.created_at, self.metadata.as_of_at, self.metadata.temporal_mode):
                raise ValueError("delta component clocks and temporal mode must match")


@dataclass(frozen=True, slots=True, kw_only=True)
class Position(Contract):
    actor: ActorIdentity
    claim_id: str
    summary: str
    epistemic_state: EpistemicState
    provenance_refs: tuple[str, ...] = ()
    request_id: str | None = None
    input_hash: str | None = None
    state_hash: str | None = None
    as_of_at: datetime | None = None
    temporal_mode: TemporalMode | None = None
    task: TaskKind | None = None
    result_status: ResultStatus = ResultStatus.UNKNOWN

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.actor.role in _AI_ROLES and self.epistemic_state not in _AI_STATES:
            raise ValueError("AI position cannot become evidence")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReconciliationReport(Contract):
    metadata: Metadata
    state_hash: str
    agreement: AgreementState
    positions: tuple[Position, ...]
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.agreement in (AgreementState.AGREEMENT, AgreementState.PARTIAL_AGREEMENT, AgreementState.DISAGREEMENT):
            if len(self.positions) < 2:
                raise ValueError("comparison requires at least two preserved positions")


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservedOutcome(Contract):
    fixture_id: str
    outcome: Outcome
    evidence: EvidenceSummary

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.evidence.epistemic_state is not EpistemicState.OBSERVATION:
            raise ValueError("accuracy needs a validated observed outcome")


@dataclass(frozen=True, slots=True, kw_only=True)
class CalibrationBin(Contract):
    mean_probability: float
    observed_count: int
    sample_count: int

    def __post_init__(self):
        Contract.__post_init__(self)
        _probability(self.mean_probability, "mean_probability")
        if not 0 <= self.observed_count <= self.sample_count or self.sample_count < 1:
            raise ValueError("calibration bin requires bounded counts and a nonempty sample")


@dataclass(frozen=True, slots=True, kw_only=True)
class CalibrationMeasurement(Contract):
    metadata: Metadata
    model_id: str
    evaluation_ref: str
    protocol_ref: str
    outcome_class: Outcome
    observed_outcome_refs: tuple[str, ...]
    bins: tuple[CalibrationBin, ...]

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.metadata.actor.role in _AI_ROLES:
            raise ValueError("calibration is a measured system result")
        if (not self.bins or len(self.observed_outcome_refs) < 2
                or sum(item.sample_count for item in self.bins) != len(self.observed_outcome_refs)
                or len(set(self.observed_outcome_refs)) != len(self.observed_outcome_refs)):
            raise ValueError("calibration requires a traced multi-outcome cohort matching bin counts")

    @property
    def expected_calibration_error(self) -> float:
        """Binned one-vs-rest ECE; no statistical significance is inferred."""
        return sum(abs(item.mean_probability - item.observed_count / item.sample_count) * item.sample_count
                   for item in self.bins) / len(self.observed_outcome_refs)


@dataclass(frozen=True, slots=True, kw_only=True)
class LearningFeedback(Contract):
    metadata: Metadata
    feedback_id: str
    before_state_hash: str
    after_state_hash: str
    action_refs: tuple[str, ...]
    new_evidence_refs: tuple[str, ...]
    fixture_id: str | None = None
    prediction_before_ref: str | None = None
    prediction_after_ref: str | None = None
    prediction_before_at: datetime | None = None
    prediction_after_at: datetime | None = None
    prediction_before: tuple[float, ...] = ()
    prediction_after: tuple[float, ...] = ()
    actual_outcome: ObservedOutcome | None = None
    model_error_before: float | None = None
    model_error_after: float | None = None
    accuracy_gain: float | None = None
    prediction_quality_improved: bool | None = None
    uncertainty_before: float | None = None
    uncertainty_after: float | None = None
    cost: float | None = None
    latency_ms: float | None = None
    source_useful: bool | None = None
    qwen_proposal_useful: bool | None = None
    codex_proposal_useful: bool | None = None
    both_wrong: bool | None = None
    calibration_before: CalibrationMeasurement | None = None
    calibration_after: CalibrationMeasurement | None = None
    calibration_gain: float | None = None
    metric: str = "MULTICLASS_BRIER"
    epistemic_state: EpistemicState = EpistemicState.OPERATION

    def __post_init__(self):
        Contract.__post_init__(self)
        if self.metadata.actor.role in _AI_ROLES or self.epistemic_state is not EpistemicState.OPERATION:
            raise ValueError("feedback is a measured system operation")
        if self.metric != "MULTICLASS_BRIER":
            raise ValueError("foundation feedback supports only explicit multiclass Brier scoring")
        _distribution(self.prediction_before, optional=True)
        _distribution(self.prediction_after, optional=True)
        for name in ("uncertainty_before", "uncertainty_after"):
            _probability(getattr(self, name), name)
        for name in ("model_error_before", "model_error_after", "cost", "latency_ms"):
            if getattr(self, name) is not None and getattr(self, name) < 0:
                raise ValueError(f"{name}: nonnegative measurement required")
        measured = (self.model_error_before, self.model_error_after, self.accuracy_gain,
                    self.prediction_quality_improved, self.both_wrong)
        if any(item is not None for item in measured):
            if self.actual_outcome is None or not self.prediction_before or not self.prediction_after:
                raise ValueError("accuracy claim requires observed outcome and both frozen forecasts")
            if (self.fixture_id is None or self.prediction_before_ref is None
                    or self.prediction_after_ref is None or self.prediction_before_at is None
                    or self.prediction_after_at is None):
                raise ValueError("accuracy claim requires fixture, immutable forecast references and clocks")
            if self.fixture_id != self.actual_outcome.fixture_id:
                raise ValueError("forecast and observed outcome fixture must match")
            if not self.prediction_before_at <= self.prediction_after_at < self.actual_outcome.evidence.event_at:
                raise ValueError("scored forecasts must be frozen in order before the outcome event")
        if self.actual_outcome is not None:
            evidence = self.actual_outcome.evidence
            if evidence.available_at > self.metadata.as_of_at or evidence.event_at > self.metadata.as_of_at:
                raise ValueError("outcome is not known at feedback cursor")
            if self.metadata.temporal_mode is TemporalMode.STRICT_PIT and evidence.temporal_mode is not TemporalMode.STRICT_PIT:
                raise ValueError("reconstructed outcome cannot silently become STRICT_PIT")
        if self.actual_outcome is not None and self.prediction_before and self.prediction_after:
            selected = tuple(Outcome).index(self.actual_outcome.outcome)
            errors = tuple(sum((p - int(i == selected)) ** 2 for i, p in enumerate(values))
                           for values in (self.prediction_before, self.prediction_after))
            for value, expected in zip((self.model_error_before, self.model_error_after), errors):
                if value is not None and not math.isclose(value, expected, abs_tol=1e-9):
                    raise ValueError("reported model error differs from measured Brier score")
            gain = errors[0] - errors[1]
            if self.accuracy_gain is not None and not math.isclose(self.accuracy_gain, gain, abs_tol=1e-9):
                raise ValueError("accuracy gain differs from measured score improvement")
            if self.prediction_quality_improved is not None and self.prediction_quality_improved != (gain > 1e-9):
                raise ValueError("quality improvement claim differs from measured score")
            if self.both_wrong is not None:
                if any(values.count(max(values)) != 1 for values in (self.prediction_before, self.prediction_after)):
                    raise ValueError("both_wrong is unknown for tied highest-probability outcomes")
                expected_wrong = all(values.index(max(values)) != selected
                                     for values in (self.prediction_before, self.prediction_after))
                if self.both_wrong != expected_wrong:
                    raise ValueError("both_wrong differs from highest-probability outcomes")
        if any(item is not None for item in (self.source_useful, self.qwen_proposal_useful, self.codex_proposal_useful)):
            if not self.action_refs or not self.new_evidence_refs:
                raise ValueError("usefulness attribution requires action and new evidence references")
        if any(item is True for item in (self.source_useful, self.qwen_proposal_useful, self.codex_proposal_useful)):
            uncertainty_reduced = (self.uncertainty_before is not None and self.uncertainty_after is not None
                                   and self.uncertainty_after < self.uncertainty_before)
            if not uncertainty_reduced and not (self.accuracy_gain is not None and self.accuracy_gain > 0):
                raise ValueError("usefulness claim requires measured uncertainty or score improvement")
        if self.calibration_gain is not None:
            before, after = self.calibration_before, self.calibration_after
            if before is None or after is None:
                raise ValueError("calibration improvement requires both cohort measurements")
            if (before.evaluation_ref, before.protocol_ref, before.outcome_class, before.observed_outcome_refs) != (
                    after.evaluation_ref, after.protocol_ref, after.outcome_class, after.observed_outcome_refs):
                raise ValueError("calibration comparison requires identical evaluation cohort and protocol")
            if (sum(item.sample_count for item in before.bins), sum(item.observed_count for item in before.bins)) != (
                    sum(item.sample_count for item in after.bins), sum(item.observed_count for item in after.bins)):
                raise ValueError("calibration comparison cannot change the cohort's observed outcome totals")
            if not math.isclose(self.calibration_gain,
                                before.expected_calibration_error - after.expected_calibration_error, abs_tol=1e-9):
                raise ValueError("calibration improvement differs from measured cohort ECE")
        for measurement in (self.calibration_before, self.calibration_after):
            if measurement is not None and (measurement.metadata.as_of_at > self.metadata.as_of_at
                                           or measurement.metadata.temporal_mode != self.metadata.temporal_mode):
                raise ValueError("calibration measurement must preserve feedback cursor and temporal mode")


@dataclass(frozen=True, slots=True, kw_only=True)
class CognitiveCycleReceipt(Contract):
    metadata: Metadata
    cycle_id: str
    state_hash: str
    request_hashes: tuple[str, ...] = ()
    response_hashes: tuple[str, ...] = ()
    action_hashes: tuple[str, ...] = ()
    result_status: ResultStatus = ResultStatus.COMPLETE
    failure_state: str | None = None

    def __post_init__(self):
        Contract.__post_init__(self)
        _failure(self.result_status, self.failure_state)
