"""Contract, permissions, durable recovery, exports and canonical navigation."""
from contextlib import closing
from datetime import date, timedelta
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import secrets
import tempfile
import time
import unittest
from unittest.mock import patch

AVAILABLE = importlib.util.find_spec('fastapi') is not None
ROOT = Path(__file__).resolve().parents[1]
API = '/dragon/api/v1'


@unittest.skipUnless(AVAILABLE, 'HTTP checks require the pinned runtime/server-env environment; legacy engine remains dependency-free')
class ProductAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        from dragonhydra import public_results
        (ROOT/'runtime'/'scratch').mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime'/'scratch', prefix='api-test-')
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(Path(self.temp.name), local_token='test-only-local-token-1234567890',
                              bridge_secret='test-only-bridge-secret', start_worker=False)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.product, self.jobs = self.app.state.product, self.app.state.jobs
        self.client.headers['Authorization'] = 'Bearer test-only-local-token-1234567890'
        self.raw = json.dumps({'name': 'Test League 2026/27', 'matches': [
            {'date': '2026-01-01', 'team1': '=Unsafe Team', 'team2': 'Second', 'score': {'ft': [2, 1]}},
            {'date': '2026-01-02', 'team1': 'Second', 'team2': '=Unsafe Team', 'score': {'ft': [0, 0]}},
            {'date': (date.today()+timedelta(days=5)).isoformat(), 'team1': '=Unsafe Team', 'team2': 'Third'}]}).encode()
        with closing(self.product.connect()) as db:
            public_results.ingest_bytes(db, self.raw, source_id='synthetic-contract-test', source_url='https://example.test/fixture')
        self.matches = self.client.get(API+'/matches').json()['items']
        self.finished = next(m for m in self.matches if m['status']=='finished')
        self.future = next(m for m in self.matches if m['status']=='scheduled')

    def bridge(self, method, path, body=b'', role='reader', user='joomla:42', nonce=None):
        stamp, nonce = str(int(time.time())), nonce or secrets.token_hex(16)
        signed = '\n'.join((method, path, stamp, nonce, user, role, hashlib.sha256(body).hexdigest()))
        return {'X-Dragon-User':user, 'X-Dragon-Roles':role, 'X-Dragon-Time':stamp, 'X-Dragon-Nonce':nonce,
                'X-Dragon-Signature':hmac.new(b'test-only-bridge-secret',signed.encode(),hashlib.sha256).hexdigest()}

    def test_authentication_origin_and_error_contract(self):
        self.client.headers.clear()
        self.assertEqual(self.client.get(API+'/matches').status_code, 401)
        self.assertEqual(self.client.get(API+'/health/live').json()['status'], 'alive')
        bad = self.client.post(API+'/session', json={'token':'not-authorized-token-1234'})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(bad.json()['error']['code'], 'INVALID_PAIRING_TOKEN')
        self.assertEqual(self.client.post(API+'/session', json={'token':'test-only-local-token-1234567890'}, headers={'Origin':'https://untrusted.test'}).status_code,403)
        response = self.client.post(API+'/session',json={'token':'test-only-local-token-1234567890'})
        self.assertEqual(response.status_code,200)
        self.assertIn('HttpOnly',response.headers['set-cookie'])
        self.assertEqual(self.client.get(API+'/matches').status_code,200)
        self.assertEqual(self.client.get(API+'/matches?limit=0').status_code,422)
        self.assertEqual(self.client.get(API+'/matches?date=nonsense').status_code,400)
        self.assertEqual(self.client.get(API+'/matches?timezone=Europe%2FBerlin').status_code,200)
        self.assertEqual(self.client.get(API+'/matches?timezone=No%2FZone').status_code,400)

    def test_same_match_navigation_pagination_and_time_precision(self):
        first = self.client.get(API+'/matches?limit=1').json()
        second = self.client.get(API+'/matches?limit=1&offset=1').json()
        self.assertEqual(first['total'],3)
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
        self.assertEqual(self.client.get(API+'/matches?status=live').json()['total'],0)
        row = self.client.get(API+'/matches/'+self.finished['id']).json()
        self.assertIsNone(row['kickoff_utc'])
        self.assertEqual(row['time_precision'],'date')
        team = self.client.get(API+'/teams/'+row['home']['id']).json()
        self.assertIn(row['id'],[r['id'] for r in team['matches']])
        standings = self.client.get(API+'/competitions/'+row['competition_id']+'/standings').json()
        self.assertFalse(standings['official'])
        self.assertEqual(sum(r['played'] for r in standings['items']),4)
        self.assertTrue(all(not self.client.get(API+'/matches/'+row['id']+'/'+p).json()['items'] for p in ('odds','events','lineups','statistics','odds-history')))
        self.assertEqual(self.client.get(API+'/matches/missing').json()['error']['code'],'MATCH_NOT_FOUND')

    def test_forecast_reuses_all_models_for_selected_future_event(self):
        response = self.client.get(API+'/matches/'+self.future['id']+'/predictions')
        self.assertEqual(response.status_code,200,response.text)
        data = response.json()
        self.assertEqual({m['id'] for m in data['models']},{'frequency','poisson_goals','elo','recency'})
        self.assertAlmostEqual(sum(data['ensemble'].values()),1,places=12)
        self.assertFalse(self.client.get(API+'/matches/'+self.finished['id']+'/predictions').json()['available'])

    def test_bridge_signature_replay_permissions_and_owner(self):
        self.client.headers.clear()
        path = API+'/matches?limit=1'
        headers = self.bridge('GET',path)
        self.assertEqual(self.client.get(path,headers=headers).status_code,200)
        self.assertEqual(self.client.get(path,headers=headers).json()['error']['code'],'BRIDGE_REPLAY')
        self.assertEqual(self.client.get(API+'/matches?limit=2',headers=self.bridge('GET',path)).status_code,401)
        path = API+'/connections/openfootball/sync'
        self.assertEqual(self.client.post(path,content=b'{}',headers={**self.bridge('POST',path,b'{}'),'content-type':'application/json'}).status_code,403)
        job=self.jobs.submit('explanation',{'match_id':self.finished['id']},'joomla:other')
        path=API+'/jobs/'+job['id']
        self.assertEqual(self.client.get(path,headers=self.bridge('GET',path)).status_code,403)

    def test_job_idempotency_cancel_and_committed_updates(self):
        path=API+'/connections/openfootball/sync'
        a=self.client.post(path,json={},headers={'Idempotency-Key':'same-import'}).json()
        b=self.client.post(path,json={},headers={'Idempotency-Key':'same-import'}).json()
        self.assertEqual(a['id'],b['id'])
        self.assertEqual(self.client.post(path,json={'mode':'fresh'},headers={'Idempotency-Key':'same-import'}).status_code,409)
        self.assertEqual(self.client.post(API+'/jobs/'+a['id']+'/cancel',json={}).json()['status'],'cancelled')
        self.assertFalse(self.jobs.run_once())
        events=self.jobs.updates(0)
        self.assertEqual(events[-1]['data']['status'],'cancelled')
        self.assertTrue(all('committed_at' in e for e in events))

    def test_expired_lease_recovers_without_duplicate_imports(self):
        job=self.jobs.submit('import_public',{'mode':'retained'},'local:owner','restart')
        with closing(self.product.connect()) as db:
            db.execute("UPDATE product_jobs SET status='running',attempts=1,lease_until=? WHERE id=?",(time.time()-1,job['id']))
            db.commit()
        self.assertTrue(self.jobs.run_once())
        result=self.jobs.get(job['id'])
        self.assertEqual(result['status'],'succeeded',result)
        self.assertEqual(result['attempts'],2)
        count=len(self.product.rows())
        other=self.jobs.submit('import_public',{'mode':'retained'},'local:owner')
        self.jobs.run_once()
        self.assertEqual(self.jobs.get(other['id'])['result']['inserted'],0)
        self.assertEqual(len(self.product.rows()),count)
        self.assertTrue(any(e['data'].get('status')=='interrupted' for e in self.jobs.updates(0)))

    def test_explanation_references_open_retained_source(self):
        response=self.client.post(API+'/matches/'+self.finished['id']+'/explanations',json={})
        self.assertEqual(response.status_code,202)
        job=response.json()
        self.jobs.run_once()
        result=self.jobs.get(job['id'])['result']
        self.assertEqual(result['kind'],'deterministic')
        evidence=self.client.get(result['evidence'][0]['url']).json()
        self.assertEqual(evidence['fixture_key'],self.product.find(self.finished['id'])['fixture_key'])

    def test_real_workbook_csv_json_and_spreadsheet_formula_protection(self):
        from openpyxl import load_workbook
        for kind in ('xlsx','csv','json'):
            response=self.client.post(API+'/exports',json={'match_id':self.finished['id'],'format':kind})
            self.assertEqual(response.status_code,202)
            job_id=response.json()['id']
            self.jobs.run_once()
            job=self.jobs.get(job_id)
            self.assertEqual(job['status'],'succeeded',job)
            result=job['result']
            downloaded=self.client.get(result['download_url'])
            self.assertEqual(downloaded.status_code,200)
            self.assertEqual(hashlib.sha256(downloaded.content).hexdigest(),result['sha256'])
            if kind=='xlsx':
                workbook=load_workbook(self.product.exports/result['filename'])
                self.assertIn('Metadata',workbook.sheetnames)
                for cell in workbook['Match'][2]:
                    self.assertNotEqual(cell.data_type,'f')
                self.assertTrue(any(str(c.value).startswith("'=Unsafe") for c in workbook['Match'][2]))
                self.assertIsInstance(workbook['Match']['F2'].value,int)
                workbook.close()
            elif kind=='json':
                self.assertEqual(downloaded.json()['match']['id'],self.finished['id'])

    def test_provider_failure_retains_cached_records_and_redacts_exception(self):
        count=len(self.product.rows())
        with patch('dragonhydra.jobs.fetch_public',side_effect=TimeoutError('secret=DO_NOT_EXPOSE')), patch('dragonhydra.api.fetch_public',side_effect=TimeoutError('secret=DO_NOT_EXPOSE')):
            probe=self.client.post(API+'/connections/openfootball/test',json={})
            self.assertEqual(probe.json()['status'],'unavailable')
            job=self.jobs.submit('import_public',{'mode':'fresh'},'local:owner')
            for attempt in range(3):
                with closing(self.product.connect()) as db:
                    db.execute('UPDATE product_jobs SET next_attempt=0 WHERE id=?',(job['id'],))
                    db.commit()
                self.jobs.run_once()
        result=self.jobs.get(job['id'])
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['attempts'],3)
        self.assertNotIn('DO_NOT_EXPOSE',json.dumps(result))
        self.assertEqual(len(self.product.rows()),count)

    def test_schema_and_get_requests_do_not_import(self):
        with closing(self.product.connect()) as db:
            before=db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0]
        schema=self.client.get(API+'/openapi.json').json()
        self.assertEqual(schema['components']['schemas']['Match']['properties']['id']['type'],'string')
        self.client.get(API+'/connections')
        self.client.get(API+'/matches')
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0],before)


if __name__=='__main__':
    unittest.main()
