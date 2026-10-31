"""Optional model configuration cannot masquerade as runtime health or break SQLite."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra import public_results
from dragonhydra.local_ai_settings import KEY_ENV, URL_ENV


ROOT = Path(__file__).resolve().parents[1]
API = '/dragon/api/v1'
KEY = 'fixture-health-local-model-key-123456789'


@unittest.skipUnless(importlib.util.find_spec('fastapi'), 'Pinned API environment required')
class LocalAIHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime'/'scratch', prefix='local-ai-health-')
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {KEY_ENV: '', URL_ENV: ''})
        self.environment.start(); self.addCleanup(self.environment.stop)
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.state = Path(self.temp.name)
        self.client = TestClient(create_app(self.state, local_token='fixture-health-token-123456789', start_worker=False))
        self.addCleanup(self.client.close)
        self.client.headers['Authorization'] = 'Bearer fixture-health-token-123456789'

    def health(self, expected, configured):
        ready, system = self.client.get(API+'/health/ready'), self.client.get(API+'/system')
        self.assertEqual((ready.status_code, system.status_code), (200, 200))
        self.assertEqual(ready.json()['backend'], 'sqlite')
        self.assertEqual(ready.json()['status'], 'ready')
        self.assertEqual(ready.json()['optional_ai'], expected)
        self.assertEqual(system.json()['ai'], expected)
        self.assertEqual(system.json()['capabilities']['local_llm'], configured)
        self.assertEqual(system.json()['local_ai']['runtime_health'], 'not_checked')
        self.assertEqual(system.json()['local_ai']['mode'], 'constrained_source_fact_selection')
        self.assertNotIn(KEY, ready.text+system.text)
        return system.json()

    @unittest.skipUnless(os.name == 'nt', 'Persisted Windows identity DPAPI configuration')
    def test_configured_status_is_masked_and_never_decrypts_connects_or_runs_inference(self):
        self.health('not_configured', False)
        response = self.client.put(API+'/local-model/configuration', json={'endpoint': 'http://127.0.0.1:18746', 'credential': KEY})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(KEY, response.text)
        with patch('dragonhydra.connectors.vault.Vault.get', side_effect=AssertionError('health must not decrypt')), \
             patch('dragonhydra.local_ai.infer', side_effect=AssertionError('health must not infer')), \
             patch('socket.create_connection', side_effect=AssertionError('health must not connect')):
            self.health('configured_not_tested', True)

    @unittest.skipUnless(os.name == 'nt', 'Persisted Windows identity DPAPI configuration')
    def test_removing_persisted_configuration_restores_unconfigured_status(self):
        self.assertEqual(self.client.put(API+'/local-model/configuration', json={'endpoint': 'http://127.0.0.1:18746', 'credential': KEY}).status_code, 200)
        self.health('configured_not_tested', True)
        removed = self.client.put(API+'/local-model/configuration', json={'endpoint': '', 'remove_credential': True})
        self.assertEqual(removed.status_code, 200)
        self.assertFalse((self.state/'vault'/'local-ai.dpapi').exists())
        self.health('not_configured', False)

    def test_corrupt_optional_settings_preserve_core_health_and_deterministic_fallback(self):
        (self.state/'local-ai.json').write_text('{broken optional settings', encoding='utf-8')
        system = self.health('misconfigured', False)
        self.assertEqual(system['local_ai']['code'], 'AI_SETTINGS_INVALID')
        product = self.client.app.state.product
        raw = json.dumps({'name': 'Fixture league', 'matches': [{'date': '2026-10-01', 'team1': 'Home',
                           'team2': 'Away', 'score': {'ft': [2, 1]}}]}).encode()
        with closing(product.connect()) as db:
            public_results.ingest_bytes(db, raw, source_id='fixture-health-source', source_url='https://example.test/fixture')
        match = product.matches()['items'][0]
        with patch('dragonhydra.local_ai.infer') as inference:
            requested = self.client.post(API+'/matches/'+match['id']+'/local-explanations', json={})
            self.assertEqual(requested.status_code, 202)
            self.assertTrue(self.client.app.state.jobs.run_once())
            job = self.client.get(API+'/jobs/'+requested.json()['id']).json()
        inference.assert_not_called()
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(job['result']['kind'], 'deterministic')
        self.assertEqual(job['result']['local_ai']['code'], 'AI_SETTINGS_INVALID')
        self.health('misconfigured', False)
