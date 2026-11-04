"""Default optional archive storage; canonical core.sqlite3 is never modified here."""
from contextlib import contextmanager, closing
from pathlib import Path
import json
import sqlite3
from uuid import uuid4, UUID
from .base import StorageError, canonical, fingerprint, utc_now, validate_bundle

SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS research_schema(version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO research_schema VALUES(1);
CREATE TABLE IF NOT EXISTS research_archives(scope TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,
 hash TEXT NOT NULL,persisted_at TEXT NOT NULL,match_id TEXT NOT NULL,PRIMARY KEY(scope,id));
CREATE TRIGGER IF NOT EXISTS research_archives_no_update BEFORE UPDATE ON research_archives BEGIN SELECT RAISE(ABORT,'immutable research archive'); END;
CREATE TRIGGER IF NOT EXISTS research_archives_no_delete BEFORE DELETE ON research_archives BEGIN SELECT RAISE(ABORT,'immutable research archive'); END;
CREATE TABLE IF NOT EXISTS research_notes(scope TEXT NOT NULL,id TEXT NOT NULL,match_id TEXT NOT NULL,
 content TEXT NOT NULL,revision INTEGER NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(scope,id));
CREATE TABLE IF NOT EXISTS research_note_revisions(scope TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,
 content TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(scope,id,revision));
CREATE TRIGGER IF NOT EXISTS research_note_revisions_no_update BEFORE UPDATE ON research_note_revisions BEGIN SELECT RAISE(ABORT,'immutable note revision'); END;
CREATE TRIGGER IF NOT EXISTS research_note_revisions_no_delete BEFORE DELETE ON research_note_revisions BEGIN SELECT RAISE(ABORT,'immutable note revision'); END;
'''

class SQLiteResearchRepository:
    provider = 'sqlite'
    def __init__(self, path, scope):
        self.path, self.scope = Path(path), scope
        self.last_success_at = self.last_error = None

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            yield db;db.commit();self.last_success_at=utc_now();self.last_error=None
        except BaseException:
            db.rollback();raise
        finally:db.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(SCHEMA_SQL);db.commit()
        return {'provider':self.provider,'schema_version':1,'initialized':True}

    def health(self):
        if not self.path.exists():return {'provider':self.provider,'connected':False,'ready':False,'schema_version':None,'reason_code':'RESEARCH_SCHEMA_NOT_INITIALIZED','last_success_at':self.last_success_at,'last_error':self.last_error}
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
                db.execute('PRAGMA query_only=ON');version=db.execute('SELECT version FROM research_schema').fetchone()[0]
            return {'provider':self.provider,'connected':True,'ready':True,'schema_version':version,'last_success_at':self.last_success_at,'last_error':self.last_error}
        except sqlite3.Error:
            return {'provider':self.provider,'connected':False,'ready':False,'schema_version':None,'reason_code':'RESEARCH_STORAGE_UNAVAILABLE','last_success_at':self.last_success_at,'last_error':'SQLITE_READ_FAILED'}

    def save(self,bundle):
        validate_bundle(bundle);digest=fingerprint(bundle)
        with self.transaction() as db:
            old=db.execute('SELECT payload,hash,persisted_at FROM research_archives WHERE scope=? AND id=?',(self.scope,bundle['archive_id'])).fetchone()
            if old:
                if old[1]!=digest:raise StorageError('RESEARCH_IDEMPOTENCY_CONFLICT')
                stamp=old[2]
            else:
                stamp=utc_now();db.execute('INSERT INTO research_archives VALUES(?,?,?,?,?,?)',
                    (self.scope,bundle['archive_id'],canonical(bundle).decode(),digest,stamp,bundle['match_id']))
        return dict(provider=self.provider,archive_id=bundle['archive_id'],payload_sha256=digest,persisted_at=stamp,duplicate=bool(old))

    def get(self,archive_id):
        if not self.path.exists():return None
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            row=db.execute('SELECT payload,hash,persisted_at FROM research_archives WHERE scope=? AND id=?',(self.scope,archive_id)).fetchone()
        return None if row is None else {'archive':json.loads(row[0]),'storage':dict(provider=self.provider,archive_id=archive_id,payload_sha256=row[1],persisted_at=row[2])}

    def history(self,match_id,limit=50):
        if type(limit) is not int or not 1<=limit<=100:raise StorageError('INVALID_RESEARCH_LIMIT')
        if not self.path.exists():return []
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            rows=db.execute('SELECT id FROM research_archives WHERE scope=? AND match_id=? ORDER BY persisted_at,id LIMIT ?',(self.scope,match_id,limit)).fetchall()
        return [self.get(row[0]) for row in rows]

    def create_note(self,match_id,text,note_id=None):
        note_id=str(UUID(note_id)) if note_id else str(uuid4());self._text(text)
        with self.transaction() as db:
            stamp=utc_now();db.execute('INSERT INTO research_notes VALUES(?,?,?,?,?,?)',(self.scope,note_id,match_id,text,1,stamp))
            db.execute('INSERT INTO research_note_revisions VALUES(?,?,?,?,?)',(self.scope,note_id,1,text,stamp))
        return dict(note_id=note_id,match_id=match_id,text=text,revision=1,updated_at=stamp)

    @staticmethod
    def _text(text):
        if not isinstance(text,str) or not 1<=len(text)<=4000:raise StorageError('INVALID_RESEARCH_NOTE')

    def update_note(self,note_id,text,expected_revision):
        self._text(text)
        if type(expected_revision) is not int or expected_revision<1:raise StorageError('INVALID_NOTE_REVISION')
        with self.transaction() as db:
            stamp=utc_now();result=db.execute('UPDATE research_notes SET content=?,revision=revision+1,updated_at=? WHERE scope=? AND id=? AND revision=?',
                (text,stamp,self.scope,note_id,expected_revision))
            if result.rowcount!=1:raise StorageError('RESEARCH_NOTE_REVISION_CONFLICT')
            db.execute('INSERT INTO research_note_revisions VALUES(?,?,?,?,?)',(self.scope,note_id,expected_revision+1,text,stamp))
        return next(row for row in self.notes(None) if row['note_id']==note_id)

    def notes(self,match_id):
        if not self.path.exists():return []
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            rows=db.execute('SELECT id,match_id,content,revision,updated_at FROM research_notes WHERE scope=? AND (? IS NULL OR match_id=?) ORDER BY updated_at,id',(self.scope,match_id,match_id)).fetchall()
        return [dict(note_id=r[0],match_id=r[1],text=r[2],revision=r[3],updated_at=r[4]) for r in rows]
