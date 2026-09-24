from uuid import uuid4
from ..config import PROJECT_ROOT
from ..web.contracts import utcnow
from ..web.provenance import encode,digest,exclusive_json
from .contracts import SCHEMA


def synthetic_example(root=PROJECT_ROOT):
    hid=str(uuid4());now=utcnow()
    body=encode({'synthetic':True,'fixture':'DRAGONHYDRA demonstration fixture','home_score':2,'decimal_odds':2.5})
    relative=f'runtime/handoff/browser_downloads/{hid}.json'
    p=root/relative;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as stream:stream.write(body)
    source={'source_id':'bridge-synthetic','url':'https://example.org/dragonhydra-bridge-test',
            'title':'Synthetic bridge test — not Desktop browser research','source_type':'SYNTHETIC',
            'observed_at':now,'access_method':'synthetic','terms_status':'NOT_APPLICABLE',
            'robots_status':'NOT_APPLICABLE','license_status':'NOT_APPLICABLE','confidence':1.0}
    common={'entity_type':'fixture','entity_name':'Synthetic Team A vs Synthetic Team B','observed_at':now,
            'effective_at':None,'source_id':'bridge-synthetic','confidence':1.0,'synthetic':True}
    return {'schema_version':'1.0','handoff_id':hid,'producer':'test-fixture','created_at':now,
            'task':'Verify the supported file bridge with synthetic data','project_root':str(PROJECT_ROOT),
            'capture_method':'synthetic','status':'SUCCESS','sources':[source],
            'artifacts':[{'relative_path':relative,'sha256':digest(body),'media_type':'application/json','size_bytes':len(body),'downloaded_at':now}],
            'observations':[dict(common,observation_type='home_score',value=2,unit='goals'),
                            dict(common,observation_type='decimal_odds',value=2.5,unit='decimal')],
            'notes':'SYNTHETIC: generated locally; no browser used.','reason':None,'observed_failure':None,'browser_evidence':None}


def desktop_template():
    now=utcnow()
    return {'schema_version':'1.0','handoff_id':str(uuid4()),'producer':'codex-desktop','created_at':now,
            'task':'Replace with the actual bounded Desktop research task','project_root':str(PROJECT_ROOT),
            'capture_method':'desktop-browser','status':'BLOCKED',
            'sources':[{'source_id':'openfootball','url':'https://raw.githubusercontent.com/openfootball/football.json/master/2023-24/en.1.json',
                        'title':'OpenFootball Premier League 2023/24','source_type':'PUBLIC_DATASET','observed_at':now,
                        'access_method':'rendered-browser','terms_status':'UNVERIFIED','robots_status':'UNVERIFIED','license_status':'UNVERIFIED','confidence':0.0}],
            'artifacts':[],'observations':[],'notes':'TEMPLATE ONLY — fill actual evidence, regenerate UUID/timestamps before publishing.',
            'reason':'TEMPLATE_ONLY','observed_failure':'Replace with the actual observed failure; never invent a successful capture.','browser_evidence':None}


def install_schemas(root=PROJECT_ROOT):
    for parent in (root/'config',root/'runtime/handoff/schemas'):
        exclusive_json(parent/'browser-handoff-envelope.schema.json',SCHEMA)
    exclusive_json(root/'runtime/handoff/schemas/browser-handoff-example.json',desktop_template())
