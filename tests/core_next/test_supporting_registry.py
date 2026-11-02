"""Genuine supporting definitions and synthetic owned-receipt validation."""
from contextlib import closing
from datetime import datetime,timedelta,timezone
import json,os,sqlite3,tempfile,unittest
from pathlib import Path
from dragonhydra.kernel.contracts import KernelConfig
from dragonhydra.kernel.ports import StoragePort,ApplicationContext
from dragonhydra.kernel.supporting import SupportingObservations,definitions

ROOT=Path(__file__).resolve().parents[2]
LAB=Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')


class SupportingRegistryTests(unittest.TestCase):
    def setUp(self):
        (LAB/'tests').mkdir(exist_ok=True)
        t=tempfile.TemporaryDirectory(dir=LAB/'tests',prefix='supporting-');self.addCleanup(t.cleanup)
        self.root=Path(t.name);self.state=self.root/'state/kernel';self.state.mkdir(parents=True)
        self.db=self.state/'core.sqlite3';self.at=datetime(2026,11,2,tzinfo=timezone.utc)
        with closing(sqlite3.connect(self.db)) as c:
            c.executescript('CREATE TABLE product_schema(version);CREATE TABLE product_jobs(id,status);CREATE TABLE connector_settings(provider,config,interval_seconds,next_due);')
        self.config=KernelConfig('core-next-support-fixture',source_commit='a'*40,build_id='fixture-build')
        self.cfg={'product':'DRAGONHYDRA CORE NEXT','installation_id':self.config.installation_id,
            'source_commit':self.config.source_commit,'build_id':self.config.build_id,'state_root':str(self.state.parent),
            'install_root':str(self.root/'application'),'service_name':'DragonhydraCoreNextfixture',
            'api_port':18891,'web_port':18892,'database_port':18893,'admin_password':'SYNTHETIC_NOT_A_REAL_PASSWORD'}
        self.cfgpath=self.state.parent/'workstation.json';self.cfgpath.write_text(json.dumps(self.cfg))
        def forbidden():raise AssertionError('Supporting observations must not use write connections')
        context=ApplicationContext(StoragePort(self.state,self.db,ROOT,self.state/'exports',forbidden),None,lambda:self.at.isoformat())
        self.source=SupportingObservations(context,self.config,lambda:self.at)
    def receipt(self,**changes):
        value={'schema_version':2,'observer':'core-next.supervisor',
            **{k:self.cfg[k] for k in ('installation_id','source_commit','build_id','service_name')},
            'api_pid':os.getpid(),'supervisor_pid':1234,'observed_at':self.at.isoformat(),
            'api_verified':True,'last_success_at':self.at.isoformat(),
            'expires_at':(self.at+timedelta(seconds=45)).isoformat(),'checks':{
                'web_server':{'state':'READY','reason':'LOOPBACK_HTTP_REACHABLE','scope':'HTTP_REACHABILITY_ONLY','metrics':{'http_status':200},'observed_at':self.at.isoformat(),'last_success_at':self.at.isoformat()}}}
        value.update(changes);(self.state.parent/'runtime-observations.json').write_text(json.dumps(value))
    def test_all_supporting_definitions_have_actual_sources_and_inspection_bindings(self):
        values=definitions('0.5.0-dev.2');self.assertEqual(len(values),12)
        self.assertEqual(len({v.id for v in values}),12)
        bindings=self.source.bindings()
        for value in values:
            self.assertTrue((ROOT/value.implementation_reference).exists(),value.implementation_reference)
            self.assertEqual(value.layer,'supporting');self.assertTrue(value.runtime_owner)
            self.assertTrue(callable(bindings[value.id].status))
    def test_external_receipt_needs_fresh_clocks_build_and_owned_process_identity(self):
        self.receipt();self.assertEqual(self.source.observe('web_server')['state'],'READY')
        self.assertEqual(self.source.observe('runtime_supervisor')['state'],'READY')
        for changes in ({'api_pid':os.getpid()+1},{'source_commit':'b'*40},{'supervisor_pid':None},
                {'supervisor_pid':True},{'supervisor_pid':0},{'observed_at':None},
                {'observed_at':(self.at+timedelta(seconds=1)).isoformat()},
                {'expires_at':self.at.isoformat()},{'schema_version':3}):
            with self.subTest(fields=changes):
                self.receipt(**changes);self.assertNotEqual(self.source.observe('runtime_supervisor')['state'],'READY')
        for changes in ({'api_verified':False},{'last_success_at':None},{'last_success_at':(self.at+timedelta(seconds=1)).isoformat()},
                {'last_success_at':(self.at-timedelta(seconds=91)).isoformat()}):
            self.receipt(**changes);self.assertNotEqual(self.source.observe('runtime_supervisor')['state'],'READY')
    def test_unknown_profile_is_not_mislabelled_as_non_applicable(self):
        self.cfg['installation_id']='another-profile';self.cfgpath.write_text(json.dumps(self.cfg))
        value=self.source.observe('web_server');self.assertEqual(value['state'],'UNAVAILABLE')
        self.assertNotIn('SYNTHETIC_NOT_A_REAL_PASSWORD',json.dumps(value))
    def test_scheduler_counts_actual_interval_schema_without_reading_secret_config(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('INSERT INTO connector_settings VALUES(?,?,?,?)',('fake','SYNTHETIC invalid secret JSON never read',60,0));c.commit()
        value=self.source.observe('provider_scheduler')
        self.assertEqual(value['metrics']['enabled_schedules'],1)
        self.assertEqual(value['state'],'UNAVAILABLE') # no worker in this fixture
        self.assertNotIn('secret JSON',json.dumps(value))
    def test_no_store_does_not_create_file_or_infer_zero_schedules(self):
        self.db.unlink();self.source.begin_cycle()
        self.assertEqual(self.source.observe('sqlite_storage')['state'],'UNAVAILABLE')
        self.assertEqual(self.source.observe('provider_scheduler')['state'],'UNAVAILABLE')
        self.assertFalse(self.db.exists())
    def test_external_clients_remain_unverified_from_sources_or_files(self):
        for identifier in ('windows_desktop','android_client'):
            self.assertEqual(self.source.observe(identifier)['state'],'UNVERIFIED')
