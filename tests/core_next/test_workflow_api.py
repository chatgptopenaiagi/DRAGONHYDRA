"""Typed workflow routes, bridge roles, durable replay and restart in LAB only."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from dragonhydra import public_results
from dragonhydra.api import create_app
from dragonhydra.kernel import KernelConfig


LAB = Path('C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB')
API = '/dragon/api/v1'
LOCAL = 'synthetic-workflow-api-local-token'
BRIDGE = 'synthetic-workflow-api-bridge-secret'


class WorkflowAPITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=LAB/'tests', prefix='workflow-api-')
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        self.open_client()
        day = datetime.now(timezone.utc).date()
        document = {'name': 'Fictional workflow API league', 'matches': [
            {'date': str(day-timedelta(days=20-index)), 'team1': 'Home' if index == 0 else f'Other {index}',
             'team2': 'Away' if index == 1 else f'Visitor {index}', 'score': {'ft': [index % 3, (index+1) % 2]}}
            for index in range(8)] + [
            {'date': str(day+timedelta(days=5)), 'team1': 'Home', 'team2': 'Away'},
            {'date': str(day+timedelta(days=6)), 'team1': 'Other target', 'team2': 'Other visitor'}]}
        with closing(self.product.connect()) as db:
            public_results.ingest_bytes(db, json.dumps(document).encode(),
                source_id='fictional-workflow-api', source_url='fictional:test-only')
        matches = self.product.matches()['items']
        self.target = next(row for row in matches if row['home']['name'] == 'Home' and row['status'] == 'scheduled')
        self.other = next(row for row in matches if row['home']['name'] == 'Other target')

    def open_client(self):
        self.app = create_app(self.state, local_token=LOCAL, bridge_secret=BRIDGE, start_worker=False,
            kernel_config=KernelConfig('core-next-workflow-api-fixture', environment_id='candidate'))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.client.headers['Authorization'] = 'Bearer '+LOCAL
        self.product, self.jobs = self.app.state.product, self.app.state.jobs

    def bridge(self, method, path, body=b'', role='reader'):
        stamp, nonce, user = str(int(time.time())), secrets.token_hex(16), 'joomla:424242'
        signed = '\n'.join((method, path, stamp, nonce, user, role, hashlib.sha256(body).hexdigest()))
        return {'X-Dragon-User': user, 'X-Dragon-Roles': role, 'X-Dragon-Time': stamp, 'X-Dragon-Nonce': nonce,
                'X-Dragon-Signature': hmac.new(BRIDGE.encode(), signed.encode(), hashlib.sha256).hexdigest()}

    def test_anonymous_and_reader_permissions_empty_body_and_no_backdating(self):
        history = API+'/matches/'+self.target['id']+'/cognition-history'
        self.client.headers.clear()
        self.assertEqual(self.client.get(history).status_code, 401)
        read = self.client.get(history, headers=self.bridge('GET', history))
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()['schema_version'], 'core-next.workflow/1')
        self.assertEqual(read.json()['installation']['installation_id'], 'core-next-workflow-api-fixture')
        for suffix in ('forecasts', 'evaluations'):
            path = API+'/matches/'+self.target['id']+'/'+suffix
            self.assertEqual(self.client.post(path, json={}).status_code, 401)
            self.assertEqual(self.client.post(path, content=b'{}', headers={
                **self.bridge('POST', path, b'{}'), 'Content-Type': 'application/json'}).status_code, 403)
            self.client.headers['Authorization'] = 'Bearer '+LOCAL
            self.assertEqual(self.client.post(path, json={'cutoff': '2020-01-01T00:00:00Z'}).status_code, 422)
            self.assertEqual(self.client.post(path, json={'run_id': 'caller-controlled'}).status_code, 422)
            self.client.headers.clear()
        self.assertEqual(self.client.post(API+'/modules/observe', content=b'{}', headers={
            **self.bridge('POST', API+'/modules/observe', b'{}'), 'Content-Type': 'application/json'}).status_code, 403)
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0], 0)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='cognitive_records'").fetchone())

    def test_durable_forecast_jobs_bind_owner_key_run_and_same_state_restart(self):
        path = API+'/matches/'+self.target['id']+'/forecasts'
        first = self.client.post(path, json={}, headers={'Idempotency-Key': 'synthetic-forecast-click'})
        second = self.client.post(path, json={}, headers={'Idempotency-Key': 'synthetic-forecast-click'})
        self.assertEqual(first.status_code, 202, first.text)
        self.assertEqual(first.json()['id'], second.json()['id'])
        job_id = first.json()['id']
        other = API+'/matches/'+self.other['id']+'/forecasts'
        self.assertEqual(self.client.post(other, json={}, headers={'Idempotency-Key': 'synthetic-forecast-click'}).status_code, 409)
        self.assertTrue(self.jobs.run_once())
        completed = self.client.get(API+'/jobs/'+job_id).json()
        self.assertEqual(completed['status'], 'succeeded', completed['error'])
        self.assertEqual(completed['result']['run_id'], job_id)
        self.assertEqual(len(completed['result']['predictions']), 5)
        self.assertEqual(completed['result']['installation']['installation_id'], 'core-next-workflow-api-fixture')
        stored_ids = [row['record_id'] for row in completed['result']['predictions']]
        self.client.__exit__(None, None, None)
        self.open_client()
        replay = self.client.post(path, json={}, headers={'Idempotency-Key': 'synthetic-forecast-click'})
        self.assertEqual(replay.json()['id'], job_id)
        self.assertEqual([row['record_id'] for row in replay.json()['result']['predictions']], stored_ids)
        history = self.client.get(API+'/matches/'+self.target['id']+'/cognition-history').json()
        self.assertEqual(history['counts']['predictions'], 5)

    def test_evaluation_job_is_honestly_pending_without_later_result(self):
        forecast = self.client.post(API+'/matches/'+self.target['id']+'/forecasts', json={})
        self.assertEqual(forecast.status_code, 202)
        self.assertTrue(self.jobs.run_once())
        queued = self.client.post(API+'/matches/'+self.target['id']+'/evaluations', json={},
                                  headers={'Idempotency-Key': 'synthetic-evaluation-click'})
        self.assertEqual(queued.status_code, 202)
        self.assertTrue(self.jobs.run_once())
        result = self.client.get(API+'/jobs/'+queued.json()['id']).json()
        self.assertEqual(result['status'], 'succeeded', result['error'])
        self.assertEqual(result['result']['status'], 'pending')
        self.assertEqual(result['result']['reason'], 'LATER_RETAINED_OUTCOME_UNAVAILABLE')
        self.assertEqual(result['result']['persisted_evaluations'], [])


if __name__ == '__main__':
    unittest.main()
