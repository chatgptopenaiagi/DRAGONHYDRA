"""Pure, synthetic-only residual-time probability experiments.

Rates are configured examples, never fitted estimates. No acquisition, storage,
clock lookup, random sampling or legacy forecast workflow is invoked here.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import math
import re

from ..cognition.models import poisson_distribution

SCHEMA = "dragonhydra.realtime-probability/1"
MODEL = "synthetic-independent-goal-poisson/1"
HORIZONS = ("1", "5", "10", "30", "FULL_TIME")
SIDES = ("home", "away")
OUTCOMES = ("home", "draw", "away")
DEFAULTS = {
    "home_rate": 1.6, "away_rate": 1.2, "rate_basis_minutes": 90.0,
    "own_red_card_multiplier": 0.75, "opponent_red_card_multiplier": 1.10,
    "tail_tolerance": 1e-12, "max_goals": 64,
    "comparison_low_scale": 0.8, "comparison_high_scale": 1.2,
}
LIMITATIONS = [
    "All inputs and rates are synthetic; calibration and predictive accuracy are unverified.",
    "Independent constant goal hazards share configured assumptions; game-state feedback, dependence and rate uncertainty are omitted.",
    "Variant spread measures configured sensitivity, not independent evidence or a confidence interval.",
    "Playing-minute horizons are not wall-clock delivery times; future unannounced stoppage is excluded.",
]


def _number(value, name, low, high, integer=False):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError("REALTIME_INVALID_" + name.upper())
    if integer and type(value) is not int:
        raise ValueError("REALTIME_INVALID_" + name.upper())
    return int(value) if integer else float(value)


def _configuration(config):
    if config is not None and (not isinstance(config, dict) or set(config) - DEFAULTS.keys()):
        raise ValueError("REALTIME_INVALID_CONFIGURATION")
    result = {**DEFAULTS, **(config or {})}
    bounds = {"home_rate": (0, 5), "away_rate": (0, 5),
              "rate_basis_minutes": (45, 120), "own_red_card_multiplier": (0, 1),
              "opponent_red_card_multiplier": (1, 1.5), "tail_tolerance": (1e-14, 1e-6),
              "max_goals": (1, 100), "comparison_low_scale": (0.1, 1),
              "comparison_high_scale": (1, 2)}
    for key, (low, high) in bounds.items():
        result[key] = _number(result[key], key, low, high, key == "max_goals")
    return result


def _state(raw):
    if not isinstance(raw, dict) or raw.get("synthetic") is not True:
        raise ValueError("REALTIME_SYNTHETIC_STATE_REQUIRED")
    if raw.get("source_mode") not in ("REPLAY", "DEMONSTRATION"):
        raise ValueError("REALTIME_VIRTUAL_MODE_REQUIRED")
    if not isinstance(raw.get("match_id"), str) or not re.fullmatch(r"virtual-[A-Za-z0-9_.:-]{1,100}", raw["match_id"]):
        raise ValueError("REALTIME_VIRTUAL_MATCH_REQUIRED")
    state = {key: raw.get(key) for key in ("match_id", "source_mode", "status")}
    state["synthetic"] = True
    if state["status"] not in ("SCHEDULED", "IN_PLAY", "HALF_TIME", "SUSPENDED", "FINISHED"):
        raise ValueError("REALTIME_INVALID_STATUS")
    for key, low, high, integer in (("revision", 0, 1000000, True), ("minute", 0, 150, False),
                                   ("period", 0, 5, True), ("duration_minutes", 1, 150, False),
                                   ("period_end_minute", 1, 150, False)):
        state[key] = _number(raw.get(key), key, low, high, integer)
    if type(raw.get("end_time_known")) is not bool:
        raise ValueError("REALTIME_INVALID_END_TIME_KNOWN")
    state["end_time_known"] = raw["end_time_known"]
    for key, limit in (("score", 100), ("red_cards", 4)):
        value = raw.get(key)
        if not isinstance(value, dict) or set(value) != set(SIDES):
            raise ValueError("REALTIME_INVALID_" + key.upper())
        state[key] = {side: _number(value[side], key, 0, limit, True) for side in SIDES}
    return state


def _exposures(state):
    """Return playing minutes, or a fail-closed reason; finality is authoritative."""
    status, period = state["status"], state["period"]
    if status == "FINISHED":
        return {key: 0.0 for key in HORIZONS}, "OBSERVED_FINAL"
    if status == "SUSPENDED":
        return None, "SUSPENDED_RESUMPTION_UNKNOWN"
    if period not in (1, 2) or state["duration_minutes"] != 90:
        return None, "UNSUPPORTED_REGULATION_DURATION_OR_PERIOD"
    if not state["end_time_known"]:
        return None, "END_TIME_UNKNOWN"
    minute, end = state["minute"], state["period_end_minute"]
    if (period == 1 and end < 45) or (period == 2 and end < 90):
        return None, "INCONSISTENT_PERIOD_CLOCK"
    if status == "HALF_TIME":
        if period != 1 or minute < 45:
            return None, "INCONSISTENT_HALF_TIME_CLOCK"
        available, full, reason = 45.0, 45.0, "CONDITIONAL_ON_SECOND_HALF_RESUMPTION"
    elif status == "SCHEDULED":
        if period != 1 or minute != 0 or state["score"] != {"home": 0, "away": 0}:
            return None, "INCONSISTENT_SCHEDULED_STATE"
        available, full, reason = end, end + 45.0, "CONDITIONAL_ON_KICKOFF"
    else:
        if minute >= end:
            return None, "PERIOD_BOUNDARY_REQUIRES_AUTHORITATIVE_UPDATE"
        if period == 2 and minute < 45:
            return None, "INCONSISTENT_PERIOD_CLOCK"
        available = end - minute
        full = available + (45.0 if period == 1 else 0.0)
        reason = "KNOWN_PERIOD_END_REGULATION_ONLY"
    return {key: full if key == "FULL_TIME" else min(float(key), available) for key in HORIZONS}, reason


def _rates(state, config, scale):
    own, other = config["own_red_card_multiplier"], config["opponent_red_card_multiplier"]
    return tuple(config[side + "_rate"] * scale * own ** state["red_cards"][side]
                 * other ** state["red_cards"][SIDES[1 - i]] / config["rate_basis_minutes"]
                 for i, side in enumerate(SIDES))


@lru_cache(maxsize=1024)
def _poisson(mean, limit, tolerance):
    """Cache immutable adaptive supports; callers never receive cached mutables."""
    probabilities, tail = poisson_distribution(mean, limit)
    cumulative = 0.0
    for index, probability in enumerate(probabilities):
        cumulative = math.fsum((cumulative, probability))
        if 1.0 - cumulative <= tolerance:
            probabilities = probabilities[:index + 1]
            break
    return tuple(probabilities), max(0.0, 1.0 - math.fsum(probabilities))


@lru_cache(maxsize=1024)
def _joint(home_mean, away_mean, limit, tolerance):
    home, home_tail = _poisson(home_mean, limit, tolerance / 2)
    away, away_tail = _poisson(away_mean, limit, tolerance / 2)
    coverage = math.fsum(home) * math.fsum(away)
    omitted = max(0.0, 1.0 - coverage)
    if omitted > tolerance or coverage <= 0:
        return None, omitted
    cells = tuple((h, a, hp * ap / coverage) for h, hp in enumerate(home) for a, ap in enumerate(away))
    return cells, omitted


def _entropy(probabilities):
    return -math.fsum(p * math.log(p) for p in probabilities if p > 0)


@lru_cache(maxsize=2048)
def _outcomes(home_mean, away_mean, score_difference, limit, tolerance):
    cells, _ = _joint(home_mean, away_mean, limit, tolerance)
    groups = ([], [], [])
    for home, away, probability in cells:
        difference = score_difference + home - away
        groups[0 if difference > 0 else 2 if difference < 0 else 1].append(probability)
    values = tuple(math.fsum(group) for group in groups)
    total = math.fsum(values)
    return tuple(value / total for value in values)


def _unavailable(reason, effective_minutes=None, tail=None):
    return {"availability": False, "reason": reason, "effective_minutes": effective_minutes,
            "next_goal_occurrence": None, "next_goal_side": None, "remaining_goals": None,
            "score_distribution": None, "tail_mass": tail,
            "uncertainty": {"outcome_entropy": None, "normalized_outcome_entropy": None,
                            "next_goal_entropy": None, "model_comparison": None,
                            "limitations": list(LIMITATIONS)}}


def _horizon(state, minutes, reason, rates, config, dense):
    home_mean, away_mean = (rate * minutes for rate in rates)
    total_mean = home_mean + away_mean
    if total_mean > 20:
        return _unavailable("RATE_OUTSIDE_IMPLEMENTED_RANGE", minutes)
    cells, omitted = _joint(home_mean, away_mean, config["max_goals"], config["tail_tolerance"])
    total, total_tail = _poisson(total_mean, config["max_goals"], config["tail_tolerance"])
    if cells is None or total_tail > config["tail_tolerance"]:
        return _unavailable("TRUNCATION_BOUND_EXCEEDED", minutes, max(omitted, total_tail))
    occurrence = -math.expm1(-total_mean)
    no_goal = math.exp(-total_mean)
    shares = (home_mean / total_mean, away_mean / total_mean) if total_mean else (None, None)
    side = {"home": occurrence * shares[0] if total_mean else 0.0,
            "away": occurrence * shares[1] if total_mean else 0.0, "no_goal": no_goal,
            "conditional_home": shares[0], "conditional_away": shares[1]}
    result = dict(zip(OUTCOMES, _outcomes(home_mean, away_mean, state["score"]["home"] - state["score"]["away"],
                                         config["max_goals"], config["tail_tolerance"])))
    return {"availability": True, "reason": reason, "effective_minutes": minutes,
            "next_goal_occurrence": occurrence, "next_goal_side": side,
            "remaining_goals": {"mean": total_mean, "home_mean": home_mean, "away_mean": away_mean,
                                "distribution": list(total),
                                "tail_bucket": {"from_goals": len(total), "probability": total_tail}},
            "score_distribution": [{"home": state["score"]["home"] + h,
                                    "away": state["score"]["away"] + a, "probability": p}
                                   for h, a, p in cells] if dense else None,
            "tail_mass": omitted, "result": result,
            "uncertainty": {"outcome_entropy": _entropy(result.values()),
                            "normalized_outcome_entropy": _entropy(result.values()) / math.log(3),
                            "next_goal_entropy": _entropy((side["home"], side["away"], no_goal)),
                            "model_comparison": None, "limitations": list(LIMITATIONS)}}


def _calculate(state, config, scale=1.0, dense=False):
    exposures, reason = _exposures(state)
    rates = _rates(state, config, scale)
    horizons = {key: _horizon(state, exposures[key], reason, rates, config, dense)
                if exposures is not None else _unavailable(reason) for key in HORIZONS}
    return horizons


def _compact(horizons):
    return {"full_time_result": horizons["FULL_TIME"].get("result"),
            "horizons": {key: {field: value[field] for field in
                                ("availability", "effective_minutes", "next_goal_occurrence", "next_goal_side")}
                         | {"entropy": value["uncertainty"]["outcome_entropy"]}
                         for key, value in horizons.items()}}


def _comparison(state, config, baseline=None):
    models = []
    for label, scale in (("baseline", 1.0), ("low_tempo", config["comparison_low_scale"]),
                         ("high_tempo", config["comparison_high_scale"])):
        horizons = baseline if label == "baseline" and baseline is not None else _calculate(state, config, scale)
        models.append({"model_id": MODEL + "/" + label, "rate_factors": {"home": scale, "away": scale},
                       **_compact(horizons)})
    ft = [model["full_time_result"] for model in models]
    spread = {"full_time_result": {key: max(row[key] for row in ft) - min(row[key] for row in ft)
                                    for key in OUTCOMES} if all(row is not None for row in ft) else None,
              "horizon_occurrence": {}}
    for key in HORIZONS:
        values = [model["horizons"][key]["next_goal_occurrence"] for model in models]
        spread["horizon_occurrence"][key] = ({"minimum": min(values), "maximum": max(values),
                                               "range": max(values) - min(values)}
                                              if all(v is not None for v in values) else None)
    return {"schema_version": SCHEMA, "model_status": "EXPERIMENTAL", "calibration_state": "UNVERIFIED",
            "models": models, "spread": spread, "limitations": list(LIMITATIONS)}


def predict(state, config=None):
    """Predict synthetic future increments without reading any external state."""
    validated, configured = _state(state), _configuration(config)
    horizons = _calculate(validated, configured, dense=True)
    comparison = _comparison(validated, configured, horizons)
    for key, horizon in horizons.items():
        horizon["uncertainty"]["model_comparison"] = comparison["spread"]["horizon_occurrence"][key]
    assumptions = list(LIMITATIONS) + [
        "Home and away future goals are independent Poisson increments; current goals shift the score, not the remaining rate.",
        "Full-time result is conditioned on the bounded score grid; tail_mass exposes omitted probability before normalization.",
        "remaining_goals.distribution is unconditioned; its explicit tail_bucket completes total probability.",
        "First-half FULL_TIME includes the known remainder plus 45 second-half playing minutes; fixed horizons stop at the current period boundary.",
        "HALF_TIME predictions are conditional on resumption; FINISHED scores are observed, never inferred from the clock.",
    ]
    return {"schema_version": SCHEMA, "model_id": MODEL, "model_status": "EXPERIMENTAL",
            "calibration_state": "UNVERIFIED", "synthetic": True, "match_id": validated["match_id"],
            "source_mode": validated["source_mode"], "state_revision": validated["revision"],
            "full_time_result": horizons["FULL_TIME"].get("result"), "horizons": horizons,
            "uncertainty": {"entropy": horizons["FULL_TIME"]["uncertainty"]["outcome_entropy"],
                            "model_comparison": comparison["spread"], "limitations": list(LIMITATIONS)},
            "assumptions": assumptions}


def compare_models(state, config=None):
    """Independently recompute configured sensitivity variants, not trained models."""
    return _comparison(_state(state), _configuration(config))


def bounded_counterfactual(state, changes, config=None):
    """Apply bounded absolute synthetic changes, keeping match and time policy fixed."""
    validated, configured = _state(state), _configuration(config)
    if not isinstance(changes, dict) or not changes or set(changes) - {"score", "red_cards", "minute"}:
        raise ValueError("REALTIME_INVALID_COUNTERFACTUAL")
    changed = deepcopy(validated)
    for key, value in changes.items():
        if key == "minute":
            minute = _number(value, "counterfactual_minute", validated["minute"], min(150, validated["minute"] + 10))
            if minute > validated["period_end_minute"]:
                raise ValueError("REALTIME_COUNTERFACTUAL_PERIOD_BOUNDARY")
            changed[key] = minute
        else:
            if not isinstance(value, dict) or not value or set(value) - set(SIDES):
                raise ValueError("REALTIME_INVALID_COUNTERFACTUAL_SIDE")
            for side, number in value.items():
                bounded = _number(number, "counterfactual_" + key, 0, 100 if key == "score" else 4, True)
                if abs(bounded - validated[key][side]) > 1:
                    raise ValueError("REALTIME_COUNTERFACTUAL_CHANGE_TOO_LARGE")
                changed[key][side] = bounded
    if validated["status"] == "FINISHED":
        raise ValueError("REALTIME_COUNTERFACTUAL_FINAL_STATE_IMMUTABLE")
    baseline = _compact(_calculate(validated, configured))
    alternative = _compact(_calculate(changed, configured))
    before, after = baseline["full_time_result"], alternative["full_time_result"]
    return {"schema_version": SCHEMA, "model_status": "EXPERIMENTAL", "calibration_state": "UNVERIFIED",
            "changes": deepcopy(changes), "changed_state": changed, "baseline": baseline,
            "counterfactual": alternative,
            "full_time_result_delta": {key: after[key] - before[key] for key in OUTCOMES}
                                      if before is not None and after is not None else None,
            "horizon_occurrence_delta": {key: alternative["horizons"][key]["next_goal_occurrence"]
                                            - baseline["horizons"][key]["next_goal_occurrence"]
                                          if baseline["horizons"][key]["availability"] and alternative["horizons"][key]["availability"]
                                          else None for key in HORIZONS},
            "limitations": list(LIMITATIONS) + ["Counterfactuals change configured scenarios; they do not estimate causal effects."]}
