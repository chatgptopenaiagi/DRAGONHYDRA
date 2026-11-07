"""Registered bounded numerical investigations; never execute generated code."""
from copy import deepcopy
import math
import statistics
import time

from .contracts import LOCATIONS, canonical, digest
from .forecast import METHODS, combine_demand, forecast_demand, rescale_demand
from .metrics import FIELDS, evaluate_outcomes
from .policies import COSTS

ANALYSES = ('compare_methods', 'bounded_method_search', 'counterfactual')
TRANSFORMS = (('sba-scale-080/1', 'scale', .8), ('sba-scale-120/1', 'scale', 1.2),
              ('naive-ses-blend-025/1', 'blend', .25), ('naive-ses-blend-050/1', 'blend', .5),
              ('naive-ses-blend-075/1', 'blend', .75))
INTERVENTIONS = (('supplier_delay', 2), ('capacity_reduction', .75), ('demand_shock', 1.5),
                 ('policy_change', 'base_stock'), ('shelf_life', 8))


def registered_methods():
    return [{'configuration_id': 'logistics-' + method + '/1', 'kind': 'baseline', 'method': method} for method in METHODS] + [
        {'configuration_id': 'logistics-' + identifier, 'kind': kind, 'parameter': parameter} for identifier, kind, parameter in TRANSFORMS]


def select_next_experiment(snapshot):
    """Past-only uncertainty heuristic, not calibrated information gain."""
    day = snapshot['day']
    rows = [row for location in LOCATIONS for row in snapshot['history'][location]
            if row['day'] <= day and row['available_day'] <= day]
    uncensored = [row['sales'] for row in rows if not row['censored']]
    censor_fraction = sum(row['censored'] for row in rows)/len(rows) if rows else 0.
    variation = statistics.pvariance(uncensored) if len(uncensored) > 1 else None
    past_lead = [row['received_day']-row['ordered_day'] for row in snapshot['completed_leadtimes']
                 if row['received_day'] <= day and row['available_day'] <= day]
    lead_variance = statistics.pvariance(past_lead) if len(past_lead) > 1 else None
    if not rows:
        name, reason = 'cold-start-evidence/1', 'No eligible history; collect and mature fictional observations before method selection.'
    elif censor_fraction >= .15:
        name, reason = 'censor-aware-versus-omission/1', 'Observed censoring warrants an untouched comparison of lower-bound likelihood and omission baselines.'
    elif lead_variance is not None and lead_variance >= 2:
        name, reason = 'registered-supplier-delay/1', 'Past completed lead-time variability warrants a controlled virtual delay study.'
    elif variation is not None and variation > max(1., statistics.fmean(uncensored)):
        name, reason = 'intermittent-methods/1', 'Past uncensored variation warrants a fresh Croston/SBA/TSB/censored-Poisson comparison.'
    else:
        name, reason = 'registered-demand-shock/1', 'Limited observed variation does not prove robustness; use a new held-out virtual shock cohort.'
    return {'experiment_id': 'logistics-experiment-' + name, 'status': 'PROPOSED_NOT_EXECUTED',
            'reason': reason, 'decision_cutoff': day, 'criterion': 'Bounded past variance/censoring heuristic',
            'past_statistics': {'eligible_rows': len(rows), 'censored_fraction': censor_fraction,
                                'uncensored_sales_variance': variation, 'completed_lead_variance': lead_variance},
            'calibrated_information_gain': None, 'automatic_acquisition_or_adoption': False}


def _origins(snapshot):
    cutoff = snapshot['day']
    # At most five past target dates and two retailers. No privileged demand labels.
    dates = sorted({row['day'] for loc in LOCATIONS for row in snapshot['history'][loc]
                    if 7 <= row['day'] <= cutoff and row['available_day'] <= cutoff and not row['censored']})[-5:]
    training_dates = set(dates[:max(1, len(dates)*2//3)])
    cases = []
    for day in dates:
        for loc in LOCATIONS:
            matches = [row for row in snapshot['history'][loc] if row['day'] == day and row['available_day'] <= cutoff and not row['censored']]
            if len(matches) > 1:
                raise ValueError('LOGISTICS_ANALYTICS_DUPLICATE_LABEL')
            if matches:
                cases.append({'location': loc, 'target_day': day, 'label': matches[0]['sales'],
                              'label_available_day': matches[0]['available_day'],
                              'split': 'TRAIN' if day in training_dates else 'VALIDATION'})
    return cases


def _compare(snapshot, search, counts):
    cases = _origins(snapshot)
    configs = registered_methods() if search else registered_methods()[:len(METHODS)]
    memo, results = {}, []
    def base(case, method):
        key = case['location'], case['target_day'], method
        if key not in memo:
            counts['forecast_calls'] += 1
            memo[key] = forecast_demand(snapshot['history'][case['location']], method=method, horizon=1, cutoff=case['target_day']-1)
        return memo[key]
    for config in configs:
        observations, failures = [], []
        for case in cases:
            counts['candidate_evaluations'] += 1
            try:
                if config['kind'] == 'baseline':
                    prediction = base(case, config['method'])
                elif config['kind'] == 'scale':
                    source = base(case, 'sba')
                    counts['probability_rebuilds'] += 1
                    prediction = rescale_demand(source, config['parameter'])
                else:
                    weight = config['parameter']
                    a, b = base(case, 'naive'), base(case, 'ses')
                    counts['probability_rebuilds'] += 1
                    left = rescale_demand(a, weight)
                    counts['probability_rebuilds'] += 1
                    right = rescale_demand(b, 1-weight)
                    counts['probability_rebuilds'] += 1
                    prediction = combine_demand([left, right])
                error = prediction['mean']-case['label']
                pinball = {}
                for level in (.1, .5, .9):
                    residual = case['label']-prediction['quantiles'][str(level)]
                    pinball[str(level)] = max(level*residual, (level-1)*residual)
                observations.append({'split': case['split'], 'absolute_error': abs(error), 'bias': error, 'pinball': pinball})
            except (ValueError, TypeError, KeyError) as error:
                failures.append({'location': case['location'], 'target_day': case['target_day'], 'reason': str(error)[:160]})
        split_results = {}
        for split in ('TRAIN', 'VALIDATION'):
            selected = [item for item in observations if item['split'] == split]
            split_results[split] = {'forecast_count': len(selected),
                'mae': statistics.fmean(item['absolute_error'] for item in selected) if selected else None,
                'bias': statistics.fmean(item['bias'] for item in selected) if selected else None,
                'pinball_loss': {str(level): statistics.fmean(item['pinball'][str(level)] for item in selected) if selected else None for level in (.1, .5, .9)}}
        results.append({'configuration': deepcopy(config), 'status': 'FAILED' if failures else 'EVALUATED' if observations else 'NOT_ELIGIBLE',
                        'splits': split_results, 'failures': failures, 'nonimproving_vs_sba_validation': None})
    baseline = next(item for item in results if item['configuration'].get('method') == 'sba')
    baseline_mae = baseline['splits']['VALIDATION']['mae']
    for item in results:
        score = item['splits']['VALIDATION']['mae']
        if score is not None and baseline_mae is not None:
            item['validation_mae_improvement_vs_sba'] = baseline_mae-score
            item['nonimproving_vs_sba_validation'] = score >= baseline_mae
    eligible = [item for item in results if item['status'] == 'EVALUATED' and item['splits']['TRAIN']['mae'] is not None
                and item['splits']['VALIDATION']['mae'] is not None]
    best = min(eligible, key=lambda item: (item['splits']['VALIDATION']['mae'], item['configuration']['configuration_id'])) if eligible else None
    return results, {'eligible_cases': len(cases), 'evaluation_targets': [{'location': case['location'], 'target_day': case['target_day'],
        'forecast_cutoff': case['target_day']-1, 'label_available_day': case['label_available_day'], 'split': case['split']} for case in cases],
        'selected_configuration': deepcopy(best['configuration']) if best else None, 'adopted': False,
        'selection_rule': 'Fixed registered candidates, expanding past-only origins; select on chronological past VALIDATION MAE.',
        'heldout_test': 'NOT_RUN; these past diagnostics do not estimate unbiased future performance.',
        'label_scope': 'Eligible uncensored observed sales only; no hidden actual censored demand label is used.'}


def _future_window(clone, original, counts):
    start_rows = len(clone.outcomes)
    before_cost = clone.costs.summary()
    steps = min(5, clone.end_day-clone.day)
    for _ in range(steps):
        start_decisions, start_calls, start_day = len(clone.decisions), clone.cache.calls, clone.day
        counts['world_step_attempts'] += 1
        try:
            clone.step()
        finally:
            counts['world_steps'] += clone.day-start_day
            counts['world_forecast_cache_misses'] += clone.cache.calls-start_calls
            added_decisions = clone.decisions[start_decisions:]
            counts['optimization_candidates'] += sum(row['optimization_candidates'] for row in added_decisions)
            counts['routing_calls'] += sum(row['routing_calls'] for row in added_decisions)
    suffix = clone.outcomes[start_rows:]
    result = evaluate_outcomes([{key: row[key] for key in FIELDS} for row in suffix], cutoff=clone.day)
    result['completed_delivery_on_time_rate'] = result['on_time_rate']
    result['supplier_reliability_scope'] = 'COMPLETED_WINDOW_DELIVERIES_ONLY_NOT_ALL_DUE_ORDERS'
    # Carry pre-window cycle failures so a partial initial cycle is not reset to success.
    failed, completed, successful = False, 0, 0
    for row in original.outcomes:
        failed = failed or row['stockout']
        if row['cycle_complete']:
            failed = False
    for row in suffix:
        failed = failed or row['stockout']
        if row['cycle_complete']:
            completed += 1; successful += int(not failed); failed = False
    result.update(completed_cycles=completed, successful_cycles=successful,
                  cycle_service_level=successful/completed if completed else None)
    after_cost = clone.costs.summary()
    result['costs'] = {key: after_cost[key]-before_cost[key] for key in COSTS}
    result['total_cost'] = math.fsum(result['costs'].values())
    return result, steps


def _counterfactual(world, counts):
    if world.day >= world.end_day:
        return [], {'status': 'NOT_ELIGIBLE', 'reason': 'No future simulation window remains.'}
    base = world.clone()
    baseline, steps = _future_window(base, world, counts)
    rows = []
    for kind, amount in INTERVENTIONS:
        branch = world.clone()
        if branch.group_id != world.group_id:
            raise ValueError('LOGISTICS_COUNTERFACTUAL_GROUP_CHANGED')
        before_revision = branch.revision
        try:
            receipt = branch.intervene(kind, amount)
            result, branch_steps = _future_window(branch, world, counts)
            rows.append({'intervention': {'kind': kind, 'amount': amount}, 'status': 'TESTED',
                         'intervention_receipt': receipt, 'horizon_days': branch_steps,
                         'metrics': result, 'cost_difference_vs_baseline': result['total_cost']-baseline['total_cost'],
                         'fill_rate_difference': result['fill_rate']-baseline['fill_rate'] if result['fill_rate'] is not None and baseline['fill_rate'] is not None else None,
                         'original_clone_revision': before_revision,
                         'classification': 'TESTED_INTERVENTION_IN_SIMULATION',
                         'causal_scope': 'Conditional effect of the registered virtual mechanism under the same seeded exogenous streams; no real-world causal claim.'})
        except ValueError as error:
            rows.append({'intervention': {'kind': kind, 'amount': amount}, 'status': 'REJECTED_OR_FAILED', 'reason': str(error)[:200]})
    return rows, {'status': 'TESTED', 'horizon_days': steps, 'baseline_metrics': baseline,
                  'group_id': world.group_id, 'same_exogenous_streams': True,
                  'limitation': 'Demand shocks intentionally change demand; common simulator streams do not mean identical outcomes or independent replicated worlds.'}


def analyze(world, method='compare_methods'):
    if method not in ANALYSES:
        raise ValueError('LOGISTICS_REGISTERED_ANALYSIS_REQUIRED')
    from .world import World
    if not isinstance(world, World):
        raise ValueError('LOGISTICS_TRUSTED_VIRTUAL_WORLD_REQUIRED')
    before = digest(world.to_dict())
    snapshot = world.snapshot()
    counts = {'forecast_calls': 0, 'probability_rebuilds': 0, 'candidate_evaluations': 0,
              'world_steps': 0, 'world_step_attempts': 0, 'world_forecast_cache_misses': 0, 'optimization_candidates': 0, 'routing_calls': 0}
    started, cpu = time.perf_counter(), time.process_time()
    try:
        experiment = select_next_experiment(snapshot)
        candidates, counterfactuals = [], []
        if method == 'counterfactual':
            counterfactuals, mathematics = _counterfactual(world, counts)
            summary = 'Registered five-day virtual interventions compared with one paired baseline; rejected cases remain visible.'
        else:
            candidates, mathematics = _compare(snapshot, method == 'bounded_method_search', counts)
            summary = 'Past-only rolling count forecasts evaluated; fixed candidates and nonimproving results retained; no method automatically adopted.'
        result = {'schema_version': 'dragonhydra.logistics-analysis/1', 'method': method, 'status': 'COMPLETED',
                  'synthetic': True, 'source_mode': 'VIRTUAL', 'cutoff': snapshot['day'], 'episode_id': snapshot['episode_id'],
                  'summary': summary, 'observed_facts': [{'classification': 'OBSERVED_FACT_IN_SIMULATION',
                      'name': 'available_history_counts', 'value': {loc: sum(row['day'] <= snapshot['day'] and row['available_day'] <= snapshot['day'] for row in snapshot['history'][loc]) for loc in LOCATIONS}}],
                  'mathematical_results': {'classification': 'MATHEMATICAL_RESULT', **mathematics},
                  'hypotheses': [{'classification': 'HYPOTHESIS_UNTESTED', 'text': 'A proposed method or intervention may behave differently on a new untouched virtual cohort; current diagnostics are not proof of transfer.'}],
                  'candidates': candidates, 'counterfactuals': counterfactuals, 'selected_next_experiment': experiment,
                  'actual_computations': counts,
                  'priced_work_counters': [key for key in counts if key != 'world_steps'],
                  'computation_units': sum(value for key, value in counts.items() if key != 'world_steps'),
                  'original_world_sha256': before, 'original_unchanged': digest(world.to_dict()) == before,
                  'limitations': ['Only registered fixed computations execute; no generated Python, shell, network or AI tool runs.',
                      'At most five past origins and two retailers; tiny chronological TRAIN/VALIDATION is exploratory, not held-out qualification.',
                      'Count PMFs are declared uncalibrated; censored target sales cannot reveal true demand.',
                      'Work units count unlike explicit operations and are a virtual pricing proxy, not measured hardware or token cost; completed steps are an audit subtotal, not billed a second time.',
                      'The selected next experiment uses past variance/censoring only; it is proposed, not executed or calibrated information gain.']}
        result['analysis_id'] = 'virtual-logistics-analysis-' + digest(result)[:28]
        result['latency_ms'] = (time.perf_counter()-started)*1000
        result['cpu_ms'] = (time.process_time()-cpu)*1000
        canonical(result)
        return result
    finally:
        if digest(world.to_dict()) != before:
            raise ValueError('LOGISTICS_ANALYSIS_MODIFIED_ORIGINAL_WORLD')
