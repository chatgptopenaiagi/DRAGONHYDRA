"""Evidence-linked probability, value and backtesting research calculations.

These calculations operate on explicitly supplied evidence and assumptions. They
never place bets. The caller retains the source records identified by hashes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math
import random
import re
import statistics

from .market_signals import convert_odds

VERSION = 'research/1'
MODEL_VERSION = 'smoothed-frequency/1'
SCOPE = ('event_id', 'competition', 'home', 'away', 'market_type', 'period',
         'outcome', 'line', 'status', 'settlement')
OUTCOMES = ('home', 'draw', 'away')


def _time(value):
    if not isinstance(value, str):
        raise ValueError('TIMESTAMP_REQUIRED')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('INVALID_TIMESTAMP') from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('NAIVE_TIMESTAMP')
    return parsed.astimezone(timezone.utc)


def _number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('INVALID_NUMBER')
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('INVALID_NUMBER') from None
    if not n.is_finite():
        raise ValueError('NONFINITE_NUMBER')
    return n


def _evidence(item, cutoff):
    if not isinstance(item, dict):
        raise ValueError('MISSING_EVIDENCE')
    for name in ('evidence_id', 'source_id', 'data_origin'):
        if not isinstance(item.get(name), str) or not item[name].strip():
            raise ValueError('MISSING_' + name.upper())
    if item['data_origin'] not in ('synthetic', 'captured_real', 'imported_historical', 'user_supplied', 'model_state'):
        raise ValueError('INVALID_DATA_ORIGIN')
    if not isinstance(item.get('source_hash'), str) or not re.fullmatch(r'[0-9a-f]{64}', item['source_hash']):
        raise ValueError('INVALID_SOURCE_HASH')
    received = _time(item.get('received_at'))
    persisted = _time(item.get('persisted_at'))
    usable = _time(item.get('usable_at'))
    published = item.get('source_published_at', item.get('published_at'))
    if published is not None and _time(published) > received:
        raise ValueError('PUBLICATION_AFTER_RECEIPT')
    if not received <= persisted <= usable:
        raise ValueError('INVALID_AVAILABILITY')
    if usable > cutoff:
        raise ValueError('EVIDENCE_AFTER_CUTOFF')
    if item.get('source_raw') is not None:
        raw = item['source_raw']
        if not isinstance(raw, str) or hashlib.sha256(raw.encode('utf-8')).hexdigest() != item['source_hash']:
            raise ValueError('SOURCE_HASH_MISMATCH')
    return usable


def _validate_scope(scope):
    for key in SCOPE:
        if key == 'line':
            if key not in scope:
                raise ValueError('MISSING_MARKET_LINE')
        elif not isinstance(scope.get(key), str) or not scope[key].strip():
            raise ValueError('MISSING_MARKET_SCOPE')
    if scope['home'].casefold() == scope['away'].casefold():
        raise ValueError('AMBIGUOUS_PARTICIPANTS')
    if scope['status'] not in ('pregame', 'live'):
        raise ValueError('INVALID_MARKET_STATUS')
    if scope['line'] is not None:
        _number(scope['line'])


def _refs(records):
    result = {}
    for obj in records:
        key = obj['evidence_id']
        reference = {k: obj.get(k) for k in ('evidence_id', 'source_id', 'source_hash', 'data_origin',
                                               'source_published_at', 'received_at', 'persisted_at', 'usable_at')}
        if obj.get('source_raw') is not None:
            reference['source_raw'] = obj['source_raw']
        if key in result and result[key] != reference:
            raise ValueError('CONFLICTING_EVIDENCE_ID')
        result[key] = reference
    return [result[k] for k in sorted(result)]


def _metric(value, unit, evidence_ids, formula, **extra):
    return {'value': str(value), 'unit': unit, 'evidence_ids': sorted(set(evidence_ids)),
            'transformation': {'version': VERSION, 'formula': formula}, **extra}


def _model_inputs(estimate, cutoff):
    model_time = _evidence(estimate, cutoff)
    if not isinstance(estimate.get('model_version'), str) or not estimate['model_version']:
        raise ValueError('MODEL_VERSION_REQUIRED')
    inputs = estimate.get('input_evidence')
    if not isinstance(inputs, list):
        raise ValueError('MODEL_LINEAGE_REQUIRED')
    if not inputs and estimate['data_origin'] != 'user_supplied':
        raise ValueError('MODEL_LINEAGE_REQUIRED')
    for item in inputs:
        if _evidence(item, cutoff) > model_time:
            raise ValueError('MODEL_INPUT_AFTER_MODEL')
    return inputs


def assess(quote, estimate, cutoff, *, fraction='0.25', cap='0.02', bankroll='1000',
           trials=1000, steps=20, seed=42, max_quote_age_seconds=600):
    """Calculate evidence-linked expected return, fractional Kelly and IID paths.

    Parameters are run-time scenario assumptions, recorded with actual run time;
    they are not represented as historical facts or a historical recommendation.
    """
    decision = _time(cutoff)
    _validate_scope(quote)
    _validate_scope(estimate)
    if any(quote.get(k) != estimate.get(k) for k in SCOPE):
        raise ValueError('INCOMPATIBLE_MARKET_SCOPE')
    if quote['status'] == 'live' and (not quote.get('game_state_id') or
                                      quote.get('game_state_id') != estimate.get('game_state_id')):
        raise ValueError('LIVE_GAME_STATE_REQUIRED')
    _evidence(quote, decision)
    inputs = _model_inputs(estimate, decision)
    probability = _number(estimate.get('probability'))
    if not 0 <= probability <= 1:
        raise ValueError('INVALID_PROBABILITY')
    price = convert_odds(quote.get('odds_original'), quote.get('odds_format'))
    f, limit, starting = _number(fraction), _number(cap), _number(bankroll)
    if not 0 <= f <= 1 or not 0 <= limit <= 1 or starting <= 0:
        raise ValueError('INVALID_RISK_CONFIGURATION')
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (trials, steps, seed, max_quote_age_seconds)):
        raise ValueError('INVALID_SIMULATION_CONFIGURATION')
    if not (1 <= trials <= 10000 and 1 <= steps <= 10000 and 0 <= seed <= (2**63-1)
            and trials * steps <= 1_000_000 and max_quote_age_seconds >= 0):
        raise ValueError('INVALID_SIMULATION_CONFIGURATION')
    records = [quote, estimate] + inputs
    manifest = _refs(records)
    ids = [r['evidence_id'] for r in records]
    now = datetime.now(timezone.utc).isoformat()
    config = {'source_id': 'runtime_configuration', 'recorded_at': now,
              'fractional_kelly': str(f), 'kelly_cap': str(limit), 'starting_bankroll': str(starting),
              'trials': trials, 'steps': steps, 'seed': seed,
              'max_quote_age_seconds': max_quote_age_seconds, 'simulation': 'IID Bernoulli',
              'rng': 'Python random.Random.getrandbits(53)',
              'note': 'Configuration is an analysis-time scenario, not a historical observation.'}
    config_bytes = json.dumps({k: v for k, v in config.items() if k != 'recorded_at'}, sort_keys=True, separators=(',', ':')).encode()
    config['evidence_id'] = 'config:' + hashlib.sha256(config_bytes).hexdigest()
    config['source_hash'] = hashlib.sha256(config_bytes).hexdigest()
    calc_ids = ids + [config['evidence_id']]
    with localcontext() as ctx:
        ctx.prec = 34
        expected = probability * price - 1
        raw_kelly = expected / (price - 1)
        stake = min(limit, max(Decimal(0), raw_kelly) * f)
        rng = random.Random(seed)
        endings, drawdowns, ruined = [], [], 0
        for _ in range(trials):
            bank, peak, drawdown = starting, starting, Decimal(0)
            for _ in range(steps):
                bet = bank * stake
                won = Decimal(rng.getrandbits(53)) < probability * Decimal(2**53)
                bank = bank + bet * (price - 1) if won else bank - bet
                peak = max(peak, bank)
                if peak:
                    drawdown = max(drawdown, (peak - bank) / peak)
            endings.append(bank)
            drawdowns.append(drawdown)
            if bank == 0:
                ruined += 1
        mean = sum(endings, Decimal(0)) / trials
        variance = sum(((x - mean) ** 2 for x in endings), Decimal(0)) / trials
        quote_clock = quote.get('effective_market_received_at') or quote['received_at']
        age = Decimal(str((decision - _time(quote_clock)).total_seconds()))
        if age < 0:
            raise ValueError('QUOTE_TIME_AFTER_CUTOFF')
        unknown_source_time = quote['data_origin'] in ('captured_real', 'imported_historical')
        age_metric = ({'value': None, 'unit': 'seconds', 'evidence_ids': [quote['evidence_id']],
                       'reason': 'SOURCE_QUOTE_TIME_UNKNOWN', 'transformation': {'version': VERSION}}
                      if unknown_source_time else _metric(age, 'seconds since simulated capture', [quote['evidence_id']],
                                                         'decision_cutoff - original_quote_received_at'))
        capture_age = _metric(age, 'seconds since capture', [quote['evidence_id']],
                              'decision_cutoff - original_quote_received_at',
                              interpretation='The provider quote can be older than the capture.')
        flags = ['SOURCE_QUOTE_TIME_UNKNOWN'] if unknown_source_time else []
        if age > max_quote_age_seconds:
            flags.append('STALE_CAPTURE')
        return {'decision_cutoff': decision.isoformat(), 'actual_run_time': now,
                'scope': {k: quote[k] for k in SCOPE},
                'model_version': estimate['model_version'],
                'input_values': {'model_probability': str(probability), 'decimal_odds': str(price),
                                 'odds_original': quote['odds_original'], 'odds_format': quote['odds_format']},
                'evidence_manifest': manifest, 'scenario_configuration': config,
                'quote_age_seconds': age_metric, 'capture_age_seconds': capture_age,
                'quality_flags': flags,
                'expected_net_return_per_unit': _metric(expected, 'stake fraction', ids, 'p * decimal_odds - 1'),
                'raw_kelly': _metric(raw_kelly, 'bankroll fraction', ids, '(p * decimal_odds - 1) / (decimal_odds - 1)'),
                'fractional_capped_kelly': _metric(stake, 'bankroll fraction', calc_ids, 'min(cap, max(0, raw_kelly) * fraction)'),
                'simulation': {
                    'mean_final_bankroll': _metric(mean, 'bankroll units', calc_ids, 'mean of final balances'),
                    'variance_final_bankroll': _metric(variance, 'bankroll units squared', calc_ids, 'population variance of final balances'),
                    'mean_max_drawdown': _metric(sum(drawdowns, Decimal(0)) / trials, 'fraction', calc_ids, 'mean of peak-to-trough maxima'),
                    'zero_balance_frequency': _metric(Decimal(ruined) / trials, 'fraction', calc_ids, 'zero balance trials / trials')},
                'assumptions': ['Model probability is supplied, not established by these calculations.',
                                'IID outcomes, unchanged quote and probability, fractional stakes; no fees, limits or correlations.',
                                'Simulated outcomes use a 53-bit random threshold.'],
                'interpretation': 'Conditional research scenario; it does not establish an edge or executable quote.'}


def _known_before(item, cutoff):
    if not isinstance(item, dict):
        return False
    try:
        return _time(item.get('usable_at')) <= cutoff
    except ValueError:
        return False


def frequency_prediction(history, target, cutoff, *, smoothing='1', minimum_training=1):
    """Synthetic, retrospective 1X2 baseline with cutoff-isolated training inputs.

    Prediction and fixture clocks are a declared simulated research replay. Real
    retrospective predictions require separately persisted model-state evidence.
    """
    decision = _time(cutoff)
    _validate_scope(target)
    _evidence(target, decision)
    if target['data_origin'] != 'synthetic':
        raise ValueError('SYNTHETIC_REPLAY_REQUIRED')
    if target['market_type'].lower() != '1x2':
        raise ValueError('UNSUPPORTED_MARKET')
    target_event = _time(target.get('event_at'))
    if decision > target_event:
        raise ValueError('PREDICTION_AFTER_EVENT')
    alpha = _number(smoothing)
    if alpha < Decimal('1e-12') or alpha > Decimal('1e12') or isinstance(minimum_training, bool) or not isinstance(minimum_training, int) or minimum_training < 1:
        raise ValueError('INVALID_MODEL_CONFIGURATION')
    if not isinstance(history, list):
        raise ValueError('HISTORY_REQUIRED')
    eligible, seen = [], set()
    for row in history:
        # No result value is interpreted until its own availability is eligible.
        if not _fully_known_before(row, decision):
            continue
        _evidence(row, decision)
        if row['data_origin'] != 'synthetic':
            raise ValueError('SYNTHETIC_REPLAY_REQUIRED')
        if _time(row.get('event_at')) >= decision:
            continue
        if row.get('event_id') == target['event_id']:
            continue
        if row.get('event_id') in seen:
            raise ValueError('DUPLICATE_TRAINING_EVENT')
        if row.get('competition') != target['competition'] or row.get('market_type') != '1x2' or row.get('period') != target['period'] or row.get('settlement') != target['settlement']:
            continue
        if row.get('outcome') not in OUTCOMES:
            raise ValueError('INVALID_TRAINING_OUTCOME')
        seen.add(row['event_id'])
        eligible.append(row)
    eligible.sort(key=lambda r: (_time(r['event_at']), r['event_id']))
    ids = [target['evidence_id']] + [r['evidence_id'] for r in eligible]
    base = {'decision_cutoff': decision.isoformat(), 'data_origin': 'synthetic',
            'replay_mode': 'SYNTHETIC_HYPOTHETICAL_REPLAY', 'model_version': MODEL_VERSION,
            'training_count': len(eligible), 'evidence_manifest': _refs([target] + eligible),
            'limitations': ['Synthetic retrospective clock; not evidence that a historical prediction was persisted.',
                            'Smoothed frequencies are not established calibrated probabilities.']}
    if len(eligible) < minimum_training:
        return dict(base, abstained=True, probabilities=None, reason='INSUFFICIENT_TRAINING')
    with localcontext() as ctx:
        ctx.prec = 34
        denominator = Decimal(len(eligible)) + 3 * alpha
        probabilities = {o: _metric((Decimal(sum(r['outcome'] == o for r in eligible)) + alpha) / denominator,
                                   'probability fraction', ids,
                                   '(eligible outcome count + smoothing) / (eligible count + 3*smoothing)',
                                   model_version=MODEL_VERSION, smoothing=str(alpha)) for o in OUTCOMES}
    return dict(base, abstained=False, probabilities=probabilities, reason=None,
                scenario_configuration={'smoothing': str(alpha), 'minimum_training': minimum_training})


def evaluate_chronological(records, cutoff):
    """Score retained predictions only once their corresponding outcomes are eligible.

    Each row has {'prediction': ..., 'outcome': ...}. Prediction contains three
    probability strings, decision_cutoff, event_at, scope, model evidence and
    input_evidence. Outcome has its own scope and availability evidence.
    """
    evaluation = _time(cutoff)
    if not isinstance(records, list):
        raise ValueError('RECORD_LIST_REQUIRED')
    cases = []
    ids_seen = set()
    for row in records:
        if not isinstance(row, dict):
            continue
        pred, outcome = row.get('prediction'), row.get('outcome')
        if not isinstance(pred, dict) or not _fully_known_before(outcome, evaluation):
            continue
        try:
            decision = _time(pred.get('decision_cutoff'))
        except ValueError:
            continue
        if decision > evaluation or not _fully_known_before(pred, decision):
            continue
        _validate_scope(pred)
        _validate_scope(outcome)
        if any(pred.get(k) != outcome.get(k) for k in SCOPE if k != 'outcome'):
            raise ValueError('OUTCOME_SCOPE_MISMATCH')
        if pred['status'] == 'live' and (not pred.get('game_state_id') or pred.get('game_state_id') != outcome.get('game_state_id')):
            raise ValueError('LIVE_GAME_STATE_REQUIRED')
        if decision > _time(pred.get('event_at')):
            raise ValueError('PREDICTION_AFTER_EVENT')
        outcome_time = _evidence(outcome, evaluation)
        if outcome_time < _time(pred['event_at']):
            raise ValueError('OUTCOME_BEFORE_EVENT')
        inputs = _model_inputs(pred, decision)
        probabilities = pred.get('probabilities')
        if not isinstance(probabilities, dict) or set(probabilities) != set(OUTCOMES):
            raise ValueError('INCOMPLETE_PROBABILITIES')
        probs = {k: _number(v) for k, v in probabilities.items()}
        if any(v <= 0 or v >= 1 for v in probs.values()) or abs(sum(probs.values()) - 1) > Decimal('1e-12'):
            raise ValueError('INVALID_PROBABILITIES')
        actual = outcome['outcome']
        if actual not in OUTCOMES:
            raise ValueError('INVALID_OUTCOME')
        if pred['event_id'] in ids_seen:
            raise ValueError('DUPLICATE_EVENT')
        ids_seen.add(pred['event_id'])
        records_used = [pred, outcome] + inputs
        refs = [r['evidence_id'] for r in records_used]
        score = sum((float(probs[o]) - float(o == actual)) ** 2 for o in OUTCOMES)
        logloss = -math.log(float(probs[actual]))
        cases.append({'event_id': pred['event_id'], 'decision_cutoff': decision.isoformat(),
                      'prediction': pred, 'outcome': outcome, 'evidence_manifest': _refs(records_used),
                      'brier': _metric(score, 'multiclass Brier score', refs, 'sum((p - outcome indicator)^2)'),
                      'log_loss': _metric(logloss, 'natural log loss', refs, '-ln(p_actual)')})
    cases.sort(key=lambda c: (c['decision_cutoff'], c['event_id']))
    def aggregate(name):
        values = [float(c[name]['value']) for c in cases]
        refs = sorted({eid for c in cases for eid in c[name]['evidence_ids']})
        return {'value': statistics.fmean(values) if values else None,
                'sample_variance': statistics.variance(values) if len(values) > 1 else None,
                'sample_size': len(values), 'evidence_ids': refs,
                'transformation': {'version': VERSION, 'formula': 'arithmetic mean and sample variance'}}
    return {'evaluation_cutoff': evaluation.isoformat(), 'cases': cases,
            'metrics': {'brier': aggregate('brier'), 'log_loss': aggregate('log_loss')},
            'interpretation': 'Scores describe retained eligible forecasts, not a demonstration of improvement.'}




def _fully_known_before(item, cutoff):
    """Gate all operational evidence clocks before reading an as-of record."""
    if not isinstance(item,dict):
        return False
    try:
        received,persisted,usable=(_time(item.get(k)) for k in ('received_at','persisted_at','usable_at'))
        published=item.get('source_published_at',item.get('published_at'))
        return (published is None or _time(published) <= received) and received <= persisted <= usable <= cutoff
    except ValueError:
        return False

def current_frequency_prior(rows, target, cutoff, raw_resolver, *, smoothing='1', minimum_training=1):
    """Build a current, evidence-linked 1X2 frequency prior for a future fixture.

    Only exact source/competition/period/settlement matches are admitted. Source
    bytes and per-row normalization are reverified. The model is computed now and
    is not asserted to have existed at the supplied input cutoff.
    """
    from datetime import date, time, timedelta
    from .public_results import _match, find_ambiguous_fixtures

    decision = _time(cutoff)
    if decision > datetime.now(timezone.utc):
        raise ValueError('CUTOFF_AFTER_ACTUAL_TIME')
    if not isinstance(rows, list) or not isinstance(target, dict) or not callable(raw_resolver):
        raise ValueError('INVALID_PRIOR_INPUT')
    if not _fully_known_before(target, decision):
        raise ValueError('TARGET_NOT_ELIGIBLE')
    _evidence(target, decision)
    if target['data_origin'] not in ('imported_historical', 'captured_real'):
        raise ValueError('REAL_TARGET_EVIDENCE_REQUIRED')
    if target.get('market_type') != '1x2' or target.get('period') != 'full_time':
        raise ValueError('UNSUPPORTED_MARKET')
    if target.get('result_state') != 'unavailable' or target.get('outcome') is not None:
        raise ValueError('TARGET_ALREADY_HAS_RESULT')
    alpha = _number(smoothing)
    if alpha < Decimal('1e-12') or alpha > Decimal('1e12') or isinstance(minimum_training, bool) or not isinstance(minimum_training, int) or minimum_training < 1:
        raise ValueError('INVALID_MODEL_CONFIGURATION')
    try:
        target_day = date.fromisoformat(target.get('event_date'))
    except (TypeError, ValueError):
        raise ValueError('INVALID_EVENT_DATE') from None
    # With unknown source timezone, a full 24-hour civil-date buffer establishes
    # that the local event date cannot already have started at the cutoff.
    target_earliest = datetime.combine(target_day - timedelta(days=1), time.min, tzinfo=timezone.utc)
    if decision >= target_earliest:
        raise ValueError('FUTURE_FIXTURE_TIME_UNCERTAIN')
    docs = {}

    def verify(record):
        _evidence(record, decision)
        source_hash = record['source_hash']
        if source_hash not in docs:
            raw = raw_resolver(source_hash)
            if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != source_hash:
                raise ValueError('SOURCE_HASH_MISMATCH')
            try:
                doc = json.loads(raw.decode('utf-8-sig'))
            except (UnicodeError, json.JSONDecodeError):
                raise ValueError('INVALID_SOURCE_BYTES') from None
            if not isinstance(doc, dict) or not isinstance(doc.get('matches'), list):
                raise ValueError('INVALID_SOURCE_BYTES')
            docs[source_hash] = doc
        doc = docs[source_hash]
        path = record.get('source_record_path')
        match = re.fullmatch(r'\$\.matches\[(\d+)\]', path or '')
        if not match:
            raise ValueError('SOURCE_RECORD_PATH_REQUIRED')
        ordinal = int(match.group(1))
        if ordinal >= len(doc['matches']):
            raise ValueError('SOURCE_RECORD_PATH_INVALID')
        expected = _match(doc.get('name'), doc['matches'][ordinal], ordinal)
        for name in ('fixture_key','competition','event_date','source_local_time','home','away',
                     'market_type','period','settlement','home_goals','away_goals','outcome','result_state'):
            if record.get(name) != expected.get(name):
                raise ValueError('SOURCE_RECORD_MISMATCH')
        if not record.get('acquisition_id') or not record.get('source_id'):
            raise ValueError('SOURCE_ACQUISITION_REQUIRED')
        evidence_id = hashlib.sha256(json.dumps([record['source_id'],record['acquisition_id'],ordinal],
                                               ensure_ascii=False,sort_keys=True,separators=(',', ':')).encode('utf-8')).hexdigest()
        if record['evidence_id'] != evidence_id:
            raise ValueError('SOURCE_EVIDENCE_ID_MISMATCH')

    verify(target)
    candidates = []
    target_matches = []
    for row in rows:
        if not _fully_known_before(row, decision):
            continue
        if row.get('fixture_key') == target.get('fixture_key'):
            target_matches.append(row)
        if (row.get('data_origin') not in ('imported_historical', 'captured_real') or
            row.get('source_id') != target.get('source_id') or row.get('competition') != target.get('competition')
            or row.get('market_type') != target.get('market_type') or row.get('period') != target.get('period')
            or row.get('settlement') != target.get('settlement') or row.get('outcome') not in OUTCOMES):
            continue
        try:
            day = date.fromisoformat(row.get('event_date'))
        except (ValueError, TypeError):
            raise ValueError('INVALID_EVENT_DATE') from None
        # Require the date to have fully elapsed even under an unknown timezone.
        event_latest = datetime.combine(day + timedelta(days=2), time.min, tzinfo=timezone.utc)
        if event_latest > decision or day >= target_day:
            continue
        verify(row)
        candidates.append(row)
    if len(target_matches) != 1 or target_matches[0].get('evidence_id') != target.get('evidence_id'):
        raise ValueError('AMBIGUOUS_TARGET_MAPPING')
    candidate_keys = {row['fixture_key'] for row in candidates}
    relevant_keys = candidate_keys | {target['fixture_key']}
    date_flags = [flag for flag in find_ambiguous_fixtures(rows, cutoff)
                  if flag['source_id'] == target['source_id'] and flag['competition'] == target['competition']
                  and relevant_keys.intersection(flag['fixture_keys'])]
    flagged_ids = {eid for flag in date_flags for eid in flag['evidence_ids']}
    quarantined = [row for row in rows if _fully_known_before(row, decision) and row.get('evidence_id') in flagged_ids]
    # Quarantine references must resolve to eligible, hash-verified source rows.
    for row in quarantined:
        verify(row)
    if any(target['fixture_key'] in flag['fixture_keys'] for flag in date_flags):
        raise ValueError('AMBIGUOUS_TARGET_FIXTURE')
    excluded_keys = {key for flag in date_flags for key in flag['fixture_keys']}
    candidates = [row for row in candidates if row['fixture_key'] not in excluded_keys]
    groups = {}
    for row in candidates:
        groups.setdefault(row['fixture_key'], []).append(row)
    if any(len(group) > 1 for group in groups.values()):
        raise ValueError('AMBIGUOUS_TRAINING_MAPPING')
    candidates.sort(key=lambda x: (x['event_date'], x['fixture_key'], x['evidence_id']))
    actual = datetime.now(timezone.utc)
    if actual >= target_earliest:
        raise ValueError('FUTURE_FIXTURE_TIME_UNCERTAIN')
    evidence = [target] + candidates
    ids = [x['evidence_id'] for x in evidence]
    counts = {name: sum(x['outcome'] == name for x in candidates) for name in OUTCOMES}
    config = {'source_id':'research_configuration', 'recorded_at':actual.isoformat(),
              'smoothing':str(alpha), 'minimum_training':minimum_training,
              'source_scope':'same source ID and exact competition, period and settlement',
              'temporal_rule':'result date completed with conservative timezone buffer'}
    config_identity = {k:v for k,v in config.items() if k != 'recorded_at'}
    config['source_hash'] = hashlib.sha256(json.dumps(config_identity,sort_keys=True,separators=(',', ':')).encode()).hexdigest()
    config['evidence_id'] = 'config:' + config['source_hash']
    base = {'data_cutoff':decision.isoformat(), 'decision_cutoff':None, 'actual_run_time':actual.isoformat(),
            'model_usable_at':None, 'model_persisted_at':None,
            'clock_semantics':'Inputs eligible at data cutoff; model output and decision become usable at actual computation time.',
            'model_status':'ephemeral_current_calculation', 'model_version':MODEL_VERSION,
            'target':target, 'training_manifest':candidates, 'training_count':len(candidates),
            'quality_flags':date_flags, 'quarantined_evidence':quarantined,
            'research_tasks':[{'gap':'AMBIGUOUS_FIXTURE_DATE',
                               'question':'Are the differently dated records a rescheduled match or separate fixtures?',
                               'permitted_source':'documented source fixture IDs or user-supplied mapping',
                               'priority_rationale':'An unresolved mapping can double-count or misidentify outcomes.',
                               'expected_evidence':'retained source identifiers and dated fixture revisions',
                               'budget':'one bounded identity review',
                               'stopping_condition':'mapping is verified or remains unresolved',
                               'evidence_ids':flag['evidence_ids']} for flag in date_flags],
            'counts':{k:_metric(v,'eligible results',ids + [config['evidence_id']],
                                'count of eligible same-source outcome observations') for k,v in counts.items()},
            'configuration':config,
            'uncertainty':['This is an uncalibrated descriptive prior, not a demonstrated predictive edge.',
                           'Source supplies local dates/times without a verified UTC kickoff timezone.',
                           'Ephemeral model state was calculated now and has not been persisted.']}
    if len(candidates) < minimum_training:
        finished = datetime.now(timezone.utc)
        if finished >= target_earliest:
            raise ValueError('FUTURE_FIXTURE_TIME_UNCERTAIN')
        base['actual_run_time'] = finished.isoformat()
        base['model_usable_at'] = finished.isoformat()
        base['decision_cutoff'] = finished.isoformat()
        return dict(base,abstained=True,probabilities=None,reason='INSUFFICIENT_ELIGIBLE_RESULTS',
                    research_task={'gap':'INSUFFICIENT_ELIGIBLE_RESULTS',
                                   'question':'Can same-competition historical results be captured and validated?',
                                   'evidence_ids':ids})
    with localcontext() as ctx:
        ctx.prec = 34
        denominator = Decimal(len(candidates)) + 3 * alpha
        probs = {name:_metric((Decimal(counts[name]) + alpha) / denominator,'probability fraction',
                             ids + [config['evidence_id']],
                             '(eligible outcome count + smoothing) / (eligible count + 3*smoothing)')
                 for name in OUTCOMES}
    finished = datetime.now(timezone.utc)
    if finished >= target_earliest:
        raise ValueError('FUTURE_FIXTURE_TIME_UNCERTAIN')
    base['actual_run_time'] = finished.isoformat()
    base['model_usable_at'] = finished.isoformat()
    base['decision_cutoff'] = finished.isoformat()
    return dict(base,abstained=False,probabilities=probs,reason=None)








