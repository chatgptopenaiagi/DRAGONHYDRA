"""Project-local data loading for cognitive research commands."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from .. import market_store, public_results
from . import adaptation, memory, models

ROOT = Path(__file__).resolve().parents[3]
FILES = ('openfootball-2025-26-en1.json', 'openfootball-2026-27-en1.json')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def prepare(db_path):
    """Import existing captured files using their verified acquisition receipts."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    imports = []
    for filename in FILES:
        path = ROOT / 'data' / 'raw' / filename
        if not path.is_file():
            path = Path(__file__).resolve().parents[1] / 'resources' / 'data' / 'raw' / filename
        receipt_path = path.with_suffix(path.suffix + '.receipt.json')
        if not path.exists() or not receipt_path.exists():
            continue
        receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
        item = public_results.import_file(db_path, path, source_id=receipt['source_id'],
            source_url=receipt['source_url'], acquisition_id=receipt['sha256'], receipt_path=receipt_path)
        imports.append(item)
    return imports


def source_rows(db_path, cutoff):
    return public_results.latest_as_of(db_path, cutoff)


def forecast_current(db_path, *, event_date=None):
    """Run forecasts only for a fixture demonstrably available and in the future."""
    imports = prepare(db_path)
    cutoff = now()
    rows = source_rows(db_path, cutoff)
    memory_view = memory.as_of(db_path, cutoff)
    candidates = sorted((r for r in rows if r.get('source_id') == FILES[1]
                         and r.get('result_state') == 'unavailable'
                         and (not event_date or r.get('event_date') == event_date)),
                        key=lambda r: (r['event_date'], r['fixture_key']))
    result = None
    skipped_flags=[]
    for target in candidates:
        try:
            selected = adaptation.select(memory_view,rows,target,cutoff,
                                         raw_resolver=lambda h:market_store.raw_source(db_path,h))
            result = models.forecast(rows, target, cutoff, lambda h: market_store.raw_source(db_path, h),
                                     performance_records=selected['records'],
                                     performance_resolver=lambda eid:memory.resolve_evidence(db_path,eid,cutoff))
            result['adaptation'] = selected
            break
        except ValueError as exc:
            if str(exc) == 'AMBIGUOUS_TARGET_FIXTURE':
                skipped_flags.extend(flag for flag in public_results.find_ambiguous_fixtures(rows,cutoff)
                                     if target['fixture_key'] in flag['fixture_keys'] and flag not in skipped_flags)
                continue
            if str(exc) != 'FUTURE_FIXTURE_TIME_UNCERTAIN':
                raise
    if result is None:
        if skipped_flags:
            raise ValueError('NO_UNAMBIGUOUS_ELIGIBLE_FUTURE_FIXTURE')
        raise ValueError('NO_ELIGIBLE_FUTURE_FIXTURE')
    for flag in skipped_flags:
        if flag not in result['quality_flags']:
            result['quality_flags'].append(flag)
        result['research_tasks'].append({'gap':'AMBIGUOUS_FIXTURE_DATE',
            'question':'Are the differently dated records a rescheduled match or separate fixtures?',
            'permitted_source':'documented source fixture IDs or user-supplied mapping',
            'priority_rationale':'Ambiguous identities must not be selected as forecasts.',
            'expected_evidence':'retained source fixture identifiers and revisions',
            'budget':'one bounded mapping review',
            'stopping_condition':'mapping verified or source remains ambiguous',
            'evidence_ids':flag['evidence_ids']})
    result['imports'] = imports
    return result


def holdout(db_path, *, cutoff=None):
    """Diagnose chronological partitions of data already captured by this system."""
    from . import evaluation
    prepare(db_path)
    cutoff = cutoff or now()
    rows = source_rows(db_path, cutoff)
    result = evaluation.chronological_holdout(rows, cutoff,
        lambda h: market_store.raw_source(db_path, h), source_id=FILES[0])
    cases = result['cases']
    if len(cases) >= 4:
        from statistics import fmean, variance
        middle = len(cases) // 2
        early, late = cases[:middle], cases[middle:]
        def segment(items):
            vals = [row['brier'] for row in items]
            return {'sample_size':len(vals),'mean_brier':fmean(vals),
                    'sample_variance':variance(vals) if len(vals)>1 else None,
                    'first_event_date':items[0]['event_date'],'last_event_date':items[-1]['event_date'],
                    'evidence_ids':sorted({eid for row in items for eid in row['evidence_ids']})}
        first, second = segment(early), segment(late)
        result['performance_change']={'first':first,'second':second,
            'mean_brier_change':second['mean_brier']-first['mean_brier'],
            'evidence_ids':sorted(set(first['evidence_ids']+second['evidence_ids'])),
            'evaluation_cutoff':cutoff,
            'interpretation':'Descriptive split within a present-knowledge holdout; not a verified live improvement.',
            'transformation':{'version':'cognitive-trend/1','formula':'later-half mean Brier minus earlier-half mean Brier'}}
    else:
        result['performance_change']={'value':None,'reason':'INSUFFICIENT_CASES'}
    return result


def train_current(db_path, *, event_date=None):
    """Persist model runs with actual times and linked eligible source evidence."""
    from uuid import uuid4
    from . import memory
    forecast = forecast_current(db_path, event_date=event_date)
    run_id = uuid4().hex
    inputs = [row['evidence_id'] for row in forecast['training_manifest']]
    if not inputs:
        return {'run_id':run_id,'forecast':forecast,'model_runs':[],
                'stop_reason':'NO_ELIGIBLE_TRAINING_EVIDENCE'}
    candidates = {name: model for name,model in forecast['models'].items() if model.get('available')}
    if forecast.get('ensemble'):
        candidates['ensemble'] = forecast['ensemble']
    stored = []
    for name, model in candidates.items():
        draft = {'run_id':run_id, 'model_name':name, 'model_version':forecast['model_version'],
            'data_cutoff':forecast['data_cutoff'], 'input_evidence_ids':inputs,
            'parameters':{'target_evidence_id':forecast['target']['evidence_id'],'result':model},
            'configuration':forecast['configuration'],
            'transformation':'deterministic provenance-checked football model; '+name}
        saved = memory.record_model_run(db_path, draft)
        stored.append({'model_name':name, **saved})
    return {'run_id':run_id, 'forecast':forecast, 'model_runs':stored}


def predict_current(db_path, *, event_date=None):
    """Persist each available forecast after its corresponding model record."""
    from . import memory
    trained = train_current(db_path, event_date=event_date)
    forecast = trained['forecast']
    predictions = []
    for saved in trained['model_runs']:
        name = saved['model_name']
        model = forecast['ensemble'] if name == 'ensemble' else forecast['models'][name]
        draft = {'run_id':trained['run_id'], 'model_run_id':saved['record_id'],
            'target_evidence_id':forecast['target']['evidence_id'],
            'probabilities':{key:model['probabilities'][key]['value'] for key in ('home','draw','away')},
            'transformation':'persisted forecast from model '+name+' and retained training evidence'}
        prediction = memory.record_prediction(db_path, draft)
        predictions.append({'model_name':name, **prediction})
    trained['predictions'] = predictions
    return trained


def attach_later_outcomes(db_path):
    """Attach retained result revisions only after matching genuine predictions."""
    from . import memory
    cutoff=now()
    view=memory.as_of(db_path,cutoff)
    rows=source_rows(db_path,cutoff)
    attached=[]
    pending=[]
    for row in rows:
        if row.get('result_state')!='available' or row.get('outcome') not in ('home','draw','away'):
            continue
        matches=[p for p in view['predictions'] if p.get('fixture_key')==row.get('fixture_key')
                 and p.get('target_evidence',{}).get('source_id')==row.get('source_id')]
        if not matches:
            continue
        try:
            receipt=memory.record_outcome(db_path,row['evidence_id'])
            attached.append({'source_evidence_id':row['evidence_id'],**receipt})
        except ValueError as exc:
            if str(exc) not in ('NO_EARLIER_ELIGIBLE_PREDICTION','OUTCOME_TIME_NOT_PROVABLY_POST_EVENT',
                                'AMBIGUOUS_OUTCOME_FIXTURE'):
                raise
            task={'gap':str(exc),'question':'Can the outcome timing and fixture identity be established?',
                  'permitted_source':'documented source fixture IDs or a verified later result',
                  'priority_rationale':'The outcome cannot yet be safely linked to an earlier forecast.',
                  'expected_evidence':'unambiguous fixture identity and actual result availability',
                  'budget':'one bounded source review','stopping_condition':'eligible outcome attached or source remains ambiguous',
                  'evidence_ids':[row['evidence_id']]}
            pending.append({'source_evidence_id':row['evidence_id'],'reason':str(exc),
                            'research_task':task,'task_status':'PROPOSED_NOT_PERSISTED'})
    return {'scan_cutoff':cutoff,'attached':attached,'pending':pending}


def current_research(db_path, forecast, *, model_run_id=None):
    from . import evaluation, memory, research as gaps
    cutoff = now()
    view = memory.as_of(db_path, cutoff)
    evaluated = evaluation.evaluate_observed(view, cutoff)
    scored = sum(group['metrics']['brier']['sample_size'] for group in evaluated['groups'])
    market_rows = market_store.get_as_of(db_path, cutoff)
    assessment = gaps.assess(forecast, market_rows, evaluated_predictions=scored, assessment_cutoff=cutoff)
    stored = []
    normalized_tasks=[]
    available_ids = {forecast['target']['evidence_id']} | {r['evidence_id'] for r in forecast['training_manifest']}
    available_ids.update(row['evidence_id'] for row in source_rows(db_path,forecast['data_cutoff']))
    config_id = forecast['configuration']['evidence_id']
    for task in assessment['research_tasks']:
        draft = dict(task)
        original = set(task.get('evidence_ids',[]))
        if not original.issubset(available_ids | {config_id}):
            raise ValueError('UNKNOWN_RESEARCH_EVIDENCE')
        if config_id in original and not model_run_id:
            draft['evidence_ids']=sorted(original)
            draft['persistence']='NOT_PERSISTED_CONFIGURATION_UNAVAILABLE'
            normalized_tasks.append(draft)
            continue
        draft['evidence_ids'] = sorted(original & available_ids)
        if model_run_id:
            draft['evidence_ids'].append(model_run_id)
        stored.append(memory.record_research_task(db_path, draft))
        normalized_tasks.append(draft)
    assessment['research_tasks'] = normalized_tasks
    assessment['persisted_tasks'] = stored
    assessment['configuration'] = forecast['configuration']
    latest={item['hypothesis_id']:item for item in memory.latest_hypotheses(db_path,now())}
    hypotheses=[]
    for hypothesis in assessment.get('hypotheses',[]):
        draft=dict(hypothesis)
        for field in ('supporting_evidence_ids','contradicting_evidence_ids'):
            original=set(draft.get(field,[]))
            if not original.issubset(available_ids | {config_id}):
                raise ValueError('UNKNOWN_HYPOTHESIS_EVIDENCE')
            if config_id in original and not model_run_id:
                raise ValueError('HYPOTHESIS_CONFIGURATION_NOT_RETAINED')
            draft[field]=sorted(original & available_ids)
            if config_id in original:
                draft[field].append(model_run_id)
        draft['source_id']='cognitive-research'
        previous=latest.get(draft['hypothesis_id'])
        compared=('claim','supporting_evidence_ids','contradicting_evidence_ids','assumptions',
                  'missing_information','next_question','source_id')
        if previous and all(previous.get(key)==draft.get(key) for key in compared):
            draft.update(revision=previous['revision'],record_id=previous['record_id'],duplicate=True)
        else:
            draft['revision']=previous['revision']+1 if previous else 1
            receipt=memory.record_hypothesis(db_path,draft)
            draft.update(record_id=receipt['record_id'],duplicate=receipt['duplicate'])
        hypotheses.append(draft)
    assessment['hypotheses']=hypotheses
    assessment['memory_counts'] = {key:len(value) for key,value in view.items()}
    return assessment
