"""Research API/queue acceptance using synthetic memory and temporary SQLite only."""
from contextlib import closing
from copy import deepcopy
from datetime import date,timedelta
import hashlib,hmac,importlib.util,json,secrets,sys,tempfile,time,unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock,patch

from dragonhydra.research_storage.base import StorageError

ROOT=Path(__file__).resolve().parents[1]
API='/dragon/api/v1'
TOKEN='SYNTHETIC-unit-local-token-only-123456789'
BRIDGE=b'SYNTHETIC-unit-bridge-only'
AVAILABLE=all(importlib.util.find_spec(n) is not None for n in ('fastapi','httpx'))


@unittest.skipUnless(AVAILABLE,'Requires existing FastAPI/TestClient runtime; no dependency installation')
class ResearchStorageAPI(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        from dragonhydra import public_results
        parent=ROOT/'runtime/sqlserver-evidence/api-unit-temp';parent.mkdir(parents=True,exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(prefix='SYNTHETIC-',dir=parent)
        self.root=Path(self.temporary.name).resolve();self.assertTrue(self.root.is_relative_to(parent.resolve()))
        self.addCleanup(self.temporary.cleanup)
        self.app=create_app(self.root,local_token=TOKEN,bridge_secret=BRIDGE.decode(),start_worker=False)
        self.product,self.jobs=self.app.state.product,self.app.state.jobs
        self.addCleanup(self.jobs.close)
        self.client=TestClient(self.app,raise_server_exceptions=False);self.addCleanup(self.client.close)
        self.client.headers['Authorization']='Bearer '+TOKEN
        raw=json.dumps({'name':'SYNTHETIC research API league','matches':[{
            'date':(date.today()+timedelta(days=10)).isoformat(),'team1':'SYNTHETIC home','team2':'SYNTHETIC away'}]}).encode()
        with closing(self.product.connect()) as db:
            public_results.ingest_bytes(db,raw,source_id='synthetic-research-api-unit',source_url='https://example.test/SYNTHETIC')
        self.match=self.client.get(API+'/matches').json()['items'][0]
        self.match_id=self.match['id'];self.run_id='SYNTHETIC-already-persisted-forecast'

    def bridge(self,method,path,body=b'',role='reader'):
        stamp,nonce=str(int(time.time())),secrets.token_hex(16)
        user='joomla:424242'  # Syntheticidentityusingtheactualbridgecontract
        signed='\n'.join((method,path,stamp,nonce,user,role,hashlib.sha256(body).hexdigest()))
        return {'X-Dragon-User':user,'X-Dragon-Roles':role,'X-Dragon-Time':stamp,'X-Dragon-Nonce':nonce,
                'X-Dragon-Signature':hmac.new(BRIDGE,signed.encode(),hashlib.sha256).hexdigest()}

    def job_count(self):
        with closing(self.product.connect()) as db:return db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0]

    def initialize(self):
        response=self.client.post(API+'/research/storage/initialize',json={},headers={'Idempotency-Key':'SYNTHETIC-initialize'})
        self.assertEqual(response.status_code,202,response.text)
        self.assertTrue(self.jobs.run_once());job=self.jobs.get(response.json()['id'])
        self.assertEqual(job['status'],'succeeded',job)
        return job

    def memory_view(self):
        probabilities={'home':'0.5','draw':'0.25','away':'0.25'}
        target=deepcopy(self.product.find(self.match_id))
        models=[{'record_id':'1'*64,'run_id':self.run_id,'model_name':'SYNTHETIC-model','version':'unit/1',
                 'training_manifest':[{'evidence_id':'SYNTHETIC-input','retained_version':'SYNTHETIC-v1'}],
                 'parameters':{'workflow':{'model_names':['SYNTHETIC-model'],'match_id':self.match_id,
                                          'build':{'kind':'SYNTHETIC immutable memory fixture'}},
                               'result':{'probabilities':{k:{'value':v} for k,v in probabilities.items()}}}}]
        predictions=[{'record_id':'2'*64,'model_run_id':'1'*64,'run_id':self.run_id,
                      'probabilities':probabilities,'target_evidence':target}]
        return {'models':models,'predictions':predictions,'outcomes':[],'evaluations':[]}

    def publish(self,key='SYNTHETIC-publish'):
        self.initialize();view=self.memory_view()
        response=self.client.post(API+'/matches/'+self.match_id+'/research/archives',
                                  json={'forecast_run_id':self.run_id},headers={'Idempotency-Key':key})
        self.assertEqual(response.status_code,202,response.text)
        with patch.object(self.product.kernel.engines['memory'],'view',return_value=view), \
             patch.object(self.product.kernel.engines['prediction'],'persist',side_effect=AssertionError('New inference forbidden')), \
             patch.object(self.jobs,'import_public',side_effect=AssertionError('Import forbidden')), \
             patch.object(self.jobs.providers,'run',side_effect=AssertionError('Provider request forbidden')):
            self.assertTrue(self.jobs.run_once())
        job=self.jobs.get(response.json()['id']);self.assertEqual(job['status'],'succeeded',job)
        return job,view

    def test_01_health_history_and_missing_archive_are_passive(self):
        before=self.product.db_path.read_bytes();jobs=self.job_count()
        response=self.client.get(API+'/research/storage');self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['canonical_backend'],'sqlite');self.assertFalse(response.json()['research']['connected'])
        history=self.client.get(API+'/matches/'+self.match_id+'/research/archives')
        self.assertEqual(history.status_code,200);self.assertEqual(history.json()['items'],[])
        self.assertEqual(self.client.get(API+'/research/archives/'+'a'*64).status_code,404)
        self.assertFalse((self.root/'research.sqlite3').exists())
        self.assertEqual(self.job_count(),jobs);self.assertEqual(self.product.db_path.read_bytes(),before)

    def test_02_anonymous_users_cannot_read_or_write_research(self):
        self.client.headers.clear()
        actions=[('GET','/research/storage',None),('GET','/research/archives/'+'a'*64,None),
                 ('GET','/matches/'+self.match_id+'/research/archives',None),
                 ('POST','/research/storage/initialize',{}),
                 ('POST','/matches/'+self.match_id+'/research/archives',{'forecast_run_id':self.run_id}),
                 ('POST','/research/notes',{'match_id':self.match_id,'text':'SYNTHETIC note'})]
        for method,path,body in actions:
            with self.subTest(method=method,path=path):self.assertEqual(self.client.request(method,API+path,json=body).status_code,401)
        self.assertEqual(self.job_count(),0);self.assertFalse((self.root/'research.sqlite3').exists())

    def test_03_authenticated_reader_cannot_execute_admin_writes(self):
        self.client.headers.clear()
        actions=[('GET','/research/storage',None),('POST','/research/storage/initialize',{}),
                 ('POST','/matches/'+self.match_id+'/research/archives',{'forecast_run_id':self.run_id}),
                 ('POST','/research/notes',{'match_id':self.match_id,'text':'SYNTHETIC note'}),
                 ('PUT','/research/notes/00000000-0000-4000-8000-000000000000',{'text':'SYNTHETIC update','expected_revision':1})]
        for method,path,body in actions:
            raw=b'' if body is None else json.dumps(body,separators=(',',':')).encode()
            headers=self.bridge(method,API+path,raw)
            with self.subTest(method=method,path=path):
                self.assertEqual(self.client.request(method,API+path,content=raw,headers={**headers,'Content-Type':'application/json'}).status_code,403)
        path=API+'/matches/'+self.match_id+'/research/archives'
        self.assertEqual(self.client.get(path,headers=self.bridge('GET',path)).status_code,200)
        self.assertEqual(self.job_count(),0)

    def test_04_foreign_origin_is_rejected_before_any_write(self):
        for method,path,body in [('POST','/research/storage/initialize',{}),
                                 ('POST','/research/notes',{'match_id':self.match_id,'text':'SYNTHETIC'}),
                                 ('PUT','/research/notes/00000000-0000-4000-8000-000000000000',{'text':'SYNTHETIC','expected_revision':1})]:
            response=self.client.request(method,API+path,json=body,headers={'Origin':'https://untrusted.example.test'})
            self.assertEqual(response.status_code,403);self.assertEqual(response.json()['error']['code'],'ORIGIN_NOT_ALLOWED')
        self.assertEqual(self.job_count(),0);self.assertFalse((self.root/'research.sqlite3').exists())

    def test_05_initialize_is_an_explicit_idempotent_durable_job(self):
        first=self.initialize();count=self.job_count()
        duplicate=self.client.post(API+'/research/storage/initialize',json={},headers={'Idempotency-Key':'SYNTHETIC-initialize'})
        self.assertEqual(duplicate.status_code,202);self.assertEqual(duplicate.json()['id'],first['id'])
        self.assertEqual(self.job_count(),count);self.assertFalse(self.jobs.run_once())
        self.assertTrue(self.client.get(API+'/research/storage').json()['research']['connected'])

    def test_06_published_existing_memory_is_read_through_all_archive_routes(self):
        job,view=self.publish();archive_id=job['result']['archive_id']
        fetched=self.client.get(API+'/research/archives/'+archive_id)
        self.assertEqual(fetched.status_code,200,fetched.text)
        value=fetched.json()['archive'];self.assertEqual(value['predictions'],view['predictions'])
        self.assertEqual(value['models'],view['models']);self.assertEqual(value['evaluation_status'],'pending')
        history=self.client.get(API+'/matches/'+self.match_id+'/research/archives').json()['items']
        self.assertEqual([r['archive']['archive_id'] for r in history],[archive_id])
        match=self.client.get(API+'/research/archives/'+archive_id+'/match')
        self.assertEqual(match.status_code,200,match.text);self.assertEqual(match.json()['match']['id'],self.match_id)
        self.assertIn('Immutable',match.json()['scope'])

    def test_07_archive_submission_is_idempotent_without_repeating_the_worker(self):
        first,_=self.publish();count=self.job_count()
        duplicate=self.client.post(API+'/matches/'+self.match_id+'/research/archives',
                                  json={'forecast_run_id':self.run_id},headers={'Idempotency-Key':'SYNTHETIC-publish'})
        self.assertEqual(duplicate.status_code,202);self.assertEqual(duplicate.json()['id'],first['id'])
        self.assertEqual(self.job_count(),count);self.assertFalse(self.jobs.run_once())
        self.assertEqual(len(self.product.research.history(self.match_id)),1)

    def test_08_missing_persisted_forecast_fails_without_inference(self):
        self.initialize()
        response=self.client.post(API+'/matches/'+self.match_id+'/research/archives',json={'forecast_run_id':'SYNTHETIC-missing'})
        with patch.object(self.product.kernel.engines['memory'],'view',return_value={'models':[],'predictions':[]}), \
             patch.object(self.product.kernel.engines['prediction'],'persist',side_effect=AssertionError('No inference')):
            self.assertTrue(self.jobs.run_once())
        job=self.jobs.get(response.json()['id']);self.assertEqual(job['status'],'failed')
        self.assertEqual(job['error']['code'],'COMPLETE_PERSISTED_FORECAST_REQUIRED')
        self.assertEqual(self.product.research.history(self.match_id),[]);self.assertFalse(self.jobs.run_once())

    def test_09_published_snapshot_does_not_change_with_later_memory(self):
        job,view=self.publish();path=API+'/research/archives/'+job['result']['archive_id']
        before=self.client.get(path).json()
        view['predictions'][0]['probabilities']['home']='0.999'
        view['models'][0]['parameters']['result']['probabilities']['home']['value']='0.999'
        view['predictions'][0]['target_evidence']['score_home']=99
        self.assertEqual(self.client.get(path).json(),before)
        self.assertEqual(before['archive']['evaluation_status'],'pending')

    def test_10_note_update_conflict_preserves_current_revision(self):
        self.initialize()
        response=self.client.post(API+'/research/notes',json={'match_id':self.match_id,'text':'SYNTHETIC original ✓'})
        self.assertEqual(response.status_code,200,response.text);note=response.json()
        path=API+'/research/notes/'+note['note_id']
        updated=self.client.put(path,json={'text':'SYNTHETIC revision2','expected_revision':1})
        self.assertEqual(updated.status_code,200,updated.text);self.assertEqual(updated.json()['revision'],2)
        stale=self.client.put(path,json={'text':'SYNTHETIC stale','expected_revision':1})
        self.assertEqual(stale.status_code,409);self.assertEqual(stale.json()['error']['code'],'RESEARCH_NOTE_REVISION_CONFLICT')
        notes=self.client.get(API+'/matches/'+self.match_id+'/research/notes').json()['items']
        self.assertEqual(notes,[updated.json()])

    def test_11_invalid_request_cannot_change_storage_configuration(self):
        actions=[('/research/storage/initialize',{'provider':'sqlserver'}),
                 ('/matches/'+self.match_id+'/research/archives',{'forecast_run_id':'','settings':{}}),
                 ('/research/notes',{'match_id':'SYNTHETIC-invalid','text':'SYNTHETIC'})]
        for path,body in actions:
            with self.subTest(path=path):self.assertEqual(self.client.post(API+path,json=body).status_code,422)
        self.assertEqual(self.job_count(),0);self.assertFalse((self.root/'research-storage.json').exists())

    def test_12_uninitialized_notes_read_is_useful_and_does_not_create_storage(self):
        response=self.client.get(API+'/matches/'+self.match_id+'/research/notes')
        self.assertIn(response.status_code,(200,503),response.text)
        if response.status_code==200:
            self.assertEqual(response.json()['items'],[])
            self.assertFalse(response.json()['research']['connected'])
        else:self.assertIn('code',response.json()['error'])
        self.assertFalse((self.root/'research.sqlite3').exists());self.assertEqual(self.job_count(),0)

    def test_13_sqlserver_unavailable_is_explicit_without_sqlite_fallback(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        connect=Mock(side_effect=StorageError('SYNTHETIC_SQLSERVER_UNAVAILABLE',sqlstate='08001'))
        class UnavailableRepository:
            provider='sqlserver'
            def __init__(self,config,scope):self.scope=scope
            def health(self):
                try:connect()
                except StorageError:return {'provider':'sqlserver','connected':False,'reason_code':'SYNTHETIC_SQLSERVER_UNAVAILABLE'}
            def initialize(self):return connect()
            def get(self,key):return connect()
        fake=ModuleType('dragonhydra.research_storage.sqlserver')
        fake.SQLServerConfig=type('SyntheticConfig',(),{'from_dict':staticmethod(lambda settings: object())})
        fake.SQLServerResearchRepository=UnavailableRepository
        state=self.root/'SYNTHETIC-sql-unavailable';state.mkdir()
        (state/'research-storage.json').write_text(json.dumps({'schema_version':1,'provider':'sqlserver','sqlserver':{}}))
        with patch.dict(sys.modules,{'dragonhydra.research_storage.sqlserver':fake}):
            app=create_app(state,local_token=TOKEN,start_worker=False)
        self.addCleanup(app.state.jobs.close)
        with TestClient(app,raise_server_exceptions=False) as client:
            client.headers['Authorization']='Bearer '+TOKEN
            health=client.get(API+'/research/storage');self.assertEqual(health.status_code,200,health.text)
            self.assertFalse(health.json()['research']['connected']);self.assertEqual(health.json()['canonical_backend'],'sqlite')
            request=client.post(API+'/research/storage/initialize',json={});self.assertEqual(request.status_code,202)
            self.assertTrue(app.state.jobs.run_once());job=app.state.jobs.get(request.json()['id'])
            self.assertEqual(job['status'],'failed');self.assertEqual(job['error']['code'],'SYNTHETIC_SQLSERVER_UNAVAILABLE')
            self.assertFalse(job['error']['uncertain_write']);self.assertFalse(app.state.jobs.run_once())
            self.assertEqual(client.get(API+'/research/archives/'+'a'*64).status_code,503)
            self.assertEqual(client.get(API+'/matches').status_code,200)
        self.assertGreaterEqual(connect.call_count,3)
        self.assertFalse((state/'research.sqlite3').exists());self.assertTrue((state/'core.sqlite3').exists())


    def test_14_real_sqlserver_factory_is_lazy_and_needs_no_driver_import(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        from dragonhydra.research_storage import sqlserver
        state=self.root/'SYNTHETIC-real-factory';state.mkdir()
        settings={'schema_version':1,'provider':'sqlserver','sqlserver':{
            'server':'lpc:localhost','database':'SYNTHETIC_research_unit_never_connected',
            'encrypt':True,'trust_server_certificate':False,'authentication':'windows_integrated'}}
        (state/'research-storage.json').write_text(json.dumps(settings))
        with patch.dict(sys.modules,{'pyodbc':None}), \
             patch.object(sqlserver.Repo,'_connect',side_effect=AssertionError('No connection allowed')) as connect:
            app=create_app(state,local_token=TOKEN,start_worker=False)
            self.addCleanup(app.state.jobs.close)
            self.assertIsInstance(app.state.product.research,sqlserver.Repo)
            self.assertEqual(app.state.product.research.provider,'sqlserver')
            self.assertEqual(app.state.product.research.config.database,settings['sqlserver']['database'])
            self.assertEqual(app.state.product.research.config.driver,'ODBC Driver 18 for SQL Server')
            connect.assert_not_called()
        self.assertFalse((state/'research.sqlite3').exists())

if __name__=='__main__':unittest.main()