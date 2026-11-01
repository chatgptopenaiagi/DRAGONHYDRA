"""Private service-owned model setup, precedence, permissions and safe fallback."""
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

from dragonhydra import public_results
from dragonhydra.connectors.core import ConnectorError
from dragonhydra.local_ai import LocalAIError
from dragonhydra.local_ai_settings import KEY_ENV, URL_ENV, Settings

ROOT = Path(__file__).resolve().parents[1]
API = '/dragon/api/v1'
KEY = 'fixture-local-model-key-1234567890'
OTHER_KEY = 'fixture-replacement-key-1234567890'


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime/scratch', prefix='local-model-settings-')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.settings = Settings(self.state)
        self.environment = patch.dict(os.environ, {URL_ENV: '', KEY_ENV: ''})
        self.environment.start(); self.addCleanup(self.environment.stop)

    def test_unconfigured_reads_create_nothing_and_never_start_inference(self):
        with patch('dragonhydra.local_ai.infer') as inference:
            self.assertEqual(self.settings.public(), {'endpoint': '', 'configured': False,
                'endpoint_source': 'none', 'credential_source': 'none'})
            self.assertEqual(self.settings.effective(), ('', None))
        inference.assert_not_called()
        self.assertEqual(list(self.state.iterdir()), [])

    def test_endpoint_validation_rejects_remote_and_malformed_routes_before_storage(self):
        for selected in ('https://127.0.0.1:18746', 'http://localhost:18746', 'http://192.0.2.1:18746',
                         'http://127.0.0.1:18746/completion', 'http://127.0.0.1:18746?key=secret',
                         'http://127.0.0.1:18746/#secret', 'http://user:secret@127.0.0.1:18746',
                         'http://127.0.0.1:0', 'http://127.0.0.1:65536', ' http://127.0.0.1:18746',
                         'http://127.0.0.1:18746\n'):
            with self.subTest(endpoint=selected):
                with self.assertRaises(LocalAIError) as error:
                    self.settings.configure(selected, KEY)
                self.assertEqual(error.exception.code, 'AI_ENDPOINT_INVALID')
                self.assertNotIn(selected, str(error.exception))
                self.assertNotIn(KEY, str(error.exception))
                self.assertEqual(list(self.state.iterdir()), [])

    def test_non_ascii_or_control_keys_are_rejected_before_storage(self):
        for selected in ('short', 'a'*20+'\n', 'a'*20+' ', 'a'*20+'\x7f', 'a'*20+'é', 'a'*4097):
            with self.subTest(length=len(selected)):
                with self.assertRaises(LocalAIError) as error:
                    self.settings.configure('http://127.0.0.1:18746', selected)
                self.assertEqual(error.exception.code, 'AI_KEY_INVALID')
                self.assertNotIn(selected, str(error.exception))
                self.assertEqual(list(self.state.iterdir()), [])

    def test_endpoint_only_save_is_private_canonical_and_can_be_cleared(self):
        current = self.settings.configure('http://127.0.0.1:01874/')
        self.assertEqual(current['endpoint'], 'http://127.0.0.1:1874')
        self.assertFalse(current['configured'])
        self.assertEqual(json.loads(self.settings.path.read_text()), {'version': 1, 'endpoint': 'http://127.0.0.1:1874'})
        self.assertEqual(self.settings.configure('')['endpoint_source'], 'none')
        self.assertEqual(list(self.state.glob('*.tmp')), [])

    @unittest.skipUnless(os.name == 'nt', 'Real current-Windows-identity DPAPI proof')
    def test_dpapi_roundtrip_keeps_key_out_of_endpoint_file_and_public_reads(self):
        with patch('dragonhydra.local_ai.infer') as inference:
            saved = self.settings.configure('http://127.0.0.1:18746', KEY)
            restarted = Settings(self.state)
            self.assertEqual(restarted.effective(), ('http://127.0.0.1:18746', KEY))
        inference.assert_not_called()
        self.assertTrue(saved['configured'])
        self.assertEqual(saved['credential_source'], 'vault')
        self.assertNotIn(KEY, json.dumps(saved))
        self.assertNotIn(KEY.encode(), self.settings.path.read_bytes())
        self.assertNotIn(KEY.encode(), self.settings.vault.path('local-ai').read_bytes())
        self.assertEqual(set(saved), {'endpoint', 'configured', 'endpoint_source', 'credential_source'})

    @unittest.skipUnless(os.name == 'nt', 'Real current-Windows-identity DPAPI proof')
    def test_environment_precedence_and_removing_only_the_stored_key(self):
        self.settings.configure('http://127.0.0.1:18746', KEY)
        with patch.dict(os.environ, {URL_ENV: 'http://127.0.0.1:18747/', KEY_ENV: OTHER_KEY}):
            current = self.settings.public()
            self.assertEqual(current['endpoint'], 'http://127.0.0.1:18747')
            self.assertEqual(current['credential_source'], current['endpoint_source'])
            self.assertEqual(current['credential_source'], 'environment')
            self.assertEqual(self.settings.effective(), ('http://127.0.0.1:18747', OTHER_KEY))
            current = self.settings.configure('http://127.0.0.1:18748', remove_credential=True)
            self.assertFalse(self.settings.vault.path('local-ai').exists())
            self.assertTrue(current['configured'])
            self.assertEqual(os.environ[KEY_ENV], OTHER_KEY)
            self.assertEqual(current['credential_source'], 'environment')
        self.assertEqual(self.settings.effective(), ('http://127.0.0.1:18748', None))
        self.assertFalse(self.settings.public()['configured'])

    @unittest.skipUnless(os.name == 'nt', 'Real current-Windows-identity DPAPI proof')
    def test_failed_atomic_endpoint_commit_restores_previous_encrypted_key(self):
        self.settings.configure('http://127.0.0.1:18746', KEY)
        old_endpoint, old_ciphertext = self.settings.path.read_bytes(), self.settings.vault.path('local-ai').read_bytes()
        original = os.replace
        def fail_endpoint(source, destination):
            if Path(destination) == self.settings.path:
                raise OSError('fixture commit failure')
            return original(source, destination)
        with patch('dragonhydra.local_ai_settings.os.replace', side_effect=fail_endpoint):
            with self.assertRaises(LocalAIError) as error:
                self.settings.configure('http://127.0.0.1:18747', OTHER_KEY)
        self.assertEqual(error.exception.code, 'AI_SETTINGS_WRITE_FAILED')
        self.assertEqual(self.settings.path.read_bytes(), old_endpoint)
        self.assertEqual(self.settings.vault.path('local-ai').read_bytes(), old_ciphertext)
        self.assertEqual(self.settings.effective(), ('http://127.0.0.1:18746', KEY))
        self.assertEqual(list(self.state.rglob('*.tmp')), [])


@unittest.skipUnless(importlib.util.find_spec('fastapi'), 'Pinned API environment required')
class SettingsAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime/scratch', prefix='local-model-api-')
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(Path(self.temp.name), local_token='fixture-local-settings-admin-token', start_worker=False)
        self.client = TestClient(self.app); self.addCleanup(self.client.close)
        self.client.headers['Authorization'] = 'Bearer fixture-local-settings-admin-token'
        self.environment = patch.dict(os.environ, {URL_ENV: '', KEY_ENV: ''})
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.product, self.jobs = self.app.state.product, self.app.state.jobs
        self.path = API+'/local-model/configuration'

    def test_authentication_and_administrator_role_are_required_for_reads_and_writes(self):
        self.client.headers.clear()
        self.assertEqual(self.client.get(self.path).status_code, 401)
        response = self.client.put(self.path, json={'endpoint': 'http://127.0.0.1:18746', 'credential': KEY})
        self.assertEqual(response.status_code, 401); self.assertNotIn(KEY, response.text)
        cookie = 'fixture-reader-cookie-kept-local'
        with closing(self.product.connect()) as db:
            db.execute('INSERT INTO product_sessions VALUES(?,?,?,?)', (hashlib.sha256(cookie.encode()).hexdigest(), 'fixture:reader', '["reader"]', time.time()+60))
            db.commit()
        self.client.cookies.set(self.app.state.session_cookie_name, cookie)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.assertEqual(self.client.put(self.path, json={'endpoint': ''}).status_code, 403)
        self.assertFalse((self.product.state/'local-ai.json').exists())

    def test_validation_errors_never_reflect_passwords_or_embedded_url_credentials(self):
        for body in ({'endpoint': 'http://user:'+KEY+'@127.0.0.1:18746', 'credential': KEY},
                     {'endpoint': 'http://127.0.0.1:18746', 'credential': KEY+'\n'},
                     {'endpoint': 'http://127.0.0.1:18746', 'credential': KEY, 'extra': KEY}):
            response = self.client.put(self.path, json=body)
            self.assertGreaterEqual(response.status_code, 400)
            self.assertNotIn(KEY, response.text)
        self.assertFalse((self.product.state/'local-ai.json').exists())
        self.assertFalse((self.product.state/'vault/local-ai.dpapi').exists())

    @unittest.skipUnless(os.name == 'nt', 'Real current-Windows-identity DPAPI proof')
    def test_api_never_returns_key_and_leaves_database_schema_unchanged(self):
        with closing(self.product.connect()) as db:
            before = db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        response = self.client.put(self.path, json={'endpoint': 'http://127.0.0.1:18746', 'credential': KEY})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['credential_source'], 'vault')
        self.assertNotIn(KEY, response.text)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(KEY, response.text)
        with closing(self.product.connect()) as db:
            self.assertEqual(before, db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall())
        response = self.client.put(self.path, json={'endpoint': '', 'remove_credential': True})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['configured'])

    def seed_package(self):
        raw = json.dumps({'name': 'Fixture League 2026/27', 'matches': [
            {'date': '2026-10-01', 'team1': 'First', 'team2': 'Second', 'score': {'ft': [2, 1]}}
        ]}).encode()
        with closing(self.product.connect()) as db:
            public_results.ingest_bytes(db, raw, source_id='synthetic-settings-fixture', source_url='https://example.test/fixture')
        return self.product.matches()['items'][0]

    @unittest.skipUnless(os.name == 'nt', 'Real current-Windows-identity DPAPI proof')
    def test_saved_configuration_uses_real_unavailable_loopback_runtime_fallback(self):
        match = self.seed_package()
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))  # Owned bound port deliberately does not listen.
            selected = 'http://127.0.0.1:'+str(reserved.getsockname()[1])
            self.assertEqual(self.client.put(self.path, json={'endpoint': selected, 'credential': KEY}).status_code, 200)
            created = self.client.post(API+'/matches/'+match['id']+'/local-explanations', json={})
            self.assertEqual(created.status_code, 202)
            self.assertTrue(self.jobs.run_once())
        job = self.jobs.get(created.json()['id'])
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(job['result']['kind'], 'deterministic')
        self.assertEqual(job['result']['local_ai']['code'], 'AI_UNAVAILABLE')
        self.assertNotIn(KEY, json.dumps(job))

    @unittest.skipUnless(os.name == 'nt', 'Real current-Windows-identity DPAPI proof')
    def test_service_identity_mismatch_is_a_labelled_deterministic_fallback(self):
        match = self.seed_package()
        Settings(self.product.state).configure('http://127.0.0.1:18746', KEY)
        with patch('dragonhydra.connectors.vault.protect_bytes', side_effect=ConnectorError('VAULT_IDENTITY_MISMATCH', 'Save the key again for this Windows account.')):
            created = self.client.post(API+'/matches/'+match['id']+'/local-explanations', json={})
            self.assertTrue(self.jobs.run_once())
        job = self.jobs.get(created.json()['id'])
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(job['result']['kind'], 'deterministic')
        self.assertEqual(job['result']['local_ai']['code'], 'VAULT_IDENTITY_MISMATCH')
        self.assertNotIn(KEY, json.dumps(job))


if __name__ == '__main__':
    unittest.main()
