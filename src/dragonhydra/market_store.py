"""Local append-only market observations and point-in-time retrieval.

Raw source bytes are retained in SQLite. For operational imports, source-supplied
capture/persistence clocks are never trusted: receipt is the actual file read and
persistence is the UTC acknowledgment of the completed first transaction. A
separate immutable receipt gates replay. Synthetic simulated clocks are opt-in.
"""
from __future__ import annotations

from contextlib import closing
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3

ADAPTER_VERSION = 'local-market-snapshot/1'


def utc(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('invalid timestamp') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timestamp must be timezone-aware')
    return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _now():
    return utc(datetime.now(timezone.utc))


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _required(item, key):
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError('missing ' + key)
    return value.strip()


def _decimal(value):
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError('invalid number')
        parsed = Decimal(str(value))
        if not parsed.is_finite():
            raise ValueError('non-finite number')
        return parsed
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('invalid number') from exc


def _validate_price(original, form):
    if not isinstance(original, str) or not original.strip():
        raise ValueError('missing original odds')
    form = str(form).lower().strip()
    if form == 'decimal':
        if _decimal(original) <= 1:
            raise ValueError('invalid decimal odds')
    elif form == 'american':
        value = _decimal(original)
        if value != value.to_integral_value() or abs(value) < 100:
            raise ValueError('invalid American odds')
    elif form == 'fractional':
        match = re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*', original)
        if not match or int(match.group(1)) <= 0 or int(match.group(2)) <= 0:
            raise ValueError('invalid fractional odds')
    else:
        raise ValueError('unknown odds format')
    return original, form


def _snapshots(raw, suffix):
    if suffix.lower() == '.json':
        def invalid_constant(value):
            raise ValueError('non-finite JSON')
        value = json.loads(raw.decode('utf-8-sig'), parse_float=str, parse_int=str, parse_constant=invalid_constant)
        value = value.get('snapshots') if isinstance(value, dict) else value
        if not isinstance(value, list):
            raise ValueError('JSON must contain a snapshots list')
        return value
    if suffix.lower() == '.csv':
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError('invalid CSV header')
        grouped = {}
        for original in reader:
            if None in original:
                raise ValueError('invalid CSV row')
            row = dict(original)
            quote = {k: row.pop(k, '') for k in ('outcome', 'odds_original', 'odds_format')}
            key = (row.get('source_id'), row.get('acquisition_id'))
            if key not in grouped:
                grouped[key] = (row, [])
            elif grouped[key][0] != row:
                raise ValueError('inconsistent CSV snapshot metadata')
            grouped[key][1].append(quote)
        return [dict(meta, quotes=quotes) for meta, quotes in grouped.values()]
    raise ValueError('expected JSON or CSV')


def _normalize(item, captured_at, simulated):
    if not isinstance(item, dict):
        raise ValueError('snapshot must be an object')
    if item.get('ambiguous_mapping') not in (None, False, '', 'false', 'False', '0'):
        raise ValueError('ambiguous entity mapping')
    names = ('source_id', 'provider_id', 'adapter_version', 'acquisition_id', 'data_origin',
             'event_id', 'competition', 'home', 'away', 'market_type', 'period', 'status', 'settlement')
    result = {name: _required(item, name) for name in names}
    if result['data_origin'] not in ('synthetic', 'captured_real', 'imported_historical'):
        raise ValueError('invalid data origin')
    if simulated and result['data_origin'] != 'synthetic':
        raise ValueError('simulated clock is allowed for synthetic evidence only')
    if result['home'].casefold() == result['away'].casefold():
        raise ValueError('ambiguous participants')
    if result['status'] not in ('pregame', 'live', 'unknown'):
        raise ValueError('invalid event status')
    result['feed_id'] = item.get('feed_id') or None
    if result['feed_id'] is not None and not isinstance(result['feed_id'], str):
        raise ValueError('invalid feed id')
    result['line'] = None if item.get('line') in (None, '') else str(_decimal(item['line']))
    market = result['market_type'].lower()
    if market in ('totals', 'spreads', 'handicap') and result['line'] is None:
        raise ValueError('market line required')
    if market in ('1x2', 'h2h_3way') and result['line'] is not None:
        raise ValueError('line incompatible with 1x2')
    published = item.get('source_published_at') or item.get('published_at')
    result['source_published_at'] = utc(published) if published else None
    result['received_at'] = utc(item.get('received_at')) if simulated else captured_at
    if result['source_published_at'] and result['source_published_at'] > result['received_at']:
        raise ValueError('source publication after receipt')
    if simulated:
        result['persisted_at'] = utc(item.get('persisted_at'))
        result['usable_at'] = utc(item.get('usable_at') or result['persisted_at'])
        if not result['received_at'] <= result['persisted_at'] <= result['usable_at']:
            raise ValueError('invalid simulated timestamp order')
    for key in ('quote_phase', 'timing_basis', 'source_reference', 'source_record_hash',
                'source_attribution', 'source_license', 'transformation', 'event_at',
                'source_result', 'source_void_reason', 'source_provider_label', 'provider_mapping_basis',
                'source_match_date', 'source_match_time', 'source_score_home', 'source_score_away',
                'source_url', 'source_column'):
        if item.get(key) is not None:
            if not isinstance(item[key], str) or not item[key].strip():
                raise ValueError('invalid ' + key)
            result[key] = item[key]
    for key in ('quote_time_known', 'synchronization_proven', 'result_time_known', 'provider_mapping_verified'):
        if key in item:
            if type(item[key]) is not bool:
                raise ValueError('invalid ' + key)
            result[key] = item[key]
    result['supersedes_acquisition_id'] = item.get('supersedes_acquisition_id') or None
    result['clock_mode'] = 'synthetic_simulated' if simulated else 'operational'
    result['effective_market_received_at'] = result['received_at']
    quotes = item.get('quotes')
    if not isinstance(quotes, list) or not quotes:
        raise ValueError('missing quotes')
    result['quotes'] = []
    seen = set()
    for quote in quotes:
        if not isinstance(quote, dict):
            raise ValueError('invalid quote')
        outcome = _required(quote, 'outcome').lower()
        if result['market_type'].lower() in ('1x2', 'h2h_3way') and outcome not in ('home', 'draw', 'away'):
            raise ValueError('invalid 1x2 outcome')
        if outcome in seen:
            raise ValueError('duplicate outcome')
        seen.add(outcome)
        price, form = _validate_price(quote.get('odds_original'), quote.get('odds_format'))
        result['quotes'].append({'outcome': outcome, 'odds_original': price, 'odds_format': form})
    return result


def _connect(path):
    connection = sqlite3.connect(str(path), timeout=10)
    connection.execute('PRAGMA foreign_keys=ON')
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS raw_sources (source_hash TEXT PRIMARY KEY, bytes BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS acquisitions (
      source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
      source_hash TEXT NOT NULL REFERENCES raw_sources(source_hash), payload TEXT NOT NULL,
      supersedes TEXT, PRIMARY KEY(source_id,acquisition_id));
    CREATE TABLE IF NOT EXISTS receipts (
      source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL, received_at TEXT NOT NULL,
      persisted_at TEXT NOT NULL, usable_at TEXT NOT NULL, clock_mode TEXT NOT NULL,
      PRIMARY KEY(source_id,acquisition_id),
      FOREIGN KEY(source_id,acquisition_id) REFERENCES acquisitions(source_id,acquisition_id));
    CREATE TABLE IF NOT EXISTS quarantine (
      source_hash TEXT NOT NULL REFERENCES raw_sources(source_hash), ordinal INTEGER NOT NULL,
      reason TEXT NOT NULL, recorded_at TEXT NOT NULL, PRIMARY KEY(source_hash,ordinal,reason));
    CREATE TABLE IF NOT EXISTS quarantine_receipts (
      source_hash TEXT NOT NULL, ordinal INTEGER NOT NULL, reason TEXT NOT NULL,
      usable_at TEXT NOT NULL, clock_mode TEXT NOT NULL, PRIMARY KEY(source_hash,ordinal,reason),
      FOREIGN KEY(source_hash,ordinal,reason) REFERENCES quarantine(source_hash,ordinal,reason));
    CREATE TRIGGER IF NOT EXISTS quarantine_receipts_no_update BEFORE UPDATE ON quarantine_receipts BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS quarantine_receipts_no_delete BEFORE DELETE ON quarantine_receipts BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS raw_immutable_update BEFORE UPDATE ON raw_sources BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS raw_immutable_delete BEFORE DELETE ON raw_sources BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS acquisition_immutable_update BEFORE UPDATE ON acquisitions BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS acquisition_immutable_delete BEFORE DELETE ON acquisitions BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS receipt_immutable_update BEFORE UPDATE ON receipts BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS receipt_immutable_delete BEFORE DELETE ON receipts BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS quarantine_immutable_update BEFORE UPDATE ON quarantine BEGIN SELECT RAISE(ABORT,'immutable'); END;
    CREATE TRIGGER IF NOT EXISTS quarantine_immutable_delete BEFORE DELETE ON quarantine BEGIN SELECT RAISE(ABORT,'immutable'); END;
    ''')
    # Older quarantine receipts did not record a clock mode; exclude them until
    # separately reconciled instead of assuming operational availability.
    columns = {row[1] for row in connection.execute('PRAGMA table_info(quarantine_receipts)')}
    if 'clock_mode' not in columns:
        connection.execute("ALTER TABLE quarantine_receipts ADD COLUMN clock_mode TEXT NOT NULL DEFAULT 'unknown'")
        connection.commit()
    return connection


def import_file(db_path, path, *, simulated=False):
    """Import one local JSON/CSV file; return counts and explicit clock mode.

    Actual imports commit raw content and records first. Only after the first
    commit succeeds is its acknowledgment time captured and an immutable receipt
    appended. A record without that receipt is excluded from as-of retrieval.
    Imported historical publication time never substitutes for local receipt.
    """
    path = Path(path)
    raw = path.read_bytes()
    captured_at = _now()
    items = _snapshots(raw, path.suffix)
    return _import_records(db_path, raw, items, captured_at=captured_at, simulated=simulated)


def _import_records(db_path, raw, items, *, captured_at, simulated=False):
    """Shared append path for adapters that derive typed claims from retained raw bytes."""
    source_hash = _sha(raw)
    if simulated and any(not isinstance(x, dict) or x.get('data_origin') != 'synthetic' for x in items):
        raise ValueError('simulated clock is allowed for synthetic evidence only')
    counts = {'inserted': 0, 'duplicates': 0, 'quarantined': 0, 'source_hash': source_hash,
              'clock_mode': 'synthetic_simulated' if simulated else 'operational'}
    needs_receipt = []
    needs_quarantine_receipt = []
    with closing(_connect(db_path)) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO raw_sources VALUES(?,?)', (source_hash, raw))
            for ordinal, item in enumerate(items):
                try:
                    data = _normalize(item, captured_at, simulated)
                    fingerprint = _sha(_canonical({k: v for k, v in item.items() if k != 'source_reference'}))
                    identity = (data['source_id'], data['acquisition_id'])
                    old = db.execute('SELECT fingerprint,payload FROM acquisitions WHERE source_id=? AND acquisition_id=?', identity).fetchone()
                    if old:
                        if json.loads(old[1]).get('clock_mode') != data['clock_mode']:
                            raise ValueError('acquisition clock mode conflict')
                        if old[0] != fingerprint:
                            raise ValueError('acquisition identity collision')
                        counts['duplicates'] += 1
                        if not db.execute('SELECT 1 FROM receipts WHERE source_id=? AND acquisition_id=?', identity).fetchone():
                            needs_receipt.append(json.loads(old[1]))
                        continue
                    supersedes = data['supersedes_acquisition_id']
                    if supersedes:
                        prior = db.execute('SELECT payload,source_hash FROM acquisitions WHERE source_id=? AND acquisition_id=?', (data['source_id'], supersedes)).fetchone()
                        if not prior:
                            raise ValueError('unknown correction target')
                        previous = json.loads(prior[0])
                        scope = ('provider_id', 'feed_id', 'event_id', 'competition', 'home', 'away', 'market_type', 'period', 'status', 'settlement', 'line', 'data_origin', 'clock_mode')
                        if any(previous.get(k) != data.get(k) for k in scope):
                            raise ValueError('correction identity mismatch')
                        if {q['outcome'] for q in previous['quotes']} != {q['outcome'] for q in data['quotes']}:
                            raise ValueError('correction outcome mismatch')
                        if simulated and data['usable_at'] < previous.get('usable_at', previous['received_at']):
                            raise ValueError('correction usable before target')
                        if db.execute('SELECT 1 FROM acquisitions WHERE source_id=? AND supersedes=?', (data['source_id'], supersedes)).fetchone():
                            raise ValueError('conflicting correction branch')
                        data['effective_market_received_at'] = previous.get('effective_market_received_at', previous['received_at'])
                        data['revision_lineage'] = previous.get('revision_lineage', []) + [
                            {'source_id': data['source_id'], 'acquisition_id': supersedes, 'source_hash': prior[1]}]
                    data['snapshot_id'] = data['acquisition_id']
                    data['source_hash'] = source_hash
                    db.execute('INSERT INTO acquisitions VALUES(?,?,?,?,?,?)',
                               (*identity, fingerprint, source_hash, _canonical(data).decode('utf-8'), supersedes))
                    needs_receipt.append(data)
                    counts['inserted'] += 1
                except (ValueError, TypeError) as exc:
                    recorded_at = captured_at
                    if simulated and isinstance(item, dict):
                        try:
                            recorded_at = utc(item.get('usable_at') or item.get('persisted_at'))
                        except ValueError:
                            pass
                    db.execute('INSERT OR IGNORE INTO quarantine VALUES(?,?,?,?)', (source_hash, ordinal, str(exc), recorded_at))
                    needs_quarantine_receipt.append((source_hash, ordinal, str(exc), recorded_at))
                    counts['quarantined'] += 1
            db.commit()
            acknowledged_at = _now()
            counts['data_commit_acknowledged_at'] = acknowledged_at
            db.execute('BEGIN IMMEDIATE')
            for data in needs_receipt:
                persisted = data['persisted_at'] if simulated else acknowledged_at
                usable = data['usable_at'] if simulated else acknowledged_at
                db.execute('INSERT OR IGNORE INTO receipts VALUES(?,?,?,?,?,?)',
                           (data['source_id'], data['acquisition_id'], data['received_at'], persisted, usable, counts['clock_mode']))
            for qhash, ordinal, reason, recorded_at in needs_quarantine_receipt:
                q_usable = recorded_at if simulated else acknowledged_at
                db.execute('INSERT OR IGNORE INTO quarantine_receipts VALUES(?,?,?,?,?)',
                           (qhash, ordinal, reason, q_usable, counts['clock_mode']))
            db.commit()
            counts['receipt_commit_acknowledged_at'] = _now()
        except Exception:
            db.rollback()
            raise
    return counts


def get_as_of(db_path, cutoff, *, clock_mode='operational'):
    """Return eligible revisions at an inclusive UTC cutoff."""
    cutoff = utc(cutoff)
    if clock_mode not in ('operational', 'synthetic_simulated'):
        raise ValueError('invalid clock mode')
    with closing(_connect(db_path)) as db:
        rows = db.execute('''SELECT a.payload, r.received_at, r.persisted_at, r.usable_at, r.clock_mode
          FROM acquisitions a JOIN receipts r ON r.source_id=a.source_id AND r.acquisition_id=a.acquisition_id
          WHERE r.usable_at<=? AND r.persisted_at<=? AND r.received_at<=? AND r.clock_mode=?
          ORDER BY r.usable_at, a.source_id, a.acquisition_id''', (cutoff, cutoff, cutoff, clock_mode)).fetchall()
    snapshots = []
    for payload, received, persisted, usable, mode in rows:
        data = json.loads(payload)
        data.update(received_at=received, persisted_at=persisted, usable_at=usable, clock_mode=mode)
        snapshots.append(data)
    superseded = {(s['source_id'], s['supersedes_acquisition_id']) for s in snapshots if s.get('supersedes_acquisition_id')}
    quotes = []
    for data in snapshots:
        if (data['source_id'], data['acquisition_id']) in superseded:
            continue
        metadata = {key: value for key, value in data.items() if key != 'quotes'}
        for quote in data['quotes']:
            identity = [data['source_id'], data['acquisition_id'], quote['outcome']]
            quotes.append(dict(metadata, **quote, evidence_id=_sha(_canonical(identity))))
    return quotes


def get_quarantine(db_path, cutoff, *, clock_mode='operational'):
    cutoff = utc(cutoff)
    if clock_mode not in ('operational', 'synthetic_simulated'):
        raise ValueError('invalid clock mode')
    with closing(_connect(db_path)) as db:
        rows = db.execute('''SELECT q.source_hash,q.ordinal,q.reason,q.recorded_at,r.usable_at,r.clock_mode
            FROM quarantine q JOIN quarantine_receipts r ON r.source_hash=q.source_hash
            AND r.ordinal=q.ordinal AND r.reason=q.reason
            WHERE r.usable_at<=? AND r.clock_mode=? ORDER BY q.source_hash,q.ordinal,q.reason''', (cutoff, clock_mode)).fetchall()
        return [dict(source_hash=row[0], ordinal=row[1], reason=row[2], recorded_at=row[3], usable_at=row[4], clock_mode=row[5]) for row in rows]


def raw_source(db_path, source_hash):
    with closing(_connect(db_path)) as db:
        row = db.execute('SELECT bytes FROM raw_sources WHERE source_hash=?', (source_hash,)).fetchone()
        if row is None:
            raise KeyError(source_hash)
        return bytes(row[0])






