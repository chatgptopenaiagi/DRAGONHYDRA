"""Outcome-availability-gated inventory metrics; no policy-side oracle access."""
import math
import statistics

from .forecast import integer, number
from .policies import COSTS

FIELDS = {'day', 'available_day', 'demand', 'fulfilled', 'backordered', 'lost_sales', 'on_hand',
          'stockout', 'cycle_complete', 'deliveries', 'forecast', 'costs'}


def evaluate_outcomes(outcomes, *, cutoff, naive_scale=None):
    integer(cutoff)
    if not isinstance(outcomes, list) or len(outcomes) > 100000:
        raise ValueError('LOGISTICS_OUTCOME_BOUND')
    if naive_scale is not None:
        naive_scale = number(naive_scale, 0, 1000000)
    rows, seen, excluded = [], set(), 0
    for row in outcomes:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError('LOGISTICS_OUTCOME_SCHEMA')
        day, available = integer(row['day']), integer(row['available_day'])
        if day in seen or available < day:
            raise ValueError('LOGISTICS_OUTCOME_CHRONOLOGY_OR_DUPLICATE')
        seen.add(day)
        if day > cutoff or available > cutoff:
            excluded += 1
            continue
        for key in ('demand', 'fulfilled', 'backordered', 'lost_sales', 'on_hand'):
            number(row[key], 0, 1000000)
        if abs(row['fulfilled']+row['backordered']+row['lost_sales']-row['demand']) > 1e-8:
            raise ValueError('LOGISTICS_DEMAND_CONSERVATION_MISMATCH')
        if any(type(row[key]) is not bool for key in ('stockout', 'cycle_complete')):
            raise ValueError('LOGISTICS_OUTCOME_FLAGS')
        if row['demand'] > row['fulfilled'] and not row['stockout']:
            raise ValueError('LOGISTICS_UNFULFILLED_DEMAND_REQUIRES_STOCKOUT_FLAG')
        if not isinstance(row['costs'], dict) or set(row['costs']) != set(COSTS):
            raise ValueError('LOGISTICS_SEVEN_COST_COMPONENTS_REQUIRED')
        for value in row['costs'].values():
            number(value, 0, 1e12)
        if not isinstance(row['deliveries'], list) or len(row['deliveries']) > 10000:
            raise ValueError('LOGISTICS_DELIVERY_BOUND')
        for delivery in row['deliveries']:
            if not isinstance(delivery, dict) or set(delivery) != {'promised_day', 'received_day', 'lead_time'}:
                raise ValueError('LOGISTICS_DELIVERY_SCHEMA')
            integer(delivery['promised_day']); received = integer(delivery['received_day'])
            integer(delivery['lead_time'], 1, 14)
            if received > day:
                raise ValueError('LOGISTICS_FUTURE_DELIVERY_IN_OUTCOME')
        forecast = row['forecast']
        if forecast is not None:
            if not isinstance(forecast, dict) or set(forecast) != {'mean', 'quantiles', 'interval90', 'horizon', 'cutoff'}:
                raise ValueError('LOGISTICS_METRIC_FORECAST_SCHEMA')
            number(forecast['mean'], 0, 1e6)
            if integer(forecast['horizon'], 1, 90) != 1 or integer(forecast['cutoff']) != day-1:
                raise ValueError('LOGISTICS_METRIC_FORECAST_TARGET_OR_LEAKAGE')
            if not isinstance(forecast['quantiles'], dict) or set(forecast['quantiles']) != {'0.1', '0.5', '0.9'}:
                raise ValueError('LOGISTICS_METRIC_QUANTILE_SCHEMA')
            qs = [number(forecast['quantiles'][key], 0, 1e6) for key in ('0.1', '0.5', '0.9')]
            interval = forecast['interval90']
            if not isinstance(interval, list) or len(interval) != 2:
                raise ValueError('LOGISTICS_METRIC_INTERVAL_SCHEMA')
            low, high = (number(value, 0, 1e6) for value in interval)
            if qs != sorted(qs) or not low <= qs[0] <= qs[-1] <= high:
                raise ValueError('LOGISTICS_METRIC_QUANTILE_ORDER')
        rows.append(row)
    rows.sort(key=lambda row: row['day'])
    demand = math.fsum(row['demand'] for row in rows)
    fulfilled = math.fsum(row['fulfilled'] for row in rows)
    average = statistics.fmean(row['on_hand'] for row in rows) if rows else None
    cycles, successful, failed_cycle = 0, 0, False
    for row in rows:
        failed_cycle = failed_cycle or row['stockout']
        if row['cycle_complete']:
            cycles += 1
            successful += int(not failed_cycle)
            failed_cycle = False
    deliveries = [delivery for row in rows for delivery in row['deliveries']]
    durations = [item['lead_time'] for item in deliveries]
    on_time = sum(item['received_day'] <= item['promised_day'] for item in deliveries)
    predicted = [row for row in rows if row['forecast'] is not None]
    errors = [row['forecast']['mean']-row['demand'] for row in predicted]
    mae = statistics.fmean(abs(value) for value in errors) if errors else None
    pinball, calibration = {}, {}
    for level in (.1, .5, .9):
        values = []
        for row in predicted:
            error = row['demand']-row['forecast']['quantiles'][str(level)]
            values.append(max(level*error, (level-1)*error))
        pinball[str(level)] = statistics.fmean(values) if values else None
        calibration[str(level)] = sum(row['demand'] <= row['forecast']['quantiles'][str(level)] for row in predicted)/len(predicted) if predicted else None
    costs = {key: math.fsum(row['costs'][key] for row in rows) for key in COSTS}
    return {'schema_version': 'dragonhydra.logistics-metrics/1', 'cutoff': cutoff,
            'eligible_days': len(rows), 'excluded_future_outcomes': excluded,
            'total_demand': demand, 'immediately_fulfilled_units': fulfilled,
            'fill_rate': fulfilled/demand if demand else None,
            'cycle_service_level': successful/cycles if cycles else None,
            'completed_cycles': cycles, 'successful_cycles': successful,
            'stockout_days': sum(row['stockout'] for row in rows),
            'backordered_units': math.fsum(row['backordered'] for row in rows),
            'lost_sales_units': math.fsum(row['lost_sales'] for row in rows),
            'average_on_hand': average, 'inventory_turns': fulfilled/average if average else None,
            'costs': costs, 'total_cost': math.fsum(costs.values()),
            'completed_deliveries': len(deliveries), 'on_time_deliveries': on_time,
            'on_time_rate': on_time/len(deliveries) if deliveries else None,
            'supplier_reliability': on_time/len(deliveries) if deliveries else None,
            'lead_time_mean': statistics.fmean(durations) if durations else None,
            'lead_time_variance': statistics.pvariance(durations) if durations else None,
            'forecast_count': len(predicted), 'forecast_bias': statistics.fmean(errors) if errors else None,
            'forecast_mae': mae, 'forecast_mase': mae/naive_scale if mae is not None and naive_scale else None,
            'mase_training_scale': naive_scale, 'pinball_loss': pinball,
            'interval90_coverage': sum(row['forecast']['interval90'][0] <= row['demand'] <= row['forecast']['interval90'][1] for row in predicted)/len(predicted) if predicted else None,
            'quantile_empirical_coverage': calibration, 'calibration_status': 'UNVERIFIED_SYNTHETIC',
            'assumptions': ['Fill rate counts immediate units only; later backlog clearing is not counted as immediate fulfillment.',
                            'Cycle success aggregates any stockout since the preceding synchronized cycle completion; trailing incomplete cycles excluded.',
                            'Daily aggregate one-day forecasts must be issued at day-1; five-day policy horizons are not scored against daily demand.',
                            'MASE is defined only with a positive caller-supplied past TRAIN naive-MAE scale, never a test-derived scale.',
                            'Observed daily average inventory and study-horizon turns are not annualized; missing days are not imputed.',
                            'Reliability here means observed completed-delivery on-time fraction, not probability that an outstanding order will arrive.']}
