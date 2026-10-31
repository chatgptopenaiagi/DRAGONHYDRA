"""Exact acquisition bindings for normalized multi-document provider records."""
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from dragonhydra.connectors.core import ConnectorError, Document
from dragonhydra.connectors.service import Connections
from dragonhydra.connectors.store import PROVENANCE_FIELD
from dragonhydra.product import Product


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = 'api-football'
FIRST = '2026-10-31T10:00:00Z'
SECOND = '2026-10-31T10:01:00Z'


class ProvenanceFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime'/'scratch', prefix='acquisition-binding-')
        self.addCleanup(self.temp.cleanup)
        self.product = Product(Path(self.temp.name))
        self.store = self.product.connector_store
        self.fixture = self.document(b'{"fixture":42}', captured_at=FIRST, path='fixtures')
        self.odds = self.document(b'{"odds":2.1}', captured_at=SECOND, path='odds')

    def document(self, raw, *, provider=PROVIDER, captured_at=FIRST, path='fixtures'):
        digest = hashlib.sha256(raw).hexdigest()
        url = 'https://v3.football.api-sports.io/'+path
        doc = Document(url, url, raw, captured_at, digest, 'application/json', uuid4().hex, digest+'.payload')
        self.store.receipt(provider, doc)
        return doc

    def record(self, **overrides):
        return {'source_record_id': '42', 'sport': 'football', 'competition': '39', 'season': '2026',
                'home': 'Home', 'away': 'Away', 'event_date': '2026-10-30', 'kickoff_utc': None,
                'source_local_time': None, 'status': 'historical_result', 'score_home': 2, 'score_away': 1,
                'statistics': {}, 'attributes': {}, 'original': {'fixture': 42},
                'source_document_sha256': self.fixture.sha256,
                'odds': [{'provider': 'fixture-bookmaker', 'feed': 'api-football-prematch', 'market': '1x2',
                          'period': 'regulation', 'selection': 'home', 'settlement_rules': 'regulation_only',
                          'decimal_odds': 2.1, 'quote_at': None, 'source_document_sha256': self.odds.sha256}],
                **overrides}

    def ingest(self, record=None, documents=None):
        return self.store.ingest(PROVIDER, [record or self.record()], documents or [self.fixture, self.odds])

    def match(self):
        return self.product.matches(provider=PROVIDER)['items'][0]

    def legacy_without_bindings(self):
        row = self.store.rows(PROVIDER)[0]
        record = row['record']
        record.pop(PROVENANCE_FIELD, None)
        with closing(self.product.connect()) as db:
            db.execute('UPDATE connector_observations SET record=? WHERE id=?', (json.dumps(record), row['id']))
            db.commit()

    def quarantine_reason(self):
        with closing(self.product.connect()) as db:
            return db.execute('SELECT reason FROM connector_quarantine ORDER BY created_at DESC LIMIT 1').fetchone()[0]


class AcquisitionBindingTests(ProvenanceFixture, unittest.TestCase):
    def test_quote_uses_its_own_payload_clock_hash_url_and_acquisition(self):
        self.assertEqual(self.ingest()['inserted'], 1)
        match = self.match()
        quote = self.product.odds(match['id'])['items'][0]
        self.assertEqual(quote['captured_at'], SECOND)
        self.assertEqual(quote['source_document_sha256'], self.odds.sha256)
        self.assertEqual(quote['acquisition_id'], self.odds.acquisition_id)
        self.assertEqual(quote['source_url'], self.odds.url)
        self.assertEqual(quote['observation_received_at'], FIRST)
        self.assertEqual(quote['observation_evidence_id'], match['evidence_id'])
        self.assertEqual(quote['evidence_id'], match['evidence_id'])
        self.assertEqual(quote['provenance_status'], 'bound')
        evidence = self.product.evidence(match['evidence_id'])
        self.assertEqual({doc['id'] for doc in evidence['source_documents']},
                         {self.fixture.acquisition_id, self.odds.acquisition_id})

    def test_orphan_quote_catalog_and_score_dependencies_are_quarantined(self):
        for number, kind in enumerate(('quote', 'catalog', 'scores')):
            with self.subTest(kind=kind):
                record = self.record(source_record_id=str(number))
                if kind == 'quote':
                    record['odds'][0]['source_document_sha256'] = 'f'*64
                elif kind == 'catalog':
                    record['attributes']['catalog_sha256'] = 'f'*64
                else:
                    record['attributes']['related_source_sha256'] = ['f'*64]
                result = self.ingest(record)
                self.assertEqual((result['inserted'], result['quarantined']), (0, 1))
                self.assertEqual(self.quarantine_reason(), 'MISSING_ACQUISITION')
        self.assertEqual(self.store.count(PROVIDER), 0)

    def test_catalog_and_score_dependencies_keep_their_exact_receipts(self):
        catalog = self.document(b'{"catalog":43}', path='catalog')
        scores = self.document(b'{"scores":[2,1]}', path='scores')
        record = self.record(attributes={'catalog_sha256': catalog.sha256, 'related_source_sha256': [scores.sha256]})
        self.ingest(record, [self.fixture, self.odds, catalog, scores])
        evidence = self.product.evidence(self.match()['evidence_id'])
        sources = {doc['sha256']: doc for doc in evidence['source_documents']}
        self.assertEqual(sources[catalog.sha256]['references'], ['attributes/catalog_sha256'])
        self.assertEqual(sources[scores.sha256]['references'], ['attributes/related_source_sha256/0'])
        self.assertEqual(sources[catalog.sha256]['id'], catalog.acquisition_id)
        self.assertEqual(sources[scores.sha256]['id'], scores.acquisition_id)

    def test_identical_bytes_new_receipts_do_not_revise_original_binding(self):
        record = self.record()
        self.ingest(record)
        original_id = self.match()['evidence_id']
        later_fixture = self.document(self.fixture.body, captured_at='2026-10-31T11:00:00Z')
        later_odds = self.document(self.odds.body, captured_at='2026-10-31T11:01:00Z', path='odds')
        result = self.ingest(self.record(attributes={'captured_at': '2026-10-31T11:01:00Z'}), [later_fixture, later_odds])
        self.assertEqual((result['inserted'], result['unchanged']), (0, 1))
        self.assertEqual(self.match()['evidence_id'], original_id)
        quote = self.product.odds(self.match()['id'])['items'][0]
        self.assertEqual((quote['acquisition_id'], quote['captured_at']), (self.odds.acquisition_id, SECOND))
        self.assertNotIn(PROVENANCE_FIELD, record)
        with closing(self.product.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0], 1)

    def test_corrected_quotes_add_history_without_rebinding_old_evidence(self):
        self.ingest()
        previous = self.match()['evidence_id']
        correction = self.document(b'{"odds":2.4}', captured_at='2026-10-31T10:03:00Z', path='odds')
        record = self.record()
        record['odds'][0].update(decimal_odds=2.4, source_document_sha256=correction.sha256)
        self.assertEqual(self.ingest(record, [self.fixture, correction])['inserted'], 1)
        history = self.product.odds(self.match()['id'], history=True)['items']
        self.assertEqual([quote['decimal_odds'] for quote in history], [2.1, 2.4])
        self.assertEqual([quote['acquisition_id'] for quote in history], [self.odds.acquisition_id, correction.acquisition_id])
        self.assertEqual(history[0]['observation_evidence_id'], previous)

    def test_legacy_secondary_hash_is_unresolved_instead_of_borrowing_parent_capture(self):
        self.ingest()
        self.legacy_without_bindings()
        quote = self.product.odds(self.match()['id'])['items'][0]
        self.assertEqual(quote['provenance_status'], 'unresolved')
        self.assertEqual(quote['provenance_code'], 'QUOTE_ACQUISITION_UNBOUND')
        self.assertIsNone(quote['captured_at'])
        self.assertIsNone(quote['acquisition_id'])
        self.assertIsNone(quote['source_url'])
        self.assertEqual(quote['observation_received_at'], FIRST)

    def test_primary_legacy_binding_is_resolvable_but_undeclared_quote_is_not_inferred(self):
        record = self.record()
        record['odds'][0]['source_document_sha256'] = self.fixture.sha256
        self.ingest(record, [self.fixture])
        self.legacy_without_bindings()
        quote = self.product.odds(self.match()['id'])['items'][0]
        self.assertEqual((quote['provenance_status'], quote['captured_at']), ('bound', FIRST))
        record = self.record(source_record_id='43')
        record['odds'][0].pop('source_document_sha256')
        self.ingest(record)
        match = next(item for item in self.product.matches(provider=PROVIDER)['items'] if item['evidence_id'] != quote['evidence_id'])
        undeclared = self.product.odds(match['id'])['items'][0]
        self.assertEqual(undeclared['provenance_code'], 'QUOTE_SOURCE_UNDECLARED')
        self.assertIsNone(undeclared['captured_at'])

    def test_other_provider_or_unretained_payload_cannot_satisfy_dependency(self):
        foreign = self.document(b'{"foreign":true}', provider='statsbomb', path='odds')
        record = self.record()
        record['odds'][0]['source_document_sha256'] = foreign.sha256
        self.assertEqual(self.ingest(record, [self.fixture, foreign])['quarantined'], 1)
        self.assertEqual(self.quarantine_reason(), 'ACQUISITION_PROVIDER_MISMATCH')
        unretained = Document(self.odds.url, self.odds.url, b'not retained', SECOND,
                              hashlib.sha256(b'not retained').hexdigest(), 'application/json', uuid4().hex, 'missing.payload')
        record['odds'][0]['source_document_sha256'] = unretained.sha256
        self.assertEqual(self.ingest(record, [self.fixture, unretained])['quarantined'], 1)
        self.assertEqual(self.quarantine_reason(), 'MISSING_ACQUISITION')

    def test_supplied_metadata_changes_and_ambiguous_receipts_are_not_guessed(self):
        self.odds.captured_at = '2026-10-31T12:00:00Z'
        self.assertEqual(self.ingest()['quarantined'], 1)
        self.assertEqual(self.quarantine_reason(), 'ACQUISITION_METADATA_MISMATCH')
        self.odds.captured_at = SECOND
        duplicate = self.document(self.odds.body, captured_at='2026-10-31T12:00:00Z', path='odds')
        self.assertEqual(self.ingest(documents=[self.fixture, self.odds, duplicate])['quarantined'], 1)
        self.assertEqual(self.quarantine_reason(), 'AMBIGUOUS_ACQUISITION')

    def test_adapter_cannot_inject_reserved_bindings_and_retained_metadata_drift_fails_closed(self):
        record = self.record(**{PROVENANCE_FIELD: {'version': 1, 'provider': PROVIDER, 'documents': {}}})
        self.assertEqual(self.ingest(record)['quarantined'], 1)
        self.assertEqual(self.quarantine_reason(), 'RESERVED_PROVENANCE_FIELD')
        self.ingest()
        with closing(self.product.connect()) as db:
            db.execute('UPDATE connector_acquisitions SET captured_at=? WHERE id=?', ('2026-10-31T14:00:00Z', self.odds.acquisition_id))
            db.commit()
        quote = self.product.odds(self.match()['id'])['items'][0]
        self.assertEqual(quote['provenance_status'], 'unresolved')
        self.assertIsNone(quote['captured_at'])

    def test_orphan_dependency_test_fails_and_sync_retains_quarantine_without_import_success(self):
        connections = Connections(self.product)
        record = self.record()
        record['odds'][0]['source_document_sha256'] = 'f'*64

        def fetch(provider, config, secret, transport, check):
            transport.documents.extend([self.fixture])
            return [record]

        with patch('dragonhydra.connectors.football.fetch', side_effect=fetch):
            for operation in ('test', 'sync'):
                with self.subTest(operation=operation):
                    with self.assertRaises(ConnectorError) as caught:
                        connections.run(PROVIDER, operation)
                    self.assertEqual(caught.exception.code, 'NORMALIZATION_FAILED')
                    diagnostic = connections.describe(PROVIDER)
                    self.assertEqual(diagnostic['status'], 'failing')
                    self.assertIsNone(diagnostic['last_successful_retrieval'])
                    self.assertEqual(self.store.count(PROVIDER), 0)
        self.assertEqual(self.quarantine_reason(), 'MISSING_ACQUISITION')

    def test_each_payload_is_hashed_once_per_operation_not_per_record_and_is_not_trusted_next_time(self):
        records = [self.record(source_record_id=str(number)) for number in range(50)]
        connections = Connections(self.product)

        def fetch(provider, config, secret, transport, check):
            transport.documents.extend([self.fixture, self.odds])
            return records

        real_sha256 = hashlib.sha256
        hashed = []

        def counted(data=b''):
            if data in (self.fixture.body, self.odds.body):
                hashed.append(data)
            return real_sha256(data)

        with patch('dragonhydra.connectors.football.fetch', side_effect=fetch):
            for operation in ('test', 'sync'):
                with self.subTest(operation=operation):
                    hashed.clear()
                    with patch('dragonhydra.connectors.store.hashlib.sha256', side_effect=counted):
                        result = connections.run(PROVIDER, operation)
                    self.assertEqual(result['normalized_rows'], 50)
                    self.assertEqual(hashed.count(self.fixture.body), 1)
                    self.assertEqual(hashed.count(self.odds.body), 1)
            self.odds.body = b'changed after earlier successful validation'
            with self.assertRaises(ConnectorError) as caught:
                connections.run(PROVIDER, 'test')
            self.assertEqual(caught.exception.code, 'NORMALIZATION_FAILED')
        self.assertEqual(self.store.count(PROVIDER), 50)

    def test_mixed_batch_reports_valid_and_quarantined_dependency_counts_explicitly(self):
        good = self.record()
        orphan = self.record(source_record_id='43')
        orphan['odds'][0]['source_document_sha256'] = 'f'*64

        def fetch(provider, config, secret, transport, check):
            transport.documents.extend([self.fixture, self.odds])
            return [good, orphan]

        with patch('dragonhydra.connectors.football.fetch', side_effect=fetch):
            result = Connections(self.product).run(PROVIDER, 'sync')
        self.assertEqual(result['status'], 'imported')
        self.assertEqual((result['retrieved_rows'], result['normalized_rows'], result['invalid_rows']), (2, 1, 1))
        self.assertEqual((result['inserted'], result['quarantined']), (1, 1))
        self.assertEqual(result['normalization_errors'], {'MISSING_ACQUISITION': 1})


@unittest.skipUnless(importlib.util.find_spec('fastapi'), 'Pinned API environment required')
class AcquisitionAPITests(ProvenanceFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.client = TestClient(create_app(self.product.state, local_token='fixture-acquisition-token-123456789', start_worker=False))
        self.addCleanup(self.client.close)
        self.client.headers['Authorization'] = 'Bearer fixture-acquisition-token-123456789'

    def test_acquisition_metadata_requires_authentication_and_provider_scope_without_raw_body(self):
        path = '/dragon/api/v1/connections/'+PROVIDER+'/acquisitions/'+self.odds.acquisition_id
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['sha256'], self.odds.sha256)
        self.assertEqual(response.json()['captured_at'], SECOND)
        self.assertNotIn('body', response.json())
        self.assertNotIn('raw_reference', response.json())
        self.assertNotIn(self.odds.body.decode(), response.text)
        self.assertEqual(self.client.get(path.replace(PROVIDER, 'statsbomb')).status_code, 404)
        self.client.headers.clear()
        self.assertEqual(self.client.get(path).status_code, 401)

    def test_odds_metadata_link_resolves_actual_secondary_hash_and_redacts_old_receipt_urls(self):
        secret = 'fixture-provider-key-never-return'
        self.odds.url += '?apiKey='+secret
        self.odds.resolved_url = self.odds.url
        with closing(self.product.connect()) as db:
            db.execute('UPDATE connector_acquisitions SET original_url=?,resolved_url=? WHERE id=?',
                       (self.odds.url, self.odds.url, self.odds.acquisition_id))
            db.commit()
        self.ingest()
        response = self.client.get('/dragon/api/v1/matches/'+self.match()['id']+'/odds')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(secret, response.text)
        quote = response.json()['items'][0]
        metadata = self.client.get(quote['acquisition_url'])
        self.assertEqual(metadata.status_code, 200)
        self.assertNotIn(secret, metadata.text)
        self.assertEqual(metadata.json()['sha256'], quote['source_document_sha256'])
        self.assertEqual(metadata.json()['captured_at'], quote['captured_at'])

    def test_orphan_dependency_job_cannot_claim_working_through_api(self):
        record = self.record()
        record['attributes']['related_source_sha256'] = ['f'*64]

        def fetch(provider, config, secret, transport, check):
            transport.documents.append(self.fixture)
            return [record]

        with patch('dragonhydra.connectors.football.fetch', side_effect=fetch):
            for action in ('test', 'sync'):
                response = self.client.post('/dragon/api/v1/connections/'+PROVIDER+'/'+action, json={})
                self.assertEqual(response.status_code, 202)
                self.assertTrue(self.client.app.state.jobs.run_once())
                result = self.client.get('/dragon/api/v1/jobs/'+response.json()['id']).json()
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['error']['code'], 'NORMALIZATION_FAILED')
        card = next(item for item in self.client.get('/dragon/api/v1/connections').json()['items'] if item['id'] == PROVIDER)
        self.assertEqual(card['status'], 'failing')
        self.assertEqual(card['record_count'], 0)
        self.assertEqual(card['quarantined_count'], 1)
