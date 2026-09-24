import copy
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from uuid import uuid4
from urllib.request import urlopen,Request
from urllib.error import HTTPError

from dragonhydra.config import PROJECT_ROOT
from dragonhydra.web.contracts import FetchPolicy,HandoffManifest,PipelineError,public_url,utcnow
from dragonhydra.web.provenance import digest,encode,exclusive_json,bounded_file
from dragonhydra.web.terms import load_sources,allow_source
from dragonhydra.web.robots import evaluate_robots
from dragonhydra.web.fetch import fetch,_request
from dragonhydra.web.html import parse_html
from dragonhydra.web.json_api import parse_json
from dragonhydra.web.odds import probability,overround,normalized_probabilities,movement,OddsObservation,compare_quotes,validate_temporal
from dragonhydra.web.validation import validate_observation
from dragonhydra.web.license_evidence import evidence_record,extract_pdf,readable_english
from dragonhydra.web.bridge import bridge_event,bridge_status,manifest_origin
from dragonhydra.web.pipeline import process_item,normalize_matches
from dragonhydra.storage.intelligence import IntelligenceStore,PresentationStore,sql_connection,maria_connection
from dragonhydra.storage.router import StorageRouter,DataClass


def manifest(**changes):
    now=utcnow()
    d=dict(handoff_id=uuid4().hex,created_at=now,created_by='unit test',source_url=load_sources(PROJECT_ROOT)['openfootball']['allowed_urls'][0],
           source_title='test',source_type='PUBLIC_DATASET',capture_method='PYTHON_ALLOWED_FETCH',
           download_path='runtime/handoff/browser_downloads/test.json',content_hash=digest(b'{}'),observed_at=now,
           event_time_if_known=None,terms_note='test',robots_note='ABSENT',license_note='CC0-1.0',confidence=0.8,
           processing_status='PENDING',source_id='openfootball',content_type='text/plain')
    d.update(changes)
    return HandoffManifest(**d)


def quote(**changes):
    now=utcnow()
    d=dict(observation_id=uuid4().hex,fixture_id='test-fixture',source_id='test',bookmaker='synthetic',market_type='h2h',
           market_key='h2h',selection='home',line_value=None,decimal_odds=2.0,implied_probability=0.5,
           observed_at=now,available_at=now,event_at=None,expires_at=None,currency_if_relevant=None,
           market_status='UNKNOWN',source_url='https://example.org/test',source_hash=digest(b'test'),confidence=1.,
           verification_state='UNCONFIRMED',updated_at=now,synthetic=True)
    d.update(changes)
    return OddsObservation(**d)


class WebContractsTests(unittest.TestCase):
    def test_manifest_roundtrip(self):
        m=manifest(); self.assertEqual(HandoffManifest(**json.loads(encode(m))),m)

    def test_manifest_invalid_hash(self):
        with self.assertRaises(PipelineError):manifest(content_hash='bad')

    def test_manifest_missing_field(self):
        with self.assertRaises(PipelineError):manifest(terms_note='')

    def test_manifest_naive_time(self):
        with self.assertRaises(PipelineError):manifest(observed_at='2026-01-01T00:00:00')

    def test_manifest_future(self):
        with self.assertRaises(PipelineError):manifest(created_at='2099-01-01T00:00:00Z')

    def test_invalid_urls(self):
        for url in ('http://example.org','https://localhost/x','https://127.0.0.1/x','file:///x','https://example.org?key=secret','https://a:b@example.org/x','https://example.org:8443/x','https://example.org/\nx'):
            with self.subTest(url=url),self.assertRaises(PipelineError):public_url(url)

    def test_hash_exact_bytes(self):
        self.assertEqual(digest(b'abc'),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

    def test_path_escape_and_size(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            root=Path(folder); (root/'inbox').mkdir(); (root/'outside').write_bytes(b'secret')
            with self.assertRaises(PipelineError):bounded_file(root/'outside',root/'inbox')
            p=root/'inbox/big';p.write_bytes(b'abcdef')
            with self.assertRaises(PipelineError):bounded_file(p,root/'inbox',2)

    def test_immutable_checkpoint(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            p=Path(folder)/'receipt.json';exclusive_json(p,{'a':1})
            with self.assertRaises(FileExistsError):exclusive_json(p,{'a':2})

    def test_fetch_policy_bounds(self):
        for changes in ({'timeout':31},{'retry_count':3},{'max_bytes':5_000_001},{'rate_limit':0},{'method':'POST'}):
            with self.subTest(changes=changes),self.assertRaises(PipelineError):FetchPolicy('x','https://example.org/x','test',**changes)

    def test_terms_unverified_denied(self):
        s=load_sources(PROJECT_ROOT)['openfootball'].copy();s['terms_verification']='UNVERIFIED'
        with self.assertRaisesRegex(PipelineError,'UNVERIFIED'):allow_source(s,s['allowed_urls'][0])

    def test_terms_prohibited(self):
        s=load_sources(PROJECT_ROOT)['openfootball'].copy();s['terms_status']='PROHIBITED'
        with self.assertRaisesRegex(PipelineError,'TERMS_BLOCKED'):allow_source(s,s['allowed_urls'][0])

    def test_terms_exact_url(self):
        s=load_sources(PROJECT_ROOT)['openfootball']
        with self.assertRaises(PipelineError):allow_source(s,'https://raw.githubusercontent.com/other/file')

    def test_robots_disallow(self):
        r=evaluate_robots('User-agent: *\nDisallow: /private\nCrawl-delay: 5','https://example.org/private/a','Test')
        self.assertEqual(r['robots_status'],'DISALLOWED');self.assertEqual(r['crawl_delay_if_any'],5)

    def test_robots_allow_and_absent(self):
        self.assertEqual(evaluate_robots('User-agent: *\nAllow: /','https://example.org/a','Test')['robots_status'],'ALLOWED')
        self.assertEqual(evaluate_robots('','https://example.org/a','Test',404)['robots_status'],'ABSENT')

    def test_robots_unavailable_closed(self):
        with self.assertRaises(PipelineError):evaluate_robots('','https://example.org/a','Test',503)

    def test_fetch_terms_blocks_before_network(self):
        s=load_sources(PROJECT_ROOT)['statsbomb-open']
        with patch('dragonhydra.web.fetch._request') as request,self.assertRaises(PipelineError):
            fetch(FetchPolicy(s['source_id'],s['allowed_urls'][0],'test'),s)
        request.assert_not_called()

    def test_dns_private_blocked(self):
        with patch('dragonhydra.web.fetch.LIMITER.wait'),patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),self.assertRaisesRegex(PipelineError,'NON_PUBLIC_DNS'):
            _request(FetchPolicy('x','https://example.org/x','test'))

    def test_fetch_response_limits_and_failure_no_retry(self):
        for status,ctype,body,expected in ((429,'text/plain',b'','RATE_LIMITED'),(401,'text/plain',b'','AUTH_REQUIRED'),
                (302,'text/plain',b'','HTTP_ERROR'),(200,'image/png',b'','CONTENT_TYPE_UNEXPECTED'),
                (200,'text/plain',b'123456','MAX_BYTES_EXCEEDED'),(200,'text/plain',b'captcha','CAPTCHA_PRESENT')):
            with self.subTest(expected=expected):
                response=MagicMock();response.status=status
                response.getheader.side_effect=lambda k,default=None:{'Content-Type':ctype,'Content-Encoding':'identity'}.get(k,default)
                response.read1.side_effect=[body,b''];conn=MagicMock();conn.getresponse.return_value=response
                with patch('dragonhydra.web.fetch.LIMITER.wait'),patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]),patch('socket.create_connection'),patch('ssl.create_default_context'),patch('http.client.HTTPSConnection',return_value=conn),self.assertRaisesRegex(PipelineError,expected):
                    _request(FetchPolicy('x','https://example.org/x','test',max_bytes=5 if expected=='MAX_BYTES_EXCEEDED' else 100))
                conn.request.assert_called_once()

    def test_html_no_scripts_executed(self):
        p=parse_html(b'<h1>A &amp; B</h1><script>bad()</script><a href="/x">X</a>')
        self.assertEqual(p['text'],'A & B X');self.assertEqual(p['links'],['/x'])

    def test_json_invalid_and_duplicate_fields(self):
        for raw in (b'bad',b'{"a":1,"a":2}',b'{"a":NaN}',b'1'):
            with self.assertRaises(PipelineError):parse_json(raw)
        self.assertEqual(parse_json(b'{"a":1}'),{'a':1})

    def test_odds_invalid(self):
        for v in (0,1,-1,float('nan'),float('inf'),True):
            with self.assertRaises(PipelineError):probability(v)

    def test_odds_math(self):
        self.assertEqual(probability(2),0.5)
        self.assertAlmostEqual(overround([2,3.5,4]),0.0357142857142856)
        self.assertAlmostEqual(sum(normalized_probabilities([2,3.5,4])),1)
        self.assertEqual(movement(2,2.2,'2026-01-01T00:00:00Z','2026-01-01T00:01:00Z')['seconds_between'],60)
        self.assertAlmostEqual(movement(2,2.2,'2026-01-01T00:00:00Z','2026-01-01T00:01:00Z')['percentage_movement'],10)

    def test_missing_quote_not_suspended(self):
        self.assertEqual(quote().market_status,'UNKNOWN')

    def test_unknown_market(self):
        with self.assertRaisesRegex(PipelineError,'UNKNOWN_MARKET'):quote(market_type='mystery')

    def test_duplicate_conflict_and_movement_distinct(self):
        q=quote();self.assertEqual(compare_quotes(q,replace(q,observation_id='other')),'DUPLICATE')
        self.assertEqual(compare_quotes(q,replace(q,decimal_odds=3,implied_probability=1/3)),'CONFLICTING_DATA')
        self.assertEqual(compare_quotes(q,replace(q,source_id='other')),'DISTINCT')

    def test_timestamp_order(self):
        with self.assertRaises(PipelineError):validate_temporal('2026-02-01T00:00:00Z','2026-01-01T00:00:00Z','2026-03-01T00:00:00Z')

    def test_future_leakage_and_boundary(self):
        with self.assertRaisesRegex(PipelineError,'FUTURE_LEAKAGE'):
            validate_temporal('2026-01-01T00:00:00Z','2026-02-01T00:00:00Z','2026-02-01T00:00:00Z','2026-01-15T00:00:00Z')
        validate_temporal('2026-01-01T00:00:00Z','2026-02-01T00:00:00Z','2026-02-01T00:00:00Z','2026-02-01T00:00:00Z')

    def test_router_single_owner(self):
        r=StorageRouter();self.assertEqual(r.route(r.classify('odds')),'sqlserver');self.assertEqual(r.route(r.classify('job')),'mariadb')
        self.assertEqual(r.route(DataClass.ANALYTICAL),'future_parquet')
        with self.assertRaises(TypeError):r.route('CACHE')

    def test_medusa_verdicts(self):
        m=manifest();s=load_sources(PROJECT_ROOT)['openfootball']
        r=normalize_matches(encode({'name':'League','matches':[{'team1':'A','team2':'B','date':'2020-01-01','round':'1','score':{'ft':[1,0]}}]}),m,s,{'robots_status':'ABSENT'})[0]
        self.assertIsNone(r['event_at'])
        self.assertEqual(validate_observation(r,s).decision,'ACCEPT')
        self.assertEqual(validate_observation(r,s,conflict=True).decision,'QUARANTINE')
        self.assertEqual(validate_observation(r,s,duplicate=True).decision,'REJECT')
        self.assertEqual(validate_observation(r,s,now=datetime.now(timezone.utc)+timedelta(days=40)).decision,'ACCEPT_WITH_WARNING')


class LicenseBridgeTests(unittest.TestCase):
    def test_corrupted_license_cannot_verify(self):
        for text in ('','Ɨ΀Ȅ΀ͯ'*100,'The data service agreement research user '+chr(0)*10,'\ufffd'*300):
            e=evidence_record(b'pdf',text,'https://example.org/license',utcnow(),'pypdf/6.19.0',reviewed=True,review_note='test')
            self.assertEqual(e['TERMS_STATUS'],'UNVERIFIED');self.assertEqual(e['LICENSE_STATUS'],'UNVERIFIED')

    def test_readable_does_not_auto_approve(self):
        text='The user data service agreement terms research is available. '*30
        self.assertTrue(readable_english(text))
        self.assertEqual(evidence_record(b'pdf',text,'https://example.org/license',utcnow(),'pypdf/6.19.0')['TERMS_STATUS'],'UNVERIFIED')

    def test_unreadable_pdf_stays_unverified(self):
        text,method=extract_pdf(b'%PDF-broken',PROJECT_ROOT)
        self.assertEqual(evidence_record(b'%PDF-broken',text,'https://example.org/license',utcnow(),method)['LICENSE_STATUS'],'UNVERIFIED')

    def test_statsbomb_unverified_explicit(self):
        source=load_sources(PROJECT_ROOT)['statsbomb-open']
        self.assertEqual(source['license_status'],'UNVERIFIED');self.assertEqual(source['terms_status'],'UNVERIFIED')

    def test_bridge_states_and_cli_not_desktop(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            root=Path(folder);self.assertEqual(bridge_status(root)['state'],'NO_HANDOFF')
            bridge_event(root,'CLI_FETCHED','CLI_FETCH','test')
            bridge_event(root,'PROCESSED','CLI_FETCH','test')
            status=bridge_status(root);self.assertEqual(status['state'],'PROCESSED');self.assertEqual(status['desktop_result'],'NOT_CONFIRMED')
            self.assertEqual(manifest_origin(manifest()),'CLI_FETCH')

    def test_desktop_confirmation_requires_evidence(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            with self.assertRaises(ValueError):bridge_event(Path(folder),'DESKTOP_CONFIRMED','CLI_FETCH','test')

    def test_desktop_handoff_processed_changes_bridge(self):
        # Actual processor path, isolated test DB mocks and test evidence; never a live Desktop claim.
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            root=Path(folder)
            for d in ('browser_inbox','browser_downloads','browser_notes','processed','failed'):(root/'runtime/handoff'/d).mkdir(parents=True)
            body=encode({'name':'Test','matches':[{'team1':'A','team2':'B','date':'2020-01-01','round':'1','score':{'ft':[1,0]}}]})
            m=manifest(content_hash=digest(body),capture_method='DESKTOP_BROWSER_RENDERED')
            (root/m.download_path).write_bytes(body)
            path=root/'runtime/handoff/browser_inbox'/f'{m.handoff_id}.json';exclusive_json(path,m)
            exclusive_json(root/'runtime/handoff/browser_notes'/f'{m.handoff_id}.json',{'SOURCE_URL':m.source_url,'DESKTOP_STAGE':'CONFIRMED','BROWSER_EVIDENCE':'test-only browser capture','CONTENT_HASH':m.content_hash})
            with patch('dragonhydra.web.pipeline.load_sources',return_value=load_sources(PROJECT_ROOT)),patch('dragonhydra.web.pipeline._request',return_value=(b'','text/plain',404)),patch('dragonhydra.web.pipeline.sql_connection'),patch('dragonhydra.web.pipeline.PresentationStore'),patch('dragonhydra.web.pipeline.IntelligenceStore') as store:
                store.return_value.previous.return_value=None
                result=process_item(path,root)
            self.assertEqual(result['status'],'SUCCEEDED')
            state=bridge_status(root);self.assertEqual(state['state'],'PROCESSED');self.assertEqual(state['origin'],'DESKTOP_BROWSER');self.assertEqual(state['desktop_result'],'CONFIRMED')

    def test_summary_dynamic_latest_bridge(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            root=Path(folder)
            with patch('dragonhydra.storage.intelligence.PROJECT_ROOT',root),patch('dragonhydra.storage.intelligence.sql_connection') as connection:
                cur=connection.return_value.__enter__.return_value.cursor.return_value
                cur.fetchone.return_value=None
                # Counts require a row; last fetch/processing are null payloads represented by valid JSON.
                cur.fetchone.side_effect=[(0,),(0,),(0,),(0,),None,None]*2
                cur.fetchall.return_value=[]
                bridge_event(root,'CLI_FETCHED','CLI_FETCH','one')
                self.assertEqual(IntelligenceStore().summary()['browser_handoff'],'CLI_FETCHED')
                bridge_event(root,'FAILED','CLI_FETCH','one')
                summary=IntelligenceStore().summary()
                self.assertEqual(summary['browser_handoff'],'FAILED');self.assertEqual(summary['bridge']['desktop_result'],'NOT_CONFIRMED')

    def test_hash_failure_moves_to_failed_without_sql(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            root=Path(folder)
            for d in ('browser_inbox','browser_downloads','failed'):(root/'runtime/handoff'/d).mkdir(parents=True)
            m=manifest();(root/m.download_path).write_bytes(b'tampered')
            path=root/'runtime/handoff/browser_inbox'/f'{m.handoff_id}.json';exclusive_json(path,m)
            with patch('dragonhydra.web.pipeline.load_sources',return_value=load_sources(PROJECT_ROOT)),patch('dragonhydra.web.pipeline.PresentationStore'),patch('dragonhydra.web.pipeline.sql_connection') as sql:
                result=process_item(path,root)
            self.assertEqual(result['reason'],'HASH_MISMATCH');self.assertFalse(path.exists())
            self.assertEqual(len(list((root/'runtime/handoff/failed').glob('*.receipt.json'))),1)
            self.assertEqual(bridge_status(root)['state'],'FAILED');sql.assert_not_called()

    def test_cli_processing_never_confirms_desktop(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            root=Path(folder)
            for d in ('browser_inbox','browser_downloads','processed','failed'):(root/'runtime/handoff'/d).mkdir(parents=True)
            body=encode({'name':'Test','matches':[{'team1':'A','team2':'B','date':'2020-01-01','round':'1'}]})
            m=manifest(content_hash=digest(body));(root/m.download_path).write_bytes(body)
            path=root/'runtime/handoff/browser_inbox'/f'{m.handoff_id}.json';exclusive_json(path,m)
            with patch('dragonhydra.web.pipeline.load_sources',return_value=load_sources(PROJECT_ROOT)),patch('dragonhydra.web.pipeline._request',return_value=(b'','text/plain',404)),patch('dragonhydra.web.pipeline.sql_connection'),patch('dragonhydra.web.pipeline.PresentationStore'),patch('dragonhydra.web.pipeline.IntelligenceStore') as store:
                store.return_value.previous.return_value=None
                result=process_item(path,root)
            self.assertEqual(result['status'],'SUCCEEDED')
            state=bridge_status(root);self.assertEqual(state['state'],'PROCESSED');self.assertEqual(state['origin'],'CLI_FETCH');self.assertEqual(state['desktop_result'],'NOT_CONFIRMED')


class LiveWebSQLTests(unittest.TestCase):
    def test_sql_append_versions_injection_and_rollback(self):
        store=IntelligenceStore();key='test-'+uuid4().hex+"'; DROP TABLE dragonhydra.sources;--";now=utcnow()
        with sql_connection() as conn:
            first,added=store.append(conn,'sources',key,{'name':key},'test',now)
            second,added2=store.append(conn,'sources',key,{'name':key},'test',now)
            third,_=store.append(conn,'sources',key,{'name':key,'revision':2},'test',now)
            self.assertTrue(added);self.assertFalse(added2);self.assertEqual(first,second);self.assertNotEqual(first,third)
            rows=conn.cursor().execute('SELECT version,supersedes_id FROM dragonhydra.sources WHERE natural_key=? ORDER BY version',key).fetchall()
            self.assertEqual([r[0] for r in rows],[1,2]);self.assertEqual(rows[1][1],first)
            conn.rollback()

    def test_sql_runtime_cannot_mutate_history(self):
        for role in ('ingest','read'):
            with sql_connection(role) as conn:
                cur=conn.cursor();cur.execute("SELECT IS_SRVROLEMEMBER('sysadmin'),IS_MEMBER('db_owner')")
                self.assertEqual(tuple(cur.fetchone()),(0,0))
                with self.assertRaises(Exception):cur.execute('UPDATE dragonhydra.sources SET version=version WHERE 1=0')
                conn.rollback()
                with self.assertRaises(Exception):cur.execute('DELETE FROM dragonhydra.sources WHERE 1=0')
                conn.rollback()

    def test_sql_read_identity_cannot_insert(self):
        with sql_connection('read') as conn:
            with self.assertRaises(Exception):conn.cursor().execute('INSERT INTO dragonhydra.sources SELECT * FROM dragonhydra.sources WHERE 1=0')
            conn.rollback()

    def test_sql_asof_excludes_late_discovery(self):
        self.assertEqual(IntelligenceStore().fixtures_as_of('2000-01-01T00:00:00Z'),[])
        self.assertGreater(len(IntelligenceStore().fixtures_as_of(utcnow())),0)

    def test_maria_cache_and_web_readonly(self):
        with maria_connection('web') as conn:
            cur=conn.cursor();cur.execute("SELECT payload FROM presentation_cache WHERE cache_key='intelligence'")
            dto=json.loads(cur.fetchone()[0]);self.assertGreaterEqual(dto['counts']['fixtures'],380)
            with self.assertRaises(Exception):cur.execute('UPDATE presentation_cache SET payload=payload WHERE 1=0')
            with self.assertRaises(Exception):cur.execute('SELECT * FROM job_state LIMIT 1')
            conn.rollback()

    def test_maria_ops_cannot_touch_joomla(self):
        with maria_connection() as conn:
            with self.assertRaises(Exception):conn.cursor().execute('SELECT * FROM joomla_codex_lab.j5faba9_users LIMIT 0')
            conn.rollback()

    def test_joomla_endpoint_200_and_bridge(self):
        with urlopen('http://localhost/joomla-codex-lab/dragonhydra/',timeout=10) as r:
            self.assertEqual(r.status,200);html=r.read().decode();self.assertIn('SYNTHETIC DATA',html)
        with urlopen('http://localhost/joomla-codex-lab/dragonhydra/?format=json',timeout=10) as r:
            dto=json.load(r)
        self.assertEqual(dto['browser_handoff'],bridge_status(PROJECT_ROOT)['state'])
        self.assertEqual(dto['bridge']['origin'],bridge_status(PROJECT_ROOT)['origin'])
        self.assertIn(dto['bridge']['desktop_result'],html)

    def test_endpoint_rejects_post_and_untrusted_host(self):
        for request in (Request('http://localhost/joomla-codex-lab/dragonhydra/',method='POST'),Request('http://127.0.0.1/joomla-codex-lab/dragonhydra/',headers={'Host':'evil.example'})):
            with self.assertRaises(HTTPError) as error:urlopen(request,timeout=10)
            self.assertIn(error.exception.code,(403,405))
            error.exception.close()

    def test_secrets_absent_from_evidence_and_web(self):
        passwords=[json.loads(p.read_text())['password'] for p in (PROJECT_ROOT/'runtime/secrets').glob('web-*.json')]
        for path in list((PROJECT_ROOT/'runtime/checkpoints').glob('web-*.json'))+list((PROJECT_ROOT/'runtime/handoff').rglob('*.json')):
            data=path.read_text(encoding='utf-8')
            self.assertTrue(all(p not in data for p in passwords),path.name)
        with urlopen('http://localhost/joomla-codex-lab/dragonhydra/?format=json',timeout=10) as r:
            body=r.read().decode()
            self.assertTrue(all(p not in body for p in passwords))
