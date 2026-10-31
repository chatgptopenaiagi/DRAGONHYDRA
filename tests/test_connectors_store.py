"""Provider storage/worker/API contracts, with isolated data and deterministic HTTP fixtures."""
from contextlib import closing
from email.message import Message
import hashlib
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from dragonhydra.connectors.core import ConnectorError, Document, SafeRedirect, redact_url, utc_now, validate_url
from dragonhydra.connectors.store import Store, digest
from dragonhydra.product import Product

ROOT = Path(__file__).resolve().parents[1]


class ConnectorFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime'/'scratch', prefix='provider-contract-')
        self.addCleanup(self.temp.cleanup)
        self.product = Product(Path(self.temp.name))
        self.store = self.product.connector_store
        self.doc = self.document(b'{"original":"retained response"}')

    def document(self, raw, provider='statsbomb'):
        sha = hashlib.sha256(raw).hexdigest()
        doc = Document('https://github.com/statsbomb/open-data', 'https://github.com/hudl/open-data', raw,
                       utc_now(), sha, 'application/json', uuid4().hex, sha+'.payload')
        self.store.receipt(provider, doc)
        return doc

    def record(self, **values):
        return {'source_record_id': '42', 'sport': 'football', 'competition': 'Test cup', 'season': '2022',
                'home': 'Équipe A', 'away': 'Team B', 'event_date': '2022-11-20', 'kickoff_utc': None,
                'source_local_time': '18:00', 'status': 'historical_result', 'score_home': 2, 'score_away': 1,
                'statistics': {}, 'attributes': {}, 'odds': [], 'original': {'id': 42},
                'source_document_sha256': self.doc.sha256, **values}


class ConnectorStoreTests(ConnectorFixture, unittest.TestCase):
    def test_ingest_provenance_and_existing_match_team_standings_flow(self):
        result = self.store.ingest('statsbomb', [self.record()], [self.doc])
        self.assertEqual(result['record_count'], 1)
        match = self.product.matches(provider='statsbomb')['items'][0]
        self.assertEqual(match['home']['name'], 'Équipe A')
        self.assertEqual(match['record_kind'], 'historical_result')
        self.assertEqual(self.product.team(match['home']['id'])['form'][0]['result'], 'W')
        self.assertEqual(self.product.standings(match['competition_id'])['items'][0]['points'], 3)
        evidence = self.product.evidence(match['evidence_id'])
        self.assertEqual(evidence['raw_sha256'], self.doc.sha256)
        self.assertEqual(evidence['adapter_version'], 'statsbomb/1')
        self.assertEqual(evidence['source_record_id'], '42')
        self.assertEqual(evidence['resolved_url'], 'https://github.com/hudl/open-data')

    def test_duplicate_import_and_reopen_retain_one_record(self):
        self.store.ingest('statsbomb', [self.record()], [self.doc])
        second = self.store.ingest('statsbomb', [self.record()], [self.doc])
        self.assertEqual((second['inserted'], second['unchanged']), (0, 1))
        reopened = Product(Path(self.temp.name))
        self.assertEqual(reopened.connector_store.count('statsbomb'), 1)

    def test_new_capture_clock_does_not_create_a_semantic_revision(self):
        self.store.ingest('statsbomb', [self.record(attributes={'captured_at': '2026-10-31T10:00:00Z'})], [self.doc])
        result = self.store.ingest('statsbomb', [self.record(attributes={'captured_at': '2026-10-31T11:00:00Z'})], [self.doc])
        self.assertEqual((result['inserted'], result['unchanged']), (0, 1))

    def test_legacy_capture_inclusive_hash_is_unchanged_without_rewriting_evidence(self):
        catalog = self.document(b'{"competition_catalog":"legacy StatsBomb fixture"}')
        attributes = {'captured_at': '2026-10-31T10:00:00Z', 'retrieved_at': '2026-10-31T10:00:01Z',
                      'catalog_sha256': catalog.sha256, 'retained_business_attribute': 'unchanged'}
        original = self.record(attributes=attributes)
        self.store.ingest('statsbomb', [original], [self.doc, catalog])
        evidence_id = self.store.rows('statsbomb')[0]['id']
        # Older real StatsBomb/NFL imports used the full record digest, including
        # acquisition clocks. Preserve that exact legacy row/hash/ID; importing
        # its current semantic equivalent must not silently add a new binding.
        with closing(self.product.connect()) as db:
            db.execute('UPDATE connector_observations SET content_hash=?,record=? WHERE id=?',
                       (digest(original), json.dumps(original), evidence_id))
            db.commit()
            before = db.execute('SELECT * FROM connector_observations WHERE id=?', (evidence_id,)).fetchone()
        for record in (original, self.record(attributes={**attributes, 'captured_at': '2026-10-31T11:00:00Z',
                                                        'retrieved_at': '2026-10-31T11:00:01Z'})):
            result = self.store.ingest('statsbomb', [record], [self.doc, catalog])
            self.assertEqual((result['inserted'], result['unchanged']), (0, 1))
            self.assertEqual(self.store.rows('statsbomb')[0]['id'], evidence_id)
            with closing(self.product.connect()) as db:
                self.assertEqual(db.execute('SELECT * FROM connector_observations WHERE id=?', (evidence_id,)).fetchone(), before)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0], 1)
        # Only the last revision is compared. A genuine A -> B -> A correction
        # still creates two further observations, even though A exists in history.
        for score in (3, 2):
            result = self.store.ingest('statsbomb', [self.record(score_home=score, attributes=attributes)], [self.doc, catalog])
            self.assertEqual(result['inserted'], 1)
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT * FROM connector_observations WHERE id=?', (evidence_id,)).fetchone(), before)

    def test_corrections_preserve_old_evidence(self):
        self.store.ingest('statsbomb', [self.record()], [self.doc])
        old = self.store.rows()[0]['id']
        changed = self.record(score_home=3)
        result = self.store.ingest('statsbomb', [changed], [self.doc])
        self.assertEqual(result['inserted'], 1)
        self.assertEqual(result['record_count'], 1)
        self.assertEqual(self.store.evidence(old)['record']['score_home'], 2)
        self.assertEqual(self.store.rows()[0]['record']['score_home'], 3)

    def test_correction_can_revert_to_previous_content_without_losing_revision(self):
        for score in (2, 3, 2):
            result = self.store.ingest('statsbomb', [self.record(score_home=score)], [self.doc])
            self.assertEqual(result['inserted'], 1)
        self.assertEqual(self.store.rows()[0]['record']['score_home'], 2)
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0], 3)

    def test_conflicting_native_id_quarantines_both_without_overwriting_committed(self):
        self.store.ingest('statsbomb', [self.record()], [self.doc])
        result = self.store.ingest('statsbomb', [self.record(score_home=3), self.record(score_home=4)], [self.doc])
        self.assertEqual((result['inserted'], result['quarantined']), (0, 2))
        self.assertEqual(self.store.rows()[0]['record']['score_home'], 2)

    def test_missing_provenance_invalid_scores_and_market_identity_quarantined(self):
        for record in (self.record(source_document_sha256='missing'), self.record(score_home=-1),
                       self.record(odds=[{'decimal_odds': 1.8}])):
            self.assertEqual(self.store.ingest('statsbomb', [record], [self.doc])['quarantined'], 1)
        self.assertEqual(self.store.count('statsbomb'), 0)

    def test_multisport_does_not_enter_football_views(self):
        doc = self.document(b'cricket payload', 'cricsheet')
        self.store.ingest('cricsheet', [self.record(sport='cricket', score_home=None, score_away=None,
            source_document_sha256=doc.sha256)], [doc])
        self.assertEqual(self.product.matches()['total'], 0)
        self.assertEqual(self.store.page('cricsheet')['total'], 1)

    def test_cross_provider_candidate_is_reviewed_without_merging(self):
        self.store.ingest('statsbomb', [self.record()], [self.doc])
        other = self.document(b'other source payload', 'football-data-couk')
        self.store.ingest('football-data-couk', [self.record(source_document_sha256=other.sha256)], [other])
        self.assertEqual(self.product.matches()['total'], 2)
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM connector_identity_review').fetchone()[0], 1)

    def test_tournament_stages_are_not_recomputed_as_a_single_league(self):
        self.store.ingest('statsbomb', [self.record(attributes={'competition_stage': {'name': 'Final'}})], [self.doc])
        match = self.product.matches()['items'][0]
        standings = self.product.standings(match['competition_id'])
        self.assertFalse(standings['available'])
        self.assertEqual(standings['items'], [])
        self.assertEqual(standings['stages'], ['Final'])

    def test_v1_store_migration_retains_evidence_and_allows_reversion(self):
        self.store.ingest('statsbomb', [self.record()], [self.doc])
        old_id = self.store.rows()[0]['id']
        with closing(self.product.connect()) as db:
            definition = db.execute("SELECT sql FROM sqlite_master WHERE name='connector_observations'").fetchone()[0]
            legacy = definition.replace('connector_observations', 'connector_observations_legacy', 1)
            legacy = legacy.rstrip()[:-1]+', UNIQUE(provider,source_record_id,content_hash))'
            db.execute(legacy)
            db.execute('INSERT INTO connector_observations_legacy SELECT * FROM connector_observations')
            db.execute('DROP TABLE connector_observations')
            db.execute('ALTER TABLE connector_observations_legacy RENAME TO connector_observations')
            db.commit()
        reopened = Product(self.product.state)
        self.assertEqual(reopened.connector_store.evidence(old_id)['record']['score_home'], 2)
        for score in (3, 2):
            self.assertEqual(reopened.connector_store.ingest('statsbomb', [self.record(score_home=score)], [self.doc])['inserted'], 1)

    def test_live_and_historical_are_separately_filterable(self):
        self.store.ingest('statsbomb', [self.record(), self.record(source_record_id='43', status='live', score_home=0, score_away=0)], [self.doc])
        self.assertEqual(self.store.page('statsbomb', status='historical_result')['total'], 1)
        self.assertEqual(self.product.matches(status='live')['total'], 1)
        self.assertEqual(self.product.matches(status='finished')['total'], 1)

    def test_archive_odds_keep_phase_and_no_fabricated_quote_time(self):
        quote = {'provider': 'Example bookmaker', 'feed': 'archive', 'market': '1x2', 'period': 'full_time',
                 'selection': 'home', 'settlement_rules': 'regulation_only', 'decimal_odds': 2.1,
                 'archive_phase': 'opening', 'quote_at': None}
        self.store.ingest('statsbomb', [self.record(odds=[quote])], [self.doc])
        match = self.product.matches()['items'][0]
        result = self.product.odds(match['id'], history=True)
        self.assertEqual(result['axis'], 'archive_phase')
        self.assertIsNone(result['items'][0]['quote_at'])
        self.assertEqual(result['items'][0]['match_id'], match['id'])

    def test_transport_secret_redaction_and_private_endpoint_rejection(self):
        secret = 'PRIVATE_TEST_KEY'
        self.assertNotIn(secret, redact_url('https://api.the-odds-api.com/v4/sports?apiKey='+secret))
        for url in ('http://127.0.0.1/', 'https://localhost/', 'https://api.football-data.org:999/v4/', 'https://user:secret@github.com/'):
            with self.assertRaises(ConnectorError):
                validate_url(url)

    @unittest.skipUnless(os.name == 'nt', 'Windows service-identity DPAPI workload')
    def test_vault_encrypts_and_round_trips_without_plaintext(self):
        from dragonhydra.connectors.vault import Vault
        vault = Vault(self.product.state)
        value = 'fixture-only-secret-12345'
        vault.put('api-football', value)
        self.assertTrue(vault.configured('api-football'))
        self.assertNotIn(value.encode(), vault.path('api-football').read_bytes())
        self.assertEqual(vault.get('api-football'), value)
        vault.delete('api-football')
        self.assertFalse(vault.configured('api-football'))

    def test_persisted_attempt_error_has_specific_code(self):
        from dragonhydra.connectors.service import Connections
        connections = Connections(self.product)
        with patch('dragonhydra.connectors.service.adapter', return_value=SimpleNamespace(fetch=lambda *a: (_ for _ in ()).throw(ConnectorError('NEEDS_KEY', 'Save a provider key.')))):
            with self.assertRaises(ConnectorError):
                connections.run('api-football', 'test')
        result = connections.describe('api-football')
        self.assertEqual(result['status'], 'needs_key')
        self.assertEqual(result['last_diagnostic']['error']['code'], 'NEEDS_KEY')
        self.assertIsNone(result['last_successful_retrieval'])

    def test_quota_cooldown_is_shared_by_manual_jobs_and_survives_restart(self):
        from dragonhydra.connectors.service import Connections
        connections = Connections(self.product)
        ident = self.store.start('statsbomb', 'sync')
        self.store.finish(ident, error={'code': 'RATE_LIMITED', 'retry_after': 120, 'cooldown_until': time.time()+120})
        with patch('dragonhydra.connectors.service.adapter') as fetch_adapter:
            with self.assertRaises(ConnectorError) as cm:
                Connections(Product(self.product.state)).run('statsbomb', 'sync')
        self.assertEqual(cm.exception.code, 'RATE_LIMITED')
        fetch_adapter.assert_not_called()

    def test_periodic_settings_persist_and_do_not_queue_duplicate_active_job(self):
        from dragonhydra.jobs import Jobs
        jobs = Jobs(self.product)
        jobs.providers.configure('statsbomb', {}, 3600)
        with closing(self.product.connect()) as db:
            db.execute('UPDATE connector_settings SET next_due=1')
            db.commit()
        jobs.providers.schedule_due(jobs)
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM product_jobs WHERE kind='connector_sync'").fetchone()[0], 1)
            db.execute('UPDATE connector_settings SET next_due=1')
            db.commit()
        jobs.providers.schedule_due(jobs)
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM product_jobs WHERE kind='connector_sync'").fetchone()[0], 1)
        self.assertEqual(Store(Product(self.product.state)).settings('statsbomb')['interval_seconds'], 3600)


class ProviderResponse(BytesIO):
    """HTTP framing fixture used by the actual retaining Transport and worker."""
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = Message()
        self.headers['Content-Type'] = 'text/csv' if status == 200 else 'application/json'
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def getcode(self):
        return self.status

    def geturl(self):
        return 'https://www.football-data.co.uk/mmz4281/2526/E0.csv'


class ConnectorWorkerTransportTests(ConnectorFixture, unittest.TestCase):
    def retry_now(self, job_id):
        # Only advance this isolated fixture's eligibility; exercise persisted
        # backoff first, without waiting for a real provider cooldown.
        with closing(self.product.connect()) as db:
            db.execute('UPDATE product_jobs SET next_attempt=0 WHERE id=?', (job_id,))
            db.commit()

    def verify_recovered_import(self, first_response, minimum_delay, failed_acquisitions):
        from dragonhydra.jobs import Jobs
        raw = (ROOT/'tests'/'fixtures'/'connectors'/'football'/'archive.csv').read_bytes()
        opener = SimpleNamespace(open=Mock(side_effect=[first_response, ProviderResponse(raw)]))
        jobs = Jobs(self.product)
        job_id = jobs.submit('connector_sync', {'provider': 'football-data-couk'}, 'fixture-owner')['id']
        with patch('dragonhydra.connectors.core.build_opener', return_value=opener):
            before = time.time()
            self.assertTrue(jobs.run_once())
            pending = jobs.get(job_id)
            self.assertEqual((pending['status'], pending['attempts']), ('queued', 1))
            self.assertEqual(pending['error']['code'], 'NETWORK_UNAVAILABLE')
            self.assertGreaterEqual(pending['next_attempt'], before+minimum_delay)
            self.assertEqual(self.store.count('football-data-couk'), 0)
            with closing(self.product.connect()) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM connector_acquisitions WHERE provider='football-data-couk'").fetchone()[0], failed_acquisitions)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0], 0)
            # Recreate the coordinator to prove the cooldown survives restart.
            recovered = Jobs(Product(self.product.state))
            self.assertEqual(recovered.get(job_id)['next_attempt'], pending['next_attempt'])
            self.assertFalse(recovered.run_once())
            self.assertEqual(opener.open.call_count, 1)
            self.retry_now(job_id)
            self.assertTrue(recovered.run_once())
            completed = recovered.get(job_id)
            self.assertEqual((completed['status'], completed['attempts']), ('succeeded', 2))
            self.assertIsNone(completed['error'])
            self.assertEqual((completed['result']['inserted'], completed['result']['record_count']), (2, 2))
            self.assertFalse(recovered.run_once())
            self.assertEqual(opener.open.call_count, 2)
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM product_updates WHERE topic='data'").fetchone()[0], 1)
        self.assertEqual([row['status'] for row in self.store.attempts('football-data-couk')], ['succeeded', 'failed'])

    def test_worker_persists_http503_backoff_then_imports_once_after_restart(self):
        response = ProviderResponse(b'{"error":"temporary"}', 503, {'Retry-After': '120'})
        self.verify_recovered_import(response, minimum_delay=120, failed_acquisitions=1)

    def test_worker_persists_interrupted_transfer_backoff_then_imports_once(self):
        response = ProviderResponse(b'')
        response.read = Mock(side_effect=[b'Div,Date,HomeTeam,', ConnectionResetError('fixture reset')])
        self.verify_recovered_import(response, minimum_delay=60, failed_acquisitions=0)
        self.assertTrue(response.closed)

    def test_worker_stops_after_three_transient_http_attempts(self):
        from dragonhydra.jobs import Jobs
        opener = SimpleNamespace(open=Mock(side_effect=lambda *a, **k:
            ProviderResponse(b'{"error":"temporary"}', 503, {'Retry-After': '120'})))
        jobs = Jobs(self.product)
        job_id = jobs.submit('connector_sync', {'provider': 'football-data-couk'}, 'fixture-owner')['id']
        with patch('dragonhydra.connectors.core.build_opener', return_value=opener):
            for attempt in range(1, 4):
                self.assertTrue(jobs.run_once())
                result = jobs.get(job_id)
                self.assertEqual(result['attempts'], attempt)
                self.assertEqual(result['status'], 'queued' if attempt < 3 else 'failed')
                self.assertEqual((result['error']['code'], result['error']['http_status']), ('NETWORK_UNAVAILABLE', 503))
                if attempt < 3:
                    self.assertGreater(result['next_attempt'], time.time())
                    self.assertFalse(jobs.run_once())
                    self.retry_now(job_id)
            self.assertFalse(jobs.run_once())
            self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(self.store.count('football-data-couk'), 0)
        self.assertEqual(len(self.store.attempts('football-data-couk')), 3)
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM connector_acquisitions WHERE provider='football-data-couk'").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM product_updates WHERE topic='data'").fetchone()[0], 0)


@unittest.skipUnless(importlib.util.find_spec('fastapi'), 'Pinned API environment required')
class ConnectorAPITests(ConnectorFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.client = TestClient(create_app(self.product.state, local_token='fixture-connector-token-12345678', start_worker=False))
        self.addCleanup(self.client.close)
        self.client.headers['Authorization'] = 'Bearer fixture-connector-token-12345678'

    def test_api_diagnostic_is_a_job_and_get_does_not_import(self):
        response = self.client.post('/dragon/api/v1/connections/statsbomb/test', json={})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['kind'], 'connector_test')
        self.client.get('/dragon/api/v1/connections')
        self.assertEqual(self.store.count('statsbomb'), 0)
        self.client.headers.clear()
        self.assertEqual(self.client.put('/dragon/api/v1/connections/statsbomb/configuration', json={}).status_code, 401)

    def test_api_rejects_custom_url_and_preserves_credentials_in_validation_errors(self):
        response = self.client.put('/dragon/api/v1/connections/statsbomb/configuration', json={'config': {'url': 'http://localhost/'}})
        self.assertGreaterEqual(response.status_code, 400)
        response = self.client.put('/dragon/api/v1/connections/api-football/configuration', json={'credential': 'sensitive-fixture-value', 'invalid': 1})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('sensitive-fixture-value', response.text)

    def test_api_records_retain_native_identity_and_evidence(self):
        self.store.ingest('statsbomb', [self.record()], [self.doc])
        response = self.client.get('/dragon/api/v1/connections/statsbomb/records?limit=1')
        self.assertEqual(response.status_code, 200)
        item = response.json()['items'][0]
        self.assertEqual(item['source_record_id'], '42')
        self.assertEqual(self.client.get(item['evidence_url']).status_code, 200)


if __name__ == '__main__':
    unittest.main()
