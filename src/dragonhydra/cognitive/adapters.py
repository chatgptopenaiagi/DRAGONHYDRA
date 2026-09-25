"""Local-first Qwen boundary: deterministic mock and explicitly blocked live path.

No network, subprocess, model loading, SQL, filesystem or agent tools are exposed
by an adapter. A real runtime requires a separately reviewed implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

from . import contracts as c


def request_input_hash(snapshot, request: c.CognitiveRequest) -> str:
    """Bind the complete bounded task envelope to exactly one state artifact."""
    return c.canonical_hash({"snapshot": snapshot.to_dict(), "request": request.to_dict()})


@dataclass(frozen=True, slots=True)
class AdapterLimits:
    timeout_seconds: float = 2.0
    max_context_bytes: int = 65_536
    max_output_bytes: int = 8_192

    def __post_init__(self):
        if (isinstance(self.timeout_seconds, bool) or
                not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 30):
            raise ValueError("INVALID_ADAPTER_TIMEOUT")
        if type(self.max_context_bytes) is not int or not 1024 <= self.max_context_bytes <= 131_072:
            raise ValueError("INVALID_CONTEXT_BOUND")
        if type(self.max_output_bytes) is not int or not 4096 <= self.max_output_bytes <= 16_384:
            raise ValueError("INVALID_OUTPUT_BOUND")


class QwenAdapter(Protocol):
    limits: AdapterLimits

    def analyze(self, snapshot: c.SystemStateSnapshot, request: c.CognitiveRequest) -> c.CognitiveResponse:
        """Return bounded conclusions or a typed operational failure."""
        ...


class _BoundedAdapter:
    def __init__(self, limits: AdapterLimits | None = None):
        self.limits = limits or AdapterLimits()

    def _metadata(self, snapshot, request, actor, reasons):
        return c.Metadata(
            created_at=request.metadata.created_at,
            as_of_at=request.metadata.as_of_at,
            temporal_mode=request.metadata.temporal_mode,
            actor=actor,
            source_refs=request.metadata.source_refs[:16],
            input_hashes=(snapshot.state_hash, request.digest()),
            reason_codes=tuple(reasons),
        )

    def _failure(self, snapshot, request, actor, reason):
        # Hash references retain provenance without copying potentially lengthy
        # input references into a bounded operational failure.
        metadata = c.Metadata(
            created_at=request.metadata.created_at, as_of_at=request.metadata.as_of_at,
            temporal_mode=request.metadata.temporal_mode, actor=actor,
            input_hashes=(snapshot.state_hash, request.digest()), reason_codes=(reason,),
        )
        return c.CognitiveResponse(
            metadata=metadata,
            request_id=request.request_id, state_hash=snapshot.state_hash,
            input_hash=request_input_hash(snapshot, request), result_status=c.ResultStatus.BLOCKED,
            conclusions=(), failure_state=reason,
        )

    def _check(self, snapshot, request):
        # Reparse trusted contract types at the process-facing boundary.
        if type(snapshot) is not c.SystemStateSnapshot or type(request) is not c.CognitiveRequest:
            raise ValueError("TYPED_COGNITIVE_INPUT_REQUIRED")
        c.SystemStateSnapshot.from_dict(snapshot.to_dict())
        c.CognitiveRequest.from_dict(request.to_dict())
        if request.state_hash != snapshot.state_hash:
            return "STATE_HASH_MISMATCH"
        if (request.metadata.as_of_at != snapshot.metadata.as_of_at or
                request.metadata.temporal_mode != snapshot.metadata.temporal_mode):
            return "TEMPORAL_CONTEXT_MISMATCH"
        if len(snapshot.to_json().encode("utf-8")) + len(request.to_json().encode("utf-8")) > self.limits.max_context_bytes:
            return "CONTEXT_LIMIT_EXCEEDED"
        permitted = {item.action for item in snapshot.capabilities if item.enabled}
        if c.ActionClass.REQUEST_QWEN_ANALYSIS not in permitted:
            return "QWEN_ANALYSIS_CAPABILITY_DISABLED"
        if not set(request.allowed_actions).issubset(permitted | {c.ActionClass.NO_ACTION}):
            return "REQUEST_CAPABILITY_NOT_ALLOWED"
        return None


class MockQwenAdapter(_BoundedAdapter):
    """Deterministic contract test only; never represented as Qwen inference."""

    status = "MOCK_ONLY"
    actor = c.ActorIdentity(
        actor_id="qwen-contract-mock", role=c.ActorRole.QWEN,
        model_id="deterministic-mock-not-qwen", model_version="1",
        runtime_id="stdlib-mock", runtime_version="1",
    )

    def analyze(self, snapshot: c.SystemStateSnapshot, request: c.CognitiveRequest) -> c.CognitiveResponse:
        reason = self._check(snapshot, request)
        if reason:
            return self._failure(snapshot, request, self.actor, reason)
        metadata = self._metadata(snapshot, request, self.actor, ("MOCK_ONLY", "NOT_LIVE_INFERENCE"))
        hypothesis = c.Hypothesis(
            metadata=metadata, hypothesis_id="mock-" + request.digest()[:24],
            summary="Evidence sufficiency may require review before a revised forecast.",
            confidence=None, epistemic_state=c.EpistemicState.HYPOTHESIS,
        )
        response = c.CognitiveResponse(
            metadata=metadata, request_id=request.request_id, state_hash=snapshot.state_hash,
            input_hash=request_input_hash(snapshot, request), result_status=c.ResultStatus.COMPLETE,
            conclusions=(hypothesis,), epistemic_state=c.EpistemicState.INTERPRETATION,
        )
        if len(response.to_json().encode("utf-8")) > self.limits.max_output_bytes:
            return self._failure(snapshot, request, self.actor, "OUTPUT_LIMIT_EXCEEDED")
        return response


class UnavailableQwenAdapter(_BoundedAdapter):
    """Honest live status when no approved working runtime has been verified."""

    status = "BLOCKED"
    actor = c.ActorIdentity(
        actor_id="qwen-unavailable", role=c.ActorRole.QWEN,
        model_id="UNKNOWN", model_version="UNKNOWN",
        runtime_id="UNAVAILABLE", runtime_version="UNKNOWN",
    )

    def analyze(self, snapshot: c.SystemStateSnapshot, request: c.CognitiveRequest) -> c.CognitiveResponse:
        reason = self._check(snapshot, request) or "QWEN_RUNTIME_UNAVAILABLE"
        return self._failure(snapshot, request, self.actor, reason)
