"""Explicit publication of already-persisted forecasts; never runs a model/import."""
from .base import SCHEMA, StorageError, canonical, fingerprint, validate_bundle

def archive_forecast(*, repository, data, memory_view, clock, match_id, run_id):
    if repository is None:raise StorageError('RESEARCH_STORAGE_NOT_CONFIGURED')
    if not isinstance(run_id,str) or not 1<=len(run_id)<=128:raise StorageError('INVALID_FORECAST_RUN_ID')
    # These are original immutable records, not today's recalculated prediction.
    view=memory_view(clock())
    models=[r for r in view['models'] if r.get('run_id')==run_id]
    model_ids={r['record_id'] for r in models}
    predictions=[r for r in view['predictions'] if r.get('model_run_id') in model_ids]
    if not models or len(models)!=len(predictions):raise StorageError('COMPLETE_PERSISTED_FORECAST_REQUIRED')
    workflow=models[0].get('parameters',{}).get('workflow',{})
    expected=set(workflow.get('model_names',[]))
    if not expected or expected!={m['model_name'] for m in models} or any(m.get('parameters',{}).get('workflow',{}).get('match_id')!=match_id for m in models):
        raise StorageError('RESEARCH_FORECAST_MATCH_MISMATCH')
    inputs=models[0]['training_manifest']
    if any(canonical(m['training_manifest'])!=canonical(inputs) for m in models):
        raise StorageError('RESEARCH_INPUT_SNAPSHOT_MISMATCH')
    target=predictions[0]['target_evidence']
    if any(canonical(p['target_evidence'])!=canonical(target) for p in predictions):
        raise StorageError('RESEARCH_TARGET_SNAPSHOT_MISMATCH')
    # The retained target snapshot has date precision. Never enrich it with
    # later scores or imply an evidenced UTC kickoff that was not retained.
    match=data.present({**target,'event_at_utc':None,'source_local_time':None})
    if match['id']!=match_id:raise StorageError('RESEARCH_MATCH_ID_MISMATCH')
    bundle=dict(schema_version=SCHEMA,archive_id=fingerprint([SCHEMA,repository.scope,match_id,run_id]),
        match_id=match_id,forecast_run_id=run_id,match=match,models=models,predictions=predictions,
        input_manifest=inputs,evaluation_status='pending',
        source_build=workflow.get('build',{}),
        ownership={'canonical_source':'existing retained SQLite evidence and immutable cognitive memory',
            'publication':'Explicit immutable research snapshot. No background synchronization or source overwrite.',
            'evaluation':'Forecast snapshot preserves its original pending state; later outcomes are separate records.'})
    validate_bundle(bundle)
    receipt=repository.save(bundle)
    return {'archive_id':bundle['archive_id'],'storage':receipt,'canonical_run_id':run_id,
            'match_id':match_id,'prediction_count':len(predictions),'input_count':len(inputs)}
