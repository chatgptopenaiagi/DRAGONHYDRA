"""Two durable, non-reissuable GET intents for one explicit context job.

The existing mutable attempt row is a private request journal, not context
authority. A crash after intent commit can spend a request without obtaining
usable bytes; recovery never guesses whether that GET reached the provider.
"""
from contextlib import closing, contextmanager
import hashlib
import json
import re
import sqlite3
import time
from uuid import uuid4

from .. import source_context
from ..cognition import memory
from ..jobs import Cancelled, ClaimLost, Interrupted
from . import statsbomb_context as binding, statsbomb_context_parser as parser
from .core import ConnectorError, Transport, utc_now
from .store import Store

VERSION = 'statsbomb-context-job/1'
OPERATION = 'statsbomb_context'
REQUEST_FIELDS = {'provider', 'source_record_id', 'parent', 'parser_version', 'match_id'}
INTENT_FIELDS = {'state', 'claim', 'token', 'url', 'intent_at'}


def _fail(code, message='Context acquisition cannot continue in this job. Submit an explicit new job; retained data remains available.'):
    raise ConnectorError('STATSBOMB_CONTEXT_'+code, message)


@contextmanager
def _readonly(product):
    with closing(source_context._connect(product.db_path, readonly=True)) as db:
        db.execute('BEGIN')
        yield db


def _raw(product):
    return product.state/'raw'/'connectors'


def _request(product, payload):
    expected_match = product.match_id({'source_id':binding.PROVIDER, 'fixture_key':binding.MATCH_ID})
    if (not isinstance(payload, dict) or set(payload) != REQUEST_FIELDS
            or payload['provider'] != binding.PROVIDER or payload['source_record_id'] != binding.MATCH_ID
            or payload['parser_version'] != parser.VERSION or payload['match_id'] != expected_match):
        _fail('REQUEST_INVALID')
    return json.loads(memory._canonical(payload))


def prepare(product, match_id):
    """Freeze an exact retained parent using SELECTs only; never acquire data."""
    from .statsbomb_context_view import resolve_match
    selected = resolve_match(product, match_id)
    if selected['provider'] != binding.PROVIDER or selected['source_record_id'] != binding.MATCH_ID:
        raise ValueError('STATSBOMB_CONTEXT_SELECTION_UNSUPPORTED')
    with _readonly(product) as db:
        parent = binding.parent_binding(db, _raw(product), selected['evidence_id'])
    return _request(product, {'provider':binding.PROVIDER, 'source_record_id':binding.MATCH_ID,
        'parent':parent, 'parser_version':parser.VERSION, 'match_id':match_id})


def _guard(db, job, require_claim):
    current = require_claim(db, job['id'], job['attempts'])
    if current['cancel_requested']:
        raise Cancelled()
    if current['deadline'] and time.time() > current['deadline']:
        raise TimeoutError('JOB_DEADLINE_EXCEEDED')


@contextmanager
def _write(product, job, require_claim):
    with closing(product.connect()) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            _guard(db, job, require_claim)
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise


def attempt_id(job):
    if not isinstance(job.get('id'), str) or not re.fullmatch('[a-f0-9]{32}', job['id']):
        _fail('JOB_INVALID')
    return 'statsbomb-context:'+job['id']


def _journal(db, job, payload):
    row = db.execute('SELECT job_id,provider,operation,status,result FROM connector_attempts WHERE id=?', (attempt_id(job),)).fetchone()
    if row is None:
        return None, None
    if row[:3] != (job['id'], binding.PROVIDER, OPERATION) or row[3] not in ('running','succeeded','failed'):
        _fail('JOURNAL_INVALID')
    try:
        journal = json.loads(row[4])
        if (set(journal) != {'version','request','roles','publication','outcome'} or journal['version'] != VERSION
                or memory._canonical(journal['request']) != memory._canonical(payload)
                or not isinstance(journal['roles'], dict) or set(journal['roles'])-set(binding.ROLE_URLS)
                or (journal['outcome'] is not None and not isinstance(journal['outcome'], dict))):
            _fail('JOURNAL_INVALID')
        publication = journal['publication']
        if publication is not None:
            if (not isinstance(publication, dict)
                    or set(publication) != {'head_record_id','head_revision','semantic_sha256','reuse_record_id'}
                    or type(publication['head_revision']) is not int or publication['head_revision'] < 0
                    or not re.fullmatch('[a-f0-9]{64}', publication['semantic_sha256'])
                    or any(value is not None and (not isinstance(value, str) or not value.startswith('source_context:'))
                           for value in (publication['head_record_id'], publication['reuse_record_id']))):
                _fail('JOURNAL_INVALID')
        for role, entry in journal['roles'].items():
            fields = INTENT_FIELDS | ({'acquisition'} if entry.get('state') == 'complete' else set())
            if (set(entry) != fields or entry['state'] not in ('intent','complete')
                    or type(entry['claim']) is not int or entry['claim'] < 1
                    or not isinstance(entry['token'], str) or not re.fullmatch('[a-f0-9]{32}', entry['token'])
                    or entry['url'] != binding.ROLE_URLS[role]):
                _fail('JOURNAL_INVALID')
            memory._time(entry['intent_at'])
            if entry['state'] == 'complete' and not isinstance(entry['acquisition'], dict):
                _fail('JOURNAL_INVALID')
        return journal, row[3]
    except (ValueError, TypeError, KeyError, AttributeError):
        _fail('JOURNAL_INVALID')


def _save(db, job, journal, *, status='running', error=None):
    # Caller holds the fenced write transaction. The full journal survives
    # terminal diagnostics; generic Store.finish must never erase this budget.
    updated = db.execute("UPDATE connector_attempts SET result=?,status=?,finished_at=?,error=? WHERE id=? AND job_id=? "
        "AND EXISTS(SELECT 1 FROM product_jobs WHERE id=? AND status='running' AND attempts=?)",
        (memory._canonical(journal).decode(), status, utc_now() if status != 'running' else None,
         memory._canonical(error).decode() if error else None, attempt_id(job), job['id'], job['id'], job['attempts']))
    if updated.rowcount != 1:
        raise ClaimLost()


def _start(product, job, payload, require_claim):
    with _write(product, job, require_claim) as db:
        # The submitted parent is immutable; never resolve its newest version.
        actual = binding.parent_binding(db, _raw(product), payload['parent'].get('observation_id'))
        if memory._canonical(actual) != memory._canonical(payload['parent']):
            _fail('PARENT_CHANGED')
        journal, status = _journal(db, job, payload)
        if journal is None:
            journal = {'version':VERSION, 'request':payload, 'roles':{}, 'publication':None, 'outcome':None}
            db.execute('INSERT INTO connector_attempts(id,job_id,provider,operation,started_at,status,result) VALUES(?,?,?,?,?,?,?)',
                (attempt_id(job), job['id'], binding.PROVIDER, OPERATION, utc_now(), 'running', memory._canonical(journal).decode()))
        elif status == 'failed':
            _fail('JOB_FAILED_NEW_JOB_REQUIRED')
        return journal


def _reserve(product, job, payload, role, require_claim):
    with _write(product, job, require_claim) as db:
        journal, status = _journal(db, job, payload)
        if status != 'running' or role in journal['roles']:
            _fail('REQUEST_ALREADY_SPENT')
        intent = {'state':'intent', 'claim':job['attempts'], 'token':uuid4().hex,
                  'url':binding.ROLE_URLS[role], 'intent_at':utc_now()}
        journal['roles'][role] = intent
        _save(db, job, journal)
    # Only this invocation that committed a NEW intent may make its one GET.
    return intent


def _complete(product, job, payload, role, intent, doc, require_claim):
    with _write(product, job, require_claim) as db:
        journal, status = _journal(db, job, payload)
        if status != 'running' or journal['roles'].get(role) != intent:
            _fail('RESERVATION_CHANGED')
        if (doc.url != binding.ROLE_URLS[role] or doc.resolved_url != doc.url
                or type(doc.body) is not bytes or len(doc.body) > binding.MAX_DOCUMENT_BYTES
                or hashlib.sha256(doc.body).hexdigest() != doc.sha256
                or doc.raw_reference != doc.sha256+'.payload'
                or not re.fullmatch('[a-f0-9]{32}', doc.acquisition_id)):
            _fail('RESPONSE_BINDING_INVALID')
        memory._time(doc.captured_at)
        db.execute('INSERT INTO connector_acquisitions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (doc.acquisition_id, binding.PROVIDER, binding.PROVIDER+'/1', doc.url, doc.resolved_url,
             doc.captured_at, doc.sha256, doc.raw_reference, len(doc.body), doc.content_type, doc.http_status))
        acquisition = Store._acquisition_row(db, doc.acquisition_id)
        journal['roles'][role] = dict(intent, state='complete', acquisition=Store._acquisition_metadata(acquisition))
        _save(db, job, journal)


def _load_role(db, product, role, entry):
    acquisition = Store._acquisition_row(db, entry['acquisition'].get('id'))
    if acquisition is None or memory._canonical(Store._acquisition_metadata(acquisition)) != memory._canonical(entry['acquisition']):
        _fail('RECEIPT_CHANGED')
    return binding._role_document(db, _raw(product), role, acquisition['id'])


def _ensure_context_schema(product, job, require_claim):
    with _write(product, job, require_claim) as db:
        tables = source_context._tables(db)
        if tables and tables != source_context.TABLES:
            _fail('SCHEMA_INCOMPLETE')
        if not tables:
            # executescript would implicitly commit and release the claim lock.
            statement = ''
            for line in memory.SCHEMA_SQL.splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    db.execute(statement)
                    statement = ''
            if statement.strip():
                _fail('SCHEMA_INVALID')


def _recover(product, job, validate):
    with _readonly(product) as db:
        tables = source_context._tables(db)
    if tables:
        if tables != source_context.TABLES:
            _fail('SCHEMA_INCOMPLETE')
        return source_context.recover(product.db_path, binding.PROVIDER, binding.MATCH_ID, validate_dependencies=validate)


def _semantic_hash(payload):
    return hashlib.sha256(memory._canonical(source_context._semantic(payload))).hexdigest()


def _chain(db, validate):
    chain = memory._revision_chain(db, source_context.KIND, source_context.scope_key(binding.PROVIDER, binding.MATCH_ID))
    checked = source_context._validator(validate)
    for item in chain:
        checked(db, item['payload'])
    return chain


def _publication(product, job, payload, draft, require_claim, validate):
    with _write(product, job, require_claim) as db:
        journal, _ = _journal(db, job, payload)
        if journal['publication'] is None:
            chain = _chain(db, validate)
            head = chain[-1] if chain else None
            if head and head['received_at'] is None:
                _fail('PENDING_CONTEXT_REQUIRES_RECOVERY')
            semantic = _semantic_hash(draft)
            journal['publication'] = {'head_record_id':head['record_id'] if head else None,
                'head_revision':head['payload']['revision'] if head else 0, 'semantic_sha256':semantic,
                'reuse_record_id':head['record_id'] if head and _semantic_hash(head['payload']) == semantic else None}
            _save(db, job, journal)
        marker = journal['publication']
        if marker['semantic_sha256'] != _semantic_hash(draft):
            _fail('PUBLICATION_CHANGED')
        return marker


def _target(product, marker, validate):
    with _readonly(product) as db:
        chain = _chain(db, validate)
        if marker['reuse_record_id'] is not None:
            return marker['reuse_record_id']
        target = next((item for item in chain if item['payload']['revision'] == marker['head_revision']+1), None)
        if target:
            if (target['payload']['supersedes_record_id'] != marker['head_record_id']
                    or _semantic_hash(target['payload']) != marker['semantic_sha256']):
                _fail('PUBLICATION_CONFLICT_NEW_JOB_REQUIRED')
            return target['record_id']
        head = chain[-1] if chain else None
        if (head['record_id'] if head else None) != marker['head_record_id']:
            _fail('PUBLICATION_CONFLICT_NEW_JOB_REQUIRED')
        return None


def _accepted(product, job, payload, draft, record_id, validate):
    with _readonly(product) as db:
        chain = _chain(db, validate)
        selected = next((item for item in chain if item['record_id'] == record_id), None)
        if selected is None or selected['received_at'] is None or _semantic_hash(selected['payload']) != _semantic_hash(draft):
            _fail('OUTCOME_INVALID')
        body = selected['payload']
        return {'status':'available', 'provider':binding.PROVIDER, 'source_record_id':binding.MATCH_ID,
            'parent_observation_id':payload['parent']['observation_id'], 'parser_version':parser.VERSION,
            'context_record_id':selected['record_id'], 'revision':body['revision'],
            'event_rows':body['projection']['event_summary']['row_count'],
            'source_context_url':'/dragon/api/v1/matches/'+payload['match_id']+'/source-context',
            'availability_mode':'OPERATIONAL_AS_OF_RECEIPT', 'documents':body['documents']}


def _finish(product, job, payload, require_claim, *, outcome=None, error=None):
    with _write(product, job, require_claim) as db:
        journal, _ = _journal(db, job, payload)
        if outcome is not None:
            journal['outcome'] = outcome
        _save(db, job, journal, status='failed' if error else 'succeeded', error=error)


def run(product, job, check, require_claim):
    """Execute/recover one claimed job; normal caller also fences process stop."""
    if job.get('kind') != OPERATION:
        _fail('JOB_INVALID')
    payload = _request(product, job['payload'])
    check()
    journal = _start(product, job, payload, require_claim)
    full_validator = parser.make_validator(_raw(product))

    def validate(db, context_payload):
        _guard(db, job, require_claim)
        full_validator(db, context_payload)

    try:
        # Repair an already durable context before considering any new GET.
        _recover(product, job, validate)
        check()
        if any(entry['state'] == 'intent' for entry in journal['roles'].values()):
            _fail('REQUEST_OUTCOME_UNKNOWN_NEW_JOB_REQUIRED')
        documents, bodies = {}, {}
        with _readonly(product) as db:
            for role, entry in journal['roles'].items():
                documents[role], bodies[role] = _load_role(db, product, role, entry)
        for role in binding.ROLE_URLS:
            if role in documents:
                continue
            check()
            intent = _reserve(product, job, payload, role, require_claim)
            transport = Transport(_raw(product),
                lambda doc, role=role, intent=intent: _complete(product, job, payload, role, intent, doc, require_claim),
                check, max_bytes=binding.MAX_DOCUMENT_BYTES, follow_redirects=False)
            transport.get(binding.ROLE_URLS[role])
            check()
            with _readonly(product) as db:
                current, _ = _journal(db, job, payload)
                documents[role], bodies[role] = _load_role(db, product, role, current['roles'][role])
        projection = parser.parse(bodies['events'], bodies['lineups'], parent=payload['parent'])
        draft = {key:payload[key] for key in ('provider','source_record_id','parent','parser_version')}
        draft.update(documents=documents, projection=projection)
        check()
        if journal['outcome'] is not None:
            result = _accepted(product, job, payload, draft, journal['outcome']['context_record_id'], validate)
            if memory._canonical(result) != memory._canonical(journal['outcome']):
                _fail('OUTCOME_INVALID')
        else:
            _ensure_context_schema(product, job, require_claim)
            marker = _publication(product, job, payload, draft, require_claim, validate)
            target = _target(product, marker, validate)
            if target is None:
                def publish_validate(db, context_payload):
                    validate(db, context_payload)
                    raw = memory._canonical(context_payload)
                    natural = memory._hash(memory._canonical([context_payload['scope'], context_payload['revision']]))
                    ident = source_context.KIND+':'+memory._hash(memory._canonical([source_context.KIND, natural, memory._hash(raw)]))
                    if db.execute('SELECT 1 FROM cognitive_records WHERE record_id=?', (ident,)).fetchone() is None:
                        if (context_payload['revision'] != marker['head_revision']+1
                                or context_payload['supersedes_record_id'] != marker['head_record_id']
                                or _semantic_hash(context_payload) != marker['semantic_sha256']):
                            _fail('PUBLICATION_CONFLICT_NEW_JOB_REQUIRED')
                receipt = source_context.append(product.db_path, draft, validate_dependencies=publish_validate)
                target = receipt['record_id']
            result = _accepted(product, job, payload, draft, target, validate)
        _finish(product, job, payload, require_claim, outcome=result)
        return result
    except (ClaimLost, Cancelled, Interrupted):
        # Never let a stale/cancelled owner erase newer state or its budget.
        raise
    except Exception as error:
        code = error.code if isinstance(error, ConnectorError) else str(error)
        if not isinstance(code, str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,127}', code):
            code = 'STATSBOMB_CONTEXT_OPERATION_FAILED'
        _finish(product, job, payload, require_claim, error={'code':code,
            'message':'Context operation failed. Retained data remains available; an explicit new job is required.'})
        if isinstance(error, ValueError):
            raise ConnectorError(code, 'Retained context documents failed validation; previous context remains available.') from None
        raise
