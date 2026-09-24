"""Strict schema subset evaluator plus Medusa policy/temporal/artifact gates."""
from dataclasses import dataclass
from datetime import datetime,timezone
import math,re
from uuid import UUID
from .contracts import SCHEMA,PROVENANCE,MAX_MANIFEST_BYTES
from .security import scan_secrets,source_url,read_artifact
from ..web.contracts import PipelineError,timestamp
from ..web.json_api import parse_json
from ..web.provenance import digest,encode
from ..web.terms import load_sources,allow_source


def check_schema(value,schema):
    types=schema.get('type');types=types if isinstance(types,list) else [types]
    actual='null' if value is None else 'boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'number' if isinstance(value,float) else 'string' if isinstance(value,str) else 'object' if isinstance(value,dict) else 'array' if isinstance(value,list) else 'invalid'
    if actual not in types and not (actual=='integer' and 'number' in types):raise PipelineError('INVALID_SCHEMA_TYPE')
    if 'const' in schema and value!=schema['const']:raise PipelineError('INVALID_SCHEMA_CONST')
    if 'enum' in schema and value not in schema['enum']:raise PipelineError('INVALID_SCHEMA_ENUM')
    if isinstance(value,dict):
        props=schema['properties']
        if set(value)-set(props) or set(schema['required'])-set(value):raise PipelineError('UNEXPECTED_OR_MISSING_FIELDS')
        for k,v in value.items():check_schema(v,props[k])
    elif isinstance(value,list):
        if not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',100):raise PipelineError('ARRAY_LIMIT')
        for v in value:check_schema(v,schema['items'])
    elif isinstance(value,str):
        if not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',4000):raise PipelineError('STRING_LIMIT')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'],value):raise PipelineError('INVALID_SCHEMA_PATTERN')
        if schema.get('format')=='date-time':timestamp(value)
        if schema.get('format')=='uuid':
            try:
                if str(UUID(value))!=value:raise ValueError()
            except ValueError:raise PipelineError('INVALID_UUID') from None
    elif actual in ('integer','number'):
        if not math.isfinite(value) or not schema.get('minimum',-1e100)<=value<=schema.get('maximum',1e100):raise PipelineError('INVALID_NUMBER')


@dataclass(frozen=True)
class ValidatedHandoff:
    envelope: dict
    manifest_sha256: str
    normalized: tuple
    normalized_hashes: tuple
    provenance: str
    artifact_bytes: tuple


def validate(raw,root,*,check_artifacts=True):
    if len(raw)>MAX_MANIFEST_BYTES:raise PipelineError('OVERSIZED_MANIFEST')
    scan_secrets(raw)
    envelope=parse_json(raw)
    scan_secrets(envelope)
    check_schema(envelope,SCHEMA)
    if envelope['reason']=='TEMPLATE_ONLY':raise PipelineError('TEMPLATE_NOT_CAPTURED')
    if envelope['project_root']!=str(root):
        # Tests may use a contained temporary realm while keeping the canonical project identity.
        from ..config import PROJECT_ROOT
        if not root.resolve().is_relative_to(PROJECT_ROOT/'runtime/tmp'):raise PipelineError('PROJECT_ROOT_MISMATCH')
    producer=envelope['producer']
    if envelope['capture_method']!={'codex-desktop':'desktop-browser','human-browser':'human-browser','python-fetch':'python-fetch','test-fixture':'synthetic'}[producer]:
        raise PipelineError('PRODUCER_CAPTURE_MISMATCH')
    created=timestamp(envelope['created_at']); now=datetime.now(timezone.utc)
    if created>now:raise PipelineError('FUTURE_TIMESTAMP')
    if envelope['status']=='BLOCKED':
        if not envelope['reason'] or not envelope['observed_failure'] or envelope['observations']:
            raise PipelineError('INVALID_BLOCKED_EVIDENCE')
    elif not envelope['observations'] or not envelope['artifacts']:
        raise PipelineError('SUCCESS_REQUIRES_DATA_AND_ARTIFACT')
    if producer=='codex-desktop' and envelope['status']=='SUCCESS' and not envelope['browser_evidence']:
        raise PipelineError('DESKTOP_EVIDENCE_REQUIRED')
    sources={}
    policies=load_sources(root if (root/'config/web_sources.json').exists() else __import__('dragonhydra.config',fromlist=['PROJECT_ROOT']).PROJECT_ROOT)
    for source in envelope['sources']:
        sid=source['source_id']
        if sid in sources:raise PipelineError('DUPLICATE_SOURCE')
        source_url(source['url'])
        if timestamp(source['observed_at'])>created:raise PipelineError('INVALID_TIMESTAMP_ORDER')
        if source['access_method']!={'codex-desktop':'rendered-browser','human-browser':'manual-browser','python-fetch':'python-fetch','test-fixture':'synthetic'}[producer]:raise PipelineError('ACCESS_METHOD_MISMATCH')
        if envelope['status']=='SUCCESS' and producer!='test-fixture':
            policy=policies.get(sid)
            if policy is None:raise PipelineError('SOURCE_UNKNOWN')
            allow_source(policy,source['url'])
            if source['terms_status']!=policy['terms_status'] or source['license_status']!=policy['license_status']:raise PipelineError('SOURCE_POLICY_MISMATCH')
            if source['robots_status'] not in ('ALLOWED','ABSENT'):raise PipelineError('ROBOTS_UNVERIFIED')
        if producer=='test-fixture' and source['source_type']!='SYNTHETIC':raise PipelineError('SYNTHETIC_SOURCE_REQUIRED')
        sources[sid]=source
    paths,hashes=set(),set();artifact_bytes=[]
    if sum(a['size_bytes'] for a in envelope['artifacts'])>10_000_000:raise PipelineError('ARTIFACT_BATCH_LIMIT')
    for artifact in envelope['artifacts']:
        key=artifact['relative_path'].replace('\\','/').casefold()
        if key in paths or artifact['sha256'] in hashes:raise PipelineError('DUPLICATE_ARTIFACT')
        paths.add(key);hashes.add(artifact['sha256'])
        if timestamp(artifact['downloaded_at'])>created:raise PipelineError('INVALID_TIMESTAMP_ORDER')
        from .security import artifact_path
        artifact_path(root,artifact['relative_path'])
        if check_artifacts:artifact_bytes.append(read_artifact(root,artifact))
    if producer=='codex-desktop' and envelope['status']=='SUCCESS':
        if envelope['browser_evidence'] not in [a['relative_path'] for a in envelope['artifacts']]:
            raise PipelineError('DESKTOP_EVIDENCE_ARTIFACT_REQUIRED')
    normalized=[];seen=set()
    for observation in envelope['observations']:
        source=sources.get(observation['source_id'])
        if source is None:raise PipelineError('OBSERVATION_SOURCE_UNKNOWN')
        observed=timestamp(observation['observed_at'])
        if observed>created or observed>timestamp(source['observed_at']):raise PipelineError('INVALID_TIMESTAMP_ORDER')
        if producer=='test-fixture' and observation['synthetic'] is not True:raise PipelineError('SYNTHETIC_LABEL_REQUIRED')
        if observation['observation_type']=='decimal_odds':
            from ..web.odds import probability
            probability(observation['value'])
        record=dict(observation,source_url=source['url'],source_type=source['source_type'],
                    terms_status=source['terms_status'],license_status=source['license_status'],robots_status=source['robots_status'],
                    handoff_id=envelope['handoff_id'],producer=producer,provenance='SYNTHETIC' if observation['synthetic'] else PROVENANCE[producer],
                    available_at=envelope['created_at'],parser_version='handoff/1.0.0')
        record['confidence']=min(observation['confidence'],source['confidence'])
        payload_hash=digest(encode(record))
        if payload_hash in seen:raise PipelineError('DUPLICATE_OBSERVATION')
        seen.add(payload_hash);normalized.append(record)
    provenance=PROVENANCE[producer]
    if envelope['status']=='BLOCKED' and provenance=='DESKTOP_CONFIRMED':provenance='DESKTOP_BLOCKED'
    return ValidatedHandoff(envelope,digest(raw),tuple(normalized),tuple(digest(encode(r)) for r in normalized),provenance,tuple(artifact_bytes))


def usable_as_of(record,target):
    target=timestamp(target)
    if any(timestamp(record[k])>target for k in ('observed_at','available_at','ingested_at')):
        raise PipelineError('FUTURE_LEAKAGE')
    return True
