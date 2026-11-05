"""Bounded offline guards only; no installed profile, service or HTTP calls."""
from pathlib import Path
from contextlib import closing
import argparse, copy, hashlib, importlib.util, json, sqlite3, tempfile, unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dev7_service_adapter',ROOT/'tests/installation/dev7_service_acceptance.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
TARGET='d'*64

class AdapterGuards(unittest.TestCase):
    def test_release_versions_match_their_exact_frozen_source_matrices(self):
        for source,version in [('a'*40,'0.5.0-dev.7'),('b'*40,'0.5.0-dev.8')]:
            with self.subTest(version=version),patch.object(m,'source_bytes',return_value=json.dumps({'product_version':version}).encode()) as frozen,patch.object(m.subprocess,'check_output') as process:
                m.validate_release_identity(source,version)
                frozen.assert_called_once_with(source,'packaging/release/version.json')
                process.assert_not_called()
    def test_wrong_version_or_different_source_matrix_is_rejected(self):
        matrices={'a'*40:{'product_version':'0.5.0-dev.7'},'b'*40:{'product_version':'0.5.0-dev.8'}}
        for source,version in [('a'*40,'0.5.0-dev.8'),('b'*40,'0.5.0-dev.7'),('b'*40,'0.5.0-dev.8-tampered'),('b'*40,None)]:
            with self.subTest(source=source,version=version),patch.object(m,'source_bytes',side_effect=lambda sha,path:json.dumps(matrices[sha]).encode()) as frozen,patch.object(m.subprocess,'check_output') as process:
                with self.assertRaisesRegex(m.GateError,'RELEASE_VERSION_NOT_FROZEN_SOURCE'):m.validate_release_identity(source,version)
                frozen.assert_called_once_with(source,'packaging/release/version.json')
                process.assert_not_called()
    def test_invalid_source_is_refused_before_frozen_source_or_subprocess_access(self):
        for source in [None,'','a'*39,'A'*40,'HEAD','a'*40+':other','--help',123]:
            with self.subTest(source=source),patch.object(m,'source_bytes') as frozen,patch.object(m.subprocess,'check_output') as process:
                with self.assertRaisesRegex(m.GateError,'RELEASE_IDENTITY_REQUIRED'):m.validate_release_identity(source,'0.5.0-dev.8')
                frozen.assert_not_called();process.assert_not_called()
    def test_tampered_or_malformed_frozen_matrix_is_rejected(self):
        for matrix in [b'{"product_version":"changed"}',b'{}',b'[]',b'{"product_version":8}',b'{"product_version":""}',b'{broken',b'\xff']:
            with self.subTest(matrix=matrix),patch.object(m,'source_bytes',return_value=matrix),patch.object(m.subprocess,'check_output') as process:
                with self.assertRaises(m.GateError):m.validate_release_identity('b'*40,'0.5.0-dev.8')
                process.assert_not_called()
    def test_read_modes_forbid_every_state_changing_route(self):
        for phase in ['read-fresh','restart-readback','repair-readback','reinstall-readback']:
            for route in ['/research/storage/initialize','/matches/'+TARGET+'/forecasts','/exports','/modules/observe','/system/shutdown']:
                with self.subTest(phase=phase,route=route),self.assertRaises(m.GateError):m.authorize(phase,'POST',route,TARGET,{})
            m.authorize(phase,'GET','/research/storage',TARGET,{})
    def test_workflows_are_phase_specific_and_no_generic_proxy_or_provider(self):
        cases={'initialize':'/research/storage/initialize','forecast':'/matches/'+TARGET+'/forecasts','publication-denied':'/matches/'+TARGET+'/research/archives','publish':'/exports'}
        for phase,path in cases.items():
            m.authorize(phase,'POST',path,TARGET,{})
            for wrong in ['/jobs','/connections/api-football/sync','https://example.invalid','/system/shutdown']:
                with self.subTest(phase=phase,path=wrong),self.assertRaises(m.GateError):m.authorize(phase,'POST',wrong,TARGET,{})
        with self.assertRaises(m.GateError):m.authorize('publication-denied','POST','/exports',TARGET,{})
    def test_job_and_download_gets_are_owned_ids_only(self):
        identity='a'*32
        for route in ['/jobs/'+identity,'/exports/'+identity+'/download']:m.authorize('restart-readback','GET',route,TARGET,{identity:'succeeded'})
        for route in ['/jobs/'+'b'*32,'/exports/'+'b'*32+'/download','/jobs/../state','/connections']:
            with self.subTest(route=route),self.assertRaises(m.GateError):m.authorize('read-fresh','GET',route,TARGET,{identity:'succeeded'})
    def test_support_provenance_and_only_two_literal_seams(self):
        b={'installation_id':'core-next-'+'e'*32,'source_commit':'a'*40,'version':'0.5.0-dev.7','setup':{'path':str(m.LAB/'dist/test.exe'),'sha256':'b'*64},
           'target_match_id':TARGET,'ports':{'api':19991,'web':19992,'database':19993},'profile':{'path':str(m.LAB/'profiles'/('core-next-'+'e'*32)/'installation-profile.json')},
           'operation_root':str(m.LAB/'fixture-operation'),'profile_helper':{'path':str(ROOT/'packaging/windows/workstation/CoreNextProfile.ps1'),'sha256':'c'*64},'build_id':'fixture-dev7'}
        support=m.support_module(b,{},argparse.Namespace(bindings_sha256='f'*64))
        self.assertEqual(support.SOURCE,'a'*40);self.assertEqual(support.FRESH,b['installation_id'])
        self.assertIn('fixture-dev7',support.guard_profile.__code__.co_consts)
        self.assertNotIn('package-dev5-r1',support.guard_profile.__code__.co_consts)
        self.assertIn(b['profile_helper']['path'],support.Acceptance.ownership.__code__.co_consts)
        with self.assertRaises(m.GateError):m.specialize(support,'guard_profile','NOT_A_LITERAL','new')
    def fixture(self,status):
        folder=m.LAB/'tests';folder.mkdir(exist_ok=True)
        temp=tempfile.TemporaryDirectory(prefix='dev7-service-guards-',dir=folder);self.addCleanup(temp.cleanup);root=Path(temp.name)
        before=root/'before.sqlite3';after=root/'after.sqlite3'
        db=sqlite3.connect(before)
        db.executescript('CREATE TABLE product_jobs(id TEXT PRIMARY KEY,kind TEXT,status TEXT,attempts INTEGER);CREATE TABLE product_updates(seq INTEGER PRIMARY KEY AUTOINCREMENT,topic TEXT,payload TEXT);')
        db.execute('INSERT INTO product_jobs VALUES(?,?,?,?)',('old','export','succeeded',1));db.execute('INSERT INTO product_updates(topic,payload) VALUES(?,?)',('job','{}'));db.commit()
        other=sqlite3.connect(after);db.backup(other);db.close()
        identity='a'*32;other.execute('INSERT INTO product_jobs VALUES(?,?,?,?)',(identity,'research_archive',status,1))
        for state in ['queued','running',status]:other.execute('INSERT INTO product_updates(topic,payload) VALUES(?,?)',('job',json.dumps({'id':identity,'status':state})))
        if status=='succeeded':other.execute('INSERT INTO product_updates(topic,payload) VALUES(?,?)',('data',json.dumps({'job_id':identity,'kind':'research_archive'})))
        other.commit();other.close();return before,after,identity
    def test_failed_publication_three_events_and_success_four_events(self):
        for status,count in [('failed',3),('succeeded',4)]:
            before,after,identity=self.fixture(status);result=m.job_delta(before,after,{identity:status})
            self.assertEqual(result['new_events'],count);self.assertEqual(result['approved_jobs'],1)
    def test_unapproved_job_and_changed_old_row_fail(self):
        before,after,identity=self.fixture('failed')
        with self.assertRaisesRegex(m.GateError,'UNAPPROVED_JOB_DELTA'):m.job_delta(before,after,{})
        with closing(sqlite3.connect(after)) as db,db:db.execute("UPDATE product_jobs SET kind='changed' WHERE id='old'")
        with self.assertRaisesRegex(m.GateError,'PREEXISTING'):m.job_delta(before,after,{identity:'failed'})
    def test_extra_event_and_retry_fail(self):
        before,after,identity=self.fixture('failed')
        with closing(sqlite3.connect(after)) as db,db:db.execute('UPDATE product_jobs SET attempts=2 WHERE id=?',(identity,))
        with self.assertRaisesRegex(m.GateError,'RETRY'):m.job_delta(before,after,{identity:'failed'})
        with closing(sqlite3.connect(after)) as db,db:
            db.execute('UPDATE product_jobs SET attempts=1 WHERE id=?',(identity,));db.execute('INSERT INTO product_updates(topic,payload) VALUES(?,?)',('job',json.dumps({'id':identity,'status':'failed'})))
        with self.assertRaisesRegex(m.GateError,'TRANSITION'):m.job_delta(before,after,{identity:'failed'})
    def test_sqlite_sequence_drift_fails(self):
        before,after,identity=self.fixture('failed')
        with closing(sqlite3.connect(after)) as db,db:db.execute("UPDATE sqlite_sequence SET seq=999 WHERE name='product_updates'")
        with self.assertRaisesRegex(m.GateError,'SEQUENCE_MAX'):m.job_delta(before,after,{identity:'failed'})

if __name__=='__main__':unittest.main(verbosity=2)
