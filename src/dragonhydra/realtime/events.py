"""Strict virtual-event boundary and deterministic, correction-aware reduction."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import re

SCHEMA = "dragonhydra.live-event/1"
MODES = frozenset(("REPLAY", "DEMONSTRATION"))
FIELDS = frozenset(("schema_version", "event_id", "source_id", "match_id", "event_type",
                    "event_time", "received_at", "sequence", "revision", "participant",
                    "attributes", "source_mode", "quality_state"))
ATTRIBUTES = {
    "KICKOFF": {"minute", "duration_minutes", "period_end_minute", "home_team", "away_team"},
    "CLOCK": {"minute", "period", "period_end_minute", "end_time_known"},
    "GOAL": {"minute"}, "RED_CARD": {"minute"}, "YELLOW_CARD": {"minute"},
    "SHOT": {"minute", "on_target"}, "POSSESSION": {"minute", "home_percent"},
    "SUBSTITUTION": {"minute", "out", "in"},
    "SCORE": {"minute", "home", "away"}, "FULL_TIME": {"minute", "home", "away"},
    "HALF_TIME": {"minute"}, "RESUME": {"minute", "period", "period_end_minute"},
    "SUSPEND": {"minute"}, "STOPPAGE": {"minute", "duration_minutes", "period_end_minute"},
    "SOURCE_DISCONNECT": {"minute"}, "SOURCE_RECONNECT": {"minute"},
    "CORRECTION": {"minute", "target_event_id", "target_source_id", "target_revision",
                   "cancelled", "replacement_attributes"},
    "MARKET": {"minute", "home", "draw", "away"},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def identifier(prefix, value):
    return prefix + hashlib.sha256(canonical(value).encode()).hexdigest()[:32]


def instant(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("EVENT_TIMESTAMP_INVALID")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("EVENT_TIMESTAMP_INVALID") from None
    if result.utcoffset() is None:
        raise ValueError("EVENT_TIMESTAMP_ZONE_REQUIRED")
    return result.astimezone(timezone.utc)


def number(value, low, high, code="EVENT_NUMBER_INVALID"):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(code)
    return value


def virtual_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"virtual-[A-Za-z0-9_.:-]{1,100}", value):
        raise ValueError("VIRTUAL_ID_REQUIRED")
    return value


def validate_attributes(kind, attrs):
    if not isinstance(attrs, dict) or set(attrs) - ATTRIBUTES[kind] or "minute" not in attrs:
        raise ValueError("EVENT_ATTRIBUTES_INVALID")
    number(attrs["minute"], 0, 150)
    for name in ("home", "away"):
        if name in attrs:
            if kind == "MARKET":
                number(attrs[name], 1.001, 10000)
            elif type(attrs[name]) is not int or not 0 <= attrs[name] <= 100:
                raise ValueError("EVENT_SCORE_INVALID")
    if kind in ("SCORE", "FULL_TIME") and not {"home", "away"} <= attrs.keys():
        raise ValueError("EVENT_SCORE_REQUIRED")
    if kind == "MARKET":
        if not {"home", "draw", "away"} <= attrs.keys():
            raise ValueError("EVENT_MARKET_REQUIRED")
        number(attrs["draw"], 1.001, 10000)
    for name in ("duration_minutes", "period_end_minute"):
        if name in attrs:
            number(attrs[name], 1, 150)
    if "period" in attrs and (type(attrs["period"]) is not int or not 1 <= attrs["period"] <= 5):
        raise ValueError("EVENT_PERIOD_INVALID")
    for name in ("end_time_known", "on_target"):
        if name in attrs and type(attrs[name]) is not bool:
            raise ValueError("EVENT_BOOLEAN_INVALID")
    if "home_percent" in attrs:
        number(attrs["home_percent"], 0, 100)
    for name in ("home_team", "away_team", "out", "in"):
        if name in attrs and (not isinstance(attrs[name], str) or not 1 <= len(attrs[name]) <= 80):
            raise ValueError("VIRTUAL_LABEL_INVALID")
    if kind == "CORRECTION":
        for name in ("target_event_id", "target_source_id"):
            virtual_id(attrs.get(name))
        if type(attrs.get("target_revision")) is not int or attrs["target_revision"] < 1:
            raise ValueError("CORRECTION_REVISION_REQUIRED")
        if type(attrs.get("cancelled")) is not bool:
            raise ValueError("CORRECTION_ACTION_REQUIRED")
        if "replacement_attributes" in attrs and not isinstance(attrs["replacement_attributes"], dict):
            raise ValueError("CORRECTION_REPLACEMENT_INVALID")


def validate_event(raw):
    if not isinstance(raw, dict) or set(raw) != FIELDS:
        raise ValueError("EVENT_SCHEMA_FIELDS_INVALID")
    event = deepcopy(raw)
    if event["schema_version"] != SCHEMA or event["source_mode"] not in MODES:
        raise ValueError("VIRTUAL_EVENT_MODE_REQUIRED")
    for name in ("event_id", "source_id", "match_id"):
        virtual_id(event[name])
    if event["event_type"] not in ATTRIBUTES or event["quality_state"] != "VALIDATED":
        raise ValueError("EVENT_TYPE_OR_QUALITY_INVALID")
    if event["participant"] not in ("HOME", "AWAY", "NONE"):
        raise ValueError("EVENT_PARTICIPANT_INVALID")
    if event["event_type"] in ("GOAL", "RED_CARD", "YELLOW_CARD", "SUBSTITUTION", "SHOT") and event["participant"] == "NONE":
        raise ValueError("EVENT_SIDE_REQUIRED")
    for name in ("sequence", "revision"):
        if type(event[name]) is not int or not 1 <= event[name] <= 1000000:
            raise ValueError("EVENT_SEQUENCE_OR_REVISION_INVALID")
    if instant(event["received_at"]) < instant(event["event_time"]):
        raise ValueError("RECEIPT_PRECEDES_EVENT")
    for name in ("event_time", "received_at"):
        event[name] = instant(event[name]).isoformat(timespec="microseconds").replace("+00:00", "Z")
    validate_attributes(event["event_type"], event["attributes"])
    if len(canonical(event).encode()) > 4096:
        raise ValueError("EVENT_TOO_LARGE")
    return event


def fact_hash(event):
    """Repeated delivery time does not change an observation's identity."""
    return identifier("fact:", {k: v for k, v in event.items() if k != "received_at"})


def initial_state(match_id, source_mode="DEMONSTRATION"):
    virtual_id(match_id)
    if source_mode not in MODES:
        raise ValueError("VIRTUAL_EVENT_MODE_REQUIRED")
    return {"schema_version": "dragonhydra.match-state/1", "match_id": match_id,
            "synthetic": True, "source_mode": source_mode, "revision": 0,
            "minute": 0.0, "period": 1, "status": "SCHEDULED",
            "score": {"home": 0, "away": 0}, "red_cards": {"home": 0, "away": 0},
            "yellow_cards": {"home": 0, "away": 0},
            "teams": {"home": "Vector Town", "away": "Orbit Athletic"},
            "duration_minutes": 90.0, "period_end_minute": 45.0, "end_time_known": True,
            "primary_source_id": None, "connected": True, "source_scores": {},
            "statistics": {"shots": {"home": 0, "away": 0},
                           "shots_on_target": {"home": 0, "away": 0}, "home_possession_percent": None},
            "quality": {"status": "NO_OBSERVATIONS", "flags": [], "freshness_seconds": None},
            "last_event_time": None, "received_at": None}


def apply_fact(previous, event):
    state = deepcopy(previous)
    attrs, kind = event["attributes"], event["event_type"]
    source = event["source_id"]
    if state["primary_source_id"] is None and kind == "KICKOFF":
        state["primary_source_id"] = source
    primary = state["primary_source_id"] == source
    if primary and (state["status"] != "FINISHED" or kind == "FULL_TIME"):
        # A new period may reset the display clock after first-half added time.
        advances_period = attrs.get("period", state["period"]) > state["period"]
        state["minute"] = float(attrs["minute"]) if advances_period else max(state["minute"], float(attrs["minute"]))
        side = event["participant"].lower()
        if kind == "KICKOFF":
            state["status"] = "IN_PLAY"
            state["duration_minutes"] = float(attrs.get("duration_minutes", 90))
            state["period_end_minute"] = float(attrs.get("period_end_minute", 45))
            state["teams"] = {"home": attrs.get("home_team", "Vector Town"),
                              "away": attrs.get("away_team", "Orbit Athletic")}
        elif kind == "GOAL":
            state["score"][side] += 1
        elif kind in ("RED_CARD", "YELLOW_CARD"):
            state["red_cards" if kind == "RED_CARD" else "yellow_cards"][side] += 1
        elif kind == "SHOT":
            state["statistics"]["shots"][side] += 1
            state["statistics"]["shots_on_target"][side] += int(attrs.get("on_target", False))
        elif kind == "POSSESSION":
            state["statistics"]["home_possession_percent"] = attrs.get("home_percent")
        elif kind in ("SCORE", "FULL_TIME"):
            state["score"] = {key: attrs[key] for key in ("home", "away")}
        if kind == "HALF_TIME":
            state["status"] = "HALF_TIME"
        elif kind == "SUSPEND":
            state["status"] = "SUSPENDED"
        elif kind == "RESUME":
            state["status"] = "IN_PLAY"
        elif kind == "FULL_TIME":
            state["status"] = "FINISHED"
            state["minute"] = float(attrs["minute"])
        for key in ("period", "period_end_minute", "duration_minutes", "end_time_known"):
            if key in attrs:
                state[key] = attrs[key]
    if kind == "SCORE":
        state["source_scores"][source] = {"home": attrs["home"], "away": attrs["away"], "minute": attrs["minute"]}
    if kind == "SOURCE_DISCONNECT" and primary:
        state["connected"] = False
    elif kind == "SOURCE_RECONNECT" and primary:
        state["connected"] = True
    state["last_event_time"] = max(filter(None, (state["last_event_time"], event["event_time"])))
    state["received_at"] = max(filter(None, (state["received_at"], event["received_at"])))
    return state


def reduce_events(events, match_id, source_mode):
    """Rebuild only for corrections/reordering; select latest known event versions."""
    latest = {}
    for event in events:
        key = event["source_id"], event["event_id"]
        if key not in latest or event["revision"] > latest[key]["revision"]:
            latest[key] = event
    patches = {}
    for event in sorted(latest.values(), key=lambda e: (e["received_at"], e["sequence"], e["event_id"])):
        if event["event_type"] != "CORRECTION":
            continue
        a = event["attributes"]
        key = a["target_source_id"], a["target_event_id"]
        target = latest.get(key)
        if not target or target["revision"] != a["target_revision"]:
            continue
        patches[key] = a
    selected = []
    for key, event in latest.items():
        if event["event_type"] == "CORRECTION":
            continue
        patch = patches.get(key)
        if patch:
            if patch["cancelled"]:
                continue
            event = deepcopy(event)
            event["attributes"] = patch.get("replacement_attributes", event["attributes"])
            validate_attributes(event["event_type"], event["attributes"])
        selected.append(event)
    selected.sort(key=lambda e: (instant(e["event_time"]), e["sequence"], e["source_id"], e["event_id"]))
    state = initial_state(match_id, source_mode)
    for event in selected:
        state = apply_fact(state, event)
    reviews = [e for e in latest.values() if e["event_type"] == "CORRECTION"
               and e["source_id"] == state["primary_source_id"]]
    if reviews:
        state["minute"] = max(state["minute"], max(e["attributes"]["minute"] for e in reviews))
    return state


def semantic_state(state):
    return {key: state[key] for key in ("minute", "period", "status", "score", "red_cards",
            "duration_minutes", "period_end_minute", "end_time_known")}


CAPABILITIES = {
    "virtual-normalized-replay": {
        "source_modes": ["REPLAY", "DEMONSTRATION"], "synthetic_only": True,
        "event_types": sorted(ATTRIBUTES), "push_feed": False, "live_verified": False,
        "identity": "Explicit virtual source-scoped event ID, sequence and revision",
        "corrections": "Same-source version replacement or explicit correction; forecasts append invalidations",
    },
    "genuine-live-provider": {"configured": False, "live_verified": False, "state": "NEUTRAL"},
}
