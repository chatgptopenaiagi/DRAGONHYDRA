"""Controlled observation clocks and existing-worker cadence; no live profile."""
from contextlib import closing
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile,threading,time,unittest

from dragonhydra.kernel.contracts import KernelConfig,ModuleDefinition
from dragonhydra.kernel.local_observer import LocalObserver
from dragonhydra.kernel.registry import ModuleRegistry

LAB=Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')


class Probe:
    contract_version='core-next.engine/1'
    def __init__(self):self.calls=0;self.fail=False;self.entered=None;self.release=None
    def observe(self):
        self.calls+=1
        if self.entered:self.entered.set();assert self.release.wait(2)
        if self.fail:raise RuntimeError('SYNTHETIC sensitive exception must not be published')
        return {'state':'READY','reason':'BOUNDED_FIXTURE_CHECK','metrics':{'cognitive_records':5}}
    def read(self):return []
    def stop(self):pass


class Support:
    def begin_cycle(self):pass


class LocalObserverTests(unittest.TestCase):
    def setUp(self):
        (LAB/'tests').mkdir(exist_ok=True)
        t=tempfile.TemporaryDirectory(dir=LAB/'tests',prefix='observer-')
        self.addCleanup(t.cleanup);self.state=Path(t.name)
        self.at=datetime(2026,11,2,tzinfo=timezone.utc);self.tick=0.0
        self.probe=Probe();self.identity={'installation_id':'isolated-observer','source_commit':'a'*40,'build_id':'test-a'}
        self.registry,self.observer=self.make()
    def make(self,identity=None):
        identity=identity or self.identity
        definition=ModuleDefinition('sample','Sample','Fixture','Fixture',supported_operations=('read',))
        registry=ModuleRegistry((definition,),{'sample':self.probe},ttl_seconds=9,clock=lambda:self.at,
            installation_id=identity['installation_id'],build_identity=identity['build_id'])
        observer=LocalObserver(registry,Support(),self.state,identity,interval=3,
            clock=lambda:self.at,monotonic=lambda:self.tick)
        return registry,observer
    def advance(self,seconds):self.at+=timedelta(seconds=seconds);self.tick+=seconds

    def test_reads_do_not_renew_evidence_and_real_check_recovers_after_expiry(self):
        self.observer.start();initial=self.registry.item('sample')['observation']['observation_id']
        for _ in range(5):self.registry.items()
        self.assertEqual(self.probe.calls,1)
        self.observer.running=False;self.advance(10)
        self.assertEqual(self.registry.item('sample')['state'],'EXPIRED')
        self.assertEqual(self.observer.tick()['status'],'disabled')
        self.observer.running=True;result=self.observer.tick(force=True)
        self.assertEqual(result['status'],'completed');self.assertEqual(self.probe.calls,2)
        self.assertEqual(self.registry.item('sample')['state'],'READY')
        self.assertNotEqual(initial,self.registry.item('sample')['observation']['observation_id'])

    def test_non_overlapping_manual_and_scheduled_cycles(self):
        self.observer.start();self.probe.entered=threading.Event();self.probe.release=threading.Event()
        worker=threading.Thread(target=lambda:self.observer.tick(force=True));worker.start()
        self.assertTrue(self.probe.entered.wait(1))
        self.assertEqual(self.observer.tick(force=True)['status'],'busy')
        self.probe.release.set();worker.join(2);self.assertFalse(worker.is_alive())
        self.assertEqual(self.probe.calls,2)

    def test_failed_check_retains_success_but_does_not_renew_old_metrics(self):
        self.observer.start();success=self.registry.item('sample')['last_success_at']
        self.advance(3);self.probe.fail=True;result=self.observer.tick()
        self.assertEqual(result['failed_module_ids'],['sample'])
        item=self.registry.item('sample');self.assertEqual(item['last_success_at'],success)
        self.assertEqual(item['state'],'DEGRADED');self.assertEqual(item['observation']['metrics'],{})
        self.assertNotIn('sensitive exception',json.dumps(item))

    def test_cache_rejects_wrong_build_and_future_or_malformed_clocks(self):
        self.observer.start();data=json.loads(self.observer.path.read_text())
        _,other=self.make({**self.identity,'build_id':'test-b'});other._load_history();self.assertFalse(other.registry.observations)
        for invalid in (None,'invalid-clock',(self.at+timedelta(days=1)).isoformat()):
            with self.subTest(clock=invalid):
                item=data['observations']['sample'];item['observed_at']=invalid
                self.observer.path.write_text(json.dumps(data));registry,observer=self.make();observer._load_history()
                self.assertFalse(registry.observations)

    def test_restart_history_does_not_renew_old_counter_or_claim_ready(self):
        self.observer.start();sampled=self.registry.item('sample')['observation']['metrics_sampled_at']
        self.advance(2);self.probe.read();self.registry.record_operation('sample','read','READY','EXPLICIT_READ')
        success=self.registry.item('sample')['last_success_at'];self.observer.stop()
        registry,observer=self.make();observer._load_history();item=registry.item('sample')
        self.assertEqual(item['last_success_at'],success);self.assertEqual(item['state'],'UNVERIFIED')
        self.assertEqual(item['observation']['metrics_sampled_at'],sampled)

    def test_cache_write_failure_is_bounded_and_reported(self):
        self.observer.path=self.state/'missing-parent'/'observations.json'
        result=self.observer.start();self.assertEqual(result['status'],'completed')
        self.assertEqual(result['cache_state'],'unavailable')
        self.assertEqual(self.registry.item('sample')['state'],'READY')
        self.assertFalse((self.state/'missing-parent').exists())

    def test_external_evidence_keeps_its_shorter_expiry_and_real_success_clock(self):
        original=self.at
        self.probe.observe=lambda:{'state':'READY','reason':'EXTERNAL_BOUNDED_CHECK','metrics':{'http_status':200},
            'observed_at':original,'expires_at':original+timedelta(seconds=5),'last_success_at':original}
        self.observer.start();self.advance(3);self.observer.tick(force=True)
        proof=self.registry.item('sample')['observation']
        self.assertEqual(proof['observed_at'],original.isoformat(timespec='microseconds').replace('+00:00','Z'))
        self.assertEqual(proof['last_success_at'],proof['observed_at'])
        self.assertEqual(proof['expires_at'],(original+timedelta(seconds=5)).isoformat(timespec='microseconds').replace('+00:00','Z'))
        self.assertEqual(proof['metrics_expires_at'],proof['expires_at'])
        self.advance(2);self.assertEqual(self.registry.item('sample')['state'],'EXPIRED')
        self.assertEqual(self.registry.item('sample')['observation']['metrics_state'],'EXPIRED')

    def test_slow_staged_probe_cannot_replace_newer_explicit_operation(self):
        self.observer.start();old=self.at;self.advance(2)
        self.registry.record_operation('sample','read','READY','NEWER_EXPLICIT_READ')
        self.probe.observe=lambda:{'state':'UNAVAILABLE','reason':'OLD_FAILURE','metrics':{},
            'observed_at':old,'expires_at':old+timedelta(seconds=9)}
        self.observer.tick(force=True)
        self.assertEqual(self.registry.item('sample')['reason'],'NEWER_EXPLICIT_READ')


class ExistingWorkerObserverTests(unittest.TestCase):
    def test_periodic_checks_run_without_any_page_or_model_request(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        with tempfile.TemporaryDirectory(dir=LAB/'tests',prefix='observer-worker-') as directory:
            app=create_app(Path(directory),local_token='synthetic-only-observer-test-token',
                kernel_config=KernelConfig('isolated-worker-observer',observation_interval_seconds=1,observation_ttl_seconds=3))
            with TestClient(app):
                observer=app.state.kernel.observer;initial=observer.completed;deadline=time.monotonic()+3
                while observer.completed<=initial and time.monotonic()<deadline:time.sleep(0.05)
                self.assertGreater(observer.completed,initial)
                with closing(app.state.product.connect()) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0],0)
                    self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='cognitive_records'").fetchone())

    def test_registry_layer_counts_and_local_check_role_separation(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        with tempfile.TemporaryDirectory(dir=LAB/'tests',prefix='observer-api-') as directory:
            app=create_app(Path(directory),local_token='synthetic-only-observer-test-token',start_worker=False)
            with TestClient(app) as client:
                client.headers['Authorization']='Bearer synthetic-only-observer-test-token'
                path=app.state.kernel.observer.path;before=path.read_bytes();calls=app.state.kernel.observer.completed
                engine=client.get('/dragon/api/v1/modules').json();all_=client.get('/dragon/api/v1/modules?scope=all').json();support=client.get('/dragon/api/v1/modules?scope=supporting').json()
                self.assertEqual(engine['inventory'],{'engines':6,'supporting':12,'total':18})
                self.assertEqual([len(v['items']) for v in (engine,all_,support)],[6,18,12])
                self.assertEqual(len({v['module_id'] for v in all_['items']}),18)
                self.assertTrue(all(v['layer']=='supporting' for v in support['items']))
                self.assertEqual(path.read_bytes(),before);self.assertEqual(app.state.kernel.observer.completed,calls)
                client.headers.clear();self.assertEqual(client.post('/dragon/api/v1/modules/observe',json={}).status_code,401)
                client.headers['Authorization']='Bearer synthetic-only-observer-test-token'
                self.assertEqual(client.post('/dragon/api/v1/modules/observe',json={'url':'https://invalid.example'}).status_code,422)
                response=client.post('/dragon/api/v1/modules/observe',json={});self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()['status'],'completed')
