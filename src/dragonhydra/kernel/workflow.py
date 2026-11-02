"""Selected-match durable commands over existing engine ports and mathematics.

Explicit forecasts reuse the deterministic engines. No provider acquisition,
local-AI request, secondary store or backdated prediction is introduced here.
Durable job IDs bind immutable commands and replay identity.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from .. import market_store, public_results
from ..build_meta import info as build_info
from ..cognition import adaptation, evaluation, memory as memory_backend, models
from ..domain import identity


VERSION = 'core-next.workflow/1'


def _cutoff(clock, value=None):
    return evaluation._bound(value or clock()).isoformat().replace('+00:00', 'Z')


def _target(data, db_path, match_id, cutoff):
    # Reuse the existing transformation under a read-only connection: its
    # CREATE IF NOT EXISTS statements cannot repair missing source objects.
    try:
        with closing(sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)) as db:
            db.execute('PRAGMA query_only=ON')
            deadline = time.monotonic()+2
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            rows = public_results.latest(db, cutoff)
    except (sqlite3.Error, OSError):
        raise ValueError('RETAINED_SOURCE_STORE_UNAVAILABLE') from None
    target = next((row for row in rows if identity('fixture', row['source_id'], row['fixture_key']) == match_id), None)
    if target is None:
        current = data.find(match_id)
        if current.get('_connector'):
            raise ValueError('SOURCE_FORECAST_WORKFLOW_UNAVAILABLE')
        raise ValueError('TARGET_NOT_ELIGIBLE_AT_CUTOFF')
    return target, rows


def _matches(record, target):
    source = record.get('target_evidence', {}).get('source_id') if record.get('model_run_id') else record.get('source_id')
    return source == target['source_id'] and record.get('fixture_key') == target['fixture_key']


def _run_records(view, run_id, target, match_id):
    runs = [row for row in view['models'] if row.get('run_id') == run_id]
    predictions = [row for row in view['predictions'] if row.get('run_id') == run_id]
    if any(row.get('parameters', {}).get('workflow', {}).get('match_id') != match_id for row in runs):
        raise ValueError('WORKFLOW_RUN_IDENTITY_CONFLICT')
    if any(not _matches(row, target) for row in predictions) or predictions and not runs:
        raise ValueError('WORKFLOW_RUN_IDENTITY_CONFLICT')
    return runs, predictions


def _run_id(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError('INVALID_WORKFLOW_RUN_ID')
    return value


def forecast_match(*, data, model_backend, memory, db_path, clock, match_id, run_id=None):
    run_id = _run_id(uuid4().hex if run_id is None else run_id)
    cutoff = _cutoff(clock)
    target, rows = _target(data, db_path, match_id, cutoff)
    view = memory.view(cutoff)
    prior_models, prior_predictions = _run_records(view, run_id, target, match_id)
    if prior_models:
        expected = set(prior_models[0]['parameters']['workflow']['model_names'])
        complete = (expected == {row['model_name'] for row in prior_models}
                    and {row['record_id'] for row in prior_models} == {row['model_run_id'] for row in prior_predictions})
        return {'schema_version': VERSION, 'workflow_version': VERSION, 'operation': 'forecast',
                'match_id': match_id, 'run_id': run_id, 'duplicate': True,
                'status': 'persisted' if complete else 'partial', 'available': complete,
                'reason': None if complete else 'PARTIAL_RUN_REQUIRES_REVIEW',
                'model_runs': prior_models, 'predictions': prior_predictions}
    if target.get('outcome') is not None or target.get('result_state') != 'unavailable':
        raise ValueError('PROSPECTIVE_FORECAST_REQUIRES_UNPLAYED_TARGET')
    resolver = lambda digest: market_store.raw_source(db_path, digest)
    selected = adaptation.select(view, rows, target, cutoff, raw_resolver=resolver)
    forecast = model_backend.forecast(rows, target, cutoff, resolver,
        performance_records=selected['records'],
        performance_resolver=lambda eid: memory_backend.resolve_evidence(db_path, eid, cutoff))
    inputs = [row['evidence_id'] for row in forecast['training_manifest']]
    candidates = {name: result for name, result in forecast['models'].items() if result.get('available')}
    if forecast.get('ensemble'):
        candidates['ensemble'] = forecast['ensemble']
    if not inputs or not candidates:
        return {'schema_version': VERSION, 'workflow_version': VERSION, 'operation': 'forecast',
                'match_id': match_id, 'run_id': run_id, 'duplicate': False, 'available': False,
                'status': 'unavailable', 'reason': forecast['stop_reason'], 'forecast': forecast,
                'model_runs': [], 'predictions': []}
    build = {key: value for key, value in build_info().items() if key in
             ('version', 'source_sha', 'source_content_sha256', 'build_kind', 'api_namespace', 'schema_version')}
    for name, result in candidates.items():
        saved = memory.record_model({
            'run_id': run_id, 'model_name': name, 'model_version': forecast['model_version'],
            'data_cutoff': forecast['data_cutoff'], 'input_evidence_ids': inputs,
            'parameters': {'target_evidence_id': target['evidence_id'], 'result': result,
                'workflow': {'version': VERSION, 'match_id': match_id,
                    'generated_at': forecast['actual_run_time'], 'model_names': list(candidates),
                    'input_versions': inputs, 'build': build,
                    'uncertainty': forecast['uncertainty_summary'], 'adaptation': selected}},
            'configuration': forecast['configuration'],
            'transformation': 'existing deterministic model output; '+name})
        memory.record_prediction({'run_id': run_id, 'model_run_id': saved['record_id'],
            'target_evidence_id': target['evidence_id'],
            'probabilities': {key: result['probabilities'][key]['value'] for key in ('home', 'draw', 'away')},
            'transformation': 'persisted selected-match forecast from retained model output'})
    stored_models, stored_predictions = _run_records(memory.view(_cutoff(clock)), run_id, target, match_id)
    return {'schema_version': VERSION, 'workflow_version': VERSION, 'operation': 'forecast',
            'match_id': match_id, 'run_id': run_id, 'duplicate': False, 'available': True,
            'status': 'persisted', 'reason': None, 'forecast': forecast,
            'model_runs': stored_models, 'predictions': stored_predictions}


def match_history(*, data, view, db_path, clock, match_id, cutoff=None):
    at = _cutoff(clock, cutoff)
    target, _ = _target(data, db_path, match_id, at)
    retained = view(at)
    predictions = [row for row in retained['predictions'] if _matches(row, target)]
    outcomes = [row for row in retained['outcomes'] if _matches(row, target)]
    model_ids = {row['model_run_id'] for row in predictions}
    model_runs = [row for row in retained['models'] if row['record_id'] in model_ids
                  or row.get('parameters', {}).get('workflow', {}).get('match_id') == match_id]
    evaluations = [row for row in retained['evaluations']
                   if row.get('evaluation_scope', {}).get('source_id') == target['source_id']
                   and target['fixture_key'] in row.get('fixture_keys', [])]
    records = {'models': model_runs, 'predictions': predictions, 'outcomes': outcomes, 'evaluations': evaluations}
    return {'schema_version': VERSION, 'workflow_version': VERSION, 'match_id': match_id, 'cutoff': at,
            'target_evidence_id': target['evidence_id'], 'source_id': target['source_id'],
            'fixture_key': target['fixture_key'], 'records': records,
            'counts': {name: len(items) for name, items in records.items()},
            'operational': evaluation.evaluate_observed({'predictions': predictions, 'outcomes': outcomes}, at),
            'present_knowledge_holdout': {'mode': 'PRESENT_KNOWLEDGE_CHRONOLOGICAL_HOLDOUT',
                'available': False, 'reason': 'EXPLICIT_DIAGNOSTIC_NOT_REQUESTED'},
            'limitations': ['A stored forecast is not proof of predictive skill.',
                'Operational scores require an earlier retained prediction and a later eligible result.',
                'No model diagnostic, import or forecast was run by opening this history.']}


def evaluate_match(*, data, memory, persist, db_path, clock, match_id, run_id):
    run_id = _run_id(run_id)
    target, _ = _target(data, db_path, match_id, _cutoff(clock))
    current = memory.view(_cutoff(clock))
    prior = [row for row in current['evaluations'] if row.get('run_id') == run_id]
    if any(row.get('evaluation_scope', {}).get('source_id') != target['source_id']
           or target['fixture_key'] not in row.get('fixture_keys', []) for row in prior):
        raise ValueError('WORKFLOW_RUN_IDENTITY_CONFLICT')
    attached, pending = None, None
    if prior:
        pass
    elif target.get('result_state') != 'available' or target.get('outcome') is None:
        pending = 'LATER_RETAINED_OUTCOME_UNAVAILABLE'
    elif not any(_matches(row, target) for row in current['predictions']):
        pending = 'NO_EARLIER_ELIGIBLE_PREDICTION'
    else:
        try:
            attached = memory.attach_outcome(target['evidence_id'])
        except ValueError as error:
            if str(error) not in ('NO_EARLIER_ELIGIBLE_PREDICTION', 'OUTCOME_TIME_NOT_PROVABLY_POST_EVENT',
                                  'AMBIGUOUS_OUTCOME_FIXTURE'):
                raise
            pending = str(error)
    cutoff = prior[0]['evaluation_cutoff'] if prior else _cutoff(clock)
    retained = memory.view(cutoff)
    report = evaluation.evaluate_observed(retained, cutoff)
    persisted = []
    for group in report['groups']:
        scope = group['evaluation_scope']
        if (group['model_name'] not in models.NAMES
                or scope['source_id'] != target['source_id'] or scope['competition'] != target['competition']
                or not any(case['fixture_key'] == target['fixture_key'] for case in group['cases'])):
            continue
        for metric in ('brier', 'log_loss'):
            persisted.append(persist({'run_id': run_id, 'model_name': group['model_name'],
                'model_version': group['model_version'], 'metric': metric, 'evaluation_cutoff': cutoff, **scope}))
    return {'schema_version': VERSION, 'workflow_version': VERSION, 'operation': 'evaluate',
            'match_id': match_id, 'run_id': run_id, 'duplicate': bool(prior),
            'available': bool(persisted), 'status': 'persisted' if persisted else 'pending',
            'reason': pending, 'attached_outcome': attached, 'persisted_evaluations': persisted,
            'history': match_history(data=data, view=memory.view, db_path=db_path, clock=clock, match_id=match_id)}
