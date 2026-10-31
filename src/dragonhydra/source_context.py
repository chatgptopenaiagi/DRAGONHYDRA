"""Optional immutable source-context persistence, with no provider acquisition.

This foundation validates structure, revisions and clocks, not sports content.
Every operation requires a trusted dependency validator ``(db, payload)`` that
proves the exact parent observation and both retained acquisition bindings.
It must raise ValueError on failure and perform no network access. SQLite
authorisation restricts that callback to reads. Callers compose provider and
parser validation; accepting a callback alone is not proof of source data.

Records and their receipts commit separately. Stored receipt clocks remain
OPERATIONAL_AS_OF_RECEIPT; the exact receipt transaction visibility is unproven.
"""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

from .cognition import memory

VERSION = 'source-context/1'
KIND = 'source_context'
ROLES = ('events', 'lineups')
TABLES = {'cognitive_records', 'cognitive_receipts'}
DOCUMENT_FIELDS = {'id', 'provider', 'sha256', 'original_url', 'resolved_url', 'captured_at'}
DRAFT_FIELDS = {'provider', 'source_record_id', 'parent', 'documents', 'parser_version', 'projection'}


def _text(value, maximum=128):
    if not isinstance(value, str) or not value or value != value.strip() or len(value.encode('utf-8')) > maximum:
        raise ValueError('CONTEXT_INVALID_TEXT')
    return value


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('CONTEXT_INVALID_SOURCE_HASH')


def scope_key(provider, source_record_id):
    return memory._hash(memory._canonical([KIND, _text(provider, 64), _text(source_record_id)]))


def _structure(payload):
    if set(payload) != DRAFT_FIELDS | {'version', 'scope', 'revision', 'supersedes_record_id', 'record_started_at'}:
        raise ValueError('CONTEXT_PAYLOAD_FIELDS_INVALID')
    if payload.get('version') != VERSION or payload.get('scope') != scope_key(payload.get('provider'), payload.get('source_record_id')):
        raise ValueError('CONTEXT_SCOPE_INVALID')
    parent, documents = payload.get('parent'), payload.get('documents')
    if not isinstance(parent, dict):
        raise ValueError('CONTEXT_PARENT_REQUIRED')
    _text(parent.get('observation_id'))
    _digest(parent.get('source_document_sha256'))
    if not isinstance(documents, dict) or set(documents) != set(ROLES):
        raise ValueError('CONTEXT_TWO_DOCUMENTS_REQUIRED')
    ids = []
    for role in ROLES:
        document = documents[role]
        if not isinstance(document, dict) or set(document) != DOCUMENT_FIELDS:
            raise ValueError('CONTEXT_DOCUMENT_METADATA_REQUIRED')
        ids.append(_text(document['id']))
        if document['provider'] != payload['provider']:
            raise ValueError('CONTEXT_DOCUMENT_PROVIDER_MISMATCH')
        _digest(document['sha256'])
        for key in ('original_url', 'resolved_url'):
            _text(document[key], 2048)
        if memory._time(document['captured_at']) > memory._time(payload['record_started_at']):
            raise ValueError('CONTEXT_CAPTURE_AFTER_RECORD')
    if len(set(ids)) != 2:
        raise ValueError('CONTEXT_DISTINCT_DOCUMENTS_REQUIRED')
    _text(payload.get('parser_version'))
    if not isinstance(payload.get('projection'), dict) or len(memory._canonical(payload)) > 1024 * 1024:
        raise ValueError('CONTEXT_INVALID_PROJECTION')


def _validator(validate_dependencies):
    if not callable(validate_dependencies):
        raise ValueError('CONTEXT_DEPENDENCY_VALIDATOR_REQUIRED')

    def validate(db, payload):
        _structure(payload)
        # Callback mutation must not implicitly commit or alter the chain.
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
        db.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        try:
            # A validator cannot rewrite the object being persisted or read.
            isolated = json.loads(memory._canonical(payload))
            result = validate_dependencies(db, isolated)
            if result is False:
                raise ValueError('CONTEXT_DEPENDENCY_VALIDATION_FAILED')
            if memory._canonical(isolated) != memory._canonical(payload):
                raise ValueError('CONTEXT_VALIDATOR_MUTATION')
        finally:
            db.set_authorizer(None)
    return validate


def _semantic(payload):
    return {key:payload[key] for key in ('provider', 'source_record_id', 'parent', 'parser_version', 'projection')} | {
        'documents':{role:payload['documents'][role]['sha256'] for role in ROLES}}


def _tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('cognitive_records','cognitive_receipts')")}


def _connect(db_path, *, readonly):
    # mode=rw/ro refuses to create a missing database. Reads never initialize it.
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=10)
    if readonly:
        db.execute('PRAGMA query_only=ON')
    else:
        db.execute('PRAGMA foreign_keys=ON')
    return db


def append(db_path, draft, *, validate_dependencies):
    """Append one validated context or reuse its latest semantic duplicate.

    Only explicit writes initialize the exact optional two-table profile.
    Incoming and original retained bindings are independently revalidated.
    Callers cannot supply a revision, predecessor, scope or receipt clock.
    """
    validate = _validator(validate_dependencies)
    if not isinstance(draft, dict) or set(draft) != DRAFT_FIELDS:
        raise ValueError('CONTEXT_DRAFT_REQUIRED')
    # Canonical roundtrip freezes caller-owned mutable dictionaries.
    body = json.loads(memory._canonical(dict(draft, version=VERSION)))
    scope = scope_key(body['provider'], body['source_record_id'])
    with closing(_connect(db_path, readonly=False)) as db:
        tables = _tables(db)
        if tables and tables != TABLES:
            raise ValueError('CONTEXT_SCHEMA_INCOMPLETE')
        if not tables:
            # executescript implicitly commits first: start its own explicit
            # transaction so competing initializers never see half the DDL.
            try:
                db.executescript('BEGIN IMMEDIATE;\n' + memory.SCHEMA_SQL + '\nCOMMIT;')
            except Exception:
                db.rollback()
                raise
        return memory._append_revision(db, KIND, scope, body, _semantic, validate)


def recover(db_path, provider, source_record_id, *, validate_dependencies):
    """Receipt a valid durable pending head without acquiring any new data."""
    validate = _validator(validate_dependencies)
    scope = scope_key(provider, source_record_id)
    with closing(_connect(db_path, readonly=False)) as db:
        if _tables(db) != TABLES:
            raise ValueError('CONTEXT_SCHEMA_INCOMPLETE')
        try:
            db.execute('BEGIN IMMEDIATE')
            chain = memory._revision_chain(db, KIND, scope)
            for item in chain:
                validate(db, item['payload'])
            head = chain[-1] if chain else None
            db.commit()
        except Exception:
            db.rollback()
            raise
        if head is None:
            return {'availability':'not_requested', 'item':None}
        result = memory._revision_receipt(db, KIND, scope, head['record_id'], memory._now(), validate)
        return dict(result, duplicate=True, recovered=head['received_at'] is None)


def _record_id(value):
    return isinstance(value,str) and re.fullmatch(KIND+':[a-f0-9]{64}',value) is not None


def _exact_node(db,record_id):
    """Verify one immutable node; do not inspect other records' payloads."""
    rows = db.execute('''SELECT r.kind,r.record_id,r.natural_key,r.fingerprint,r.payload,
        c.record_id,c.received_at,c.persisted_at,c.usable_at FROM cognitive_records r
        LEFT JOIN cognitive_receipts c ON c.record_id=r.record_id WHERE r.record_id=?''',(record_id,)).fetchall()
    if not rows:
        raise ValueError('CONTEXT_RECORD_NOT_FOUND')
    if len(rows) != 1:
        raise ValueError('CONTEXT_IDENTITY_FORK')
    kind,ident,natural_key,fingerprint,raw,receipt_id,received,persisted,usable = rows[0]
    if kind != KIND:
        raise ValueError('CONTEXT_RECORD_KIND_MISMATCH')
    if ident != record_id or not _record_id(ident):
        raise ValueError('CONTEXT_RECORD_ID_INVALID')
    for value in (natural_key,fingerprint):
        _digest(value)
    if not isinstance(raw,str):
        raise ValueError('CONTEXT_CONTENT_INVALID')
    encoded = raw.encode('utf-8')
    if len(encoded) > 1024*1024 or memory._hash(encoded) != fingerprint:
        raise ValueError('CONTEXT_CONTENT_HASH_MISMATCH')
    try:
        payload = json.loads(raw)
        if not isinstance(payload,dict) or memory._canonical(payload) != encoded:
            raise ValueError()
    except (ValueError,TypeError,RecursionError):
        raise ValueError('CONTEXT_CONTENT_INVALID') from None
    expected_id = KIND+':'+memory._hash(memory._canonical([KIND,natural_key,fingerprint]))
    if ident != expected_id:
        raise ValueError('CONTEXT_RECORD_ID_MISMATCH')
    _structure(payload)
    revision = payload['revision']
    if type(revision) is not int or revision < 1:
        raise ValueError('CONTEXT_REVISION_INVALID')
    if natural_key != memory._hash(memory._canonical([payload['scope'],revision])):
        raise ValueError('CONTEXT_REVISION_KEY_MISMATCH')
    # The exact schema's UNIQUE(kind,natural_key) prevents valid forks. Check
    # this node's canonical slot as well, failing closed if that constraint was
    # damaged. This reads IDs only and never decodes a descendant/unrelated row.
    slot = db.execute('SELECT record_id FROM cognitive_records WHERE kind=? AND natural_key=?',
                      (KIND,natural_key)).fetchall()
    if slot != [(ident,)]:
        raise ValueError('CONTEXT_IDENTITY_FORK')
    if receipt_id is None:
        if any(value is not None for value in (received,persisted,usable)):
            raise ValueError('CONTEXT_RECEIPT_INVALID')
        raise ValueError('CONTEXT_RECEIPT_PENDING')
    if receipt_id != ident:
        raise ValueError('CONTEXT_RECEIPT_INVALID')
    if (memory._time(received) != memory._time(payload['record_started_at']) or
            not memory._time(received) <= memory._time(persisted) <= memory._time(usable)):
        raise ValueError('CONTEXT_RECEIPT_CLOCK_INVALID')
    return {'record_id':ident,'record_content_hash':fingerprint,'payload':payload,
            'received_at':received,'persisted_at':persisted,'usable_at':usable}


def by_id(db_path,record_id,*,validate_dependencies,cutoff=None):
    """Read one receipted version and its immutable predecessor prefix only.

    Every prefix node must satisfy structural/receipt invariants. The trusted
    full dependency validator runs ONCE, on the selected complete snapshot;
    ancestors' old raw documents and later/unrelated payloads are not read.
    Missing/pending/future/corrupt targets never fall back to another version.
    This function only uses a read-only SQLite snapshot and never repairs it.
    """
    validate = _validator(validate_dependencies)
    if not _record_id(record_id):
        raise ValueError('CONTEXT_RECORD_ID_INVALID')
    current = memory._time(memory._now())
    boundary = memory._time(cutoff) if cutoff is not None else current
    if boundary > current:
        raise ValueError('CONTEXT_CUTOFF_IN_FUTURE')
    if not Path(db_path).is_file():
        return {'availability':'unavailable','item':None,'code':'CONTEXT_DATABASE_MISSING'}
    try:
        with closing(_connect(db_path,readonly=True)) as db:
            db.execute('BEGIN')
            tables = _tables(db)
            if not tables:
                raise ValueError('CONTEXT_RECORD_NOT_FOUND')
            if tables != TABLES:
                raise ValueError('CONTEXT_SCHEMA_INCOMPLETE')
            target = None
            scope = None
            expected_revision = None
            successor_usable = None
            seen = set()
            ident = record_id
            while ident is not None:
                if ident in seen:
                    raise ValueError('CONTEXT_REVISION_CYCLE')
                if not _record_id(ident):
                    raise ValueError('CONTEXT_PREDECESSOR_ID_INVALID')
                seen.add(ident)
                node = _exact_node(db,ident)
                body = node['payload']
                if target is None:
                    target,scope,expected_revision = node,body['scope'],body['revision']
                if body['scope'] != scope:
                    raise ValueError('CONTEXT_PREFIX_SCOPE_MISMATCH')
                if body['revision'] != expected_revision:
                    raise ValueError('CONTEXT_REVISION_GAP')
                if any(memory._time(node[key]) > boundary for key in ('received_at','persisted_at','usable_at')):
                    raise ValueError('CONTEXT_RECEIPT_AFTER_CUTOFF')
                if successor_usable is not None and memory._time(node['usable_at']) > successor_usable:
                    raise ValueError('CONTEXT_RECEIPT_CLOCK_INVALID')
                successor_usable = memory._time(node['usable_at'])
                predecessor = body['supersedes_record_id']
                if expected_revision == 1:
                    if predecessor is not None:
                        raise ValueError('CONTEXT_REVISION_CHAIN_INVALID')
                elif predecessor is None:
                    raise ValueError('CONTEXT_REVISION_GAP')
                expected_revision -= 1
                ident = predecessor
            if expected_revision != 0:
                raise ValueError('CONTEXT_REVISION_GAP')
            validate(db,target['payload'])
            item = {**target['payload'],**{key:value for key,value in target.items() if key != 'payload'},
                    'availability_mode':'OPERATIONAL_AS_OF_RECEIPT'}
            return {'availability':'available','item':item}
    except sqlite3.DatabaseError:
        return {'availability':'unavailable','item':None,'code':'CONTEXT_STORAGE_UNAVAILABLE'}
    except (ValueError,TypeError,KeyError,RecursionError) as exc:
        code = str(exc)
        if not re.fullmatch('[A-Z0-9_]{1,100}',code):
            code = 'CONTEXT_CONTENT_INVALID'
        return {'availability':'unavailable','item':None,'code':code}


def latest(db_path, provider, source_record_id, *, parent_observation_id=None, cutoff=None, validate_dependencies):
    """Pure SELECT context lookup on a read-only connection; never repairs.

    An unavailable pending or corrupt head cannot fall back to older context.
    A cutoff selects only receipted revisions eligible at all three clocks.
    """
    validate = _validator(validate_dependencies)
    scope = scope_key(provider, source_record_id)
    if cutoff is not None:
        cutoff = memory._time(cutoff)
    if not Path(db_path).is_file():
        return {'availability':'not_requested', 'item':None}
    try:
        with closing(_connect(db_path, readonly=True)) as db:
            db.execute('BEGIN')
            tables = _tables(db)
            if not tables:
                return {'availability':'not_requested', 'item':None}
            if tables != TABLES:
                raise ValueError('CONTEXT_SCHEMA_INCOMPLETE')
            chain = memory._revision_chain(db, KIND, scope)
            for item in chain:
                validate(db, item['payload'])
            if chain and chain[-1]['received_at'] is None:
                raise ValueError('CONTEXT_RECEIPT_PENDING')
            eligible = [item for item in chain if cutoff is None or all(
                memory._time(item[key]) <= cutoff for key in ('received_at', 'persisted_at', 'usable_at'))]
            if not eligible:
                return {'availability':'not_requested', 'item':None}
            selected = eligible[-1]
            body = selected['payload']
            availability = 'parent_changed' if parent_observation_id is not None and body['parent']['observation_id'] != parent_observation_id else 'available'
            return {'availability':availability, 'item':{**body, **{key:value for key,value in selected.items() if key != 'payload'},
                    'availability_mode':'OPERATIONAL_AS_OF_RECEIPT'}}
    except (ValueError, sqlite3.DatabaseError, KeyError, TypeError) as exc:
        return {'availability':'unavailable', 'item':None, 'code':str(exc)}
