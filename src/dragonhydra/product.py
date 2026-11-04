"""Application services for the product UI; existing research modules remain owners.

This increment deliberately uses an explicit SQLite backend in a separate product
state directory. It never changes authority or copies the existing research DB.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

from . import public_results, market_store
from .cognition import models
from .build_meta import VERSION

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
from .domain import API, now, identity






class Product:
    def __init__(self, state: Path, source_root: Path = ROOT, *, kernel_config=None, engine_adapters=None, research_settings=None):
        self.state = Path(state).resolve()
        self.source_root = Path(source_root).resolve()
        packaged = Path(__file__).parent / 'resources'
        if self.source_root == ROOT and (packaged / 'data' / 'raw').is_dir():
            self.source_root = packaged
        self.state.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state / 'core.sqlite3'
        with closing(self.connect()) as db:
            db.execute('PRAGMA journal_mode=WAL')
            public_results._schema(db)
            db.commit()
        self.exports = self.state / 'exports'
        self.exports.mkdir(exist_ok=True)
        from .connectors.store import Store
        self.connector_store = Store(self)
        from .kernel.composition import Kernel
        from .kernel.ports import ApplicationContext, StoragePort
        from .research_storage import configured_repository
        scope = (kernel_config.get('installation_id') if isinstance(kernel_config,dict)
                 else getattr(kernel_config,'installation_id',None))
        scope = scope or 'core-next-source-'+hashlib.sha256(str(self.state).encode()).hexdigest()[:16]
        self.research = configured_repository(self.state,scope,research_settings)
        context = ApplicationContext(StoragePort(self.state, self.db_path, self.source_root, self.exports, self.connect),
                                     self.connector_store, lambda: now(), self.research)
        self.kernel = Kernel(context, config=kernel_config, adapters=engine_adapters)

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def rows(self):
        return self.kernel.execute('data', 'rows')

    def match_id(self, row):
        return self.kernel.execute('data', 'match_id', row)

    def competition_id(self, row):
        return self.kernel.execute('data', 'competition_id', row)

    def team_id(self, row, name):
        return self.kernel.execute('data', 'team_id', row, name)

    def present(self, row):
        return self.kernel.execute('data', 'present', row)

    def find(self, match_id):
        return self.kernel.execute('data', 'find', match_id)

    def matches(self, *, date=None, status=None, competition=None, provider=None, search='', limit=50, offset=0):
        return self.kernel.execute('data', 'matches', date=date, status=status, competition=competition, provider=provider, search=search, limit=limit, offset=offset)

    def competitions(self):
        return self.kernel.execute('data', 'competitions')

    def team(self, team_id):
        return self.kernel.execute('data', 'team', team_id)

    def standings(self, competition_id):
        return self.kernel.execute('data', 'standings', competition_id)

    def predictions(self, match_id):
        return self.kernel.execute('prediction', 'predictions', match_id)

    def explanation(self, match_id):
        return self.kernel.execute('ai', 'explanation', match_id)

    def evidence(self, evidence_id):
        return self.kernel.execute('data', 'evidence', evidence_id)

    def odds(self, match_id, history=False):
        return self.kernel.execute('odds', 'odds', match_id, history)
