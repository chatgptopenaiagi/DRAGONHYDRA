"""Time-aware forecast evaluation and explicitly present-knowledge holdouts.

Retrospective records imported today were not available to this system at earlier
match dates. A chronological holdout here trains on older match dates and scores
later dates *using evidence available now*. It is not a historical STRICT_PIT
replay, a persisted historical forecast, or an estimate of live performance.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import math
import re
import statistics

from .. import public_results, research

VERSION = 'cognitive-evaluation/1'
HOLDOUT_MODEL = 'chronological-frequency/1'
OUTCOMES = ('home', 'draw', 'away')


def _utc(value):
    return research._time(value)


def _bound(cutoff):
    when = _utc(cutoff)
    if when > datetime.now(timezone.utc):
        raise ValueError('CUTOFF_AFTER_ACTUAL_TIME')
    return when


def _metric(value, units, ids, formula):
    return {'value':value, 'units':units, 'evidence_ids':sorted(set(ids)),
            'transformation':{'version':VERSION, 'formula':formula}}


def _score(probabilities, outcome):
    if not isinstance(probabilities, dict) or set(probabilities) != set(OUTCOMES):
        raise ValueError('INCOMPLETE_PROBABILITIES')
    probs = {}
    for name, value in probabilities.items():
        if isinstance(value, dict):
            value = value.get('value')
        n = research._number(value)
        if not 0 < n < 1:
            raise ValueError('INVALID_PROBABILITY')
        probs[name] = n
    if abs(sum(probs.values()) - Decimal(1)) > Decimal('1e-12'):
        raise ValueError('PROBABILITIES_NOT_NORMALIZED')
    if outcome not in OUTCOMES:
        raise ValueError('INVALID_OUTCOME')
    brier = sum((float(probs[k]) - float(k == outcome))**2 for k in OUTCOMES)
    log_loss = -math.log(float(probs[outcome]))
    return probs, brier, log_loss


def _summarize(cases, total, cutoff, *, model_version, mode, candidate_ids=()):
    ids = sorted({i for case in cases for i in case['evidence_ids']})
    def aggregate(key, units):
        numbers = [case[key] for case in cases]
        return {'value':statistics.fmean(numbers) if numbers else None,
                'sample_variance':statistics.variance(numbers) if len(numbers)>1 else None,
                'sample_size':len(numbers), 'units':units, 'evidence_ids':ids,
                'transformation':{'version':VERSION,'formula':'arithmetic mean and unbiased sample variance'}}
    calibration = []
    for outcome in OUTCOMES:
        for index in range(5):
            items = [case for case in cases if min(int(case['probabilities'][outcome] * 5),4)==index]
            refs = sorted({i for case in items for i in case['evidence_ids']})
            calibration.append({'outcome':outcome, 'lower_inclusive':index/5, 'upper':(index+1)/5,
                'upper_inclusive':index==4, 'sample_size':len(items),
                'mean_forecast':statistics.fmean(c['probabilities'][outcome] for c in items) if items else None,
                'observed_frequency':statistics.fmean(float(c['actual_outcome']==outcome) for c in items) if items else None,
                'evidence_ids':refs, 'transformation':{'version':VERSION,'formula':'equal-width bin, mean forecast and observed frequency'},
                'quality':'small_sample' if len(items)<20 else 'descriptive'})
    return {'mode':mode,'evaluation_cutoff':cutoff.isoformat(),'model_version':model_version,
            'metrics':{'brier':aggregate('brier','multiclass Brier score'),
                       'log_loss':aggregate('log_loss','natural logarithmic loss'),
                       'accuracy':aggregate('correct','fraction correct')},
            'coverage':{'evaluated':len(cases),'eligible_candidates':total,
                        'fraction':len(cases)/total if total else None,
                        'evidence_ids':sorted(set(ids).union(candidate_ids)),
                        'transformation':{'version':VERSION,'formula':'evaluated forecasts / eligible targets'}},
            'calibration_bins':calibration, 'cases':cases}


def _verify_public(record, cutoff, raw_resolver, cache):
    research._evidence(record, cutoff)
    if record.get('data_origin') not in ('imported_historical','captured_real'):
        raise ValueError('REAL_SOURCE_EVIDENCE_REQUIRED')
    source_hash=record['source_hash']
    if source_hash not in cache:
        raw=raw_resolver(source_hash)
        if not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=source_hash:
            raise ValueError('SOURCE_HASH_MISMATCH')
        try:
            doc=json.loads(raw.decode('utf-8-sig'))
        except (UnicodeError,json.JSONDecodeError):
            raise ValueError('INVALID_SOURCE_BYTES') from None
        if not isinstance(doc,dict) or not isinstance(doc.get('matches'),list):
            raise ValueError('INVALID_SOURCE_BYTES')
        cache[source_hash]=doc
    doc=cache[source_hash]
    match=re.fullmatch(r'\$\.matches\[(\d+)\]',record.get('source_record_path') or '')
    if not match:
        raise ValueError('SOURCE_RECORD_PATH_REQUIRED')
    ordinal=int(match.group(1))
    if ordinal>=len(doc['matches']):
        raise ValueError('SOURCE_RECORD_PATH_INVALID')
    expected=public_results._match(doc.get('name'),doc['matches'][ordinal],ordinal)
    for key in ('fixture_key','competition','event_date','source_local_time','home','away',
                'market_type','period','settlement','home_goals','away_goals','outcome','result_state'):
        if record.get(key)!=expected.get(key):
            raise ValueError('SOURCE_RECORD_MISMATCH')
    if not record.get('source_id') or not record.get('acquisition_id'):
        raise ValueError('SOURCE_ACQUISITION_REQUIRED')
    raw_id=json.dumps([record['source_id'],record['acquisition_id'],ordinal],ensure_ascii=False,
                      sort_keys=True,separators=(',',':')).encode('utf-8')
    if hashlib.sha256(raw_id).hexdigest()!=record['evidence_id']:
        raise ValueError('SOURCE_EVIDENCE_ID_MISMATCH')


def chronological_holdout(rows, cutoff, raw_resolver, *, source_id=None, competition=None,
                          holdout_fraction='0.2', minimum_training=50, smoothing='1'):
    """Evaluate a frequency baseline on later match dates, using today's knowledge.

    The evidence cutoff gates local capture/persistence clocks. Output cases are
    calculations made now from a pre-selected older-date subset. The held-out
    outcomes were already known to the system, so this is a retrospective model
    diagnostic and explicitly not a live, point-in-time backtest.
    """
    decision=_bound(cutoff)
    if not isinstance(rows,list) or not callable(raw_resolver):
        raise ValueError('INVALID_HOLDOUT_INPUT')
    fraction=research._number(holdout_fraction)
    alpha=research._number(smoothing)
    if not 0 < fraction < 1 or not Decimal('1e-12') <= alpha <= Decimal('1e12'):
        raise ValueError('INVALID_HOLDOUT_CONFIGURATION')
    if type(minimum_training) is not int or minimum_training < 1:
        raise ValueError('INVALID_MINIMUM_TRAINING')
    eligible=[]
    cache={}
    scoped=[row for row in rows if isinstance(row,dict) and research._fully_known_before(row,decision)
            and (not source_id or row.get('source_id')==source_id)
            and (not competition or row.get('competition')==competition)]
    ambiguity=public_results.find_ambiguous_fixtures(scoped,decision.isoformat())
    ambiguous_ids={eid for flag in ambiguity for eid in flag['evidence_ids']}
    # An ambiguous unplayed row matters as much as a completed row. Resolve
    # each conflicting claim before allowing it to influence this diagnostic.
    for row in scoped:
        if row.get('evidence_id') in ambiguous_ids:
            _verify_public(row,decision,raw_resolver,cache)
    for row in rows:
        if not isinstance(row,dict) or not research._fully_known_before(row,decision):
            continue
        if source_id and row.get('source_id')!=source_id: continue
        if competition and row.get('competition')!=competition: continue
        if row.get('evidence_id') in ambiguous_ids: continue
        if row.get('outcome') not in OUTCOMES or row.get('result_state')!='available': continue
        try:
            match_day=date.fromisoformat(row.get('event_date'))
        except (TypeError,ValueError):
            raise ValueError('INVALID_EVENT_DATE') from None
        # Do not use an outcome whose source-local event day might not yet be over.
        if match_day+timedelta(days=2) > decision.date(): continue
        _verify_public(row,decision,raw_resolver,cache)
        eligible.append(row)
    scopes={(r['source_id'],r['competition'],r['market_type'],r['period'],r['settlement']) for r in eligible}
    if len(scopes)>1:
        raise ValueError('MULTIPLE_COMPETITION_SCOPES')
    fixtures=set()
    for row in eligible:
        if row['fixture_key'] in fixtures:
            raise ValueError('AMBIGUOUS_FIXTURE_REVISION')
        fixtures.add(row['fixture_key'])
    eligible.sort(key=lambda r:(r['event_date'],r['fixture_key']))
    n=len(eligible)
    split=int(Decimal(n)*(1-fraction))
    heldout=eligible[split:]
    cases=[]
    for target in heldout:
        training=[row for row in eligible if row['event_date'] < target['event_date']]
        if len(training)<minimum_training:
            continue
        ids=[r['evidence_id'] for r in training]+[target['evidence_id']]
        with localcontext() as ctx:
            ctx.prec=34
            denominator=Decimal(len(training))+3*alpha
            values={name:(Decimal(sum(r['outcome']==name for r in training))+alpha)/denominator for name in OUTCOMES}
        probs,brier,log_loss=_score(values,target['outcome'])
        predicted=max(OUTCOMES,key=lambda name:probs[name])
        cases.append({'fixture_key':target['fixture_key'],'competition':target['competition'],
                      'event_date':target['event_date'],'home':target['home'],'away':target['away'],
                      'probabilities':{k:float(v) for k,v in probs.items()},'actual_outcome':target['outcome'],
                      'model_version':HOLDOUT_MODEL,'training_count':len(training),
                      'training_latest_event_date':training[-1]['event_date'],
                      'target_evidence_id':target['evidence_id'],'evidence_ids':sorted(set(ids)),
                      'brier':brier,'log_loss':log_loss,'predicted_outcome':predicted,
                      'correct':int(predicted==target['outcome']),
                      'scoring_transforms':{'brier':'sum((probability - outcome indicator)^2)',
                                            'log_loss':'-ln(probability assigned to actual outcome)',
                                            'accuracy':'argmax prediction; ties resolve home, draw, away'},
                      'transformation':{'version':HOLDOUT_MODEL,
                        'formula':'(earlier-date outcome count + smoothing) / (earlier-date count + 3*smoothing)'}})
    result=_summarize(cases,len(heldout),decision,model_version=HOLDOUT_MODEL,mode='PRESENT_KNOWLEDGE_CHRONOLOGICAL_HOLDOUT',
                      candidate_ids=[row['evidence_id'] for row in heldout])
    result.update(actual_run_time=datetime.now(timezone.utc).isoformat(),dataset_count=n,
                  dataset_evidence_ids=sorted(r['evidence_id'] for r in eligible),
                  quality_flags=ambiguity,
                  excluded_ambiguous_evidence_ids=sorted(ambiguous_ids),
                  source_id=next(iter(scopes))[0] if scopes else source_id,
                  competition=next(iter(scopes))[1] if scopes else competition,
                  configuration={'holdout_fraction':str(fraction),'minimum_training':minimum_training,
                                 'smoothing':str(alpha),'seed':'not applicable; deterministic chronological split'},
                  assumptions=['All inputs were usable by the supplied current cutoff.',
                    'Each fit uses only earlier event dates, including earlier held-out outcomes; same-day matches are excluded.',
                    'Every prediction in this diagnostic is computed now after the historic outcomes were already known.',
                    'This is not a historical STRICT_PIT replay or proof of out-of-sample live performance.'])
    return result


def _record_time(record, cutoff):
    """Validate memory receipt clocks independently of stored domain content."""
    if not isinstance(record,dict):
        raise ValueError('MEMORY_RECORD_REQUIRED')
    times=[_utc(record.get(k)) for k in ('received_at','persisted_at','usable_at')]
    if times != sorted(times) or times[-1] > cutoff:
        raise ValueError('INVALID_MEMORY_AVAILABILITY')
    if not isinstance(record.get('record_id'),str) or not record['record_id']:
        raise ValueError('MEMORY_RECORD_ID_REQUIRED')
    return times[-1]


def _latest_outcome(candidates):
    """Resolve exactly one explicit, nonbranching eligible revision chain."""
    by_id={item['record_id']:item for item in candidates}
    if len(by_id)!=len(candidates):
        return None
    children={}
    for item in candidates:
        parent=item.get('supersedes_record_id')
        if parent:
            if parent not in by_id or parent in children:
                return None
            children[parent]=item['record_id']
    heads=[item for item in candidates if item['record_id'] not in children]
    if len(heads)!=1:
        return None
    seen=set()
    item=heads[0]
    while item:
        if item['record_id'] in seen:
            return None
        seen.add(item['record_id'])
        parent=item.get('supersedes_record_id')
        item=by_id.get(parent) if parent else None
    return heads[0] if len(seen)==len(candidates) else None


def evaluate_observed(memory_view, cutoff):
    """Score actual recorded predictions only after matching results became usable.

    `memory_view` must be the cutoff-filtered immutable memory view. The evaluator
    independently checks all clock boundaries and abstains when fixture mapping,
    outcome revision or pregame timing cannot be established. It never constructs
    an earlier prediction from later-imported results.
    """
    from datetime import time
    decision=_bound(cutoff)
    if not isinstance(memory_view,dict) or not isinstance(memory_view.get('predictions'),list) or not isinstance(memory_view.get('outcomes'),list):
        raise ValueError('MEMORY_VIEW_REQUIRED')
    predictions=[p for p in memory_view['predictions'] if research._fully_known_before(p,decision)]
    # Input order must not select a later rerun over the original prediction.
    # The record ID is a stable, explicit tie-break for identical usable times.
    predictions.sort(key=lambda p:(_utc(p['usable_at']),str(p.get('record_id') or '')))
    outcomes=[o for o in memory_view['outcomes'] if research._fully_known_before(o,decision)]
    by_fixture={}
    for outcome in outcomes:
        _record_time(outcome,decision)
        if not isinstance(outcome.get('fixture_key'),str) or not outcome['fixture_key']:
            raise ValueError('OUTCOME_FIXTURE_REQUIRED')
        by_fixture.setdefault(outcome['fixture_key'],[]).append(outcome)
    groups={}
    missing=[]
    cohort={}
    for pred in predictions:
        pred_available=_record_time(pred,decision)
        for field in ('fixture_key','model_name','model_version','competition','home','away','period','settlement'):
            if not isinstance(pred.get(field),str) or not pred[field]:
                raise ValueError('INCOMPLETE_PREDICTION_RECORD')
        predicted_at=_utc(pred.get('predicted_at'))
        pred_cutoff=_utc(pred.get('decision_cutoff'))
        if pred_cutoff > predicted_at or predicted_at > pred_available:
            raise ValueError('INVALID_PREDICTION_CLOCKS')
        target=pred.get('target_evidence')
        source_id=target.get('source_id') if isinstance(target,dict) else None
        if not isinstance(source_id,str) or not source_id:
            missing.append({'prediction_id':pred['record_id'],'reason':'SOURCE_MAPPING_UNPROVEN'})
            continue
        try:
            event_day=date.fromisoformat(pred.get('event_date'))
        except (TypeError,ValueError):
            missing.append({'prediction_id':pred['record_id'],'reason':'EVENT_DATE_UNAVAILABLE'})
            continue
        # No kickoff timezone is assumed. Select the earliest prediction which
        # can be proved pregame even at the earliest plausible source date.
        earliest=datetime.combine(event_day-timedelta(days=1),time.min,tzinfo=timezone.utc)
        if pred_available>=earliest:
            missing.append({'prediction_id':pred['record_id'],'reason':'PREGAME_TIMING_UNPROVEN'})
            continue
        key=(source_id or '',pred['competition'],pred['period'],pred['settlement'],pred['model_name'],pred['model_version'])
        cohort_key=key+(pred['fixture_key'],)
        if cohort_key in cohort:
            missing.append({'prediction_id':pred['record_id'],'reason':'DUPLICATE_FIXTURE_PREDICTION',
                            'retained_prediction_id':cohort[cohort_key]})
            continue
        cohort[cohort_key]=pred['record_id']
        group=groups.setdefault(key,{'candidates':0,'cases':[],'candidate_ids':[]})
        group['candidates']+=1
        group['candidate_ids'].append(pred['record_id'])
        # Source identities are distinct evaluation scopes. A same-key outcome
        # from a different source must not suppress or corroborate this cohort.
        candidates=[item for item in by_fixture.get(pred['fixture_key'],[])
                    if item.get('source_id') == source_id]
        if not candidates:
            missing.append({'prediction_id':pred['record_id'],'reason':'OUTCOME_UNAVAILABLE'})
            continue
        outcome=_latest_outcome(candidates)
        if outcome is None:
            missing.append({'prediction_id':pred['record_id'],'reason':'AMBIGUOUS_OUTCOME_REVISIONS'})
            continue
        if any(pred.get(k)!=outcome.get(k) for k in ('competition','home','away','event_date','market_type','period','settlement')):
            missing.append({'prediction_id':pred['record_id'],'reason':'FIXTURE_MAPPING_CONFLICT'})
            continue
        if not isinstance(target,dict) or not target.get('source_id') or target['source_id']!=outcome.get('source_id'):
            missing.append({'prediction_id':pred['record_id'],'reason':'SOURCE_MAPPING_UNPROVEN'})
            continue
        if any(item.get('source_id')!=target['source_id'] or
               any(pred.get(k)!=item.get(k) for k in ('competition','home','away','event_date','market_type','period','settlement'))
               for item in candidates):
            missing.append({'prediction_id':pred['record_id'],'reason':'FIXTURE_MAPPING_CONFLICT'})
            continue
        for item in candidates:
            if not isinstance(item.get('source_evidence_id'),str) or not item['source_evidence_id']:
                raise ValueError('OUTCOME_SOURCE_EVIDENCE_REQUIRED')
            if _utc(item.get('source_usable_at')) > _record_time(item,decision):
                raise ValueError('OUTCOME_SOURCE_NOT_YET_USABLE')
        source_usable=_utc(outcome.get('source_usable_at'))
        outcome_available=_record_time(outcome,decision)
        if source_usable>outcome_available:
            raise ValueError('OUTCOME_SOURCE_NOT_YET_USABLE')
        if any(_utc(item.get('source_usable_at'))<=pred_available for item in candidates):
            missing.append({'prediction_id':pred['record_id'],'reason':'OUTCOME_KNOWN_AT_PREDICTION'})
            continue
        if not isinstance(outcome.get('source_evidence_id'),str) or not outcome['source_evidence_id']:
            raise ValueError('OUTCOME_SOURCE_EVIDENCE_REQUIRED')
        probs,brier,logloss=_score(pred.get('probabilities'),outcome.get('outcome'))
        predicted=max(OUTCOMES,key=lambda name:probs[name])
        refs=[pred['record_id'],outcome['record_id'],outcome['source_evidence_id']]
        refs.extend(pred.get('input_evidence_ids') or [])
        if pred.get('target_evidence_id'): refs.append(pred['target_evidence_id'])
        if pred.get('model_run_id'): refs.append(pred['model_run_id'])
        for revision in candidates:
            refs.extend([revision['record_id'],revision['source_evidence_id']])
        group['cases'].append({'fixture_key':pred['fixture_key'],'competition':pred['competition'],
            'model_name':pred['model_name'],'model_version':pred['model_version'],
            'prediction_record_id':pred['record_id'],'outcome_record_id':outcome['record_id'],
            'predicted_at':predicted_at.isoformat(),'prediction_usable_at':pred_available.isoformat(),
            'outcome_source_usable_at':source_usable.isoformat(),'outcome_usable_at':outcome_available.isoformat(),
            'probabilities':{name:float(value) for name,value in probs.items()},'actual_outcome':outcome['outcome'],
            'brier':brier,'log_loss':logloss,'predicted_outcome':predicted,
            'correct':int(predicted==outcome['outcome']),'evidence_ids':sorted(set(refs)),
            'scoring_transforms':{'brier':'sum((probability - outcome indicator)^2)',
                                  'log_loss':'-ln(probability assigned to actual outcome)',
                                  'accuracy':'argmax prediction; ties resolve home, draw, away'},
            'transformation':{'version':VERSION,'formula':'recorded forecast scored after eligible source outcome'}})
    reports=[]
    for (source_id,league,period,settlement,name,version),group in sorted(groups.items()):
        info=_summarize(group['cases'],group['candidates'],decision,model_version=version,
                        mode='OPERATIONAL_RECORDED_PREDICTIONS',candidate_ids=group['candidate_ids'])
        info.update(competition=league,model_name=name,
                    evaluation_scope={'source_id':source_id,'competition':league,'period':period,'settlement':settlement})
        reports.append(info)
    return {'mode':'OPERATIONAL_RECORDED_PREDICTIONS','evaluation_cutoff':decision.isoformat(),
            'actual_run_time':datetime.now(timezone.utc).isoformat(), 'groups':reports,
            'eligible_prediction_count':len(predictions),'cohort_prediction_count':len(cohort),
            'cohort_policy':'earliest eligible pregame prediction per source, market scope, model version and fixture; record ID breaks equal-time ties',
            'eligible_outcome_count':len(outcomes),
            'unscored':missing,'limitations':['Only stored eligible predictions with later usable, unambiguous outcomes are scored.',
                'Receipt-visibility precision remains subject to the storage adapter evidence.']}
