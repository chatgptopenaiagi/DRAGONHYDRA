"""Pure scoring of explicitly synthetic forward episodes; never a real calibration claim."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math

_PREDICTION = {'prediction_id', 'match_id', 'forecast_target', 'horizon',
               'probabilities', 'decision_at', 'available_at', 'source_mode', 'synthetic'}
_OUTCOME = {'match_id', 'forecast_target', 'horizon', 'label', 'occurred_at',
            'available_at', 'source_mode', 'synthetic'}
_MODES = {'DEMONSTRATION', 'REPLAY'}


def _time(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('UTC_TIMESTAMP_REQUIRED')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('UTC_TIMESTAMP_REQUIRED') from exc
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ValueError('UTC_TIMESTAMP_REQUIRED')
    return result


def _text(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError('INVALID_SYNTHETIC_IDENTITY')
    return value


def _horizon(value):
    if value == 'FULL_TIME':
        return value
    if type(value) is not int or not 1 <= value <= 120:
        raise ValueError('INVALID_HORIZON')
    return value


def _probabilities(value):
    if not isinstance(value, dict) or not 2 <= len(value) <= 16:
        raise ValueError('INVALID_PROBABILITY_VECTOR')
    for key, number in value.items():
        _text(key)
        if type(number) not in (int, float) or not 0 <= number <= 1 or not math.isfinite(number):
            raise ValueError('INVALID_PROBABILITY_VECTOR')
    if not math.isclose(math.fsum(value.values()), 1.0, abs_tol=1e-12, rel_tol=0):
        raise ValueError('PROBABILITIES_NOT_NORMALIZED')
    return dict(value)


def _rows(values, fields):
    if not isinstance(values, (list, tuple)) or len(values) > 10000:
        raise ValueError('BOUNDED_EPISODES_REQUIRED')
    result = []
    identities = set()
    prediction_ids = set()
    for value in values:
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError('UNEXPECTED_EPISODE_FIELDS')
        if (value['synthetic'] is not True or not isinstance(value['source_mode'], str) or
                value['source_mode'] not in _MODES):
            raise ValueError('SYNTHETIC_EPISODES_ONLY')
        item = dict(value)
        for key in ('match_id', 'forecast_target'):
            _text(item[key])
        item['horizon'] = _horizon(item['horizon'])
        item['available_at'] = _time(item['available_at'])
        identity = (item['match_id'], item['forecast_target'], item['horizon'])
        if identity in identities:
            raise ValueError('AMBIGUOUS_DUPLICATE_EPISODE')
        identities.add(identity)
        if fields == _PREDICTION:
            _text(item['prediction_id'])
            if item['prediction_id'] in prediction_ids:
                raise ValueError('DUPLICATE_PREDICTION_ID')
            prediction_ids.add(item['prediction_id'])
            item['decision_at'] = _time(item['decision_at'])
            item['probabilities'] = _probabilities(item['probabilities'])
            if item['available_at'] < item['decision_at']:
                raise ValueError('PREDICTION_AVAILABLE_BEFORE_DECISION')
        else:
            _text(item['label'])
            item['occurred_at'] = _time(item['occurred_at'])
            if item['available_at'] < item['occurred_at']:
                raise ValueError('OUTCOME_AVAILABLE_BEFORE_MATURITY')
        result.append(item)
    return result


def _key(row):
    return row['match_id'], row['forecast_target'], row['horizon']


def evaluate_forecasts(predictions, outcomes, *, cutoff=None, bins=10, horizon=None):
    """Score exact matched synthetic targets whose labels have actually matured.

    ``occurred_at`` means the target's maturity time (window end, or full time),
    not the time at which an early goal occurred. Numeric horizons must mature
    exactly that many minutes after ``decision_at``. Zero assigned probability
    is valid: infinite log loss is represented by null plus an explicit flag,
    never silently clipped into a finite, flattering score.
    """
    if type(bins) is not int or not 2 <= bins <= 50:
        raise ValueError('INVALID_CALIBRATION_BINS')
    if horizon is not None:
        _horizon(horizon)
    bound = _time(cutoff) if cutoff is not None else datetime.now(timezone.utc)
    predictions = _rows(predictions, _PREDICTION)
    outcomes = {_key(row): row for row in _rows(outcomes, _OUTCOME)}
    exclusions = defaultdict(int)
    scored = []
    for prediction in predictions:
        if horizon is not None and prediction['horizon'] != horizon:
            exclusions['HORIZON_FILTERED'] += 1
            continue
        if prediction['available_at'] > bound or prediction['decision_at'] > bound:
            exclusions['PREDICTION_NOT_AVAILABLE_AT_CUTOFF'] += 1
            continue
        outcome = outcomes.get(_key(prediction))
        if outcome is None:
            exclusions['OUTCOME_PENDING'] += 1
            continue
        if outcome['source_mode'] != prediction['source_mode']:
            raise ValueError('SOURCE_MODE_MISMATCH')
        if outcome['label'] not in prediction['probabilities']:
            raise ValueError('OUTCOME_LABEL_MISMATCH')
        if prediction['horizon'] != 'FULL_TIME':
            expected = prediction['decision_at'] + timedelta(minutes=prediction['horizon'])
            if outcome['occurred_at'] > expected:
                exclusions['NOT_ELIGIBLE_PLAYING_CLOCK_MAPPING_UNAVAILABLE'] += 1
                continue
            if outcome['occurred_at'] < expected:
                raise ValueError('HORIZON_MATURITY_MISMATCH')
        if outcome['available_at'] > bound:
            exclusions['OUTCOME_NOT_AVAILABLE_AT_CUTOFF'] += 1
            continue
        if prediction['available_at'] >= outcome['occurred_at']:
            exclusions['PREDICTION_NOT_PROSPECTIVE'] += 1
            continue
        vector = prediction['probabilities']
        label = outcome['label']
        probability = vector[label]
        brier = math.fsum((p - (key == label)) ** 2 for key, p in vector.items())
        chosen = max(sorted(vector), key=lambda key: vector[key])
        scored.append({'prediction_id': prediction['prediction_id'], 'match_id': prediction['match_id'],
                       'forecast_target': prediction['forecast_target'], 'horizon': prediction['horizon'],
                       'brier': brier, 'log_loss': -math.log(probability) if probability else None,
                       'zero_probability_label': probability == 0, 'confidence': vector[chosen],
                       'correct': chosen == label,
                       'boundary_probabilities': sum(p in (0, 1) for p in vector.values())})
    reliability = [{'lower': index / bins, 'upper': (index + 1) / bins,
                    'upper_inclusive': index == bins - 1, 'count': 0,
                    'mean_confidence': None, 'accuracy': None} for index in range(bins)]
    for index, bucket in enumerate(reliability):
        members = [row for row in scored if min(bins - 1, int(row['confidence'] * bins)) == index]
        if members:
            bucket['count'] = len(members)
            bucket['mean_confidence'] = math.fsum(row['confidence'] for row in members) / len(members)
            bucket['accuracy'] = sum(row['correct'] for row in members) / len(members)
    count = len(scored)
    infinite = any(row['zero_probability_label'] for row in scored)
    return {'schema_version': 1, 'scope': 'SYNTHETIC_FORWARD_EPISODES', 'synthetic': True,
            'calibration_state': 'UNVERIFIED', 'real_calibration_claim': False,
            'status': 'scored' if count else 'pending', 'cutoff': bound.isoformat(),
            'prediction_count': len(predictions), 'sample_count': count,
            'independent_match_count': len({row['match_id'] for row in scored}),
            'small_sample': count < 20,
            'brier_score': math.fsum(row['brier'] for row in scored) / count if count else None,
            'log_loss': (None if infinite or not count else
                         math.fsum(row['log_loss'] for row in scored) / count),
            'log_loss_infinite': infinite,
            'zero_probability_events': sum(row['zero_probability_label'] for row in scored),
            'boundary_probability_count': sum(row['boundary_probabilities'] for row in scored),
            'ece': (math.fsum(bucket['count'] / count * abs(bucket['mean_confidence'] - bucket['accuracy'])
                              for bucket in reliability if bucket['count']) if count else None),
            'ece_definition': 'top_label_equal_width_absolute_confidence_accuracy_gap',
            'mixed_target_horizon_aggregate': len({(row['forecast_target'], row['horizon']) for row in scored}) > 1,
            'reliability_bins': reliability, 'exclusions': dict(exclusions), 'scores': scored,
            'limitations': ['Synthetic episodes do not establish real calibration or predictive quality.',
                            'Correlated forecasts and repeated horizons are not independent matches.',
                            'Compare like targets and horizons; mixed aggregate errors are descriptive only.']}


def evaluate_baseline_vs_assisted(baseline, assisted, outcomes, **kwargs):
    """The fact-selection assistant may explain a forecast but cannot replace it."""
    left = {_key(row): row for row in _rows(baseline, _PREDICTION)}
    right = {_key(row): row for row in _rows(assisted, _PREDICTION)}
    if left.keys() != right.keys():
        raise ValueError('A_B_COHORT_MISMATCH')
    for key, row in left.items():
        other = right[key]
        if row['probabilities'] != other['probabilities']:
            raise ValueError('AI_PROBABILITY_OVERRIDE_REJECTED')
        if {k: v for k, v in row.items() if k != 'prediction_id'} != {
                k: v for k, v in other.items() if k != 'prediction_id'}:
            raise ValueError('A_B_INPUTS_OR_CUTOFF_MISMATCH')
    first = evaluate_forecasts(baseline, outcomes, **kwargs)
    second = evaluate_forecasts(assisted, outcomes, **kwargs)
    return {'schema_version': 1, 'synthetic': True, 'scope': 'MATCHED_SAME_DATA_A_B',
            'probability_vectors_unchanged': True, 'quality_improvement_claim': False,
            'expected_quality_difference': 0.0, 'baseline': first, 'assisted': second,
            'brier_delta': 0.0 if first['sample_count'] else None,
            'log_loss_delta': 0.0 if first['log_loss'] is not None else None,
            'ece_delta': 0.0 if first['sample_count'] else None,
            'limitations': ['AI fact selection cannot change probabilities; same-data scoring is identical.',
                            'Synthetic results are not evidence of real forecasting improvement.']}
