"""Pure proposal decisions and conservative reconciliation; never tool execution."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from . import contracts as c
from .adapters import request_input_hash
from ..science.temporal import aware_utc


def default_capabilities() -> tuple[c.CapabilityDescriptor, ...]:
    """Reviewed foundation capabilities, independent of any model's proposals."""
    definitions = (
        ("no-action", c.ActionClass.NO_ACTION, True, False, False),
        ("qwen-mock-analysis", c.ActionClass.REQUEST_QWEN_ANALYSIS, True, False, False),
        ("calculation-proposal", c.ActionClass.REQUEST_CALCULATION, False, False, False),
        ("simulation-proposal", c.ActionClass.REQUEST_SIMULATION, False, False, False),
        ("hydra-research-proposal", c.ActionClass.REQUEST_RESEARCH, False, True, True),
        ("hydra-source-refresh-proposal", c.ActionClass.REQUEST_SOURCE_REFRESH, False, True, True),
        ("human-review-proposal", c.ActionClass.REQUEST_HUMAN_REVIEW, True, False, False),
    )
    return tuple(c.CapabilityDescriptor(
        capability_id=name, action=action, enabled=enabled,
        requires_medusa=medusa, requires_source_policy=policy,
    ) for name, action, enabled, medusa, policy in definitions)


def _system_metadata(snapshot, now, inputs=(), reasons=(), source_refs=()):
    return c.Metadata(
        created_at=aware_utc(now), as_of_at=snapshot.metadata.as_of_at,
        temporal_mode=snapshot.metadata.temporal_mode,
        actor=c.ActorIdentity(actor_id="cognitive-orchestrator", role=c.ActorRole.SYSTEM),
        source_refs=tuple(source_refs), input_hashes=tuple(inputs), reason_codes=tuple(reasons),
    )


def decide_action(
    snapshot: c.SystemStateSnapshot,
    proposal: c.ActionProposal,
    *,
    now: datetime,
    request: c.CognitiveRequest | None = None,
    previous_decisions: tuple[c.ActionDecision, ...] = (),
    max_age_seconds: int = 300,
) -> c.ActionDecision:
    """Validate against the controlled snapshot; return a decision, not an action.

    Callers must supply retained prior decisions when resuming an artifact cycle.
    No positive decision dispatches anything. Research/source requests remain
    blocked for the separate permitted HYDRA -> MEDUSA -> memory path.
    """
    if type(snapshot) is not c.SystemStateSnapshot or type(proposal) is not c.ActionProposal:
        raise ValueError("TYPED_PROPOSAL_REQUIRED")
    c.SystemStateSnapshot.from_dict(snapshot.to_dict())
    c.ActionProposal.from_dict(proposal.to_dict())
    now = aware_utc(now)
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 3600:
        raise ValueError("INVALID_PROPOSAL_AGE_BOUND")
    reasons = []
    if type(request) is not c.CognitiveRequest:
        reasons.append("ORIGINATING_REQUEST_REQUIRED")
    else:
        c.CognitiveRequest.from_dict(request.to_dict())
        if request.digest() not in proposal.metadata.input_hashes:
            reasons.append("PROPOSAL_REQUEST_HASH_MISMATCH")
        if proposal.action not in request.allowed_actions:
            reasons.append("ACTION_OUTSIDE_REQUEST_SCOPE")
        if (request.state_hash != snapshot.state_hash
                or request.metadata.as_of_at != snapshot.metadata.as_of_at
                or request.metadata.temporal_mode != snapshot.metadata.temporal_mode):
            reasons.append("REQUEST_CONTEXT_MISMATCH")
        if request.metadata.created_at > now:
            reasons.append("FUTURE_REQUEST_CLOCK")
        if (now - request.metadata.created_at).total_seconds() > max_age_seconds:
            reasons.append("STALE_REQUEST")
    if proposal.state_hash != snapshot.state_hash:
        reasons.append("STATE_HASH_MISMATCH")
    if (proposal.metadata.as_of_at != snapshot.metadata.as_of_at or
            proposal.metadata.temporal_mode != snapshot.metadata.temporal_mode):
        reasons.append("TEMPORAL_CONTEXT_MISMATCH")
    if any(prior.proposal_id == proposal.proposal_id for prior in previous_decisions):
        reasons.append("PROPOSAL_REPLAY")
    if proposal.metadata.created_at > now or snapshot.metadata.created_at > now:
        reasons.append("FUTURE_OPERATION_CLOCK")
    if ((now - proposal.metadata.created_at).total_seconds() > max_age_seconds or
            (now - snapshot.metadata.created_at).total_seconds() > max_age_seconds):
        reasons.append("STALE_PROPOSAL_OR_STATE")
    descriptors = [item for item in snapshot.capabilities if item.capability_id == proposal.requested_capability]
    if len(descriptors) != 1 or descriptors[0].action != proposal.action:
        reasons.append("CAPABILITY_NOT_ALLOWLISTED")
    elif not descriptors[0].enabled:
        reasons.append("CAPABILITY_DISABLED")
    if proposal.action in (c.ActionClass.REQUEST_RESEARCH, c.ActionClass.REQUEST_SOURCE_REFRESH):
        reasons.append("HYDRA_MEDUSA_POLICY_PATH_REQUIRED")
    permitted = not reasons
    if permitted:
        reasons.append("NO_ACTION" if proposal.action == c.ActionClass.NO_ACTION else "PROPOSAL_ONLY_NO_EXECUTION")
    # COMPLETE describes the decision only; it never claims an action ran.
    status = c.ResultStatus.COMPLETE if permitted else c.ResultStatus.BLOCKED
    return c.ActionDecision(
        metadata=_system_metadata(snapshot, now, (proposal.digest(),)
                                  + ((request.digest(),) if type(request) is c.CognitiveRequest else ()), reasons),
        proposal_id=proposal.proposal_id, state_hash=snapshot.state_hash,
        action=proposal.action, requested_capability=proposal.requested_capability,
        permitted=permitted, result_status=status, reason_codes=tuple(reasons),
    )


def reconcile_responses(
    snapshot: c.SystemStateSnapshot,
    requests: tuple[c.CognitiveRequest, ...],
    responses: tuple[c.CognitiveResponse, ...],
    *,
    now: datetime,
    reviewed_agreement: c.AgreementState | None = None,
    reviewer: c.ActorIdentity | None = None,
    review_refs: tuple[str, ...] = (),
) -> c.ReconciliationReport:
    """Preserve claims and context; prose alone never establishes agreement.

    An optional explicit human classification requires references already in the
    controlled snapshot. This records a review, not an automatic semantic proof
    or an authentication mechanism. Mismatched inputs always override a review.
    """
    if len(requests) > 16 or len(responses) > 16:
        raise ValueError("RECONCILIATION_INPUT_BOUND")
    c.SystemStateSnapshot.from_dict(snapshot.to_dict())
    by_id = {}
    for request in requests:
        c.CognitiveRequest.from_dict(request.to_dict())
        if request.request_id in by_id:
            raise ValueError("DUPLICATE_REQUEST_ID")
        by_id[request.request_id] = request
    positions = []
    contexts = set()
    comparable = True
    complete = len(responses) >= 2
    actors = set()
    for response in responses:
        c.CognitiveResponse.from_dict(response.to_dict())
        request = by_id.get(response.request_id)
        actors.add(response.metadata.actor.actor_id)
        complete &= response.result_status == c.ResultStatus.COMPLETE and bool(response.conclusions)
        matches = request is not None and (
            response.state_hash == snapshot.state_hash == request.state_hash and
            response.metadata.as_of_at == request.metadata.as_of_at == snapshot.metadata.as_of_at and
            response.metadata.temporal_mode == request.metadata.temporal_mode == snapshot.metadata.temporal_mode and
            response.input_hash == request_input_hash(snapshot, request)
        )
        comparable &= matches
        if request is not None:
            contexts.add(request.task)
        for claim in response.conclusions:
            positions.append(c.Position(
                actor=response.metadata.actor, claim_id=claim.hypothesis_id,
                summary=claim.summary, epistemic_state=claim.epistemic_state,
                provenance_refs=claim.metadata.source_refs,
                request_id=response.request_id, input_hash=response.input_hash,
                state_hash=response.state_hash, as_of_at=response.metadata.as_of_at,
                temporal_mode=response.metadata.temporal_mode,
                task=request.task if request else None, result_status=response.result_status,
            ))
    comparable &= len(contexts) <= 1
    complete &= len(actors) >= 2
    agreement = c.AgreementState.INSUFFICIENT_EVIDENCE
    reasons = ["NO_MEASURED_CLAIM_COMPARISON"]
    if not comparable:
        agreement = c.AgreementState.NOT_COMPARABLE
        reasons = ["INPUT_OR_TEMPORAL_CONTEXT_MISMATCH"]
    elif not complete:
        reasons = ["INCOMPLETE_OR_SINGLE_ACTOR_ANALYSIS"]
    elif reviewed_agreement is not None:
        if (reviewer is None or reviewer.role != c.ActorRole.HUMAN or not review_refs or
                not set(review_refs).issubset(set(snapshot.metadata.source_refs))):
            raise ValueError("CONTROLLED_HUMAN_REVIEW_REFERENCE_REQUIRED")
        agreement = c.AgreementState(reviewed_agreement)
        reasons = ["EXPLICIT_HUMAN_REVIEW_CLASSIFICATION", "NOT_AUTOMATIC_SEMANTIC_PROOF"]
    metadata = _system_metadata(
        snapshot, now,
        tuple(response.digest() for response in responses), reasons, review_refs,
    )
    if "EXPLICIT_HUMAN_REVIEW_CLASSIFICATION" in reasons:
        metadata = replace(metadata, actor=reviewer)
    return c.ReconciliationReport(
        metadata=metadata, state_hash=snapshot.state_hash,
        agreement=agreement, positions=tuple(positions), reason_codes=tuple(reasons),
    )
