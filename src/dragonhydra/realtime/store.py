"""Owned SQLite event journal. Facts, states and forecasts are append-only.

The only mutable rows are derived pointers, operational counters and replay
controls. No existing product/retained/provider database is accepted here.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import threading

from .events import (apply_fact, canonical, fact_hash, identifier, initial_state,
                     instant, reduce_events, semantic_state, validate_attributes,
                     validate_event, virtual_id)

DDL = """
CREATE TABLE IF NOT EXISTS research_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS matches(match_id TEXT PRIMARY KEY,state TEXT NOT NULL,current_forecast TEXT,descriptor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(match_id TEXT NOT NULL,source_id TEXT NOT NULL,event_id TEXT NOT NULL,
 revision INTEGER NOT NULL,sequence INTEGER NOT NULL,state_revision INTEGER NOT NULL,
 event_time TEXT NOT NULL,received_at TEXT NOT NULL,fact_hash TEXT NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(match_id,source_id,event_id,revision));
CREATE INDEX IF NOT EXISTS events_order ON events(match_id,state_revision);
CREATE INDEX IF NOT EXISTS events_sequence ON events(match_id,source_id,sequence);
CREATE TABLE IF NOT EXISTS states(match_id TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(match_id,revision));
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY,match_id TEXT NOT NULL,event_id TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS forecasts(forecast_id TEXT PRIMARY KEY,match_id TEXT NOT NULL,
 revision INTEGER NOT NULL,state_revision INTEGER NOT NULL,payload TEXT NOT NULL,UNIQUE(match_id,revision));
CREATE TABLE IF NOT EXISTS invalidations(forecast_id TEXT NOT NULL,state_revision INTEGER NOT NULL,reason TEXT NOT NULL,
 PRIMARY KEY(forecast_id,state_revision));
CREATE TABLE IF NOT EXISTS analyses(packet_id TEXT PRIMARY KEY,match_id TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_intents(packet_id TEXT PRIMARY KEY,match_id TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS replay(match_id TEXT PRIMARY KEY,fixture TEXT NOT NULL,controls TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metrics(name TEXT PRIMARY KEY,value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS experiments(experiment_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
"""


class Store:
    def __init__(self, directory, *, max_events=100000, max_matches=128):
        if type(max_events) is not int or not 1 <= max_events <= 1000000:
            raise ValueError("EVENT_RETENTION_BUDGET_INVALID")
        if type(max_matches) is not int or not 1 <= max_matches <= 1024:
            raise ValueError("MATCH_RETENTION_BUDGET_INVALID")
        self.directory = Path(directory).absolute()
        for path in (self.directory, *self.directory.parents):
            if path.exists() and (path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
                raise ValueError("RESEARCH_REPARSE_PATH_REJECTED")
        self.path = self.directory / "virtual-research.sqlite3"
        if self.directory.exists():
            allowed = {self.path.name, self.path.name+"-wal", self.path.name+"-shm", self.path.name+"-journal"}
            for child in self.directory.iterdir():
                if child.name not in allowed:
                    raise ValueError("FOREIGN_RESEARCH_DIRECTORY_REJECTED")
                if child.is_symlink() or getattr(child.lstat(), "st_file_attributes", 0) & 0x400:
                    raise ValueError("RESEARCH_REPARSE_PATH_REJECTED")
        if self.path.exists():
            # Immutable read-only preflight cannot create WAL/SHM or mutate a
            # foreign schema merely to discover that ownership is wrong.
            try:
                with closing(sqlite3.connect(self.path.as_uri()+"?mode=ro&immutable=1", uri=True)) as probe:
                    row = probe.execute("SELECT value FROM research_meta WHERE key='identity'").fetchone()
                    if not row or row[0] != "dragonhydra.synthetic-research/1":
                        raise ValueError("FOREIGN_DATABASE_REJECTED")
            except sqlite3.DatabaseError:
                raise ValueError("FOREIGN_DATABASE_REJECTED") from None
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_events, self.max_matches = max_events, max_matches
        self.lock = threading.RLock()
        with self.connect() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and "research_meta" not in tables:
                raise ValueError("FOREIGN_DATABASE_REJECTED")
            db.executescript(DDL)
            previous = db.execute("SELECT value FROM research_meta WHERE key='identity'").fetchone()
            identity = "dragonhydra.synthetic-research/1"
            if previous and previous[0] != identity:
                raise ValueError("FOREIGN_DATABASE_REJECTED")
            db.execute("INSERT OR IGNORE INTO research_meta VALUES('identity',?)", (identity,))
            for table in ("events", "states", "forecasts", "analyses", "analysis_intents", "decisions", "invalidations", "experiments"):
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RESEARCH_EVIDENCE'); END")
            db.commit()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def bump(db, name, amount=1):
        db.execute("INSERT INTO metrics VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=value+excluded.value",
                   (name, amount))

    def metric(self, name, amount=1):
        with self.lock, self.connect() as db:
            self.bump(db, name, amount)
            db.commit()

    def metrics(self):
        with self.connect() as db:
            return dict(db.execute("SELECT name,value FROM metrics"))

    def create_match(self, match_id, source_mode="DEMONSTRATION", descriptor=None):
        state = initial_state(match_id, source_mode)
        descriptor = {"synthetic": True, **(descriptor or {})}
        if descriptor.get("synthetic") is not True:
            raise ValueError("SYNTHETIC_DESCRIPTOR_REQUIRED")
        with self.lock, self.connect() as db:
            row = db.execute("SELECT state FROM matches WHERE match_id=?", (match_id,)).fetchone()
            if row:
                if json.loads(row[0])["source_mode"] != source_mode:
                    raise ValueError("MATCH_MODE_CONFLICT")
                return json.loads(row[0])
            if db.execute("SELECT COUNT(*) FROM matches").fetchone()[0] >= self.max_matches:
                raise ValueError("MATCH_RETENTION_BUDGET_REACHED")
            db.execute("INSERT INTO matches VALUES(?,?,NULL,?)", (match_id, canonical(state), canonical(descriptor)))
            db.execute("INSERT INTO states VALUES(?,0,?)", (match_id, canonical(state)))
            db.commit()
        return state

    def state(self, match_id, revision=None):
        virtual_id(match_id)
        with self.connect() as db:
            if revision is None:
                row = db.execute("SELECT state FROM matches WHERE match_id=?", (match_id,)).fetchone()
            else:
                row = db.execute("SELECT payload FROM states WHERE match_id=? AND revision=?", (match_id, revision)).fetchone()
            if not row:
                raise LookupError("VIRTUAL_MATCH_STATE_NOT_FOUND")
            return json.loads(row[0])

    def descriptor(self, match_id):
        with self.connect() as db:
            row = db.execute("SELECT descriptor FROM matches WHERE match_id=?", (match_id,)).fetchone()
            if not row:
                raise LookupError("VIRTUAL_MATCH_NOT_FOUND")
            return json.loads(row[0])

    def matches(self):
        with self.connect() as db:
            return [{"match_id": r[0], "source_mode": json.loads(r[1])["source_mode"],
                     "synthetic": True, "state": json.loads(r[1])}
                    for r in db.execute("SELECT match_id,state FROM matches ORDER BY match_id")]

    def events(self, match_id, *, limit=10000, through_revision=None):
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError("HISTORY_LIMIT_INVALID")
        with self.connect() as db:
            if through_revision is None:
                rows = db.execute("SELECT payload FROM events WHERE match_id=? ORDER BY state_revision DESC LIMIT ?",
                                  (match_id, limit)).fetchall()
            else:
                rows = db.execute("SELECT payload FROM events WHERE match_id=? AND state_revision<=? "
                                  "ORDER BY state_revision DESC LIMIT ?", (match_id, through_revision, limit)).fetchall()
            return [json.loads(r[0]) for r in reversed(rows)]

    def accept(self, raw, *, force_recompute=False):
        if type(force_recompute) is not bool:
            raise ValueError("COMPUTATION_POLICY_INVALID")
        event = validate_event(raw)
        match_id = event["match_id"]
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM matches WHERE match_id=?", (match_id,)).fetchone()
            if not row:
                raise LookupError("VIRTUAL_MATCH_NOT_FOUND")
            previous = json.loads(row[0])
            if previous["source_mode"] != event["source_mode"]:
                raise ValueError("MATCH_MODE_CONFLICT")
            self.bump(db, "events_received")
            key = (match_id, event["source_id"], event["event_id"], event["revision"])
            old = db.execute("SELECT fact_hash FROM events WHERE match_id=? AND source_id=? AND event_id=? AND revision=?", key).fetchone()
            digest = fact_hash(event)
            if old:
                if old[0] != digest:
                    raise ValueError("EVENT_IDENTITY_CONFLICT")
                self.bump(db, "duplicates_rejected")
                decision = {"action": "DUPLICATE", "event_id": event["event_id"],
                            "reason_codes": ["ALREADY_INCORPORATED"], "state_revision": previous["revision"]}
                db.execute("INSERT INTO decisions(match_id,event_id,payload) VALUES(?,?,?)",
                           (match_id, event["event_id"], canonical(decision)))
                db.commit()
                return event, decision, previous
            accepted = db.execute("SELECT value FROM metrics WHERE name='events_accepted'").fetchone()
            if (accepted[0] if accepted else 0) >= self.max_events:
                raise ValueError("EVENT_RETENTION_BUDGET_REACHED")
            prior_version = db.execute("SELECT revision,payload FROM events WHERE match_id=? AND source_id=? AND event_id=? "
                                      "ORDER BY revision DESC LIMIT 1", key[:3]).fetchone()
            if prior_version:
                original = json.loads(prior_version[1])
                if event["revision"] != prior_version[0] + 1:
                    raise ValueError("EVENT_REVISION_CHAIN_INVALID")
                if any(event[k] != original[k] for k in ("sequence", "event_type", "event_time", "participant")):
                    raise ValueError("EVENT_REVISION_IDENTITY_CHANGED")
            elif event["revision"] != 1:
                raise ValueError("INITIAL_EVENT_REVISION_INVALID")
            if (previous["status"] == "FINISHED" and event["source_id"] == previous["primary_source_id"]
                    and not prior_version and event["event_type"] not in
                    ("CORRECTION", "SOURCE_DISCONNECT", "SOURCE_RECONNECT", "MARKET")):
                final = db.execute("SELECT event_time FROM events WHERE match_id=? AND source_id=? "
                                   "AND json_extract(payload,'$.event_type')='FULL_TIME' ORDER BY state_revision DESC LIMIT 1",
                                   (match_id, event["source_id"])).fetchone()
                if not final or instant(event["event_time"]) > instant(final[0]):
                    raise ValueError("POST_FINAL_UNVERSIONED_SPORT_EVENT_REJECTED")
            if event["event_type"] == "CORRECTION":
                a = event["attributes"]
                if a["target_source_id"] != event["source_id"]:
                    raise ValueError("FOREIGN_SOURCE_CORRECTION_REJECTED")
                target = db.execute("SELECT revision,payload FROM events WHERE match_id=? AND source_id=? AND event_id=? "
                                    "ORDER BY revision DESC LIMIT 1",
                                    (match_id, a["target_source_id"], a["target_event_id"])).fetchone()
                if not target or target[0] != a["target_revision"]:
                    raise ValueError("CORRECTION_TARGET_NOT_CURRENT")
                target_event = json.loads(target[1])
                if target_event["event_type"] in ("CORRECTION", "KICKOFF", "FULL_TIME"):
                    raise ValueError("CORRECTION_TARGET_UNSUPPORTED")
                if not a["cancelled"]:
                    validate_attributes(target_event["event_type"], a.get("replacement_attributes", {}))
            watermarks = deepcopy(previous.get("sequence_watermarks", {}))
            source = event["source_id"]
            if source not in watermarks and len(watermarks) >= 16:
                raise ValueError("SOURCE_CARDINALITY_BUDGET_REACHED")
            position_exists = db.execute("SELECT 1 FROM events WHERE match_id=? AND source_id=? AND sequence=? LIMIT 1",
                                         (match_id, source, event["sequence"])).fetchone()
            if position_exists and not prior_version:
                raise ValueError("SOURCE_SEQUENCE_IDENTITY_CONFLICT")
            w = watermarks.setdefault(source, {"first": event["sequence"], "last": event["sequence"],
                                               "positions": 0, "last_event_time": event["event_time"],
                                               "clock_regressed": False})
            out_of_order = event["sequence"] < w["last"]
            if event["sequence"] > w["last"]:
                w["clock_regressed"] = event["event_time"] < w["last_event_time"]
                w["last_event_time"] = max(w["last_event_time"], event["event_time"])
            w["first"], w["last"] = min(w["first"], event["sequence"]), max(w["last"], event["sequence"])
            w["positions"] += int(not position_exists)
            revision = previous["revision"] + 1
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (*key[:3], event["revision"], event["sequence"], revision, event["event_time"],
                        event["received_at"], digest, canonical(event)))
            reconciliation = (out_of_order or bool(prior_version) or event["event_type"] == "CORRECTION"
                              or previous["status"] == "FINISHED")
            if reconciliation:
                all_events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events WHERE match_id=? ORDER BY state_revision",
                                                                  (match_id,))]
                state = reduce_events(all_events, match_id, previous["source_mode"])
            else:
                state = apply_fact(previous, event)
            state["revision"], state["sequence_watermarks"] = revision, watermarks
            if any(v > 100 for v in state["score"].values()) or any(v > 4 for v in state["red_cards"].values()):
                raise ValueError("SPORT_STATE_OUTSIDE_IMPLEMENTED_RANGE")
            state["received_at"] = max(filter(None, (previous["received_at"], event["received_at"])))
            flags = []
            if not state["primary_source_id"]:
                flags.append("MISSING_KICKOFF")
            if any(v["last"] - v["first"] + 1 > v["positions"] for v in watermarks.values()):
                flags.append("MISSING_SEQUENCE")
            if any(v["clock_regressed"] for v in watermarks.values()):
                flags.append("PROVIDER_CLOCK_REGRESSION")
            if not state["connected"]:
                flags.append("SOURCE_DISCONNECTED")
            latency = (instant(event["received_at"]) - instant(event["event_time"])).total_seconds()
            if latency > 30:
                flags.append("LATE_EVENT")
            for source_id, score in state["source_scores"].items():
                if source_id == state["primary_source_id"]:
                    continue
                if score["minute"] < state["minute"]:
                    flags.append("STALE_SECONDARY_OBSERVATION")
                elif any(score[k] != state["score"][k] for k in ("home", "away")):
                    flags.append("PROVIDER_DISAGREEMENT")
            state["quality"] = {"status": "DEGRADED" if flags else "VALIDATED",
                                "flags": sorted(set(flags)), "freshness_seconds": 0,
                                "event_latency_seconds": latency,
                                "clock": "VIRTUAL_RECEIPT_CLOCK"}
            changed = semantic_state(previous) != semantic_state(state)
            reasons = []
            if changed:
                reasons.append("MODEL_INPUT_CHANGED")
            quality_changed = previous.get("quality", {}).get("flags", []) != state["quality"]["flags"]
            if quality_changed:
                reasons.append("DATA_QUALITY_CHANGED")
            if reconciliation:
                reasons.append("EVENT_HISTORY_RECONCILED")
            if not changed:
                reasons.append("SUPPORTED_MODEL_INPUT_UNCHANGED")
            decision = {"schema_version": "dragonhydra.relevance-decision/1", "event_id": event["event_id"],
                        "state_revision": revision, "action": "UPDATE_FORECAST" if changed or reconciliation or quality_changed else "STATE_ONLY",
                        "reason_codes": reasons, "relevance_score": 1.0 if changed else 0.0,
                        "score_kind": "MODEL_DEPENDENCY_HEURISTIC_NOT_PROBABILITY",
                        "expected_information_value": None, "information_value_state": "NOT_ESTIMATED",
                        "observation_novelty": "NEW_VERSION" if prior_version else "NEW_FACT",
                        "forecast_targets": ["FULL_TIME_RESULT", "NEXT_GOAL", "REMAINING_GOALS", "HORIZON_SCORE"] if changed else []}
            decision["computation_policy"] = "FULL_REFERENCE" if force_recompute else "INCREMENTAL"
            db.execute("UPDATE matches SET state=? WHERE match_id=?", (canonical(state), match_id))
            db.execute("INSERT INTO states VALUES(?,?,?)", (match_id, revision, canonical(state)))
            db.execute("INSERT INTO decisions(match_id,event_id,payload) VALUES(?,?,?)",
                       (match_id, event["event_id"], canonical(decision)))
            self.bump(db, "events_accepted")
            self.bump(db, "relevant_events" if decision["action"] == "UPDATE_FORECAST" else "irrelevant_events")
            if decision["action"] == "STATE_ONLY" and not force_recompute:
                self.bump(db, "expensive_calculations_avoided")
            if reconciliation:
                db.execute("INSERT OR IGNORE INTO invalidations SELECT forecast_id,?,'LATER_CORRECTION_OR_REORDERING' "
                           "FROM forecasts WHERE match_id=?", (revision, match_id))
                self.bump(db, "reconciliations")
            db.commit()
        return event, decision, state

    def append_forecast(self, wrapper):
        match_id, state_revision = wrapper["match_id"], wrapper["state_revision"]
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = json.loads(db.execute("SELECT state FROM matches WHERE match_id=?", (match_id,)).fetchone()[0])
            if state["revision"] != state_revision:
                self.bump(db, "obsolete_calculations_rejected")
                db.commit()
                return False
            old = db.execute("SELECT payload FROM forecasts WHERE forecast_id=?", (wrapper["forecast_id"],)).fetchone()
            if old:
                if old[0] != canonical(wrapper):
                    raise ValueError("FORECAST_IDENTITY_CONFLICT")
                return True
            db.execute("INSERT INTO forecasts VALUES(?,?,?,?,?)", (wrapper["forecast_id"], match_id,
                       wrapper["revision"], state_revision, canonical(wrapper)))
            db.execute("UPDATE matches SET current_forecast=? WHERE match_id=?", (wrapper["forecast_id"], match_id))
            self.bump(db, "forecast_updates")
            db.commit()
        return True

    def current_forecast(self, match_id):
        with self.connect() as db:
            row = db.execute("SELECT f.payload FROM matches m LEFT JOIN forecasts f ON f.forecast_id=m.current_forecast "
                             "WHERE m.match_id=?", (match_id,)).fetchone()
            return json.loads(row[0]) if row and row[0] else None

    def timeline(self, match_id, limit=200):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("HISTORY_LIMIT_INVALID")
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM forecasts WHERE match_id=? ORDER BY revision DESC LIMIT ?",
                              (match_id, limit)).fetchall()
            return [json.loads(r[0]) for r in reversed(rows)]

    def save_analysis(self, packet_id, match_id, result):
        with self.lock, self.connect() as db:
            previous = db.execute("SELECT payload FROM analyses WHERE packet_id=?", (packet_id,)).fetchone()
            if previous:
                return json.loads(previous[0])
            db.execute("INSERT INTO analyses VALUES(?,?,?)", (packet_id, match_id, canonical(result)))
            self.bump(db, "ai_investigations")
            db.commit()
        return result

    def analysis_intent(self, packet):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT payload FROM analyses WHERE packet_id=?", (packet["packet_id"],)).fetchone()
            if row:
                return "COMPLETED", json.loads(row[0])
            row = db.execute("SELECT payload FROM analysis_intents WHERE packet_id=?", (packet["packet_id"],)).fetchone()
            if row:
                return "UNRESOLVED", None
            db.execute("INSERT INTO analysis_intents VALUES(?,?,?)",
                       (packet["packet_id"], packet["match_id"], canonical(packet)))
            db.commit()
            return "NEW", None

    def analyses(self, match_id, limit=50):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM analyses WHERE match_id=? ORDER BY rowid DESC LIMIT ?",
                                                        (match_id, limit))]

    def get_replay(self, match_id, include_fixture=False):
        with self.connect() as db:
            row = db.execute("SELECT fixture,controls FROM replay WHERE match_id=?", (match_id,)).fetchone()
            if not row:
                return {"position": 0, "total": 0, "status": "NOT_CONFIGURED", "speed": 1}
            controls = json.loads(row[1])
            if include_fixture:
                controls["fixture"] = json.loads(row[0])
            return controls

    def set_replay(self, match_id, controls, fixture=None):
        with self.lock, self.connect() as db:
            if fixture is not None:
                if any(validate_event(e)["match_id"] != match_id for e in fixture):
                    raise ValueError("REPLAY_MATCH_SCOPE_INVALID")
                db.execute("INSERT INTO replay VALUES(?,?,?)", (match_id, canonical(fixture), canonical(controls)))
            else:
                db.execute("UPDATE replay SET controls=? WHERE match_id=?", (canonical(controls), match_id))
            db.commit()

    def meta(self, key, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute("INSERT INTO research_meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (key, canonical(value)))
                db.commit()
            row = db.execute("SELECT value FROM research_meta WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row and key != "identity" else None

    def save_experiment(self, report):
        key = identifier("virtual-experiment-", report)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO experiments VALUES(?,?)", (key, canonical(report)))
            db.commit()
        return {"experiment_id": key, **report}

    def latest_experiment(self):
        with self.connect() as db:
            row = db.execute("SELECT experiment_id,payload FROM experiments ORDER BY rowid DESC LIMIT 1").fetchone()
            return {"experiment_id": row[0], **json.loads(row[1])} if row else None
