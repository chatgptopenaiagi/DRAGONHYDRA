"""Disjoint chronological synthetic learning and untouched-world policy study."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import math
import random

from .forecast import CATEGORIES, TARGETS, canonical, forecast, instant
from .learning import feature_vector, select_model, validate_model
from .policies import POLICIES

EXPERIMENT_ACQUISITION_CAP = 100.0


def proper_loss(probabilities, label):
    if not probabilities or label not in probabilities:
        raise ValueError("FUTURE_OUTCOME_PROBABILITY_LABEL_MISMATCH")
    return math.fsum((probability - float(key == label))**2 for key, probability in probabilities.items())


def _settings(seed, cases, split):
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1 or type(cases) is not int or not 6 <= cases <= 2000:
        raise ValueError("FUTURE_EXPERIMENT_BOUNDS")
    phases = {"TRAIN": 0, "VALIDATION": 200000, "FINAL_TEST": 400000}
    if split not in phases:
        raise ValueError("FUTURE_EXPERIMENT_SPLIT_INVALID")
    values = random.Random(seed).sample(range(1000, 99000), cases)
    return [phases[split] + value for value in values]


def _specs(seed, cases, split):
    from .environment import TRAIN_FAMILIES, VALIDATION_FAMILIES, TEST_FAMILIES
    families = {"TRAIN": TRAIN_FAMILIES, "VALIDATION": VALIDATION_FAMILIES, "FINAL_TEST": TEST_FAMILIES}[split]
    horizons = ("1", "5", "10", "30", "FULL_TIME")
    minutes = (50, 60, 70, 80, 87)
    for family in families:
        for index, world_seed in enumerate(_settings(seed, cases, split)):
            for target in TARGETS:
                yield {"family": family, "seed": world_seed, "minute": minutes[(index // 5) % len(minutes)],
                       "target": target, "horizon": "FULL_TIME" if target == "FULL_TIME_RESULT" else horizons[index % 5],
                       "budget": (.04, .08, .12)[index % 3]}


def _settle(episode):
    from .environment import OUTCOME_DELAY_MINUTES
    snapshot = episode.public()
    delta = max(0.0, snapshot["target_maturity_minute"] + OUTCOME_DELAY_MINUTES - snapshot["now_minute"])
    episode.advance(delta + 1e-9)
    return episode.matured_outcome()


def make_rows(seed=42, cases=40, split="TRAIN"):
    """Create acquisition labels at identical pre/post cutoffs; no FINAL access."""
    from .environment import VirtualEpisode
    if split not in ("TRAIN", "VALIDATION"):
        raise ValueError("FUTURE_TRAINING_FINAL_TEST_ACCESS_REJECTED")
    rows = []
    for spec in _specs(seed, cases, split):
        base = VirtualEpisode(**spec)
        contexts = [base]
        initial = base.public()
        affordable = [row for row in initial["candidates"] if row["availability"] == "AVAILABLE" and row["cost"] <= initial["budget_remaining"]]
        if affordable:
            conditioned = base.clone()
            selected = affordable[spec["seed"] % len(affordable)]["category"]
            conditioned.acquire(selected, "virtual-context-" + str(spec["seed"]))
            contexts.append(conditioned)
        fatigue = next(row for row in initial["candidates"] if row["category"] == "fatigue")
        delay = (instant(fatigue["available_at"]) - instant(initial["now"])).total_seconds() / 60
        if initial["now_minute"] + delay < initial["target_maturity_minute"]:
            delayed = base.clone()
            delayed.advance(delay)
            contexts.append(delayed)
        for context in contexts:
            snapshot = context.public()
            before = forecast(snapshot)
            if not before["availability"]:
                raise ValueError("FUTURE_TRAINING_FORECAST_WITHHELD")
            snapshot_hash = hashlib.sha256(canonical(snapshot).encode()).hexdigest()
            decision_id = "virtual-training-" + snapshot_hash[:32]
            for candidate in snapshot["candidates"]:
                delay = max(0.0, (instant(candidate["available_at"]) - instant(snapshot["now"])).total_seconds()/60)
                if candidate["availability"] not in ("AVAILABLE", "PENDING") or candidate["cost"] > snapshot["budget_remaining"] or snapshot["now_minute"] + delay >= snapshot["target_maturity_minute"]:
                    continue
                category = candidate["category"]
                # Freeze features before acquisition and obtain labels only
                # after the target matures. The clone shares the same world.
                features = feature_vector(snapshot, category)
                acquired = context.clone()
                if delay:
                    acquired.advance(delay)
                evaluation_before = forecast(acquired.public()) if delay else before
                acquired.acquire(category, decision_id)
                after = forecast(acquired.public())
                if not after["availability"] or evaluation_before["cutoff"] != after["cutoff"]:
                    raise ValueError("FUTURE_TRAINING_ACQUISITION_CUTOFF_MISMATCH")
                outcome = _settle(acquired)
                old = proper_loss(evaluation_before["probabilities"], outcome["label"])
                new = proper_loss(after["probabilities"], outcome["label"])
                rows.append({"schema_version": "dragonhydra.future-training-row/1", "split": split,
                             "episode_id": snapshot["episode_id"], "group_id": snapshot["group_id"],
                             "decision_id": decision_id, "target": snapshot["target"], "horizon": snapshot["horizon"],
                             "category": category, "cost": candidate["cost"], "computation_cost": candidate["computation_cost"],
                             "decision_at": snapshot["now"], "label_available_at": outcome["available_at"],
                             "acquisition_at": after["cutoff"], "evaluation_cutoff": evaluation_before["cutoff"],
                             "outcome_occurred_at": outcome["occurred_at"],
                             "snapshot_sha256": snapshot_hash, "features": features, "label": old - new,
                             "before_brier": old, "after_brier": new, "outcome_id": outcome["outcome_id"]})
    return rows


def train_model(seed=42, cases=40, cost_weight=1.0):
    train = make_rows(seed, cases, "TRAIN")
    validation = make_rows(seed, cases, "VALIDATION")
    model = select_model(train, validation, cost_weight=cost_weight)
    return {"model": model,
            "training_summary": {"train_rows": len(train), "validation_rows": len(validation),
                                 "train_root_groups": len({row["group_id"] for row in train}),
                                 "validation_root_groups": len({row["group_id"] for row in validation}),
                                 "training_label_cutoff": model["training_label_cutoff"],
                                 "available_at": model["available_at"],
                                 "prospective_pending_rows": sum(row["features"]["pending"] == 1 for row in train),
                                 "validation_prospective_pending_rows": sum(row["features"]["pending"] == 1 for row in validation),
                                 "predeclared_seed_ranges_disjoint": True, "final_test_constructed": False,
                                 "label_definition": "Sum-of-class squared Brier before minus after acquisition at identical evaluation cutoff; PENDING features freeze earlier at decision time."}}


def _mean(values):
    return math.fsum(values) / len(values) if values else None


def _grouped(values):
    """Equal weight per underlying root group, not per correlated branch/target."""
    groups = defaultdict(list)
    for group_id, value in values:
        groups[group_id].append(value)
    means = [_mean(rows) for rows in groups.values()]
    center = _mean(means)
    if not means:
        return {"mean": None, "standard_error": None, "approximate_95_percent_interval": None, "root_group_count": 0}
    variance = math.fsum((value - center)**2 for value in means) / (len(means) - 1) if len(means) > 1 else 0.0
    se = math.sqrt(variance / len(means))
    return {"mean": center, "standard_error": se,
            "approximate_95_percent_interval": [center - 1.96 * se, center + 1.96 * se],
            "root_group_count": len(means), "method": "Equal-weight root-group paired means; normal approximation, no multiplicity adjustment."}


def _metrics(rows):
    infinite = sum(row["log_loss"] is None for row in rows)
    bins = []
    for index in range(10):
        members = [row for row in rows if min(9, int(row["confidence"] * 10)) == index]
        bins.append({"lower": index / 10, "upper": (index + 1) / 10, "count": len(members),
                     "confidence": _mean([row["confidence"] for row in members]),
                     "accuracy": _mean([float(row["correct"]) for row in members])})
    return {"episode_count": len(rows), "brier_score": _mean([row["brier"] for row in rows]),
            "log_loss": None if infinite else _mean([row["log_loss"] for row in rows]),
            "log_loss_infinite": bool(infinite), "zero_probability_labels": infinite,
            "ece": math.fsum(row["count"] * abs(row["confidence"] - row["accuracy"]) for row in bins if row["count"]) / len(rows) if rows else None,
            "reliability_bins": bins}


def train_and_evaluate(seed=42, cases=40, cost_weight=1.0):
    """Freeze using TRAIN/VALIDATION, then evaluate all five policies on new worlds."""
    from .environment import VirtualEpisode, TRAIN_FAMILIES, VALIDATION_FAMILIES, TEST_FAMILIES
    from .service import execute_policy
    trained = train_model(seed, cases, cost_weight)
    model = validate_model(trained["model"])
    frozen_hash = model["content_sha256"]
    used_groups = set(model["training_group_ids"]) | set(model["selection"]["validation_group_ids"])
    measured = {policy: [] for policy in POLICIES}
    receipts = {policy: [] for policy in POLICIES}
    spent = {policy: 0.0 for policy in POLICIES}
    budget_rejections = Counter()
    hindsight = {policy: Counter() for policy in POLICIES}
    hindsight_kernel_calls = 0
    prospective = []
    episode_ids, test_groups = [], set()
    # No FINAL_TEST world is constructed until both selection and content
    # hashing above have completed. No test result is fed back to selection.
    for spec in _specs(seed, cases, "FINAL_TEST"):
        base = VirtualEpisode(**spec)
        public = base.public()
        if public["group_id"] in used_groups or instant(public["now"]) <= instant(model["available_at"]):
            raise ValueError("FUTURE_FINAL_TEST_GROUP_OR_TIME_LEAKAGE")
        episode_ids.append(public["episode_id"])
        test_groups.add(public["group_id"])
        decisions = []
        initial_remaining = {}
        # All five strategies decide before any outcome or retrospective
        # opportunity is inspected, with independent equal experiment caps.
        for policy in POLICIES:
            remaining = max(0.0, EXPERIMENT_ACQUISITION_CAP - spent[policy])
            initial_remaining[policy] = remaining
            budget_rejections[policy] += sum(candidate["availability"] == "AVAILABLE"
                and candidate["cost"] <= public["budget_remaining"] + 1e-12
                and candidate["cost"] > remaining + 1e-12 for candidate in public["candidates"])
            episode = base.clone()
            receipt = execute_policy(episode, policy, model=model if policy == "learned" else None,
                                     request_id="virtual-study-" + policy + "-" + public["episode_id"][8:],
                                     cost_weight=cost_weight, acquisition_limit=remaining)
            spent[policy] = math.fsum((spent[policy], receipt["acquisition_cost"]))
            if spent[policy] > EXPERIMENT_ACQUISITION_CAP + 1e-9:
                raise ValueError("FUTURE_EXPERIMENT_ACQUISITION_CAP_EXCEEDED")
            decisions.append((policy, episode, receipt))
        expected_outcome = None
        for policy, episode, receipt in decisions:
            outcome = _settle(episode)
            identity = outcome["outcome_id"], outcome["label"]
            if expected_outcome is None:
                expected_outcome = identity
            elif identity != expected_outcome:
                raise ValueError("FUTURE_ACQUISITION_CHANGED_OUTCOME")
            vector = receipt["after"]["probabilities"]
            label = outcome["label"]
            brier = proper_loss(vector, label)
            p = vector[label]
            chosen = max(sorted(vector), key=vector.get)
            total_cost = receipt["acquisition_cost"] + receipt["computation_cost"]
            measured[policy].append({"episode_id": public["episode_id"], "group_id": public["group_id"],
                                     "target": public["target"], "horizon": public["horizon"], "brier": brier,
                                     "log_loss": -math.log(p) if p else None, "confidence": vector[chosen], "correct": chosen == label,
                                     "acquisition_cost": receipt["acquisition_cost"], "computation_cost": receipt["computation_cost"],
                                     "total_cost": total_cost, "utility": -brier - cost_weight * total_cost})
            receipts[policy].append(receipt)
            for acquisition in receipt["acquisitions"]:
                if not {"forecast_before", "forecast_after"} <= acquisition.keys():
                    hindsight[policy]["actual_marginal_not_estimated"] += 1
                    continue
                marginal = proper_loss(acquisition["forecast_before"]["probabilities"], label) - proper_loss(acquisition["forecast_after"]["probabilities"], label)
                incremental_compute_cost = receipt["computation_cost"] / receipt["kernel_calls"]
                net = marginal - cost_weight * (acquisition["actual_cost"] + incremental_compute_cost)
                hindsight[policy]["acquired_positive_realized_marginal" if marginal > 1e-12 else "acquired_nonpositive_realized_marginal"] += 1
                hindsight[policy]["acquired_positive_realized_net" if net > 1e-12 else "acquired_nonpositive_realized_net"] += 1
        # Hindsight probes are evaluation-only and never fed back into this
        # episode's already frozen actions, future policy features or model.
        probe_before = forecast(public)
        hindsight_kernel_calls += 1
        for candidate in public["candidates"]:
            if candidate["availability"] != "AVAILABLE" or candidate["cost"] > public["budget_remaining"] + 1e-12:
                continue
            probe = base.clone()
            probe.acquire(candidate["category"], "virtual-hindsight-" + public["episode_id"][8:])
            probe_after = forecast(probe.public())
            hindsight_kernel_calls += 1
            probe_outcome = _settle(probe)
            if (probe_outcome["outcome_id"], probe_outcome["label"]) != expected_outcome:
                raise ValueError("FUTURE_HINDSIGHT_CHANGED_OUTCOME")
            marginal = proper_loss(probe_before["probabilities"], probe_outcome["label"]) - proper_loss(probe_after["probabilities"], probe_outcome["label"])
            net = marginal - cost_weight * (candidate["cost"] + candidate["computation_cost"])
            for policy, _, receipt in decisions:
                acquired_categories = {row["category"] for row in receipt["acquisitions"]}
                hindsight[policy]["initial_opportunities_evaluated"] += 1
                if candidate["category"] not in acquired_categories and marginal > 1e-12:
                    key = "missed_positive_initial_opportunity" if candidate["cost"] <= initial_remaining[policy] + 1e-12 else "budget_constrained_positive_initial_opportunity"
                    hindsight[policy][key] += 1
                if candidate["category"] not in acquired_categories and net > 1e-12:
                    key = "missed_positive_net_initial_opportunity" if candidate["cost"] <= initial_remaining[policy] + 1e-12 else "budget_constrained_positive_net_initial_opportunity"
                    hindsight[policy][key] += 1
        # Prospective value is predicted from S_t before the observation exists.
        # Future state enters only this trusted, post-action label probe.
        from .learning import estimate
        fatigue = next(row for row in public["candidates"] if row["category"] == "fatigue")
        delay = max(0.0, (instant(fatigue["available_at"]) - instant(public["now"])).total_seconds()/60)
        if fatigue["availability"] == "PENDING" and public["now_minute"] + delay < public["target_maturity_minute"] and fatigue["cost"] <= public["budget_remaining"]:
            prediction = estimate(public, "fatigue", model)["estimated_value"]
            shadow = base.clone()
            shadow.advance(delay)
            future_before = forecast(shadow.public())
            shadow.acquire("fatigue", "virtual-prospective-" + public["episode_id"][8:])
            future_after = forecast(shadow.public())
            hindsight_kernel_calls += 2
            outcome = _settle(shadow)
            if future_before["cutoff"] != future_after["cutoff"] or (outcome["outcome_id"], outcome["label"]) != expected_outcome:
                raise ValueError("FUTURE_PROSPECTIVE_PROBE_COUPLING_FAILED")
            value = proper_loss(future_before["probabilities"], outcome["label"]) - proper_loss(future_after["probabilities"], outcome["label"])
            prospective.append({"group_id": public["group_id"], "prediction": prediction, "realized_value": value,
                                "decision_before_acquisition": instant(public["now"]) < instant(future_before["cutoff"])})
    if validate_model(model)["content_sha256"] != frozen_hash:
        raise ValueError("FUTURE_FINAL_TEST_CHANGED_FROZEN_MODEL")
    comparisons = []
    for policy in POLICIES:
        rows, policy_receipts = measured[policy], receipts[policy]
        baseline = {row["episode_id"]: row for row in measured["acquire_none"]}
        segments = defaultdict(list)
        for row in rows:
            segments[row["target"] + "/" + row["horizon"]].append(row)
        log_pairs = [(row["group_id"], baseline[row["episode_id"]]["log_loss"] - row["log_loss"]) for row in rows
                     if row["log_loss"] is not None and baseline[row["episode_id"]]["log_loss"] is not None]
        comparisons.append({"policy": policy, **_metrics(rows), "root_group_count": len(test_groups),
            "mean_acquisition_cost": _mean([row["acquisition_cost"] for row in rows]),
            "mean_computation_cost": _mean([row["computation_cost"] for row in rows]),
            "mean_total_cost": _mean([row["total_cost"] for row in rows]),
            "mean_cost_adjusted_utility": _mean([row["utility"] for row in rows]),
            "acquisition_count": sum(len(row["acquisitions"]) for row in policy_receipts),
            "kernel_calls": sum(row["kernel_calls"] for row in policy_receipts),
            "computation_units": sum(row["computation_units"] for row in policy_receipts),
            "policy_estimation_units": sum(row["policy_estimation_units"] for row in policy_receipts),
            "action_counts": dict(Counter(action["action"] for row in policy_receipts for action in row["actions"])),
            "budget_violation_count": sum(row["budget_remaining"] < -1e-12 for row in policy_receipts),
            "experiment_budget_initial": EXPERIMENT_ACQUISITION_CAP,
            "experiment_acquisition_spent": spent[policy],
            "experiment_acquisition_remaining": max(0.0, EXPERIMENT_ACQUISITION_CAP - spent[policy]),
            "experiment_budget_rejections": budget_rejections[policy],
            "hindsight_realized_counts": {key: hindsight[policy][key] for key in (
                "initial_opportunities_evaluated", "acquired_positive_realized_marginal", "acquired_nonpositive_realized_marginal",
                "acquired_positive_realized_net", "acquired_nonpositive_realized_net", "actual_marginal_not_estimated",
                "missed_positive_initial_opportunity", "missed_positive_net_initial_opportunity",
                "budget_constrained_positive_initial_opportunity", "budget_constrained_positive_net_initial_opportunity")},
            "paired_vs_acquire_none": {
                "brier_improvement": _grouped([(row["group_id"], baseline[row["episode_id"]]["brier"] - row["brier"]) for row in rows]),
                "net_utility_improvement": _grouped([(row["group_id"], row["utility"] - baseline[row["episode_id"]]["utility"]) for row in rows]),
                "log_loss_improvement_nats": _grouped(log_pairs), "finite_log_loss_pair_count": len(log_pairs)},
            "metrics_by_target_horizon": {key: _metrics(value) for key, value in sorted(segments.items())}})
    report = {"schema_version": "dragonhydra.future-learning-study/1", "status": "RESEARCH_ONLY", "synthetic": True,
              "seed": seed, "cases_per_family": cases, "train_families": list(TRAIN_FAMILIES),
              "validation_families": list(VALIDATION_FAMILIES), "final_test_families": list(TEST_FAMILIES),
              "training_summary": trained["training_summary"], "model_id": model["model_id"],
              "model_content_sha256": frozen_hash, "model_available_at": model["available_at"],
              "final_test_access_after_freeze": True, "final_test_episode_ids": episode_ids,
              "final_test_root_group_ids": sorted(test_groups), "group_splits_disjoint": True,
              "test_episode_count_per_policy": len(episode_ids), "policy_comparison": comparisons,
              "small_root_group_sample": len(test_groups) < 30,
              "experiment_acquisition_cap_per_policy": EXPERIMENT_ACQUISITION_CAP,
              "hindsight_analysis_kernel_calls": hindsight_kernel_calls,
              "prospective_pending_value": {
                  "category": "fatigue", "count": len(prospective),
                  "decision_strictly_before_acquisition_count": sum(row["decision_before_acquisition"] for row in prospective),
                  "mean_estimated_value": _mean([row["prediction"] for row in prospective]),
                  "mean_realized_local_value": _mean([row["realized_value"] for row in prospective]),
                  "mean_squared_error": _mean([(row["prediction"]-row["realized_value"])**2 for row in prospective]),
                  "constant_train_pending_baseline": model["uncertainty_by_category"]["fatigue"]["pending_training_label_mean"],
                  "constant_train_pending_baseline_mse": _mean([(model["uncertainty_by_category"]["fatigue"]["pending_training_label_mean"]-row["realized_value"])**2 for row in prospective]),
                  "grouped_signed_error_estimate_minus_realized": _grouped([(row["group_id"], row["prediction"]-row["realized_value"]) for row in prospective]),
                  "grouped_realized_value": _grouped([(row["group_id"], row["realized_value"]) for row in prospective]),
                  "calibration_state": "UNVERIFIED",
                  "scope": "Frozen model estimates E[local Brier improvement at availability|public S_t]; shadow outcomes are inspected only after all actual policy decisions, never used as features or for fitting."},
              "hindsight_scope": "Realized one-outcome, same-cutoff initial one-step opportunities, inspected only after all five policy decisions. Positive means >1e-12; nonpositive realized benefit does not prove a bad expected decision.",
              "experiment_budget_rejections_definition": "Initially AVAILABLE quotes affordable under the match budget but blocked by the remaining experiment acquisition cap; not failed transactions.",
              "cost_weight": cost_weight, "cost_unit": "VIRTUAL_CREDIT_NOT_MONEY",
              "metric_definitions": {"brier": "Sum over classes of (p-one_hot_label)^2; binary equals twice scalar binary Brier.",
                                     "log_loss": "Natural-log loss; zero probability is reported as infinite, not clipped.",
                                     "utility": "-Brier-cost_weight*(actual acquisition cost + actual computation cost).",
                                     "uncertainty": "Paired root-group means; approximate normal interval without multiplicity correction."},
              "limitations": ["All worlds, observations and outcomes are fictional; no real calibration or production skill is established.",
                              "Final worlds were withheld from fitting and threshold selection; this finite synthetic result does not establish general transfer.",
                              "Negative policy utility and worse proper scores remain valid study outcomes.",
                              "Overall metrics mix targets/horizons and are descriptive; inspect the matching target/horizon segments.",
                              "Policy acquisition changes visibility only; all five strategies settle the same underlying episode outcome.",
                              "Deferred information is not automatically acquired or allowed to advance the same-time policy trajectory."]}
    return {"model": model, "report": report}
