"""Narrow product adapters for the existing evidence-bound cognition engine.

No provider request, implicit import, new model or second database belongs here.
Explicit commands persist actual current calculations; reads never invent a
historical prediction or attach an outcome. The job ID is the command identity.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone

from . import market_store, public_results
from .cognition import adaptation, evaluation, memory, models

VERSION = 'system-workflow/1'
_KINDS = ('models', 'predictions', 'outcomes', 'research_tasks', 'evaluations', 'hypotheses')


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _cutoff(value=None):
    stamp = value or _now()
    when = evaluation._bound(stamp)
    return when.isoformat().replace('+00:00', 'Z')


def _memory_view(product, cutoff):
    # A workspace read must not create cognition tables merely to show zeroes.
    with closing(product.connect()) as db:
        schema = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','trigger')")}
    tables = {'cognitive_records', 'cognitive_receipts'}
    if not schema & tables:
        return {key: [] for key in _KINDS}
    required = tables | {'cognitive_records_no_update', 'cognitive_records_no_delete',
                         'cognitive_receipts_no_update', 'cognitive_receipts_no_delete'}
    if not required <= schema:
        raise ValueError('COGNITIVE_STORE_INCOMPLETE')
    return memory.as_of(product.db_path, cutoff, readonly=True)


def _target(product, match_id, cutoff):
    current = product.find(match_id)
    if current.get('_connector'):
        raise ValueError('SOURCE_FORECAST_WORKFLOW_UNAVAILABLE')
    rows = public_results.latest_as_of(product.db_path, cutoff)
    target = next((row for row in rows if product.match_id(row) == match_id), None)
    if target is None:
        raise ValueError('TARGET_NOT_ELIGIBLE_AT_CUTOFF')
    return target, rows


def _matches_target(record, target):
    source = record.get('target_evidence', {}).get('source_id') if record.get('model_run_id') else record.get('source_id')
    return source == target['source_id'] and record.get('fixture_key') == target['fixture_key']


def _run_records(view, run_id, target, match_id):
    runs = [row for row in view['models'] if row.get('run_id') == run_id]
    predictions = [row for row in view['predictions'] if row.get('run_id') == run_id]
    if any(row.get('parameters', {}).get('workflow', {}).get('match_id') != match_id for row in runs):
        raise ValueError('WORKFLOW_RUN_IDENTITY_CONFLICT')
    if any(not _matches_target(row, target) for row in predictions):
        raise ValueError('WORKFLOW_RUN_IDENTITY_CONFLICT')
    return runs, predictions


def forecast_match(product, match_id, run_id):
    """Compute and retain a prospective forecast for exactly one selected match.

    A replay returns its original records. A partially completed run remains
    visible and is not silently re-computed from newer evidence. The caller's
    persisted job/idempotency mechanism decides whether a new command is wanted.
    """
    if not isinstance(run_id, str) or not 1 <= len(run_id) <= 128:
        raise ValueError('INVALID_WORKFLOW_RUN_ID')
    cutoff = _cutoff()
    target, rows = _target(product, match_id, cutoff)
    view = _memory_view(product, cutoff)
    prior_models, prior_predictions = _run_records(view, run_id, target, match_id)
    if prior_models:
        expected = set(prior_models[0]['parameters']['workflow']['model_names'])
        complete = (expected == {row['model_name'] for row in prior_models}
                    and {row['record_id'] for row in prior_models}
                    == {row['model_run_id'] for row in prior_predictions})
        return {'workflow_version': VERSION, 'operation': 'forecast', 'match_id': match_id,
                'run_id': run_id, 'duplicate': True,
                'status': 'persisted' if complete else 'partial',
                'reason': None if complete else 'PARTIAL_RUN_REQUIRES_REVIEW',
                'model_runs': prior_models, 'predictions': prior_predictions}
    if target.get('outcome') is not None or target.get('result_state') != 'unavailable':
        raise ValueError('PROSPECTIVE_FORECAST_REQUIRES_UNPLAYED_TARGET')
    resolver = lambda digest: market_store.raw_source(product.db_path, digest)
    selected = adaptation.select(view, rows, target, cutoff, raw_resolver=resolver)
    forecast = models.forecast(rows, target, cutoff, resolver,
        performance_records=selected['records'],
        performance_resolver=lambda eid: memory.resolve_evidence(product.db_path, eid, cutoff))
    inputs = [row['evidence_id'] for row in forecast['training_manifest']]
    candidates = {name: model for name, model in forecast['models'].items() if model.get('available')}
    if forecast.get('ensemble'):
        candidates['ensemble'] = forecast['ensemble']
    if not inputs or not candidates:
        return {'workflow_version': VERSION, 'operation': 'forecast', 'match_id': match_id,
                'run_id': run_id, 'duplicate': False, 'status': 'unavailable',
                'reason': forecast['stop_reason'], 'model_runs': [], 'predictions': []}
    for name, result in candidates.items():
        saved = memory.record_model_run(product.db_path, {
            'run_id': run_id, 'model_name': name, 'model_version': forecast['model_version'],
            'data_cutoff': forecast['data_cutoff'], 'input_evidence_ids': inputs,
            'parameters': {'target_evidence_id': target['evidence_id'], 'result': result,
                'workflow': {'version': VERSION, 'match_id': match_id,
                    'generated_at': forecast['actual_run_time'], 'model_names': list(candidates),
                    'uncertainty': forecast['uncertainty_summary'], 'adaptation': selected}},
            'configuration': forecast['configuration'],
            'transformation': 'existing deterministic model output; ' + name})
        memory.record_prediction(product.db_path, {
            'run_id': run_id, 'model_run_id': saved['record_id'],
            'target_evidence_id': target['evidence_id'],
            'probabilities': {key: result['probabilities'][key]['value'] for key in ('home', 'draw', 'away')},
            'transformation': 'persisted selected-match forecast from retained model output'})
    stored_models, stored_predictions = _run_records(_memory_view(product, _cutoff()), run_id, target, match_id)
    return {'workflow_version': VERSION, 'operation': 'forecast', 'match_id': match_id,
            'run_id': run_id, 'duplicate': False, 'status': 'persisted', 'reason': None,
            'model_runs': stored_models, 'predictions': stored_predictions}


def match_history(product, match_id, cutoff=None):
    """Read retained selected-match history; no forecast, import or evaluation write."""
    at = _cutoff(cutoff)
    target, _ = _target(product, match_id, at)
    view = _memory_view(product, at)
    predictions = [row for row in view['predictions'] if _matches_target(row, target)]
    outcomes = [row for row in view['outcomes'] if _matches_target(row, target)]
    model_ids = {row['model_run_id'] for row in predictions}
    model_runs = [row for row in view['models'] if row['record_id'] in model_ids
                  or row.get('parameters', {}).get('target_evidence_id') == target['evidence_id']]
    evaluations = [row for row in view['evaluations']
                   if row.get('evaluation_scope', {}).get('source_id') == target['source_id']
                   and target['fixture_key'] in row.get('fixture_keys', [])]
    observed = evaluation.evaluate_observed({'predictions': predictions, 'outcomes': outcomes}, at)
    # Historical diagnostics remain explicit CLI operations. Merely opening
    # history or a monitoring page must not execute another forecasting model.
    holdout = {'mode': 'PRESENT_KNOWLEDGE_CHRONOLOGICAL_HOLDOUT', 'available': False,
               'reason': 'EXPLICIT_DIAGNOSTIC_NOT_REQUESTED'}
    records = {'models': model_runs, 'predictions': predictions, 'outcomes': outcomes, 'evaluations': evaluations}
    return {'workflow_version': VERSION, 'match_id': match_id, 'cutoff': at,
            'target_evidence_id': target['evidence_id'], 'source_id': target['source_id'],
            'fixture_key': target['fixture_key'], 'records': records,
            'counts': {name: len(items) for name, items in records.items()},
            'operational': observed, 'present_knowledge_holdout': holdout,
            'limitations': ['A stored forecast is not proof of predictive skill.',
                'Operational scores require an earlier retained prediction and a later eligible result.',
                'The historical holdout uses present knowledge and is separate from operational history.']}


def evaluate_match(product, match_id, run_id):
    """Attach a real later outcome and retain existing comparable cohort metrics.

    Outcome attachment is selected-match scoped. Persisted evaluation groups keep
    the engine's source/competition/model/period/settlement cohort scope; they do
    not pretend that a single fixture is an independent performance estimate.
    """
    if not isinstance(run_id, str) or not 1 <= len(run_id) <= 128:
        raise ValueError('INVALID_WORKFLOW_RUN_ID')
    target, _ = _target(product, match_id, _cutoff())
    current = _memory_view(product, _cutoff())
    prior = [row for row in current['evaluations'] if row.get('run_id') == run_id]
    if any(row.get('evaluation_scope', {}).get('source_id') != target['source_id']
           or target['fixture_key'] not in row.get('fixture_keys', []) for row in prior):
        raise ValueError('WORKFLOW_RUN_IDENTITY_CONFLICT')
    attached = None
    pending = None
    if prior:
        pass
    elif target.get('result_state') != 'available' or target.get('outcome') is None:
        pending = 'LATER_RETAINED_OUTCOME_UNAVAILABLE'
    else:
        try:
            attached = memory.record_outcome(product.db_path, target['evidence_id'])
        except ValueError as exc:
            if str(exc) not in ('NO_EARLIER_ELIGIBLE_PREDICTION', 'OUTCOME_TIME_NOT_PROVABLY_POST_EVENT',
                                'AMBIGUOUS_OUTCOME_FIXTURE'):
                raise
            pending = str(exc)
    # A retried evaluation reuses its first retained cutoff. New evidence needs a
    # new explicit command; it must never overwrite that command's original view.
    cutoff = prior[0]['evaluation_cutoff'] if prior else _cutoff()
    view = _memory_view(product, cutoff)
    report = evaluation.evaluate_observed(view, cutoff)
    persisted = []
    for group in report['groups']:
        scope = group['evaluation_scope']
        if (group['model_name'] not in models.NAMES
                or scope['source_id'] != target['source_id'] or scope['competition'] != target['competition']
                or not any(case['fixture_key'] == target['fixture_key'] for case in group['cases'])):
            continue
        for metric in ('brier', 'log_loss'):
            persisted.append(memory.record_evaluation(product.db_path, {
                'run_id': run_id, 'model_name': group['model_name'],
                'model_version': group['model_version'], 'metric': metric,
                'evaluation_cutoff': cutoff, **scope}))
    return {'workflow_version': VERSION, 'operation': 'evaluate', 'match_id': match_id,
            'run_id': run_id, 'duplicate': bool(prior), 'status': 'persisted' if persisted else 'pending',
            'reason': pending, 'attached_outcome': attached,
            'persisted_evaluations': persisted, 'history': match_history(product, match_id)}
