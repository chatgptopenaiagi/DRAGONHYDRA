"""Authenticated-route projections backed only by read-only retained reads."""
from contextlib import closing
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

from .. import source_context
from ..cognition import memory
from ..product import API, identity, now
from . import statsbomb_context as binding, statsbomb_context_parser as parser


def _connect(product):
    db = sqlite3.connect(Path(product.db_path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    db.execute('PRAGMA query_only=ON')
    return db


def resolve_match(product,match_id):
    """Find retained identity without Product.rows/find's schema helpers."""
    with closing(_connect(product)) as db:
        db.execute('BEGIN')
        rows = db.execute('''SELECT o.provider,o.source_record_id,o.id FROM connector_observations o
            WHERE o.seq=(SELECT MAX(n.seq) FROM connector_observations n
            WHERE n.provider=o.provider AND n.source_record_id=o.source_record_id)''')
        for provider,native_id,observation_id in rows:
            if identity('fixture',provider,native_id) == match_id:
                if not isinstance(observation_id,str) or not re.fullmatch('[a-f0-9]{64}',observation_id):
                    raise ValueError('MATCH_OBSERVATION_ID_INVALID')
                return {'provider':provider,'source_record_id':native_id,'evidence_id':observation_id}
        cutoff = now()
        public = db.execute('''SELECT DISTINCT f.source_id,f.fixture_key FROM public_fixture_records f
            JOIN public_result_captures c USING(source_id,acquisition_id)
            JOIN public_result_receipts r USING(source_id,acquisition_id)
            WHERE c.received_at<=? AND r.persisted_at<=? AND r.usable_at<=?''',(cutoff,cutoff,cutoff))
        for provider,native_id in public:
            if identity('fixture',provider,native_id) == match_id:
                return {'provider':provider,'source_record_id':native_id,'evidence_id':None}
    raise LookupError('MATCH_NOT_FOUND')


def _head(product):
    """Expose immutable references only if the stored chain itself verifies."""
    try:
        with closing(_connect(product)) as db:
            db.execute('BEGIN')
            if source_context._tables(db) != source_context.TABLES:
                return None
            chain = memory._revision_chain(db,source_context.KIND,
                source_context.scope_key(binding.PROVIDER,binding.MATCH_ID))
            return chain[-1] if chain else None
    except (ValueError,KeyError,TypeError,RecursionError,sqlite3.DatabaseError):
        return None


def _documents(item):
    return [{**item['documents'][role], 'role':role,
             'metadata_url':API+'/connections/'+binding.PROVIDER+'/acquisitions/'+quote(item['documents'][role]['id'],safe='')}
            for role in binding.ROLE_URLS]


def _read(product,match_id,*,with_events=False,offset=0,limit=200):
    row = resolve_match(product,match_id)
    supported = row['provider'] == binding.PROVIDER and row['source_record_id'] == binding.MATCH_ID
    result = {'supported':supported,'availability':'unsupported','match_id':match_id,
        'provider':row['provider'],'source_record_id':row['source_record_id'],
        'parent_observation_id':row['evidence_id'],'context_parent_observation_id':None,
        'context_record_id':None,'parser_version':parser.VERSION,'documents':[],
        'attribution':parser.ATTRIBUTION,
        'reason':'Source context is supported only for the selected StatsBomb match 3869685.'}
    if not supported:
        return result
    raw_dir = product.state/'raw'/'connectors'
    pages = {}
    if with_events:
        def validate(db,payload):
            pages[payload['revision']] = parser.read_event_page(db,raw_dir,payload,offset=offset,limit=limit)
    else:
        validate = parser.make_validator(raw_dir)
    try:
        retained = source_context.latest(product.db_path,binding.PROVIDER,binding.MATCH_ID,
            parent_observation_id=row['evidence_id'],validate_dependencies=validate)
    except (RecursionError,OSError):
        retained = {'availability':'unavailable','code':'CONTEXT_READ_FAILED'}
    availability,item = retained['availability'],retained.get('item')
    result['availability'] = availability
    result['reason'] = {
        'not_requested':'No retained context has been requested for this match.',
        'parent_changed':'Retained context belongs to an earlier parent observation. Request context for the current observation.',
        'unavailable':'Retained context could not be verified. Existing match metadata remains available.',
        'available':'Retained source-native context verified against its exact parent and acquisitions.'}[availability]
    if item is None:
        head = _head(product) if availability == 'unavailable' else None
        if head:
            result['context_record_id'] = head['record_id']
            parent = head['payload'].get('parent')
            if (isinstance(parent,dict) and isinstance(parent.get('observation_id'),str)
                    and re.fullmatch('[a-f0-9]{64}',parent['observation_id'])):
                result['context_parent_observation_id'] = parent['observation_id']
        if availability == 'unavailable':
            code = retained.get('code','')
            result['code'] = code if re.fullmatch('[A-Z0-9_]{1,100}',code) else 'CONTEXT_UNAVAILABLE'
        return result
    result.update(context_record_id=item['record_id'],context_parent_observation_id=item['parent']['observation_id'],
                  documents=_documents(item),received_at=item['received_at'],persisted_at=item['persisted_at'],
                  usable_at=item['usable_at'],availability_mode=item['availability_mode'])
    if availability == 'available':
        result['projection'] = item['projection']
        if with_events:
            result.update(pages[item['revision']])
    return result


def context(product,match_id):
    return _read(product,match_id)


def events(product,match_id,*,offset=0,limit=200):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= parser.MAX_PAGE:
        raise ValueError('INVALID_SOURCE_EVENT_PAGE')
    return _read(product,match_id,with_events=True,offset=offset,limit=limit)
