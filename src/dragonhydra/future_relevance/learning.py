"""Four TRAIN-only ridge regressions for conditional value of observable evidence."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import math

from .forecast import CATEGORIES, TARGETS, canonical, instant, number, visible_acquired

HORIZONS = ("1", "5", "10", "30", "FULL_TIME")
FEATURES = ("intercept", "minute_fraction", "remaining_fraction", "elapsed_fraction", "score_difference",
            "budget_fraction", "cost", "computation_cost", "freshness_fraction", "freshness_missing",
            "pending", "delay_fraction") + tuple("acquired_" + name for name in CATEGORIES) + (
            "visible_possession", "visible_shots", "visible_fatigue", "visible_card_difference") + tuple(
            "target_" + name for name in TARGETS) + tuple("horizon_" + name for name in HORIZONS)
ROW_FIELDS = {"schema_version", "split", "episode_id", "group_id", "decision_id", "target", "horizon",
              "category", "cost", "computation_cost", "decision_at", "label_available_at", "snapshot_sha256",
              "acquisition_at", "evaluation_cutoff", "outcome_occurred_at",
              "features", "label", "before_brier", "after_brier", "outcome_id"}


def feature_vector(snapshot, category):
    """Whitelist only pre-decision context, including eligible revealed values."""
    visible = visible_acquired(snapshot)
    if category not in CATEGORIES:
        raise ValueError("FUTURE_FEATURE_CATEGORY_INVALID")
    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 4:
        raise ValueError("FUTURE_CANDIDATE_SCHEMA_INVALID")
    matches = [candidate for candidate in candidates if candidate.get("category") == category]
    if len(matches) != 1:
        raise ValueError("FUTURE_FEATURE_CANDIDATE_MISSING_OR_DUPLICATE")
    candidate = matches[0]
    availability = candidate.get("availability")
    if availability not in ("AVAILABLE", "PENDING", "ACQUIRED", "UNOBSERVABLE"):
        raise ValueError("FUTURE_CANDIDATE_AVAILABILITY_INVALID")
    target, horizon = snapshot.get("target"), snapshot.get("horizon")
    if target not in TARGETS or horizon not in HORIZONS:
        raise ValueError("FUTURE_FEATURE_TARGET_INVALID")
    now, available = instant(snapshot["now"]), instant(candidate["available_at"])
    minute = number(snapshot["now_minute"], 0, 150)
    origin = number(snapshot["target_origin_minute"], 0, 150)
    maturity = number(snapshot["target_maturity_minute"], origin, 150)
    total = number(snapshot["budget_total"], 0, 100)
    budget = number(snapshot["budget_remaining"], 0, total)
    state = snapshot["observed_state"]
    score = state["score"]
    difference = number(score["home"], 0, 100) - number(score["away"], 0, 100)
    freshness = candidate.get("freshness_seconds")
    result = {"intercept": 1.0, "minute_fraction": minute / 90,
              "remaining_fraction": max(0.0, maturity - minute) / 90,
              "elapsed_fraction": max(0.0, minute - origin) / 90,
              "score_difference": difference / 100,
              "budget_fraction": budget / total if total else 0.0,
              "cost": number(candidate["cost"], 0, 100),
              "computation_cost": number(candidate["computation_cost"], 0, 100),
              "freshness_fraction": number(freshness, 0, 86400) / 3600 if freshness is not None else 0.0,
              "freshness_missing": float(freshness is None), "pending": float(availability == "PENDING"),
              "delay_fraction": max(0.0, (available - now).total_seconds()) / 5400}
    result.update({"acquired_" + key: float(key in visible) for key in CATEGORIES})
    result.update({"visible_" + key: visible.get(key, 0.0) for key in ("possession", "shots", "fatigue")})
    cards = visible.get("red_cards", {"home": 0, "away": 0})
    result["visible_card_difference"] = float(cards["home"] - cards["away"])
    result.update({"target_" + key: float(key == target) for key in TARGETS})
    result.update({"horizon_" + key: float(key == horizon) for key in HORIZONS})
    return {key: result[key] for key in FEATURES}


def _rows(rows, split):
    if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= 300000:
        raise ValueError("FUTURE_BOUNDED_TRAINING_ROWS_REQUIRED")
    identities = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS or row["schema_version"] != "dragonhydra.future-training-row/1" or row["split"] != split:
            raise ValueError("FUTURE_TRAINING_ROW_SCHEMA_INVALID")
        if row["category"] not in CATEGORIES or row["target"] not in TARGETS or row["horizon"] not in HORIZONS:
            raise ValueError("FUTURE_TRAINING_ROW_TARGET_INVALID")
        if not isinstance(row["features"], dict) or set(row["features"]) != set(FEATURES):
            raise ValueError("FUTURE_TRAINING_FEATURE_WHITELIST_VIOLATION")
        for value in row["features"].values():
            number(value, -1000, 1000)
        if row["features"]["intercept"] != 1:
            raise ValueError("FUTURE_TRAINING_INTERCEPT_INVALID")
        before, after, label = (number(row[key], -2 if key == "label" else 0, 2) for key in ("before_brier", "after_brier", "label"))
        if abs(label - (before - after)) > 1e-12:
            raise ValueError("FUTURE_LABEL_LOSS_MISMATCH")
        decision, acquisition, evaluation, occurred, available = (instant(row[key]) for key in
            ("decision_at", "acquisition_at", "evaluation_cutoff", "outcome_occurred_at", "label_available_at"))
        if not decision <= acquisition == evaluation < occurred <= available:
            raise ValueError("FUTURE_LABEL_NOT_PROSPECTIVE")
        pending = float(acquisition > decision)
        if row["features"]["pending"] != pending or abs(row["features"]["delay_fraction"] - (acquisition-decision).total_seconds()/5400) > 1e-12:
            raise ValueError("FUTURE_LABEL_AVAILABILITY_FEATURE_MISMATCH")
        for key in ("episode_id", "group_id", "decision_id", "outcome_id"):
            if not isinstance(row[key], str) or not row[key].startswith("virtual-") or len(row[key]) > 200:
                raise ValueError("FUTURE_ROW_VIRTUAL_ID_REQUIRED")
        identity = row["decision_id"], row["category"]
        if identity in identities:
            raise ValueError("FUTURE_DUPLICATE_TRAINING_DECISION")
        identities.add(identity)
        number(row["cost"], 0, 100)
        number(row["computation_cost"], 0, 100)
    return rows


def _solve(matrix, vector):
    """Partial-pivot Gauss-Jordan for the small positive ridge system."""
    size = len(vector)
    augmented = [list(row) + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("FUTURE_RIDGE_SINGULAR_SYSTEM")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            multiplier = augmented[row][column]
            augmented[row] = [a - multiplier * b for a, b in zip(augmented[row], augmented[column])]
    return [row[-1] for row in augmented]


def _seal(payload):
    payload = deepcopy(payload)
    digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
    return {**payload, "content_sha256": digest, "model_id": "ridge-future-relevance/1-" + digest[:24]}


def validate_model(model):
    if not isinstance(model, dict) or model.get("schema_version") != "dragonhydra.future-ridge/1" or model.get("frozen") is not True:
        raise ValueError("FUTURE_FROZEN_MODEL_REQUIRED")
    payload = {key: value for key, value in model.items() if key not in ("content_sha256", "model_id")}
    expected = _seal(payload)
    if model.get("content_sha256") != expected["content_sha256"] or model.get("model_id") != expected["model_id"]:
        raise ValueError("FUTURE_MODEL_CONTENT_HASH_MISMATCH")
    if model.get("feature_names") != list(FEATURES):
        raise ValueError("FUTURE_MODEL_FEATURE_WHITELIST_MISMATCH")
    return model


def _predict_features(features, category, model):
    centers = model["centers_by_category"][category]
    scales = model["scales_by_category"][category]
    coefficients = model["coefficients_by_category"][category]
    return math.fsum(coefficient * (features[key] - center) / scale
                     for key, center, scale, coefficient in zip(FEATURES, centers, scales, coefficients))


def fit_ridge(train_rows, regularization=1.0, threshold=0.0):
    rows = _rows(train_rows, "TRAIN")
    regularization = number(regularization, 1e-6, 1000)
    threshold = number(threshold, 0, 2)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
    if set(grouped) != set(CATEGORIES):
        raise ValueError("FUTURE_TRAINING_CATEGORY_MISSING")
    centers, scales, coefficients, uncertainty = {}, {}, {}, {}
    for category in CATEGORIES:
        subset = grouped[category]
        center = [0.0 if key == "intercept" else math.fsum(row["features"][key] for row in subset) / len(subset) for key in FEATURES]
        scale = [1.0 if key == "intercept" else max(1e-6, math.sqrt(math.fsum((row["features"][key] - mean)**2 for row in subset) / len(subset)))
                 for key, mean in zip(FEATURES, center)]
        xs = [[(row["features"][key] - mean) / sd for key, mean, sd in zip(FEATURES, center, scale)] for row in subset]
        size = len(FEATURES)
        gram = [[0.0] * size for _ in range(size)]
        response = [0.0] * size
        for x, row in zip(xs, subset):
            for i in range(size):
                response[i] += x[i] * row["label"]
                for j in range(i, size):
                    gram[i][j] += x[i] * x[j]
        for i in range(size):
            for j in range(i):
                gram[i][j] = gram[j][i]
            if i:
                gram[i][i] += regularization
        beta = _solve(gram, response)
        residuals = [row["label"] - math.fsum(a*b for a, b in zip(x, beta)) for row, x in zip(subset, xs)]
        rmse = math.sqrt(math.fsum(value * value for value in residuals) / len(residuals))
        residual_groups = defaultdict(list)
        for row, residual in zip(subset, residuals):
            residual_groups[row["group_id"]].append(residual)
        grouped_means = [math.fsum(values) / len(values) for values in residual_groups.values()]
        grouped_center = math.fsum(grouped_means) / len(grouped_means)
        grouped_se = math.sqrt(math.fsum((value-grouped_center)**2 for value in grouped_means)
                               / (len(grouped_means)-1) / len(grouped_means)) if len(grouped_means)>1 else None
        centers[category], scales[category], coefficients[category] = center, scale, beta
        uncertainty[category] = {"training_count": len(subset), "residual_rmse": rmse,
                                 "training_root_group_count": len(residual_groups),
                                 "grouped_residual_mean_standard_error": grouped_se,
                                 "pending_training_count": sum(row["features"]["pending"] == 1 for row in subset),
                                 "pending_training_label_mean": (math.fsum(row["label"] for row in subset if row["features"]["pending"] == 1)
                                     / sum(row["features"]["pending"] == 1 for row in subset)) if any(row["features"]["pending"] == 1 for row in subset) else None,
                                 "scope": "EMPIRICAL_TRAIN_RESIDUAL_NOT_CALIBRATION_OR_PREDICTION_INTERVAL"}
    return _seal({"schema_version": "dragonhydra.future-ridge/1", "frozen": True,
                  "feature_names": list(FEATURES), "regularization": regularization, "threshold": threshold,
                  "coefficients_by_category": coefficients, "centers_by_category": centers,
                  "scales_by_category": scales, "uncertainty_by_category": uncertainty,
                  "training_row_count": len(rows), "training_group_ids": sorted({row["group_id"] for row in rows}),
                  "training_rows_sha256": hashlib.sha256(canonical(rows).encode()).hexdigest(),
                  "training_label_cutoff": max((row["label_available_at"] for row in rows), key=instant),
                  "available_at": max((row["label_available_at"] for row in rows), key=instant),
                  "selection": {"method": "EXPLICIT_PARAMETERS_NOT_YET_VALIDATED"},
                  "target": "R(X,Y,T)=EXPECTED_PROPER_BRIER_LOSS_REDUCTION", "calibration_state": "UNVERIFIED"})


def estimate(snapshot, category, model):
    validate_model(model)
    if instant(model["available_at"]) > instant(snapshot["now"]):
        raise ValueError("FUTURE_MODEL_NOT_AVAILABLE_AT_DECISION")
    features = feature_vector(snapshot, category)
    value = _predict_features(features, category, model)
    if not math.isfinite(value):
        raise ValueError("FUTURE_NONFINITE_LEARNED_VALUE")
    return {"estimated_value": value, "residual_uncertainty": deepcopy(model["uncertainty_by_category"][category]),
            "model_id": model["model_id"], "feature_sha256": hashlib.sha256(canonical(features).encode()).hexdigest()}


def select_model(train_rows, validation_rows, regularizations=(.01, .1, 1.0, 10.0), thresholds=(0.0, .005, .02, .05), cost_weight=1.0):
    _rows(train_rows, "TRAIN")
    validation = _rows(validation_rows, "VALIDATION")
    cost_weight = number(cost_weight, 0, 100)
    if {row["group_id"] for row in train_rows} & {row["group_id"] for row in validation}:
        raise ValueError("FUTURE_TRAIN_VALIDATION_GROUP_LEAKAGE")
    if max(instant(row["label_available_at"]) for row in train_rows) >= min(instant(row["decision_at"]) for row in validation):
        raise ValueError("FUTURE_TRAIN_VALIDATION_TEMPORAL_LEAKAGE")
    if not 1 <= len(regularizations) <= 8 or not 1 <= len(thresholds) <= 12:
        raise ValueError("FUTURE_SELECTION_GRID_BOUNDS")
    trials, best = [], None
    for regularization in regularizations:
        fitted = fit_ridge(train_rows, regularization)
        for threshold in thresholds:
            threshold = number(threshold, 0, 2)
            groups = defaultdict(list)
            mse = []
            for row in validation:
                prediction = _predict_features(row["features"], row["category"], fitted)
                net = prediction - cost_weight * (row["cost"] + row["computation_cost"])
                groups[row["decision_id"]].append((net, row))
                mse.append((prediction - row["label"])**2)
            rewards = []
            for alternatives in groups.values():
                net, selected = max(alternatives, key=lambda item: (item[0], item[1]["category"]))
                rewards.append(selected["label"] - cost_weight * (selected["cost"] + selected["computation_cost"]) if net > threshold else 0.0)
            utility = math.fsum(rewards) / len(rewards)
            error = math.fsum(mse) / len(mse)
            trial = {"regularization": float(regularization), "threshold": threshold,
                     "validation_mean_net_utility": utility, "validation_label_mse": error,
                     "validation_decision_count": len(groups)}
            trials.append(trial)
            ranking = utility, -error, float(regularization), threshold
            if best is None or ranking > best[0]:
                best = ranking, fitted, trial
    payload = {key: value for key, value in best[1].items() if key not in ("content_sha256", "model_id")}
    payload["threshold"] = best[2]["threshold"]
    payload["frozen_at"] = max((row["label_available_at"] for row in validation), key=instant)
    payload["available_at"] = max((row["label_available_at"] for row in (*train_rows, *validation)), key=instant)
    payload["selection"] = {"method": "VALIDATION_ONLY_NET_UTILITY_THEN_LABEL_MSE",
                            "selected": best[2], "trials": trials,
                            "validation_row_count": len(validation),
                            "validation_group_ids": sorted({row["group_id"] for row in validation}),
                            "validation_rows_sha256": hashlib.sha256(canonical(validation).encode()).hexdigest(),
                            "final_test_used": False, "cost_weight": cost_weight}
    return _seal(payload)
