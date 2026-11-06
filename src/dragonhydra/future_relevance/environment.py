"""Private fictional world and a deliberately narrow observation boundary.

Policy code receives public() dictionaries, never this simulator instance.
Acquisition changes visibility only; it never changes the goal stream.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import math
import random

from ..realtime.events import canonical, identifier, initial_state, instant, virtual_id
from ..realtime.worlds import UNIVERSES as BASE_FAMILIES, _hazards

CATEGORIES = ("possession", "red_cards", "shots", "fatigue")
FAMILIES = (*BASE_FAMILIES, "possession_inverse", "late_card_interaction")
TARGETS = ("GOAL_OCCURRENCE", "FULL_TIME_RESULT", "NEXT_GOAL_SIDE", "REMAINING_GOALS")
HORIZONS = ("1", "5", "10", "30", "FULL_TIME")
TRAIN_FAMILIES = ("constant", "card_sensitive", "tempo_signal")
VALIDATION_FAMILIES = ("clock_sensitive",)
TEST_FAMILIES = ("noisy_signal", "possession_inverse", "late_card_interaction")
EPOCH = datetime(2036, 1, 1, 12, tzinfo=timezone.utc)
OUTCOME_DELAY_MINUTES = 2 / 60


def finite(value, low, high, code="FUTURE_NUMBER_INVALID"):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(code)
    return float(value)


def integer(value, low=0, high=2**31-1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("FUTURE_INTEGER_INVALID")
    return value


def rng(seed, label):
    value = hashlib.sha256(canonical([seed, label]).encode()).digest()
    return random.Random(int.from_bytes(value[:16], "big"))


class VirtualEpisode:
    """Opaque seeded world; only explicit eligible acquisitions disclose values."""

    def __init__(self, family="constant", seed=42, *, minute=60, target="GOAL_OCCURRENCE",
                 horizon="10", budget=.12, branch_seed=None, match_id=None, group_id=None):
        if family not in FAMILIES or target not in TARGETS or horizon not in HORIZONS:
            raise ValueError("FUTURE_WORLD_TARGET_OR_HORIZON_UNSUPPORTED")
        if target == "FULL_TIME_RESULT" and horizon != "FULL_TIME":
            raise ValueError("FUTURE_RESULT_REQUIRES_FULL_TIME")
        self._seed, self._family = integer(seed), family
        self._branch_seed = integer(branch_seed) if branch_seed is not None else None
        self._origin = finite(minute, 45, 89)
        self._target, self._horizon = target, horizon
        self._maturity = 90. if horizon == "FULL_TIME" else min(90., self._origin+float(horizon))
        self._budget = finite(budget, 0, 100)
        self._now, self._spent, self._revision = self._origin, 0., 0
        self._acquired = {}
        self._group = group_id or identifier("virtual-root-", seed)
        if self._group != identifier("virtual-root-", seed):
            raise ValueError("FUTURE_ROOT_GROUP_IDENTITY_INVALID")
        self._id = match_id or identifier("virtual-episode-", [family, seed, minute, target, horizon, budget, branch_seed])
        virtual_id(self._group); virtual_id(self._id)
        self._epoch = EPOCH+timedelta(days=seed//100000, microseconds=(seed%1000)*10000)
        random_world = rng(seed, "latent")
        self._possession = random_world.choice((False, True))
        self._hidden_tempo = random_world.choice((False, True))
        self._card = random_world.choice((False, True))
        self._card_home = random_world.choice((False, True))
        self._shots = self._possession if random_world.random() < .75 else not self._possession
        self._values = {"possession": .8 if self._possession else .2,
                        "shots": .8 if self._shots else .2,
                        "fatigue": .8 if self._hidden_tempo else .2,
                        "red_cards": {"home": int(self._card and self._card_home),
                                      "away": int(self._card and not self._card_home)}}
        self._costs = {category: round(rng(seed, "cost:"+category).uniform(.006, .055), 6) for category in CATEGORIES}
        self._available = {category: self._origin+(2 if category == "fatigue" else 0) for category in CATEGORIES}
        self._goals = self._generate_goals()

    def _at(self, minute):
        return (self._epoch+timedelta(minutes=minute)).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _rates(self, minute):
        if self._family == "possession_inverse":
            return _hazards("tempo_signal", minute, self._card, self._card_home,
                            not self._possession, self._hidden_tempo)
        if self._family == "late_card_interaction":
            family = "card_sensitive" if minute >= 65 else "constant"
            return _hazards(family, minute, self._card and minute >= 30, self._card_home,
                            self._possession, self._hidden_tempo)
        return _hazards(self._family, minute, self._card and minute >= 30, self._card_home,
                        self._possession, self._hidden_tempo)

    def _generate_goals(self):
        result = []
        for minute in range(90):
            # A branch changes future random draws only. Its accepted prefix and
            # hidden state at the branch origin remain shared with its parent.
            future = self._branch_seed if minute >= self._origin and self._branch_seed is not None else self._seed
            random_events = rng([self._seed, future], "goals:"+str(minute))
            home, away = self._rates(minute)
            elapsed = 0.
            for _ in range(64):
                elapsed += random_events.expovariate(home+away)
                if elapsed >= 1:
                    break
                result.append((minute+elapsed, "home" if random_events.random() < home/(home+away) else "away"))
            else:
                raise ValueError("FUTURE_WORLD_GENERATION_LIMIT")
        return tuple(result)

    def public(self):
        before_now = [(at, side) for at, side in self._goals if at <= min(90, self._now)]
        in_window = [(at, side) for at, side in before_now if self._origin < at <= self._maturity]
        state = initial_state(self._id)
        state.update(minute=min(90., self._now), period=2, period_end_minute=90.,
                     status="FINISHED" if self._now >= 90 else "IN_PLAY", revision=self._revision,
                     score={side: sum(s == side for _, s in before_now) for side in ("home", "away")},
                     received_at=self._at(self._now), last_event_time=self._at(min(90, self._now)))
        if "red_cards" in self._acquired:
            state["red_cards"] = deepcopy(self._acquired["red_cards"]["value"])
        state["quality"] = {"status": "VIRTUAL_PARTIAL_INFORMATION",
            "flags": ["UNREVEALED_RED_CARDS_USE_BASELINE_ZERO_ASSUMPTION"] if "red_cards" not in self._acquired else [],
            "clock": "VIRTUAL", "freshness_seconds": 0}
        candidates = []
        for category in CATEGORIES:
            acquired = self._acquired.get(category)
            available = self._available[category]
            candidates.append({"category": category,
                "availability": "ACQUIRED" if acquired else "AVAILABLE" if self._now >= available else "PENDING",
                "available_at": self._at(available), "cost": self._costs[category],
                "computation_cost": .001,
                "freshness_seconds": max(0., (self._now-available)*60) if acquired else None})
        return {"schema_version": "dragonhydra.future-snapshot/1", "synthetic": True,
            "source_mode": "DEMONSTRATION", "episode_id": self._id, "match_id": self._id,
            "group_id": self._group, "revision": self._revision, "now": self._at(self._now),
            "now_minute": self._now, "decision_at": self._at(self._now),
            "target": self._target, "horizon": self._horizon, "target_origin_minute": self._origin,
            "target_maturity_minute": self._maturity, "observed_state": state,
            "candidates": candidates, "acquired": deepcopy(self._acquired),
            "budget_total": self._budget, "budget_remaining": max(0., self._budget-self._spent),
            "observed_goal_count_since_origin": len(in_window),
            "first_observed_goal_side": in_window[0][1] if in_window else None}

    def acquire(self, category, decision_id):
        if category not in CATEGORIES:
            raise ValueError("FUTURE_CATEGORY_UNSUPPORTED")
        virtual_id(decision_id)
        if category in self._acquired:
            raise ValueError("FUTURE_REDUNDANT_ACQUISITION")
        if self._now < self._available[category]:
            raise ValueError("FUTURE_OBSERVATION_NOT_AVAILABLE")
        if self._now >= self._maturity:
            raise ValueError("FUTURE_TARGET_ALREADY_MATURED")
        cost = self._costs[category]
        if cost > self._budget-self._spent+1e-12:
            raise ValueError("FUTURE_ACQUISITION_BUDGET_EXHAUSTED")
        observation = {"value": deepcopy(self._values[category]),
                       "observed_at": self._at(self._available[category]),
                       "available_at": self._at(self._available[category]), "received_at": self._at(self._now)}
        self._acquired[category] = observation
        self._spent += cost
        self._revision += 1
        return {"schema_version": "dragonhydra.future-acquisition/1", "synthetic": True,
            "acquisition_id": identifier("virtual-acquisition-", [self._id, category, decision_id]),
            "episode_id": self._id, "decision_id": decision_id, "category": category,
            "estimated_cost": cost, "actual_cost": cost, "cost_unit": "VIRTUAL_CREDIT",
            "information_revealed": observation, "revision": self._revision}

    def advance(self, minutes):
        minutes = finite(minutes, 0, 95)
        if self._now+minutes > 95:
            raise ValueError("FUTURE_CLOCK_LIMIT")
        self._now += minutes
        self._revision += 1
        return self.public()

    def matured_outcome(self):
        if self._now+1e-12 < self._maturity+OUTCOME_DELAY_MINUTES:
            raise ValueError("FUTURE_OUTCOME_NOT_AVAILABLE")
        events = [(at, side) for at, side in self._goals if self._origin < at <= self._maturity]
        if self._target == "GOAL_OCCURRENCE":
            label = "goal" if events else "no_goal"
        elif self._target == "NEXT_GOAL_SIDE":
            label = events[0][1] if events else "no_goal"
        elif self._target == "REMAINING_GOALS":
            label = str(len(events)) if len(events) <= 12 else "13PLUS"
        else:
            scores = {side: sum(s == side for at, s in self._goals if at <= self._maturity) for side in ("home", "away")}
            label = "home" if scores["home"] > scores["away"] else "away" if scores["away"] > scores["home"] else "draw"
        return {"schema_version": "dragonhydra.future-outcome/1", "synthetic": True,
            "outcome_id": identifier("virtual-outcome-", [self._id, self._target, self._horizon]),
            "episode_id": self._id, "group_id": self._group, "target": self._target,
            "horizon": self._horizon, "label": label,
            "occurred_at": self._at(self._maturity),
            "available_at": self._at(self._maturity+OUTCOME_DELAY_MINUTES)}

    def descriptor(self):
        """Private persistence contract. Never hand this dictionary to a policy."""
        return {"family": self._family, "seed": self._seed, "minute": self._origin,
                "target": self._target, "horizon": self._horizon, "budget": self._budget,
                "branch_seed": self._branch_seed, "match_id": self._id, "group_id": self._group,
                "now_minute": self._now, "spent": self._spent, "revision": self._revision,
                "acquired": deepcopy(self._acquired)}

    @classmethod
    def from_descriptor(cls, raw):
        value = deepcopy(raw)
        now, spent, revision, acquired = (value.pop(key) for key in ("now_minute", "spent", "revision", "acquired"))
        episode = cls(**value)
        episode._now = finite(now, episode._origin, 95)
        episode._spent = finite(spent, 0, episode._budget)
        episode._revision = integer(revision, 0, 1000000)
        if not isinstance(acquired, dict) or set(acquired)-set(CATEGORIES):
            raise ValueError("FUTURE_RETAINED_VISIBILITY_INVALID")
        for category, observation in acquired.items():
            if (not isinstance(observation, dict) or set(observation) != {"value", "observed_at", "available_at", "received_at"}
                    or observation["value"] != episode._values[category]
                    or instant(observation["available_at"]) != instant(episode._at(episode._available[category]))
                    or instant(observation["observed_at"]) > instant(observation["received_at"])
                    or instant(observation["available_at"]) > instant(observation["received_at"])
                    or instant(observation["received_at"]) > instant(episode._at(episode._now))):
                raise ValueError("FUTURE_RETAINED_OBSERVATION_INVALID")
        if not math.isclose(episode._spent, math.fsum(episode._costs[c] for c in acquired), abs_tol=1e-12, rel_tol=0):
            raise ValueError("FUTURE_RETAINED_COST_INVALID")
        if episode._revision < len(acquired):
            raise ValueError("FUTURE_RETAINED_REVISION_INVALID")
        episode._acquired = acquired
        return episode

    def clone(self):
        # Immutable private goal tuples may be shared; visibility and budgets
        # are copied. No identical world is regenerated merely to compare arms.
        return deepcopy(self)

    def fork(self, branch_seed):
        if self._now != self._origin or self._acquired:
            raise ValueError("FUTURE_BRANCH_REQUIRES_INITIAL_INFORMATION_PREFIX")
        return VirtualEpisode(self._family, self._seed, minute=self._origin, target=self._target,
                              horizon=self._horizon, budget=self._budget, branch_seed=integer(branch_seed),
                              group_id=self._group)
