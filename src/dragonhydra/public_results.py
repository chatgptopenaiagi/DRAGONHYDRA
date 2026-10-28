"""OpenFootball local historical fixture import with immutable source provenance.

Event dates and any source-provided local times are retained without inventing a
UTC kickoff. Historical records become usable at this system's import, not at
their event dates. A source capture receipt is preserved as supplied metadata.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

ADAPTER_VERSION = 'openfootball-json/1'


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _utc(value):
    if not isinstance(value, str):
        raise ValueError('TIMESTAMP_REQUIRED')
    try:
        x = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('INVALID_TIMESTAMP') from None
    if x.tzinfo is None or x.utcoffset() is None:
        raise ValueError('NAIVE_TIMESTAMP')
    return x.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _need(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('MISSING_' + name.upper())
    return value.strip()


def _schema(db):
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS raw_sources (source_hash TEXT PRIMARY KEY, bytes BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS public_result_captures (
      source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL, source_hash TEXT NOT NULL REFERENCES raw_sources(source_hash),
      source_url TEXT NOT NULL, received_at TEXT NOT NULL, source_capture_at TEXT, receipt_json TEXT,
      PRIMARY KEY(source_id, acquisition_id));
    CREATE TABLE IF NOT EXISTS public_result_receipts (
      source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL, persisted_at TEXT NOT NULL, usable_at TEXT NOT NULL,
      PRIMARY KEY(source_id, acquisition_id), FOREIGN KEY(source_id,acquisition_id) REFERENCES public_result_captures(source_id,acquisition_id));
    CREATE TABLE IF NOT EXISTS public_fixture_records (
      source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL, ordinal INTEGER NOT NULL, fixture_key TEXT NOT NULL,
      payload TEXT NOT NULL, PRIMARY KEY(source_id,acquisition_id,ordinal),
      FOREIGN KEY(source_id,acquisition_id) REFERENCES public_result_captures(source_id,acquisition_id));
    CREATE TABLE IF NOT EXISTS public_fixture_quarantine (
      source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL, ordinal INTEGER NOT NULL, reason TEXT NOT NULL,
      PRIMARY KEY(source_id,acquisition_id,ordinal),
      FOREIGN KEY(source_id,acquisition_id) REFERENCES public_result_captures(source_id,acquisition_id));
    CREATE TRIGGER IF NOT EXISTS public_raw_immutable_update BEFORE UPDATE ON raw_sources BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS public_raw_immutable_delete BEFORE DELETE ON raw_sources BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS public_capture_immutable_update BEFORE UPDATE ON public_result_captures BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS public_capture_immutable_delete BEFORE DELETE ON public_result_captures BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS public_receipt_immutable_update BEFORE UPDATE ON public_result_receipts BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS public_receipt_immutable_delete BEFORE DELETE ON public_result_receipts BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS public_fixture_immutable_update BEFORE UPDATE ON public_fixture_records BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS public_fixture_immutable_delete BEFORE DELETE ON public_fixture_records BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS public_quarantine_immutable_update BEFORE UPDATE ON public_fixture_quarantine BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS public_quarantine_immutable_delete BEFORE DELETE ON public_fixture_quarantine BEGIN SELECT RAISE(ABORT,'immutable'); END;
    ''')


def _read_score(value):
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get('ft')
        if value is None:
            return None
    if not isinstance(value, list) or len(value) != 2 or any(type(x) is not int or x < 0 for x in value):
        raise ValueError('INVALID_FULL_TIME_SCORE')
    return value


def _match(competition, item, ordinal):
    if not isinstance(item, dict):
        raise ValueError('INVALID_MATCH')
    day = _need(item.get('date'), 'date')
    try:
        date.fromisoformat(day)
    except ValueError:
        raise ValueError('INVALID_EVENT_DATE') from None
    home, away = _need(item.get('team1'), 'home'), _need(item.get('team2'), 'away')
    if home.casefold() == away.casefold():
        raise ValueError('AMBIGUOUS_PARTICIPANTS')
    raw_time = item.get('time')
    if raw_time is not None:
        if not isinstance(raw_time, str) or not re.fullmatch(r'\d{2}:\d{2}', raw_time):
            raise ValueError('INVALID_SOURCE_TIME')
        hours, minutes = map(int, raw_time.split(':'))
        if hours > 23 or minutes > 59:
            raise ValueError('INVALID_SOURCE_TIME')
    score = _read_score(item.get('score'))
    identity = [competition, day, home, away]
    return {'fixture_key': _hash(_canonical(identity)), 'source_record_path': '$.matches[' + str(ordinal) + ']',
            'competition': competition, 'event_date': day, 'source_local_time': raw_time,
            'event_at_utc': None, 'timezone': None, 'home': home, 'away': away,
            'market_type': '1x2', 'period': 'full_time', 'settlement': 'source_full_time',
            'home_goals': None if score is None else score[0], 'away_goals': None if score is None else score[1],
            'outcome': None if score is None else ('home' if score[0] > score[1] else 'away' if score[1] > score[0] else 'draw'),
            'result_state': 'available' if score is not None else 'unavailable',
            'transformation': {'version': ADAPTER_VERSION, 'formula': 'full-time score comparison; event date is not a knowledge timestamp'}}


def ingest_bytes(db, raw, *, source_id, source_url, acquisition_id=None, source_receipt=None):
    """Persist raw bytes and accepted matches, then append commit-acknowledged receipt."""
    _need(source_id, 'source_id')
    _need(source_url, 'source_url')
    if not isinstance(raw, bytes):
        raise ValueError('RAW_BYTES_REQUIRED')
    captured_at = _now()
    fingerprint = _hash(raw)
    acquisition_id = _need(acquisition_id or uuid4().hex, 'acquisition_id')
    try:
        doc = json.loads(raw.decode('utf-8-sig'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('INVALID_JSON') from None
    if not isinstance(doc, dict) or not isinstance(doc.get('matches'), list):
        raise ValueError('OPENFOOTBALL_MATCHES_REQUIRED')
    competition = _need(doc.get('name'), 'competition')
    source_capture_at = None
    if source_receipt is not None:
        if not isinstance(source_receipt, dict) or source_receipt.get('sha256') != fingerprint or source_receipt.get('source_url') != source_url:
            raise ValueError('CAPTURE_RECEIPT_MISMATCH')
        if source_receipt.get('source_id') != source_id:
            raise ValueError('CAPTURE_RECEIPT_MISMATCH')
        if source_receipt.get('bytes') != len(raw):
            raise ValueError('CAPTURE_RECEIPT_MISMATCH')
        if source_receipt.get('captured_at') is not None:
            source_capture_at = _utc(source_receipt['captured_at'])
            if source_capture_at > captured_at:
                raise ValueError('CAPTURE_AFTER_RECEIPT')
    _schema(db)
    old = db.execute('SELECT source_hash, source_url FROM public_result_captures WHERE source_id=? AND acquisition_id=?', (source_id, acquisition_id)).fetchone()
    if old:
        if old != (fingerprint, source_url):
            raise ValueError('ACQUISITION_ID_COLLISION')
        receipt = db.execute('SELECT usable_at FROM public_result_receipts WHERE source_id=? AND acquisition_id=?', (source_id, acquisition_id)).fetchone()
        if receipt is None:
            ack = _now()
            db.execute('INSERT INTO public_result_receipts VALUES(?,?,?,?)', (source_id, acquisition_id, ack, ack))
            db.commit()
            receipt = (ack,)
        return {'acquisition_id': acquisition_id, 'source_hash': fingerprint, 'duplicate': True,
                'usable_at': receipt[0], 'inserted': 0, 'quarantined': 0}
    valid, bad, seen = [], [], set()
    for ordinal, item in enumerate(doc['matches']):
        try:
            row = _match(competition, item, ordinal)
            if row['fixture_key'] in seen:
                raise ValueError('AMBIGUOUS_DUPLICATE_FIXTURE')
            seen.add(row['fixture_key'])
            valid.append((ordinal, row))
        except (ValueError, TypeError) as exc:
            bad.append((ordinal, str(exc)))
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO raw_sources(source_hash,bytes) VALUES(?,?)', (fingerprint, raw))
        db.execute('INSERT INTO public_result_captures VALUES(?,?,?,?,?,?,?)',
                   (source_id, acquisition_id, fingerprint, source_url, captured_at, source_capture_at,
                    None if source_receipt is None else _canonical(source_receipt).decode('utf-8')))
        db.executemany('INSERT INTO public_fixture_records VALUES(?,?,?,?,?)',
                       [(source_id, acquisition_id, i, x['fixture_key'], _canonical(x).decode('utf-8')) for i,x in valid])
        db.executemany('INSERT INTO public_fixture_quarantine VALUES(?,?,?,?)',
                       [(source_id, acquisition_id, i, reason) for i,reason in bad])
        db.commit()
        ack = _now()
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO public_result_receipts VALUES(?,?,?,?)', (source_id, acquisition_id, ack, ack))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'acquisition_id': acquisition_id, 'source_hash': fingerprint, 'duplicate': False,
            'received_at': captured_at, 'persisted_at': ack, 'usable_at': ack,
            'inserted': len(valid), 'result_count': sum(x['outcome'] is not None for _,x in valid),
            'quarantined': len(bad), 'clock_mode': 'operational'}


def import_file(db_path, path, *, source_id, source_url, acquisition_id=None, receipt_path=None):
    raw = Path(path).read_bytes()
    receipt = json.loads(Path(receipt_path).read_text(encoding='utf-8-sig')) if receipt_path else None
    with closing(sqlite3.connect(str(db_path), timeout=10)) as db:
        return ingest_bytes(db, raw, source_id=source_id, source_url=source_url,
                            acquisition_id=acquisition_id, source_receipt=receipt)


def as_of(db, cutoff):
    cutoff = _utc(cutoff)
    _schema(db)
    rows = db.execute('''SELECT f.payload, f.ordinal, c.source_id, c.acquisition_id, c.source_hash,
        c.source_url, c.received_at, c.source_capture_at, r.persisted_at, r.usable_at
        FROM public_fixture_records f JOIN public_result_captures c USING(source_id,acquisition_id)
        JOIN public_result_receipts r USING(source_id,acquisition_id)
        WHERE c.received_at <= ? AND r.persisted_at <= ? AND r.usable_at <= ?
        ORDER BY c.source_id,c.acquisition_id,f.ordinal''', (cutoff,cutoff,cutoff)).fetchall()
    result = []
    for payload, ordinal, source, acquisition, source_hash, url, received, source_capture, persisted, usable in rows:
        row = json.loads(payload)
        evidence_id = _hash(_canonical([source, acquisition, ordinal]))
        row.update(evidence_id=evidence_id, source_id=source, acquisition_id=acquisition,
                   source_hash=source_hash, source_url=url, adapter_version=ADAPTER_VERSION,
                   data_origin='imported_historical', source_published_at=None, source_capture_at=source_capture,
                   received_at=received, persisted_at=persisted, usable_at=usable)
        result.append(row)
    return result


def get_as_of(db_path, cutoff):
    with closing(sqlite3.connect(str(db_path), timeout=10)) as db:
        return as_of(db, cutoff)


def latest(db, cutoff):
    """Return the latest eligible revision per source and normalized fixture key.

    Original immutable observations remain accessible through get_as_of; a later
    correction cannot alter a replay before the correction's usable time.
    """
    latest = {}
    for row in as_of(db, cutoff):
        key = (row['source_id'], row['fixture_key'])
        order = (row['usable_at'], row['acquisition_id'])
        if key not in latest or order > latest[key][0]:
            latest[key] = (order, row)
    return [latest[key][1] for key in sorted(latest)]


def latest_as_of(db_path, cutoff):
    with closing(sqlite3.connect(str(db_path), timeout=10)) as db:
        return latest(db, cutoff)


def summarize(db, cutoff, *, source_id=None):
    """Descriptive score counts from latest eligible result revisions."""
    from decimal import Decimal, localcontext
    rows = latest(db, cutoff)
    if source_id is not None:
        rows = [row for row in rows if row['source_id'] == source_id]
    date_flags = find_ambiguous_fixtures(rows, cutoff)
    date_blocked = {key for flag in date_flags for key in flag['fixture_keys']}
    candidates = [row for row in rows if row['outcome'] in ('home', 'draw', 'away')
                  and row['fixture_key'] not in date_blocked]
    grouped = {}
    for row in candidates:
        grouped.setdefault(row['fixture_key'], []).append(row)
    # Matching text labels alone do not establish an approved cross-source mapping.
    ambiguous = [group for group in grouped.values() if len({row['source_id'] for row in group}) > 1]
    blocked = {row['fixture_key'] for group in ambiguous for row in group}
    eligible = [row for row in candidates if row['fixture_key'] not in blocked]
    flags = date_flags + [{'code':'AMBIGUOUS_CROSS_SOURCE_FIXTURE',
              'source_ids':sorted({row['source_id'] for row in group}),
              'evidence_ids':sorted(row['evidence_id'] for row in group)} for group in ambiguous]
    ids = sorted(row['evidence_id'] for row in eligible)
    transform = {'version': ADAPTER_VERSION, 'formula': 'count eligible full-time outcomes'}
    counts = {outcome: {'value': sum(row['outcome'] == outcome for row in eligible),
                        'evidence_ids': ids, 'transformation': transform}
              for outcome in ('home', 'draw', 'away')}
    with localcontext() as ctx:
        ctx.prec = 34
        proportions = {outcome: {'value': str(Decimal(counts[outcome]['value']) / len(eligible)) if eligible else None,
                                 'evidence_ids': ids, 'reason': None if eligible else 'NO_ELIGIBLE_RESULTS',
                                 'transformation': {'version': ADAPTER_VERSION,
                                                    'formula': 'outcome count / eligible result count'}}
                       for outcome in counts}
    return {'cutoff': _utc(cutoff), 'evidence_manifest': rows,
            'eligible_result_count': {'value': len(eligible), 'evidence_ids': ids, 'transformation': transform},
            'counts': counts, 'proportions': proportions, 'quality_flags': flags,
            'interpretation': 'Descriptive frequencies of eligible observations, not a calibrated forecast.'}


def summarize_as_of(db_path, cutoff, *, source_id=None):
    with closing(sqlite3.connect(str(db_path), timeout=10)) as db:
        return summarize(db, cutoff, source_id=source_id)




def find_ambiguous_fixtures(rows, cutoff):
    """Identify date conflicts without assuming rescheduling or a repeat fixture.

    Only cutoff-eligible records participate. Exact source, competition, home and
    away labels are grouped; multiple dates require explicit mapping evidence.
    """
    if not isinstance(rows, list):
        raise ValueError('RECORD_LIST_REQUIRED')
    limit = _utc(cutoff)
    grouped = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            received, persisted, usable = (_utc(row.get(k)) for k in ('received_at','persisted_at','usable_at'))
            published = row.get('source_published_at',row.get('published_at'))
            if published is not None and _utc(published) > received:
                continue
        except ValueError:
            continue
        if not received <= persisted <= usable <= limit:
            continue
        keys = ('source_id','competition','home','away','event_date','acquisition_id','fixture_key','evidence_id')
        if any(not isinstance(row.get(k),str) or not row[k].strip() for k in keys):
            continue
        try:
            day = date.fromisoformat(row['event_date']).isoformat()
        except ValueError:
            continue
        identity = tuple(row[k] for k in ('source_id','competition','home','away'))
        grouped.setdefault(identity, []).append((day,row))
    result=[]
    for identity, records in sorted(grouped.items()):
        dates=sorted({day for day,_ in records})
        if len(dates) < 2:
            continue
        result.append({'code':'AMBIGUOUS_FIXTURE_DATE',
                       'source_id':identity[0], 'competition':identity[1],
                       'home':identity[2], 'away':identity[3], 'event_dates':dates,
                       'fixture_keys':sorted({r['fixture_key'] for _,r in records}),
                       'acquisition_ids':sorted({r['acquisition_id'] for _,r in records}),
                       'evidence_ids':sorted({r['evidence_id'] for _,r in records}),
                       'reason':'Different dates may represent rescheduling or separate fixtures; identity mapping is unresolved.'})
    return result


def ambiguous_fixtures_as_of(db_path, cutoff):
    return find_ambiguous_fixtures(latest_as_of(db_path, cutoff), cutoff)


