"""One-target fictional forecast adapter; acquisition never changes an outcome."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math

from ..realtime import models
from ..cognition.models import poisson_distribution

TARGETS = ("GOAL_OCCURRENCE", "FULL_TIME_RESULT", "NEXT_GOAL_SIDE", "REMAINING_GOALS")
CATEGORIES = ("possession", "red_cards", "shots", "fatigue")
MODEL_ID = "synthetic-acquired-evidence-poisson/1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def instant(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("FUTURE_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("FUTURE_TIMESTAMP_INVALID") from None
    if parsed.utcoffset() is None:
        raise ValueError("FUTURE_TIMESTAMP_ZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError("FUTURE_NUMBER_INVALID")
    return float(value)


def visible_acquired(snapshot):
    """Only timestamp-eligible observed values cross the mathematical boundary."""
    if not isinstance(snapshot, dict) or snapshot.get("synthetic") is not True or snapshot.get("source_mode") != "DEMONSTRATION":
        raise ValueError("FUTURE_VIRTUAL_SNAPSHOT_REQUIRED")
    now = instant(snapshot.get("now"))
    acquired = snapshot.get("acquired")
    if not isinstance(acquired, dict) or set(acquired) - set(CATEGORIES):
        raise ValueError("FUTURE_ACQUIRED_SCHEMA_INVALID")
    values = {}
    for category, receipt in acquired.items():
        if not isinstance(receipt, dict) or not {"value", "observed_at", "available_at", "received_at"} <= receipt.keys():
            raise ValueError("FUTURE_ACQUISITION_RECEIPT_INVALID")
        observed, available, received = (instant(receipt[key]) for key in ("observed_at", "available_at", "received_at"))
        if not observed <= available <= received <= now:
            raise ValueError("FUTURE_UNAVAILABLE_OBSERVATION_REJECTED")
        value = receipt["value"]
        if category == "red_cards":
            if not isinstance(value, dict) or set(value) != {"home", "away"} or any(type(v) is not int or v not in (0, 1) for v in value.values()):
                raise ValueError("FUTURE_CARD_OBSERVATION_INVALID")
            values[category] = dict(value)
        else:
            values[category] = number(value, 0, 1)
    return values


def _empty(snapshot, reason, config_id=None, minutes=None):
    return {"schema_version": "dragonhydra.future-forecast/1", "model_id": MODEL_ID,
            "configuration_id": config_id, "target": snapshot.get("target"), "horizon": snapshot.get("horizon"),
            "cutoff": snapshot.get("now"), "probabilities": {}, "effective_minutes": minutes,
            "availability": False, "reason": reason, "uncertainty": {"calibration_state": "UNVERIFIED"},
            "computation_units": 1, "synthetic": True}


def forecast(snapshot):
    """Reuse the existing Poisson kernel for exactly one requested horizon."""
    values = visible_acquired(snapshot)
    target, horizon = snapshot.get("target"), snapshot.get("horizon")
    if target not in TARGETS or horizon not in models.HORIZONS or (target == "FULL_TIME_RESULT" and horizon != "FULL_TIME"):
        return _empty(snapshot, "UNSUPPORTED_TARGET_OR_HORIZON")
    state = models._state(snapshot.get("observed_state"))
    if state["match_id"] != snapshot.get("match_id") or state["source_mode"] != snapshot["source_mode"]:
        raise ValueError("FUTURE_SNAPSHOT_IDENTITY_MISMATCH")
    now = number(snapshot.get("now_minute"), 0, 150)
    origin = number(snapshot.get("target_origin_minute"), 0, 150)
    maturity = number(snapshot.get("target_maturity_minute"), origin, 150)
    if now < origin or abs(state["minute"] - min(now, 90.0)) > 1e-8:
        raise ValueError("FUTURE_TARGET_CLOCK_MISMATCH")
    expected_cards = values.get("red_cards", {"home": 0, "away": 0})
    if state["red_cards"] != expected_cards:
        raise ValueError("FUTURE_UNACQUIRED_CARD_VALUE_REJECTED")
    observed_count = snapshot.get("observed_goal_count_since_origin")
    first_side = snapshot.get("first_observed_goal_side")
    if type(observed_count) is not int or not 0 <= observed_count <= 100 or first_side not in (None, "home", "away"):
        raise ValueError("FUTURE_OBSERVED_GOAL_STATE_INVALID")
    if bool(observed_count) != bool(first_side):
        raise ValueError("FUTURE_OBSERVED_GOAL_STATE_INVALID")
    factors = {key: (1.8 if value >= .5 else .65) for key, value in values.items() if key == "possession"}
    if "shots" in values:
        factors["shots"] = 1.3 if values["shots"] >= .5 else .8
    proxy = math.fsum(factors.values()) / len(factors) if factors else 1.0
    fatigue = (1.4 if values["fatigue"] >= .5 else .85) if "fatigue" in values else 1.0
    config_raw = {"home_rate": models.DEFAULTS["home_rate"] * proxy * fatigue,
                  "away_rate": models.DEFAULTS["away_rate"] * proxy * fatigue}
    config_id = "virtual-config-" + hashlib.sha256(canonical({"fusion": "mean_proxy_times_fatigue/1", "values": values, "rates": config_raw}).encode()).hexdigest()[:32]
    exposures, reason = models._exposures(state)
    if exposures is None:
        return _empty(snapshot, reason, config_id)
    minutes = min(max(0.0, maturity - now), exposures[horizon])
    if any(value > 5 for value in config_raw.values()):
        return _empty(snapshot, "ADAPTER_RATE_OUTSIDE_SUPPORTED_RANGE", config_id, minutes)
    config = models._configuration(config_raw)
    rates = models._rates(state, config, 1.0)
    if any(rate * config["rate_basis_minutes"] > 5 for rate in rates):
        return _empty(snapshot, "EFFECTIVE_RATE_OUTSIDE_SUPPORTED_RANGE", config_id, minutes)
    h = models._horizon(state, minutes, reason, rates, config, False)
    if not h["availability"]:
        return _empty(snapshot, h["reason"], config_id, minutes)
    if target == "GOAL_OCCURRENCE":
        occurrence = 1.0 if observed_count else h["next_goal_occurrence"]
        probabilities = {"goal": occurrence, "no_goal": 1 - occurrence}
    elif target == "FULL_TIME_RESULT":
        probabilities = h["result"]
    elif target == "NEXT_GOAL_SIDE":
        probabilities = {side: float(side == first_side) for side in ("home", "away", "no_goal")} if first_side else {
            side: h["next_goal_side"][side] for side in ("home", "away", "no_goal")}
    else:
        probabilities = {str(index): 0.0 for index in range(13)} | {"13PLUS": 0.0}
        if observed_count >= 13:
            probabilities["13PLUS"] = 1.0
        else:
            vector, tail = poisson_distribution(h["remaining_goals"]["mean"], 12)
            for index, probability in enumerate(vector):
                key = str(index + observed_count) if index + observed_count <= 12 else "13PLUS"
                probabilities[key] += probability
            probabilities["13PLUS"] += tail
    total = math.fsum(probabilities.values())
    if not math.isfinite(total) or abs(total - 1) > 1e-12:
        raise ValueError("FUTURE_FORECAST_NOT_NORMALIZED")
    probabilities = {key: value / total for key, value in probabilities.items()}
    return {"schema_version": "dragonhydra.future-forecast/1", "model_id": MODEL_ID,
            "configuration_id": config_id, "target": target, "horizon": horizon, "cutoff": snapshot["now"],
            "probabilities": probabilities, "effective_minutes": minutes, "availability": True, "reason": reason,
            "uncertainty": {**h["uncertainty"], "calibration_state": "UNVERIFIED",
                            "score_tail_mass": h["tail_mass"], "fusion": "ARITHMETIC_MEAN_OF_ACQUIRED_POSSESSION_AND_SHOTS_FACTORS_TIMES_FATIGUE",
                            "limitations": ["Signal mappings are configured fictional assumptions, not learned forecasting coefficients.",
                                            "Possession and shots are treated as redundant proxies; their factors are averaged when both are visible."]},
            "computation_units": 1, "synthetic": True}
