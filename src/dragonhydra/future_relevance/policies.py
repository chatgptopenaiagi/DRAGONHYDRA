"""Cost-aware one-step policies; their only input is the public snapshot."""
from __future__ import annotations

import hashlib
import math
import random

from .forecast import CATEGORIES, canonical, instant, number, visible_acquired
from .learning import estimate, validate_model

POLICIES = ("acquire_all", "acquire_none", "random", "handcrafted", "learned")


def choose_action(snapshot, policy, model=None, seed=42, cost_weight=1.0):
    visible_acquired(snapshot)
    if policy not in POLICIES or type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError("FUTURE_POLICY_INVALID")
    cost_weight = number(cost_weight, 0, 100)
    budget = number(snapshot["budget_remaining"], 0, 100)
    remaining = max(0.0, number(snapshot["target_maturity_minute"], 0, 150) - number(snapshot["now_minute"], 0, 150))
    if policy == "learned":
        validate_model(model)
        if instant(model["available_at"]) > instant(snapshot["now"]):
            raise ValueError("FUTURE_MODEL_NOT_AVAILABLE_AT_DECISION")
    if policy == "acquire_none":
        return {"action": "IGNORE", "category": None, "estimated_value": 0.0, "estimated_cost": 0.0,
                "reason": "ACQUIRE_NONE_POLICY", "scores": []}
    if remaining <= 0:
        return {"action": "NO_ADDITIONAL_INFORMATION", "category": None, "estimated_value": 0.0,
                "estimated_cost": 0.0, "reason": "TARGET_WINDOW_CLOSED", "scores": []}
    if snapshot["target"] in ("GOAL_OCCURRENCE", "NEXT_GOAL_SIDE") and snapshot["observed_goal_count_since_origin"]:
        return {"action": "NO_ADDITIONAL_INFORMATION", "category": None, "estimated_value": 0.0,
                "estimated_cost": 0.0, "reason": "TARGET_DETERMINED_BY_ACCEPTED_GOAL", "scores": []}
    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 4 or len({row.get("category") for row in candidates}) != len(candidates):
        raise ValueError("FUTURE_CANDIDATES_INVALID")
    scores = []
    for candidate in candidates:
        category, availability = candidate.get("category"), candidate.get("availability")
        if category not in CATEGORIES or availability not in ("AVAILABLE", "PENDING", "ACQUIRED", "UNOBSERVABLE"):
            raise ValueError("FUTURE_CANDIDATES_INVALID")
        acquisition = number(candidate["cost"], 0, 100)
        computation = number(candidate["computation_cost"], 0, 100)
        delay = max(0.0, (instant(candidate["available_at"]) - instant(snapshot["now"])).total_seconds() / 60)
        eligible = availability in ("AVAILABLE", "PENDING") and acquisition <= budget + 1e-12 and delay < remaining
        uncertainty = None
        if policy == "learned" and eligible:
            prediction = estimate(snapshot, category, model)
            value, uncertainty = prediction["estimated_value"], prediction["residual_uncertainty"]
        elif policy == "handcrafted":
            base = {"possession": .035, "red_cards": .05, "shots": .02, "fatigue": .025}[category]
            target_scale = 1.15 if snapshot["target"] in ("FULL_TIME_RESULT", "REMAINING_GOALS") else 1.0
            # Explicit public heuristic, not a fitted estimate or hidden truth.
            value = base * min(1.0, remaining / 10) * target_scale
            if category == "shots" and "possession" in snapshot["acquired"]:
                value *= .2
        else:
            value = 0.0
        scores.append({"category": category, "availability": availability, "eligible": eligible,
                       "estimated_value": value, "estimated_cost": acquisition,
                       "estimated_computation_cost": computation,
                       "net_value": value - cost_weight * (acquisition + computation),
                       "delay_minutes": delay, "uncertainty": uncertainty})
    eligible = [row for row in scores if row["eligible"]]
    if not eligible:
        return {"action": "NO_ADDITIONAL_INFORMATION", "category": None, "estimated_value": 0.0,
                "estimated_cost": 0.0, "reason": "NO_ELIGIBLE_AFFORDABLE_OBSERVATION", "scores": scores}
    if policy == "acquire_all":
        selected = min(eligible, key=lambda row: (row["availability"] != "AVAILABLE", row["estimated_cost"], row["category"]))
        reason = "ACQUIRE_ALL_WITHIN_SHARED_BUDGET"
    elif policy == "random":
        # Metadata IDs, family and hidden state never determine the draw.
        public_draw_context = {"seed": seed, "now": snapshot["now"], "target": snapshot["target"],
                               "horizon": snapshot["horizon"], "acquired_categories": sorted(snapshot["acquired"]),
                               "categories": sorted(row["category"] for row in eligible)}
        draw_seed = int(hashlib.sha256(canonical(public_draw_context).encode()).hexdigest(), 16)
        choices = sorted(eligible, key=lambda row: row["category"]) + [None]
        selected = random.Random(draw_seed).choice(choices)
        if selected is None:
            return {"action": "IGNORE", "category": None, "estimated_value": 0.0, "estimated_cost": 0.0,
                    "reason": "RANDOM_NO_ACQUISITION_DRAW", "scores": scores}
        reason = "RANDOM_PUBLIC_CONTEXT_DRAW"
    else:
        selected = max(eligible, key=lambda row: (row["net_value"], row["category"]))
        threshold = model["threshold"] if policy == "learned" else 0.0
        if selected["net_value"] <= threshold:
            return {"action": "IGNORE", "category": None, "estimated_value": selected["estimated_value"],
                    "estimated_cost": selected["estimated_cost"], "reason": "NO_POSITIVE_COST_ADJUSTED_VALUE",
                    "scores": scores}
        reason = "TRAINED_CONTEXTUAL_VALUE_EXCEEDS_COST_AND_VALIDATED_THRESHOLD" if policy == "learned" else "HANDCRAFTED_PUBLIC_CONTEXT_RULE"
    return {"action": "ACQUIRE_NOW" if selected["availability"] == "AVAILABLE" else "DEFER",
            "category": selected["category"], "estimated_value": selected["estimated_value"],
            "estimated_cost": selected["estimated_cost"], "reason": reason, "scores": scores}
