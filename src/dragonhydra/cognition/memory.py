"""Append-only, source-linked cognitive model and feedback memory.

Records use actual local operational clocks. A source's publication, local
capture, first durable commit acknowledgment and receipt are distinct. The
exact visibility time of the subsequent SQLite receipt commit is not proven;
this store exposes receipt-bounded operational replay rather than claiming a
verified retrospective STRICT_PIT boundary.
"""
from __future__ import annotations

from contextlib import closing
import base64
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time as monotonic_time

from .. import market_store, public_results

VERSION = 'cognitive-memory/1'
OUTCOMES = ('home', 'draw', 'away')
COGNITIVE_KINDS = ('model', 'prediction', 'outcome', 'task', 'evaluation', 'hypothesis')
SCHEMA_TABLES = frozenset({'cognitive_records', 'cognitive_receipts'})
SCHEMA_TRIGGERS = frozenset({'cognitive_records_no_update', 'cognitive_records_no_delete',
                           'cognitive_receipts_no_update', 'cognitive_receipts_no_delete'})

# Shared verbatim by the optional context migration profile. Keep these exact
# table/trigger definitions compatible with existing cognitive databases.
SCHEMA_SQL = '''
    CREATE TABLE IF NOT EXISTS cognitive_records (
      kind TEXT NOT NULL, record_id TEXT NOT NULL PRIMARY KEY, natural_key TEXT NOT NULL,
      fingerprint TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(kind,natural_key));
    CREATE TABLE IF NOT EXISTS cognitive_receipts (
      record_id TEXT PRIMARY KEY REFERENCES cognitive_records(record_id),
      received_at TEXT NOT NULL, persisted_at TEXT NOT NULL, usable_at TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS cognitive_records_no_update BEFORE UPDATE ON cognitive_records
      BEGIN SELECT RAISE(ABORT,'immutable cognitive record'); END;
    CREATE TRIGGER IF NOT EXISTS cognitive_records_no_delete BEFORE DELETE ON cognitive_records
      BEGIN SELECT RAISE(ABORT,'immutable cognitive record'); END;
    CREATE TRIGGER IF NOT EXISTS cognitive_receipts_no_update BEFORE UPDATE ON cognitive_receipts
      BEGIN SELECT RAISE(ABORT,'immutable cognitive receipt'); END;
    CREATE TRIGGER IF NOT EXISTS cognitive_receipts_no_delete BEFORE DELETE ON cognitive_receipts
      BEGIN SELECT RAISE(ABORT,'immutable cognitive receipt'); END;
    '''


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _time(value):
    if not isinstance(value, str):
        raise ValueError('TIMESTAMP_REQUIRED')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('INVALID_TIMESTAMP') from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('NAIVE_TIMESTAMP')
    return parsed.astimezone(timezone.utc)


def _utc(value):
    return _time(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('MISSING_' + field.upper())
    return value.strip()


def _schema(db):
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript(SCHEMA_SQL)


def _probabilities(value):
    if not isinstance(value, dict) or set(value) != set(OUTCOMES):
        raise ValueError('PROBABILITIES_REQUIRED')
    result = {}
    try:
        for key in OUTCOMES:
            if isinstance(value[key], bool):
                raise ValueError('INVALID_PROBABILITY')
            number = Decimal(str(value[key]))
            if not number.is_finite() or number <= 0 or number >= 1:
                raise ValueError('INVALID_PROBABILITY')
            result[key] = str(number)
        if abs(sum(Decimal(x) for x in result.values()) - 1) > Decimal('1e-12'):
            raise ValueError('PROBABILITIES_NOT_NORMALIZED')
    except (InvalidOperation, TypeError):
        raise ValueError('INVALID_PROBABILITY') from None
    return result


def _source_rows(db, cutoff):
    rows = public_results.as_of(db, cutoff)
    return {row['evidence_id']:row for row in rows}


def _latest_source_rows(db, cutoff):
    rows = public_results.latest(db, cutoff)
    return {row['evidence_id']:row for row in rows}


def _ambiguous_fixture_evidence(rows, cutoff):
    return {evidence_id for flag in public_results.find_ambiguous_fixtures(list(rows.values()),cutoff)
            for evidence_id in flag['evidence_ids']}


def _ambiguous_fixture_identities(db, cutoff):
    latest = _latest_source_rows(db,cutoff)
    return {(flag['source_id'],flag['competition'],flag['home'],flag['away'])
            for flag in public_results.find_ambiguous_fixtures(list(latest.values()),cutoff)}


def _row_has_ambiguous_identity(row, identities):
    return tuple(row.get(key) for key in ('source_id','competition','home','away')) in identities


def _verify_source(db, row):
    """Bind an accepted record back to retained raw source bytes and row."""
    if row.get('data_origin') not in ('captured_real', 'imported_historical'):
        raise ValueError('REAL_SOURCE_RECORD_REQUIRED')
    digest = row.get('source_hash')
    stored = db.execute('SELECT bytes FROM raw_sources WHERE source_hash=?', (digest,)).fetchone()
    if stored is None or _hash(bytes(stored[0])) != digest:
        raise ValueError('SOURCE_HASH_MISMATCH')
    try:
        document = json.loads(bytes(stored[0]).decode('utf-8-sig'))
        match = re.fullmatch(r'\$\.matches\[(\d+)\]', row.get('source_record_path') or '')
        if not match:
            raise ValueError('SOURCE_RECORD_PATH_REQUIRED')
        ordinal = int(match.group(1))
        raw = document['matches'][ordinal]
        expected = public_results._match(document['name'], raw, ordinal)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise ValueError('SOURCE_RECORD_UNRESOLVED') from None
    fields = ('fixture_key', 'competition', 'event_date', 'source_local_time', 'home', 'away',
              'market_type', 'period', 'settlement', 'home_goals', 'away_goals', 'outcome', 'result_state')
    if any(row.get(key) != expected.get(key) for key in fields):
        raise ValueError('SOURCE_RECORD_MISMATCH')
    expected_id = _hash(_canonical([row['source_id'], row['acquisition_id'], ordinal]))
    if row['evidence_id'] != expected_id:
        raise ValueError('SOURCE_EVIDENCE_ID_MISMATCH')


def _source_snapshot(row):
    fields = ('evidence_id', 'source_id', 'acquisition_id', 'source_hash', 'source_url',
              'source_record_path', 'data_origin', 'source_published_at', 'source_capture_at',
              'received_at', 'persisted_at', 'usable_at', 'fixture_key', 'event_date',
              'competition', 'home', 'away', 'market_type', 'period', 'settlement',
              'home_goals', 'away_goals', 'outcome', 'result_state', 'transformation')
    return {field:row.get(field) for field in fields}


def _embedded_evidence_ids(value):
    """Extract every nested evidence_ids list without trusting its shape."""
    found = set()
    if isinstance(value,dict):
        for key,item in value.items():
            if isinstance(key,str) and key.endswith('evidence_ids'):
                if not isinstance(item,list) or any(not isinstance(x,str) or not x for x in item):
                    raise ValueError('INVALID_EMBEDDED_EVIDENCE_IDS')
                found.update(item)
            else:
                found.update(_embedded_evidence_ids(item))
    elif isinstance(value,list):
        for item in value:
            found.update(_embedded_evidence_ids(item))
    return found


def _configuration_evidence_id(configuration, received):
    """Verify a model configuration's identity against its canonical values."""
    evidence_id = configuration.get('evidence_id')
    if evidence_id is None:
        return None
    if not isinstance(configuration.get('values'),dict):
        raise ValueError('INVALID_CONFIGURATION_EVIDENCE')
    raw = json.dumps(configuration['values'],sort_keys=True,separators=(',', ':'),allow_nan=False).encode('utf-8')
    digest = _hash(raw)
    if configuration.get('source_hash') != digest or evidence_id != 'config:' + digest:
        raise ValueError('INVALID_CONFIGURATION_EVIDENCE')
    if configuration.get('data_origin') != 'configuration' or not configuration.get('source_id'):
        raise ValueError('INVALID_CONFIGURATION_EVIDENCE')
    if _time(configuration.get('recorded_at')) > _time(received):
        raise ValueError('CONFIGURATION_AFTER_MODEL')
    return evidence_id


def _append(db, kind, natural_key, payload, received):
    _schema(db)
    raw = _canonical(payload)
    fingerprint = _hash(raw)
    record_id = kind + ':' + _hash(_canonical([kind,natural_key,fingerprint]))
    try:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT record_id,fingerprint FROM cognitive_records WHERE kind=? AND natural_key=?',
                              (kind,natural_key)).fetchone()
        if existing:
            if existing[1] != fingerprint:
                raise ValueError('MEMORY_IDENTITY_COLLISION')
            receipt = db.execute('SELECT received_at,persisted_at,usable_at FROM cognitive_receipts WHERE record_id=?',
                                 (existing[0],)).fetchone()
            if receipt is None:
                raise ValueError('MEMORY_RECEIPT_MISSING')
            db.commit()
            return {'record_id':existing[0], 'record_content_hash':fingerprint, 'duplicate':True, 'received_at':receipt[0],
                    'persisted_at':receipt[1], 'usable_at':receipt[2]}
        db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)',
                   (kind,record_id,natural_key,fingerprint,raw.decode('utf-8')))
        db.commit()
        acknowledged = _now()
        if _time(acknowledged) < _time(received):
            raise ValueError('CLOCK_MOVED_BACKWARDS')
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO cognitive_receipts VALUES(?,?,?,?)', (record_id,received,acknowledged,acknowledged))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'record_id':record_id,'record_content_hash':fingerprint,'duplicate':False,'received_at':received,
            'persisted_at':acknowledged,'usable_at':acknowledged}


def _existing(db, kind, natural_key):
    _schema(db)
    row = db.execute('''SELECT r.record_id,r.payload,c.received_at,c.persisted_at,c.usable_at,r.fingerprint
                        FROM cognitive_records r LEFT JOIN cognitive_receipts c ON r.record_id=c.record_id
                        WHERE r.kind=? AND r.natural_key=?''',(kind,natural_key)).fetchone()
    if row is None:
        return None
    if row[2] is None:
        raise ValueError('MEMORY_RECEIPT_MISSING')
    return json.loads(row[1]), {'record_id':row[0],'record_content_hash':row[5],'duplicate':True,
                                 'received_at':row[2],'persisted_at':row[3],'usable_at':row[4]}


def _revision_chain(db, kind, scope):
    """Read and verify a complete scoped chain, without schema creation.

    Revision allocation must call this while holding BEGIN IMMEDIATE. Unknown
    kinds are excluded before decoding; a corrupt record in this kind fails
    closed instead of silently selecting an earlier head.
    """
    rows = db.execute('''SELECT r.record_id,r.natural_key,r.fingerprint,r.payload,
        c.received_at,c.persisted_at,c.usable_at FROM cognitive_records r
        LEFT JOIN cognitive_receipts c ON c.record_id=r.record_id WHERE r.kind=?''', (kind,)).fetchall()
    chain = []
    for record_id, natural_key, fingerprint, raw, received, persisted, usable in rows:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            raise ValueError('MEMORY_CONTENT_INVALID') from None
        if not isinstance(payload, dict):
            raise ValueError('MEMORY_CONTENT_INVALID')
        if _hash(raw.encode('utf-8')) != fingerprint or _canonical(payload).decode('utf-8') != raw:
            raise ValueError('MEMORY_CONTENT_HASH_MISMATCH')
        expected_id = kind + ':' + _hash(_canonical([kind, natural_key, fingerprint]))
        if record_id != expected_id:
            raise ValueError('MEMORY_RECORD_ID_MISMATCH')
        if payload.get('scope') != scope:
            continue
        revision = payload.get('revision')
        if type(revision) is not int or revision < 1:
            raise ValueError('MEMORY_REVISION_CHAIN_INVALID')
        if natural_key != _hash(_canonical([scope, revision])):
            raise ValueError('MEMORY_REVISION_KEY_MISMATCH')
        if received is not None:
            if (_time(received) != _time(payload['record_started_at']) or
                    not _time(received) <= _time(persisted) <= _time(usable)):
                raise ValueError('MEMORY_RECEIPT_CLOCK_INVALID')
        elif persisted is not None or usable is not None:
            raise ValueError('MEMORY_RECEIPT_INVALID')
        chain.append({'record_id':record_id, 'record_content_hash':fingerprint, 'payload':payload,
                      'received_at':received, 'persisted_at':persisted, 'usable_at':usable})
    chain.sort(key=lambda item:item['payload']['revision'])
    predecessor = None
    predecessor_usable = None
    for ordinal, item in enumerate(chain, 1):
        body = item['payload']
        if body['revision'] != ordinal or body.get('supersedes_record_id') != predecessor:
            raise ValueError('MEMORY_REVISION_CHAIN_INVALID')
        if item['received_at'] is None and ordinal != len(chain):
            raise ValueError('MEMORY_PENDING_PREDECESSOR')
        if item['usable_at'] is not None:
            if predecessor_usable is not None and _time(item['usable_at']) < _time(predecessor_usable):
                raise ValueError('MEMORY_RECEIPT_CLOCK_INVALID')
            predecessor_usable = item['usable_at']
        predecessor = item['record_id']
    return chain


def _revision_receipt(db, kind, scope, record_id, acknowledged, validate):
    """Complete/recover a receipt after a prior durable record commit.

    Another writer can recover the same record between the two commits. The
    winner's immutable receipt is reused, including its original clocks.
    """
    try:
        db.execute('BEGIN IMMEDIATE')
        chain = _revision_chain(db, kind, scope)
        for item in chain:
            validate(db, item['payload'])
        selected = next((item for item in chain if item['record_id'] == record_id), None)
        if selected is None:
            raise ValueError('MEMORY_RECORD_MISSING')
        if selected['received_at'] is None:
            received = selected['payload']['record_started_at']
            if _time(acknowledged) < _time(received):
                raise ValueError('CLOCK_MOVED_BACKWARDS')
            predecessor = next((item for item in chain
                                if item['record_id'] == selected['payload']['supersedes_record_id']), None)
            if predecessor is not None and _time(acknowledged) < _time(predecessor['usable_at']):
                raise ValueError('CLOCK_MOVED_BACKWARDS')
            db.execute('INSERT INTO cognitive_receipts VALUES(?,?,?,?)',
                       (record_id, received, acknowledged, acknowledged))
            selected.update(received_at=received, persisted_at=acknowledged, usable_at=acknowledged)
        db.commit()
        receipt_acknowledged = _now()
        if _time(receipt_acknowledged) < _time(selected['usable_at']):
            raise ValueError('CLOCK_MOVED_BACKWARDS')
    except Exception:
        db.rollback()
        raise
    return {key:value for key,value in selected.items() if key != 'payload'} | {
        'receipt_acknowledged_at':receipt_acknowledged}


def _append_revision(db, kind, scope, body, semantic, validate):
    """Append latest-head semantic revisions using the shared immutable store.

    Schema initialization belongs to the caller, before this transaction. The
    trusted validation callback must only read dependencies, with no network
    or transaction changes. Both incoming and retained bindings are validated.
    """
    received = _now()
    recovered = False
    while True:
        try:
            db.execute('BEGIN IMMEDIATE')
            chain = _revision_chain(db, kind, scope)
            for item in chain:
                validate(db, item['payload'])
            head = chain[-1] if chain else None
            revision = head['payload']['revision'] + 1 if head else 1
            candidate = dict(body, scope=scope, revision=revision,
                             supersedes_record_id=head['record_id'] if head else None,
                             record_started_at=received)
            validate(db, candidate)
            if head and head['received_at'] is None:
                # Do not advance past a durable but not yet receipted record.
                db.commit()
                _revision_receipt(db, kind, scope, head['record_id'], _now(), validate)
                recovered = True
                continue
            if head and semantic(head['payload']) == semantic(candidate):
                db.commit()
                result = {key:value for key,value in head.items() if key != 'payload'}
                result.update(duplicate=True, recovered=recovered, receipt_acknowledged_at=_now())
                if _time(result['receipt_acknowledged_at']) < _time(head['usable_at']):
                    raise ValueError('CLOCK_MOVED_BACKWARDS')
                return result
            raw = _canonical(candidate)
            fingerprint = _hash(raw)
            natural_key = _hash(_canonical([scope, revision]))
            record_id = kind + ':' + _hash(_canonical([kind, natural_key, fingerprint]))
            db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)',
                       (kind, record_id, natural_key, fingerprint, raw.decode('utf-8')))
            db.commit()
            acknowledged = _now()
        except Exception:
            db.rollback()
            raise
        result = _revision_receipt(db, kind, scope, record_id, acknowledged, validate)
        result.update(duplicate=False, recovered=recovered)
        return result


def _schema_state(db):
    objects = list(db.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','trigger')"))
    tables = {name for name, kind in objects if kind == 'table'}
    triggers = {name for name, kind in objects if kind == 'trigger'}
    if SCHEMA_TABLES <= tables and SCHEMA_TRIGGERS <= triggers:
        return 'complete'
    return 'incomplete' if SCHEMA_TABLES & tables or SCHEMA_TRIGGERS & triggers else 'absent'


def inspect_store(db_path):
    """Bounded read-only structural evidence; never initialize or repair memory."""
    deadline = monotonic_time.monotonic()+.25
    try:
        with closing(sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)) as db:
            db.execute('PRAGMA query_only=ON')
            db.set_progress_handler(lambda: int(monotonic_time.monotonic() > deadline), 1000)
            state = _schema_state(db)
            counts = {table: db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                      for table in SCHEMA_TABLES} if state == 'complete' else {}
            return {'schema_state': state, 'counts': counts}
    except (sqlite3.Error, OSError):
        raise ValueError('COGNITIVE_STORE_UNAVAILABLE') from None


def _as_of(db, cutoff, *, initialize=True):
    cutoff = _utc(cutoff)
    if initialize:
        _schema(db)
    rows = db.execute('''SELECT r.kind,r.record_id,r.payload,c.received_at,c.persisted_at,c.usable_at,r.fingerprint
      FROM cognitive_records r JOIN cognitive_receipts c ON r.record_id=c.record_id
      WHERE r.kind IN ('model','prediction','outcome','task','evaluation','hypothesis')
      AND c.received_at<=? AND c.persisted_at<=? AND c.usable_at<=?
      ORDER BY c.usable_at,r.record_id''', (cutoff,cutoff,cutoff)).fetchall()
    result = {'models':[], 'predictions':[], 'outcomes':[], 'research_tasks':[], 'evaluations':[], 'hypotheses':[]}
    names = {'model':'models','prediction':'predictions','outcome':'outcomes','task':'research_tasks',
             'evaluation':'evaluations','hypothesis':'hypotheses'}
    for kind, record_id, payload, received, persisted, usable, fingerprint in rows:
        record = json.loads(payload)
        record.update(record_id=record_id,evidence_id=record_id,received_at=received,persisted_at=persisted,usable_at=usable,
                      record_content_hash=fingerprint,record_source_id='cognitive-memory',
                      record_reference='sqlite:cognitive_records/'+record_id,
                      memory_version=VERSION, availability_mode='OPERATIONAL_AS_OF_RECEIPT')
        if kind == 'prediction':
            record.update(decision_cutoff=usable, predicted_at=usable)
        result[names[kind]].append(record)
    return result


def as_of(db_path, cutoff, *, readonly=False):
    if readonly:
        cutoff = _utc(cutoff)
        try:
            with closing(sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)) as db:
                db.execute('PRAGMA query_only=ON')
                deadline = monotonic_time.monotonic()+2
                db.set_progress_handler(lambda: int(monotonic_time.monotonic() > deadline), 1000)
                state = _schema_state(db)
                if state == 'absent':
                    return {'models': [], 'predictions': [], 'outcomes': [], 'research_tasks': [], 'evaluations': [], 'hypotheses': []}
                if state != 'complete':
                    raise ValueError('COGNITIVE_STORE_INCOMPLETE')
                return _as_of(db, cutoff, initialize=False)
        except (sqlite3.Error, OSError):
            raise ValueError('COGNITIVE_STORE_UNAVAILABLE') from None
    with closing(sqlite3.connect(str(db_path),timeout=10)) as db:
        return _as_of(db,cutoff)


def _record_model_run(db, draft):
    if not isinstance(draft,dict):
        raise ValueError('MODEL_DRAFT_REQUIRED')
    received = _now()
    cutoff = _utc(draft.get('data_cutoff'))
    if _time(cutoff) > _time(received):
        raise ValueError('MODEL_DATA_CUTOFF_IN_FUTURE')
    name = _text(draft.get('model_name'),'model_name')
    version = _text(draft.get('model_version'),'model_version')
    run_id = _text(draft.get('run_id'),'run_id')
    transform = _text(draft.get('transformation'),'transformation')
    ids = draft.get('input_evidence_ids')
    if not isinstance(ids,list) or not ids or len(ids) != len(set(ids)):
        raise ValueError('MODEL_INPUT_EVIDENCE_REQUIRED')
    if not isinstance(draft.get('parameters'),dict) or not isinstance(draft.get('configuration'),dict):
        raise ValueError('MODEL_CONFIGURATION_REQUIRED')
    sources = _latest_source_rows(db,cutoff)
    ambiguous = _ambiguous_fixture_evidence(sources,cutoff)
    training = []
    for eid in ids:
        row = sources.get(eid)
        if row is None:
            raise ValueError('MODEL_INPUT_NOT_ELIGIBLE')
        if eid in ambiguous:
            raise ValueError('AMBIGUOUS_MODEL_TRAINING_FIXTURE')
        _verify_source(db,row)
        if row.get('outcome') not in OUTCOMES or row.get('result_state') != 'available':
            raise ValueError('MODEL_RESULT_REQUIRED')
        try:
            event_day = date.fromisoformat(row['event_date'])
        except (TypeError,ValueError):
            raise ValueError('INVALID_EVENT_DATE') from None
        # No UTC kickoff is inferred. Two-day buffer ensures the source-local
        # event date is fully in the past even when its timezone is unknown.
        if datetime.combine(event_day + timedelta(days=2),time.min,tzinfo=timezone.utc) > _time(cutoff):
            raise ValueError('MODEL_EVENT_DATE_NOT_COMPLETE')
        training.append(row)
    scope = {(x['source_id'],x['competition'],x['market_type'],x['period'],x['settlement']) for x in training}
    if len(scope) != 1:
        raise ValueError('MODEL_INPUT_SCOPE_MISMATCH')
    if len({x['fixture_key'] for x in training}) != len(training):
        raise ValueError('AMBIGUOUS_TRAINING_FIXTURE')
    source_id,competition,market_type,period,settlement=next(iter(scope))
    target_id = draft['parameters'].get('target_evidence_id')
    if target_id is not None:
        target = sources.get(_text(target_id,'target_evidence_id'))
        if target is None:
            raise ValueError('MODEL_TARGET_NOT_ELIGIBLE')
        if target_id in ambiguous:
            raise ValueError('AMBIGUOUS_MODEL_TARGET_FIXTURE')
        _verify_source(db,target)
        if (target.get('source_id'),target.get('competition'),target.get('market_type'),
            target.get('period'),target.get('settlement')) != (source_id,competition,market_type,period,settlement):
            raise ValueError('MODEL_TARGET_SCOPE_MISMATCH')
        if target.get('result_state') != 'unavailable' or target.get('outcome') is not None:
            raise ValueError('MODEL_TARGET_ALREADY_HAS_OUTCOME')
        if any(row['fixture_key']==target['fixture_key'] and row.get('outcome') in OUTCOMES
               for row in _source_rows(db,cutoff).values()):
            raise ValueError('MODEL_TARGET_OUTCOME_ALREADY_KNOWN')
        event_day = date.fromisoformat(target['event_date'])
        if _time(received) >= datetime.combine(event_day-timedelta(days=1),time.min,tzinfo=timezone.utc):
            raise ValueError('MODEL_TARGET_TIME_NOT_PROVABLY_PREGAME')
    configuration_id = _configuration_evidence_id(draft['configuration'],received)
    embedded = _embedded_evidence_ids(draft['parameters']) | _embedded_evidence_ids(draft['configuration'])
    for eid in embedded:
        if eid == configuration_id:
            continue
        resolved = _resolve_evidence(db,eid,cutoff)
        if resolved is None:
            raise ValueError('UNKNOWN_MODEL_EVIDENCE_REFERENCE')
        if (resolved.get('data_origin') == 'synthetic' or
                resolved.get('original_data_origin') in ('hypothesis','research_task')):
            raise ValueError('MODEL_NON_EVIDENCE_REFERENCE')
    payload = {'run_id':run_id,'model_name':name,'model_version':version,
               'data_cutoff':cutoff,'input_evidence_ids':list(ids),
               'training_manifest':[_source_snapshot(x) for x in training],
               'source_id':source_id,'competition':competition,'market_type':market_type,
               'period':period,'settlement':settlement,'parameters':draft['parameters'],
               'configuration':draft['configuration'],'transformation':transform,
               'data_origin':'model_state','model_computation_verification':'submitted calculation; retained inputs and metadata validated'}
    return _append(db,'model',run_id + ':' + name,payload,received)


def record_model_run(db_path, draft):
    with closing(sqlite3.connect(str(db_path),timeout=10)) as db:
        return _record_model_run(db,draft)


def _record_prediction(db, draft):
    if not isinstance(draft,dict):
        raise ValueError('PREDICTION_DRAFT_REQUIRED')
    received = _now()
    run_id = _text(draft.get('run_id'),'run_id')
    model_id = _text(draft.get('model_run_id'),'model_run_id')
    target_id = _text(draft.get('target_evidence_id'),'target_evidence_id')
    transform = _text(draft.get('transformation'),'transformation')
    probabilities = _probabilities(draft.get('probabilities'))
    models = {r['record_id']:r for r in _as_of(db,received)['models']}
    model = models.get(model_id)
    if model is None:
        raise ValueError('MODEL_STATE_NOT_ELIGIBLE')
    model_output = model['parameters'].get('result')
    declared_target = model['parameters'].get('target_evidence_id')
    output_probabilities = model_output.get('probabilities') if isinstance(model_output,dict) else None
    if declared_target != target_id or not isinstance(output_probabilities,dict):
        raise ValueError('MODEL_OUTPUT_NOT_BOUND_TO_TARGET')
    try:
        values = {key:(output_probabilities[key].get('value') if isinstance(output_probabilities[key],dict)
                       else output_probabilities[key]) for key in OUTCOMES}
        bound_probabilities = _probabilities(values)
    except (KeyError,TypeError):
        raise ValueError('MODEL_OUTPUT_NOT_BOUND_TO_TARGET') from None
    if any(Decimal(probabilities[key]) != Decimal(bound_probabilities[key]) for key in OUTCOMES):
        raise ValueError('MODEL_OUTPUT_PROBABILITY_MISMATCH')
    prior = _existing(db,'prediction',run_id + ':' + model['model_name'])
    if prior:
        payload, receipt = prior
        if (payload['model_run_id'] != model_id or payload['target_evidence_id'] != target_id or
                payload['probabilities'] != probabilities or payload['transformation'] != transform):
            raise ValueError('MEMORY_IDENTITY_COLLISION')
        return receipt
    source = _source_rows(db,received)
    latest_sources = _latest_source_rows(db,received)
    target = latest_sources.get(target_id)
    if target is None:
        raise ValueError('TARGET_NOT_ELIGIBLE')
    if target_id in _ambiguous_fixture_evidence(latest_sources,received):
        raise ValueError('AMBIGUOUS_TARGET_FIXTURE')
    _verify_source(db,target)
    if target['result_state'] != 'unavailable' or target['outcome'] is not None:
        raise ValueError('TARGET_ALREADY_HAS_OUTCOME')
    keys = ('source_id','competition','market_type','period','settlement')
    if any(target[k] != model[k] for k in keys):
        raise ValueError('MODEL_TARGET_SCOPE_MISMATCH')
    for row in source.values():
        if row['fixture_key'] == target['fixture_key'] and row.get('outcome') in OUTCOMES:
            raise ValueError('OUTCOME_ALREADY_KNOWN')
    try:
        event_day = date.fromisoformat(target['event_date'])
    except (TypeError,ValueError):
        raise ValueError('INVALID_EVENT_DATE') from None
    event_earliest = datetime.combine(event_day - timedelta(days=1),time.min,tzinfo=timezone.utc)
    if _time(received) >= event_earliest:
        raise ValueError('PREDICTION_TIME_NOT_PROVABLY_PREGAME')
    payload = {'run_id':run_id,'model_run_id':model_id,'model_name':model['model_name'],
               'model_version':model['model_version'],'fixture_key':target['fixture_key'],
               'event_id':target['fixture_key'],'event_date':target['event_date'],
               'competition':target['competition'],'home':target['home'],'away':target['away'],
               'market_type':target['market_type'],'period':target['period'],'settlement':target['settlement'],
               'target_evidence_id':target_id,'target_evidence':_source_snapshot(target),
               'input_evidence_ids':model['input_evidence_ids'],'probabilities':probabilities,
               'transformation':transform,'data_origin':'model_estimate',
               'source_id':'cognitive-model:'+model['model_name'],
               'model_computation_verification':'submitted prediction; input eligibility and scope verified'}
    return _append(db,'prediction',run_id + ':' + model['model_name'],payload,received)


def record_prediction(db_path, draft):
    with closing(sqlite3.connect(str(db_path),timeout=10)) as db:
        return _record_prediction(db,draft)


def _record_outcome(db, source_evidence_id):
    received = _now()
    source_id = _text(source_evidence_id,'source_evidence_id')
    prior = _existing(db,'outcome',source_id)
    if prior:
        return prior[1]
    source = _latest_source_rows(db,received)
    row = source.get(source_id)
    if row is None:
        raise ValueError('OUTCOME_SOURCE_NOT_ELIGIBLE')
    if source_id in _ambiguous_fixture_evidence(source,received):
        raise ValueError('AMBIGUOUS_OUTCOME_FIXTURE')
    _verify_source(db,row)
    if row['result_state'] != 'available' or row['outcome'] not in OUTCOMES:
        raise ValueError('SOURCE_RESULT_REQUIRED')
    event_day = date.fromisoformat(row['event_date'])
    complete = datetime.combine(event_day + timedelta(days=2),time.min,tzinfo=timezone.utc)
    if _time(row['usable_at']) < complete:
        raise ValueError('OUTCOME_TIME_NOT_PROVABLY_POST_EVENT')
    predictions = _as_of(db,received)['predictions']
    eligible = [p for p in predictions if p['fixture_key']==row['fixture_key'] and
                p['target_evidence']['source_id']==row['source_id'] and
                all(p.get(k)==row.get(k) for k in ('competition','home','away','market_type','period','settlement')) and
                _time(p['usable_at']) < _time(row['usable_at'])]
    if not eligible:
        raise ValueError('NO_EARLIER_ELIGIBLE_PREDICTION')
    previous = [o for o in _as_of(db,received)['outcomes']
                if o['fixture_key']==row['fixture_key'] and o['source_id']==row['source_id']]
    previous.sort(key=lambda o:(o['source_usable_at'],o['record_id']))
    if previous and _time(row['usable_at']) <= _time(previous[-1]['source_usable_at']):
        if previous[-1]['source_evidence_id'] != source_id:
            raise ValueError('OUTCOME_REVISION_ORDER_AMBIGUOUS')
        previous = previous[:-1]
    payload = {'fixture_key':row['fixture_key'],'event_id':row['fixture_key'],
               'competition':row['competition'],'home':row['home'],'away':row['away'],
               'market_type':row['market_type'],'period':row['period'],'settlement':row['settlement'],
               'event_date':row['event_date'],'outcome':row['outcome'],
               'home_goals':row['home_goals'],'away_goals':row['away_goals'],
               'source_evidence_id':source_id,'source_usable_at':row['usable_at'],
               'source_hash':row['source_hash'],'source_id':row['source_id'],
               'source_evidence':_source_snapshot(row),'data_origin':row['data_origin'],
               'supersedes_record_id':previous[-1]['record_id'] if previous else None,
               'transformation':'verified OpenFootball full-time result; later source observation'}
    return _append(db,'outcome',source_id,payload,received)


def record_outcome(db_path, source_evidence_id):
    with closing(sqlite3.connect(str(db_path),timeout=10)) as db:
        return _record_outcome(db,source_evidence_id)


def _record_research_task(db, draft):
    if not isinstance(draft,dict):
        raise ValueError('TASK_DRAFT_REQUIRED')
    received = _now()
    required = ('gap','question','permitted_source','priority_rationale','expected_evidence','budget','stopping_condition')
    payload = {key:_text(draft.get(key),key) for key in required}
    ids = draft.get('evidence_ids',[])
    if not isinstance(ids,list) or any(not isinstance(x,str) or not x for x in ids):
        raise ValueError('INVALID_TASK_EVIDENCE')
    sources = _source_rows(db,received)
    memory = _as_of(db,received)
    known = set(sources)
    known.update(x['record_id'] for values in memory.values() for x in values)
    if any(eid not in known and _resolve_evidence(db,eid,received) is None for eid in ids):
        raise ValueError('UNKNOWN_TASK_EVIDENCE')
    ambiguous = _ambiguous_fixture_identities(db,received)
    ambiguous_ids = sorted(eid for eid in ids if eid in sources and _row_has_ambiguous_identity(sources[eid],ambiguous))
    payload.update(evidence_ids=sorted(set(ids)),data_origin='research_task',
                   source_id='cognitive-research',transformation=VERSION,
                   quality_flags=[{'code':'AMBIGUOUS_FIXTURE_EVIDENCE','evidence_ids':ambiguous_ids}] if ambiguous_ids else [])
    natural_key = _text(draft.get('task_id') or _hash(_canonical(payload)), 'task_id')
    payload['task_id'] = natural_key
    return _append(db,'task',natural_key,payload,received)


def record_research_task(db_path, draft):
    with closing(sqlite3.connect(str(db_path),timeout=10)) as db:
        return _record_research_task(db,draft)


def _market_evidence(db, evidence_id, cutoff):
    """Resolve operational market records by immutable acquisition and raw hash."""
    tables = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('acquisitions','receipts','raw_sources')")}
    if tables != {'acquisitions','receipts','raw_sources'}:
        return None
    rows = db.execute('''SELECT a.source_id,a.acquisition_id,a.payload,a.source_hash,
        r.received_at,r.persisted_at,r.usable_at,s.bytes
        FROM acquisitions a JOIN receipts r USING(source_id,acquisition_id)
        JOIN raw_sources s ON s.source_hash=a.source_hash
        WHERE r.clock_mode='operational' AND r.received_at<=? AND r.persisted_at<=? AND r.usable_at<=?''',
        (cutoff,cutoff,cutoff)).fetchall()
    for source_id, acquisition_id, payload, digest, received, persisted, usable, raw in rows:
        data = json.loads(payload)
        if data.get('source_id') != source_id or data.get('acquisition_id') != acquisition_id:
            raise ValueError('MARKET_ACQUISITION_IDENTITY_MISMATCH')
        for quote in data.get('quotes',[]):
            candidate = _hash(_canonical([source_id,acquisition_id,quote.get('outcome')]))
            if candidate != evidence_id:
                continue
            if data.get('source_hash') != digest or _hash(bytes(raw)) != digest:
                raise ValueError('SOURCE_HASH_MISMATCH')
            result = {key:value for key,value in data.items() if key != 'quotes'}
            result.update(quote,evidence_id=candidate,received_at=received,persisted_at=persisted,
                          usable_at=usable,source_hash=digest,source_reference='sqlite:raw_sources/'+digest,
                          clock_mode='operational')
            _verify_market_source_binding(result,bytes(raw))
            try:
                result['source_raw']=bytes(raw).decode('utf-8')
            except UnicodeDecodeError:
                result['source_raw_base64']=base64.b64encode(bytes(raw)).decode('ascii')
            return result
    return None


def _verify_market_source_binding(quote, raw):
    """Prove that a stored quote matches its retained source bytes."""
    from .. import football_data
    if quote.get('adapter_version') == football_data.TRANSFORM_VERSION:
        from ..scenario import _verify_archival_source
        _verify_archival_source(quote,raw)
        return
    try:
        prefix=raw.decode('utf-8-sig').lstrip()[:1]
        source_items=market_store._snapshots(raw,'.json' if prefix in ('[','{') else '.csv')
        matches=[item for item in source_items if item.get('source_id')==quote['source_id']
                 and item.get('acquisition_id')==quote['acquisition_id']]
        if len(matches) != 1:
            raise ValueError('MARKET_SOURCE_BINDING_UNPROVED')
        normalized=market_store._normalize(matches[0],quote['received_at'],False)
        fields=('source_id','provider_id','feed_id','adapter_version','acquisition_id','data_origin',
                'event_id','competition','home','away','market_type','period','status','settlement','line')
        if any(normalized.get(key)!=quote.get(key) for key in fields):
            raise ValueError('MARKET_SOURCE_BINDING_UNPROVED')
        candidates=[item for item in normalized['quotes'] if item['outcome']==quote['outcome']]
        if len(candidates)!=1 or any(candidates[0].get(key)!=quote.get(key) for key in ('odds_original','odds_format')):
            raise ValueError('MARKET_SOURCE_BINDING_UNPROVED')
    except (UnicodeError,KeyError,TypeError,ValueError) as exc:
        raise ValueError('MARKET_SOURCE_BINDING_UNPROVED') from exc


def _resolve_evidence(db, evidence_id, cutoff):
    """Resolve a cutoff-eligible memory record or retained OpenFootball row."""
    evidence_id = _text(evidence_id,'evidence_id')
    cutoff = _utc(cutoff)
    _schema(db)
    row = db.execute('''SELECT r.kind,r.record_id,r.payload,r.fingerprint,c.received_at,c.persisted_at,c.usable_at
        FROM cognitive_records r JOIN cognitive_receipts c ON r.record_id=c.record_id
        WHERE r.kind IN ('model','prediction','outcome','task','evaluation','hypothesis')
        AND r.record_id=? AND c.received_at<=? AND c.persisted_at<=? AND c.usable_at<=?''',
        (evidence_id,cutoff,cutoff,cutoff)).fetchone()
    if row:
        kind,record_id,payload,fingerprint,received,persisted,usable=row
        if _hash(payload.encode('utf-8')) != fingerprint:
            raise ValueError('MEMORY_CONTENT_HASH_MISMATCH')
        content=json.loads(payload)
        return {'evidence_id':record_id,'source_id':'cognitive-memory','source_hash':fingerprint,
                'source_raw':payload,'source_reference':'sqlite:cognitive_records/'+record_id,
                'source_published_at':None,'received_at':received,'persisted_at':persisted,'usable_at':usable,
                'data_origin':'model_state','record_kind':kind,'original_data_origin':content.get('data_origin'),
                'transformation':VERSION,'availability_mode':'OPERATIONAL_AS_OF_RECEIPT'}
    source=_source_rows(db,cutoff).get(evidence_id)
    if source is None:
        return _market_evidence(db,evidence_id,cutoff)
    _verify_source(db,source)
    raw=db.execute('SELECT bytes FROM raw_sources WHERE source_hash=?',(source['source_hash'],)).fetchone()
    if raw is None:
        raise ValueError('SOURCE_NOT_RETAINED')
    result=_source_snapshot(source)
    result.update(source_raw=bytes(raw[0]).decode('utf-8'),
                  source_reference='sqlite:raw_sources/'+source['source_hash'])
    return result


def resolve_evidence(db_path, evidence_id, cutoff):
    with closing(sqlite3.connect(str(db_path),timeout=10)) as db:
        return _resolve_evidence(db,evidence_id,cutoff)


def _string_list(value, field):
    if not isinstance(value,list) or any(not isinstance(item,str) or not item.strip() for item in value):
        raise ValueError('INVALID_' + field.upper())
    result=[item.strip() for item in value]
    if len(result) != len(set(result)):
        raise ValueError('DUPLICATE_' + field.upper())
    return result


def _record_hypothesis(db, draft):
    """Append a validated hypothesis revision without mutating its predecessors."""
    if not isinstance(draft,dict):
        raise ValueError('HYPOTHESIS_DRAFT_REQUIRED')
    received = _now()
    hypothesis_id = _text(draft.get('hypothesis_id'),'hypothesis_id')
    revision = draft.get('revision')
    if type(revision) is not int or revision < 1:
        raise ValueError('INVALID_HYPOTHESIS_REVISION')
    body = {'hypothesis_id':hypothesis_id,'revision':revision,
            'claim':_text(draft.get('claim'),'claim'),
            'supporting_evidence_ids':_string_list(draft.get('supporting_evidence_ids'),'supporting_evidence_ids'),
            'contradicting_evidence_ids':_string_list(draft.get('contradicting_evidence_ids'),'contradicting_evidence_ids'),
            'assumptions':_string_list(draft.get('assumptions'),'assumptions'),
            'missing_information':_string_list(draft.get('missing_information'),'missing_information'),
            'next_question':_text(draft.get('next_question'),'next_question'),
            'source_id':_text(draft.get('source_id','user-supplied-hypothesis'),'source_id')}
    if set(body['supporting_evidence_ids']) & set(body['contradicting_evidence_ids']):
        raise ValueError('CONFLICTING_HYPOTHESIS_EVIDENCE_LINK')
    natural_key = _canonical([hypothesis_id,revision]).decode('utf-8')
    prior = _existing(db,'hypothesis',natural_key)
    if prior:
        stored,receipt=prior
        if any(stored.get(key) != value for key,value in body.items()):
            raise ValueError('MEMORY_IDENTITY_COLLISION')
        return receipt
    references = body['supporting_evidence_ids'] + body['contradicting_evidence_ids']
    source_rows = _source_rows(db,received)
    ambiguous = _ambiguous_fixture_identities(db,received)
    for evidence_id in references:
        if _resolve_evidence(db,evidence_id,received) is None:
            raise ValueError('UNKNOWN_HYPOTHESIS_EVIDENCE')
        if evidence_id in source_rows and _row_has_ambiguous_identity(source_rows[evidence_id],ambiguous):
            raise ValueError('AMBIGUOUS_HYPOTHESIS_EVIDENCE')
    records = [item for item in _as_of(db,received)['hypotheses'] if item['hypothesis_id']==hypothesis_id]
    records.sort(key=lambda item:item['revision'])
    expected_revision = records[-1]['revision'] + 1 if records else 1
    if revision != expected_revision:
        raise ValueError('HYPOTHESIS_REVISION_OUT_OF_ORDER')
    body.update(supersedes_record_id=records[-1]['record_id'] if records else None,
                unsupported_claim=not bool(body['supporting_evidence_ids']),
                data_origin='hypothesis',transformation='structured-hypothesis/1')
    return _append(db,'hypothesis',natural_key,body,received)


def record_hypothesis(db_path, draft):
    with closing(sqlite3.connect(str(db_path),timeout=10)) as db:
        return _record_hypothesis(db,draft)


def latest_hypotheses(db_path, cutoff):
    """Return each hypothesis's highest revision eligible by the cutoff."""
    records=as_of(db_path,cutoff)['hypotheses']
    latest={}
    for record in records:
        if record['hypothesis_id'] not in latest or record['revision'] > latest[record['hypothesis_id']]['revision']:
            latest[record['hypothesis_id']]=record
    return [latest[key] for key in sorted(latest)]


def _record_evaluation(db, draft):
    """Recompute observed prediction scores and persist one comparable metric.

    Draft identifies the group and cutoff; caller cannot supply the score or
    substitute retrospective holdout output. Every supporting record resolves
    against retained receipts at the evaluation cutoff. Calculation and record
    availability are actual current times, not the input cutoff.
    """
    from . import evaluation, models
    if not isinstance(draft,dict):
        raise ValueError('EVALUATION_DRAFT_REQUIRED')
    started = _now()
    run_id = _text(draft.get('run_id'),'run_id')
    model = _text(draft.get('model_name'),'model_name')
    version = _text(draft.get('model_version'),'model_version')
    metric = _text(draft.get('metric'),'metric')
    if model not in models.NAMES or version != models.VERSION:
        raise ValueError('UNSUPPORTED_EVALUATION_MODEL')
    if metric not in ('brier','log_loss'):
        raise ValueError('UNSUPPORTED_EVALUATION_METRIC')
    cutoff = _utc(draft.get('evaluation_cutoff'))
    if _time(cutoff) > _time(started):
        raise ValueError('EVALUATION_CUTOFF_IN_FUTURE')
    scope = {key:_text(draft.get(key),key) for key in ('source_id','competition','period','settlement')}
    natural = run_id + ':' + model + ':' + metric
    prior = _existing(db,'evaluation',natural)
    if prior:
        payload,receipt = prior
        if (payload.get('model') != model or payload.get('model_version') != version or
                payload.get('metric') != metric or payload.get('evaluation_cutoff') != cutoff or
                payload.get('evaluation_scope') != scope):
            raise ValueError('MEMORY_IDENTITY_COLLISION')
        return receipt
    view = _as_of(db,cutoff)
    report = evaluation.evaluate_observed(view,cutoff)
    groups=[group for group in report['groups'] if group.get('model_name') == model
            and group.get('model_version') == version and group.get('evaluation_scope') == scope]
    if len(groups) != 1:
        raise ValueError('EVALUATION_GROUP_UNAVAILABLE_OR_AMBIGUOUS')
    group=groups[0]
    identities=_ambiguous_fixture_identities(db,cutoff)
    source_rows=_source_rows(db,cutoff)
    for case in group['cases']:
        if any(eid in source_rows and _row_has_ambiguous_identity(source_rows[eid],identities)
               for eid in case['evidence_ids']):
            raise ValueError('EVALUATION_FIXTURE_MAPPING_AMBIGUOUS')
    measured=group['metrics'][metric]
    count=measured['sample_size']
    loss=measured['value']
    if type(count) is not int or count < 1 or loss is None:
        raise ValueError('NO_SCORED_OPERATIONAL_PREDICTIONS')
    value=Decimal(str(loss))
    if not value.is_finite() or value < 0:
        raise ValueError('INVALID_EVALUATION_LOSS')
    fixture_keys = sorted(case['fixture_key'] for case in group['cases'])
    if len(fixture_keys) != len(set(fixture_keys)) or len(fixture_keys) != count:
        raise ValueError('EVALUATION_DUPLICATE_FIXTURE_PREDICTIONS')
    supporting = sorted(set(measured['evidence_ids']))
    if not supporting:
        raise ValueError('EVALUATION_LINEAGE_REQUIRED')
    for evidence_id in supporting:
        if _resolve_evidence(db,evidence_id,cutoff) is None:
            raise ValueError('EVALUATION_SUPPORT_NOT_ELIGIBLE')
    finished=_now()
    if _time(finished) < _time(cutoff):
        raise ValueError('CLOCK_MOVED_BACKWARDS')
    payload={'run_id':run_id,'model':model,'model_version':version,'evaluation_cutoff':cutoff,
             'evaluation_end':finished,'evaluation_scope':scope,'metric':metric,'loss':float(value),
             'sample_size':count,'sample_variance':measured['sample_variance'],'fixture_keys':fixture_keys,
             'supporting_evidence_ids':supporting,'cases':group['cases'],
             'coverage':group['coverage'],'calibration_bins':group['calibration_bins'],
             'accuracy':group['metrics'].get('accuracy'),
             'data_origin':'model_state','source_id':'cognitive-memory',
             'transformation':{'version':evaluation.VERSION,'formula':'recomputed observed prediction loss from eligible immutable records'},
             'interpretation':'Measured operational prediction results; sample size and limitations remain explicit.',
             'limitations':['Receipt-visibility precision remains subject to storage evidence.',
                            'Small samples can be unstable; observed scores do not establish future performance.']}
    return _append(db,'evaluation',natural,payload,finished)


def record_evaluation(db_path, draft):
    with closing(sqlite3.connect(str(db_path),timeout=10)) as db:
        return _record_evaluation(db,draft)
