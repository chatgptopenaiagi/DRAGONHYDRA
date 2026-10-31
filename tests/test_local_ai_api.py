"""Authenticated package export and evidence-frozen optional worker inference."""
from contextlib import closing
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from dragonhydra import public_results
from dragonhydra.local_ai import LocalAIError, build_package, canonical, observations, validate_output
from dragonhydra.local_ai_service import explain
from dragonhydra.product import now

ROOT = Path(__file__).resolve().parents[1]
API = '/dragon/api/v1'


@unittest.skipUnless(importlib.util.find_spec('fastapi'), 'Pinned server environment required')
class LocalAIAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime/scratch', prefix='local-ai-api-')
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(Path(self.temp.name), local_token='local-ai-fixture-owner-token', start_worker=False)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.client.headers['Authorization'] = 'Bearer local-ai-fixture-owner-token'
        self.product, self.jobs = self.app.state.product, self.app.state.jobs
        self.ingest(2)
        self.match = self.product.matches()['items'][0]
        self.path = API+'/matches/'+self.match['id']

    def ingest(self, goals):
        raw = json.dumps({'name': 'Fixture League 2026/27', 'matches': [
            {'date': '2026-10-01', 'team1': 'First', 'team2': 'Second', 'score': {'ft': [goals, 1]}}
        ]}).encode()
        with closing(self.product.connect()) as db:
            public_results.ingest_bytes(db, raw, source_id='synthetic-local-ai-api', source_url='https://example.test/fixture')

    def test_package_requires_authentication_and_resolves_retained_evidence_without_inference(self):
        self.client.headers.clear()
        self.assertEqual(self.client.get(self.path+'/analysis-package').status_code, 401)
        self.client.headers['Authorization'] = 'Bearer local-ai-fixture-owner-token'
        with patch('dragonhydra.local_ai.infer') as inference:
            response = self.client.get(self.path+'/analysis-package')
        self.assertEqual(response.status_code, 200)
        package = response.json()
        self.assertEqual(package['event']['id'], self.match['id'])
        self.assertEqual(package['evidence']['E1']['id'], self.match['evidence_id'])
        self.assertEqual(package['event']['score'], {'home': 2, 'away': 1})
        inference.assert_not_called()

    def test_unconfigured_local_job_is_deterministic_and_idempotent(self):
        with patch.dict('os.environ', {}, clear=True), patch('dragonhydra.local_ai.infer') as inference:
            response = self.client.post(self.path+'/local-explanations', json={}, headers={'Idempotency-Key': 'same-local-request'})
            self.assertEqual(response.status_code, 202)
            repeated = self.client.post(self.path+'/local-explanations', json={}, headers={'Idempotency-Key': 'same-local-request'})
            self.assertEqual(response.json()['id'], repeated.json()['id'])
            self.assertTrue(self.jobs.run_once())
            job = self.jobs.get(response.json()['id'])
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(job['result']['kind'], 'deterministic')
        self.assertEqual(job['result']['local_ai']['code'], 'AI_NOT_CONFIGURED')
        self.assertEqual(job['result']['input_manifest'], [self.match['evidence_id']])
        inference.assert_not_called()

    def test_accepted_selection_retains_validated_citation_and_labels_its_limited_scope(self):
        def accepted(package, endpoint, key, **kwargs):
            kwargs['check']()
            result = validate_output(package, json.dumps({'observation': package['allowed_observations'][0], 'evidence_alias': 'E1'}))
            return {**result, 'runtime': {'local_endpoint': True}}
        configured = {'DRAGONHYDRA_LOCAL_AI_URL': 'http://127.0.0.1:12345', 'DRAGONHYDRA_LOCAL_AI_KEY': 'fixture-key-kept-private-1234'}
        with patch.dict('os.environ', configured, clear=True), patch('dragonhydra.local_ai.infer', side_effect=accepted):
            response = self.client.post(self.path+'/local-explanations', json={})
            self.jobs.run_once()
        result = self.jobs.get(response.json()['id'])['result']
        self.assertEqual(result['kind'], 'local_llm')
        self.assertEqual(result['mode'], 'constrained_source_fact_selection')
        self.assertTrue(result['local_ai']['accepted'])
        self.assertEqual(result['evidence'][0]['id'], self.match['evidence_id'])
        self.assertIn('no new analysis', result['unknowns'][0])
        self.assertNotIn(configured['DRAGONHYDRA_LOCAL_AI_KEY'], json.dumps(result))

    def test_rejected_model_output_uses_labelled_fallback(self):
        configured = {'DRAGONHYDRA_LOCAL_AI_URL': 'http://127.0.0.1:12345', 'DRAGONHYDRA_LOCAL_AI_KEY': 'fixture-key-kept-private-1234'}
        with patch.dict('os.environ', configured, clear=True), patch('dragonhydra.local_ai.infer', side_effect=LocalAIError('AI_OUTPUT_REJECTED', 'Unsupported facts.')):
            response = self.client.post(self.path+'/local-explanations', json={})
            self.jobs.run_once()
        result = self.jobs.get(response.json()['id'])['result']
        self.assertEqual(result['kind'], 'deterministic')
        self.assertEqual(result['local_ai']['code'], 'AI_OUTPUT_REJECTED')
        self.assertFalse(result['local_ai']['accepted'])

    def test_queued_package_preserves_old_citation_after_source_correction(self):
        with patch.dict('os.environ', {}, clear=True):
            response = self.client.post(self.path+'/local-explanations', json={})
            self.ingest(3)
            current = self.product.matches()['items'][0]
            self.assertNotEqual(current['evidence_id'], self.match['evidence_id'])
            self.jobs.run_once()
        result = self.jobs.get(response.json()['id'])['result']
        self.assertEqual(result['input_manifest'], [self.match['evidence_id']])
        evidence = self.client.get(result['evidence'][0]['url']).json()
        self.assertEqual(evidence['home_goals'], 2)

    def test_client_cannot_supply_endpoint_key_or_an_arbitrary_package(self):
        response = self.client.post(self.path+'/local-explanations', json={'url': 'https://example.test', 'key': 'private-fixture-key', 'package': {}})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('private-fixture-key', response.text)
        self.assertEqual(self.client.get(API+'/matches/'+'0'*64+'/analysis-package').status_code, 404)

    @staticmethod
    def rehash(package):
        package['allowed_observations'] = observations(package['event'])
        package['package_sha256'] = hashlib.sha256(canonical(
            {key: value for key, value in package.items() if key != 'package_sha256'})).hexdigest()
        return package

    def assert_binding_rejected(self, package):
        configured = {'DRAGONHYDRA_LOCAL_AI_URL': 'http://127.0.0.1:12345',
                      'DRAGONHYDRA_LOCAL_AI_KEY': 'fixture-key-kept-private-1234'}
        with patch.dict('os.environ', configured, clear=True), patch('dragonhydra.local_ai.infer') as inference:
            with self.assertRaises(LocalAIError) as caught:
                explain(self.product, package)
        self.assertEqual(caught.exception.code, 'AI_EVIDENCE_MISMATCH')
        inference.assert_not_called()

    def test_service_rejects_rehashed_event_and_evidence_tampering_before_inference(self):
        original = build_package(self.product, self.match['id'])
        cases = [
            ('event', 'id', 'f'*64), ('event', 'competition', 'Unrelated competition'),
            ('event', 'event_date', '2026-09-01'), ('event', 'status', 'live'),
            ('event', 'home', {'id': 'e'*64, 'name': 'Unrelated participant'}),
            ('event', 'away', {'id': original['event']['away']['id'], 'name': 'Unrelated away participant'}),
            ('event', 'score', {'home': 99, 'away': 1}),
            ('evidence', 'id', '0'*64), ('evidence', 'source_id', 'unrelated-provider'),
            ('evidence', 'source_sha256', 'a'*64),
            ('evidence', 'source_url', 'https://example.test/unrelated-source'),
            ('evidence', 'usable_at', '2026-09-01T12:00:00Z'),
        ]
        for group, field, value in cases:
            changed = deepcopy(original)
            target = changed['event'] if group == 'event' else changed['evidence']['E1']
            target[field] = value
            with self.subTest(group=group, field=field):
                self.assert_binding_rejected(self.rehash(changed))
        changed = deepcopy(original)
        changed['scope'] = 'All scores are guaranteed to be regulation-only settlement evidence.'
        self.assert_binding_rejected(self.rehash(changed))

    def test_service_rejects_another_real_match_from_the_same_acquisition(self):
        raw = json.dumps({'name': 'Two fixture acquisition', 'matches': [
            {'date': '2026-10-02', 'team1': 'Original home', 'team2': 'Original away', 'score': {'ft': [2, 1]}},
            {'date': '2026-10-02', 'team1': 'Other home', 'team2': 'Other away', 'score': {'ft': [0, 3]}},
        ]}).encode()
        with closing(self.product.connect()) as db:
            public_results.ingest_bytes(db, raw, source_id='synthetic-shared-file', source_url='https://example.test/two-fixtures')
        rows = self.product.matches(provider='synthetic-shared-file')['items']
        left, right = [build_package(self.product, row['id']) for row in rows]
        self.assertEqual(left['evidence']['E1']['source_sha256'], right['evidence']['E1']['source_sha256'])
        self.assertNotEqual(left['evidence']['E1']['id'], right['evidence']['E1']['id'])
        left['event'] = right['event']
        self.assert_binding_rejected(self.rehash(left))

    def test_service_rejects_missing_queued_fields_before_inference(self):
        original = build_package(self.product, self.match['id'])
        for path in (('event',), ('event', 'home'), ('event', 'score'),
                     ('evidence', 'E1'), ('evidence', 'E1', 'source_id'), ('scope',)):
            changed = deepcopy(original)
            target = changed
            for field in path[:-1]:
                target = target[field]
            target.pop(path[-1])
            changed['package_sha256'] = hashlib.sha256(canonical(
                {key: value for key, value in changed.items() if key != 'package_sha256'})).hexdigest()
            with self.subTest(missing=path):
                self.assert_binding_rejected(changed)

    def ingest_connector(self, goals):
        from dragonhydra.connectors.core import Document
        raw = json.dumps({'id': 42, 'home': 'Provider home', 'away': 'Provider away', 'goals': goals}).encode()
        digest = hashlib.sha256(raw).hexdigest()
        doc = Document('https://example.test/connector', 'https://example.test/connector', raw, now(),
                       digest, 'application/json', uuid4().hex, digest+'.payload')
        self.product.connector_store.receipt('statsbomb', doc)
        record = {'source_record_id': '42', 'sport': 'football', 'competition': 'Provider league',
                  'season': '2026/27', 'home': 'Provider home', 'away': 'Provider away',
                  'event_date': '2026-10-01', 'kickoff_utc': None, 'source_local_time': '18:00',
                  'status': 'historical_result', 'score_home': goals, 'score_away': 1,
                  'statistics': {}, 'attributes': {'score_scope': 'Provider match score; regulation scope is unknown.'},
                  'odds': [], 'source_document_sha256': digest, 'original': json.loads(raw)}
        return self.product.connector_store.ingest('statsbomb', [record], [doc])

    def test_connector_package_preserves_exact_cited_revision_after_correction(self):
        self.ingest_connector(2)
        match = self.product.matches(provider='statsbomb')['items'][0]
        package = build_package(self.product, match['id'])
        self.ingest_connector(3)
        current = self.product.matches(provider='statsbomb')['items'][0]
        self.assertEqual(current['id'], match['id'])
        self.assertNotEqual(current['evidence_id'], match['evidence_id'])
        with patch.dict('os.environ', {}, clear=True), patch('dragonhydra.local_ai.infer') as inference:
            result = explain(self.product, package)
        self.assertEqual(result['input_manifest'], [match['evidence_id']])
        self.assertEqual(package['event']['score'], {'home': 2, 'away': 1})
        self.assertEqual(self.product.evidence(result['evidence'][0]['id'])['record']['score_home'], 2)
        inference.assert_not_called()

    def test_connector_service_rejects_rehashed_name_score_date_and_provider(self):
        self.ingest_connector(2)
        match = self.product.matches(provider='statsbomb')['items'][0]
        original = build_package(self.product, match['id'])
        for group, field, value in [('event', 'id', 'f'*64),
                ('event', 'score', {'home': 4, 'away': 1}),
                ('event', 'home', {'id': original['event']['home']['id'], 'name': 'Unrelated provider participant'}),
                ('event', 'event_date', '2026-09-30'), ('evidence', 'source_id', 'other-provider')]:
            changed = deepcopy(original)
            target = changed['event'] if group == 'event' else changed['evidence']['E1']
            target[field] = value
            with self.subTest(group=group, field=field):
                self.assert_binding_rejected(self.rehash(changed))


if __name__ == '__main__':
    unittest.main()
