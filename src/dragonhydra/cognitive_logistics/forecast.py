"""Past-only inventory-count and completed-lead-time forecasts; no I/O."""
from copy import deepcopy
from functools import lru_cache
import json
import math
import statistics

METHODS = ('naive', 'moving_average', 'ses', 'seasonal_naive', 'croston', 'sba', 'tsb', 'censored_poisson')
COMPONENTS = ('processing', 'transport', 'receiving', 'disruption')
MAX_MEAN = 10000.


def number(value, low=0., high=1e9):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError('LOGISTICS_FINITE_NUMBER_REQUIRED')
    return float(value)


def integer(value, low=0, high=1000000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('LOGISTICS_BOUNDED_INTEGER_REQUIRED')
    return value


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('LOGISTICS_SCHEMA_INVALID')


@lru_cache(maxsize=512)
def _poisson_vector(rate):
    """Normalized finite Poisson approximation with its omitted tail disclosed."""
    rate = number(rate, 0, MAX_MEAN)
    if not rate:
        return (0,), (1.,), 0.
    limit = math.ceil(rate + 12 * math.sqrt(rate) + 30)
    if rate < 700:
        probabilities = [math.exp(-rate)]
        for k in range(1, limit + 1):
            probabilities.append(probabilities[-1] * rate / k)
    else:
        probabilities = [math.exp(-rate + k * math.log(rate) - math.lgamma(k + 1)) for k in range(limit + 1)]
    total = math.fsum(probabilities)
    if not 0.999999999 <= total <= 1.000000001:
        raise ValueError('LOGISTICS_POISSON_NUMERICAL_BOUND')
    return tuple(range(limit + 1)), tuple(p / total for p in probabilities), max(0., 1. - total)


def quantile(support, probabilities, level):
    level = number(level, 0, 1)
    cumulative = 0.
    for value, probability in zip(support, probabilities):
        cumulative += probability
        if cumulative + 1e-15 >= level:
            return value
    return support[-1]


def _demand_result(rate, horizon, cutoff, method, state):
    total = number(rate * horizon, 0, MAX_MEAN)
    support, probabilities, tail = _poisson_vector(total)
    return {'schema_version': 'dragonhydra.logistics-demand/1', 'model_id': 'logistics-' + method + '-poisson/1',
            'method': method, 'cutoff': cutoff, 'horizon': horizon, 'mean': total, 'daily_mean': rate,
            'variance': total, 'quantiles': {str(p): quantile(support, probabilities, p) for p in (.1, .5, .9)},
            'interval90': [quantile(support, probabilities, .05), quantile(support, probabilities, .95)],
            'distribution': {'support': list(support), 'probabilities': list(probabilities),
                             'tail_probability': tail, 'approximation': 'Poisson; finite retained mass normalized; omitted tail disclosed'},
            'state': deepcopy(state), 'assumptions': [
                'UNVERIFIED_SYNTHETIC: prediction intervals have not been calibrated.',
                'Point-rate estimator plus independent Poisson counts; overdispersion, estimation uncertainty and serial dependence are omitted.',
                'Only observations with day and available_day at or before cutoff are eligible.',
                'Censored sales are lower bounds, never observations of true zero demand.',
                'The seven standard estimators condition on uncensored observed periods; informative stockout censoring can bias them.',
                'Total-mean numerical support is bounded to 10000 units; no real operational accuracy is claimed.']}


def _history(history, cutoff):
    integer(cutoff)
    if not isinstance(history, list) or len(history) > 10000:
        raise ValueError('LOGISTICS_HISTORY_BOUND')
    seen, eligible, future = set(), [], 0
    for row in history:
        _keys(row, ('day', 'sales', 'censored', 'available_day'))
        day, available = integer(row['day']), integer(row['available_day'])
        number(row['sales'], 0, 1000)
        if type(row['censored']) is not bool or available < day or day in seen:
            raise ValueError('LOGISTICS_HISTORY_CHRONOLOGY_OR_DUPLICATE')
        seen.add(day)
        if day > cutoff or available > cutoff:
            future += 1
        else:
            eligible.append(dict(row))
    return sorted(eligible, key=lambda row: row['day']), future


def _log_survival(k, rate):
    if k == 0:
        return 0.
    if rate == 0:
        return -math.inf
    if k > rate:
        term, mass = 1., 1.
        for j in range(1, 20000):
            term *= rate / (k + j)
            mass += term
            if term <= mass * 1e-15:
                break
        return -rate + k * math.log(rate) - math.lgamma(k + 1) + math.log(mass)
    cdf = math.fsum(math.exp(-rate + j * math.log(rate) - math.lgamma(j + 1)) for j in range(k))
    return math.log1p(-min(cdf, 1. - 1e-15))


def censored_log_likelihood(rows, rate):
    """Observed-count PMFs and P(D>=sales) for known stockout lower bounds."""
    rate = number(rate, 0, 1000)
    terms = []
    for row in rows:
        k = row['sales']
        if type(k) not in (int, float) or k != int(k):
            raise ValueError('LOGISTICS_CENSORED_POISSON_INTEGER_COUNTS_REQUIRED')
        k = integer(int(k), 0, 1000)
        if row['censored']:
            terms.append(_log_survival(k, rate))
        elif rate == 0:
            terms.append(0. if k == 0 else -math.inf)
        else:
            terms.append(-rate + k * math.log(rate) - math.lgamma(k + 1))
    return math.fsum(terms) if all(math.isfinite(term) for term in terms) else -math.inf


def forecast_demand(history, method='sba', horizon=5, *, cutoff, season=7, alpha=.2, window=7):
    """Forecast total requested-horizon demand, never infer future observations."""
    if method not in METHODS:
        raise ValueError('LOGISTICS_DEMAND_METHOD_UNSUPPORTED')
    integer(horizon, 1, 90); integer(season, 1, 365); integer(window, 1, 1000)
    alpha = number(alpha, 1e-6, 1)
    eligible, excluded = _history(history, cutoff)
    clean = [row for row in eligible if not row['censored']]
    values = [float(row['sales']) for row in clean]
    state = {'eligible_observations': len(eligible), 'uncensored_observations': len(clean),
             'excluded_future_observations': excluded, 'censored_observations': len(eligible)-len(clean),
             'used_days': [row['day'] for row in clean], 'alpha': alpha, 'window': window, 'season': season,
             'cold_start': not values, 'cold_start_prior_daily_mean': .5 if not values else None,
             'missing_periods_are_not_imputed_as_zero': True}
    rate = .5
    if method == 'censored_poisson':
        informative = [row for row in eligible if not row['censored'] or row['sales'] > 0]
        state['used_days'] = [row['day'] for row in eligible]
        state['cold_start'] = not informative
        if informative:
            upper = min(1000., max(10., 3. * max(row['sales'] for row in informative)))
            grid = [upper * index / 200 for index in range(201)]
            scores = [censored_log_likelihood(eligible, value) for value in grid]
            best = max(range(len(grid)), key=lambda index: (scores[index], -grid[index]))
            rate = grid[best]
            state.update(grid_upper=upper, grid_step=upper/200, grid_points=201,
                         fit_at_upper_bound=best == 200, log_likelihood=scores[best],
                         no_finite_unbounded_mle=all(row['censored'] for row in informative))
    elif values:
        if method == 'naive':
            rate = values[-1]
        elif method == 'moving_average':
            rate = statistics.fmean(values[-window:])
        elif method == 'seasonal_naive':
            last = {row['day'] % season: row['sales'] for row in clean}
            daily = [last.get(day % season, statistics.fmean(values)) for day in range(cutoff+1, cutoff+horizon+1)]
            rate = statistics.fmean(daily)
            state['next_daily_means'] = daily
        elif method == 'ses':
            rate = values[0]
            for value in values[1:]:
                rate += alpha * (value-rate)
        elif method in ('croston', 'sba'):
            positive = [index for index, value in enumerate(values) if value > 0]
            rate = 0.
            if positive:
                first = positive[0]
                size, interval, previous = values[first], float(first+1), first
                for index in positive[1:]:
                    size += alpha * (values[index]-size)
                    interval += alpha * (index-previous-interval)
                    previous = index
                rate = size / interval * (1-alpha/2 if method == 'sba' else 1.)
                state.update(positive_demand_size=size, observed_period_interval=interval)
        elif method == 'tsb':
            probability, size = float(values[0] > 0), values[0]
            initialized = values[0] > 0
            for value in values[1:]:
                probability += alpha * (float(value > 0)-probability)
                if value > 0:
                    size = size + alpha * (value-size) if initialized else value
                    initialized = True
            rate = probability * size
            state.update(occurrence_probability=probability, positive_demand_size=size)
    state['cold_start_prior_daily_mean'] = .5 if state['cold_start'] else None
    return _demand_result(number(rate, 0, MAX_MEAN), horizon, cutoff, method, state)


def rescale_demand(forecast, factor, evidence=None):
    validate_demand(forecast)
    factor = number(factor, 0, 10)
    try:
        if len(json.dumps(evidence, allow_nan=False)) > 16384:
            raise ValueError('LOGISTICS_SIGNAL_EVIDENCE_BOUND')
    except (TypeError, OverflowError) as exc:
        raise ValueError('LOGISTICS_SIGNAL_EVIDENCE_SCHEMA') from exc
    state = deepcopy(forecast['state'])
    if 'next_daily_means' in state:
        state['next_daily_means'] = [number(value, 0, MAX_MEAN)*factor for value in state['next_daily_means']]
    state['visible_signal_adjustment'] = {'factor': factor, 'evidence': deepcopy(evidence)}
    result = _demand_result(forecast['daily_mean']*factor, forecast['horizon'], forecast['cutoff'], forecast['method'], state)
    result['model_id'] += '+visible-signal'
    result['assumptions'].append('Visible-signal scaling is a declared experimental adjustment, not an oracle or fitted accuracy guarantee.')
    return result


def combine_demand(forecasts):
    """Sum same-target Poisson rates with explicit independence/provenance."""
    if not isinstance(forecasts, list) or not 1 <= len(forecasts) <= 64:
        raise ValueError('LOGISTICS_COMBINATION_BOUND')
    for forecast in forecasts:
        validate_demand(forecast)
    first = forecasts[0]
    if any((item['horizon'], item['cutoff']) != (first['horizon'], first['cutoff']) for item in forecasts):
        raise ValueError('LOGISTICS_COMBINATION_TARGET_MISMATCH')
    result = _demand_result(math.fsum(item['daily_mean'] for item in forecasts), first['horizon'], first['cutoff'],
        'combined', {'aggregation': 'SUM', 'source_model_ids': [item['model_id'] for item in forecasts],
                     'source_methods': [item['method'] for item in forecasts], 'source_forecast_count': len(forecasts),
                     'cold_start': any(item['state'].get('cold_start', False) for item in forecasts)})
    result['assumptions'].append('Aggregated count law assumes conditional independence; cross-location demand covariance is omitted.')
    return result


def _pmf(rows, low=0, high=14):
    if not isinstance(rows, list) or not rows or len(rows) > 100:
        raise ValueError('LOGISTICS_PMF_BOUND')
    seen, result = set(), []
    for row in rows:
        _keys(row, ('days', 'probability'))
        day = integer(row['days'], low, high)
        if day in seen:
            raise ValueError('LOGISTICS_PMF_DUPLICATE')
        seen.add(day)
        result.append((day, number(row['probability'], 0, 1)))
    if abs(math.fsum(p for _, p in result)-1) > 1e-9:
        raise ValueError('LOGISTICS_PMF_NOT_NORMALIZED')
    return sorted((day, p) for day, p in result if p > 0)


def _summary(pairs):
    mean = math.fsum(value*p for value, p in pairs)
    return {'mean': mean, 'variance': math.fsum((value-mean)**2*p for value, p in pairs),
            'pmf': [{'days': value, 'probability': p} for value, p in pairs]}


def forecast_leadtime(completed, *, cutoff, prior=None, prior_weight=2.):
    integer(cutoff); prior_weight = number(prior_weight, 1e-6, 1000)
    if not isinstance(completed, list) or len(completed) > 10000:
        raise ValueError('LOGISTICS_LEAD_HISTORY_BOUND')
    default = {'processing': [{'days': 1, 'probability': .7}, {'days': 2, 'probability': .3}],
               'transport': [{'days': 1, 'probability': .6}, {'days': 2, 'probability': .3}, {'days': 3, 'probability': .1}],
               'receiving': [{'days': 0, 'probability': .25}, {'days': 1, 'probability': .75}],
               'disruption': [{'days': 0, 'probability': .9}, {'days': 2, 'probability': .1}]}
    prior = deepcopy(default if prior is None else prior)
    _keys(prior, COMPONENTS)
    marginals = {name: _pmf(prior[name]) for name in COMPONENTS}
    total = {0: 1.}
    for name in COMPONENTS:
        combined = {}
        for left, p in total.items():
            for right, q in marginals[name]:
                combined[left+right] = combined.get(left+right, 0.) + p*q
        total = combined
    if any(not 1 <= value <= 14 for value, p in total.items() if p):
        raise ValueError('LOGISTICS_PRIOR_TOTAL_LEAD_BOUND')
    eligible, excluded = [], 0
    for row in completed:
        _keys(row, ('ordered_day', 'received_day', 'available_day', *COMPONENTS))
        ordered, received, available = (integer(row[key]) for key in ('ordered_day', 'received_day', 'available_day'))
        parts = {name: integer(row[name], 0, 14) for name in COMPONENTS}
        if not ordered < received <= available or received-ordered != sum(parts.values()) or not 1 <= sum(parts.values()) <= 14:
            raise ValueError('LOGISTICS_LEAD_CHRONOLOGY_OR_COMPONENT_MISMATCH')
        if received > cutoff or available > cutoff:
            excluded += 1
        else:
            eligible.append(row)
    denominator = prior_weight + len(eligible)
    total_counts = {day: p*prior_weight for day, p in total.items()}
    component_results = {}
    for name in COMPONENTS:
        counts = {day: p*prior_weight for day, p in marginals[name]}
        for row in eligible:
            counts[row[name]] = counts.get(row[name], 0.) + 1
        component_results[name] = _summary([(day, p/denominator) for day, p in sorted(counts.items())])
    for row in eligible:
        day = row['received_day']-row['ordered_day']
        total_counts[day] = total_counts.get(day, 0.) + 1
    return {'schema_version': 'dragonhydra.logistics-lead/1', 'model_id': 'completed-lead-empirical-prior/1',
            'cutoff': cutoff, **_summary([(day, p/denominator) for day, p in sorted(total_counts.items())]),
            'components': component_results, 'completed_observations': len(eligible), 'excluded_future_observations': excluded,
            'prior_weight': prior_weight, 'assumptions': [
                'UNVERIFIED_SYNTHETIC: finite 1..14-day predictive support is not calibrated.',
                'Only completed, available receipts enter estimation; in-transit future actual lead times are excluded.',
                'Total-duration empirical mixture retains observed component dependence; prior components alone are independent.',
                'Completed-receipt selection can underrepresent long outstanding orders; no absence-of-delay inference.']}


def validate_demand(forecast):
    if not isinstance(forecast, dict) or forecast.get('schema_version') != 'dragonhydra.logistics-demand/1':
        raise ValueError('LOGISTICS_DEMAND_FORECAST_SCHEMA')
    horizon = integer(forecast['horizon'], 1, 90); integer(forecast['cutoff'])
    mean = number(forecast['mean'], 0, MAX_MEAN)
    rate = number(forecast['daily_mean'], 0, MAX_MEAN)
    if abs(mean-rate*horizon) > 1e-8 or abs(number(forecast['variance'])-mean) > 1e-8:
        raise ValueError('LOGISTICS_DEMAND_MOMENT_MISMATCH')
    distribution = forecast['distribution']; support, probabilities = distribution['support'], distribution['probabilities']
    if not isinstance(support, list) or not isinstance(probabilities, list) or not 1 <= len(support) <= 20000 or len(support) != len(probabilities):
        raise ValueError('LOGISTICS_DEMAND_VECTOR_BOUND')
    if any(integer(value, 0, 20000) != index for index, value in enumerate(support)) or abs(math.fsum(number(p, 0, 1) for p in probabilities)-1) > 1e-9:
        raise ValueError('LOGISTICS_DEMAND_VECTOR_INVALID')
    if abs(math.fsum(k*p for k, p in zip(support, probabilities))-mean) > 1e-6 * max(1., mean):
        raise ValueError('LOGISTICS_DEMAND_VECTOR_MEAN_MISMATCH')
    variance = math.fsum((k-mean)**2*p for k, p in zip(support, probabilities))
    if abs(variance-forecast['variance']) > 1e-6 * max(1., mean):
        raise ValueError('LOGISTICS_DEMAND_VECTOR_VARIANCE_MISMATCH')
    number(distribution['tail_probability'], 0, 1e-8)
    _keys(forecast['quantiles'], ('0.1', '0.5', '0.9'))
    for key, level in (('0.1', .1), ('0.5', .5), ('0.9', .9)):
        if integer(forecast['quantiles'][key], 0, 20000) != quantile(support, probabilities, level):
            raise ValueError('LOGISTICS_QUANTILE_MISMATCH')
    if not isinstance(forecast['interval90'], list) or len(forecast['interval90']) != 2:
        raise ValueError('LOGISTICS_INTERVAL_SCHEMA')
    for value in forecast['interval90']:
        integer(value, 0, 20000)
    if forecast['interval90'] != [quantile(support, probabilities, .05), quantile(support, probabilities, .95)]:
        raise ValueError('LOGISTICS_INTERVAL_MISMATCH')
    return forecast


def validate_lead(forecast):
    if not isinstance(forecast, dict) or forecast.get('schema_version') != 'dragonhydra.logistics-lead/1':
        raise ValueError('LOGISTICS_LEAD_FORECAST_SCHEMA')
    integer(forecast['cutoff'])
    pairs = _pmf(forecast['pmf'], 1, 14)
    expected = _summary(pairs)
    if any(abs(number(forecast[key])-expected[key]) > 1e-8 for key in ('mean', 'variance')):
        raise ValueError('LOGISTICS_LEAD_MOMENT_MISMATCH')
    return pairs


def protection_distribution(demand, lead, review_period=0):
    validate_demand(demand); pairs = validate_lead(lead); integer(review_period, 0, 30)
    if demand['cutoff'] != lead['cutoff']:
        raise ValueError('LOGISTICS_FORECAST_CUTOFF_MISMATCH')
    counts = {}
    for duration, weight in pairs:
        support, probabilities, _ = _poisson_vector(demand['daily_mean']*(duration+review_period))
        for value, p in zip(support, probabilities):
            counts[value] = counts.get(value, 0.) + weight*p
    support = sorted(counts)
    probabilities = [counts[value] for value in support]
    return support, probabilities


def safety_stock(demand, lead, service_level=.95, objective='cycle_service_level', review_period=0):
    level = number(service_level, .001, .999)
    if objective not in ('cycle_service_level', 'fill_rate'):
        raise ValueError('LOGISTICS_SERVICE_OBJECTIVE_UNSUPPORTED')
    support, probabilities = protection_distribution(demand, lead, review_period)
    mean = math.fsum(value*p for value, p in zip(support, probabilities))
    if objective == 'cycle_service_level':
        target = quantile(support, probabilities, level)
    else:
        target = 0
        for candidate in support:
            if math.fsum(max(0, value-candidate)*p for value, p in zip(support, probabilities)) <= (1-level)*mean + 1e-12:
                target = candidate
                break
    shortage = math.fsum(max(0, value-target)*p for value, p in zip(support, probabilities))
    return {'objective': objective, 'service_level': level, 'target_level': target,
            'safety_stock': max(0., target-mean), 'protection_mean': mean,
            'protection_variance': math.fsum((value-mean)**2*p for value, p in zip(support, probabilities)),
            'achieved_cycle_service_level': math.fsum(p for value, p in zip(support, probabilities) if value <= target),
            'expected_shortage': shortage, 'implied_fill_rate': 1-shortage/mean if mean else None,
            'assumptions': ['One-cycle protection-stock surrogate; unit fill rate is not probability of no stockout.',
                            'Demand rate independent of lead time; Poisson and finite-support assumptions are uncalibrated.']}
