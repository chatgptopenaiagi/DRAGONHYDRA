import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from uuid import uuid4
from urllib.request import urlopen
from dragonhydra.config import PROJECT_ROOT
from dragonhydra.handoff.examples import synthetic_example,desktop_template
from dragonhydra.handoff.contracts import SCHEMA
from dragonhydra.handoff.validator import validate,check_schema,usable_as_of
from dragonhydra.handoff.security import artifact_path,SecurityError
from dragonhydra.handoff.receipts import atomic_publish
from dragonhydra.handoff.consumer import consume_once,ensure_realm
from dragonhydra.handoff.store import BridgeStore,connection
from dragonhydra.web.provenance import encode,digest
from dragonhydra.web.contracts import PipelineError,utcnow
from dragonhydra.web.bridge import bridge_status
from dragonhydra.storage.router import StorageRouter
from dragonhydra.storage.intelligence import maria_connection


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);ensure_realm(self.root);self.e=synthetic_example(self.root)

    def valid(self,e=None):return validate(encode(self.e if e is None else e),self.root)

    def test_valid_handoff_and_hashes(self):
        result=self.valid();self.assertEqual(result.provenance,'SYNTHETIC');self.assertEqual(len(result.normalized),2)
        self.assertEqual(result.manifest_sha256,digest(encode(self.e)));self.assertEqual(result.normalized_hashes[0],digest(encode(result.normalized[0])))

    def test_python314(self):self.assertEqual(sys.version_info[:2],(3,14))

    def test_schema_matches_published(self):
        self.assertEqual(SCHEMA,json.loads((PROJECT_ROOT/'config/browser-handoff-envelope.schema.json').read_text()))

    def test_unknown_field_rejected(self):
        self.e['surprise']=True
        with self.assertRaises(PipelineError):self.valid()

    def test_missing_required_rejected(self):
        del self.e['observations']
        with self.assertRaises(PipelineError):self.valid()

    def test_unknown_version(self):
        self.e['schema_version']='99'
        with self.assertRaises(PipelineError):self.valid()

    def test_partial_json(self):
        with self.assertRaises(PipelineError):validate(b'{"schema_version":"1.0",',self.root)

    def test_duplicate_json_keys(self):
        with self.assertRaises(PipelineError):validate(b'{"schema_version":"1.0","schema_version":"1.0"}',self.root)

    def test_unknown_producer(self):
        self.e['producer']='untrusted-bot'
        with self.assertRaises(PipelineError):self.valid()

    def test_capture_producer_mismatch(self):
        self.e['capture_method']='desktop-browser'
        with self.assertRaisesRegex(PipelineError,'PRODUCER_CAPTURE'):self.valid()

    def test_duplicate_artifact(self):
        self.e['artifacts'].append(copy.deepcopy(self.e['artifacts'][0]))
        with self.assertRaisesRegex(PipelineError,'DUPLICATE_ARTIFACT'):self.valid()

    def test_duplicate_observation(self):
        self.e['observations'].append(copy.deepcopy(self.e['observations'][0]))
        with self.assertRaisesRegex(PipelineError,'DUPLICATE_OBSERVATION'):self.valid()

    def test_duplicate_source(self):
        self.e['sources'].append(copy.deepcopy(self.e['sources'][0]))
        with self.assertRaisesRegex(PipelineError,'DUPLICATE_SOURCE'):self.valid()

    def test_sha_mismatch(self):
        self.e['artifacts'][0]['sha256']='a'*64
        with self.assertRaisesRegex(PipelineError,'HASH_OR_SIZE'):self.valid()

    def test_artifact_size_mismatch(self):
        self.e['artifacts'][0]['size_bytes']+=1
        with self.assertRaisesRegex(PipelineError,'HASH_OR_SIZE'):self.valid()

    def test_path_traversal_unc_absolute_ads(self):
        for path in ('../outside','runtime/handoff/browser_downloads/../secret.json','C:\\Windows\\x.json','\\\\server\\share\\x.json','runtime/handoff/browser_downloads/a.json:payload','runtime/handoff/browser_downloads/%2e%2e/a.json','runtime/handoff/browser_downloads/foo. /x.json'):
            with self.subTest(path=path),self.assertRaises(SecurityError):artifact_path(self.root,path)

    def test_executable_not_executed(self):
        a=self.e['artifacts'][0];p=self.root/a['relative_path'];p.write_bytes(b'MZdanger');a['sha256']=digest(b'MZdanger');a['size_bytes']=8
        with self.assertRaisesRegex(PipelineError,'EXECUTABLE'):self.valid()

    def test_unknown_artifact_extension(self):
        self.e['artifacts'][0]['relative_path']='runtime/handoff/browser_downloads/unknown.exe'
        with self.assertRaisesRegex(PipelineError,'UNKNOWN_ARTIFACT'):self.valid()

    def test_secret_like_values(self):
        for text in ('password=not-a-real-secret','Cookie: sid=not-real','Authorization: Bearer not-real','api_key=unit-test','Bearer fake-credential-123'):
            self.e['notes']=text
            with self.subTest(text=text),self.assertRaises(SecurityError):self.valid()

    def test_embedded_credential_fields(self):
        self.e['cookies']={'fake':'test'}
        with self.assertRaises(SecurityError):self.valid()

    def test_sql_instruction_field_rejected(self):
        self.e['sql']='DROP TABLE example'
        with self.assertRaises(SecurityError):self.valid()

    def test_sql_injection_string_is_data(self):
        self.e['observations'][0]['value']="x'; DROP TABLE dragonhydra.Source; --"
        result=self.valid();self.assertEqual(result.normalized[0]['value'],self.e['observations'][0]['value'])

    def test_invalid_timestamp(self):
        self.e['created_at']='not-a-date'
        with self.assertRaises(ValueError):self.valid()

    def test_naive_timestamp(self):
        self.e['created_at']='2026-01-01T00:00:00'
        with self.assertRaises(PipelineError):self.valid()

    def test_future_timestamp(self):
        self.e['created_at']='2099-01-01T00:00:00Z'
        with self.assertRaisesRegex(PipelineError,'FUTURE_TIMESTAMP'):self.valid()

    def test_future_leakage(self):
        r=dict(self.valid().normalized[0],ingested_at=utcnow())
        with self.assertRaisesRegex(PipelineError,'FUTURE_LEAKAGE'):usable_as_of(r,'2000-01-01T00:00:00Z')
        self.assertTrue(usable_as_of(r,utcnow()))

    def test_unlabelled_synthetic_rejected(self):
        self.e['observations'][0]['synthetic']=False
        with self.assertRaisesRegex(PipelineError,'SYNTHETIC_LABEL_REQUIRED'):self.valid()

    def test_non_https_and_url_credentials(self):
        for url in ('http://example.org/x','https://u:p@example.org/x','https://example.org/x?token=abc'):
            self.e['sources'][0]['url']=url
            with self.subTest(url=url),self.assertRaises(PipelineError):self.valid()

    def test_localhost_development_allowed(self):
        self.e['sources'][0]['url']='http://localhost:8080/test';self.valid()

    def test_blocked_desktop_evidence_not_success(self):
        e=desktop_template();e.update(reason='BROWSER_UNAVAILABLE',observed_failure='Browser tool did not open',notes='Actual test simulation, not live browser evidence')
        result=self.valid(e);self.assertEqual(result.provenance,'DESKTOP_BLOCKED');self.assertEqual(result.normalized,())

    def test_template_cannot_claim_capture(self):
        with self.assertRaisesRegex(PipelineError,'TEMPLATE_NOT_CAPTURED'):self.valid(desktop_template())

    def test_desktop_success_requires_hashed_evidence_artifact(self):
        from dragonhydra.web.terms import load_sources
        e=self.e;e.update(producer='codex-desktop',capture_method='desktop-browser',browser_evidence='missing-artifact.txt')
        policy=load_sources(PROJECT_ROOT)['openfootball'];s=e['sources'][0]
        s.update(source_id='openfootball',url=policy['allowed_urls'][0],source_type='PUBLIC_DATASET',access_method='rendered-browser',terms_status='ALLOWED_RESEARCH',license_status='CC0-1.0',robots_status='ABSENT')
        for o in e['observations']:o['source_id']='openfootball'
        with self.assertRaisesRegex(PipelineError,'DESKTOP_EVIDENCE_ARTIFACT_REQUIRED'):self.valid()
        e['browser_evidence']=e['artifacts'][0]['relative_path'];self.assertEqual(self.valid().provenance,'DESKTOP_CONFIRMED')

    def test_atomic_publish_and_collision(self):
        p=atomic_publish(self.e,self.root);self.assertTrue(p.name.endswith('.handoff.json'))
        with self.assertRaises(FileExistsError):atomic_publish(self.e,self.root)

    def test_batch_bounded(self):
        with self.assertRaises(ValueError):consume_once(self.root,limit=100)

    def test_ownership(self):
        r=StorageRouter();self.assertEqual([r.handoff_owner(k) for k in ('HANDOFF_RAW','STRUCTURED_INTELLIGENCE','WEB_PRESENTATION_CACHE','ANALYTICAL_DERIVED')],['filesystem','sqlserver','mariadb','future_parquet'])

    def test_failed_routing_and_receipt(self):
        hid=str(uuid4());p=self.root/'runtime/handoff/browser_inbox'/f'{hid}.handoff.json';p.write_text('{broken')
        with patch('dragonhydra.handoff.consumer.refresh_summary',return_value={}):r=consume_once(self.root)[0]
        self.assertEqual(r['status'],'FAILED');self.assertFalse(p.exists());self.assertTrue(Path(r['receipt_path']).exists())
        self.assertEqual(r['manifest_sha256'],digest(b'{broken'));self.assertEqual(len(list((self.root/'runtime/handoff/failed').glob('*.handoff.json'))),1)

    def test_secret_rejection_protected_not_logs(self):
        self.e['notes']='password=unit-test-fake-secret';p=self.root/'runtime/handoff/browser_inbox'/f'{self.e["handoff_id"]}.handoff.json';p.write_bytes(encode(self.e))
        with patch('dragonhydra.handoff.consumer.refresh_summary',return_value={}):r=consume_once(self.root)[0]
        self.assertEqual(r['status'],'FAILED')
        for path in (self.root/'runtime/handoff').rglob('*.json'):self.assertNotIn('unit-test-fake-secret',path.read_text())
        self.assertTrue(list((self.root/'runtime/secrets/handoff-quarantine').rglob('*.quarantined')))

    def test_unknown_inbox_file_quarantined(self):
        p=self.root/'runtime/handoff/browser_inbox/unknown.exe';p.write_bytes(b'MZnot-executed')
        with patch('dragonhydra.handoff.consumer.refresh_summary',return_value={}):r=consume_once(self.root)[0]
        self.assertEqual(r['reason'],'UNEXPECTED_FILE_TYPE');self.assertFalse(p.exists())

    def test_temporary_and_legacy_files_ignored(self):
        inbox=self.root/'runtime/handoff/browser_inbox';(inbox/'writing.tmp').write_text('{')
        (inbox/'legacy.json').write_text(json.dumps({'handoff_id':'old','download_path':'old','processing_status':'PENDING','capture_method':'old'}))
        self.assertEqual(consume_once(self.root),[])

    def test_cache_failure_after_sql_is_replay_safe(self):
        p=atomic_publish(self.e,self.root)
        with patch('dragonhydra.handoff.consumer.BridgeStore') as store,patch('dragonhydra.handoff.consumer.refresh_summary',side_effect=RuntimeError('cache offline')):
            store.return_value.ingest.return_value=({'HandoffEnvelope':1,'Observation':2,'ProcessingReceipt':1},False)
            r=consume_once(self.root)[0]
        self.assertTrue(r['sql_committed']);self.assertEqual(r['status'],'FAILED')
        self.assertIn('SQL_COMMITTED_REPLAY_SAFE_CACHE_OR_RECEIPT_FAILURE',r['warnings'])
        atomic_publish(self.e,self.root)
        with patch('dragonhydra.handoff.consumer.BridgeStore') as store,patch('dragonhydra.handoff.consumer.refresh_summary',return_value={}):
            store.return_value.ingest.return_value=({'HandoffEnvelope':0,'Observation':0,'ProcessingReceipt':0},True)
            r=consume_once(self.root)[0]
        self.assertEqual(r['status'],'DUPLICATE');self.assertEqual(r['sql_server_rows_inserted']['Observation'],0)


class LiveBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cp=Path((PROJECT_ROOT/'runtime/bridge-current.txt').read_text().strip())
        cls.e=json.loads((cp/'synthetic-handoff.json').read_text());cls.v=validate(encode(cls.e),PROJECT_ROOT)

    def assert_current_summary_matches_receipt(self, summary):
        # Historical fixture assertions below remain SYNTHETIC; presentation follows
        # the latest real ingestion, which may be a recorded blocked Desktop attempt.
        with connection(read=True) as c:
            cur=c.cursor()
            row=cur.execute('SELECT TOP(1) handoff_id,producer,provenance,status,manifest_sha256 FROM dragonhydra.HandoffEnvelope ORDER BY ingested_at DESC').fetchone()
            self.assertIsNotNone(row)
            receipt_row=cur.execute("SELECT TOP(1) payload FROM dragonhydra.ProcessingReceipt WHERE handoff_id=? AND phase='FINAL' ORDER BY processed_at DESC",row[0]).fetchone()
            self.assertIsNotNone(receipt_row)
            receipt=json.loads(receipt_row[0])
            observations=cur.execute('SELECT COUNT(*) FROM dragonhydra.Observation WHERE handoff_id=?',row[0]).fetchone()[0]
        checkpoint=Path(receipt['checkpoint_path']).resolve()
        self.assertTrue(checkpoint.is_relative_to(PROJECT_ROOT/'runtime/checkpoints'))
        self.assertEqual(receipt,json.loads((checkpoint/'receipt.json').read_text()))
        archived=(checkpoint/'handoff.json').read_bytes()
        validated=validate(archived,PROJECT_ROOT);envelope=validated.envelope
        self.assertEqual(tuple(row),(envelope['handoff_id'],envelope['producer'],validated.provenance,envelope['status'],digest(archived)))
        self.assertEqual(receipt['handoff_id'],row[0])
        self.assertEqual(receipt['manifest_sha256'],digest(archived))
        self.assertEqual(receipt['provenance'],validated.provenance)
        self.assertEqual(receipt['normalized_payload_hashes'],list(validated.normalized_hashes))
        self.assertEqual(receipt['validation_result'],'ACCEPT');self.assertTrue(receipt['sql_committed'])
        expected_status='BLOCKED' if envelope['status']=='BLOCKED' else 'DUPLICATE' if receipt['idempotent_replay'] else 'PROCESSED'
        self.assertEqual(receipt['status'],expected_status)
        for field,expected in {
            'last_handoff_id':row[0],'last_attempt_handoff_id':receipt['handoff_id'],
            'producer':row[1],'provenance':row[2],'pipeline_status':row[3],
            'consumer_status':receipt['status'],'last_attempt_provenance':receipt['provenance'],
        }.items():
            with self.subTest(field=field):self.assertEqual(summary[field],expected)
        bridge=bridge_status(PROJECT_ROOT)
        self.assertEqual(bridge['handoff_id'],row[0])
        self.assertEqual(summary['bridge_state'],bridge['state'])
        self.assertEqual(summary['desktop_handoff_status'],bridge['desktop_result'])
        if envelope['status']=='BLOCKED':
            if envelope['producer']=='codex-desktop':self.assertEqual(validated.provenance,'DESKTOP_BLOCKED')
            self.assertEqual(observations,0);self.assertEqual(validated.normalized,())
            self.assertEqual(receipt['sql_server_rows_inserted']['Observation'],0)
            self.assertIn('SOURCE_BLOCKED_EVIDENCE_ONLY',receipt['warnings'])
            self.assertEqual(bridge['state'],'BLOCKED')
            self.assertNotEqual(bridge['last_desktop_handoff_id'],row[0])
            if bridge['last_desktop_handoff_id'] is None:self.assertEqual(summary['desktop_handoff_status'],'NOT_CONFIRMED')
        return row[0]

    def test_duplicate_handoff_no_duplicate_observations(self):
        counts,replay=BridgeStore().ingest(self.v)
        self.assertTrue(replay);self.assertEqual(counts['Observation'],0)
        with connection(read=True) as c:
            n=c.cursor().execute('SELECT COUNT(*) FROM dragonhydra.Observation WHERE handoff_id=?',self.e['handoff_id']).fetchone()[0]
            self.assertEqual(n,2)

    def test_collision_rejected(self):
        e=copy.deepcopy(self.e);e['notes']='Changed same-ID content'
        with self.assertRaisesRegex(PipelineError,'HANDOFF_ID_COLLISION'):BridgeStore().ingest(validate(encode(e),PROJECT_ROOT))

    def test_sql_ingestion_provenance(self):
        with connection(read=True) as c:
            row=c.cursor().execute('SELECT producer,provenance FROM dragonhydra.HandoffEnvelope WHERE handoff_id=?',self.e['handoff_id']).fetchone()
            self.assertEqual(tuple(row),('test-fixture','SYNTHETIC'))

    def test_sql_bounded_permissions(self):
        for read in (False,True):
            with connection(read=read) as c:
                cur=c.cursor();self.assertEqual(tuple(cur.execute("SELECT IS_SRVROLEMEMBER('sysadmin'),IS_SRVROLEMEMBER('securityadmin'),IS_MEMBER('db_owner')").fetchone()),(0,0,0))
                self.assertEqual(cur.execute("SELECT HAS_PERMS_BY_NAME('dragonhydra.Observation','OBJECT','UPDATE')").fetchone()[0],0)
                self.assertEqual(cur.execute("SELECT HAS_PERMS_BY_NAME('dragonhydra.Observation','OBJECT','DELETE')").fetchone()[0],0)
                self.assertEqual(cur.execute("SELECT HAS_PERMS_BY_NAME('dragonhydra.Observation','OBJECT','INSERT')").fetchone()[0],0 if read else 1)
                self.assertEqual(cur.execute("SELECT HAS_PERMS_BY_NAME('probe.CapabilitySample','OBJECT','SELECT')").fetchone()[0],0)

    def test_sql_injection_roundtrip_rollback(self):
        injection="x'; DROP TABLE dragonhydra.Source; --"
        with connection() as c:
            cur=c.cursor();rid=uuid4().hex
            cur.execute('INSERT INTO dragonhydra.ProcessingReceipt(receipt_id,handoff_id,phase,processed_at,payload) VALUES(?,?,?,?,?)',rid,self.e['handoff_id'],'TEST',utcnow(),json.dumps({'value':injection}))
            stored=json.loads(cur.execute('SELECT payload FROM dragonhydra.ProcessingReceipt WHERE receipt_id=?',rid).fetchone()[0]);self.assertEqual(stored['value'],injection);c.rollback()

    def test_sql_asof_no_historical_leakage(self):
        self.assertEqual(BridgeStore().as_of('2000-01-01T00:00:00Z'),[])
        self.assertGreaterEqual(len(BridgeStore().as_of(utcnow())),2)

    def test_maria_summary_only(self):
        with maria_connection('web') as c:
            cur=c.cursor();cur.execute("SELECT payload FROM presentation_cache WHERE cache_key='desktop_cli_bridge'");s=json.loads(cur.fetchone()[0])
            self.assertGreaterEqual(s['observation_count'],2);self.assertNotIn('observations',s)
            self.assert_current_summary_matches_receipt(s)

    def test_joomla_bridge_endpoint(self):
        with urlopen('http://localhost/joomla-codex-lab/dragonhydra/?format=json',timeout=10) as r:
            self.assertEqual(r.status,200);dto=json.load(r)
        latest_handoff_id=self.assert_current_summary_matches_receipt(dto['desktop_cli_bridge'])
        with urlopen('http://localhost/joomla-codex-lab/dragonhydra/',timeout=10) as r:
            html=r.read().decode();self.assertIn('Desktop / CLI data bridge v1',html);self.assertIn(latest_handoff_id,html)

    def test_receipt_exists_complete(self):
        r=json.loads((PROJECT_ROOT/'runtime/handoff/receipts'/f'{self.e["handoff_id"]}.receipt.json').read_text())
        self.assertEqual(r['manifest_sha256'],self.v.manifest_sha256);self.assertEqual(r['validation_result'],'ACCEPT')
        self.assertEqual(r['sql_server_rows_inserted']['Observation'],2);self.assertEqual(r['mariadb_rows_updated'],2)
        self.assertTrue(Path(r['checkpoint_path']).is_dir())
