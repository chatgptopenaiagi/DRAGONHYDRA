"""Paired direct-kernel acquisition benchmark. No SQLite, HTTP or real data."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
import unittest
from unittest.mock import patch

ROOT = Path(__file__).absolute().parents[1]
LANE = ROOT.parent
SIZES = (100, 1000, 10000)
GIT = r'C:\Program Files\Git\cmd\git.exe'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def reserve_output(path, lane=LANE):
    path, evidence = Path(path).absolute(), Path(lane).absolute() / 'evidence'
    if '..' in path.parts or path == evidence or not path.is_relative_to(evidence):
        raise ValueError('GENESIS61_BENCHMARK_OUTPUT_OUTSIDE_LANE')
    for item in (path, *path.parents):
        if item.exists() and (item.is_symlink() or getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('GENESIS61_BENCHMARK_REPARSE_PATH')
    if path.exists():
        raise ValueError('GENESIS61_BENCHMARK_OUTPUT_ALREADY_EXISTS')
    path.mkdir(parents=True)
    return path


def selected_inputs(root=ROOT):
    paths = list((root / 'src/dragonhydra/future_relevance').glob('*.py'))
    paths += [root / relative for relative in (
        'src/dragonhydra/realtime/models.py', 'src/dragonhydra/realtime/events.py',
        'src/dragonhydra/realtime/worlds.py', 'src/dragonhydra/cognition/models.py',
        'scripts/benchmark_genesis61.py')]
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(paths))}


def check_pins(before, after):
    if before != after:
        raise ValueError('GENESIS61_BENCHMARK_SELECTED_SOURCE_CHANGED')


def quantile(values, fraction):
    if not values or not 0 <= fraction <= 1:
        raise ValueError('BENCHMARK_QUANTILE_INVALID')
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def paired_group_statistics(values):
    groups = defaultdict(list)
    for group, value in values:
        if not isinstance(group, str) or type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('BENCHMARK_PAIR_INVALID')
        groups[group].append(value)
    means = [statistics.fmean(items) for items in groups.values()]
    if not means:
        raise ValueError('BENCHMARK_EMPTY_PAIRS')
    center = statistics.fmean(means)
    se = statistics.stdev(means) / math.sqrt(len(means)) if len(means) > 1 else None
    return {'mean': center, 'standard_error': se,
            'approximate_95_percent_interval': [center - 1.96 * se, center + 1.96 * se] if se is not None else None,
            'root_group_count': len(means), 'decision_count': len(values),
            'method': 'Equal-weight paired root-group means; normal approximation; no multiplicity adjustment.'}


def validate_sizes(sizes):
    if not sizes or len(set(sizes)) != len(sizes) or any(type(n) is not int or n not in SIZES for n in sizes):
        raise ValueError('GENESIS61_BENCHMARK_SIZE_INVALID')
    return tuple(sizes)


def verify_pair(receipts, outcomes, policies):
    if set(receipts) != set(policies) or set(outcomes) != set(policies):
        raise ValueError('GENESIS61_BENCHMARK_POLICY_PAIR_MISSING')
    reference = next(iter(receipts.values()))
    identity = next(iter(outcomes.values()))
    for policy, receipt in receipts.items():
        if (receipt['decision_at'], receipt['target'], receipt['horizon'], receipt['before']['probabilities']) != (
                reference['decision_at'], reference['target'], reference['horizon'], reference['before']['probabilities']):
            raise ValueError('GENESIS61_BENCHMARK_UNEQUAL_INITIAL_INFORMATION')
        if receipt['before']['cutoff'] != receipt['after']['cutoff']:
            raise ValueError('GENESIS61_BENCHMARK_ADVANCED_DECISION_CUTOFF')
        if outcomes[policy] != identity:
            raise ValueError('GENESIS61_BENCHMARK_ACQUISITION_CHANGED_OUTCOME')


def run_case(count, model, *, cost_weight=1., seed=42):
    validate_sizes((count,))
    from dragonhydra.future_relevance.environment import VirtualEpisode, TEST_FAMILIES, OUTCOME_DELAY_MINUTES
    from dragonhydra.future_relevance.learning import validate_model
    from dragonhydra.future_relevance.policies import POLICIES
    from dragonhydra.future_relevance import service as runtime
    frozen = validate_model(model)['content_sha256']
    used_groups = set(model['training_group_ids']) | set(model['selection']['validation_group_ids'])
    metrics = {name: {'latencies': [], 'cpu': [], 'peak_increment_bytes': [], 'rows': [],
                      'kernel_calls': 0, 'acquisitions': 0, 'chooser_calls': 0, 'global_cap_binding': 0,
                      'global_budget_exhausted': 0, 'actions': Counter()} for name in POLICIES}
    spent_by_policy = {name: 0. for name in POLICIES}
    world_seeds = random.Random(seed).sample(range(401000, 499000), math.ceil(max(SIZES) / len(TEST_FAMILIES)))
    condition_hash = hashlib.sha256()
    actual_calls = 0
    original_forecast = runtime.forecast
    def counted_forecast(snapshot):
        nonlocal actual_calls
        actual_calls += 1
        return original_forecast(snapshot)
    started, cpu_started = time.perf_counter(), time.process_time()
    tracemalloc.start()
    try:
        with patch.object(runtime, 'forecast', new=counted_forecast):
            for index in range(count):
                family, world_seed = TEST_FAMILIES[index % len(TEST_FAMILIES)], world_seeds[index // len(TEST_FAMILIES)]
                base = VirtualEpisode(family, world_seed, minute=70, target='GOAL_OCCURRENCE', horizon='10', budget=.12)
                public = base.public()
                if public['group_id'] in used_groups:
                    raise ValueError('GENESIS61_BENCHMARK_TRAIN_TEST_GROUP_LEAKAGE')
                if public['now'] <= model['available_at']:
                    raise ValueError('GENESIS61_BENCHMARK_MODEL_FROM_FUTURE')
                condition_hash.update((canonical([index, public]) + '\n').encode())
                before_world = digest(base.descriptor())
                initial_hash = digest(public)
                pending, receipts, outcomes = {}, {}, {}
                for policy in POLICIES:
                    arm = base.clone()
                    if digest(arm.public()) != initial_hash:
                        raise ValueError('GENESIS61_BENCHMARK_UNCOUPLED_CLONE')
                    before_calls = actual_calls
                    global_remaining = max(0., 100. - spent_by_policy[policy])
                    metrics[policy]['global_cap_binding'] += int(global_remaining < public['budget_remaining'])
                    metrics[policy]['global_budget_exhausted'] += int(global_remaining <= 1e-12)
                    current_bytes = tracemalloc.get_traced_memory()[0]
                    tracemalloc.reset_peak()
                    tick, cpu_tick = time.perf_counter(), time.process_time()
                    receipt = runtime.execute_policy(arm, policy, model if policy == 'learned' else None,
                        request_id=f'virtual-benchmark-{index}-{policy}', expected_revision=public['revision'],
                        cost_weight=cost_weight, acquisition_limit=global_remaining)
                    elapsed, cpu_elapsed = time.perf_counter() - tick, time.process_time() - cpu_tick
                    peak = max(0, tracemalloc.get_traced_memory()[1] - current_bytes)
                    if actual_calls - before_calls != receipt['kernel_calls']:
                        raise ValueError('GENESIS61_BENCHMARK_KERNEL_ACCOUNTING_MISMATCH')
                    if receipt['computation_units'] != receipt['kernel_calls'] or not math.isclose(
                            receipt['computation_cost'], .001 * receipt['kernel_calls'], abs_tol=1e-12):
                        raise ValueError('GENESIS61_BENCHMARK_COMPUTATION_COST_MISMATCH')
                    cost = math.fsum(row['actual_cost'] for row in receipt['acquisitions'])
                    if (not math.isclose(receipt['acquisition_cost'], cost, abs_tol=1e-12) or
                            cost > min(public['budget_remaining'], global_remaining) + 1e-12):
                        raise ValueError('GENESIS61_BENCHMARK_ACQUISITION_ACCOUNTING_MISMATCH')
                    spent_by_policy[policy] += cost
                    if spent_by_policy[policy] > 100. + 1e-12:
                        raise ValueError('GENESIS61_BENCHMARK_GLOBAL_BUDGET_EXCEEDED')
                    metric = metrics[policy]
                    metric['latencies'].append(elapsed * 1000)
                    metric['cpu'].append(cpu_elapsed)
                    metric['peak_increment_bytes'].append(peak)
                    metric['kernel_calls'] += receipt['kernel_calls']
                    metric['acquisitions'] += len(receipt['acquisitions'])
                    metric['chooser_calls'] += receipt['policy_estimation_units']
                    metric['actions'].update(action['action'] for action in receipt['actions'])
                    pending[policy], receipts[policy] = arm, receipt
                # No label is requested until ALL five policy decisions finish.
                for policy, arm in pending.items():
                    snapshot = arm.public()
                    arm.advance(max(0, snapshot['target_maturity_minute'] + OUTCOME_DELAY_MINUTES - snapshot['now_minute']) + 1e-9)
                    outcome = arm.matured_outcome()
                    outcomes[policy] = (outcome['outcome_id'], outcome['label'], outcome['available_at'])
                    evaluation = runtime.evaluate_decision(receipts[policy], outcome)
                    receipt = receipts[policy]
                    metrics[policy]['rows'].append({'episode_id': public['episode_id'], 'group_id': public['group_id'],
                        'evaluation_family': family,
                        'brier_before': evaluation['before']['brier'], 'brier_after': evaluation['after']['brier'],
                        'log_loss': evaluation['after']['log_loss'],
                        'acquisition_cost': receipt['acquisition_cost'], 'computation_cost': receipt['computation_cost'],
                        'net_usefulness': evaluation['net_usefulness'],
                        'absolute_utility': -evaluation['after']['brier'] - cost_weight * (receipt['acquisition_cost'] + receipt['computation_cost']),
                        'decision_sha256': digest({k: v for k, v in receipt.items() if k not in ('latency_ms', 'cpu_ms')})})
                verify_pair(receipts, outcomes, POLICIES)
                if digest(base.descriptor()) != before_world:
                    raise ValueError('GENESIS61_BENCHMARK_BASE_WORLD_MUTATED')
    finally:
        tracemalloc.stop()
    wall, cpu = time.perf_counter() - started, time.process_time() - cpu_started
    if validate_model(model)['content_sha256'] != frozen:
        raise ValueError('GENESIS61_BENCHMARK_FROZEN_MODEL_CHANGED')
    baseline = {row['episode_id']: row for row in metrics['acquire_none']['rows']}
    comparisons = []
    for policy, metric in metrics.items():
        rows, times = metric['rows'], metric['latencies']
        if len(rows) != count:
            raise ValueError('GENESIS61_BENCHMARK_ACTUAL_DECISION_COUNT_MISMATCH')
        comparisons.append({'policy': policy, 'actual_decisions': len(rows),
            'latency_ms': {'p50': quantile(times, .5), 'p95': quantile(times, .95), 'p99': quantile(times, .99),
                           'mean': statistics.fmean(times), 'maximum': max(times)},
            'decision_wall_seconds': math.fsum(times) / 1000, 'decision_cpu_seconds': math.fsum(metric['cpu']),
            'maximum_incremental_traced_decision_bytes': max(metric['peak_increment_bytes']),
            'actual_kernel_calls': metric['kernel_calls'], 'computation_units': metric['kernel_calls'],
            'actual_acquisitions': metric['acquisitions'], 'action_counts': dict(metric['actions']),
            'policy_chooser_calls': metric['chooser_calls'],
            'global_acquisition_budget': 100., 'global_acquisition_spent': spent_by_policy[policy],
            'global_acquisition_remaining': max(0., 100. - spent_by_policy[policy]),
            'global_cap_binding_decisions': metric['global_cap_binding'],
            'global_budget_exhausted_decisions': metric['global_budget_exhausted'],
            'acquisition_credits': math.fsum(row['acquisition_cost'] for row in rows),
            'computation_credits': math.fsum(row['computation_cost'] for row in rows),
            'brier_before': statistics.fmean(row['brier_before'] for row in rows),
            'brier_after': statistics.fmean(row['brier_after'] for row in rows),
            'log_loss': None if any(row['log_loss'] is None for row in rows) else statistics.fmean(row['log_loss'] for row in rows),
            'log_loss_infinite_count': sum(row['log_loss'] is None for row in rows),
            'mean_net_usefulness': statistics.fmean(row['net_usefulness'] for row in rows),
            'mean_absolute_utility': statistics.fmean(row['absolute_utility'] for row in rows),
            'positive_pre_cost_but_negative_net_count': sum(row['brier_before'] > row['brier_after'] and row['net_usefulness'] < 0 for row in rows),
            'paired_brier_improvement_vs_none': paired_group_statistics([(row['group_id'], baseline[row['episode_id']]['brier_after'] - row['brier_after']) for row in rows]),
            'paired_net_utility_improvement_vs_none': paired_group_statistics([(row['group_id'], row['absolute_utility'] - baseline[row['episode_id']]['absolute_utility']) for row in rows]),
            'metrics_by_heldout_family': {family: {
                'actual_decisions': sum(row['evaluation_family'] == family for row in rows),
                'brier_after': statistics.fmean(row['brier_after'] for row in rows if row['evaluation_family'] == family),
                'mean_net_usefulness': statistics.fmean(row['net_usefulness'] for row in rows if row['evaluation_family'] == family),
                'paired_net_utility_improvement_vs_none': paired_group_statistics([
                    (row['group_id'], row['absolute_utility'] - baseline[row['episode_id']]['absolute_utility'])
                    for row in rows if row['evaluation_family'] == family])} for family in TEST_FAMILIES},
            'decision_trace_sha256': digest(rows)})
    return {'actual_decisions_per_policy': count, 'total_actual_decisions': count * len(POLICIES),
            'policies': comparisons, 'coupled_conditions_sha256': condition_hash.hexdigest(),
            'actual_total_kernel_calls': actual_calls, 'case_wall_seconds_including_worlds_and_scoring': wall,
            'case_cpu_seconds_including_worlds_and_scoring': cpu,
            'model_content_sha256': frozen, 'target': 'GOAL_OCCURRENCE', 'horizon': '10', 'minute': 70,
            'budget_per_episode': .12, 'global_acquisition_budget_per_policy': 100., 'cost_weight': cost_weight,
            'memory_scope': 'Maximum traced allocation peak above each decision-entry baseline; bookkeeping and tracing overhead remain; not RSS.'}


def load_model_cache(path, pins, seed, training_cases, cost_weight):
    """Reuse only a completed, source-identical canary's sealed virtual model."""
    from dragonhydra.future_relevance.learning import validate_model
    path = Path(path).absolute()
    if not path.is_relative_to(LANE / 'evidence') or path.name != 'MODEL.json':
        raise ValueError('BENCHMARK_CACHE_OUTSIDE_EVIDENCE')
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('BENCHMARK_CACHE_REPARSE_PATH')
    previous = json.loads(path.with_name('BENCHMARK.json').read_text(encoding='utf-8'))
    if (previous['status'] != 'PASS' or previous['source']['selected_inputs_sha256'] != pins
            or previous['experiment_seed'] != seed or previous['training_cases_per_family'] != training_cases
            or any(case['cost_weight'] != cost_weight for case in previous['cases'])):
        raise ValueError('BENCHMARK_CACHE_PROVENANCE_MISMATCH')
    model = validate_model(json.loads(path.read_text(encoding='utf-8')))
    if not previous['cases'] or any(case['model_content_sha256'] != model['content_sha256'] for case in previous['cases']):
        raise ValueError('BENCHMARK_CACHE_MODEL_MISMATCH')
    return {'model': model, 'training_summary': previous['model_preparation']}


def run(output, sizes=SIZES, *, seed=42, training_cases=40, cost_weight=1., model_cache=None):
    sizes = validate_sizes(sizes)
    output = reserve_output(output)
    before = selected_inputs()
    commit = subprocess.check_output([GIT, '--no-optional-locks', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output([GIT, '--no-optional-locks', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip())
    report = {'schema_version': 'dragonhydra.genesis61-benchmark/1', 'status': 'RUNNING', 'synthetic': True,
              'source': {'commit': commit, 'working_tree_has_changes': dirty, 'selected_inputs_sha256': before},
              'scope': 'DIRECT_EXECUTE_POLICY; NO_SQLITE_HTTP_BROWSER_OR_SCM', 'cases': [],
              'experiment_seed': seed, 'training_cases_per_family': training_cases,
              'random_policy_seed': 42, 'global_acquisition_budget_per_policy': 100.,
              'real_api_calls': 0, 'real_sporting_records': 0}
    write_new(output / 'PLAN.json', report)
    try:
        from dragonhydra.future_relevance.experiments import train_model
        with (patch.object(socket, 'socket', side_effect=AssertionError('NETWORK_FORBIDDEN')),
              patch.object(sqlite3, 'connect', side_effect=AssertionError('DIRECT_BENCHMARK_MUST_NOT_OPEN_SQLITE'))):
            start, cpu = time.perf_counter(), time.process_time()
            trained = (load_model_cache(model_cache, before, seed, training_cases, cost_weight) if model_cache
                       else train_model(seed=seed, cases=training_cases, cost_weight=cost_weight))
            report['model_preparation'] = {'wall_seconds': time.perf_counter()-start, 'cpu_seconds': time.process_time()-cpu,
                                         **trained['training_summary'], 'final_test_constructed': False}
            report['model_preparation']['reused_completed_canary_model'] = bool(model_cache)
            if model_cache:
                report['model_preparation']['cache_model_path'] = str(Path(model_cache).absolute())
                report['model_preparation']['cache_model_sha256'] = hashlib.sha256(Path(model_cache).read_bytes()).hexdigest()
            write_new(output / 'MODEL.json', trained['model'])
            check_pins(before, selected_inputs())
            for size in sizes:
                report['cases'].append(run_case(size, trained['model'], cost_weight=cost_weight, seed=seed))
                check_pins(before, selected_inputs())
        report['status'] = 'PASS'
    except Exception as exc:
        report.update(status='FAILED', failure_type=type(exc).__name__, failure=str(exc)[:300])
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['limitations'] = ['All worlds and costs are virtual; no real quality, money or token usage is measured.',
            'The fixed policy order, tracing and call-counting wrapper add measurement overhead.',
            'One model and shared numeric caches are reused; these are not independent cold-cache trials.',
            'Decision latency excludes world construction/cloning and oracle scoring; case aggregate includes them.',
            'No SQLite is opened; these results are not journal, API, browser or database throughput.',
            'Paired root-group normal intervals are finite synthetic uncertainty without multiplicity correction.',
            'Negative learned-policy results and post-cost reversals remain valid outcomes.']
        write_new(output / 'BENCHMARK.json', report)
    return report


class BenchmarkGuards(unittest.TestCase):
    def test_sizes_reject_unbounded_duplicate_and_boolean_inputs(self):
        self.assertEqual(validate_sizes([100, 1000, 10000]), SIZES)
        for sizes in ([], [1], [100, 100], [True], [1000000]):
            with self.assertRaises(ValueError): validate_sizes(sizes)

    def test_quantiles_and_negative_paired_utility_are_not_clipped(self):
        self.assertEqual(quantile([0, 10], .95), 9.5)
        result = paired_group_statistics([('a', -1.), ('a', -1.), ('b', -3.)])
        self.assertEqual(result['mean'], -2.)
        self.assertEqual(result['root_group_count'], 2)
        self.assertEqual(result['standard_error'], 1.)

    def test_pairing_rejects_unequal_information_or_outcomes(self):
        row = {'decision_at': 'virtual-time', 'target': 'GOAL_OCCURRENCE', 'horizon': '10',
               'before': {'probabilities': {'goal': .2}, 'cutoff': 'virtual-time'}, 'after': {'cutoff': 'virtual-time'}}
        from copy import deepcopy
        receipts, outcomes = {'a': deepcopy(row), 'b': deepcopy(row)}, {'a': ('same', 'goal'), 'b': ('same', 'goal')}
        verify_pair(receipts, outcomes, ('a', 'b'))
        outcomes['b'] = ('same', 'no_goal')
        with self.assertRaisesRegex(ValueError, 'CHANGED_OUTCOME'): verify_pair(receipts, outcomes, ('a', 'b'))
        outcomes['b'] = outcomes['a']; receipts['b']['before']['probabilities'] = {'goal': .3}
        with self.assertRaisesRegex(ValueError, 'UNEQUAL_INITIAL'): verify_pair(receipts, outcomes, ('a', 'b'))

    def test_changed_source_and_reused_output_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SELECTED_SOURCE_CHANGED'): check_pins({'a': '1'}, {'a': '2'})
        with tempfile.TemporaryDirectory(prefix='genesis61-benchmark-guards-') as temporary:
            lane = Path(temporary)
            path = reserve_output(lane / 'evidence' / 'new', lane)
            with self.assertRaisesRegex(ValueError, 'ALREADY_EXISTS'): reserve_output(path, lane)
            with self.assertRaisesRegex(ValueError, 'OUTSIDE_LANE'): reserve_output(lane / 'outside', lane)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--sizes', nargs='+', type=int, default=list(SIZES))
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--training-cases', type=int, default=40)
    parser.add_argument('--cost-weight', type=float, default=1.)
    parser.add_argument('--model-cache', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BenchmarkGuards))
        return 0 if result.wasSuccessful() else 1
    if args.output is None: parser.error('--output is required')
    sys.path.insert(0, str(ROOT / 'src'))
    result = run(args.output, args.sizes, seed=args.seed, training_cases=args.training_cases,
                 cost_weight=args.cost_weight, model_cache=args.model_cache)
    print(json.dumps({'status': result['status'], 'case_sizes': list(args.sizes), 'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
