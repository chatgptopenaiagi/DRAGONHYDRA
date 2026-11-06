"""Actual shared API/auth/router with a disjoint synthetic engine spy.

The spy verifies delegation and passivity; it is not a second forecast or policy
implementation. Algorithm/outcome/privacy acceptance belongs to service tests.
"""
from contextlib import closing
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

BASE='/dragon/api/v1/future'
TOKEN='virtual-genesis61-api-fixture-not-a-real-key'


class FutureSpy:
    contract_version='core-next.engine/1'
    def __init__(self,path,config=None): self.path=path;self.config=config;self.calls=[];self.closed=False
    def observe(self): return {'state':'DEGRADED','reason':'SYNTHETIC_TEST_ENGINE','metrics':{},'evidence':()}
    def close(self): self.closed=True
    stop=close
    def status(self): return {'synthetic':True,'state':'EXPERIMENTAL'}
    def models(self): return {'synthetic':True,'items':[]}
    def model(self,model_id): return {'synthetic':True,'model_id':model_id}
    def episodes(self): return {'synthetic':True,'items':[]}
    def episode(self,episode_id): return {'synthetic':True,'episode_id':episode_id,'snapshot':{'revision':1},'evaluations':[]}
    def experiments(self): return {'synthetic':True,'items':[]}
    def experiment(self,experiment_id): return {'synthetic':True,'experiment_id':experiment_id}
    def create_episode(self,**kw): self.calls.append(('create_episode',kw));return {'synthetic':True,'episode_id':'future-fixture-episode'}
    def decide(self,episode_id,**kw): self.calls.append(('decide',episode_id,kw));return {'synthetic':True,'request_id':kw['request_id']}
    def advance(self,episode_id,**kw): self.calls.append(('advance',episode_id,kw));return {'synthetic':True,'episode_id':episode_id}
    def train(self,**kw): self.calls.append(('train',kw));return {'synthetic':True,'model_id':'future-fixture-model','report':{'policy_comparison':[]}}


@unittest.skipUnless(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'),'Existing pinned API fixture environment required')
class FutureAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.temp=tempfile.TemporaryDirectory(prefix='genesis61-api-fixture-');self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name)/'state';self.source=self.state/'virtual-source';self.source.mkdir(parents=True)
        module=types.ModuleType('dragonhydra.future_relevance.service');module.FutureService=FutureSpy
        guard=patch.dict('sys.modules',{'dragonhydra.future_relevance.service':module});guard.start();self.addCleanup(guard.stop)
        for name in ('dragonhydra.local_ai_settings.Settings.public','dragonhydra.connectors.vault.Vault.get',
                     'dragonhydra.connectors.service.Connections.run','dragonhydra.connectors.core.Transport.get','dragonhydra.local_ai.infer'):
            trap=patch(name,side_effect=AssertionError('REAL_PROVIDER_CREDENTIAL_OR_AI_FORBIDDEN'));trap.start();self.addCleanup(trap.stop)
        self.app=create_app(self.state,local_token=TOKEN,bridge_secret='',start_worker=False,source_root=self.source,realtime_config={},future_config={})
        client=TestClient(self.app);self.client=client.__enter__();self.addCleanup(lambda:client.__exit__(None,None,None))
        self.client.headers['Authorization']='Bearer '+TOKEN
        self.engine=self.app.state.future_relevance

    def test_concrete_twentieth_extension_and_passive_reads(self):
        modules=self.client.get('/dragon/api/v1/modules?scope=all').json()
        self.assertEqual(modules['inventory']['total'],20)
        self.assertIs(self.app.state.kernel.engines['future_relevance'],self.engine)
        for path in ('/status','/models','/models/future-fixture-model','/episodes','/episodes/future-fixture-episode','/experiments','/experiments/future-fixture-experiment'):
            response=self.client.get(BASE+path)
            self.assertEqual(response.status_code,200,response.text)
            self.assertIs(response.json()['synthetic'],True)
        self.assertEqual(self.engine.calls,[])
        self.assertEqual(list(self.source.iterdir()),[])

    def test_explicit_mutators_delegate_validated_arguments_once(self):
        result=self.client.post(BASE+'/episodes',json={'universe':'late_card_interaction','target':'FULL_TIME_RESULT','horizon':'FULL_TIME'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.engine.calls[0][0],'create_episode')
        self.assertEqual(self.engine.calls[0][1]['budget'],0.12)
        for path,body,operation in (
            ('/episodes/future-fixture-episode/decisions',{'policy':'learned','request_id':'future-request-fixture','expected_revision':3},'decide'),
            ('/episodes/future-fixture-episode/advance',{'minutes':10,'expected_revision':3},'advance'),
            ('/training',{'seed':42,'cases_per_family':20},'train')):
            count=len(self.engine.calls);response=self.client.post(BASE+path,json=body)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len(self.engine.calls),count+1)
            self.assertEqual(self.engine.calls[-1][0],operation)

    def test_authentication_reader_roles_and_existing_virtual_barriers(self):
        self.client.headers.clear()
        self.assertEqual(self.client.get(BASE+'/status').status_code,401)
        self.assertEqual(self.client.post(BASE+'/episodes',json={}).status_code,401)
        cookie='virtual-genesis61-reader-fixture'
        with closing(self.app.state.product.connect()) as db:
            db.execute('INSERT INTO product_sessions VALUES(?,?,?,?)',(hashlib.sha256(cookie.encode()).hexdigest(),'virtual:reader','["reader"]',time.time()+3600));db.commit()
        self.client.cookies.set(self.app.state.session_cookie_name,cookie)
        self.assertEqual(self.client.get(BASE+'/status').status_code,200)
        for path,body in (('/episodes',{}),('/training',{}),('/episodes/future-fixture/decisions',{}),('/episodes/future-fixture/advance',{})):
            self.assertEqual(self.client.post(BASE+path,json=body).status_code,403)
        self.client.cookies.clear();self.client.headers['Authorization']='Bearer '+TOKEN
        self.assertEqual(self.client.post('/dragon/api/v1/jobs',json={}).status_code,403)
        self.assertEqual(self.client.get('/dragon/api/v1/connections').status_code,403)
        self.assertEqual(self.client.get('/dragon/api/v1/realtime/status').status_code,200)
        self.assertEqual(self.engine.calls,[])

    def test_strict_schemas_forbid_live_inputs_hidden_labels_and_wrong_targets(self):
        for body in ({'source_mode':'LIVE'},{'api_key':'fictional'},{'outcome':1},{'family_rules':{}},{'seed':True},
                     {'universe':'real-provider'},{'target':'REAL_MATCH'},{'target':'FULL_TIME_RESULT','horizon':'10'},
                     {'budget':-1},{'minute':121}):
            with self.subTest(body=body): self.assertEqual(self.client.post(BASE+'/episodes',json=body).status_code,422)
        for body in ({'policy':'shell','request_id':'request','expected_revision':0},
                     {'policy':'random','request_id':'request','expected_revision':True},
                     {'policy':'random','request_id':'../escape','expected_revision':0},
                     {'policy':'random','request_id':'request','expected_revision':0,'hidden_outcome':0}):
            self.assertEqual(self.client.post(BASE+'/episodes/future-fixture/decisions',json=body).status_code,422)
        self.assertEqual(self.client.post(BASE+'/episodes/future-fixture/advance',json={'minutes':0,'expected_revision':0}).status_code,422)
        self.assertEqual(self.client.post(BASE+'/training',json={'cases_per_family':1001}).status_code,422)
        self.assertEqual(self.engine.calls,[])

    def test_existing_host_origin_and_payload_bounds_apply(self):
        self.assertEqual(self.client.get(BASE+'/status',headers={'Host':'external.invalid'}).status_code,400)
        self.assertEqual(self.client.post(BASE+'/episodes',json={},headers={'Origin':'https://external.invalid'}).status_code,403)
        self.assertEqual(self.client.post(BASE+'/episodes',content='x'*32769,headers={'Content-Type':'application/json'}).status_code,413)
        self.assertEqual(self.engine.calls,[])

    def test_future_requires_explicit_virtual_opt_in_before_product_state(self):
        from dragonhydra.api import create_app
        target=Path(self.temp.name)/'not-created'
        for kwargs in ({'future_config':{}},{'future_config':[],'realtime_config':{}}):
            with self.assertRaisesRegex(ValueError,'FUTURE_REQUIRES_VIRTUAL_CONFIGURATION'):
                create_app(target,local_token=TOKEN,source_root=target/'virtual-source',**kwargs)
        self.assertFalse(target.exists())


class FutureRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='genesis61-runtime-fixture-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_new_lane_markers_and_no_genesis6_runtime_adoption(self):
        from dragonhydra.future_relevance.server import prepare_state,MARKER,runtime_lock
        lane=self.root/'GENESIS-6.1-FUTURE-RELEVANCE';lane.mkdir()
        state,source=prepare_state(lane/'runtime/web',lane=lane)
        self.assertTrue((state/MARKER).is_file());self.assertTrue((state/'.genesis6-runtime.json').is_file())
        self.assertEqual(prepare_state(state,lane=lane),(state,source))
        with runtime_lock(state):
            with self.assertRaisesRegex(RuntimeError,'ALREADY_RUNNING'):
                with runtime_lock(state): pass
        old=lane/'runtime/old';old.mkdir();(old/'.genesis6-runtime.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'ADOPTION'):prepare_state(old,lane=lane)
        self.assertFalse((old/MARKER).exists())
        with self.assertRaisesRegex(ValueError,'OWN_RUNTIME'):prepare_state(self.root/'old/runtime/web',lane=self.root/'old')

    def test_build_info_is_read_only_and_old_port_refused(self):
        from dragonhydra.future_relevance import server
        for port in (18740,18751,19380,0,65536):
            with self.assertRaises(ValueError):server.port_number(port)
        self.assertEqual(server.port_number(19390),19390)
        from contextlib import redirect_stdout
        output=io.StringIO()
        with (patch.object(server,'LANE',self.root/'GENESIS-6.1-FUTURE-RELEVANCE'),
              patch.object(server,'source_identity',return_value={'source_sha':'a'*40,'component_version':'0.2.0-virtual-experimental'}),
              patch.object(server,'prepare_state',side_effect=AssertionError('BUILD_INFO_MUST_NOT_CREATE_STATE')),
              redirect_stdout(output)):
            self.assertEqual(server.main(['--build-info']),0)
        self.assertEqual(json.loads(output.getvalue())['component_version'],'0.2.0-virtual-experimental')

    def test_future_package_identity_and_tamper_fail_closed_without_git_fallback(self):
        from dragonhydra.future_relevance import server
        import subprocess
        source=self.root/'GENESIS-6.1-FUTURE-RELEVANCE/source';source.mkdir(parents=True)
        names={'src/dragonhydra/api.py','src/dragonhydra/product.py','src/dragonhydra/kernel/composition.py',
               'scripts/Start-Genesis61.ps1','scripts/build_genesis61.py','docs/future-relevance/DASHBOARD.md'}
        names|={f'src/dragonhydra/{package}/{name}.py' for package in ('realtime','future_relevance')
                for name in ('__init__','server','service','router')}
        names|={'src/dragonhydra/resources/web/'+n for n in ('app.js','index.html','style.css','favicon.svg','realtime.js','realtime.css','future.js','future.css')}
        records=[]
        for name in sorted(names):
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);raw=b'# fictional package fixture\n';path.write_bytes(raw)
            records.append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                            'git_blob_sha1':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
        manifest={'schema_version':'dragonhydra.genesis61-payload/1','source_sha':'b'*40,
                  'component_version':'0.2.0-virtual-experimental','files':records}
        raw=json.dumps(manifest,sort_keys=True).encode();(source/server.PACKAGE_MANIFEST).write_bytes(raw)
        build={'schema_version':'dragonhydra.genesis61-build/1','source_sha':'b'*40,'component_version':'0.2.0-virtual-experimental',
               'payload_manifest':server.PACKAGE_MANIFEST,'payload_manifest_sha256':hashlib.sha256(raw).hexdigest(),
               'package_prefix':'GENESIS-6.1-FUTURE-RELEVANCE/source/','source_clean':True,'synthetic_only':True,
               'real_sporting_data_included':False,'runtime_or_credentials_included':False,'dependencies_included':False,
               'build_kind':'curated-virtual-development-source','commit_time_unix':1700000000,'payload_files':len(records)}
        (source/server.PACKAGE_BUILD).write_text(json.dumps(build),encoding='utf-8')
        with patch.object(server,'SOURCE',source):
            identity=server.source_identity();self.assertIs(identity['payload_verified'],True)
            self.assertEqual(identity['source_sha'],'b'*40)
            target=source/'src/dragonhydra/future_relevance/service.py';target.write_bytes(b'modified bytes')
            with self.assertRaisesRegex(RuntimeError,'FILE_HASH_MISMATCH'):server.source_identity()
            (source/'.git').write_text('gitdir: nonexistent',encoding='utf-8')
            with (patch.object(server.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','fictional Git failure')),
                  self.assertRaisesRegex(RuntimeError,'SOURCE_IDENTITY_UNAVAILABLE')):
                server.source_identity()


@unittest.skipUnless(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'),'Existing pinned API fixture environment required')
class FutureActualServiceAPITests(unittest.TestCase):
    def test_actual_authenticated_baseline_decision_then_eligible_retrospective_evaluation(self):
        from contextlib import ExitStack
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        with tempfile.TemporaryDirectory(prefix='genesis61-actual-api-fixture-') as directory, ExitStack() as guards:
            state=Path(directory)/'state';source=state/'virtual-source';source.mkdir(parents=True)
            for name in ('dragonhydra.local_ai_settings.Settings.public','dragonhydra.connectors.vault.Vault.get',
                         'dragonhydra.connectors.service.Connections.run','dragonhydra.connectors.core.Transport.get','dragonhydra.local_ai.infer'):
                guards.enter_context(patch(name,side_effect=AssertionError('REAL_PROVIDER_CREDENTIAL_OR_AI_FORBIDDEN')))
            app=create_app(state,local_token=TOKEN,bridge_secret='',start_worker=False,source_root=source,realtime_config={},future_config={})
            with TestClient(app) as client:
                client.headers['Authorization']='Bearer '+TOKEN
                response=client.post(BASE+'/episodes',json={'universe':'tempo_signal','target':'GOAL_OCCURRENCE','horizon':'10'})
                self.assertEqual(response.status_code,200,response.text)
                episode_id=response.json()['episode_id'];path=BASE+'/episodes/'+episode_id
                view=client.get(path).json();self.assertIs(view['synthetic'],True)
                self.assertEqual(view['evaluations'],[])
                self.assertEqual({item['category'] for item in view['snapshot']['candidates']},{'possession','red_cards','shots','fatigue'})
                self.assertNotIn('seed',view['snapshot']);self.assertNotIn('outcome',view['snapshot'])
                revision=view['snapshot']['revision']
                response=client.post(path+'/decisions',json={'policy':'acquire_none','request_id':'future-request-actual-api-fixture','expected_revision':revision})
                self.assertEqual(response.status_code,200,response.text)
                decision=response.json()
                self.assertEqual(decision['acquisitions'],[])
                self.assertEqual(decision['before']['probabilities'],decision['after']['probabilities'])
                self.assertEqual(decision['acquisition_cost'],0)
                after=client.get(path).json();self.assertEqual(len(after['decisions']),1);self.assertEqual(after['evaluations'],[])
                digest=hashlib.sha256(app.state.future_relevance.journal.path.read_bytes()).hexdigest()
                with patch('dragonhydra.future_relevance.service.checked_forecast',side_effect=AssertionError('PASSIVE_GET_MUST_NOT_FORECAST')):
                    for read in ('/status','/models','/episodes','/experiments','/episodes/'+episode_id):
                        self.assertEqual(client.get(BASE+read).status_code,200)
                self.assertEqual(hashlib.sha256(app.state.future_relevance.journal.path.read_bytes()).hexdigest(),digest)
                response=client.post(path+'/advance',json={'minutes':11,'expected_revision':after['snapshot']['revision']})
                self.assertEqual(response.status_code,200,response.text)
                matured=response.json();self.assertEqual(len(matured['evaluations']),1)
                self.assertEqual(matured['evaluations'][0]['decision_id'],decision['decision_id'])
                self.assertEqual(list(source.iterdir()),[])
            self.assertTrue(app.state.future_relevance.closed)


if __name__=='__main__': unittest.main()
