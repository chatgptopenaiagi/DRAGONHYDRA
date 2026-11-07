"""Measured virtual inventory events: identical cached/reference forecast requests.

No listener, provider, old database, acquisition, or service is used. Output is
one-shot evidence outside source. Wall times include the same instrumentation in
both modes; forecast latency excludes world construction and inventory updates.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
LANE = SOURCE.parent
sys.path.insert(0, str(SOURCE / 'src'))

from dragonhydra.cognitive_logistics import forecast as kernels
from dragonhydra.cognitive_logistics.computation import ForecastCache
from dragonhydra.cognitive_logistics.contracts import COST_KEYS, LOCATIONS, SKU, canonical, digest
from dragonhydra.cognitive_logistics.world import World


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_pins():
    # Pin the transitive mathematical/simulator inputs, including this driver.
    files = sorted((SOURCE/'src/dragonhydra/cognitive_logistics').glob('*.py'))
    files += [SOURCE/'src/dragonhydra/future_relevance/learning.py', Path(__file__).resolve()]
    return {p.relative_to(SOURCE).as_posix(): sha(p) for p in files}


def quantile(values, level):
    """Linear interpolation at (N-1)*q; no Gaussian latency assumption."""
    if not values:
        return None
    ordered = sorted(values); position = (len(ordered)-1)*level
    low = int(position); high = min(low+1, len(ordered)-1)
    return ordered[low]+(ordered[high]-ordered[low])*(position-low)


def latency(values):
    return {'count': len(values), 'median_ms': statistics.median(values),
            'p95_ms': quantile(values,.95), 'p99_ms': quantile(values,.99),
            'maximum_ms': max(values)}


def _run(size, reference):
    cache = ForecastCache(); status = Counter(); operation_counts = Counter()
    checks = []; times = []; cpu_times = []; world_costs = []; acquisition_cost = 0.
    measured_demand = measured_lead = auxiliary_demand = auxiliary_lead = 0
    conserved_events = inventory_rows = 0
    world = held = None
    kernels._poisson_vector.cache_clear()
    wall_start = time.perf_counter(); cpu_start = time.process_time()
    tracemalloc.start()
    original_demand = kernels.forecast_demand; original_lead = kernels.forecast_leadtime
    # Plain counters retain no call argument/history lists and are independent of
    # the cache's own accounting. Both modes incur the same wrapper overhead.
    counters = {'demand':0,'lead':0}
    def demand_call(*args,**kwargs):
        counters['demand'] += 1
        return original_demand(*args,**kwargs)
    def lead_call(*args,**kwargs):
        counters['lead'] += 1
        return original_lead(*args,**kwargs)
    try:
        with patch.object(kernels,'forecast_demand',new=demand_call), \
             patch.object(kernels,'forecast_leadtime',new=lead_call):
            for index in range(size):
                offset = index % 100
                if offset == 0:
                    if world is not None:
                        world_costs.append(world.costs.summary())
                        acquisition_cost += world.spent
                    world = World('stable',400000+index//100,days=5,budget=0.)
                    held = None
                before_rows = len(world.inventory.to_dict()['events'])
                before_demand = counters['demand']; before_lead = counters['lead']
                if (offset+1) % 25 == 0:
                    operation = 'WORLD_STEP'
                    receipt = world.step(acquisition='none')
                    status['accepted'] += 1
                elif held is not None:
                    operation = 'RELEASE'
                    receipt = world.inventory.release(held,world.day)
                    held = None; status['accepted'] += 1
                else:
                    available = world.inventory.summary()['by_location']
                    location = next((loc for loc in ('warehouse','supplier') if available[loc][SKU]['atp']>=1),None)
                    if location is not None:
                        operation = 'RESERVE' if location=='warehouse' else 'RESERVE_SUPPLIER_FALLBACK'
                        held = f'virtual-benchmark-reservation-{index}'
                        receipt = world.inventory.reserve(held,location,SKU,1,world.day)
                        status['accepted'] += 1
                    else:
                        operation = 'RESERVE_SKIPPED_NO_ATP'
                        receipt = {'status':'SKIPPED','reason':'NO_WAREHOUSE_OR_SUPPLIER_ATP',
                                   'day':world.day,'event_index':index}
                        status['skipped_no_atp'] += 1
                operation_counts[operation] += 1
                auxiliary_demand += counters['demand']-before_demand
                auxiliary_lead += counters['lead']-before_lead
                inventory_rows += len(world.inventory.to_dict()['events'])-before_rows
                conservation = world.inventory.verify_conservation(); conserved_events += 1
                snapshot = world.snapshot()
                before_demand = counters['demand']; before_lead = counters['lead']
                start = time.perf_counter(); start_cpu = time.process_time()
                results = {f'{loc}:{h}':cache.demand(snapshot,loc,horizon=h,reference=reference)
                           for loc in LOCATIONS for h in (1,5)}
                results['lead'] = cache.lead(snapshot,reference=reference)
                cpu_times.append((time.process_time()-start_cpu)*1000)
                times.append((time.perf_counter()-start)*1000)
                measured_demand += counters['demand']-before_demand
                measured_lead += counters['lead']-before_lead
                # Compare full distributions and disclosures, not rounded moments.
                checks.append({'index':index,'operation':operation,
                    'input_sha256':digest([operation,receipt,snapshot]),
                    'forecast_sha256':digest(results),
                    'inventory_sha256':digest(world.inventory.summary()),
                    'physical_total':conservation['physical_total']})
            if world is not None:
                world_costs.append(world.costs.summary()); acquisition_cost += world.spent
            total_demand = counters['demand']; total_lead = counters['lead']
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    elapsed = time.perf_counter()-wall_start; cpu = time.process_time()-cpu_start
    independent = measured_demand+measured_lead
    if independent != cache.calls or total_demand != measured_demand+auxiliary_demand or total_lead != measured_lead+auxiliary_lead:
        raise AssertionError('INDEPENDENT_FORECAST_COUNTER_MISMATCH')
    if reference and independent != size*5:
        raise AssertionError('REFERENCE_DID_NOT_RECOMPUTE_EVERY_REQUEST')
    return {'mode':'reference' if reference else 'cached', 'requested_events':size,
        'accepted_inventory_event_requests':status['accepted'],
        'event_status_counts':dict(status), 'operation_counts':dict(operation_counts),
        'inventory_operation_rows':inventory_rows,'conservation_checks':conserved_events,
        'forecast_request_count':size*5,'forecast_calls':independent,'cache_hits':cache.hits,
        'independent_kernel_calls':{'measured_demand':measured_demand,'measured_lead':measured_lead,
            'auxiliary_world_demand':auxiliary_demand,'auxiliary_world_lead':auxiliary_lead,
            'all_demand':total_demand,'all_lead':total_lead},
        'latency_per_five_request_checkpoint':latency(times),
        'cpu_latency_per_five_request_checkpoint':latency(cpu_times),
        'aggregate_wall_seconds':elapsed,'aggregate_cpu_seconds':cpu,
        'requested_events_per_aggregate_wall_second':size/elapsed,
        'tracemalloc_peak_bytes':peak,'acquisition_cost_virtual_credits':acquisition_cost,
        'measurement_computation_cost_virtual_credits':independent*.001,
        'measurement_cost_rule':'0.001 virtual credit per actual demand/lead kernel invocation; benchmark instrumentation is unpriced.',
        'simulated_world_costs':{key:sum(c[key] for c in world_costs) for key in (*COST_KEYS,'total','record_count')},
        'checkpoints_sha256':digest(checks),'checkpoints':checks}


def compare(size):
    cached = _run(size,False); reference = _run(size,True)
    mismatches = [i for i,(a,b) in enumerate(zip(cached['checkpoints'],reference['checkpoints'])) if a != b]
    return {'requested_events':size,'passed':not mismatches,
        'equivalent_input_and_inventory_checkpoints':not mismatches,
        'exact_full_forecast_distributions_equal':not mismatches,
        'mismatch_count':len(mismatches),'first_mismatch_indexes':mismatches[:10],
        'calls_avoided':reference['forecast_calls']-cached['forecast_calls'],
        'cached':cached,'reference':reference}


def self_test():
    assert quantile([0,10],.95)==9.5
    assert quantile([3],.99)==3
    result = compare(4)
    assert result['passed']
    assert result['cached']['forecast_calls']==5
    assert result['reference']['forecast_calls']==20
    assert result['cached']['cache_hits']==15
    assert result['cached']['accepted_inventory_event_requests']==4
    assert result['cached']['operation_counts']=={'RESERVE':2,'RELEASE':2}
    return {'passed':True,'checks':['quantile','four_real_reserve_release_events',
        'exact_input_inventory_distribution_equivalence','independent_actual_call_counts']}


def output_directory(value):
    output = Path(value).absolute()
    evidence = (LANE/'evidence').resolve()
    if not output.resolve().is_relative_to(evidence) or output.resolve()==evidence:
        raise ValueError('BENCHMARK_OUTPUT_MUST_BE_A_FRESH_LANE_EVIDENCE_SUBDIRECTORY')
    for parent in (output,*output.parents):
        if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(),'st_file_attributes',0)&0x400):
            raise ValueError('BENCHMARK_OUTPUT_REPARSE_REJECTED')
    output.mkdir(parents=True,exist_ok=False)
    return output


def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    parser.add_argument('--sizes',type=int,nargs='+',default=[100,1000,10000])
    parser.add_argument('--self-test',action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        print(canonical(self_test())); return 0
    if not args.output or not args.sizes or len(set(args.sizes))!=len(args.sizes) or any(n not in (100,1000,10000) for n in args.sizes):
        parser.error('A fresh --output and distinct --sizes chosen from 100 1000 10000 are required.')
    output = output_directory(args.output); pins = source_pins()
    plan = {'schema_version':'dragonhydra.logistics-benchmark/1','started_at':datetime.now(timezone.utc).isoformat(),
        'synthetic':True,'scope':'IN_MEMORY_INVENTORY_EVENTS_AND_FIVE_FORECAST_REQUESTS_PER_CHECKPOINT',
        'python':platform.python_version(),'sizes':args.sizes,'source_files':pins,
        'cohort_events':100,'world_family':'stable','first_seed':400000,
        'event_rule':'Reserve/release one real warehouse unit, falling back to supplier ATP if warehouse empty; each 25th event performs a genuine World.step; absent ATP at both nodes is explicitly skipped.',
        'workload_revision':'r2: supplier fallback replaces r1 warehouse-empty skips; r1 evidence remains historical.',
        'timing_scope':'Forecast latency excludes world generation, inventory mutation, snapshot, hashing and conservation checks. Aggregate time includes them. Tracemalloc is enabled in both modes.',
        'cpu_timing_limit':'Per-checkpoint process CPU readings may be quantized to 15.625 ms on this Windows host; zero readings do not mean zero computation. Prefer aggregate CPU for workloads shorter than the observed CPU clock quantum.',
        'memory_scope':'Python allocations within each measured mode including simulator, forecast calls, instrumentation, and checkpoint hashes; excludes pre-imports and interpreter/RSS/native allocations.',
        'reference_scope':'External ForecastCache bypass recomputes every requested forecast. Both modes use identical internally cached World.step simulation. This is not service/SQLite/persistence throughput.',
        'order':'cached then reference for each size; internal Poisson LRU reset at each mode start; single run, no speedup significance claim.',
        'external_calls':0,'ai_calls':0,'queue_depth':0,'max_in_flight_events':1,
        'queue_scope':'Synchronous loop with no queue.','parallelism':1,'calibration_state':'UNVERIFIED'}
    write(output/'PLAN.json',plan)
    summaries = []
    try:
        for size in args.sizes:
            if source_pins()!=pins:raise RuntimeError('BENCHMARK_SOURCE_CHANGED')
            result = compare(size)
            for mode in ('cached','reference'):
                value = result[mode]; checkpoints=value.pop('checkpoints')
                path=output/f'{size}-{mode}-checkpoints.json'; write(path,checkpoints)
                value['checkpoint_file']={'name':path.name,'sha256':sha(path)}
            write(output/f'{size}-RESULT.json',result); summaries.append(result)
            print(canonical({'size':size,'passed':result['passed'],
                'cached_calls':result['cached']['forecast_calls'],'reference_calls':result['reference']['forecast_calls'],
                'cached_median_ms':result['cached']['latency_per_five_request_checkpoint']['median_ms'],
                'reference_median_ms':result['reference']['latency_per_five_request_checkpoint']['median_ms']}),flush=True)
            if not result['passed']:raise AssertionError('FORECAST_OR_PHYSICAL_CHECKPOINT_DRIFT')
        if source_pins()!=pins:raise RuntimeError('BENCHMARK_SOURCE_CHANGED')
        write(output/'VERIFICATION.json',{'schema_version':plan['schema_version'],
            'passed':True,'finished_at':datetime.now(timezone.utc).isoformat(),
            'source_files_unchanged':True,'plan_sha256':sha(output/'PLAN.json'),'results':summaries,
            'limitations':['Synthetic stable-family cache workload, not calibrated real supply-chain behavior.',
                'No network, service, SQLite, UI or acquisition latency measured.',
                'Reserve/release mostly leaves forecasting dependencies unchanged by design; real history and clock advance every 25th event.',
                'Computation credit savings use an explicit virtual operation price; no commercial profit or universal latency claim.']})
    except BaseException as exc:
        write(output/'FAILED.json',{'passed':False,'error_type':type(exc).__name__,'message':str(exc),
            'source_files_unchanged':source_pins()==pins,'completed_sizes':[r['requested_events'] for r in summaries]})
        raise
    return 0


if __name__=='__main__':
    raise SystemExit(main())
