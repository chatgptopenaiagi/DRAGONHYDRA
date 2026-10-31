"""Optional package/3 service dispatch over real synthetic retained evidence."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from dragonhydra import local_ai, source_context
from dragonhydra.connectors import research
from dragonhydra.connectors import statsbomb_context as binding, statsbomb_context_parser as parser
from dragonhydra.connectors.core import Document
from dragonhydra.local_ai_service import explain
from dragonhydra.product import Product
import test_statsbomb_context as parent_fixture
import test_statsbomb_context_parser as native_fixture


ROOT = Path(__file__).resolve().parents[1]
KEY = 'synthetic-private-local-key-for-service-test'
CUTOFF = '2026-10-31T12:00:00.000000Z'


class LocalAIContextServiceTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/'runtime/scratch'
        scratch.mkdir(parents=True,exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch,prefix='local-ai-context-service-')
        self.addCleanup(temporary.cleanup)
        network = patch('dragonhydra.connectors.core.Transport.get',side_effect=AssertionError('Provider HTTP forbidden'))
        network.start()
        self.addCleanup(network.stop)
        self.product = Product(Path(temporary.name))
        self.raw = self.product.state/'raw/connectors'
        self.raw.mkdir(parents=True)
        self.catalog = self.document(parent_fixture.CATALOG,research.STATSBOMB_BASE+'competitions.json')
        self.matches = self.document([parent_fixture.MATCH],research.STATSBOMB_BASE+'matches/43/106.json')
        fixture = self
        class RetainedOnly:
            def get(self,url):
                return fixture.catalog if url.endswith('competitions.json') else fixture.matches
        record = research._statsbomb({'competition_id':43,'season_id':106},RetainedOnly(),lambda:None)[0]
        self.product.connector_store.ingest('statsbomb',[record],[self.catalog,self.matches])
        match = self.product.matches(provider='statsbomb')['items'][0]
        self.match_id = match['id']
        self.package2_before_context = local_ai.build_package(self.product,self.match_id)
        self.documents = {
            'events':self.document(native_fixture.EVENTS,binding.ROLE_URLS['events']),
            'lineups':self.document(native_fixture.LINEUPS,binding.ROLE_URLS['lineups'])}
        with closing(sqlite3.connect(self.product.db_path.as_uri()+'?mode=ro',uri=True)) as db:
            parent = binding.parent_binding(db,self.raw,match['evidence_id'])
            documents = {role:binding.document_binding(db,self.raw,role,doc.acquisition_id)
                         for role,doc in self.documents.items()}
        payload = {'provider':'statsbomb','source_record_id':'3869685','parent':parent,'documents':documents,
            'parser_version':parser.VERSION,
            'projection':parser.parse(native_fixture.raw(native_fixture.EVENTS),
                                      native_fixture.raw(native_fixture.LINEUPS),parent=parent)}
        self.context = source_context.append(self.product.db_path,payload,validate_dependencies=parser.make_validator(self.raw))
        self.package = local_ai.build_context_package(self.product,self.match_id,self.context['record_id'])

    def document(self,value,url):
        raw = native_fixture.raw(value)
        sha = hashlib.sha256(raw).hexdigest()
        resolved = url.replace(research.STATSBOMB_BASE,
            'https://raw.githubusercontent.com/hudl/open-data/refs/heads/master/data/')
        doc = Document(url,resolved,raw,parent_fixture.CAPTURE,sha,'application/json',uuid4().hex,sha+'.payload')
        (self.raw/doc.raw_reference).write_bytes(raw)
        self.product.connector_store.receipt('statsbomb',doc)
        return doc

    def manifest(self):
        evidence = self.package['evidence']
        return [evidence['E1']['id'],evidence['C1']['id'],
                evidence['C1']['documents']['events']['id'],evidence['C1']['documents']['lineups']['id']]

    def expected_parent_citation(self):
        ident = self.package['evidence']['E1']['id']
        return [{'id':ident,'url':'/dragon/api/v1/evidence/'+ident,'label':'Retained source record'}]

    @staticmethod
    def rehash(package):
        package['package_sha256'] = hashlib.sha256(local_ai.canonical(
            {key:value for key,value in package.items() if key != 'package_sha256'})).hexdigest()
        return package

    def test_unconfigured_context_falls_back_to_status_with_parent_only_and_all_input_ids(self):
        with patch('dragonhydra.local_ai_service.Settings.effective',return_value=('',None)), \
             patch('dragonhydra.local_ai.infer') as inference:
            result = explain(self.product,self.package)
        inference.assert_not_called()
        self.assertEqual(result['kind'],'deterministic')
        self.assertEqual(result['observations'],[self.package['allowed_facts'][0]['observation']])
        self.assertEqual(result['evidence'],self.expected_parent_citation())
        self.assertEqual(result['input_manifest'],self.manifest())
        self.assertEqual(result['local_ai']['code'],'AI_NOT_CONFIGURED')
        self.assertFalse(result['local_ai']['accepted'])
        self.assertNotIn('fact_id',result)
        self.assertNotIn('evidence_aliases',result)

    def test_runtime_and_output_failures_keep_deterministic_context_fallback(self):
        for code in ('AI_UNAVAILABLE','AI_OUTPUT_REJECTED','AI_OUTPUT_TRUNCATED'):
            with self.subTest(code=code), \
                 patch('dragonhydra.local_ai_service.Settings.effective',return_value=('http://127.0.0.1:12345',KEY)), \
                 patch('dragonhydra.local_ai.infer',side_effect=local_ai.LocalAIError(code,'Synthetic unavailable runtime.')):
                result = explain(self.product,self.package)
            self.assertEqual(result['kind'],'deterministic')
            self.assertEqual(result['local_ai']['code'],code)
            self.assertEqual(result['evidence'],self.expected_parent_citation())
            self.assertEqual(result['input_manifest'],self.manifest())
            self.assertEqual(result['observations'],[self.package['allowed_facts'][0]['observation']])

    def accepted(self,package,fact):
        return {**local_ai.validate_output(package,json.dumps({'fact_id':fact['fact_id']})),
                'runtime':{'local_endpoint':True,'interface':'synthetic-no-inference'}}

    def test_accepted_context_selection_copies_trusted_citations_and_manifest(self):
        fact = next(item for item in self.package['allowed_facts'] if item['evidence_aliases'] == ['E1','C1'])
        accepted = self.accepted(self.package,fact)
        with patch('dragonhydra.local_ai_service.Settings.effective',return_value=('http://127.0.0.1:12345',KEY)), \
             patch('dragonhydra.local_ai.infer',return_value=accepted):
            result = explain(self.product,self.package)
        self.assertEqual(result['kind'],'local_llm')
        self.assertEqual(result['mode'],'constrained_source_fact_selection')
        self.assertEqual(result['fact_id'],fact['fact_id'])
        self.assertEqual(result['evidence_aliases'],['E1','C1'])
        self.assertEqual(result['observations'],[fact['observation']])
        self.assertEqual(result['evidence'],accepted['evidence'])
        self.assertEqual(result['input_manifest'],accepted['input_manifest'])
        self.assertEqual(result['input_manifest'],self.manifest())
        self.assertEqual(len(result['evidence']),3)
        self.assertTrue(result['local_ai']['accepted'])
        self.assertNotIn(KEY,json.dumps(result))
        self.assertNotIn(str(self.product.state),json.dumps(result))
        self.assertFalse(any('/source-context' in item['url'] for item in result['evidence']))

    def test_context_package_parent_fact_keeps_parent_only_citation_and_full_manifest(self):
        fact = self.package['allowed_facts'][0]
        accepted = self.accepted(self.package,fact)
        with patch('dragonhydra.local_ai_service.Settings.effective',return_value=('http://127.0.0.1:12345',KEY)), \
             patch('dragonhydra.local_ai.infer',return_value=accepted):
            result = explain(self.product,self.package)
        self.assertEqual(result['fact_id'],fact['fact_id'])
        self.assertEqual(result['evidence_aliases'],['E1'])
        self.assertEqual(result['evidence'],accepted['evidence'])
        self.assertEqual(len(result['evidence']),1)
        self.assertEqual(result['input_manifest'],self.manifest())

    def test_rehashed_context_tampering_errors_before_settings_or_inference(self):
        original = self.package
        cases = []
        changed = deepcopy(original); changed['context_summary']['event_rows'] += 1; cases.append(changed)
        changed = deepcopy(original); changed['evidence']['C1']['parent_observation_id'] = 'f'*64; cases.append(changed)
        changed = deepcopy(original); changed['evidence']['C1']['documents']['events']['sha256'] = 'f'*64; cases.append(changed)
        changed = deepcopy(original); changed['allowed_facts'][0]['observation'] = 'Untrusted source fact.'; cases.append(changed)
        for index,package in enumerate(cases):
            with self.subTest(case=index), \
                 patch('dragonhydra.local_ai_service.Settings.effective') as settings, \
                 patch('dragonhydra.local_ai.infer') as inference:
                with self.assertRaises(local_ai.LocalAIError):
                    explain(self.product,self.rehash(package))
            settings.assert_not_called()
            inference.assert_not_called()

    def test_missing_selected_document_fails_before_settings_and_never_falls_back(self):
        (self.raw/self.documents['events'].raw_reference).unlink()
        with patch('dragonhydra.local_ai_service.Settings.effective') as settings, \
             patch('dragonhydra.local_ai.infer') as inference:
            with self.assertRaises(local_ai.LocalAIError):
                explain(self.product,self.package)
        settings.assert_not_called()
        inference.assert_not_called()

    def test_grounding_runs_before_settings_resolution_and_inference(self):
        calls = []
        grounding = local_ai.validate_grounding
        fact = self.package['allowed_facts'][0]
        accepted = self.accepted(self.package,fact)
        def ground(product,package):
            calls.append('grounding')
            return grounding(product,package)
        def settings():
            calls.append('settings')
            return 'http://127.0.0.1:12345',KEY
        def infer(*args,**kwargs):
            calls.append('inference')
            return accepted
        with patch('dragonhydra.local_ai.validate_grounding',side_effect=ground), \
             patch('dragonhydra.local_ai_service.Settings.effective',side_effect=settings), \
             patch('dragonhydra.local_ai.infer',side_effect=infer):
            explain(self.product,self.package)
        self.assertEqual(calls,['grounding','settings','inference'])

    def test_package_two_bytes_and_fallback_result_stay_exact_with_context_available(self):
        package = local_ai.build_package(self.product,self.match_id)
        self.assertEqual(local_ai.canonical(package),local_ai.canonical(self.package2_before_context))
        evidence,event = package['evidence']['E1'],package['event']
        with patch('dragonhydra.local_ai_service.Settings.effective',return_value=('',None)), \
             patch('dragonhydra.local_ai_service.now',return_value=CUTOFF), \
             patch('dragonhydra.local_ai.infer') as inference:
            result = explain(self.product,package)
        inference.assert_not_called()
        self.assertEqual(result,{'kind':'deterministic','summary':event['home']['name']+' vs '+event['away']['name'],
            'match_id':event['id'],'observations':[package['allowed_observations'][0]],
            'evidence':[{'id':evidence['id'],'url':'/dragon/api/v1/evidence/'+evidence['id'],'label':'Retained source record'}],
            'input_manifest':[evidence['id']],'package_sha256':package['package_sha256'],'cutoff':CUTOFF,
            'version':'local-source-fact/1',
            'unknowns':['Local inference was unavailable or rejected; this summary is deterministic.'],
            'local_ai':{'requested':True,'accepted':False,'code':'AI_NOT_CONFIGURED',
                        'message':'Local model endpoint and protected server key are not configured.'}})

    def test_package_two_accepted_result_keeps_original_fields_and_citation(self):
        package = local_ai.build_package(self.product,self.match_id)
        accepted = {**local_ai.validate_output(package,json.dumps({
            'observation':package['allowed_observations'][0],'evidence_alias':'E1'})),
            'runtime':{'local_endpoint':True}}
        with patch('dragonhydra.local_ai_service.Settings.effective',return_value=('http://127.0.0.1:12345',KEY)), \
             patch('dragonhydra.local_ai_service.now',return_value=CUTOFF), \
             patch('dragonhydra.local_ai.infer',return_value=accepted):
            result = explain(self.product,package)
        self.assertEqual(result['evidence'],self.expected_parent_citation())
        self.assertEqual(result['input_manifest'],[package['evidence']['E1']['id']])
        self.assertEqual(result['observations'],[accepted['observation']])
        self.assertEqual(set(result),{'kind','summary','match_id','observations','evidence','input_manifest',
            'package_sha256','cutoff','version','unknowns','mode','runtime','local_ai'})
        self.assertNotIn('fact_id',result)
        self.assertNotIn('evidence_aliases',result)


if __name__ == '__main__':
    unittest.main()
