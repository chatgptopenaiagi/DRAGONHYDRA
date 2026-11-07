"""Owned SQLite current views plus immutable operational and research evidence."""
from contextlib import contextmanager,closing
from pathlib import Path
import sqlite3
from .contracts import canonical

TABLES=('decisions','acquisitions','forecasts','events','outcomes','evaluations','analyses','models','experiments')
IDENTITY='dragonhydra.logistics-journal/1'

class Journal:
    def __init__(self,directory):
        self.directory=Path(directory).absolute();self.path=self.directory/'cognitive-logistics.sqlite3'
        for p in (self.path,*self.path.parents):
            if p.exists() and (p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&0x400):raise ValueError('LOGISTICS_REPARSE_STATE_REJECTED')
        if self.path.exists():
            try:
                with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
                    row=db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
                    if not row or row[0]!=canonical(IDENTITY):raise ValueError('LOGISTICS_FOREIGN_DATABASE_REJECTED')
            except sqlite3.DatabaseError:raise ValueError('LOGISTICS_FOREIGN_DATABASE_REJECTED') from None
        elif self.directory.exists() and any(self.directory.iterdir()):raise ValueError('LOGISTICS_FOREIGN_DIRECTORY_REJECTED')
        self.directory.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY,world TEXT NOT NULL,sha256 TEXT NOT NULL,view TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,payload TEXT NOT NULL)')
            for table in TABLES:
                db.execute(f'CREATE TABLE IF NOT EXISTS {table}(id TEXT PRIMARY KEY,episode_id TEXT,payload TEXT NOT NULL)')
                for action in ('UPDATE','DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'IMMUTABLE_LOGISTICS_EVIDENCE'); END")
            for action in ('UPDATE','DELETE'):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_requests_{action} BEFORE {action} ON requests BEGIN SELECT RAISE(ABORT,'IMMUTABLE_LOGISTICS_REQUEST'); END")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS evaluation_decision_identity ON evaluations(json_extract(payload,'$.decision_id'))")
            db.execute('CREATE INDEX IF NOT EXISTS decision_episode_identity ON decisions(episode_id)')
            db.execute("INSERT OR IGNORE INTO meta VALUES('identity',?)",(canonical(IDENTITY),));db.commit()
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()
    @staticmethod
    def meta(db,key,default=None):
        import json
        row=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    @staticmethod
    def put_meta(db,key,value):db.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,canonical(value)))
    @staticmethod
    def insert(db,table,key,payload,episode_id=None):
        if table not in TABLES:raise ValueError('LOGISTICS_JOURNAL_TABLE_INVALID')
        encoded=canonical(payload);old=db.execute(f'SELECT payload FROM {table} WHERE id=?',(key,)).fetchone()
        if old:
            if old[0]!=encoded:raise ValueError('LOGISTICS_IMMUTABLE_ID_CONFLICT')
            return False
        db.execute(f'INSERT INTO {table} VALUES(?,?,?)',(key,episode_id,encoded));return True
    @staticmethod
    def items(db,table,episode_id=None,limit=200):
        import json
        if table not in TABLES or type(limit) is not int or not 1<=limit<=20000:raise ValueError('LOGISTICS_JOURNAL_QUERY_INVALID')
        where,args=(' WHERE episode_id=?',[episode_id]) if episode_id else ('',[])
        rows=db.execute(f'SELECT payload FROM {table}{where} ORDER BY rowid DESC LIMIT ?',(*args,limit)).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]
