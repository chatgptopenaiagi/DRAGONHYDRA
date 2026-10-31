"""Explicit context API selection and frozen-request replay; no real inference."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import hashlib
import importlib.util
import json
import time
import unittest
from unittest.mock import patch

from dragonhydra import local_ai, source_context
from dragonhydra.cognition import memory
from dragonhydra.connectors import research, statsbomb_context as binding, statsbomb_context_parser as parser
from dragonhydra.connectors.core import Transport
import test_statsbomb_context as fixtures
import test_statsbomb_context_parser as native

API = '/dragon/api/v1'


@unittest.skipUnless(importlib.util.find_spec('fastapi'), 'Pinned server environment required')
class ContextAIAPITests(unittest.TestCase):
    readonly = fixtures.StatsBombContextTests.readonly
    document = fixtures.StatsBombContextTests.document
    update = fixtures.StatsBombContextTests.update

    def setUp(self):
        environment = patch.dict('os.environ', {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        transport = patch.object(Transport, 'get', side_effect=AssertionError('Provider HTTP forbidden'))
        transport.start()
        self.addCleanup(transport.stop)
        inference = patch('dragonhydra.local_ai.infer', side_effect=AssertionError('Real inference forbidden'))
        self.inference = inference.start()
        self.addCleanup(inference.stop)
        native.BoundParserTests.setUp(self)
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.app = create_app(self.product.state, local_token='context-api-synthetic-owner-token', start_worker=False)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.client.headers['Authorization'] = 'Bearer context-api-synthetic-owner-token'
        self.product, self.jobs = self.app.state.product, self.app.state.jobs
        self.match_id = local_ai._package_from_retained(self.product, local_ai._retained_row(
            self.product.evidence(self.observation_id)))['event']['id']
        self.route = API+'/matches/'+self.match_id
        self.package2 = local_ai.build_package(self.product, self.match_id)
        self.context_receipt = source_context.append(self.path, self.payload,
            validate_dependencies=parser.make_validator(self.raw))
        self.context_id = self.context_receipt['record_id']
        self.package3 = local_ai.build_context_package(self.product, self.match_id, self.context_id)

    def post(self, context_id=None, key=None, *, path=None):
        headers = {'Idempotency-Key':key} if key is not None else {}
        return self.client.post((path or self.route)+'/local-explanations',
            json={'context_record_id':context_id or self.context_id}, headers=headers)

    def job_count(self):
        with closing(self.product.connect()) as db:
            return db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0]

    def correction(self):
        newer = deepcopy(fixtures.MATCH)
        newer['home_score'] = 4
        document = self.document([newer], research.STATSBOMB_BASE+'matches/43/106.json')
        class RetainedOnly:
            def get(inner, url):
                return self.catalog if url.endswith('competitions.json') else document
        record = research._statsbomb({'competition_id':43,'season_id':106},RetainedOnly(),lambda:None)[0]
        self.store.ingest('statsbomb',[record],[self.catalog,document])

    def later_context(self, *, pending=False):
        events = native.EVENTS + [native.event(9)]
        document = self.document(native.raw(events), binding.ROLE_URLS['events'])
        payload = deepcopy(self.payload)
        with closing(self.readonly()) as db:
            payload['documents']['events'] = binding.document_binding(db,self.raw,'events',document.acquisition_id)
        lineups = (self.raw/(payload['documents']['lineups']['sha256']+'.payload')).read_bytes()
        payload['projection'] = parser.parse(document.body,lineups,parent=payload['parent'])
        if pending:
            with patch.object(memory,'_revision_receipt',side_effect=ValueError('SYNTHETIC_PENDING')):
                with self.assertRaisesRegex(ValueError,'SYNTHETIC_PENDING'):
                    source_context.append(self.path,payload,validate_dependencies=parser.make_validator(self.raw))
            return None
        return source_context.append(self.path,payload,validate_dependencies=parser.make_validator(self.raw))['record_id']

    @staticmethod
    def accepted(package, endpoint, key, **options):
        options['check']()
        fact = package['allowed_facts'][-3]
        return {**local_ai.validate_output(package,json.dumps({'fact_id':fact['fact_id']})),
                'runtime':{'local_endpoint':True,'model':'synthetic-selection-stub'}}

    def test_context_selection_requires_authentication(self):
        self.client.headers.clear()
        self.assertEqual(self.client.get(self.route+'/analysis-package',params={'context_record_id':self.context_id}).status_code,401)
        self.assertEqual(self.post().status_code,401)
        self.assertEqual(self.job_count(),0)
        self.inference.assert_not_called()

    def test_explicit_package_uses_exact_context_without_writes_or_inference(self):
        with patch.object(self.product,'connect',side_effect=AssertionError('Writable helper forbidden')):
            response = self.client.get(self.route+'/analysis-package',params={'context_record_id':self.context_id})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),self.package3)
        queued = self.post()
        self.assertEqual(queued.status_code,202)
        self.assertEqual(queued.json()['payload'],{'package':self.package3})
        self.assertEqual(self.package3['evidence']['C1']['documents'],self.payload['documents'])
        self.inference.assert_not_called()

    def test_default_query_and_empty_body_keep_package_two_bytes(self):
        actual = self.client.get(self.route+'/analysis-package')
        self.assertEqual(actual.status_code,200)
        self.assertEqual(local_ai.canonical(actual.json()),local_ai.canonical(self.package2))
        queued = self.client.post(self.route+'/local-explanations',json={})
        self.assertEqual(queued.status_code,202)
        self.assertEqual(local_ai.canonical(queued.json()['payload']['package']),local_ai.canonical(self.package2))
        self.assertEqual(queued.json()['payload']['package']['schema_version'],local_ai.SCHEMA)

    def test_strict_optional_selector_and_unknown_fields_are_rejected(self):
        invalid = [None,'',True,False,1,1.0,{},[],self.context_id.upper(),'latest',' '+self.context_id]
        for value in invalid:
            with self.subTest(body=value):
                self.assertEqual(self.client.post(self.route+'/local-explanations',json={'context_record_id':value}).status_code,422)
        for body in ({'context_record_id':self.context_id,'package':{}}, {'context_id':self.context_id},
                     {'context_record_id':self.context_id,'credential':'synthetic-private-input'}):
            response = self.client.post(self.route+'/local-explanations',json=body)
            self.assertEqual(response.status_code,422)
            self.assertNotIn('synthetic-private-input',response.text)
        for value in ('','null','true','1','latest',self.context_id.upper()):
            with self.subTest(query=value):
                self.assertEqual(self.client.get(self.route+'/analysis-package',params={'context_record_id':value}).status_code,422)
        self.assertEqual(self.job_count(),0)

    def test_explicit_unavailable_or_parent_mismatch_creates_no_job(self):
        with patch('dragonhydra.local_ai_service.Settings.effective',side_effect=AssertionError('No settings before grounding')):
            response = self.post('source_context:'+'0'*64)
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['error']['code'],'AI_CONTEXT_UNAVAILABLE')
            self.correction()
            response = self.post()
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['error']['code'],'AI_CONTEXT_PARENT_MISMATCH')
        self.assertEqual(self.job_count(),0)
        self.inference.assert_not_called()

    def test_unconfigured_worker_keeps_deterministic_parent_citation_and_full_manifest(self):
        queued = self.post().json()
        self.assertTrue(self.jobs.run_once())
        job = self.jobs.get(queued['id'])
        self.assertEqual(job['status'],'succeeded')
        result = job['result']
        self.assertEqual(result['kind'],'deterministic')
        self.assertEqual(result['local_ai']['code'],'AI_NOT_CONFIGURED')
        self.assertEqual(result['observations'],[self.package3['allowed_facts'][0]['observation']])
        self.assertEqual([item['id'] for item in result['evidence']],[self.observation_id])
        self.assertEqual(result['input_manifest'],[self.observation_id,self.context_id,
            self.payload['documents']['events']['id'],self.payload['documents']['lineups']['id']])
        self.inference.assert_not_called()

    def test_accepted_stub_resolves_three_exact_citations_through_worker(self):
        queued = self.post().json()
        with (patch('dragonhydra.local_ai_service.Settings.effective',return_value=('http://127.0.0.1:12345','synthetic-api-only-key')),
                patch('dragonhydra.local_ai.infer',side_effect=self.accepted)):
            self.assertTrue(self.jobs.run_once())
        job = self.jobs.get(queued['id'])
        self.assertEqual(job['status'],'succeeded')
        result = job['result']
        self.assertEqual(result['kind'],'local_llm')
        self.assertEqual(result['mode'],'constrained_source_fact_selection')
        self.assertEqual(result['evidence_aliases'],['E1','C1'])
        self.assertEqual(result['observations'],[self.package3['allowed_facts'][-3]['observation']])
        self.assertEqual(len(result['evidence']),3)
        for role,citation in zip(source_context.ROLES,result['evidence'][1:]):
            document = self.payload['documents'][role]
            self.assertEqual(citation['id'],document['id'])
            self.assertEqual(citation['sha256'],document['sha256'])
            self.assertEqual(citation['captured_at'],document['captured_at'])
            self.assertEqual(citation['context_record_id'],self.context_id)
            self.assertEqual(citation['context_record_sha256'],self.context_receipt['record_content_hash'])
            self.assertEqual(citation['parent_observation_id'],self.observation_id)
            self.assertEqual(self.client.get(citation['url']).status_code,200)
        self.assertEqual(len(result['input_manifest']),4)

    def test_queued_context_keeps_old_parent_through_correction_and_pending_tail(self):
        queued = self.post().json()
        self.correction()
        self.later_context(pending=True)
        self.assertTrue(self.jobs.run_once())
        job = self.jobs.get(queued['id'])
        self.assertEqual(job['status'],'succeeded')
        self.assertEqual(job['payload']['package'],self.package3)
        self.assertEqual(job['result']['input_manifest'][0:2],[self.observation_id,self.context_id])
        self.assertEqual(job['result']['package_sha256'],self.package3['package_sha256'])
        evidence = self.client.get(job['result']['evidence'][0]['url']).json()
        self.assertEqual(evidence['record']['score_home'],3)

    def test_queued_selected_data_loss_fails_before_runtime_settings(self):
        queued = self.post().json()
        (self.raw/(self.payload['documents']['events']['sha256']+'.payload')).unlink()
        with patch('dragonhydra.local_ai_service.Settings.effective',side_effect=AssertionError('Settings must not be read')) as settings:
            self.assertTrue(self.jobs.run_once())
        job = self.jobs.get(queued['id'])
        self.assertEqual(job['status'],'failed')
        self.assertIsNone(job['result'])
        settings.assert_not_called()
        self.inference.assert_not_called()

    def test_replay_returns_frozen_job_after_parent_change_and_selected_raw_loss(self):
        first = self.post(key='frozen-context-request')
        self.assertEqual(first.status_code,202)
        self.correction()
        (self.raw/(self.payload['documents']['events']['sha256']+'.payload')).unlink()
        with patch('dragonhydra.api.build_context_package',side_effect=AssertionError('Replay must not rebuild')):
            replay = self.post(key='frozen-context-request')
        self.assertEqual(replay.status_code,202)
        self.assertEqual(replay.json()['id'],first.json()['id'])
        self.assertEqual(replay.json()['payload'],first.json()['payload'])
        self.assertEqual(self.job_count(),1)
        self.assertEqual(self.post(key='new-context-request').status_code,409)

    def test_replay_conflicts_for_other_context_match_kind_or_schema(self):
        self.assertEqual(self.post(key='context-slot').status_code,202)
        second = self.later_context()
        self.assertEqual(self.post(second,key='context-slot').status_code,409)
        self.assertEqual(self.post(key='context-slot',path=API+'/matches/'+'0'*64).status_code,409)
        self.client.post(self.route+'/explanations',json={},headers={'Idempotency-Key':'ordinary-slot'})
        self.assertEqual(self.post(key='ordinary-slot').status_code,409)
        self.client.post(self.route+'/local-explanations',json={},headers={'Idempotency-Key':'package-two-slot'})
        self.assertEqual(self.post(key='package-two-slot').status_code,409)
        self.assertEqual(self.client.post(self.route+'/local-explanations',json={},headers={'Idempotency-Key':'context-slot'}).status_code,409)
        self.assertEqual(self.job_count(),3)

    def test_key_length_is_checked_before_lookup_or_construction(self):
        with (patch.object(self.product,'connect',side_effect=AssertionError('Invalid key must precede lookup')),
                patch('dragonhydra.api.build_context_package',side_effect=AssertionError('Invalid key must precede construction'))):
            for key in ('','x'*129):
                response = self.post(key=key)
                self.assertEqual(response.status_code,400)
                self.assertEqual(response.json()['error']['code'],'INVALID_IDEMPOTENCY_KEY')
        self.assertEqual(self.job_count(),0)

    def test_other_owner_has_independent_key_and_reader_cannot_acquire_context(self):
        owner = self.post(key='shared-spelling').json()
        token = 'synthetic-reader-session-token'
        with closing(self.product.connect()) as db:
            db.execute('INSERT INTO product_sessions VALUES(?,?,?,?)',
                (hashlib.sha256(token.encode()).hexdigest(),'fixture:reader',json.dumps(['reader']),time.time()+600))
            db.commit()
        self.client.headers.pop('Authorization')
        self.client.cookies.set('dragon_session',token)
        reader = self.post(key='shared-spelling')
        self.assertEqual(reader.status_code,202)
        self.assertNotEqual(reader.json()['id'],owner['id'])
        self.assertEqual(reader.json()['owner'],'fixture:reader')
        self.assertEqual(self.client.get(API+'/jobs/'+owner['id']).status_code,403)
        self.assertEqual(self.client.get(self.route+'/analysis-package',params={'context_record_id':self.context_id}).status_code,200)
        self.assertEqual(self.client.post(self.route+'/source-context',json={}).status_code,403)

    def test_simultaneous_first_context_requests_keep_final_submit_gate(self):
        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(lambda _:self.post(key='simultaneous-context'),range(2)))
        self.assertTrue(all(response.status_code==202 for response in responses))
        self.assertEqual(responses[0].json()['id'],responses[1].json()['id'])
        self.assertEqual(self.job_count(),1)


if __name__ == '__main__':
    unittest.main()
