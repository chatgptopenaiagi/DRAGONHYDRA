"""Deterministic, bounded projections of controlled parent state.

This module has no acquisition, inference or database write capability. The live
entry point uses the existing fixed read-role operation. Raw source prose never
crosses the snapshot boundary. A trusted projection is not source attestation.
"""
from dataclasses import asdict, fields
from datetime import datetime, timezone
from hashlib import sha256
import json

from dragonhydra.medusa.evidence import AsOfSelection, ClaimKind
from dragonhydra.science.temporal import TemporalMode

from .contracts import (
    ActorIdentity, ActorRole, EvidenceDelta, EvidenceSummary, EpistemicState, Metadata,
    ModelDelta, StateDelta, UncertaintyDelta,
    ResultStatus, SourceSummary, StatusSummary, SystemStateSnapshot,
    UncertaintySummary,
)


def _hash(value):
    def encode(item):
        if isinstance(item, datetime):
            return item.astimezone(timezone.utc).isoformat()
        raise TypeError('UNSUPPORTED_PROJECTION_VALUE')
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             allow_nan=False, default=encode).encode()).hexdigest()


def _opaque(kind, value):
    """References cannot carry secrets, raw source text or local paths."""
    return kind + ':' + _hash(value)


def project_medusa_selection(selection, *, temporal_mode, epistemic_state):
    """Only an existing usable Medusa as-of selection can enter this route.

    The controlled producer must declare synthetic/reconstructed provenance;
    the old Medusa scalar contract does not carry those labels itself.
    """
    if type(selection) is not AsOfSelection or not selection.usable:
        raise ValueError('USABLE_MEDUSA_SELECTION_REQUIRED')
    if not isinstance(temporal_mode, TemporalMode):
        raise ValueError('TEMPORAL_MODE_REQUIRED')
    if epistemic_state not in (EpistemicState.OBSERVATION,
                              EpistemicState.HYPOTHESIS, EpistemicState.SYNTHETIC):
        raise ValueError('EXPLICIT_SOURCE_EPISTEMIC_STATE_REQUIRED')
    summaries = []
    for version in selection.versions:
        packet = version.packet
        if (epistemic_state is EpistemicState.OBSERVATION
                and (packet.claim_kind is not ClaimKind.OBSERVED
                     or packet.temporal.event_at > selection.request.target_as_of_at)):
            raise ValueError('FUTURE_OR_EXPECTED_IS_NOT_OBSERVATION')
        summaries.append(EvidenceSummary(
            evidence_id=_opaque('medusa-version', version.version_id),
            source_id=_opaque('source', packet.source.source_id),
            content_hash=_hash(asdict(version)),
            available_at=packet.temporal.available_at,
            observed_at=packet.temporal.observed_at,
            event_at=packet.temporal.event_at,
            epistemic_state=epistemic_state, temporal_mode=temporal_mode,
            validation_ref=_opaque('medusa-validation', version.version_id),
            validation_reason_codes=('MEDUSA_SELECTION_USABLE',),
            provenance_refs=tuple(_opaque('provenance', ref) for ref in packet.provenance_ids),
            numeric_value=float(packet.value) if type(packet.value) in (int, float) else None,
        ))
    return tuple(summaries)


def build_snapshot(*, metadata, evidence=(), sources=(), models=(),
                   uncertainties=(), research_needs=(), recent_actions=(),
                   capabilities=(), health=(), stage_status=(), fixture_id=None,
                   goals=(), unresolved_questions=(), chain_breaks=()):
    """Canonicalize typed projections; no ambient clock or hidden live reads.

    All inputs belong to the trusted state-builder boundary, never to AI output.
    Contract validation rejects unknown fields, late evidence and label changes.
    The supplied creation timestamp is part of the reproducible input.
    """
    groups = {
        'evidence': (evidence, 'evidence_id'), 'sources': (sources, 'source_id'),
        'models': (models, 'model_id'), 'uncertainties': (uncertainties, 'uncertainty_id'),
        'health': (health, 'component'), 'stage_status': (stage_status, 'component'),
    }
    normalized = {}
    for name, (items, key) in groups.items():
        if type(items) is not tuple or len(items) > 256:
            raise ValueError('BOUNDED_IMMUTABLE_PROJECTION_REQUIRED')
        identifiers = [getattr(item, key, None) for item in items]
        if None in identifiers or len(set(identifiers)) != len(identifiers):
            raise ValueError('UNIQUE_TYPED_PROJECTION_REQUIRED')
        normalized[name] = tuple(sorted(items, key=lambda item: getattr(item, key)))
    return SystemStateSnapshot(
        metadata=metadata, fixture_id=fixture_id, **normalized,
        research_needs=research_needs, recent_actions=recent_actions,
        capabilities=capabilities, goals=goals,
        unresolved_questions=unresolved_questions, chain_breaks=chain_breaks,
    )


def project_stored_fixture(record, *, as_of_at, stored_at=None):
    """Whitelist a stored parent fixture already accepted by Web MEDUSA.

    This observes the captured source record, not a claimed exact final whistle.
    Its observation event uses the genuine capture clock. Unknown fixture UTC
    kickoff is not invented. Free text, URLs and raw scores are not exported.
    """
    if type(record) is not dict:
        raise ValueError('STORED_RECORD_REQUIRED')
    verdict = record.get('validation', {})
    if type(verdict) is not dict:
        raise ValueError('ACCEPTED_MEDUSA_RECORD_REQUIRED')
    if verdict.get('decision') not in ('ACCEPT', 'ACCEPT_WITH_WARNING'):
        raise ValueError('ACCEPTED_MEDUSA_RECORD_REQUIRED')
    if type(record.get('synthetic')) is not bool:
        raise ValueError('EXPLICIT_SYNTHETIC_LABEL_REQUIRED')
    observed = datetime.fromisoformat(record['observed_at'])
    available = datetime.fromisoformat(record['available_at'])
    updated = datetime.fromisoformat(record['updated_at'])
    clocks = (observed, available, updated, as_of_at) + ((stored_at,) if stored_at is not None else ())
    if any(not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None for t in clocks):
        raise ValueError('AWARE_CAPTURE_CLOCK_REQUIRED')
    # The legacy web record's updated_at is its normalization clock, later than
    # source availability. Use a conservative *derived* knowledge bound without
    # rewriting or claiming earlier availability of that normalized revision.
    knowledge_bound = max(available, updated, stored_at or updated)
    if observed > available or knowledge_bound > as_of_at:
        raise ValueError('EVIDENCE_OUTSIDE_CURSOR')
    # Explicit record allow-list excludes annotations/instructions/secret fields.
    projected = {k: record.get(k) for k in (
        'fixture_id', 'source_id', 'content_hash', 'observed_at', 'available_at',
        'updated_at', 'home_score', 'away_score', 'match_date', 'synthetic',
        'parser_version', 'license_status', 'terms_status', 'robots_status',
    )}
    projected['stored_at'] = stored_at.isoformat() if stored_at is not None else None
    return EvidenceSummary(
        evidence_id=_opaque('stored-fixture', [record['fixture_id'], available.isoformat()]),
        source_id=_opaque('source', record['source_id']), content_hash=_hash(projected),
        available_at=knowledge_bound, observed_at=observed, event_at=observed,
        epistemic_state=EpistemicState.SYNTHETIC if record['synthetic'] else EpistemicState.OBSERVATION,
        temporal_mode=TemporalMode.STRICT_PIT,
        validation_ref=_opaque('stored-medusa', [record['fixture_id'], verdict]),
        validation_reason_codes=('ACCEPTED_STORED_SOURCE_RECORD', 'DERIVED_KNOWLEDGE_BOUND')
        + (('STALE_DATA',) if verdict['decision'] == 'ACCEPT_WITH_WARNING' else ()),
        provenance_refs=(_opaque('raw-content', record['content_hash']),
                         _opaque('parser', record['parser_version'])),
    )


def build_parent_snapshot(*, as_of_at, created_at, capabilities=()):
    """One bounded read of existing parent state, with explicit absent stages.

    The 32-row view is a bounded sample, not a full database reconstruction.
    No Qwen/Codex adapter receives the store or its credentials.
    """
    from dragonhydra.storage.intelligence import sql_connection
    # A fixed projection with a fixed limit and stable order; no AI-supplied SQL.
    cursor = as_of_at.isoformat()
    with sql_connection('read') as connection:
        rows = connection.cursor().execute('''WITH revisions AS (
            SELECT payload,natural_key,created_at,
                ROW_NUMBER() OVER(PARTITION BY natural_key ORDER BY version DESC) AS rn
            FROM dragonhydra.fixtures WHERE available_at<=? AND created_at<=?
            AND TRY_CONVERT(datetimeoffset,JSON_VALUE(payload,'$.updated_at'))<=?)
            SELECT TOP(32) payload,CONVERT(nvarchar(64),created_at,127)
            FROM revisions WHERE rn=1 ORDER BY natural_key''',
            cursor, cursor, cursor).fetchall()
    evidence, excluded = [], 0
    for body, stored in rows:
        try:
            stored_at = datetime.fromisoformat(stored) if isinstance(stored, str) else stored
            evidence.append(project_stored_fixture(json.loads(body), as_of_at=as_of_at, stored_at=stored_at))
        except (KeyError, TypeError, ValueError):
            excluded += 1
    sources = tuple(SourceSummary(source_id=source, status=ResultStatus.COMPLETE,
                                  reason_codes=('STORED_CAPTURE_NOT_LIVE_SOURCE_HEALTH',))
                    for source in sorted({e.source_id for e in evidence}))
    return build_snapshot(
        metadata=Metadata(created_at=created_at, as_of_at=as_of_at,
                          temporal_mode=TemporalMode.STRICT_PIT,
                          actor=ActorIdentity(actor_id='parent-state-builder', role=ActorRole.SYSTEM),
                          input_hashes=tuple(sorted(e.content_hash for e in evidence)),
                          reason_codes=('BOUNDED_32_RECORD_VIEW', 'NO_ACTIVE_FIXTURE_SELECTED')
                          + (('UNACCEPTED_RECORDS_EXCLUDED',) if excluded else ())),
        evidence=tuple(evidence), sources=sources, capabilities=capabilities,
        uncertainties=(UncertaintySummary(uncertainty_id='evidence-coverage', score=None,
                                           reason_codes=('BOUNDED_VIEW', 'KICKOFF_TIMEZONE_UNVERIFIED')),
                       UncertaintySummary(uncertainty_id='research-value', score=None,
                                           reason_codes=('REAL_WORLD_BENEFIT_UNMEASURED',))),
        health=(StatusSummary(component='parent-sql-read', status=ResultStatus.COMPLETE,
                              reason_codes=('READ_ONLY_QUERY_SUCCEEDED',)),),
        stage_status=tuple(StatusSummary(component=name, status=ResultStatus.NOT_STARTED,
                                         reason_codes=('NOT_CONNECTED_TO_COGNITIVE_VIEW',))
                           for name in ('feature-summary', 'model-forecasts', 'tribunal',
                                        'simulation', 'real-market', 'source-health')),
        goals=('EXAMINE_MISSING_EVIDENCE',),
        unresolved_questions=('LAWFUL_ODDS', 'VERIFIED_KICKOFF_TIMEZONE', 'MEASURED_RESEARCH_BENEFIT'),
        chain_breaks=('LIVE_QWEN_UNAVAILABLE', 'LIVE_RESEARCH_DISPATCH_NOT_IMPLEMENTED'),
    )


def state_delta(previous, current, *, created_at):
    """Compare compatible snapshots without interpreting natural-language claims."""
    if type(previous) is not SystemStateSnapshot or type(current) is not SystemStateSnapshot:
        raise ValueError('TYPED_SNAPSHOTS_REQUIRED')
    if (previous.fixture_id != current.fixture_id
            or previous.metadata.temporal_mode != current.metadata.temporal_mode
            or previous.metadata.as_of_at > current.metadata.as_of_at):
        raise ValueError('SNAPSHOT_CONTEXT_NOT_COMPARABLE')
    metadata = Metadata(
        created_at=created_at, as_of_at=current.metadata.as_of_at,
        temporal_mode=current.metadata.temporal_mode,
        actor=ActorIdentity(actor_id='state-delta-builder', role=ActorRole.SYSTEM),
        input_hashes=(previous.state_hash, current.state_hash),
        reason_codes=('DETERMINISTIC_STATE_COMPARISON',),
    )
    before = {item.evidence_id: item for item in previous.evidence}
    after = {item.evidence_id: item for item in current.evidence}
    evidence = EvidenceDelta(
        metadata=metadata, before_state_hash=previous.state_hash,
        after_state_hash=current.state_hash,
        added=tuple(after[key] for key in sorted(after.keys() - before.keys())),
        removed_ids=tuple(sorted(before.keys() - after.keys())),
        changed_ids=tuple(key for key in sorted(before.keys() & after.keys())
                          if before[key] != after[key]),
    )
    before_models = {item.model_id: item for item in previous.models}
    after_models = {item.model_id: item for item in current.models}
    models = []
    for key in sorted(before_models.keys() | after_models.keys()):
        old, new = before_models.get(key), after_models.get(key)
        if old != new:
            models.append(ModelDelta(
                metadata=metadata, model_id=key,
                before_forecast_hash=old.forecast_hash if old else None,
                after_forecast_hash=new.forecast_hash if new else None,
                before_probabilities=old.probabilities if old else (),
                after_probabilities=new.probabilities if new else (),
            ))
    before_uncertainty = {item.uncertainty_id: item for item in previous.uncertainties}
    after_uncertainty = {item.uncertainty_id: item for item in current.uncertainties}
    uncertainties = []
    for key in sorted(before_uncertainty.keys() | after_uncertainty.keys()):
        old, new = before_uncertainty.get(key), after_uncertainty.get(key)
        if old != new:
            uncertainties.append(UncertaintyDelta(
                metadata=metadata, uncertainty_id=key,
                before=old.score if old else None, after=new.score if new else None,
            ))
    return StateDelta(
        metadata=metadata, before_state_hash=previous.state_hash,
        after_state_hash=current.state_hash, evidence=evidence,
        models=tuple(models), uncertainties=tuple(uncertainties),
        changed_sections=tuple(field.name for field in fields(previous)
                               if getattr(previous, field.name) != getattr(current, field.name)),
    )
