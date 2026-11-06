"""Owned synthetic SQLite evidence; decisions/models/outcomes are append-only."""
from __future__ import annotations
from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3
import threading

from ..realtime.events import canonical

IDENTITY = "dragonhydra.future-relevance-journal/1"
DDL = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS episodes(episode_id TEXT PRIMARY KEY,descriptor TEXT NOT NULL,view TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(decision_id TEXT PRIMARY KEY,episode_id TEXT NOT NULL,
 request_id TEXT UNIQUE NOT NULL,request_hash TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS acquisitions(acquisition_id TEXT PRIMARY KEY,decision_id TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS predictions(prediction_id TEXT PRIMARY KEY,decision_id TEXT NOT NULL,stage TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evaluations(evaluation_id TEXT PRIMARY KEY,decision_id TEXT UNIQUE NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS models(model_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS experiments(experiment_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
"""


class Journal:
    def __init__(self, directory):
        self.directory = Path(directory).absolute()
        if ".." in self.directory.parts:
            raise ValueError("FUTURE_PARENT_PATH_REJECTED")
        for path in (self.directory, *self.directory.parents):
            if path.exists() and (path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0)&0x400):
                raise ValueError("FUTURE_REPARSE_PATH_REJECTED")
        self.path = self.directory/"future-relevance.sqlite3"
        if self.directory.exists():
            for item in self.directory.iterdir():
                if item.name not in (self.path.name, self.path.name+"-journal", self.path.name+"-wal", self.path.name+"-shm"):
                    raise ValueError("FUTURE_FOREIGN_DIRECTORY_REJECTED")
                if item.is_symlink() or getattr(item.lstat(), "st_file_attributes", 0)&0x400:
                    raise ValueError("FUTURE_REPARSE_PATH_REJECTED")
        if self.path.exists():
            try:
                with closing(sqlite3.connect(self.path.as_uri()+"?mode=ro&immutable=1", uri=True)) as db:
                    row = db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
                    if not row or row[0] != canonical(IDENTITY):
                        raise ValueError("FUTURE_FOREIGN_DATABASE_REJECTED")
            except sqlite3.DatabaseError:
                raise ValueError("FUTURE_FOREIGN_DATABASE_REJECTED") from None
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript(DDL)
            db.execute("INSERT OR IGNORE INTO meta VALUES('identity',?)", (canonical(IDENTITY),))
            db.execute("INSERT OR IGNORE INTO meta VALUES('acquisition_spent','0.0')")
            for table in ("decisions", "acquisitions", "predictions", "evaluations", "models", "experiments"):
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'IMMUTABLE_FUTURE_EVIDENCE'); END")
            db.commit()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def metadata(db, key, default=None):
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def put_meta(db, key, value):
        db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, canonical(value)))

    @staticmethod
    def items(db, table, *, episode_id=None, limit=200):
        if table not in ("decisions", "acquisitions", "predictions", "evaluations", "models", "experiments"):
            raise ValueError("FUTURE_JOURNAL_TABLE_INVALID")
        clause, values = (" WHERE episode_id=?", [episode_id]) if episode_id is not None and table == "decisions" else ("", [])
        rows = db.execute(f"SELECT payload FROM {table}{clause} ORDER BY rowid DESC LIMIT ?", (*values, limit)).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]
