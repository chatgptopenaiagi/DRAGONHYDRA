"""Immutable storage for local probability assumptions and their source bytes."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from .market_store import utc


def now():
    return utc(datetime.now(timezone.utc))


def _connect(path):
    conn = sqlite3.connect(str(path), timeout=10)
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS estimate_sources (source_hash TEXT PRIMARY KEY, raw BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS estimate_receipts (
        source_hash TEXT NOT NULL, clock_mode TEXT NOT NULL, received_at TEXT NOT NULL,
        persisted_at TEXT NOT NULL, usable_at TEXT NOT NULL, PRIMARY KEY(source_hash,clock_mode));
    CREATE TRIGGER IF NOT EXISTS estimate_sources_no_update BEFORE UPDATE ON estimate_sources BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS estimate_sources_no_delete BEFORE DELETE ON estimate_sources BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS estimate_receipts_no_update BEFORE UPDATE ON estimate_receipts BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS estimate_receipts_no_delete BEFORE DELETE ON estimate_receipts BEGIN SELECT RAISE(ABORT,'immutable'); END;
    ''')
    return conn


def import_estimate(db_path, path, *, simulated=False):
    raw = Path(path).read_bytes()
    captured = now()
    payload = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(payload, dict):
        raise ValueError('estimate must be a JSON object')
    if simulated and payload.get('data_origin') != 'synthetic':
        raise ValueError('simulated clock is allowed only for synthetic data')
    digest = hashlib.sha256(raw).hexdigest()
    mode = 'synthetic_simulated' if simulated else 'operational'
    with closing(_connect(db_path)) as db:
        db.execute('INSERT OR IGNORE INTO estimate_sources VALUES(?,?)', (digest, raw))
        db.commit()
        ack = now()
        if simulated:
            captured = utc(payload['received_at'])
            persisted = utc(payload['persisted_at'])
            usable = utc(payload['usable_at'])
            if not captured <= persisted <= usable:
                raise ValueError('invalid estimate availability')
        else:
            persisted = usable = ack
        db.execute('INSERT OR IGNORE INTO estimate_receipts VALUES(?,?,?,?,?)', (digest,mode,captured,persisted,usable))
        db.commit()
    return {'source_hash': digest, 'clock_mode': mode}


def get_estimate(db_path, source_hash, cutoff, *, simulated=False):
    mode = 'synthetic_simulated' if simulated else 'operational'
    with closing(_connect(db_path)) as db:
        row = db.execute('''SELECT s.raw,r.received_at,r.persisted_at,r.usable_at FROM estimate_sources s
            JOIN estimate_receipts r ON s.source_hash=r.source_hash
            WHERE s.source_hash=? AND r.clock_mode=? AND r.usable_at<=?''',
            (source_hash,mode,utc(cutoff))).fetchone()
    if row is None:
        return None
    raw,received,persisted,usable=row
    payload=json.loads(bytes(raw).decode('utf-8-sig'))
    payload.update(source_hash=source_hash,received_at=received,persisted_at=persisted,usable_at=usable)
    payload['source_raw']=bytes(raw).decode('utf-8')
    if simulated:
        for item in payload.get('input_evidence', []):
            item['source_hash']=source_hash
            item['source_raw']=payload['source_raw']
    else:
        # An imported file can express a subjective assumption, but cannot
        # establish historical model lineage merely by asserting old timestamps.
        payload.update(data_origin='user_supplied', input_evidence=[], source_published_at=None)
        payload.setdefault('model_version','user-assumption/1')
        payload.setdefault('source_id','local-user-estimate')
        payload.setdefault('evidence_id','estimate:'+source_hash)
    return payload
