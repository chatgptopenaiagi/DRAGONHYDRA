"""Seeded fictional matches and forward-only synthetic relevance experiments."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import random

from .events import SCHEMA as EVENT_SCHEMA, validate_event, virtual_id

UNIVERSES = ("constant", "card_sensitive", "tempo_signal", "noisy_signal", "clock_sensitive")
EPOCH = datetime(2035, 1, 1, 12, tzinfo=timezone.utc)
HORIZONS = ("1", "5", "10", "30", "FULL_TIME")
ASSUMPTIONS = {
    "constant": "Constant independent fictional goal hazards; card and possession have no effect.",
    "card_sensitive": "A red card opens play: total tempo multiplies by 2.5, carded-side intensity by 0.5, opponent by 1.2.",
    "tempo_signal": "Fictional possession above 50 signals shared goal tempo 3.0; below 50 signals tempo 0.25.",
    "noisy_signal": "Hidden tempo is 3.0 or 0.25; observed fictional possession is independent noise.",
    "clock_sensitive": "Both fictional goal hazards multiply by 3 after playing minute 60.",
}


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("VIRTUAL_INVALID_" + name.upper())
    return value


def _rng(seed, label):
    digest = hashlib.sha256((str(seed) + ":" + label).encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _universe(value):
    if value not in UNIVERSES:
        raise ValueError("VIRTUAL_UNIVERSE_UNKNOWN")
    return value


def _hazards(universe, minute, card_active, card_home, possession_high, hidden_high):
    home, away = 1.6 / 90, 1.2 / 90
    if universe == "card_sensitive" and card_active:
        home *= 2.5 * (0.5 if card_home else 1.2)
        away *= 2.5 * (1.2 if card_home else 0.5)
    elif universe in ("tempo_signal", "noisy_signal"):
        signal = possession_high if universe == "tempo_signal" else hidden_high
        factor = 3.0 if signal else 0.25
        home, away = home * factor, away * factor
    elif universe == "clock_sensitive" and minute >= 60:
        home, away = home * 3, away * 3
    return home, away


def _iso(value):
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def generate_match(universe="constant", seed=42, match_id="virtual-universe-match"):
    """Return a whole fictional fixture; callers must hide unaccepted future events."""
    _universe(universe)
    _integer(seed, "seed", 0, 2**32 - 1)
    virtual_id(match_id)
    rng = _rng(seed, "match:" + universe + ":" + match_id)
    events, score = [], {"home": 0, "away": 0}
    card_home = rng.choice((True, False))
    possession_high = hidden_high = False

    def emit(kind, minute, participant="NONE", **attributes):
        sequence = len(events) + 1
        instant = EPOCH + timedelta(minutes=minute, microseconds=sequence)
        event_id = hashlib.sha256((match_id + ":" + str(seed) + ":" + universe + ":" + str(sequence)).encode()).hexdigest()[:24]
        event = {"schema_version": EVENT_SCHEMA, "event_id": "virtual-event-" + event_id,
                 "source_id": "virtual-world-" + universe, "match_id": match_id,
                 "event_type": kind, "event_time": _iso(instant),
                 "received_at": _iso(instant + timedelta(milliseconds=10)),
                 "sequence": sequence, "revision": 1, "participant": participant,
                 "attributes": {"minute": round(minute, 8), **attributes},
                 "source_mode": "DEMONSTRATION", "quality_state": "VALIDATED"}
        events.append(validate_event(event))

    emit("KICKOFF", 0, duration_minutes=90, period_end_minute=45,
         home_team="Vector Town", away_team="Orbit Athletic")
    for minute in range(90):
        if minute == 45:
            emit("CLOCK", 45, period=1, period_end_minute=45, end_time_known=True)
            emit("HALF_TIME", 45)
            emit("RESUME", 45, period=2, period_end_minute=90)
        elif minute:
            emit("CLOCK", minute, period=1 if minute < 45 else 2,
                 period_end_minute=45 if minute < 45 else 90, end_time_known=True)
        if minute == 30:
            emit("RED_CARD", minute, "HOME" if card_home else "AWAY")
        if minute % 5 == 0:
            possession_high, hidden_high = rng.choice((True, False)), rng.choice((True, False))
            emit("POSSESSION", minute, home_percent=70 if possession_high else 30)
        rates = _hazards(universe, minute, minute >= 30, card_home, possession_high, hidden_high)
        elapsed = 0.0
        for _ in range(64):
            elapsed += rng.expovariate(sum(rates))
            if elapsed >= 1:
                break
            side = "home" if rng.random() < rates[0] / sum(rates) else "away"
            score[side] += 1
            emit("GOAL", minute + elapsed, side.upper())
        else:
            raise ValueError("VIRTUAL_GENERATION_EVENT_BOUND_EXCEEDED")
    emit("CLOCK", 90, period=2, period_end_minute=90, end_time_known=True)
    emit("FULL_TIME", 90, **score)
    return {"events": events,
            "descriptor": {"schema_version": "dragonhydra.virtual-universe/1", "synthetic": True,
                           "source_mode": "DEMONSTRATION", "universe": universe, "seed": seed,
                           "match_id": match_id, "event_count": len(events),
                           "scheduled_duration_minutes": 90, "epoch": _iso(EPOCH),
                           "assumptions": [ASSUMPTIONS[universe],
                               "Independent exponential waiting times inside each minute; parameters can change at minute boundaries.",
                               "One fictional card occurs at minute 30; possession changes every five minutes.",
                               "All teams, observations and outcomes are invented; no real calibration is claimed.",
                               "The full generated future is an evaluation fixture, not model or bridge context."],
                           "true_base_goal_rates_per_90": {"home": 1.6, "away": 1.2},
                           "status": "RESEARCH_ONLY"}}


def _episodes(universe, seed, cases):
    """Independent forecast episodes; labels are separate from pre-outcome features."""
    # Couple corresponding episodes across worlds: change the hazard rule,
    # while keeping covariates and latent draws exactly the same.
    rng = _rng(seed, "experiment:common-initial-conditions/1")
    outcome_rng = _rng(seed, "experiment:common-outcome-draws/1")
    rows = []
    for index in range(cases):
        minute = rng.choice((5.0, 25.0, 55.0, 70.0, 80.0, 87.0))
        card, card_home = rng.choice((False, True)), rng.choice((False, True))
        possession = rng.choice((False, True))
        hidden_uniform = rng.random()
        hidden = hidden_uniform >= 0.5
        rates = _hazards(universe, minute, card, card_home, possession, hidden)
        # Within this independent episode the current hazard persists until the
        # boundary. This is an explicit generative rule, not future match access.
        outcome_uniform = outcome_rng.random()
        unit_exponential = -math.log1p(-outcome_uniform)
        waiting_time = unit_exponential / sum(rates)
        features = {"card_active": card, "possession_high": possession, "clock_late": minute >= 60}
        exposures = {key: min(float(key), 90 - minute) if key != "FULL_TIME" else 90 - minute for key in HORIZONS}
        rows.append({"episode_id": "virtual-experiment-" + universe + "-" + str(index).zfill(6),
                     "order": index, "minute": minute, "features": features, "exposures": exposures,
                     "generation": {"card_home": card_home, "hidden_uniform": hidden_uniform,
                                    "outcome_uniform": outcome_uniform, "unit_exponential": unit_exponential,
                                    "home_hazard": rates[0], "away_hazard": rates[1]},
                     "labels": {key: int(waiting_time <= exposure) for key, exposure in exposures.items()}})
    return rows


def _fit_rate(rows):
    """Bounded Bernoulli exposure likelihood MLE; only supplied TRAIN rows enter."""
    low, high = 1e-6, 0.3
    for _ in range(48):
        rate = (low + high) / 2
        derivative = 0.0
        for exposure, label in rows:
            derivative += exposure / math.expm1(rate * exposure) if label else -exposure
        if derivative > 0:
            low = rate
        else:
            high = rate
    return (low + high) / 2


FEATURES = {"constant_past_only": (), "card": ("card_active",),
            "possession": ("possession_high",), "clock": ("clock_late",),
            "combined": ("card_active", "possession_high", "clock_late")}


def _group(features, keys):
    return "".join("1" if features[key] else "0" for key in keys) or "ALL"


def _learn(train, feature_keys):
    groups, all_rows = {}, []
    for row in train:
        group = _group(row["features"], feature_keys)
        # Fitting the specified next-goal-10min target avoids treating a label
        # repeated across horizons as independent training evidence.
        observation = (row["exposures"]["10"], row["labels"]["10"])
        groups.setdefault(group, []).append(observation)
        all_rows.append(observation)
    return {"rates": {group: _fit_rate(rows) for group, rows in groups.items()},
            "fallback_rate": _fit_rate(all_rows), "feature_keys": list(feature_keys),
            "training_episode_count": len(train), "fitted_target": "NEXT_GOAL_10_PLAYING_MINUTES"}


def _loss(probability, label):
    p = min(1 - 1e-12, max(1e-12, probability))
    return (probability - label) ** 2, -(label * math.log(p) + (1 - label) * math.log1p(-p))


def _paired(values):
    count = len(values)
    mean = math.fsum(values) / count
    variance = math.fsum((value - mean) ** 2 for value in values) / (count - 1) if count > 1 else 0.0
    se = math.sqrt(variance / count)
    return {"mean_improvement": mean, "standard_error": se,
            "approximate_95_percent_interval": [mean - 1.96 * se, mean + 1.96 * se],
            "paired_episode_count": count,
            "method": "Paired episode differences; normal approximation, no multiple-comparison adjustment."}


def _evaluate(test, fitted, unclipped=False):
    losses, metrics = {}, {}
    for horizon in HORIZONS:
        values = []
        for row in test:
            key = _group(row["features"], fitted["feature_keys"])
            rate = fitted["rates"].get(key, fitted["fallback_rate"])
            exposure = (90.0 if horizon == "FULL_TIME" else float(horizon)) if unclipped else row["exposures"][horizon]
            values.append(_loss(-math.expm1(-rate * exposure), row["labels"][horizon]))
        losses[horizon] = values
        metrics[horizon] = {"brier": math.fsum(value[0] for value in values) / len(values),
                            "log_loss": math.fsum(value[1] for value in values) / len(values),
                            "episode_count": len(values)}
    return metrics, losses


def relevance_experiment(seed=42, cases=400):
    """TRAIN-only fits and held-out paired utility across fictional worlds.

    ``cases`` is per universe. The first 70% are TRAIN; later independent
    episodes are TEST. This is not a historical data or live accuracy result.
    """
    _integer(seed, "seed", 0, 2**32 - 1)
    _integer(cases, "cases", 100, 2000)
    cutoff = cases * 7 // 10
    reports = []
    for universe in UNIVERSES:
        rows = _episodes(universe, seed, cases)
        train, test = rows[:cutoff], rows[cutoff:]
        fitted = {name: _learn(train, keys) for name, keys in FEATURES.items()}
        evaluated = {name: _evaluate(test, model) for name, model in fitted.items()}
        baseline_losses = evaluated["constant_past_only"][1]
        utility = {}
        for name in ("card", "possession", "clock", "combined"):
            utility[name.upper()] = {}
            for horizon in HORIZONS:
                candidate_losses = evaluated[name][1][horizon]
                baseline = baseline_losses[horizon]
                utility[name.upper()][horizon] = {
                    "brier": _paired([a[0] - b[0] for a, b in zip(baseline, candidate_losses)]),
                    "log_loss": _paired([a[1] - b[1] for a, b in zip(baseline, candidate_losses)])}
        unclipped_metrics, unclipped_losses = _evaluate(test, fitted["constant_past_only"], unclipped=True)
        clipping = {horizon: {"brier": _paired([a[0] - b[0] for a, b in zip(unclipped_losses[horizon], baseline_losses[horizon])]),
                              "log_loss": _paired([a[1] - b[1] for a, b in zip(unclipped_losses[horizon], baseline_losses[horizon])])}
                    for horizon in HORIZONS}
        reports.append({"universe": universe, "true_assumption": ASSUMPTIONS[universe],
                        "initial_conditions_sha256": hashlib.sha256(json.dumps([
                            {"order": row["order"], "minute": row["minute"], "features": row["features"],
                             "card_home": row["generation"]["card_home"],
                             "hidden_uniform": row["generation"]["hidden_uniform"],
                             "outcome_uniform": row["generation"]["outcome_uniform"]}
                            for row in rows], sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                        "train": {"count": len(train), "cutoff_episode_id": train[-1]["episode_id"],
                                  "order_maximum": train[-1]["order"]},
                        "test": {"count": len(test), "order_minimum": test[0]["order"],
                                 "episode_ids": [row["episode_id"] for row in test]},
                        "cohort_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                        "models": {name: {"model_id": "synthetic-exposure-bernoulli/1/" + universe + "/" + name,
                                          "fitted_on": "TRAIN_ONLY", **model, "test_metrics": evaluated[name][0]}
                                   for name, model in fitted.items()},
                        "feature_utility_vs_constant_past_only": utility,
                        "horizon_clipping_ablation": {"comparison": "Exposure-aware baseline versus intentionally misspecified no-clock-clipping baseline.",
                                                       "unclipped_test_metrics": unclipped_metrics,
                                                       "clipping_improvement": clipping}})
    return {"schema_version": "dragonhydra.virtual-relevance/1", "status": "RESEARCH_ONLY",
            "synthetic": True, "source_mode": "DEMONSTRATION", "seed": seed,
            "cases_per_universe": cases, "total_episode_count": cases * len(UNIVERSES),
            "target": "NEXT_GOAL_10_PLAYING_MINUTES", "horizons": list(HORIZONS),
            "research_target": {"notation": "R(X,Y,T)",
                                "definition": "Held-out proper-loss reduction from including candidate X when predicting Y using TRAIN evidence available by cutoff T.",
                                "estimator": "mean_TEST[loss(TRAIN_only_baseline,Y)-loss(TRAIN_only_feature_model,Y)]",
                                "mutual_information_estimate": False, "causal_claim": False},
            "metric_definitions": {"brier": "Scalar binary (p-y)^2; the generic evaluation module sums squared errors over all class probabilities.",
                                   "log_loss": "Natural-log binary loss; positive improvement is measured in nats per episode.",
                                   "improvement": "Baseline loss minus feature-model loss; negative and zero results are retained."},
            "controlled_conditions": "Corresponding episode indices share clocks, features, hidden-uniform draws and unit-exponential outcome draws across all worlds; only hazard rules differ.",
            "unseen_universe_generalization": "NOT_ESTABLISHED",
            "anticipatory_relevance": "CANDIDATE_NEXT_INCREMENT_NOT_IMPLEMENTED",
            "universes": reports, "calibration_state": "UNVERIFIED_FOR_REAL_WORLD",
            "assumptions": ["All observations, outcomes and feature values are invented by seeded generators.",
                "TRAIN precedes disjoint TEST episode IDs; labels and hidden tempo never enter feature dictionaries.",
                "Common random numbers pair worlds at identical initial conditions; worlds are not independent datasets.",
                "Each episode holds its current hazard fixed until its known regulation end; this differs from evolving match fixtures.",
                "Only the TRAIN next-goal-10-minute likelihood fits rates; TEST is used solely for scoring.",
                "Rates are bounded to 0.000001..0.3 per playing minute; unseen groups use TRAIN-only fallback.",
                "Positive paired loss reduction means synthetic held-out utility; finite samples can reverse signs.",
                "Intervals are approximate paired TEST-episode uncertainty, not real-world calibration, causal relevance or AI improvement.",
                "No probability configuration is automatically changed by this report."]}
