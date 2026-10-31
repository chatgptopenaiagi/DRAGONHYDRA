"""Authenticated context views and frozen job submission, synthetic/no HTTP."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import sqlite3
import time
import unittest
from unittest.mock import patch

from dragonhydra import public_results, source_context
from dragonhydra.cognition import memory
from dragonhydra.connectors import statsbomb_context as binding, statsbomb_context_parser as parser
from dragonhydra.connectors import statsbomb_context_view as view
from dragonhydra.connectors.core import Transport
from dragonhydra.product import API, Product, identity
import test_statsbomb_context as fixtures
import test_statsbomb_context_parser as parser_fixtures


TOKEN = 'context-api-fixture-owner-token-123456789'


class ContextAPITests(unittest.TestCase):
    readonly = fixtures.StatsBombContextTests.readonly
    document = fixtures.StatsBombContextTests.document
    update = fixtures.StatsBombContextTests.update
    changed_parent_raw = fixtures.StatsBombContextTests.changed_parent_raw

    def setUp(self):
        fixtures.StatsBombContextTests.setUp(self)
        from dragonhydra.api import create_app
        from fastapi.testclient import TestClient
        self.client = TestClient(create_app(self.product.state,local_token=TOKEN,start_worker=False))
        self.addCleanup(self.client.close)
        self.client.headers['Authorization'] = 'Bearer '+TOKEN
        self.match_id = identity('fixture','statsbomb','3869685')
        self.url = API+'/matches/'+self.match_id+'/source-context'
        self.events_url = API+'/matches/'+self.match_id+'/source-events'
        documents = {'events':self.document(parser_fixtures.raw(parser_fixtures.EVENTS),binding.ROLE_URLS['events']),
                     'lineups':self.document(parser_fixtures.raw(parser_fixtures.LINEUPS),binding.ROLE_URLS['lineups'])}
        with closing(self.readonly()) as db:
            self.payload['documents'] = {role:binding.document_binding(db,self.raw,role,doc.acquisition_id)
                                         for role,doc in documents.items()}
        self.payload['parser_version'] = parser.VERSION
        self.payload['projection'] = parser.parse(parser_fixtures.raw(parser_fixtures.EVENTS),
            parser_fixtures.raw(parser_fixtures.LINEUPS),parent=self.parent)

    def append(self):
        return source_context.append(self.path,self.payload,validate_dependencies=parser.make_validator(self.raw))

    def current_schema(self):
        with closing(self.readonly()) as db:
            return db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall()

    def assert_safe(self,value):
        text = json.dumps(value)
        for forbidden in ('raw_reference','source_raw','normalized_record','original_repository_url',str(self.product.state),'SYNTHETIC'):
            self.assertNotIn(forbidden,text)

    def new_parent(self):
        row = deepcopy(fixtures.MATCH)
        row['last_updated'] = '2026-10-31T12:00:00Z'
        return self.changed_parent_raw([row])

    def test_authenticated_reads_and_admin_only_post(self):
        self.client.headers.pop('Authorization')
        self.assertEqual(self.client.get(self.url).status_code,401)
        self.assertEqual(self.client.get(self.events_url).status_code,401)
        self.assertEqual(self.client.post(self.url,json={}).status_code,401)
        cookie = 'fixture-context-reader'
        with closing(self.product.connect()) as db:
            db.execute('INSERT INTO product_sessions VALUES(?,?,?,?)',
                (hashlib.sha256(cookie.encode()).hexdigest(),'fixture:reader','["reader"]',time.time()+600))
            db.commit()
        self.client.cookies.set('dragon_session',cookie)
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(self.client.post(self.url,json={}).status_code,403)

    def test_missing_context_is_explicit_and_reads_never_initialize_schema(self):
        before = self.current_schema()
        for url in (self.url,self.events_url):
            response = self.client.get(url)
            self.assertEqual(response.status_code,200)
            body = response.json()
            self.assertTrue(body['supported'])
            self.assertEqual(body['availability'],'not_requested')
            self.assertEqual(body['parent_observation_id'],self.observation_id)
            self.assertIsNone(body['context_record_id'])
            for key in ('items','total','projection'):
                self.assertNotIn(key,body)
            self.assert_safe(body)
        self.assertEqual(self.current_schema(),before)
        self.assertFalse(any('cognitive_' in row[1] for row in before))

    def test_available_context_has_safe_bound_metadata_and_exact_projection(self):
        receipt = self.append()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        body = response.json()
        self.assertEqual(body['availability'],'available')
        self.assertEqual(body['context_record_id'],receipt['record_id'])
        self.assertEqual(body['context_parent_observation_id'],self.observation_id)
        self.assertEqual(body['projection'],self.payload['projection'])
        self.assertEqual({item['role'] for item in body['documents']},{'events','lineups'})
        for metadata in body['documents']:
            expected = self.payload['documents'][metadata['role']]
            self.assertEqual({key:metadata[key] for key in expected},expected)
            self.assertEqual(self.client.get(metadata['metadata_url']).status_code,200)
        self.assert_safe(body)

    def test_native_page_bounds_absent_fields_and_no_synthesized_rows(self):
        self.append()
        body = self.client.get(self.events_url+'?offset=0&limit=2').json()
        self.assertEqual(body['items'],parser_fixtures.EVENTS[:2])
        self.assertEqual(body['total'],4)
        self.assertNotIn('team',body['items'][0])
        self.assertEqual(body['items'][1]['minute'],0)
        self.assert_safe(body)
        for query in ('?limit=201','?limit=0','?offset=-1'):
            self.assertEqual(self.client.get(self.events_url+query).status_code,422)
        exhausted = self.client.get(self.events_url+'?offset=100').json()
        self.assertEqual(exhausted['items'],[])
        self.assertEqual(exhausted['total'],4)

    def test_current_parent_change_retains_old_context_reference_without_old_statistics(self):
        receipt = self.append()
        new_parent = self.new_parent()
        self.assertNotEqual(new_parent,self.observation_id)
        for url in (self.url,self.events_url):
            body = self.client.get(url).json()
            self.assertEqual(body['availability'],'parent_changed')
            self.assertEqual(body['parent_observation_id'],new_parent)
            self.assertEqual(body['context_parent_observation_id'],self.observation_id)
            self.assertEqual(body['context_record_id'],receipt['record_id'])
            for key in ('projection','items','total'):
                self.assertNotIn(key,body)

    def test_corrupt_or_missing_raw_is_unavailable_and_never_leaks_paths(self):
        receipt = self.append()
        document = self.payload['documents']['events']
        path = self.raw/(document['sha256']+'.payload')
        for contents in (None,b'corrupt'):
            if contents is None:
                path.unlink()
            else:
                path.write_bytes(contents)
            for url in (self.url,self.events_url):
                response = self.client.get(url)
                self.assertEqual(response.status_code,200)
                body = response.json()
                self.assertEqual(body['availability'],'unavailable')
                self.assertEqual(body['context_record_id'],receipt['record_id'])
                for key in ('projection','items','total'):
                    self.assertNotIn(key,body)
                self.assert_safe(body)

    def test_pending_receipt_stays_unavailable_read_does_not_recover(self):
        with patch.object(memory,'_revision_receipt',side_effect=RuntimeError('fixture crash')):
            with self.assertRaises(RuntimeError):
                self.append()
        for url in (self.url,self.events_url):
            body = self.client.get(url).json()
            self.assertEqual(body['availability'],'unavailable')
            self.assertEqual(body['code'],'CONTEXT_RECEIPT_PENDING')
            self.assertIsNotNone(body['context_record_id'])
            self.assertNotIn('projection',body)
            self.assertNotIn('items',body)
        with closing(self.readonly()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM cognitive_receipts').fetchone()[0],0)

    def test_context_reads_use_only_readonly_connections_and_selects_no_legacy_schema_helpers(self):
        self.append()
        connect = sqlite3.connect
        statements = []
        def readonly(*args,**kwargs):
            self.assertIn('?mode=ro',str(args[0]))
            self.assertTrue(kwargs.get('uri'))
            db = connect(*args,**kwargs)
            db.set_trace_callback(statements.append)
            return db
        with patch.object(sqlite3,'connect',side_effect=readonly), \
             patch.object(Product,'find',side_effect=AssertionError('legacy finder forbidden')), \
             patch.object(public_results,'_schema',side_effect=AssertionError('schema forbidden')), \
             patch.object(Transport,'get',side_effect=AssertionError('HTTP forbidden')):
            self.assertEqual(self.client.get(self.url).json()['availability'],'available')
            self.assertEqual(self.client.get(self.events_url).json()['availability'],'available')
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().upper().startswith(('SELECT','PRAGMA QUERY_ONLY','BEGIN')) for sql in statements),statements)

    def test_unsupported_known_public_match_and_unknown_match_leave_schema_unchanged(self):
        with closing(self.product.connect()) as db:
            public_results.ingest_bytes(db,json.dumps({'name':'Fixture league','matches':[
                {'date':'2026-10-01','team1':'One','team2':'Two'}]}).encode(),
                source_id='fixture-public',source_url='https://example.invalid/fixture')
            native = db.execute("SELECT fixture_key FROM public_fixture_records WHERE source_id='fixture-public'").fetchone()[0]
        match = identity('fixture','fixture-public',native)
        before = self.current_schema()
        for route in ('source-context','source-events'):
            body = self.client.get(API+'/matches/'+match+'/'+route).json()
            self.assertFalse(body['supported'])
            self.assertEqual(body['availability'],'unsupported')
            self.assertNotIn('projection',body)
            self.assertNotIn('items',body)
        self.assertEqual(self.client.get(API+'/matches/'+'0'*64+'/source-context').status_code,404)
        self.assertEqual(self.current_schema(),before)

    def test_post_freezes_exact_parent_and_idempotently_queues_one_job(self):
        before = self.current_schema()
        first = self.client.post(self.url,json={},headers={'Idempotency-Key':'context-api-idempotency'})
        self.assertEqual(first.status_code,202,first.text)
        job = first.json()
        self.assertEqual(job['kind'],'statsbomb_context')
        self.assertEqual(job['status'],'queued')
        self.assertEqual(job['attempts'],0)
        self.assertEqual(job['payload']['parent'],self.parent)
        self.assertEqual(job['payload']['match_id'],self.match_id)
        second = self.client.post(self.url,json={},headers={'Idempotency-Key':'context-api-idempotency'})
        self.assertEqual(second.status_code,202)
        self.assertEqual(second.json()['id'],job['id'])
        with closing(self.readonly()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM product_jobs WHERE kind='statsbomb_context'").fetchone()[0],1)
        self.assertEqual(self.current_schema(),before)

    def test_post_rejects_extra_fields_and_same_key_after_parent_changes(self):
        self.assertEqual(self.client.post(self.url,json={'url':'https://example.invalid'}).status_code,422)
        first = self.client.post(self.url,json={},headers={'Idempotency-Key':'parent-freeze-conflict'})
        self.assertEqual(first.status_code,202,first.text)
        self.new_parent()
        conflict = self.client.post(self.url,json={},headers={'Idempotency-Key':'parent-freeze-conflict'})
        self.assertEqual(conflict.status_code,409,conflict.text)
        self.assertEqual(conflict.json()['error']['code'],'IDEMPOTENCY_CONFLICT')
        original = self.client.get(API+'/jobs/'+first.json()['id']).json()
        self.assertEqual(original['payload']['parent']['observation_id'],self.observation_id)

    def test_post_unsupported_known_native_selection_and_unknown_match_are_controlled(self):
        record = deepcopy(self.record)
        record['source_record_id'] = 'other-native-match'
        self.assertEqual(self.store.ingest('statsbomb',[record],[self.catalog,self.matches])['inserted'],1)
        other = identity('fixture','statsbomb','other-native-match')
        rejected = self.client.post(API+'/matches/'+other+'/source-context',json={})
        self.assertEqual(rejected.status_code,400,rejected.text)
        self.assertEqual(rejected.json()['error']['code'],'STATSBOMB_CONTEXT_SELECTION_UNSUPPORTED')
        self.assertEqual(self.client.post(API+'/matches/'+'0'*64+'/source-context',json={}).status_code,404)

    def test_unavailable_hash_valid_context_never_exposes_private_parent_path(self):
        self.append()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER cognitive_records_no_update')
            db.execute('DROP TRIGGER cognitive_receipts_no_update')
            old_id,natural_key,raw = db.execute('SELECT record_id,natural_key,payload FROM cognitive_records').fetchone()
            payload = json.loads(raw)
            payload['parent']['observation_id'] = str(self.product.state)
            encoded = memory._canonical(payload)
            fingerprint = memory._hash(encoded)
            new_id = source_context.KIND+':'+memory._hash(memory._canonical([source_context.KIND,natural_key,fingerprint]))
            db.execute('UPDATE cognitive_records SET record_id=?,fingerprint=?,payload=? WHERE record_id=?',
                       (new_id,fingerprint,encoded.decode(),old_id))
            db.execute('UPDATE cognitive_receipts SET record_id=? WHERE record_id=?',(new_id,old_id))
            db.commit()
        for url in (self.url,self.events_url):
            body = self.client.get(url).json()
            self.assertEqual(body['availability'],'unavailable')
            self.assertEqual(body['context_record_id'],new_id)
            self.assertIsNone(body['context_parent_observation_id'])
            self.assert_safe(body)

    def test_ordinary_context_endpoints_preserve_existing_behavior(self):
        before = {name:self.client.get(API+'/matches/'+self.match_id+'/'+name).json() for name in ('lineups','statistics')}
        self.append()
        for name,value in before.items():
            self.assertEqual(self.client.get(API+'/matches/'+self.match_id+'/'+name).json(),value)


if __name__ == '__main__':
    unittest.main()
