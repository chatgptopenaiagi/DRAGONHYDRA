"""Offline guards for the A6 journey; never construct its live-state Journey."""
from contextlib import closing, redirect_stderr
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_a6_installed_guard_test',ROOT/'tests/installation/context_ai_workstation.py')
helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)


class InstalledContextGuards(unittest.TestCase):
    def argv(self,*extra):
        result=['--installer','dist/connections/workstation-a6/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe',
            '--extraction','dist/connections/workstation-a6/EXTRACTION-VERIFICATION.json',
            '--output','build/workstation/evidence/SYNTHETIC-never-run']
        for name in ('installer_sha256','installer_bytes','extraction_sha256','kernel_sha256','source_content_sha256',
                     'source_manifest_sha256','ui_sha256'):
            result.extend(['--'+name.replace('_','-'),str(helper.A6[name])])
        return result+list(extra)

    def rejected(self,*extra):
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:
            helper.arguments(self.argv(*extra))
        self.assertEqual(error.exception.code,2)

    def test_explicit_apply_and_reviewed_receipt_gates_before_construction(self):
        with patch.object(helper.Journey,'__init__',side_effect=AssertionError('Live Journey forbidden')):
            self.assertEqual(helper.arguments(self.argv()).phase,'preflight')
            self.rejected('--apply')
            self.rejected('--phase','repair')
            self.rejected('--phase','repair','--apply')
            self.rejected('--phase','readchecks','--apply')
            self.rejected('--phase','repair','--apply','--preflight-receipt','SYNTHETIC.json')
            args=helper.arguments(self.argv('--phase','repair','--apply','--preflight-receipt','SYNTHETIC.json',
                '--preflight-receipt-sha256','a'*64))
            self.assertTrue(args.apply)

    def test_strict_hash_and_length_arguments(self):
        for value in ('','A'*64,'a'*63,'a'*65,'../other','a'*64+'\n'):
            self.rejected('--kernel-sha256',value)
        self.rejected('--installer-bytes','0')
        self.rejected('--installer-bytes','-1')

    def test_wrong_approval_pin_fails_before_any_artifact_or_live_read(self):
        args=helper.arguments(self.argv('--kernel-sha256','a'*64))
        journey=object.__new__(helper.Journey); journey.args=args
        with patch.object(helper.prior,'digest',side_effect=AssertionError('No file reads')):
            with self.assertRaisesRegex(AssertionError,'approval pins'):
                journey.artifact()

    def test_wrong_installer_path_fails_before_hashing_or_service_access(self):
        args=helper.arguments(self.argv('--installer','SYNTHETIC-not-approved.exe'))
        journey=object.__new__(helper.Journey); journey.args=args
        with patch.object(helper.prior,'digest',side_effect=AssertionError('No file reads')):
            with self.assertRaises(AssertionError): journey.artifact()

    def test_job_idempotency_key_is_redacted_but_not_mistaken_for_a_credential_echo(self):
        journey=object.__new__(helper.Journey)
        journey.url='http://127.0.0.1:18746'; journey.token='SYNTHETIC-pairing-credential'
        key='SYNTHETIC-idempotency-intent'
        journey.private=[journey.token,key]; journey.redact_only={key}
        body={'idempotency_key':key,'id':'2'*32}
        def response(value):
            incoming=io.BytesIO(json.dumps(value).encode()); incoming.code=200
            return incoming
        journey.opener=SimpleNamespace(open=lambda *args,**kwargs:response(body))
        self.assertEqual(journey.call('/jobs/'+'2'*32),(200,body))
        self.assertNotIn(key,journey.safe(json.dumps(body)))
        journey.opener=SimpleNamespace(open=lambda *args,**kwargs:response({'untrusted_echo':journey.token}))
        with self.assertRaises(AssertionError): journey.call('/jobs/'+'2'*32)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'runtime/scratch',prefix='a6-guard-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.kernel=Path(self.temp.name)
        (self.kernel/'raw/connectors').mkdir(parents=True)
        self.db_path=self.kernel/'core.sqlite3'
        with closing(sqlite3.connect(self.db_path)) as db:
            db.executescript('''CREATE TABLE raw_sources(id TEXT PRIMARY KEY,body BLOB);
                CREATE TABLE connector_acquisitions(sha256 TEXT,raw_reference TEXT,bytes INTEGER);
                CREATE TABLE connector_observations(seq INTEGER PRIMARY KEY AUTOINCREMENT,provider TEXT,source_record_id TEXT);
                CREATE TABLE public_fixture_records(id TEXT PRIMARY KEY);
                CREATE TABLE cognitive_records(id TEXT PRIMARY KEY,payload TEXT);
                CREATE TABLE cognitive_receipts(id TEXT PRIMARY KEY,payload TEXT);
                CREATE TABLE product_jobs(id TEXT PRIMARY KEY,owner TEXT,kind TEXT,status TEXT,attempts INTEGER,created_at TEXT,updated_at TEXT,payload TEXT,idempotency_key TEXT);
                CREATE TABLE product_updates(seq INTEGER PRIMARY KEY AUTOINCREMENT,topic TEXT,payload TEXT,committed_at TEXT);
                CREATE TABLE product_sessions(token_hash TEXT PRIMARY KEY);
                CREATE TABLE product_bridge_nonces(nonce TEXT PRIMARY KEY);''')
            db.execute('INSERT INTO raw_sources VALUES(?,?)',('SYNTHETIC',b'SYNTHETIC retained bytes'))
            db.execute('INSERT INTO product_jobs VALUES(?,?,?,?,?,?,?,?,?)',('1'*32,'fixture:owner','export','succeeded',1,'old','old','{}',None))
            db.execute('INSERT INTO product_updates(topic,payload,committed_at) VALUES(?,?,?)',('data','{}','old'))
            db.execute('INSERT INTO product_sessions VALUES(?)',('a'*64,)); db.commit()
        self.before=helper.snapshot(self.kernel)

    def mutate(self,callback):
        with closing(sqlite3.connect(self.db_path)) as db:
            callback(db); db.commit()

    def add(self,ident,kind='local_explanation',*,event_count=4):
        def action(db):
            db.execute('INSERT INTO product_jobs VALUES(?,?,?,?,?,?,?,?,?)',(ident,'fixture:owner',kind,'succeeded',1,'new','new','{}','SYNTHETIC-key-'+ident))
            events=[('job',{'id':ident,'status':state}) for state in ('queued','running','succeeded')]+[('data',{'job_id':ident,'kind':kind})]
            for topic,event in events[:event_count]:
                db.execute('INSERT INTO product_updates(topic,payload,committed_at) VALUES(?,?,?)',(topic,json.dumps(event),'new'))
        self.mutate(action)

    def test_snapshot_is_read_only_and_keeps_auth_values_out_of_rows(self):
        fingerprint=hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        result=helper.snapshot(self.kernel)
        self.assertEqual(hashlib.sha256(self.db_path.read_bytes()).hexdigest(),fingerprint)
        self.assertNotIn('product_sessions',result['row_hashes'])
        self.assertIn('product_sessions',result['auth_tables'])
        self.assertNotIn('a'*64,json.dumps(result))

    def test_one_own_job_four_events_with_separate_unproven_concurrent_additions(self):
        own='2'*32; self.add(own); self.add('3'*32,'export')
        result=helper.compare(self.before,helper.snapshot(self.kernel),own)
        self.assertEqual(result['own_outbox_events'],4)
        self.assertEqual([job['id'] for job in result['other_jobs']],['3'*32])
        self.assertEqual(len(result['other_outbox_events']),4)
        self.assertEqual(result['concurrent_additions_origin'],'unproven')

    def test_auth_lifecycle_is_separate_and_old_non_auth_rows_stay_exact(self):
        self.mutate(lambda db:db.execute('UPDATE product_sessions SET token_hash=?',('b'*64,)))
        result=helper.compare(self.before,helper.snapshot(self.kernel))
        self.assertNotEqual(result['auth_lifecycle_before'],result['auth_lifecycle_after'])
        self.mutate(lambda db:db.execute('UPDATE product_jobs SET status=? WHERE id=?',('failed','1'*32)))
        with self.assertRaisesRegex(AssertionError,'old non-auth row'):
            helper.compare(self.before,helper.snapshot(self.kernel))

    def test_public_blob_or_schema_change_cannot_hide_as_job_growth(self):
        self.mutate(lambda db:db.execute('UPDATE raw_sources SET body=?',(b'changed',)))
        with self.assertRaisesRegex(AssertionError,'old non-auth row'):
            helper.compare(self.before,helper.snapshot(self.kernel))
        self.mutate(lambda db:db.execute('CREATE TABLE unexpected(id INTEGER)'))
        with self.assertRaisesRegex(AssertionError,'Schema changed'):
            helper.compare(self.before,helper.snapshot(self.kernel))

    def test_own_missing_event_or_unbacked_sequence_advance_fails(self):
        own='2'*32; self.add(own,event_count=3)
        with self.assertRaises(AssertionError): helper.compare(self.before,helper.snapshot(self.kernel),own)
        self.mutate(lambda db:db.execute("UPDATE sqlite_sequence SET seq=seq+1 WHERE name='product_updates'"))
        with self.assertRaises(AssertionError): helper.compare(self.before,helper.snapshot(self.kernel))

    def test_changed_or_missing_referenced_raw_is_rejected(self):
        body=b'SYNTHETIC document'; sha=hashlib.sha256(body).hexdigest()
        self.mutate(lambda db:db.execute('INSERT INTO connector_acquisitions VALUES(?,?,?)',(sha,sha+'.payload',len(body))))
        with self.assertRaises(AssertionError): helper.snapshot(self.kernel)
        (self.kernel/'raw/connectors'/(sha+'.payload')).write_bytes(b'changed')
        with self.assertRaises(AssertionError): helper.snapshot(self.kernel)


if __name__=='__main__': unittest.main()
