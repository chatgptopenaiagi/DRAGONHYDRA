"""Shared API/auth guard tests with a synthetic logistics engine spy.

No listening server, provider, original database or operational inventory.
The spy verifies delegation; it is not a second logistics implementation.
"""
from contextlib import closing,redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

BASE='/dragon/api/v1/logistics'
TOKEN='virtual-genesis62-api-fixture-not-a-real-key'

class LogisticsSpy:
    contract_version='core-next.engine/1'
    def __init__(self,path,config=None):self.path=path;self.config=config;self.calls=[];self.closed=False
    def observe(self):return {'state':'DEGRADED','reason':'SYNTHETIC_TEST_ENGINE','metrics':{},'evidence':()}
    def close(self):self.closed=True
    stop=close
    def status(self):return {'synthetic':True,'state':'EXPERIMENTAL'}
    def episodes(self):return {'synthetic':True,'items':[]}
    def episode(self,episode_id):return {'synthetic':True,'episode_id':episode_id,'snapshot':{'revision':3},'evaluations':[]}
    def models(self):return {'synthetic':True,'items':[]}
    def experiments(self):return {'synthetic':True,'items':[]}
    def experiment(self,experiment_id):return {'synthetic':True,'experiment_id':experiment_id}
    def create_episode(self,**kw):self.calls.append(('create_episode',kw));return {'synthetic':True,'episode_id':'virtual-logistics-fixture'}
    def decide(self,episode_id,**kw):self.calls.append(('decide',episode_id,kw));return {'synthetic':True,'request_id':kw['request_id']}
    def advance(self,episode_id,**kw):self.calls.append(('advance',episode_id,kw));return self.episode(episode_id)
    def train(self,**kw):self.calls.append(('train',kw));return {'synthetic':True,'report':{'policy_comparison':[]}}
    def analyze(self,episode_id,**kw):self.calls.append(('analyze',episode_id,kw));return {'synthetic':True,'classification':'MATHEMATICAL_RESULT'}

@unittest.skipUnless(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'),'Existing pinned API environment required')
class LogisticsAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.temp=tempfile.TemporaryDirectory(prefix='genesis62-api-fixture-');self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name)/'state';self.source=self.state/'virtual-source';self.source.mkdir(parents=True)
        module=types.ModuleType('dragonhydra.cognitive_logistics.service');module.LogisticsService=LogisticsSpy
        p=patch.dict('sys.modules',{'dragonhydra.cognitive_logistics.service':module});p.start();self.addCleanup(p.stop)
        for name in ('dragonhydra.local_ai_settings.Settings.public','dragonhydra.connectors.vault.Vault.get',
                     'dragonhydra.connectors.service.Connections.run','dragonhydra.connectors.core.Transport.get','dragonhydra.local_ai.infer'):
            p=patch(name,side_effect=AssertionError('REAL_CREDENTIAL_PROVIDER_OR_INFERENCE_FORBIDDEN'));p.start();self.addCleanup(p.stop)
        self.app=create_app(self.state,local_token=TOKEN,bridge_secret='',start_worker=False,source_root=self.source,realtime_config={},future_config={},logistics_config={})
        client=TestClient(self.app);self.client=client.__enter__();self.addCleanup(lambda:client.__exit__(None,None,None))
        self.client.headers['Authorization']='Bearer '+TOKEN;self.engine=self.app.state.cognitive_logistics

    def test_twenty_first_concrete_extension_and_passive_reads(self):
        self.assertEqual(self.client.get('/dragon/api/v1/modules?scope=all').json()['inventory']['total'],21)
        self.assertIs(self.app.state.kernel.engines['cognitive_logistics'],self.engine)
        for path in ('/status','/episodes','/episodes/virtual-logistics-fixture','/models','/experiments','/experiments/virtual-experiment-fixture'):
            response=self.client.get(BASE+path);self.assertEqual(response.status_code,200,response.text);self.assertIs(response.json()['synthetic'],True)
        self.assertEqual(self.engine.calls,[]);self.assertEqual(list(self.source.iterdir()),[])
        self.assertEqual(self.client.get('/dragon/api/v1/realtime/status').status_code,200)
        self.assertEqual(self.client.get('/dragon/api/v1/future/status').status_code,200)

    def test_admin_mutators_delegate_once_with_revision_and_request_identity(self):
        response=self.client.post(BASE+'/episodes',json={'universe':'multi_location','demand_mode':'backorder'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.engine.calls[-1][1]['seed'],400042)
        self.assertEqual(self.engine.calls[-1][1]['demand_mode'],'backorder')
        for path,body,method in (
            ('/episodes/virtual-logistics-fixture/decisions',{'policy':'s_S','acquisition':'learned','request_id':'logistics-request-fixture','expected_revision':3},'decide'),
            ('/episodes/virtual-logistics-fixture/advance',{'days':1,'expected_revision':3},'advance'),
            ('/episodes/virtual-logistics-fixture/analyses',{'method':'bounded_method_search'},'analyze'),
            ('/training',{'seed':42,'cases':10},'train')):
            before=len(self.engine.calls);r=self.client.post(BASE+path,json=body)
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(len(self.engine.calls),before+1);self.assertEqual(self.engine.calls[-1][0],method)

    def test_authentication_roles_and_legacy_virtual_barriers(self):
        self.client.headers.clear();self.assertEqual(self.client.get(BASE+'/status').status_code,401)
        self.assertEqual(self.client.post(BASE+'/episodes',json={}).status_code,401)
        cookie='virtual-genesis62-reader-fixture'
        with closing(self.app.state.product.connect()) as db:
            db.execute('INSERT INTO product_sessions VALUES(?,?,?,?)',(hashlib.sha256(cookie.encode()).hexdigest(),'virtual:reader','["reader"]',time.time()+3600));db.commit()
        self.client.cookies.set(self.app.state.session_cookie_name,cookie)
        self.assertEqual(self.client.get(BASE+'/status').status_code,200)
        for path in ('/episodes','/training','/episodes/virtual-fixture/decisions','/episodes/virtual-fixture/advance','/episodes/virtual-fixture/analyses'):
            self.assertEqual(self.client.post(BASE+path,json={}).status_code,403)
        self.client.cookies.clear();self.client.headers['Authorization']='Bearer '+TOKEN
        self.assertEqual(self.client.post('/dragon/api/v1/jobs',json={}).status_code,403)
        self.assertEqual(self.client.get('/dragon/api/v1/connections').status_code,403)
        self.assertEqual(self.engine.calls,[])

    def test_strict_requests_forbid_operational_connectors_hidden_truth_and_code(self):
        for body in ({'universe':'LIVE'},{'api_key':'fictional'},{'actual_demand':[1]},{'seed':True},{'days':121},
                     {'demand_mode':'guess_unobserved_demand'},{'budget':-1},{'budget':101}):
            self.assertEqual(self.client.post(BASE+'/episodes',json=body).status_code,422)
        for body in ({'policy':'shell','request_id':'request','expected_revision':0},
                     {'acquisition':'external-provider','request_id':'request','expected_revision':0},
                     {'request_id':'../escape','expected_revision':0},{'request_id':'request','expected_revision':True}):
            self.assertEqual(self.client.post(BASE+'/episodes/virtual-fixture/decisions',json=body).status_code,422)
        self.assertEqual(self.client.post(BASE+'/episodes/virtual-fixture/advance',json={'days':31,'expected_revision':0}).status_code,422)
        self.assertEqual(self.client.post(BASE+'/episodes/virtual-fixture/analyses',json={'method':'sql','query':'not executed'}).status_code,422)
        self.assertEqual(self.client.post(BASE+'/training',json={'cases':101}).status_code,422)
        self.assertEqual(self.engine.calls,[])

    def test_existing_loopback_origin_and_body_limits_apply(self):
        self.assertEqual(self.client.get(BASE+'/status',headers={'Host':'outside.invalid'}).status_code,400)
        self.assertEqual(self.client.post(BASE+'/episodes',json={},headers={'Origin':'https://outside.invalid'}).status_code,403)
        self.assertEqual(self.client.post(BASE+'/episodes',content='x'*32769,headers={'Content-Type':'application/json'}).status_code,413)
        self.assertEqual(self.engine.calls,[])

    def test_all_host_extensions_must_be_explicit_before_any_state_creation(self):
        from dragonhydra.api import create_app
        target=Path(self.temp.name)/'not-created'
        for kw in ({'logistics_config':{}},{'logistics_config':{},'realtime_config':{}},
                   {'logistics_config':[],'realtime_config':{},'future_config':{}}):
            with self.assertRaisesRegex(ValueError,'LOGISTICS_REQUIRES_VIRTUAL_EXTENSIONS'):
                create_app(target,local_token=TOKEN,source_root=target/'virtual-source',**kw)
        self.assertFalse(target.exists())

class LogisticsRuntimeTests(unittest.TestCase):
    def test_new_owned_lane_marker_lock_and_older_lane_refusal(self):
        from dragonhydra.cognitive_logistics import server
        with tempfile.TemporaryDirectory(prefix='genesis62-runtime-fixture-') as directory:
            lane=Path(directory)/'GENESIS-6.2-COGNITIVE-LOGISTICS';lane.mkdir()
            state,source=server.prepare_state(lane/'runtime/web',lane=lane)
            self.assertTrue((state/server.MARKER).exists());self.assertEqual(list(source.iterdir()),[])
            self.assertEqual(server.prepare_state(state,lane=lane),(state,source))
            with server.runtime_lock(state):
                with self.assertRaisesRegex(RuntimeError,'ALREADY_RUNNING'):
                    with server.runtime_lock(state):pass
            for oldmarker in ('.genesis6-runtime.json','.genesis61-runtime.json'):
                old=lane/'runtime'/oldmarker.replace('.','');old.mkdir();(old/oldmarker).write_text('{}')
                with self.assertRaisesRegex(ValueError,'ADOPTION'):server.prepare_state(old,lane=lane)
                self.assertFalse((old/server.MARKER).exists())

    def test_build_info_precedes_state_creation_and_old_ports_are_rejected(self):
        from dragonhydra.cognitive_logistics import server
        for port in (18740,18751,19380,19390,0,65536):
            with self.assertRaises(ValueError):server.port_number(port)
        self.assertEqual(server.port_number(19400),19400)
        output=io.StringIO()
        with (patch.object(server,'source_identity',return_value={'source_sha':'a'*40,'component_version':'0.3.0-virtual-experimental'}),
              patch.object(server,'prepare_state',side_effect=AssertionError('BUILD_INFO_MUST_NOT_CREATE_STATE')),redirect_stdout(output)):
            self.assertEqual(server.main(['--build-info']),0)
        self.assertEqual(json.loads(output.getvalue())['component_version'],'0.3.0-virtual-experimental')

    def test_new_package_prefix_version_and_exact_inventory_are_enforced(self):
        from dragonhydra.cognitive_logistics import server
        with tempfile.TemporaryDirectory(prefix='genesis62-package-fixture-') as directory:
            source=Path(directory)/'GENESIS-6.2-COGNITIVE-LOGISTICS/source';source.mkdir(parents=True)
            names={'src/dragonhydra/api.py','src/dragonhydra/product.py','src/dragonhydra/kernel/composition.py',
                   'scripts/Start-Genesis62.ps1','scripts/build_genesis62.py','docs/logistics/DASHBOARD.md'}
            names|={f'src/dragonhydra/{package}/{name}.py' for package in ('realtime','future_relevance','cognitive_logistics') for name in ('__init__','server','router','service')}
            names|={'src/dragonhydra/resources/web/'+name for name in ('app.js','index.html','style.css','favicon.svg','realtime.js','realtime.css','future.js','future.css','logistics.js','logistics.css')}
            rows=[]
            for name in sorted(names):
                self.assertTrue(server.package_member_allowed(name),name)
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True);raw=b'# fictional package fixture\n';path.write_bytes(raw)
                rows.append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'git_blob_sha1':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
            manifest={'schema_version':'dragonhydra.genesis62-payload/1','source_sha':'b'*40,'component_version':'0.3.0-virtual-experimental','files':rows}
            raw=json.dumps(manifest,sort_keys=True).encode();(source/server.PACKAGE_MANIFEST).write_bytes(raw)
            build={'schema_version':'dragonhydra.genesis62-build/1','source_sha':'b'*40,'component_version':'0.3.0-virtual-experimental',
                   'payload_manifest':server.PACKAGE_MANIFEST,'payload_manifest_sha256':hashlib.sha256(raw).hexdigest(),
                   'package_prefix':'GENESIS-6.2-COGNITIVE-LOGISTICS/source/','source_clean':True,'synthetic_only':True,
                   'real_sporting_data_included':False,'runtime_or_credentials_included':False,'dependencies_included':False,
                   'build_kind':'curated-virtual-development-source','commit_time_unix':1700000000,'payload_files':len(rows)}
            (source/server.PACKAGE_BUILD).write_text(json.dumps(build),encoding='utf-8')
            with patch.object(server,'SOURCE',source):
                self.assertIs(server.source_identity()['payload_verified'],True)
                target=source/'src/dragonhydra/cognitive_logistics/service.py';original=target.read_bytes();target.write_bytes(b'modified bytes')
                with self.assertRaisesRegex(RuntimeError,'FILE_HASH_MISMATCH'):server.source_identity()
                target.write_bytes(original);(source/'extra.txt').write_text('extra')
                with self.assertRaisesRegex(RuntimeError,'INVENTORY_MISMATCH'):server.source_identity()
            for name in ('src/dragonhydra/resources/data/raw/observed.csv','runtime/credentials.json','../outside.py'):
                self.assertFalse(server.package_member_allowed(name),name)

@unittest.skipUnless(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'),'Existing pinned API environment required')
class LogisticsActualServiceAPITests(unittest.TestCase):
    def test_real_authenticated_episode_decision_advance_and_passive_stored_views(self):
        from contextlib import ExitStack
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        from dragonhydra.cognitive_logistics.server import prepare_state
        with tempfile.TemporaryDirectory(prefix='genesis62-actual-api-fixture-') as directory, ExitStack() as guards:
            lane=Path(directory)/'GENESIS-6.2-COGNITIVE-LOGISTICS';lane.mkdir()
            state,source=prepare_state(lane/'runtime/api-fixture',lane=lane)
            for name in ('dragonhydra.local_ai_settings.Settings.public','dragonhydra.connectors.vault.Vault.get',
                         'dragonhydra.connectors.service.Connections.run','dragonhydra.connectors.core.Transport.get','dragonhydra.local_ai.infer'):
                guards.enter_context(patch(name,side_effect=AssertionError('REAL_CREDENTIAL_PROVIDER_OR_INFERENCE_FORBIDDEN')))
            app=create_app(state,local_token=TOKEN,bridge_secret='',start_worker=False,source_root=source,realtime_config={},future_config={},logistics_config={})
            with TestClient(app) as client:
                client.headers['Authorization']='Bearer '+TOKEN
                result=client.post(BASE+'/episodes',json={'universe':'stable','days':10,'budget':10,'demand_mode':'backorder'})
                self.assertEqual(result.status_code,200,result.text)
                episode_id=result.json()['episode_id'];path=BASE+'/episodes/'+episode_id
                view=client.get(path).json();self.assertIs(view['synthetic'],True)
                self.assertEqual(view['snapshot']['day'],28)
                self.assertEqual(view['snapshot']['demand_mode'],'backorder')
                self.assertEqual(set(view['current_forecasts']),{'retail_a','retail_b'})
                for key in ('seed','actual_demand','arrival_schedule','_family'):
                    self.assertNotIn(key,view['snapshot'])
                response=client.post(path+'/decisions',json={'policy':'order_up_to','acquisition':'none','request_id':'logistics-request-actual-api-fixture','expected_revision':view['snapshot']['revision']})
                self.assertEqual(response.status_code,200,response.text)
                decision=response.json();self.assertEqual(decision['acquisitions'],[])
                accepted=client.get(path).json();self.assertEqual(len(accepted['decisions']),1)
                self.assertEqual(accepted['decisions'][0]['decision_id'],decision['decision_id'])
                response=client.post(path+'/advance',json={'days':1,'expected_revision':accepted['snapshot']['revision']})
                self.assertEqual(response.status_code,200,response.text)
                advanced=response.json();self.assertEqual(advanced['snapshot']['day'],29)
                self.assertGreater(advanced['snapshot']['revision'],accepted['snapshot']['revision'])
                self.assertIn('total_cost',advanced['metrics'])
                service=app.state.cognitive_logistics
                before=hashlib.sha256(service.journal.path.read_bytes()).hexdigest()
                with (patch.object(service,'_view',side_effect=AssertionError('GET_MUST_NOT_FORECAST_OR_REBUILD')),
                      patch('dragonhydra.cognitive_logistics.world.World.step',side_effect=AssertionError('GET_MUST_NOT_ADVANCE')),
                      patch('dragonhydra.cognitive_logistics.world.World.execute',side_effect=AssertionError('GET_MUST_NOT_DECIDE'))):
                    for read in ('/status','/episodes','/episodes/'+episode_id,'/models','/experiments'):
                        self.assertEqual(client.get(BASE+read).status_code,200)
                self.assertEqual(hashlib.sha256(service.journal.path.read_bytes()).hexdigest(),before)
                self.assertEqual(list(source.iterdir()),[])
            self.assertTrue(app.state.cognitive_logistics.closed)

if __name__=='__main__':unittest.main()
