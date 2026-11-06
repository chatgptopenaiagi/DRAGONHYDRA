"""Reproducible offline vertical slice using only new synthetic state."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import time
from unittest.mock import patch

from dragonhydra.realtime.events import canonical
from dragonhydra.realtime.service import RealtimeService


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def numerical(service, match_id):
    return [{"minute": w["minute"], "score": w["score"],
             "result": w["forecast"]["full_time_result"],
             "horizons": w["forecast"]["horizons"]} for w in service.timeline(match_id)["items"]]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=1000)
    args = parser.parse_args(argv)
    lane = Path(__file__).absolute().parents[2]
    output = args.output.absolute()
    if not output.is_relative_to(lane / "evidence") or output == lane / "evidence" or output.exists():
        raise ValueError("NEW_OWNED_EVIDENCE_DIRECTORY_REQUIRED")
    for p in (output, *output.parents):
        if p.exists() and (p.is_symlink() or getattr(p.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("REPARSE_EVIDENCE_REJECTED")
    output.mkdir(parents=True)
    checks = []
    def check(name, condition):
        checks.append({"name": name, "status": "PASS" if condition else "FAIL"})
        if not condition:
            raise AssertionError(name)
    report = {"schema_version": "dragonhydra.virtual-acceptance/1", "synthetic": True,
              "checks": checks, "status": "RUNNING", "real_api_calls": 0, "real_sporting_records": 0}
    started = time.perf_counter()
    first = second = restarted = None
    try:
        with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_FORBIDDEN_IN_OFFLINE_ACCEPTANCE")):
            first = RealtimeService(output / "first-state")
            mid = first.create_scenario()["match_id"]
            first.replay_control(mid, "step", steps=100)
            snapshot = first.match(mid)
            metrics = snapshot["metrics"]
            check("FICTIONAL_FULL_SCENARIO", snapshot["state"]["status"] == "FINISHED" and snapshot["state"]["score"] == {"home": 0, "away": 1})
            check("DUPLICATE_SUPPRESSED", metrics["events_received"] == 19 and metrics["events_accepted"] == 18 and metrics["duplicates_rejected"] == 1)
            check("RELEVANT_UPDATES_AND_SKIPPED_WORK", metrics["forecast_updates"] == 14 and metrics["expensive_calculations_avoided"] == 4)
            check("CORRECTIONS_RECONCILED", metrics["reconciliations"] == 2)
            timeline = first.timeline(mid)["items"]
            check("FIVE_COHERENT_HORIZONS", all(set(w["forecast"]["horizons"]) == {"1", "5", "10", "30", "FULL_TIME"} for w in timeline))
            check("ACTUAL_PROBABILITY_CHANGE", any(w["change"]["delta"] and max(map(abs, w["change"]["delta"].values())) > .05 for w in timeline))
            analyses = snapshot["analyses"]
            check("CLOSED_VIRTUAL_ANALYTICAL_LOOP", bool(analyses) and all(a["status"] == "completed" and a["tool_call_count"] == 4 and len(a["tool_results"]) == 4 for a in analyses))
            check("REAL_API_USAGE_ABSENT", all(a["real_network_call_count"] == 0 and a["usage"] is None and a["cost"] is None for a in analyses))
            history_hash = digest(timeline)
            numbers = numerical(first, mid)
            report["scenario"] = {"match_id": mid, "metrics": metrics, "analysis_count": len(analyses),
                                  "timeline_sha256": history_hash, "numerical_sha256": digest(numbers)}
            evaluation = first.evaluate()
            check("MATURED_EVALUATION", evaluation["metrics"]["status"] == "scored")
            report["evaluation"] = evaluation
            (output / "EVALUATION.json").write_text(json.dumps(evaluation, indent=2, allow_nan=False)+"\n", encoding="utf-8")
            first.close()
            restarted = RealtimeService(output / "first-state")
            check("RESTART_PRESERVES_IMMUTABLE_HISTORY", digest(restarted.timeline(mid)["items"]) == history_hash)
            before = deepcopy(restarted.match(mid)["metrics"])
            restarted.replay_control(mid, "step", steps=100)
            check("COMPLETED_REPLAY_NOT_REPEATED", restarted.match(mid)["metrics"] == before)
            second = RealtimeService(output / "second-state")
            other = second.create_scenario()["match_id"]
            second.replay_control(other, "step", steps=100)
            check("REPEATED_REPLAY_NUMERICAL_EQUIVALENCE", numerical(second, other) == numbers)
            prefix = next(w for w in timeline if w["event_type"] == "RED_CARD")
            child = restarted.branch(mid, prefix["state_revision"], "virtual-alternative", 73, "tempo_signal")["match_id"]
            check("REWIND_BRANCH_INHERITS_ACCEPTED_PREFIX", restarted.store.state(child)["score"] == restarted.store.state(mid, prefix["state_revision"])["score"])
            restarted.replay_control(child, "step", steps=100)
            if restarted.match(child)["replay"]["status"] != "COMPLETED":
                restarted.replay_control(child, "step", steps=100)
            check("ALTERNATIVE_FUTURE_COMPLETES", restarted.store.state(child)["status"] == "FINISHED")
            check("PARENT_FORECASTS_NEVER_REWRITTEN", digest(restarted.timeline(mid)["items"]) == history_hash)
            experiment = restarted.run_experiment(cases=args.cases)
            (output / "RELEVANCE.json").write_text(json.dumps(experiment, indent=2, allow_nan=False)+"\n", encoding="utf-8")
            check("FIVE_RULE_SETS_SHARED_INITIAL_CONDITIONS", len(experiment["universes"]) == 5 and len({w["initial_conditions_sha256"] for w in experiment["universes"]}) == 1)
            check("DISJOINT_TRAIN_TEST", all(w["train"]["order_maximum"] < w["test"]["order_minimum"] for w in experiment["universes"]))
            check("RELEVANCE_ROWS_FROM_ACTUAL_LOSSES", len(experiment["rows"]) == 100)
            report["relevance"] = {"episode_count": experiment["total_episode_count"], "cases_per_universe": args.cases,
                "initial_conditions_sha256": experiment["universes"][0]["initial_conditions_sha256"],
                "ten_minute_rows": [r for r in experiment["rows"] if r["horizon"] == "10"],
                "report_sha256": digest(experiment)}
        report["status"] = "PASS"
    except Exception as error:
        report.update(status="FAILED", failure=f"{type(error).__name__}: {error}")
        raise
    finally:
        for service in (first, second, restarted):
            if service:
                service.close()
        report["elapsed_seconds"] = time.perf_counter()-started
        (output / "ACCEPTANCE.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "episode_count": report["relevance"]["episode_count"], "report": str(output / "ACCEPTANCE.json")}))


if __name__ == "__main__":
    main()
