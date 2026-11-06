"""Identical-input local synthetic ingestion benchmark; no live interfaces."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT.parent
MATCH = "virtual-benchmark-research"
EPOCH = datetime(2035, 1, 1, 12, tzinfo=timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def event_stream(count):
    """Each size is a prefix of the same fixture, independent of execution mode."""
    if type(count) is not int or count not in (100, 1000, 10000):
        raise ValueError("BENCHMARK_SIZE_INVALID")
    from dragonhydra.realtime.events import SCHEMA, validate_event
    events, minute = [], 0.0
    for sequence in range(1, count + 1):
        participant, attributes = "NONE", {}
        if sequence == 1:
            kind = "KICKOFF"
            attributes = {"duration_minutes": 90, "period_end_minute": 45,
                          "home_team": "Vector Town", "away_team": "Orbit Athletic"}
        elif sequence == 2:
            kind, minute = "RESUME", 45.0
            attributes = {"period": 2, "period_end_minute": 90}
        elif sequence % 100 == 0:
            kind, minute = "CLOCK", 45 + (sequence // 100) * 0.4
            attributes = {"period": 2, "period_end_minute": 90, "end_time_known": True}
        elif sequence in (701, 1801, 4901, 7001):
            kind, participant = "GOAL", "HOME" if sequence in (701, 4901) else "AWAY"
        elif sequence == 3501:
            kind, participant = "RED_CARD", "HOME"
        else:
            kind = "POSSESSION"
            attributes = {"home_percent": 30 + sequence % 41}
        instant = EPOCH + timedelta(minutes=minute, microseconds=sequence * 1000)
        stamp = instant.isoformat(timespec="microseconds").replace("+00:00", "Z")
        received = (instant + timedelta(milliseconds=10)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        events.append(validate_event({"schema_version": SCHEMA, "event_id": "virtual-benchmark-event-" + str(sequence),
                      "source_id": "virtual-benchmark-source", "match_id": MATCH, "event_type": kind,
                      "event_time": stamp, "received_at": received, "sequence": sequence, "revision": 1,
                      "participant": participant, "attributes": {"minute": minute, **attributes},
                      "source_mode": "DEMONSTRATION", "quality_state": "VALIDATED"}))
    return events


def quantile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def scalar_forecast(wrapper):
    if not isinstance(wrapper, dict) or not isinstance(wrapper.get("forecast"), dict):
        raise ValueError("BENCHMARK_CURRENT_FORECAST_MISSING")
    forecast = wrapper["forecast"]
    return {"full_time_result": forecast["full_time_result"],
            "horizons": {key: {name: value for name, value in horizon.items() if name != "score_distribution"}
                         for key, horizon in forecast["horizons"].items()}}


def difference(left, right):
    if type(left) in (int, float) and type(right) in (int, float):
        return abs(left - right)
    if isinstance(left, dict) and isinstance(right, dict):
        if left.keys() != right.keys():
            raise ValueError("BENCHMARK_FORECAST_STRUCTURE_MISMATCH")
        return max((difference(left[key], right[key]) for key in left), default=0.0)
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            raise ValueError("BENCHMARK_FORECAST_STRUCTURE_MISMATCH")
        return max((difference(a, b) for a, b in zip(left, right)), default=0.0)
    if type(left) is not type(right) or left != right:
        raise ValueError("BENCHMARK_FORECAST_VALUE_MISMATCH")
    return 0.0


def source_identity():
    git = Path(r"C:\Program Files\Git\cmd\git.exe")
    head = subprocess.run([str(git), "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()
    status = subprocess.run([str(git), "status", "--porcelain"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout
    paths = sorted((ROOT / "src" / "dragonhydra" / "realtime").glob("*.py")) + [Path(__file__).resolve()]
    return {"git_head": head, "working_tree_has_changes": bool(status),
            "selected_input_sha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in paths}}


def checkpoints(count):
    return {1, 2, count} | set(range(100, count + 1, 100)) | {
        value for value in (701, 702, 1801, 1802, 3501, 3502, 4901, 4902, 7001, 7002) if value <= count}


def run_mode(events, directory, force_recompute):
    from dragonhydra.realtime import models
    from dragonhydra.realtime.service import RealtimeService
    for function in (models._poisson, models._joint, models._outcomes):
        function.cache_clear()
    config = {"auto_investigate": False, "force_recompute": force_recompute, "persist_dense": False}
    tracemalloc.start()
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    service = RealtimeService(directory, config=config)
    service.store.create_match(MATCH)
    latency, snapshots = [], {}
    points = checkpoints(len(events))
    for number, event in enumerate(events, 1):
        started = time.perf_counter()
        service.ingest(event)
        latency.append((time.perf_counter() - started) * 1000)
        if number in points:
            wrapper = service.store.current_forecast(MATCH)
            snapshots[number] = {"forecast": scalar_forecast(wrapper),
                                 "forecast_state_revision": wrapper["state_revision"]}
        if number % 1000 == 0:
            print(json.dumps({"progress": number, "count": len(events), "force_recompute": force_recompute}), flush=True)
    elapsed, cpu = time.perf_counter() - start_wall, time.process_time() - start_cpu
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    metrics = service.store.metrics()
    runtime_metrics = service.status()["metrics"]
    state = service.store.state(MATCH)
    if state["revision"] != len(events) or metrics.get("events_accepted", 0) != len(events):
        raise ValueError("BENCHMARK_EVENTS_NOT_ALL_ACCEPTED")
    ai = metrics.get("ai_investigations", 0)
    if ai:
        raise ValueError("BENCHMARK_AI_WAS_NOT_DISABLED")
    if source_identity()["selected_input_sha256"] != run_mode.expected_source:
        raise ValueError("BENCHMARK_INPUT_SOURCE_CHANGED")
    actual_updates = metrics.get("forecast_updates", 0)
    if force_recompute and actual_updates != len(events):
        raise ValueError("BENCHMARK_FORCED_RECOMPUTE_NOT_EXERCISED")
    if not force_recompute and not 0 < actual_updates < len(events):
        raise ValueError("BENCHMARK_INCREMENTAL_AVOIDANCE_NOT_EXERCISED")
    result = {"config": config, "count": len(events), "wall_seconds": elapsed, "cpu_seconds": cpu,
              "events_per_second": len(events) / elapsed,
              "ingest_latency_ms": {"p50": quantile(latency, .5), "p95": quantile(latency, .95),
                                    "p99": quantile(latency, .99), "mean": statistics.fmean(latency),
                                    "maximum": max(latency)},
              "tracemalloc_peak_bytes": peak, "sqlite_file_bytes": service.store.path.stat().st_size,
              "metrics": metrics, "actual_forecast_updates": actual_updates,
              "actual_forecasts_avoided_vs_every_event": len(events) - actual_updates,
              "ai_investigations": ai,
              "queue_depth": {"maximum_observed": runtime_metrics.get("maximum_queue_depth"),
                              "terminal": runtime_metrics.get("queue_depth"),
                              "status": "MEASURED_BY_SERVICE" if "maximum_queue_depth" in runtime_metrics else "NOT_EXPOSED",
                              "caller_in_flight_max": 1,
                              "scope": "Sequential synchronous ingestion; no producer or external queue is exercised."},
              "final_state_sha256": digest(state), "checkpoint_count": len(snapshots),
              "final_forecast_sha256": digest(snapshots[len(events)]["forecast"])}
    service.close()
    return result, snapshots


def self_test():
    from dragonhydra.realtime.events import reduce_events
    small, large = event_stream(100), event_stream(1000)
    reduced = reduce_events(large, MATCH, "DEMONSTRATION")
    checks = (small == large[:100], quantile([1, 2, 3, 4, 5], .5) == 3,
              difference({"x": [1.0, None, True]}, {"x": [1.0, None, True]}) == 0,
              reduced["score"] == {"home": 1, "away": 0}, reduced["period"] == 2 and reduced["minute"] < 90,
              all(event["source_mode"] == "DEMONSTRATION" for event in large),
              len({event["event_id"] for event in large}) == 1000)
    if not all(checks):
        raise ValueError("BENCHMARK_PURE_GUARDS_FAILED")
    print(json.dumps({"status": "PASS", "scope": "PURE_BENCHMARK_GUARDS", "checks": 7}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=LANE / "evidence" / "benchmark-r1")
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 10000])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not args.sizes or len(set(args.sizes)) != len(args.sizes) or any(value not in (100, 1000, 10000) for value in args.sizes):
        parser.error("sizes must be unique members of 100,1000,10000")
    output = args.output.resolve()
    allowed = (LANE / "evidence").resolve()
    if allowed not in output.parents or output.exists():
        parser.error("output must be a fresh directory below this isolated lane's evidence directory")
    for parent in (output, *output.parents):
        if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(), "st_file_attributes", 0) & 0x400):
            parser.error("output reparse paths are forbidden")
    output.mkdir(parents=True, exist_ok=False)
    identity = source_identity()
    run_mode.expected_source = identity["selected_input_sha256"]
    plan = {"schema_version": "dragonhydra.synthetic-benchmark-plan/1", "synthetic": True,
            "python_executable": sys.executable, "python_version": sys.version,
            "source": identity, "sizes": args.sizes,
            "scope": "Identical accepted inputs, actual owned SQLite stores, no HTTP or installed service.",
            "latency_scope": "Service.ingest call only; aggregate wall/CPU also include initialization and checkpoint reads.",
            "fixture_rule": "Kickoff then second-half resume, mostly same-clock possession; periodic clock/goals/card.",
            "ai_enabled": False, "dense_persistence": False,
            "limitations": ["Synthetic local-machine research, not real-world throughput or calibration.",
                            "One run per mode/size; ordering, OS cache and tracemalloc overhead affect timings.",
                            "Only common checkpoints compare distributions; all events must be accepted in both modes."]}
    write_new(output / "PLAN.json", plan)
    report = {"schema_version": "dragonhydra.synthetic-benchmark/1", "synthetic": True,
              "status": "RUNNING", "source": identity, "cases": [], "limitations": plan["limitations"]}
    try:
        for count in args.sizes:
            events = event_stream(count)
            case = {"count": count, "input_sha256": digest(events)}
            incremental, left = run_mode(events, output / (str(count) + "-incremental"), False)
            full, right = run_mode(events, output / (str(count) + "-forced"), True)
            drifts = [{"accepted_revision": revision,
                       "incremental_forecast_state_revision": left[revision]["forecast_state_revision"],
                       "forced_forecast_state_revision": right[revision]["forecast_state_revision"],
                       "maximum_absolute_probability_or_scalar_drift": difference(left[revision]["forecast"], right[revision]["forecast"])}
                      for revision in sorted(left)]
            maximum = max(value["maximum_absolute_probability_or_scalar_drift"] for value in drifts)
            case.update(incremental=incremental, forced=full, checkpoints=drifts,
                        maximum_drift=maximum, distributions_equal_within_1e_minus_12=maximum <= 1e-12,
                        wall_speedup=full["wall_seconds"] / incremental["wall_seconds"])
            if maximum > 1e-12 or incremental["final_state_sha256"] != full["final_state_sha256"]:
                raise ValueError("BENCHMARK_EQUIVALENCE_FAILED")
            report["cases"].append(case)
            write_new(output / ("CASE-" + str(count) + ".json"), case)
            print(json.dumps({"completed_case": count, "maximum_drift": maximum}), flush=True)
        report["status"] = "PASS"
    except Exception as exc:
        report["status"] = "FAILED"
        report["failure_type"] = type(exc).__name__
        report["failure"] = str(exc)[:500]
        write_new(output / "BENCHMARK.json", report)
        raise
    write_new(output / "BENCHMARK.json", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
