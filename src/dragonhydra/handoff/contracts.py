from ..config import PROJECT_ROOT

MAX_MANIFEST_BYTES = 1_000_000
MAX_ARTIFACT_BYTES = 5_000_000
PROVENANCE = {'codex-desktop':'DESKTOP_CONFIRMED','human-browser':'MANUAL',
              'python-fetch':'CLI_FETCHED','test-fixture':'SYNTHETIC'}


def text(maximum=2000, **extra):
    return dict(type='string', minLength=1, maxLength=maximum, **extra)


def obj(properties, required=None):
    return {'type':'object','properties':properties,'required':list(properties) if required is None else required,
            'additionalProperties':False}


TIME = text(40,format='date-time')
CONF = {'type':'number','minimum':0,'maximum':1}
SOURCE = obj(dict(source_id=text(80,pattern=r'^[a-zA-Z0-9_-]+$'),url=text(2048),title=text(240),
    source_type=text(32,enum=['PUBLIC_DATASET','PUBLIC_PAGE','PUBLIC_API','SYNTHETIC']), observed_at=TIME,
    access_method=text(40,enum=['rendered-browser','manual-browser','python-fetch','synthetic']),
    terms_status=text(40,enum=['ALLOWED_RESEARCH','UNVERIFIED','PROHIBITED','NOT_APPLICABLE']),
    robots_status=text(40,enum=['ALLOWED','ABSENT','DISALLOWED','UNVERIFIED','NOT_APPLICABLE']),
    license_status=text(40,enum=['CC0-1.0','RESEARCH_ONLY','UNVERIFIED','NOT_APPLICABLE']),confidence=CONF))
ARTIFACT = obj(dict(relative_path=text(300),sha256=text(64,pattern=r'^[a-f0-9]{64}$'),
    media_type=text(80,enum=['application/json','text/plain','text/csv','image/png','image/jpeg']),
    size_bytes={'type':'integer','minimum':0,'maximum':MAX_ARTIFACT_BYTES},downloaded_at=TIME))
OBSERVATION = obj(dict(observation_type=text(80),entity_type=text(80),entity_name=text(240),
    value={'type':['string','number','boolean','null'],'maxLength':2000},unit={'type':['string','null'],'maxLength':80},
    observed_at=TIME,effective_at={'type':['string','null'],'format':'date-time','maxLength':40},
    source_id=text(80),confidence=CONF,synthetic={'type':'boolean'}))
SCHEMA = dict(obj(dict(schema_version={'const':'1.0','type':'string'},handoff_id=text(36,format='uuid'),
    producer=text(32,enum=list(PROVENANCE)),created_at=TIME,task=text(1000),project_root={'const':str(PROJECT_ROOT),'type':'string'},
    capture_method=text(40,enum=['desktop-browser','human-browser','python-fetch','synthetic']),
    status=text(16,enum=['SUCCESS','BLOCKED']),sources={'type':'array','minItems':1,'maxItems':5,'items':SOURCE},
    artifacts={'type':'array','maxItems':10,'items':ARTIFACT},observations={'type':'array','maxItems':100,'items':OBSERVATION},
    notes={'type':'string','maxLength':4000},reason={'type':['string','null'],'maxLength':1000},
    observed_failure={'type':['string','null'],'maxLength':2000},browser_evidence={'type':['string','null'],'maxLength':2000})),
    **{'$schema':'https://json-schema.org/draft/2020-12/schema','title':'BrowserHandoffEnvelope v1'})
