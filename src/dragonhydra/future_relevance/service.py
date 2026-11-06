"""Transactional virtual information acquisition and frozen-policy experiments."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
import threading
import time

from ..realtime.events import canonical, identifier, instant, virtual_id
from . import VERSION
from .environment import VirtualEpisode, CATEGORIES, FAMILIES, finite, integer
from .forecast import forecast
from .journal import Journal
from .learning import estimate, validate_model
from .policies import POLICIES, choose_action


def checked_forecast(snapshot):
    result = forecast(snapshot)
    canonical(result)
    values = result.get("probabilities")
    if result.get("availability") is not True or not isinstance(values, dict) or not values:
        raise ValueError("FUTURE_ELIGIBLE_FORECAST_REQUIRED")
    if (any(type(v) not in (int, float) or not 0 <= v <= 1 or not math.isfinite(v) for v in values.values())
            or not math.isclose(math.fsum(values.values()), 1, abs_tol=1e-12, rel_tol=0)):
        raise ValueError("FUTURE_INVALID_PROBABILITY_VECTOR")
    if result["target"] != snapshot["target"] or result["horizon"] != snapshot["horizon"] or result["cutoff"] != snapshot["now"]:
        raise ValueError("FUTURE_STALE_FORECAST_REJECTED")
    return result


def _request(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise ValueError("FUTURE_REQUEST_ID_INVALID")
    return value


def execute_policy(episode, policy, model=None, request_id=None, expected_revision=None,
                   cost_weight=1., acquisition_limit=None):
    """Execute one same-cutoff bounded trajectory. DEFER never advances time.

    The caller supplies the private world only to this trusted executor. Every
    policy call receives a fresh public snapshot; its return is checked before
    the observation generator reveals anything. A failed trajectory commits no
    visibility or budget changes, including in this nonpersistent interface.
    """
    if not isinstance(episode, VirtualEpisode) or policy not in POLICIES:
        raise ValueError("FUTURE_POLICY_INVALID")
    cost_weight = finite(cost_weight, 0, 100)
    working = episode.clone()
    snapshot = working.public()
    if expected_revision is not None and integer(expected_revision, 0, 1000000) != snapshot["revision"]:
        raise ValueError("FUTURE_STALE_DECISION_REJECTED")
    request_id = _request(request_id or identifier("virtual-request-", [snapshot["episode_id"], snapshot["revision"], policy]))
    initial_revision = snapshot["revision"]
    decision_id = identifier("virtual-decision-", [snapshot["episode_id"], request_id, policy, initial_revision])
    limit = finite(acquisition_limit, 0, 1000000) if acquisition_limit is not None else snapshot["budget_remaining"]
    started, cpu = time.perf_counter(), time.process_time()
    before = after = checked_forecast(snapshot)
    kernel_calls, actions, acquisitions, snapshots = 1, [], [], []
    for step in range(len(CATEGORIES)+1):
        view = working.public()
        remaining_limit = max(0., limit-math.fsum(row["actual_cost"] for row in acquisitions))
        view["budget_remaining"] = min(view["budget_remaining"], remaining_limit)
        snapshots.append(deepcopy(view))
        selection = choose_action(view, policy, model, seed=42, cost_weight=cost_weight)
        canonical(selection)
        if selection.get("action") not in ("ACQUIRE_NOW", "DEFER", "IGNORE", "NO_ADDITIONAL_INFORMATION"):
            raise ValueError("FUTURE_POLICY_ACTION_UNSUPPORTED")
        value = selection.get("estimated_value")
        if value is not None:
            finite(value, -1e9, 1e9, "FUTURE_NONFINITE_RELEVANCE")
        finite(selection.get("estimated_cost", 0), 0, 100)
        actions.append(deepcopy(selection))
        if selection["action"] != "ACQUIRE_NOW":
            break
        category = selection.get("category")
        if category not in CATEGORIES:
            raise ValueError("FUTURE_CATEGORY_UNSUPPORTED")
        candidate = next(row for row in view["candidates"] if row["category"] == category)
        if candidate["cost"] > view["budget_remaining"]+1e-12:
            raise ValueError("FUTURE_ACQUISITION_BUDGET_EXHAUSTED")
        if not math.isclose(selection["estimated_cost"], candidate["cost"], abs_tol=1e-12, rel_tol=0):
            raise ValueError("FUTURE_ACQUISITION_QUOTE_MISMATCH")
        acquisition = working.acquire(category, decision_id)
        acquisition["forecast_before"] = deepcopy(after)
        after = checked_forecast(working.public())
        acquisition.update(forecast_after=deepcopy(after), estimated_future_relevance=value,
                           prediction_target=snapshot["target"], horizon=snapshot["horizon"],
                           decision_at=snapshot["now"], estimated_computation_cost=candidate["computation_cost"])
        acquisitions.append(acquisition)
        kernel_calls += 1
    else:
        raise ValueError("FUTURE_POLICY_STEP_LIMIT")
    if after["cutoff"] != before["cutoff"]:
        raise ValueError("FUTURE_ACQUISITION_MUST_NOT_ADVANCE_TIME")
    actual_cost = math.fsum(row["actual_cost"] for row in acquisitions)
    if actual_cost > min(snapshot["budget_remaining"], limit)+1e-12:
        raise ValueError("FUTURE_COST_ACCOUNTING_INVALID")
    result = {"schema_version": "dragonhydra.future-decision/1", "synthetic": True,
        "decision_id": decision_id, "request_id": request_id, "episode_id": snapshot["episode_id"],
        "group_id": snapshot["group_id"], "source_mode": "DEMONSTRATION", "policy": policy,
        "model_id": model["model_id"] if policy == "learned" else "virtual-policy-"+policy+"/1",
        "decision_at": snapshot["now"], "target": snapshot["target"], "horizon": snapshot["horizon"],
        "initial_state_revision": initial_revision, "final_state_revision": working.public()["revision"],
        "available_categories": [c["category"] for c in snapshot["candidates"] if c["availability"] == "AVAILABLE"],
        "before": before, "after": after, "actions": actions, "acquisitions": acquisitions,
        "decision_time_snapshots": snapshots, "random_policy_seed": 42,
        "acquisition_cost": actual_cost, "cost_unit": "VIRTUAL_CREDIT",
        "kernel_calls": kernel_calls, "computation_units": kernel_calls,
        "forecast_recomputations": kernel_calls, "computation_cost": .001*kernel_calls,
        "policy_estimation_units": len(actions), "cost_weight": cost_weight,
        "budget_before": snapshot["budget_remaining"], "budget_remaining": working.public()["budget_remaining"],
        "latency_ms": (time.perf_counter()-started)*1000, "cpu_ms": (time.process_time()-cpu)*1000,
        "outcome_state": "NOT_REVEALED_AT_DECISION", "expected_value_state": "EXPERIMENTAL_NOT_CALIBRATED"}
    canonical(result)
    episode._acquired, episode._spent, episode._revision = deepcopy(working._acquired), working._spent, working._revision
    return result


def score(vector, label):
    if (not isinstance(vector, dict) or not vector or label not in vector
            or any(type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1 for p in vector.values())
            or not math.isclose(math.fsum(vector.values()), 1, abs_tol=1e-12, rel_tol=0)):
        raise ValueError("FUTURE_OUTCOME_LABEL_MISMATCH")
    brier = math.fsum((v-float(k == label))**2 for k, v in vector.items())
    return {"brier": brier, "log_loss": -math.log(vector[label]) if vector[label] else None,
            "log_loss_infinite": vector[label] == 0}


def evaluate_decision(decision, outcome):
    if (decision["episode_id"] != outcome["episode_id"] or decision["target"] != outcome["target"]
            or decision["horizon"] != outcome["horizon"]
            or instant(decision["decision_at"]) >= instant(outcome["occurred_at"])
            or instant(outcome["available_at"]) < instant(outcome["occurred_at"])):
        raise ValueError("FUTURE_EVALUATION_IDENTITY_OR_TIME_INVALID")
    if any(decision[k]["target"] != decision["target"] or decision[k]["horizon"] != decision["horizon"]
           or decision[k]["cutoff"] != decision["decision_at"] for k in ("before", "after")):
        raise ValueError("FUTURE_EVALUATION_FORECAST_CUTOFF_MISMATCH")
    before, after = (score(decision[key]["probabilities"], outcome["label"]) for key in ("before", "after"))
    improvement = before["brier"]-after["brier"]
    cost = decision["acquisition_cost"]+decision["computation_cost"]
    return {"schema_version": "dragonhydra.future-evaluation/1", "synthetic": True,
        "evaluation_id": identifier("virtual-evaluation-", [decision["decision_id"], outcome["outcome_id"]]),
        "decision_id": decision["decision_id"], "episode_id": decision["episode_id"],
        "target": decision["target"], "horizon": decision["horizon"], "outcome": outcome,
        "before": before, "after": after, "observed_predictive_improvement": improvement,
        "acquisition_cost": decision["acquisition_cost"], "computation_cost": decision["computation_cost"],
        "net_usefulness": improvement-decision["cost_weight"]*cost,
        "acquisition_evaluations": [{"acquisition_id": item["acquisition_id"], "category": item["category"],
            "observed_predictive_improvement": score(item["forecast_before"]["probabilities"], outcome["label"])["brier"]
                                              -score(item["forecast_after"]["probabilities"], outcome["label"])["brier"],
            "actual_cost": item["actual_cost"], "outcome_id": outcome["outcome_id"]}
            for item in decision.get("acquisitions", [])],
        "cost_unit": "VIRTUAL_CREDIT; computation credit=0.001 per actual requested-horizon kernel call",
        "interpretation": "A negative measured benefit is retained; simulation does not establish real accuracy."}


class FutureService:
    contract_version = "core-next.engine/1"

    def __init__(self, directory, config=None):
        config = dict(config or {})
        if set(config)-{"experiment_acquisition_budget", "max_episodes", "max_decisions", "cost_weight"}:
            raise ValueError("FUTURE_CONFIGURATION_INVALID")
        self.limit = finite(config.get("experiment_acquisition_budget", 100.), 0, 1000000)
        self.max_episodes = integer(config.get("max_episodes", 512), 1, 1024)
        self.max_decisions = integer(config.get("max_decisions", 20000), 1, 100000)
        self.cost_weight = finite(config.get("cost_weight", 1.), 0, 100)
        self.journal = Journal(directory)
        self.lock = self.journal.lock
        self.closed, self._training = False, False

    @staticmethod
    def _episode(db, episode_id):
        row = db.execute("SELECT descriptor FROM episodes WHERE episode_id=?", (episode_id,)).fetchone()
        if not row:
            raise LookupError("FUTURE_EPISODE_NOT_FOUND")
        return VirtualEpisode.from_descriptor(json.loads(row[0]))

    @staticmethod
    def _active_model(db):
        key = Journal.metadata(db, "active_model")
        if key:
            row = db.execute("SELECT payload FROM models WHERE model_id=?", (key,)).fetchone()
            if row:
                return json.loads(row[0])
        return None

    @staticmethod
    def _model_available(model, now):
        if model is None:
            return False
        cutoff = model.get("available_at", model.get("frozen_at", model.get("training_label_cutoff")))
        return isinstance(cutoff, str) and instant(cutoff) <= instant(now)

    def _view(self, episode, model=None, current=None):
        snapshot = episode.public()
        current = current or checked_forecast(snapshot)
        estimates = []
        for candidate in snapshot["candidates"]:
            row = {"category": candidate["category"], "estimated_cost": candidate["cost"],
                   "estimated_computation_cost": candidate["computation_cost"], "estimated_value": None,
                   "state": "NO_TRAINED_POLICY"}
            if candidate["availability"] == "ACQUIRED":
                row["state"] = "ALREADY_ACQUIRED"
            elif snapshot["now_minute"] >= snapshot["target_maturity_minute"]:
                row["state"] = "TARGET_WINDOW_CLOSED"
            elif model and not self._model_available(model, snapshot["now"]):
                row["state"] = "POLICY_NOT_AVAILABLE_AT_CUTOFF"
            elif model:
                row.update(estimate(snapshot, candidate["category"], model))
                row["state"] = "EXPERIMENTAL_NOT_CALIBRATED"
            estimates.append(row)
        return {"episode_id": snapshot["episode_id"], "synthetic": True,
                "universe": episode._family, "snapshot": snapshot,
                "current_forecast": current, "estimates": estimates}

    def create_episode(self, universe="constant", seed=400042, target="GOAL_OCCURRENCE", horizon="10", minute=60, budget=.12):
        if self.closed:
            raise ValueError("FUTURE_SERVICE_CLOSED")
        episode = VirtualEpisode(universe, seed, minute=minute, target=target, horizon=horizon, budget=budget)
        key = episode.public()["episode_id"]
        with self.lock, self.journal.connect() as db:
            if db.execute("SELECT 1 FROM episodes WHERE episode_id=?", (key,)).fetchone():
                return {"episode_id": key, "synthetic": True, "reused": True}
            if db.execute("SELECT count(*) FROM episodes").fetchone()[0] >= self.max_episodes:
                raise ValueError("FUTURE_EPISODE_RETENTION_LIMIT")
            view = self._view(episode, self._active_model(db))
            db.execute("INSERT INTO episodes VALUES(?,?,?)", (key, canonical(episode.descriptor()), canonical(view)))
            db.commit()
        return {"episode_id": key, "synthetic": True}

    def episodes(self):
        with self.journal.connect() as db:
            items = [json.loads(row[0]) for row in db.execute("SELECT view FROM episodes ORDER BY rowid DESC LIMIT 512")]
        return {"items": items, "synthetic": True}

    def episode(self, episode_id):
        with self.journal.connect() as db:
            row = db.execute("SELECT view FROM episodes WHERE episode_id=?", (episode_id,)).fetchone()
            if not row:
                raise LookupError("FUTURE_EPISODE_NOT_FOUND")
            view = json.loads(row[0])
            decisions = Journal.items(db, "decisions", episode_id=episode_id, limit=100)
            keys = {item["decision_id"] for item in decisions}
            evaluations = [item for item in Journal.items(db, "evaluations", limit=20000) if item["decision_id"] in keys]
        return {**view, "decisions": decisions, "evaluations": evaluations}

    def _save_decision(self, db, episode, receipt, digest):
        """Caller holds one transaction, including the shared credit ledger."""
        episode._revision += 1
        receipt["final_state_revision"] = episode._revision
        canonical(receipt)
        db.execute("INSERT INTO decisions VALUES(?,?,?,?,?)", (receipt["decision_id"], receipt["episode_id"],
                    receipt["request_id"], digest, canonical(receipt)))
        for acquisition in receipt["acquisitions"]:
            db.execute("INSERT INTO acquisitions VALUES(?,?,?)", (acquisition["acquisition_id"], receipt["decision_id"], canonical(acquisition)))
        for stage in ("before", "after"):
            prediction_id = identifier("virtual-prediction-", [receipt["decision_id"], stage])
            db.execute("INSERT INTO predictions VALUES(?,?,?,?)", (prediction_id, receipt["decision_id"], stage, canonical(receipt[stage])))
        spent = self.journal.metadata(db, "acquisition_spent", 0.)
        self.journal.put_meta(db, "acquisition_spent", spent+receipt["acquisition_cost"])
        self.journal.put_meta(db, "decisions", self.journal.metadata(db, "decisions", 0)+1)

    def decide(self, episode_id, policy, request_id, expected_revision):
        if self.closed:
            raise ValueError("FUTURE_SERVICE_CLOSED")
        _request(request_id); integer(expected_revision, 0, 1000000)
        digest = identifier("request:", [episode_id, policy, request_id, expected_revision])
        with self.lock, self.journal.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT request_hash,payload FROM decisions WHERE request_id=?", (request_id,)).fetchone()
            if previous:
                if previous[0] != digest:
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                return json.loads(previous[1])
            if db.execute("SELECT count(*) FROM decisions").fetchone()[0] >= self.max_decisions:
                raise ValueError("FUTURE_DECISION_RETENTION_LIMIT")
            episode = self._episode(db, episode_id)
            model = self._active_model(db)
            if policy == "learned" and not self._model_available(model, episode.public()["now"]):
                raise ValueError("FUTURE_POLICY_NOT_AVAILABLE_AT_CUTOFF")
            spent = self.journal.metadata(db, "acquisition_spent", 0.)
            receipt = execute_policy(episode, policy, model, request_id, expected_revision,
                                     self.cost_weight, max(0., self.limit-spent))
            # Even a no-acquisition decision advances the operational revision;
            # duplicate request IDs return the immutable previous receipt.
            self._save_decision(db, episode, receipt, digest)
            view = self._view(episode, model, current=receipt["after"])
            db.execute("UPDATE episodes SET descriptor=?,view=? WHERE episode_id=?", (canonical(episode.descriptor()), canonical(view), episode_id))
            db.commit()
        return receipt

    def advance(self, episode_id, minutes, expected_revision):
        if self.closed:
            raise ValueError("FUTURE_SERVICE_CLOSED")
        with self.lock, self.journal.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            episode = self._episode(db, episode_id)
            if episode.public()["revision"] != integer(expected_revision, 0, 1000000):
                raise ValueError("FUTURE_STALE_DECISION_REJECTED")
            episode.advance(minutes)
            resumed = None
            previous_decisions = Journal.items(db, "decisions", episode_id=episode_id, limit=1)
            view_now = episode.public()
            if previous_decisions and view_now["now_minute"] < view_now["target_maturity_minute"]:
                previous = previous_decisions[-1]
                deferred = next((a for a in reversed(previous["actions"]) if a["action"] == "DEFER"), None)
                if deferred and any(c["category"] == deferred["category"] and c["availability"] == "AVAILABLE"
                                    for c in view_now["candidates"]):
                    if db.execute("SELECT count(*) FROM decisions").fetchone()[0] < self.max_decisions:
                        bound_model = None
                        if previous["policy"] == "learned":
                            row = db.execute("SELECT payload FROM models WHERE model_id=?", (previous["model_id"],)).fetchone()
                            if not row:
                                raise ValueError("FUTURE_DEFERRED_FROZEN_MODEL_MISSING")
                            bound_model = json.loads(row[0])
                        request_id = identifier("virtual-resume-", [previous["decision_id"], view_now["revision"]])
                        spent = self.journal.metadata(db, "acquisition_spent", 0.)
                        resumed = execute_policy(episode, previous["policy"], bound_model, request_id,
                            view_now["revision"], previous["cost_weight"], max(0., self.limit-spent))
                        resumed["resumes_decision_id"] = previous["decision_id"]
                        digest = identifier("request:", [episode_id, previous["policy"], request_id, view_now["revision"]])
                        self._save_decision(db, episode, resumed, digest)
            try:
                outcome = episode.matured_outcome()
            except ValueError as error:
                if str(error) != "FUTURE_OUTCOME_NOT_AVAILABLE":
                    raise
                outcome = None
            if outcome:
                all_decisions = Journal.items(db, "decisions", episode_id=episode_id, limit=self.max_decisions)
                for decision in all_decisions:
                    if instant(decision["decision_at"]) >= instant(outcome["occurred_at"]):
                        continue
                    result = evaluate_decision(decision, outcome)
                    result["deferred_future_relevance"] = []
                    for later in all_decisions:
                        if later.get("resumes_decision_id") != decision["decision_id"]:
                            continue
                        for acquisition in later["acquisitions"]:
                            proposed = next((a for a in decision["actions"] if a["action"] == "DEFER" and a["category"] == acquisition["category"]), None)
                            if proposed:
                                actual = score(acquisition["forecast_before"]["probabilities"], outcome["label"])["brier"]-score(acquisition["forecast_after"]["probabilities"], outcome["label"])["brier"]
                                result["deferred_future_relevance"].append({"category": acquisition["category"],
                                    "predicted_at": decision["decision_at"], "acquired_at": acquisition["decision_at"],
                                    "predicted_relevance": proposed["estimated_value"], "observed_local_improvement": actual,
                                    "original_model_id": decision["model_id"], "resumed_decision_id": later["decision_id"]})
                    db.execute("INSERT OR IGNORE INTO evaluations VALUES(?,?,?)", (result["evaluation_id"], decision["decision_id"], canonical(result)))
            view = self._view(episode, self._active_model(db), current=resumed["after"] if resumed else None)
            db.execute("UPDATE episodes SET descriptor=?,view=? WHERE episode_id=?", (canonical(episode.descriptor()), canonical(view), episode_id))
            db.commit()
        return self.episode(episode_id)

    def models(self):
        with self.journal.connect() as db:
            return {"items": Journal.items(db, "models", limit=32), "synthetic": True}

    def model(self, model_id):
        with self.journal.connect() as db:
            row = db.execute("SELECT payload FROM models WHERE model_id=?", (model_id,)).fetchone()
            if not row:
                raise LookupError("FUTURE_MODEL_NOT_FOUND")
            return json.loads(row[0])

    def experiments(self):
        with self.journal.connect() as db:
            return {"items": Journal.items(db, "experiments", limit=32), "synthetic": True}

    def experiment(self, experiment_id):
        with self.journal.connect() as db:
            row = db.execute("SELECT payload FROM experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
            if not row:
                raise LookupError("FUTURE_EXPERIMENT_NOT_FOUND")
            return json.loads(row[0])

    def train(self, seed=42, cases_per_family=200):
        if self.closed:
            raise ValueError("FUTURE_SERVICE_CLOSED")
        integer(seed); integer(cases_per_family, 10, 1000)
        key = identifier("training-request:", [seed, cases_per_family])
        with self.lock:
            with self.journal.connect() as db:
                previous = self.journal.metadata(db, key)
                if previous:
                    return self.experiment(previous)
                if db.execute("SELECT count(*) FROM experiments").fetchone()[0] >= 32:
                    raise ValueError("FUTURE_EXPERIMENT_RETENTION_LIMIT")
            self._training = True
            try:
                from .experiments import train_and_evaluate
                result = train_and_evaluate(seed=seed, cases=cases_per_family)
                model = result["model"]
                validate_model(model)
                experiment_id = identifier("virtual-experiment-", [seed, cases_per_family, model["model_id"]])
                result = {"experiment_id": experiment_id, "model_id": model["model_id"], "synthetic": True, **result}
                canonical(result)
                with self.journal.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("INSERT OR IGNORE INTO models VALUES(?,?)", (model["model_id"], canonical(model)))
                    db.execute("INSERT INTO experiments VALUES(?,?)", (experiment_id, canonical(result)))
                    self.journal.put_meta(db, "active_model", model["model_id"])
                    self.journal.put_meta(db, key, experiment_id)
                    for row in db.execute("SELECT episode_id,descriptor,view FROM episodes").fetchall():
                        episode = VirtualEpisode.from_descriptor(json.loads(row[1]))
                        old = json.loads(row[2])
                        view = self._view(episode, model, current=old["current_forecast"])
                        db.execute("UPDATE episodes SET view=? WHERE episode_id=?", (canonical(view), row[0]))
                    db.commit()
                return result
            finally:
                self._training = False

    def status(self):
        with self.journal.connect() as db:
            model_id = self.journal.metadata(db, "active_model")
            spent = self.journal.metadata(db, "acquisition_spent", 0.)
            count = self.journal.metadata(db, "decisions", 0)
        return {"schema_version": "dragonhydra.future-status/1", "version": VERSION,
            "synthetic": True, "mode": "VIRTUAL_ONLY", "training": self._training,
            "active_model_id": model_id, "model_state": "FROZEN_EXPERIMENTAL" if model_id else "UNTRAINED",
            "available_universes": list(FAMILIES), "acquisition_budget_total": self.limit,
            "acquisition_budget_spent": spent, "acquisition_budget_remaining": max(0., self.limit-spent),
            "decisions": count, "real_api_calls": 0, "real_sporting_records": 0,
            "calibration_state": "UNVERIFIED_REAL_WORLD", "generalization_claim": "MEASURED_REPORT_ONLY_NO_GUARANTEED_IMPROVEMENT"}

    def observe(self):
        return {"state": "DEGRADED", "reason": "VIRTUAL_EXPERIMENTAL_RESEARCH_ONLY",
                "metrics": {"configured": True, "retained_observation_count": self.status()["decisions"]},
                "evidence": ("Future-value regression is experimental; no real-world accuracy claim",)}

    def close(self):
        self.closed = True

    def stop(self):
        self.close()
