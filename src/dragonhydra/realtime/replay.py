"""Deterministic virtual objects and interruptible, server-owned virtual time."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import threading

from .events import SCHEMA, instant, validate_event

EPOCH = datetime(2035, 1, 1, 12, tzinfo=timezone.utc)


def standard_fixture(match_id="virtual-standard-match", mode="DEMONSTRATION"):
    result = []
    sequence = 0
    def add(kind, minute, participant="NONE", *, delay=2, **attrs):
        nonlocal sequence
        sequence += 1
        at = EPOCH + timedelta(minutes=minute, seconds=sequence / 10)
        event = {"schema_version": SCHEMA, "event_id": f"virtual-event-{sequence:04}",
                 "source_id": "virtual-source-primary", "match_id": match_id,
                 "event_type": kind, "event_time": at.isoformat().replace("+00:00", "Z"),
                 "received_at": (at + timedelta(seconds=delay)).isoformat().replace("+00:00", "Z"),
                 "sequence": sequence, "revision": 1, "participant": participant,
                 "attributes": {"minute": minute, **attrs}, "source_mode": mode, "quality_state": "VALIDATED"}
        result.append(validate_event(event))
        return event
    add("KICKOFF", 0, duration_minutes=90, period_end_minute=45,
        home_team="Vector Town", away_team="Orbit Athletic")
    add("POSSESSION", 0, home_percent=53)
    shot = add("SHOT", 0, "HOME", on_target=True)
    duplicate = deepcopy(shot)
    duplicate["received_at"] = (instant(shot["received_at"]) + timedelta(seconds=3)).isoformat().replace("+00:00", "Z")
    result.append(duplicate)
    add("CLOCK", 12)
    goal = add("GOAL", 12, "HOME")
    add("GOAL", 31, "AWAY")
    add("HALF_TIME", 45)
    add("RESUME", 45, period=2, period_end_minute=90)
    card = add("RED_CARD", 62, "HOME")
    add("SUBSTITUTION", 62, "HOME", out="Virtual Player H03", **{"in": "Virtual Player H07"})
    add("POSSESSION", 62, home_percent=39)
    add("CORRECTION", 70, delay=45, target_event_id=goal["event_id"],
        target_source_id=goal["source_id"], target_revision=1, cancelled=True)
    add("CLOCK", 78)
    add("CORRECTION", 82, target_event_id=card["event_id"], target_source_id=card["source_id"],
        target_revision=1, cancelled=True)
    add("STOPPAGE", 89, period_end_minute=95)
    add("SOURCE_DISCONNECT", 90)
    add("SOURCE_RECONNECT", 91)
    add("FULL_TIME", 95, delay=90, home=0, away=1)
    return result


class ReplayController:
    def __init__(self, store, ingest):
        self.store, self.ingest = store, ingest
        self.lock = threading.RLock()
        self.tasks = {}
        self.closed = False

    def install(self, match_id, fixture, *, position=0, speed=100):
        controls = {"position": position, "total": len(fixture),
                    "status": "PAUSED", "speed": speed, "clock_mode": "VIRTUAL",
                    "future_fixture_exposed": False}
        self.store.set_replay(match_id, controls, fixture)
        return controls

    def pause(self, match_id):
        with self.lock:
            task = self.tasks.get(match_id)
            if task:
                task[0].set()
            controls = self.store.get_replay(match_id)
            if controls["status"] == "PLAYING":
                controls["status"] = "PAUSED"
                self.store.set_replay(match_id, controls)
        if task and task[1] is not threading.current_thread():
            task[1].join(timeout=3)
            if task[1].is_alive():
                raise ValueError("REPLAY_PAUSE_PENDING")
        return controls

    def step(self, match_id, steps=1):
        if type(steps) is not int or not 1 <= steps <= 100:
            raise ValueError("REPLAY_STEPS_INVALID")
        self.pause(match_id)
        with self.lock:
            controls = self.store.get_replay(match_id, True)
            fixture = controls.pop("fixture", [])
            for _ in range(steps):
                if controls["position"] >= len(fixture):
                    break
                event = fixture[controls["position"]]
                self.ingest(event)
                controls["position"] += 1
                controls["virtual_time"] = event["received_at"]
                self.store.set_replay(match_id, controls)
            controls["status"] = "COMPLETED" if controls["position"] >= len(fixture) else "PAUSED"
            self.store.set_replay(match_id, controls)
            return controls

    def control(self, match_id, action, speed=100, steps=1):
        if action == "step":
            return self.step(match_id, steps)
        if action == "pause":
            return self.pause(match_id)
        if action not in ("start", "resume"):
            raise ValueError("REPLAY_ACTION_UNSUPPORTED")
        if type(speed) not in (int, float) or not math.isfinite(speed) or not 0.1 <= speed <= 100:
            raise ValueError("REPLAY_SPEED_INVALID")
        self.pause(match_id)
        with self.lock:
            if self.closed:
                raise ValueError("REPLAY_CLOSED")
            active = sum(t.is_alive() for _, t in self.tasks.values())
            if active >= 4:
                raise ValueError("REPLAY_CONCURRENCY_BUDGET_REACHED")
            controls = self.store.get_replay(match_id)
            if controls["position"] >= controls["total"]:
                return controls
            controls.update(status="PLAYING", speed=speed)
            self.store.set_replay(match_id, controls)
            stop = threading.Event()
            def run():
                try:
                    while not stop.is_set():
                        current = self.store.get_replay(match_id, True)
                        fixture = current.pop("fixture")
                        position = current["position"]
                        if position >= len(fixture):
                            current["status"] = "COMPLETED"
                            self.store.set_replay(match_id, current)
                            break
                        if position:
                            delay = max(0, (instant(fixture[position]["received_at"])
                                            - instant(fixture[position-1]["received_at"])).total_seconds()) / speed
                            if stop.wait(delay):
                                break
                        if stop.is_set():
                            break
                        self.ingest(fixture[position])
                        current["position"] += 1
                        current["virtual_time"] = fixture[position]["received_at"]
                        self.store.set_replay(match_id, current)
                except Exception:
                    current = self.store.get_replay(match_id)
                    current["status"] = "FAILED"
                    current["reason"] = "REPLAY_OPERATION_FAILED"
                    self.store.set_replay(match_id, current)
            thread = threading.Thread(target=run, name="virtual-replay", daemon=True)
            self.tasks[match_id] = stop, thread
            thread.start()
            return controls

    def close(self):
        self.closed = True
        for match in list(self.tasks):
            self.pause(match)
