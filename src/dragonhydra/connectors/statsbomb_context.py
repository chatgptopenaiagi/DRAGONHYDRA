"""Read-only binding validation for one explicitly selected StatsBomb match.

No HTTP, database initialization or context writes occur here. The callback
proves parent match metadata and exact retained acquisition bytes/receipts.
It deliberately does NOT parse events/lineups or verify a caller's projection;
that parser must be composed with this validator before application writes are
enabled. Opaque synthetic bytes can prove binding without proving sports data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from ..cognition import memory
from . import research
from .core import ConnectorError, Document
from .store import PROVENANCE_FIELD, Store, digest, semantic_digest


PROVIDER = 'statsbomb'
MATCH_ID = '3869685'
COMPETITION_ID = 43
SEASON_ID = 106
HOME_TEAM_ID = 779
AWAY_TEAM_ID = 771
EVENT_DATE = '2022-12-18'
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
ROLE_URLS = {role:'https://raw.githubusercontent.com/hudl/open-data/master/data/'+role+'/'+MATCH_ID+'.json'
             for role in ('events','lineups')}
_DOCUMENT_FIELDS = ('id','provider','sha256','original_url','resolved_url','captured_at')
_PARENT_PATHS = {'catalog':'competitions.json', 'matches':'matches/43/106.json'}


def _fail(code):
    raise ValueError('STATSBOMB_CONTEXT_' + code)


def _json(raw):
    # Ambiguous duplicate keys and non-JSON numeric constants cannot establish
    # an exact source identity, even if Python's default decoder accepts them.
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result:
                _fail('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    if isinstance(raw,str):
        raw = raw.encode('utf-8')
    if not isinstance(raw,bytes):
        _fail('INVALID_JSON')
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs,
                          parse_constant=lambda _: _fail('INVALID_JSON'))
    except (UnicodeError, json.JSONDecodeError):
        _fail('INVALID_JSON')


def _receipt(db, ident):
    if not isinstance(ident,str) or not ident:
        _fail('ACQUISITION_ID_REQUIRED')
    retained = Store._acquisition_row(db,ident)
    if retained is None:
        _fail('ACQUISITION_MISSING')
    if retained['provider'] != PROVIDER:
        _fail('PROVIDER_MISMATCH')
    if retained['http_status'] != 200:
        _fail('ACQUISITION_NOT_SUCCESSFUL')
    if retained['adapter_version'] != PROVIDER+'/1':
        _fail('ADAPTER_VERSION_UNSUPPORTED')
    try:
        memory._time(retained['captured_at'])
    except ValueError:
        _fail('ACQUISITION_CLOCK_INVALID')
    return retained


def _metadata(receipt):
    return {key:receipt[key] for key in _DOCUMENT_FIELDS}


def _body(raw_dir, receipt, maximum):
    digest_value = receipt['sha256']
    if (not isinstance(digest_value,str) or not re.fullmatch('[a-f0-9]{64}',digest_value)
            or receipt['raw_reference'] != digest_value+'.payload'):
        _fail('RAW_REFERENCE_INVALID')
    if type(receipt['bytes']) is not int or not 0 <= receipt['bytes'] <= maximum:
        _fail('PAYLOAD_LIMIT')
    root = Path(raw_dir).resolve()
    path = root/receipt['raw_reference']
    if path.is_symlink() or path.resolve().parent != root:
        _fail('RAW_REFERENCE_INVALID')
    try:
        if not path.is_file():
            _fail('RAW_MISSING')
        with path.open('rb') as incoming:
            raw = incoming.read(maximum+1)
    except OSError:
        _fail('RAW_MISSING')
    if len(raw) > maximum:
        _fail('PAYLOAD_LIMIT')
    if len(raw) != receipt['bytes'] or hashlib.sha256(raw).hexdigest() != digest_value:
        _fail('RAW_INTEGRITY_FAILURE')
    return raw


def _parent_url(receipt, role):
    suffix = _PARENT_PATHS[role]
    if receipt['original_url'] != research.STATSBOMB_BASE+suffix:
        _fail('PARENT_URL_MISMATCH')
    allowed = {'https://raw.githubusercontent.com/hudl/open-data/'+branch+'/data/'+suffix
               for branch in ('master','refs/heads/master')}
    if receipt['resolved_url'] not in allowed:
        _fail('PARENT_URL_MISMATCH')


def _summary_matches(receipt, summary):
    return (isinstance(summary,dict) and type(summary.get('bytes')) is int
        and all(isinstance(summary.get(key),str) for key in ('id','sha256','url','resolved_url'))
        and all(summary.get(right) == receipt[left] for left,right in
        (('id','id'),('sha256','sha256'),('original_url','url'),('resolved_url','resolved_url'),('bytes','bytes'))))


def _catalog_receipt(db, record, primary):
    """Resolve an exact saved binding, or the legacy original sync cohort."""
    required = Store.references(record)
    catalog_hash = record.get('attributes',{}).get('catalog_sha256')
    if catalog_hash not in required or len(required) != 2:
        _fail('PARENT_DEPENDENCIES_INVALID')
    saved = record.get(PROVENANCE_FIELD)
    if saved is not None:
        if (not isinstance(saved,dict) or saved.get('version') != 1 or saved.get('provider') != PROVIDER
                or not isinstance(saved.get('documents'),dict) or set(saved['documents']) != set(required)):
            _fail('PARENT_BINDINGS_INVALID')
        chosen = {}
        for source_hash,references in required.items():
            binding = saved['documents'][source_hash]
            if (not isinstance(binding,dict) or binding.get('references') != references
                    or not isinstance(binding.get('acquisition'),dict)):
                _fail('PARENT_BINDINGS_INVALID')
            receipt = _receipt(db,binding['acquisition'].get('id'))
            if receipt['sha256'] != source_hash or Store._acquisition_metadata(receipt) != binding['acquisition']:
                _fail('PARENT_BINDING_METADATA_MISMATCH')
            chosen[source_hash] = receipt
        if chosen[record['source_document_sha256']]['id'] != primary['id']:
            _fail('PARENT_PRIMARY_BINDING_MISMATCH')
        return chosen[catalog_hash]

    # Historical normalized records declare only a catalog hash. A matching
    # hash alone cannot establish which capture belongs to their parent.
    candidates = {}
    for (raw_result,) in db.execute("SELECT result FROM connector_attempts WHERE provider=? AND operation='sync' AND status='succeeded' AND result IS NOT NULL",(PROVIDER,)):
        result = _json(raw_result)
        acquisitions = result.get('acquisitions') if isinstance(result,dict) else None
        if not isinstance(acquisitions,list):
            continue
        if not any(isinstance(item,dict) and item.get('id') == primary['id'] for item in acquisitions):
            continue
        if result.get('provider') != PROVIDER or len(acquisitions) != 2:
            _fail('LEGACY_COHORT_INVALID')
        ids = [item.get('id') if isinstance(item,dict) else None for item in acquisitions]
        if any(not isinstance(ident,str) or not ident for ident in ids) or len(set(ids)) != 2:
            _fail('LEGACY_COHORT_INVALID')
        receipts = [_receipt(db,ident) for ident in ids]
        if any(not _summary_matches(receipt,summary) for receipt,summary in zip(receipts,acquisitions)):
            _fail('LEGACY_COHORT_METADATA_MISMATCH')
        catalog = [receipt for receipt in receipts if receipt['sha256'] == catalog_hash]
        if len(catalog) != 1 or primary['id'] not in ids:
            _fail('LEGACY_COHORT_INVALID')
        candidates[catalog[0]['id']] = catalog[0]
    if len(candidates) != 1:
        _fail('LEGACY_COHORT_UNRESOLVED')
    return next(iter(candidates.values()))


def _document(receipt, raw):
    return Document(receipt['original_url'],receipt['resolved_url'],raw,receipt['captured_at'],receipt['sha256'],
                    receipt['content_type'],receipt['id'],receipt['raw_reference'],receipt['http_status'])


def parent_binding(db, raw_dir, observation_id):
    """Reconstruct the fixed selected parent using this connection and files.

    The legacy observation ID is looked up exactly; an unsupported historical
    ID hashing algorithm is not guessed. Its FK, original bytes, normalized
    content and retained content hash are independently checked instead.
    """
    if not isinstance(observation_id,str) or not observation_id:
        _fail('PARENT_ID_REQUIRED')
    row = db.execute('''SELECT id,provider,source_record_id,sport,event_date,status,content_hash,
        acquisition_id,received_at,usable_at,record FROM connector_observations WHERE id=?''',(observation_id,)).fetchone()
    if row is None:
        _fail('PARENT_MISSING')
    columns = ('id','provider','source_record_id','sport','event_date','status','content_hash',
               'acquisition_id','received_at','usable_at','record')
    observation = dict(zip(columns,row))
    if observation['provider'] != PROVIDER or observation['source_record_id'] != MATCH_ID:
        _fail('PARENT_SELECTION_MISMATCH')
    record = _json(observation['record'])
    if not isinstance(record,dict):
        _fail('PARENT_RECORD_INVALID')
    clean = {key:value for key,value in record.items() if key != PROVENANCE_FIELD}
    try:
        Store.validate(clean)
    except (ValueError,KeyError,TypeError):
        _fail('PARENT_RECORD_INVALID')
    if observation['content_hash'] not in (digest(clean),semantic_digest(clean)):
        _fail('PARENT_CONTENT_HASH_MISMATCH')
    primary = _receipt(db,observation['acquisition_id'])
    if primary['sha256'] != record.get('source_document_sha256'):
        _fail('PARENT_PRIMARY_HASH_MISMATCH')
    catalog = _catalog_receipt(db,record,primary)
    if catalog['id'] == primary['id']:
        _fail('PARENT_DEPENDENCIES_INVALID')
    _parent_url(primary,'matches')
    _parent_url(catalog,'catalog')
    raw_matches = _body(raw_dir,primary,research.MAX_DOCUMENT_BYTES)
    raw_catalog = _body(raw_dir,catalog,research.MAX_DOCUMENT_BYTES)
    matches,competitions = _json(raw_matches),_json(raw_catalog)
    if (not isinstance(matches,list) or not isinstance(competitions,list)
            or len(matches) > 5000 or len(competitions) > 5000
            or any(not isinstance(item,dict) for item in matches+competitions)):
        _fail('PARENT_ARRAY_REQUIRED')
    selected = [item for item in matches if item.get('match_id') == int(MATCH_ID)]
    selected_competitions = [item for item in competitions
                             if item.get('competition_id') == COMPETITION_ID and item.get('season_id') == SEASON_ID]
    if len(selected) != 1 or len(selected_competitions) != 1:
        _fail('PARENT_NATIVE_ID_NOT_UNIQUE')
    native = selected[0]
    if any(not isinstance(native.get(key),dict) for key in ('competition','season','home_team','away_team')):
        _fail('PARENT_NATIVE_IDENTITY_MISMATCH')
    identity = {'match_id':native.get('match_id'),
                'competition_id':(native.get('competition') or {}).get('competition_id'),
                'season_id':(native.get('season') or {}).get('season_id'),
                'home_team_id':(native.get('home_team') or {}).get('home_team_id'),
                'away_team_id':(native.get('away_team') or {}).get('away_team_id'),
                'event_date':native.get('match_date')}
    expected_identity = {'match_id':int(MATCH_ID),'competition_id':COMPETITION_ID,'season_id':SEASON_ID,
                         'home_team_id':HOME_TEAM_ID,'away_team_id':AWAY_TEAM_ID,'event_date':EVENT_DATE}
    if identity != expected_identity or any(type(identity[key]) is not int for key in expected_identity if key != 'event_date'):
        _fail('PARENT_NATIVE_IDENTITY_MISMATCH')
    documents = {research.STATSBOMB_BASE+'competitions.json':_document(catalog,raw_catalog),
                 research.STATSBOMB_BASE+'matches/43/106.json':_document(primary,raw_matches)}
    class RetainedOnly:
        def get(self,url):
            if url not in documents:
                _fail('UNEXPECTED_PARENT_RESOURCE')
            return documents[url]
    try:
        reconstructed = research._statsbomb({'competition_id':COMPETITION_ID,'season_id':SEASON_ID},RetainedOnly(),lambda:None)
    except ConnectorError:
        _fail('PARENT_RECONSTRUCTION_FAILED')
    expected = next(item for item in reconstructed if item['source_record_id'] == MATCH_ID)
    # Capture time is reconstructed from the exact parent receipt too. Only
    # Store's reserved bindings are excluded; unsupported normalized fields
    # (including a fabricated retrieved_at) cannot hide behind semantic hash.
    if digest(clean) != digest(expected):
        _fail('PARENT_RECONSTRUCTION_MISMATCH')
    if (clean.get('attributes',{}).get('captured_at') != primary['captured_at']
            or observation['received_at'] != primary['captured_at']
            or any(observation[key] != expected[key] for key in ('sport','event_date','status'))):
        _fail('PARENT_OBSERVATION_METADATA_MISMATCH')
    try:
        if memory._time(observation['usable_at']) < memory._time(observation['received_at']):
            _fail('PARENT_OBSERVATION_CLOCK_INVALID')
    except (TypeError,ValueError):
        _fail('PARENT_OBSERVATION_CLOCK_INVALID')
    return {'observation_id':observation['id'], 'source_document_sha256':primary['sha256'],
            'observation_content_hash':observation['content_hash'], 'source_record_id':MATCH_ID,
            'native_identity':identity, 'match_list_acquisition':_metadata(primary),
            'catalog_acquisition':_metadata(catalog), 'normalized_record':clean}


def document_binding(db, raw_dir, role, acquisition_id):
    """Prove a role's exact successful receipt and bounded bytes, not its data."""
    return _role_document(db,raw_dir,role,acquisition_id)[0]


def _role_document(db, raw_dir, role, acquisition_id):
    if role not in ROLE_URLS:
        _fail('ROLE_UNSUPPORTED')
    receipt = _receipt(db,acquisition_id)
    if receipt['original_url'] != ROLE_URLS[role] or receipt['resolved_url'] != ROLE_URLS[role]:
        _fail('ROLE_URL_MISMATCH')
    raw = _body(raw_dir,receipt,MAX_DOCUMENT_BYTES)
    return _metadata(receipt),raw


def validate_and_load(db, raw_dir, payload):
    """Validate exact bindings and return each role's once-verified bytes.

    This shared loader remains binding-only; callers must parse/reconstruct
    before treating a supplied projection as verified sports context.
    """
    if not isinstance(payload,dict) or payload.get('provider') != PROVIDER or payload.get('source_record_id') != MATCH_ID:
        _fail('SELECTION_MISMATCH')
    parent = payload.get('parent')
    if not isinstance(parent,dict) or memory._canonical(parent_binding(db,raw_dir,parent.get('observation_id'))) != memory._canonical(parent):
        _fail('PARENT_BINDING_MISMATCH')
    bindings = payload.get('documents')
    if not isinstance(bindings,dict) or set(bindings) != set(ROLE_URLS):
        _fail('TWO_ROLE_BINDINGS_REQUIRED')
    ids,bodies = [],{}
    for role in ROLE_URLS:
        supplied = bindings[role]
        if not isinstance(supplied,dict):
            _fail('ROLE_BINDING_METADATA_MISMATCH')
        actual,raw = _role_document(db,raw_dir,role,supplied.get('id'))
        if actual != supplied:
            _fail('ROLE_BINDING_METADATA_MISMATCH')
        ids.append(supplied['id'])
        bodies[role] = raw
    if len(set(ids)) != 2:
        _fail('DISTINCT_ROLE_BINDINGS_REQUIRED')
    return bodies


def make_binding_validator(raw_dir):
    """Factory for source_context's read-only dependency-validation callback.

    The callback uses only the supplied connection and fresh retained file
    reads. There is no cross-call trust cache, new receipt or capture clock.
    It is a binding prerequisite, not permission to persist unparsed sports
    projections; an actual parser/reconstruction validator remains required.
    """
    root = Path(raw_dir).resolve()
    def validate(db,payload):
        validate_and_load(db,root,payload)
    return validate
