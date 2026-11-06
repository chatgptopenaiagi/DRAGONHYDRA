"""Composed virtual research engine: journal -> relevance -> math -> local tools."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import math
from pathlib import Path
import threading
import time

from . import VERSION
from .bridge import NeuralBridge, tool_schemas
from .evaluation import evaluate_baseline_vs_assisted, evaluate_forecasts
from .events import CAPABILITIES, canonical, identifier, instant, number, semantic_state, validate_event
from .models import DEFAULTS, HORIZONS, predict
from .replay import EPOCH, ReplayController, standard_fixture
from .store import Store


class RealtimeService:
    contract_version = "core-next.engine/1"

    def __init__(self, directory, config=None):
        config = dict(config or {})
        allowed = {"auto_investigate", "force_recompute", "persist_dense", "model", "bridge",
                   "change_threshold", "cooldown_seconds", "max_pending", "max_events", "max_matches"}
        if set(config) - allowed:
            raise ValueError("RESEARCH_CONFIGURATION_INVALID")
        for key in ("auto_investigate", "force_recompute", "persist_dense"):
            if key in config and type(config[key]) is not bool:
                raise ValueError("RESEARCH_CONFIGURATION_INVALID")
        self.config = {"auto_investigate": True, "force_recompute": False, "persist_dense": True,
                       "change_threshold": .05, "cooldown_seconds": 60, "max_pending": 64, **config}
        number(self.config["change_threshold"], .001, 1)
        number(self.config["cooldown_seconds"], 0, 3600)
        if type(self.config["max_pending"]) is not int or not 1 <= self.config["max_pending"] <= 128:
            raise ValueError("RESEARCH_QUEUE_BUDGET_INVALID")
        self.store = Store(directory, max_events=config.get("max_events", 100000),
                           max_matches=config.get("max_matches", 128))
        self._locks = {}
        self._guard, self._bridge_lock = threading.RLock(), threading.RLock()
        self._gate = threading.BoundedSemaphore(self.config["max_pending"])
        self._pending, self._max_pending, self._closed = 0, 0, False
        self._contexts = {}
        bridge_config = dict(config.get("bridge", {}))
        if "state" in bridge_config:
            raise ValueError("BRIDGE_STATE_IS_STORE_OWNED")
        retained = self.store.meta("bridge_state")
        if retained:
            bridge_config["state"] = retained
        self.bridge = NeuralBridge(self._bridge_context, bridge_config)
        self.replay = ReplayController(self.store, self.ingest)
        # A process restart pauses virtual time. It never replays unresolved
        # reasoning requests or silently resumes mutation from a passive GET.
        for item in self.store.matches():
            controls = self.store.get_replay(item["match_id"])
            if controls["status"] == "PLAYING":
                controls.update(status="PAUSED", reason="PROCESS_RESTARTED")
                self.store.set_replay(item["match_id"], controls)
            state = item["state"]
            current = self.store.current_forecast(item["match_id"])
            needs_recovery = not current
            if current and current["state_revision"] < state["revision"]:
                prior_state = self.store.state(item["match_id"], current["state_revision"])
                needs_recovery = (semantic_state(prior_state) != semantic_state(state)
                                  or prior_state["quality"]["flags"] != state["quality"]["flags"])
                with self.store.connect() as db:
                    invalidated = db.execute("SELECT 1 FROM invalidations WHERE forecast_id=? LIMIT 1",
                                             (current["forecast_id"],)).fetchone()
                needs_recovery = needs_recovery or bool(invalidated)
            if state["revision"] and needs_recovery:
                events = self.store.events(item["match_id"], limit=1)
                if events:
                    self._forecast(state, events[-1], {"reason_codes": ["RECOVERED_ACCEPTED_STATE"]})

    def _match_lock(self, match_id):
        with self._guard:
            if match_id not in self._locks:
                if len(self._locks) >= 1024:
                    raise ValueError("MATCH_CONCURRENCY_CARDINALITY_LIMIT")
                self._locks[match_id] = threading.RLock()
            return self._locks[match_id]

    def ingest(self, raw):
        if self._closed:
            raise ValueError("RESEARCH_ENGINE_CLOSED")
        event = validate_event(raw)
        if not self._gate.acquire(blocking=False):
            self.store.metric("backpressure_rejections")
            raise ValueError("RESEARCH_BACKPRESSURE")
        started = time.perf_counter()
        with self._guard:
            self._pending += 1
            self._max_pending = max(self._max_pending, self._pending)
        try:
            with self._match_lock(event["match_id"]):
                event, decision, state = self.store.accept(event, force_recompute=self.config["force_recompute"])
                if decision["action"] != "DUPLICATE":
                    if decision["action"] == "UPDATE_FORECAST" or self.config["force_recompute"] or not self.store.current_forecast(event["match_id"]):
                        wrapper = self._forecast(state, event, decision)
                        if wrapper and self.config["auto_investigate"] and wrapper["change"]["investigation_recommended"]:
                            self.investigate(state["match_id"], wrapper["revision"])
                    else:
                        self.store.metric("data_acquisition_requests_avoided")
                return {"schema_version": "dragonhydra.event-receipt/1", "synthetic": True,
                        "event_id": event["event_id"], "match_id": event["match_id"],
                        "decision": decision, "state_revision": state["revision"],
                        "processing_latency_ms": (time.perf_counter()-started)*1000}
        finally:
            with self._guard:
                self._pending -= 1
            self._gate.release()

    def _forecast(self, state, event, decision):
        previous = self.store.current_forecast(state["match_id"])
        result = predict(state, self.config.get("model"))
        # All distributions remain the mathematical module's result. Data and
        # operational limitations are separate dimensions, not a confidence %.
        canonical(result)
        self._validate_forecast(result)
        result["model_configuration"] = {**DEFAULTS, **(self.config.get("model") or {})}
        result["configuration_id"] = identifier("virtual-model-config-", result["model_configuration"])
        result["uncertainty"]["data"] = deepcopy(state["quality"])
        result["uncertainty"]["parameter"] = {"state": "NOT_ESTIMATED", "reason": "CONFIGURED_SYNTHETIC_RATES"}
        result["uncertainty"]["operational"] = {"external_openai": "UNCONFIGURED",
                                                 "live_provider": "UNCONFIGURED", "mode": "VIRTUAL_ONLY"}
        before = previous["forecast"]["full_time_result"] if previous else None
        after = result["full_time_result"]
        delta = {k: after[k]-before[k] for k in ("home", "draw", "away")} if before and after else None
        magnitude = max(map(abs, delta.values())) if delta else 0
        last_significant = previous["change"].get("last_significant_at") if previous else None
        elapsed = ((instant(event["received_at"])-instant(last_significant)).total_seconds()
                   if last_significant else math.inf)
        major = event["event_type"] in ("GOAL", "RED_CARD", "CORRECTION")
        qualifies = bool(before and after and state["status"] != "FINISHED"
                         and (magnitude >= self.config["change_threshold"] or major)
                         and elapsed >= self.config["cooldown_seconds"])
        reasons = list(decision["reason_codes"])
        if magnitude >= self.config["change_threshold"]:
            reasons.append("MATERIAL_PROBABILITY_MOVEMENT")
        if major:
            reasons.append("MAJOR_MATCH_OBSERVATION")
        if qualifies:
            reasons.append("BOUNDED_INVESTIGATION")
        elif before and (major or magnitude >= self.config["change_threshold"]):
            reasons.append("INVESTIGATION_COOLDOWN")
        if not self.config["persist_dense"]:
            for horizon in result["horizons"].values():
                horizon["score_distribution"] = None
        revision = previous["revision"]+1 if previous else 1
        wrapper = {"schema_version": "dragonhydra.forecast-revision/1",
                   "forecast_id": identifier("forecast:", [state["match_id"], state["revision"], result["model_id"]]),
                   "match_id": state["match_id"], "synthetic": True, "source_mode": state["source_mode"],
                   "revision": revision, "state_revision": state["revision"],
                   "event_id": event["event_id"], "event_type": event["event_type"],
                   "event_time": event["event_time"], "received_at": event["received_at"],
                   "minute": state["minute"], "score": deepcopy(state["score"]), "forecast": result,
                   "change": {"delta": delta, "maximum_absolute_probability_change": magnitude,
                              "last_significant_at": event["received_at"] if qualifies else last_significant,
                              "unit": "PROBABILITY_FRACTION; multiply by100 for percentage points",
                              "reason_codes": reasons, "investigation_recommended": qualifies,
                              "entropy_delta": (result["uncertainty"]["entropy"]-previous["forecast"]["uncertainty"]["entropy"])
                              if previous and result["uncertainty"]["entropy"] is not None
                              and previous["forecast"]["uncertainty"]["entropy"] is not None else None}}
        if not self.store.append_forecast(wrapper):
            return None
        return wrapper

    @staticmethod
    def _validate_forecast(result):
        def vector(values):
            if not isinstance(values, dict) or set(values) != {"home", "draw", "away"}:
                raise ValueError("FORECAST_OUTCOME_VECTOR_INVALID")
            if any(type(v) not in (int, float) or not 0 <= v <= 1 or not math.isfinite(v) for v in values.values()):
                raise ValueError("FORECAST_PROBABILITY_INVALID")
            if not math.isclose(math.fsum(values.values()), 1, abs_tol=1e-12, rel_tol=0):
                raise ValueError("FORECAST_NORMALIZATION_INVALID")
        if result.get("full_time_result") is not None:
            vector(result["full_time_result"])
        if not isinstance(result.get("horizons"), dict) or set(result["horizons"]) != set(HORIZONS):
            raise ValueError("FORECAST_HORIZONS_INVALID")
        for horizon in result["horizons"].values():
            if horizon.get("availability") is not True:
                continue
            number(horizon["effective_minutes"], 0, 150)
            number(horizon["next_goal_occurrence"], 0, 1)
            side = horizon["next_goal_side"]
            mass = [number(side[k], 0, 1) for k in ("home", "away", "no_goal")]
            if not math.isclose(math.fsum(mass), 1, abs_tol=1e-12, rel_tol=0):
                raise ValueError("NEXT_GOAL_NORMALIZATION_INVALID")
            goals = horizon["remaining_goals"]
            total = math.fsum(number(p, 0, 1) for p in goals["distribution"]) + number(goals["tail_bucket"]["probability"], 0, 1)
            if not math.isclose(total, 1, abs_tol=1e-12, rel_tol=0):
                raise ValueError("REMAINING_GOALS_NORMALIZATION_INVALID")

    def _context(self, match_id, state_revision=None):
        state = self.store.state(match_id, state_revision)
        timeline = [w for w in self.store.timeline(match_id, 1000) if w["state_revision"] <= state["revision"]]
        # Bounded context contains accepted observations only, never the future
        # replay fixture, generator outcomes or held-out experiment labels.
        compact = []
        for item in timeline[-6:]:
            value = deepcopy(item)
            for horizon in value["forecast"]["horizons"].values():
                horizon["score_distribution"] = None
            compact.append(value)
        cutoff = instant(state["received_at"]) if state["received_at"] else EPOCH
        analyses = []
        for analysis in self.store.analyses(match_id, 50):
            if (type(analysis.get("event_revision")) is int and analysis["event_revision"] <= state["revision"]
                    and isinstance(analysis.get("available_at"), str) and instant(analysis["available_at"]) <= cutoff):
                analyses.append({k: analysis.get(k) for k in ("analysis_id", "event_revision", "status", "summary", "evidence_ids")})
            if len(analyses) == 4:
                break
        calibration = self.evaluation_report()
        if not calibration or instant(calibration.get("available_at", "9999-01-01T00:00:00Z")) > cutoff:
            calibration = None
        elif calibration:
            calibration = {k: calibration[k] for k in ("schema_version", "synthetic", "calibration_state",
                                                        "real_sporting_cases", "available_at", "cohort_policy")}
        return {"state": state, "current_forecast": compact[-1] if compact else None,
                "timeline": compact, "events": self.store.events(match_id, limit=24, through_revision=state["revision"]),
                "analyses": analyses, "calibration_report": calibration,
                "model_config": deepcopy(compact[-1]["forecast"].get("model_configuration")) if compact else None}

    def _bridge_context(self, match_id):
        return self._contexts.get(match_id) or self._context(match_id)

    def investigate(self, match_id, forecast_revision=None):
        with self._match_lock(match_id), self._bridge_lock:
            timeline = self.store.timeline(match_id, 1000)
            selected = next((w for w in timeline if w["revision"] == forecast_revision), None) if forecast_revision is not None else (timeline[-1] if timeline else None)
            if not selected or not selected["forecast"]["full_time_result"]:
                raise ValueError("ELIGIBLE_FORECAST_REQUIRED")
            context = self._context(match_id, selected["state_revision"])
            prior = [w for w in timeline if w["revision"] < selected["revision"] and w["forecast"]["full_time_result"]]
            before = prior[-1]["forecast"]["full_time_result"] if prior else selected["forecast"]["full_time_result"]
            after = selected["forecast"]["full_time_result"]
            packet = {"schema_version": "dragonhydra.neural-packet/1",
                      "packet_id": identifier("virtual-packet-", selected["forecast_id"]),
                      "match_id": match_id, "event_revision": selected["state_revision"],
                      "source_mode": selected["source_mode"], "forecast_target": "FULL_TIME_RESULT",
                      "event": {"event_id": selected["event_id"], "type": selected["event_type"], "minute": selected["minute"]},
                      "observed_score": selected["score"], "probability_before": before,
                      "probability_after": after, "change": {k: after[k]-before[k] for k in after},
                      "data_quality": {"status": context["state"]["quality"]["status"],
                                       "flags": context["state"]["quality"]["flags"]},
                      "model_id": selected["forecast"]["model_id"],
                      "evidence_ids": [selected["forecast_id"], selected["event_id"]],
                      "investigation": {"reason": "SYNTHETIC_PREDICTIVE_CHANGE",
                                        "question": "Which assumptions or observations explain this conditional estimate?"}}
            stage, prior_result = self.store.analysis_intent(packet)
            if stage == "COMPLETED":
                return prior_result
            if stage == "UNRESOLVED":
                return {"schema_version": "dragonhydra.neural-analysis/1", "status": "UNRESOLVED",
                        "packet_id": packet["packet_id"], "synthetic": True,
                        "reason": "PRIOR_REQUEST_INTENT_REQUIRES_RECONCILIATION", "real_network_call_count": 0}
            self._contexts[match_id] = context
            try:
                analysis = self.bridge.investigate(packet)
                analysis["event_revision"] = selected["state_revision"]
                analysis["available_at"] = selected["received_at"]
                self.store.meta("bridge_state", self.bridge.export_state())
                return self.store.save_analysis(packet["packet_id"], match_id, analysis)
            finally:
                self._contexts.pop(match_id, None)

    def create_scenario(self, scenario_id="standard", source_mode="DEMONSTRATION", universe="constant", seed=42):
        if scenario_id not in ("standard", "universe") or source_mode not in ("DEMONSTRATION", "REPLAY"):
            raise ValueError("VIRTUAL_SCENARIO_INVALID")
        if type(seed) is not int or not 0 <= seed <= 2147483647:
            raise ValueError("VIRTUAL_SEED_INVALID")
        match_id = identifier("virtual-match-", [scenario_id, source_mode, universe, seed])
        existing = {m["match_id"] for m in self.store.matches()}
        if match_id in existing:
            return {"match_id": match_id, "synthetic": True, "reused": True}
        if scenario_id == "standard" and universe == "constant":
            fixture = standard_fixture(match_id, source_mode)
            descriptor = {"scenario": "standard/1", "universe": "scripted-conditional-baseline"}
        else:
            from .worlds import generate_match
            generated = generate_match(universe, seed, match_id)
            fixture, descriptor = generated["events"], generated["descriptor"]
            for event in fixture:
                event["source_mode"] = source_mode
        self.store.create_match(match_id, source_mode, descriptor)
        self.replay.install(match_id, fixture)
        return {"match_id": match_id, "synthetic": True, "source_mode": source_mode,
                "fixture_hash": identifier("fixture:", fixture), "event_count": len(fixture)}

    def replay_control(self, match_id, action, speed=100, steps=1):
        self.replay.control(match_id, action, speed, steps)
        return self.match(match_id)

    def matches(self):
        return {"items": self.store.matches(), "synthetic": True}

    def match(self, match_id):
        return {"match_id": match_id, "synthetic": True, "source_mode": self.store.state(match_id)["source_mode"],
                "state": self.store.state(match_id), "current_forecast": self.store.current_forecast(match_id),
                "replay": self.store.get_replay(match_id), "analyses": self.store.analyses(match_id),
                "descriptor": self.store.descriptor(match_id), "metrics": self.store.metrics()}

    def timeline(self, match_id, limit=200):
        items = self.store.timeline(match_id, limit)
        analyses = {a["packet_id"]: a for a in self.store.analyses(match_id)}
        for item in items:
            item["analysis"] = analyses.get(identifier("virtual-packet-", item["forecast_id"]))
        return {"items": items, "synthetic": True}

    def events(self, match_id, limit=200):
        return {"items": self.store.events(match_id, limit=limit), "synthetic": True}

    def tools(self):
        return {"schema_version": "dragonhydra.analysis-tools/1", "items": tool_schemas(), "synthetic": True}

    def budgets(self):
        exported = self.bridge.export_state()
        return {"virtual_only": True, "limits": self.bridge.limits, "days": exported["days"],
                "real_network_calls": 0, "real_api_usage": None, "real_api_cost": None}

    def evaluate(self):
        predictions, outcomes = [], []
        for match in self.store.matches():
            state = match["state"]
            if state["status"] != "FINISHED":
                continue
            events = self.store.events(match["match_id"])
            final = next(e for e in reversed(events) if e["event_type"] == "FULL_TIME")
            candidates = [w for w in self.store.timeline(match["match_id"], 1000)
                          if w["minute"] <= 30 and w["forecast"]["full_time_result"]
                          and instant(w["received_at"]) < instant(final["event_time"])]
            if not candidates:
                continue
            selected = candidates[-1]
            label = "home" if state["score"]["home"] > state["score"]["away"] else "away" if state["score"]["away"] > state["score"]["home"] else "draw"
            predictions.append({"prediction_id": selected["forecast_id"], "match_id": state["match_id"],
                                "forecast_target": "FULL_TIME_RESULT", "horizon": "FULL_TIME",
                                "probabilities": selected["forecast"]["full_time_result"],
                                "decision_at": selected["received_at"], "available_at": selected["received_at"],
                                "source_mode": state["source_mode"], "synthetic": True})
            outcomes.append({"match_id": state["match_id"], "forecast_target": "FULL_TIME_RESULT",
                             "horizon": "FULL_TIME", "label": label, "occurred_at": final["event_time"],
                             "available_at": final["received_at"], "source_mode": state["source_mode"], "synthetic": True})
        cutoff = max((r["available_at"] for r in outcomes), default=EPOCH.isoformat().replace("+00:00", "Z"))
        report = {"schema_version": "dragonhydra.synthetic-evaluation/1", "synthetic": True,
                  "available_at": cutoff,
                  "cohort_policy": "One last available forecast by minute30 per virtual match; no terminal forecast or duplicate episode",
                  "calibration_state": "UNVERIFIED_REAL_WORLD", "real_sporting_cases": 0,
                  "metrics": evaluate_forecasts(predictions, outcomes, cutoff=cutoff),
                  "baseline_vs_assisted": evaluate_baseline_vs_assisted(predictions, deepcopy(predictions), outcomes, cutoff=cutoff),
                  "interpretation": "Mock reasoning cannot override the same baseline; equal probability vectors imply zero predictive improvement."}
        self.store.meta("evaluation_report", report)
        return report

    def evaluation_report(self):
        return self.store.meta("evaluation_report")

    def experiments(self):
        return self.store.latest_experiment()

    def run_experiment(self, seed=42, cases=400):
        from .worlds import relevance_experiment
        report = relevance_experiment(seed=seed, cases=cases)
        # These display rows are projections of the actual paired held-out
        # losses, not another estimator or a thresholded success declaration.
        report["rows"] = []
        for world in report["universes"]:
            for feature, horizons in world["feature_utility_vs_constant_past_only"].items():
                for horizon, utility in horizons.items():
                    brier, log_loss = utility["brier"], utility["log_loss"]
                    report["rows"].append({"universe": world["universe"], "feature": feature,
                        "target": "NEXT_GOAL_OCCURRENCE", "horizon": horizon,
                        "test_brier": world["models"][feature.lower()]["test_metrics"][horizon]["brier"],
                        "heldout_brier_delta": brier["mean_improvement"],
                        "brier_interval_low": brier["approximate_95_percent_interval"][0],
                        "brier_interval_high": brier["approximate_95_percent_interval"][1],
                        "log_loss_delta_nats": log_loss["mean_improvement"],
                        "paired_test_episodes": brier["paired_episode_count"]})
        return self.store.save_experiment(report)

    def branch(self, match_id, at_revision, branch_name="fork", seed=42, universe="constant"):
        if type(at_revision) is not int or at_revision < 0 or at_revision > 10000:
            raise ValueError("BRANCH_REVISION_INVALID")
        if not isinstance(branch_name, str) or not 1 <= len(branch_name) <= 40:
            raise ValueError("BRANCH_NAME_INVALID")
        if type(seed) is not int or not 0 <= seed <= 2147483647:
            raise ValueError("VIRTUAL_SEED_INVALID")
        from .worlds import generate_match
        state = self.store.state(match_id, at_revision)
        if state["status"] == "FINISHED":
            raise ValueError("REWIND_TO_A_PRE_FINAL_REVISION")
        child = identifier("virtual-match-", [match_id, at_revision, branch_name, seed, universe])
        if child in {m["match_id"] for m in self.store.matches()}:
            return {"match_id": child, "synthetic": True, "reused": True}
        generated = generate_match(universe, seed, child)
        self.store.create_match(child, state["source_mode"],
                                {"parent_match_id": match_id, "parent_state_revision": at_revision,
                                 "branch_name": branch_name, "universe": universe, "seed": seed,
                                 "synthetic": True, "original_forecasts_modified": False})
        sources, prefix = {}, self.store.events(match_id, through_revision=at_revision)
        for event in prefix:
            sources.setdefault(event["source_id"], identifier("virtual-source-", [child, event["source_id"]]))
        for event in prefix:
            event = deepcopy(event)
            event["match_id"], event["source_id"] = child, sources[event["source_id"]]
            if event["event_type"] == "CORRECTION":
                event["attributes"]["target_source_id"] = sources[event["attributes"]["target_source_id"]]
            self.ingest(event)
        inherited = self.store.state(child)
        primary = inherited["primary_source_id"] or identifier("virtual-source-", child)
        last_sequence = inherited.get("sequence_watermarks", {}).get(primary, {}).get("last", 0)
        future = []
        score = deepcopy(inherited["score"])
        # A fork resumes an explicit virtual pause. A second-half clock reset
        # is an event, never an inference from a later goal or clock sample.
        continuation = []
        resumed_second_half = inherited["status"] == "HALF_TIME"
        if inherited["status"] in ("HALF_TIME", "SUSPENDED"):
            resumed = deepcopy(generated["events"][0])
            resumed.update(event_type="RESUME", participant="NONE")
            resumed["attributes"] = {"minute": 45 if resumed_second_half else inherited["minute"],
                "period": 2 if resumed_second_half else inherited["period"],
                "period_end_minute": 90 if resumed_second_half else inherited["period_end_minute"]}
            continuation.append(resumed)
        cutoff_minute = 45 if resumed_second_half else inherited["minute"]
        known_final = max(90, inherited["period_end_minute"], inherited["minute"]) if inherited["period"] == 2 else 90
        for event in generated["events"]:
            if event["attributes"]["minute"] <= cutoff_minute and at_revision and event["event_type"] != "FULL_TIME":
                continue
            continuation.append(deepcopy(event))
        virtual_at = instant(inherited["received_at"]) if inherited["received_at"] else EPOCH
        prior_minute = inherited["minute"]
        for event in continuation:
            event = deepcopy(event)
            event["match_id"], event["source_id"], event["source_mode"] = child, primary, state["source_mode"]
            event["event_id"] = f"virtual-future-{seed}-{len(future)+1}"
            event["sequence"], event["revision"] = last_sequence+len(future)+1, 1
            if event["attributes"].get("period") == 2:
                event["attributes"]["period_end_minute"] = known_final
            if event["event_type"] == "GOAL":
                score[event["participant"].lower()] += 1
            if event["event_type"] == "FULL_TIME":
                event["attributes"].update(score, minute=known_final)
            minute = event["attributes"]["minute"]
            virtual_at += timedelta(minutes=max(0, minute-prior_minute), microseconds=1000)
            event["event_time"] = virtual_at.isoformat().replace("+00:00", "Z")
            event["received_at"] = (virtual_at+timedelta(milliseconds=10)).isoformat().replace("+00:00", "Z")
            prior_minute = minute
            future.append(event)
        self.replay.install(child, future)
        return {"match_id": child, "synthetic": True, "parent_match_id": match_id,
                "parent_state_revision": at_revision, "future_event_count": len(future)}

    def status(self):
        metrics = self.store.metrics()
        metrics.update(queue_depth=self._pending, maximum_queue_depth=self._max_pending,
                       real_network_calls=0, real_sporting_records=0)
        components = {
            "live_feed": {"state": "NEUTRAL", "reason": "UNCONFIGURED; VIRTUAL_OBJECTS_ONLY"},
            "event_ingestion": {"state": "GREEN", "reason": "STRICT_SYNTHETIC_SCHEMA_AND_JOURNAL"},
            "relevance_engine": {"state": "GREEN", "reason": "EXPLICIT_MODEL_DEPENDENCIES; HEURISTIC_NOT_INFORMATION_GAIN"},
            "dynamic_forecasting": {"state": "AMBER", "reason": "EXPERIMENTAL_CONFIGURED_RATE_MODEL"},
            "calibration": {"state": "NEUTRAL", "reason": "SYNTHETIC_EVALUATION_ONLY; REAL_WORLD_UNVERIFIED"},
            "neural_bridge": {"state": "GREEN", "reason": "VIRTUAL_RESPONSES_AND_WORKING_LOCAL_TOOLS"},
            "provider_connection": {"state": "NEUTRAL", "reason": "NO_REAL_PROVIDER_OR_API_KEY"},
            "analysis_tools": {"state": "GREEN", "reason": "NINE_BOUNDED_READ_OR_CALCULATION_HANDLERS"},
            "dashboard": {"state": "NEUTRAL", "reason": "BROWSER_ACCEPTANCE_SEPARATE"},
        }
        return {"schema_version": "dragonhydra.realtime-status/1", "version": VERSION,
                "synthetic": True, "mode": "VIRTUAL_ONLY", "components": components,
                "metrics": metrics, "adapters": CAPABILITIES, "budgets": self.budgets()}

    def observe(self):
        return {"state": "DEGRADED", "reason": "VIRTUAL_EXPERIMENTAL_ONLY",
                "metrics": {"configured": True, "retained_observation_count": self.store.metrics().get("events_accepted", 0)},
                "evidence": ("Synthetic-only event journal and configured-rate model; no live coverage claim",)}

    def close(self):
        if not self._closed:
            self.replay.close()
            self._closed = True

    def stop(self):
        self.close()
