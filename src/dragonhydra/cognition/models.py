"""Deterministic, evidence-linked football probability research models.

All real-data inputs cross the existing verified as-of result/fixture boundary.
The live forecast is computed now, not asserted to have existed in the past.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from typing import TypedDict

from .. import research

VERSION = 'football-models/1'
NAMES = ('frequency', 'poisson_goals', 'elo', 'recency')
OUTCOMES = ('home', 'draw', 'away')




class ScorelineGrid(TypedDict):
    axes: dict[str, list[int]]
    probabilities: list[list[float]]
    unit: str
    evidence_ids: list[str]
    normalization: str
    omitted_mass_before_normalization: float
    transformation: dict[str, str]

def _finite(value, name, low, high):
    if isinstance(value, bool):
        raise ValueError('INVALID_' + name.upper())
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('INVALID_' + name.upper()) from None
    if not math.isfinite(n) or not low <= n <= high:
        raise ValueError('INVALID_' + name.upper())
    return n


def _integer(value, name, low, high):
    n = _finite(value, name, low, high)
    if n != int(n):
        raise ValueError('INVALID_' + name.upper())
    return int(n)


def poisson_distribution(mean, max_goals=40):
    """Return probabilities for 0..max_goals and explicit remaining tail."""
    rate = _finite(mean, 'goal_rate', 0, 20)
    limit = _integer(max_goals, 'max_goals', 1, 100)
    probs = [math.exp(-rate)]
    for n in range(1, limit+1):
        probs.append(probs[-1] * rate / n)
    tail = max(0.0, 1.0 - math.fsum(probs))
    return probs, tail


def _metric(value, unit, ids, formula, **extra):
    return {'value': value, 'unit': unit, 'evidence_ids': sorted(set(ids)),
            'transformation': {'version': VERSION, 'formula': formula}, **extra}


def _distribution(values, ids, formula):
    if set(values) != set(OUTCOMES):
        raise ValueError('INCOMPLETE_DISTRIBUTION')
    if any(not math.isfinite(values[k]) or values[k] < 0 for k in OUTCOMES):
        raise ValueError('INVALID_DISTRIBUTION')
    total = math.fsum(values.values())
    if total <= 0:
        raise ValueError('EMPTY_DISTRIBUTION')
    return {k: _metric(values[k]/total, 'probability fraction', ids,
                       formula + '; normalize numerical rounding') for k in OUTCOMES}


def _config(raw):
    if raw is not None and not isinstance(raw, dict):
        raise ValueError('INVALID_MODEL_CONFIGURATION')
    values = {'minimum_results':5, 'smoothing':1.0, 'goal_shrinkage':5.0,
              'recency_half_life_days':90.0, 'elo_initial':1500.0, 'elo_k':20.0,
              'elo_home_advantage':55.0, 'max_goals':40, 'max_omitted_mass':1e-9}
    supplied = raw or {}
    if set(supplied) - set(values):
        raise ValueError('UNKNOWN_MODEL_CONFIGURATION')
    values.update(supplied)
    values['minimum_results'] = _integer(values['minimum_results'], 'minimum_results', 1, 100000)
    values['smoothing'] = _finite(values['smoothing'], 'smoothing', 1e-12, 1e12)
    values['goal_shrinkage'] = _finite(values['goal_shrinkage'], 'goal_shrinkage', 0.000001, 100000)
    values['recency_half_life_days'] = _finite(values['recency_half_life_days'], 'recency_half_life_days', 1, 36500)
    values['elo_initial'] = _finite(values['elo_initial'], 'elo_initial', 0, 10000)
    values['elo_k'] = _finite(values['elo_k'], 'elo_k', 0, 1000)
    values['elo_home_advantage'] = _finite(values['elo_home_advantage'], 'elo_home_advantage', -1000, 1000)
    values['max_goals'] = _integer(values['max_goals'], 'max_goals', 2, 100)
    values['max_omitted_mass'] = _finite(values['max_omitted_mass'], 'max_omitted_mass', 0, 1e-5)
    return values


def _poisson(rows, target, ids, cfg):
    """Shrink team-specific scored/conceded averages toward league means."""
    if len(rows) < cfg['minimum_results']:
        return {'available':False, 'reason':'INSUFFICIENT_RESULTS'}
    home_mean = math.fsum(r['home_goals'] for r in rows)/len(rows)
    away_mean = math.fsum(r['away_goals'] for r in rows)/len(rows)
    home_rows = [r for r in rows if r['home'] == target['home']]
    away_rows = [r for r in rows if r['away'] == target['away']]
    k = cfg['goal_shrinkage']
    home_attack = (math.fsum(r['home_goals'] for r in home_rows) + k*home_mean)/(len(home_rows)+k)
    away_conceded = (math.fsum(r['home_goals'] for r in away_rows) + k*home_mean)/(len(away_rows)+k)
    away_attack = (math.fsum(r['away_goals'] for r in away_rows) + k*away_mean)/(len(away_rows)+k)
    home_conceded = (math.fsum(r['away_goals'] for r in home_rows) + k*away_mean)/(len(home_rows)+k)
    lh, la = (home_attack + away_conceded)/2, (away_attack + home_conceded)/2
    if lh > 20 or la > 20:
        return {'available':False,'reason':'GOAL_RATE_OUTSIDE_IMPLEMENTED_RANGE',
                'goal_rate_home':_metric(lh,'goals per match',ids,'mean of shrunken home attack and away conceded averages'),
                'goal_rate_away':_metric(la,'goals per match',ids,'mean of shrunken away attack and home conceded averages')}
    hp, ht = poisson_distribution(lh, cfg['max_goals'])
    ap, at = poisson_distribution(la, cfg['max_goals'])
    coverage = math.fsum(hp)*math.fsum(ap)
    omitted = max(0.0, 1.0-coverage)
    if omitted > cfg['max_omitted_mass'] or coverage <= 0:
        return {'available':False, 'reason':'POISSON_TAIL_EXCEEDS_TOLERANCE',
                'omitted_mass':_metric(omitted,'probability fraction',ids,'1 - included Poisson mass')}
    outcomes = {k:0.0 for k in OUTCOMES}
    over = under = btts = 0.0
    scores = []
    grid = []
    for h, ph in enumerate(hp):
        grid_row = []
        for a, pa in enumerate(ap):
            mass = ph*pa/coverage
            outcomes['home' if h>a else 'away' if a>h else 'draw'] += mass
            if h+a >= 3:
                over += mass
            else:
                under += mass
            if h and a:
                btts += mass
            scores.append((mass,h,a))
            grid_row.append(mass)
        grid.append(grid_row)
    scores.sort(key=lambda v:(-v[0],v[1],v[2]))
    definition='Poisson independent goals with shrunken same-venue scoring and conceded rates; finite grid normalized by covered mass'
    grid_metric: ScorelineGrid = {'axes':{'home_goals':list(range(len(hp))), 'away_goals':list(range(len(ap)))},
                                  'probabilities':grid, 'unit':'probability fraction', 'evidence_ids':sorted(set(ids)),
                                  'normalization':'finite-grid probabilities divided by included joint probability mass',
                                  'omitted_mass_before_normalization':omitted,
                                  'transformation':{'version':VERSION,'formula':definition}}
    return {'available':True, 'probabilities':_distribution(outcomes,ids,definition),
            'goal_rate_home':_metric(lh,'goals per match',ids,'mean of shrunken home attack and away conceded averages'),
            'goal_rate_away':_metric(la,'goals per match',ids,'mean of shrunken away attack and home conceded averages'),
            'totals_2_5':{'over':_metric(over,'probability fraction',ids,definition+'; home+away >= 3'),
                          'under':_metric(under,'probability fraction',ids,definition+'; home+away <= 2')},
            'both_teams_to_score':{'yes':_metric(btts,'probability fraction',ids,definition+'; home>0 and away>0'),
                                   'no':_metric(1-btts,'probability fraction',ids,definition+'; complement')},
            'scorelines':[{'home_goals':h,'away_goals':a,'probability':_metric(p,'probability fraction',ids,definition)} for p,h,a in scores[:5]],
            'scoreline_grid':grid_metric,

            'omitted_mass':_metric(omitted,'probability fraction',ids,'1 - included finite-grid Poisson mass'),
            'team_sample_counts':{'home_venue':_metric(len(home_rows),'matches',ids,'count exact same-venue home team matches'),
                                  'away_venue':_metric(len(away_rows),'matches',ids,'count exact same-venue away team matches')},
            'quality_flags':(['HOME_VENUE_HISTORY_MISSING'] if not home_rows else []) +
                            (['AWAY_VENUE_HISTORY_MISSING'] if not away_rows else []),
            'assumptions':['independent goal counts','rates estimated from match goals, not shot-derived xG',
                           'same-venue team rates shrink toward league means']}


def _recency(rows, cutoff, ids, cfg):
    if len(rows) < cfg['minimum_results']:
        return {'available':False, 'reason':'INSUFFICIENT_RESULTS'}
    day = research._time(cutoff).date()
    counts = {name:cfg['smoothing'] for name in OUTCOMES}
    for row in rows:
        age=(day-date.fromisoformat(row['event_date'])).days
        if age < 0:
            raise ValueError('FUTURE_RESULT')
        counts[row['outcome']] += math.exp(-math.log(2)*age/cfg['recency_half_life_days'])
    return {'available':True, 'probabilities':_distribution(counts,ids,
            'exponentially age-weighted same-competition outcomes plus per-outcome smoothing'),
            'half_life_days':cfg['recency_half_life_days'],
            'scope':'league-wide outcome frequencies, not team-specific form',
            'age_basis':'cutoff UTC date minus source event date; source timezone is unknown'}


def _elo_expectation(home_rating, away_rating, advantage):
    # Stable logistic form prevents overflow for extreme but finite ratings.
    z=(home_rating-away_rating+advantage)*math.log(10)/400
    if z >= 0:
        return 1/(1+math.exp(-z))
    expz=math.exp(z)
    return expz/(1+expz)

def _elo(rows, target, freq, ids, cfg):
    if len(rows) < cfg['minimum_results']:
        return {'available':False,'reason':'INSUFFICIENT_RESULTS'}
    ratings = defaultdict(lambda:cfg['elo_initial'])
    appearances=defaultdict(int)
    by_day=defaultdict(list)
    for row in rows:
        by_day[row['event_date']].append(row)
    for day in sorted(by_day):
        changes=defaultdict(float)
        for row in sorted(by_day[day], key=lambda x:x['fixture_key']):
            home, away=row['home'],row['away']
            expectation=_elo_expectation(ratings[home],ratings[away],cfg['elo_home_advantage'])
            actual=1.0 if row['outcome']=='home' else 0.5 if row['outcome']=='draw' else 0.0
            delta=cfg['elo_k']*(actual-expectation)
            changes[home] += delta
            changes[away] -= delta
            appearances[home] += 1
            appearances[away] += 1
        # Source provides dates but no reliable ordering within a day.
        for team,delta in changes.items():
            ratings[team] += delta
    home,away=target['home'],target['away']
    if not appearances[home] or not appearances[away]:
        return {'available':False,'reason':'TEAM_HISTORY_UNAVAILABLE',
                'team_sample_counts':{'home':_metric(appearances[home],'matches',ids,'count eligible home-team appearances'),
                                      'away':_metric(appearances[away],'matches',ids,'count eligible away-team appearances')}}
    expectation=_elo_expectation(ratings[home],ratings[away],cfg['elo_home_advantage'])
    draw=float(freq['probabilities']['draw']['value'])
    # Heuristic derives draw rate from frequency model; it is not independent.
    values={'home':(1-draw)*expectation,'draw':draw,'away':(1-draw)*(1-expectation)}
    return {'available':True,'probabilities':_distribution(values,ids,
            'same-day batched Elo score share with frequency-model draw share'),
            'home_rating':_metric(ratings[home],'Elo points',ids,'sequential daily-batched Elo updates'),
            'away_rating':_metric(ratings[away],'Elo points',ids,'sequential daily-batched Elo updates'),
            'team_sample_counts':{'home':_metric(appearances[home],'matches',ids,'count eligible home-team appearances'),
                                  'away':_metric(appearances[away],'matches',ids,'count eligible away-team appearances')},
            'assumptions':['draw share borrowed from frequency model; model outputs are not independent']}


def _weights(models, target, cutoff, performance_records, performance_resolver):
    available=[name for name in NAMES if models[name]['available']]
    if not available:
        return {}, 'NO_AVAILABLE_MODELS', []
    supplied=performance_records or []
    if not isinstance(supplied, list):
        raise ValueError('INVALID_PERFORMANCE_RECORDS')
    decision=research._time(cutoff)
    # Ineligible future records are ignored completely, including their content.
    eligible=[r for r in supplied if research._known_before(r,decision)]
    equal={name:1/len(available) for name in available}
    if not eligible:
        return equal,'EQUAL_WEIGHTS_NO_ELIGIBLE_EVALUATION',[]
    if not callable(performance_resolver):
        return equal,'EQUAL_WEIGHTS_EVALUATION_UNVERIFIED',[]
    weights, retained, metric_name = {}, {}, None

    def resolve(eid, at, cached=None):
        if not isinstance(eid,str) or not eid:
            raise ValueError('PERFORMANCE_EVIDENCE_ID_REQUIRED')
        saved=cached if cached is not None else performance_resolver(eid)
        if not isinstance(saved,dict) or saved.get('evidence_id') != eid:
            raise ValueError('PERFORMANCE_EVIDENCE_UNRESOLVED')
        research._evidence(saved,at)
        if target.get('data_origin') in ('captured_real','imported_historical') and saved.get('data_origin') == 'synthetic':
            raise ValueError('SYNTHETIC_EVALUATION_FOR_REAL_TARGET')
        if 'source_raw' not in saved:
            raise ValueError('PERFORMANCE_RAW_EVIDENCE_REQUIRED')
        if eid in retained and retained[eid] != saved:
            raise ValueError('CONFLICTING_EVIDENCE_ID')
        retained[eid]=saved
        return saved

    for item in eligible:
        eid=item.get('evidence_id')
        candidate=performance_resolver(eid)
        # The retained record's own clock is authoritative; an incorrect pointer
        # must not let a post-cutoff record influence or disrupt earlier replay.
        if candidate is None:
            continue  # Unresolved references are never admitted as evidence.
        if isinstance(candidate,dict) and not research._fully_known_before(candidate,decision):
            continue
        saved=resolve(eid,decision,cached=candidate)
        try:
            data=json.loads(saved['source_raw'])
        except (ValueError,TypeError):
            raise ValueError('INVALID_PERFORMANCE_EVIDENCE') from None
        if not isinstance(data,dict) or data.get('model') not in NAMES or data.get('model_version') != VERSION:
            raise ValueError('INVALID_PERFORMANCE_EVIDENCE')
        eval_end=research._time(data.get('evaluation_end'))
        if eval_end > decision or eval_end > research._time(saved['usable_at']):
            raise ValueError('EVALUATION_AFTER_CUTOFF')
        scope=data.get('evaluation_scope')
        if not isinstance(scope,dict) or any(scope.get(k) != target.get(k) for k in ('source_id','competition','period','settlement')):
            raise ValueError('EVALUATION_SCOPE_MISMATCH')
        metric=data.get('metric')
        if metric not in ('brier','log_loss') or (metric_name is not None and metric != metric_name):
            raise ValueError('INCOMPATIBLE_EVALUATION_METRIC')
        metric_name=metric
        _integer(data.get('sample_size'),'sample_size',1,100000000)
        loss=_finite(data.get('loss'),'evaluation_loss',0,1e9)
        support=data.get('supporting_evidence_ids')
        if not isinstance(support,list) or not support or len(set(support)) != len(support):
            raise ValueError('EVALUATION_LINEAGE_REQUIRED')
        for support_id in support:
            resolve(support_id,eval_end)
        name=data['model']
        if name in weights:
            raise ValueError('DUPLICATE_MODEL_WEIGHT')
        # Lower proper loss implies a larger heuristic weight; report the rule.
        weights[name]=1/max(loss,1e-12)
    evidence=[retained[k] for k in sorted(retained)]
    if not weights:
        return equal,'EQUAL_WEIGHTS_NO_ELIGIBLE_EVALUATION',[]
    if any(name not in weights for name in available) or not math.fsum(weights[name] for name in available):
        return equal,'EQUAL_WEIGHTS_INCOMPLETE_EVALUATION',evidence
    total=math.fsum(weights[name] for name in available)
    return {name:weights[name]/total for name in available},'EVALUATION_WEIGHTS',evidence

def forecast(rows, target, cutoff, raw_resolver, *, config=None, performance_records=None, performance_resolver=None):
    """Compute independent, deterministic candidate models and a transparent ensemble.

    The resolver supplies retained raw source bytes by SHA-256. The optional
    performance resolver must return the authoritative retained record by evidence
    ID; unverified or unavailable weights are never used.
    """
    cfg=_config(config)
    prior=research.current_frequency_prior(rows,target,cutoff,raw_resolver,
                                           smoothing=str(cfg['smoothing']),minimum_training=1)
    history=prior['training_manifest']
    actual_started=datetime.now(timezone.utc)
    config_identity=json.dumps(cfg,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    config_hash=hashlib.sha256(config_identity).hexdigest()
    config_evidence={'evidence_id':'config:'+config_hash,'source_id':'model_configuration',
                     'source_hash':config_hash,'values':cfg,'recorded_at':actual_started.isoformat(),
                     'data_origin':'configuration','transformation':{'version':VERSION,'formula':'canonical model parameters'}}
    ids=[target['evidence_id']]+[r['evidence_id'] for r in history]+[config_evidence['evidence_id']]
    if prior['abstained']:
        freq={'available':False,'reason':prior['reason']}
    else:
        freq={'available':True,'probabilities':_distribution(
            {name:float(prior['probabilities'][name]['value']) for name in OUTCOMES},ids,
            'same-source and same-competition outcome counts with per-outcome smoothing')}
    models={'frequency':freq,
            'poisson_goals':_poisson(history,target,ids,cfg),
            'elo':_elo(history,target,freq,ids,cfg) if freq['available'] else {'available':False,'reason':'FREQUENCY_PRIOR_UNAVAILABLE'},
            'recency':_recency(history,cutoff,ids,cfg)}
    weights, mode, performance_evidence = _weights(models,target,cutoff,performance_records,performance_resolver)
    ensemble=None
    if weights:
        values={name:math.fsum(weights[m]*models[m]['probabilities'][name]['value'] for m in weights) for name in OUTCOMES}
        ensemble_ids=ids+[e['evidence_id'] for e in performance_evidence]
        ensemble={'probabilities':_distribution(values,ensemble_ids,'weighted mean of available model probability estimates'),
                  'weights':weights,'weight_mode':mode,
                  'weight_provenance':{'evidence_ids':ensemble_ids, 'transformation': {'version':VERSION,
                    'formula':'equal weights when evaluation unavailable; otherwise normalized inverse held-out proper loss (floor 1e-12)'}},
                  'assumptions':['Models share training evidence and are not independent.',
                                 'Weights are descriptive choices; a common source can contain shared errors.',
                                 'Resolved evaluation losses are not independently recomputed in this forecast.']}
    actual=datetime.now(timezone.utc)
    # Fail rather than assert that a target remained pregame if computation crossed the safe boundary.
    from datetime import timedelta, time
    target_boundary=datetime.combine(date.fromisoformat(target['event_date'])-timedelta(days=1), time.min,tzinfo=timezone.utc)
    if actual >= target_boundary:
        raise ValueError('FUTURE_FIXTURE_TIME_UNCERTAIN')
    unavailable=[{'model':name,'reason':model.get('reason')} for name,model in models.items() if not model['available']]
    tasks=list(prior.get('research_tasks', [])) + [{'gap':item['reason'],'question':'Can additional eligible, identity-verified results be obtained?',
            'permitted_source':'documented or user-supplied source','priority_rationale':'Insufficient evidence prevents this model.',
            'expected_evidence':'dated, provenance-linked fixture and result records',
            'budget':'one bounded source review','stopping_condition':'eligible evidence obtained or source unavailable',
            'evidence_ids':ids} for item in unavailable]
    for code in models['poisson_goals'].get('quality_flags', []):
        tasks.append({'gap':code,'question':'Can exact same-venue historical team results be captured?',
                      'permitted_source':'documented or user-supplied source',
                      'priority_rationale':'League averages substitute for a missing team venue sample.',
                      'expected_evidence':'identity-verified dated match results','budget':'one bounded source review',
                      'stopping_condition':'eligible records obtained or source unavailable','evidence_ids':ids})
    if mode != 'EVALUATION_WEIGHTS':
        tasks.append({'gap':'ELIGIBLE_MODEL_EVALUATION_UNAVAILABLE',
                      'question':'Can chronological out-of-sample evaluation evidence be acquired for each model?',
                      'permitted_source':'persisted evaluation records','priority_rationale':'Evidence is needed for performance-based weights.',
                      'expected_evidence':'cutoff-eligible retained evaluation report',
                      'budget':'one bounded evaluation','stopping_condition':'all model evidence validated or unavailable',
                      'evidence_ids':ids})
    return {'data_cutoff':prior['data_cutoff'], 'decision_cutoff':actual.isoformat(),
            'actual_run_time':actual.isoformat(), 'model_usable_at':actual.isoformat(), 'model_persisted_at':None,
            'clock_semantics':'Inputs eligible at data cutoff; model output and decision become usable at actual computation time.',
            'model_status':'ephemeral_current_calculation','model_version':VERSION,
            'target':target,'training_manifest':history,'training_count':len(history),
            'quality_flags':prior.get('quality_flags',[]),
            'quarantined_evidence':prior.get('quarantined_evidence',[]),
            'configuration':config_evidence,'models':models,'ensemble':ensemble,
            'performance_evidence':performance_evidence,'abstained':ensemble is None,
            'uncertainty_summary':{'items':['All estimates are uncalibrated research models; no predictive improvement is established.',
                      'Source fixture times have no verified UTC timezone.',
                      'Forecast is computed now from eligible data, not a retained historical prediction.'],
                      'abstained':ensemble is None,'unavailable_models':unavailable},
            'research_tasks':tasks,'stop_reason':'REPORT_COMPLETE' if ensemble else 'INSUFFICIENT_EVIDENCE'}














