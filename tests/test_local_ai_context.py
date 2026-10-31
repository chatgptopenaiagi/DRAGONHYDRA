"""Optional package/3 reconstruction, isolation and fact-ID-only selection."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from dragonhydra import local_ai, local_ai_context, source_context
from dragonhydra.connectors import research, statsbomb_context_parser as parser
import test_statsbomb_context as fixtures
import test_statsbomb_context_parser as native


class ContextPackageTests(unittest.TestCase):
    readonly = fixtures.StatsBombContextTests.readonly
    document = fixtures.StatsBombContextTests.document
    update = fixtures.StatsBombContextTests.update

    def setUp(self):
        native.BoundParserTests.setUp(self)
        self.match_id = self.product.present(local_ai._retained_row(
            self.product.evidence(self.observation_id)))['id']
        self.package2 = local_ai.build_package(self.product, self.match_id)
        self.record = source_context.append(self.path, self.payload, validate_dependencies=parser.make_validator(self.raw))
        self.package = local_ai.build_context_package(self.product, self.match_id, self.record['record_id'])

    @staticmethod
    def rehash(package):
        package.pop('package_sha256', None)
        package['package_sha256'] = hashlib.sha256(local_ai.canonical(package)).hexdigest()
        return package

    def test_default_package_bytes_prompt_output_unchanged_when_context_available(self):
        current = local_ai.build_package(self.product, self.match_id)
        self.assertEqual(local_ai.canonical(current), local_ai.canonical(self.package2))
        self.assertEqual(current['schema_version'], 'sports-evidence-package/2')
        self.assertEqual(local_ai.request_body(current), local_ai.request_body(self.package2))
        content = json.dumps({'observation':current['allowed_observations'][0], 'evidence_alias':'E1'})
        self.assertEqual(local_ai.validate_output(current, content), local_ai.validate_output(self.package2, content))

    def test_exact_context_adds_only_three_row_count_facts_and_no_source_arrays(self):
        self.assertEqual(self.package['context_summary'], {'event_rows':4, 'squad_sizes':[
            {'team_id':779, 'team_name':'Argentina', 'entries':1}, {'team_id':771, 'team_name':'France', 'entries':1}]})
        self.assertEqual(self.package['event'], self.package2['event'])
        self.assertEqual(self.package['evidence']['E1'], self.package2['evidence']['E1'])
        self.assertEqual(len(self.package['allowed_facts']), len(self.package2['allowed_observations'])+3)
        context = self.package['evidence']['C1']
        self.assertEqual(context['id'], self.record['record_id'])
        self.assertEqual(context['record_sha256'], self.record['record_content_hash'])
        self.assertEqual(context['documents'], self.payload['documents'])
        encoded = local_ai.canonical(self.package)
        self.assertLessEqual(len(encoded), 16*1024)
        for absent in (b'Argentina Player', b'stadium', b'"projection"', b'"original"', b'"lineup"', b'raw_reference'):
            self.assertNotIn(absent, encoded)

    def test_context_construction_and_queued_validation_use_no_product_db_helpers_or_writes(self):
        statements = []
        connect = source_context.sqlite3.connect
        def tracked(*args, **kwargs):
            self.assertIn('?mode=ro', args[0])
            db = connect(*args, **kwargs)
            db.set_trace_callback(statements.append)
            return db
        with (patch.object(self.product, 'connect', side_effect=AssertionError('product connection')),
                patch.object(self.product, 'find', side_effect=AssertionError('latest projection')),
                patch.object(self.product, 'evidence', side_effect=AssertionError('schema helper')),
                patch.object(source_context.sqlite3, 'connect', side_effect=tracked)):
            self.assertEqual(local_ai.build_context_package(self.product, self.match_id, self.record['record_id']), self.package)
            self.assertEqual(local_ai.validate_grounding(self.product, self.package), self.package)
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().upper().startswith(('SELECT', 'BEGIN', 'PRAGMA QUERY_ONLY=ON')) for sql in statements))

    def test_rehashed_plausible_counts_and_metadata_fail_exact_grounding(self):
        cases = []
        wrong = deepcopy(self.package); wrong['context_summary']['event_rows'] = 5
        wrong['allowed_facts'] = local_ai_context._facts(wrong['event'], wrong['context_summary']); cases.append(wrong)
        wrong = deepcopy(self.package); wrong['context_summary']['squad_sizes'][0]['entries'] = 2
        wrong['allowed_facts'] = local_ai_context._facts(wrong['event'], wrong['context_summary']); cases.append(wrong)
        for key, value in (('id', 'source_context:'+'0'*64), ('record_sha256', 'f'*64),
                           ('received_at', '2026-10-31T11:00:00Z')):
            wrong = deepcopy(self.package); wrong['evidence']['C1'][key] = value; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['evidence']['C1']['documents']['events']['id'] = 'other_receipt'; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['evidence']['C1']['documents']['events']['captured_at'] = '2026-10-30T10:00:00Z'; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['evidence']['E1']['id'] = 'f'*64
        wrong['evidence']['C1']['parent_observation_id'] = 'f'*64; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['event']['home']['name'] = 'Different'
        wrong['context_summary']['squad_sizes'][0]['team_name'] = 'Different'
        wrong['allowed_facts'] = local_ai_context._facts(wrong['event'], wrong['context_summary']); cases.append(wrong)
        for wrong in cases:
            with self.subTest(wrong=wrong['evidence']['C1']['id']), self.assertRaises(local_ai.LocalAIError) as caught:
                local_ai.validate_grounding(self.product, self.rehash(wrong))
            self.assertEqual(caught.exception.code, 'AI_EVIDENCE_MISMATCH')

    def test_strict_count_types_roles_clocks_and_shape_rejected_before_prompt(self):
        cases = []
        for number in (True, 4.0, -1, 20001):
            wrong = deepcopy(self.package); wrong['context_summary']['event_rows'] = number; cases.append(wrong)
        for number in (True, 1.0, -1, 101):
            wrong = deepcopy(self.package); wrong['context_summary']['squad_sizes'][0]['entries'] = number; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['context_summary']['squad_sizes'][0]['team_id'] = 779.0; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['context_summary']['squad_sizes'][1] = wrong['context_summary']['squad_sizes'][0]; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['evidence']['C1']['documents']['events']['provider'] = 'moneypuck'; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['evidence']['C1']['documents']['events'] = wrong['evidence']['C1']['documents']['lineups']; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['evidence']['C1']['received_at'] = '2026-10-31T10:00:00'; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['evidence']['C1']['documents']['events']['original_url'] = 'https://example.test'; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['evidence']['C1']['latest_url'] = '/mutable'; cases.append(wrong)
        wrong = deepcopy(self.package); wrong['event'] = []; cases.append(wrong)
        for wrong in cases:
            with self.subTest(case=cases.index(wrong)), self.assertRaises(local_ai.LocalAIError) as caught:
                local_ai.request_body(self.rehash(wrong))
            self.assertEqual(caught.exception.code, 'AI_PACKAGE_INVALID')

    def test_newer_match_revision_does_not_replace_queued_parent(self):
        newer = deepcopy(fixtures.MATCH); newer['home_score'] = 4
        document = self.document([newer], research.STATSBOMB_BASE+'matches/43/106.json')
        class RetainedOnly:
            def get(inner, url):
                return self.catalog if url.endswith('competitions.json') else document
        record = research._statsbomb({'competition_id':43, 'season_id':106}, RetainedOnly(), lambda:None)[0]
        self.store.ingest('statsbomb', [record], [self.catalog, document])
        self.assertEqual(local_ai.validate_grounding(self.product, self.package), self.package)
        with self.assertRaises(local_ai.LocalAIError) as caught:
            local_ai.build_context_package(self.product, self.match_id, self.record['record_id'])
        self.assertEqual(caught.exception.code, 'AI_CONTEXT_PARENT_MISMATCH')

    def test_later_equal_bytes_receipts_never_replace_original_bindings_or_hash(self):
        self.document(native.raw(native.EVENTS), self.payload['documents']['events']['original_url'])
        self.document(native.raw(native.LINEUPS), self.payload['documents']['lineups']['original_url'])
        rebuilt = local_ai.build_context_package(self.product, self.match_id, self.record['record_id'])
        self.assertEqual(local_ai.canonical(rebuilt), local_ai.canonical(self.package))

    def test_selected_source_loss_fails_without_substitution(self):
        (self.raw/(self.payload['documents']['events']['sha256']+'.payload')).unlink()
        with self.assertRaises(local_ai.LocalAIError) as caught:
            local_ai.validate_grounding(self.product, self.package)
        self.assertEqual(caught.exception.code, 'AI_EVIDENCE_MISMATCH')
        with self.assertRaises(local_ai.LocalAIError) as caught:
            local_ai.build_context_package(self.product, self.match_id, self.record['record_id'])
        self.assertEqual(caught.exception.code, 'AI_CONTEXT_UNAVAILABLE')

    def test_fact_output_only_accepts_ids_and_resolves_both_role_citations(self):
        fact = self.package['allowed_facts'][-3]
        accepted = local_ai.validate_output(self.package, json.dumps({'fact_id':fact['fact_id']}))
        self.assertEqual(accepted['observation'], fact['observation'])
        self.assertEqual(accepted['evidence_aliases'], ['E1', 'C1'])
        context = self.package['evidence']['C1']
        self.assertEqual(accepted['input_manifest'], [self.observation_id, self.record['record_id'],
            self.payload['documents']['events']['id'], self.payload['documents']['lineups']['id']])
        self.assertEqual(len(accepted['evidence']), 3)
        for role, citation in zip(source_context.ROLES, accepted['evidence'][1:]):
            self.assertEqual(citation['role'], role)
            self.assertEqual(citation['context_record_id'], context['id'])
            self.assertEqual(citation['context_record_sha256'], context['record_sha256'])
            self.assertEqual(citation['captured_at'], context['documents'][role]['captured_at'])
            self.assertIn('/connections/statsbomb/acquisitions/', citation['url'])
            self.assertNotIn('/source-context', citation['url'])
        accepted = local_ai.validate_output(self.package, '{"fact_id":"F1"}')
        self.assertEqual(len(accepted['evidence']), 1)
        self.assertEqual(accepted['input_manifest'][1], context['id'])

    def test_malformed_injected_and_unknown_model_selections_rejected(self):
        for content in ('null', '[]', '{}', '"F1"', '{"fact_id":1}', '{"fact_id":"F99"}',
                        '{"fact_id":"F1","fact_id":"F1"}', '{"fact_id":"F1","evidence_alias":"C1"}',
                        '{"fact_id":"F1"} extra', '{"observation":"4 rows","fact_id":"F1"}', '\ud800'):
            with self.subTest(content=repr(content)), self.assertRaises(local_ai.LocalAIError) as caught:
                local_ai.validate_output(self.package, content)
            self.assertEqual(caught.exception.code, 'AI_OUTPUT_REJECTED')

    def test_prompt_enum_has_no_identity_hashes_urls_or_citation_text(self):
        body = local_ai.request_body(self.package)
        self.assertEqual(body['json_schema']['properties']['fact_id']['enum'],
                         [fact['fact_id'] for fact in self.package['allowed_facts']])
        self.assertEqual(body['json_schema']['required'], ['fact_id'])
        self.assertFalse(body['json_schema']['additionalProperties'])
        for absent in (self.observation_id, self.record['record_id'], self.package['package_sha256'],
                       self.payload['documents']['events']['original_url']):
            self.assertNotIn(absent, body['prompt'])


if __name__ == '__main__':
    unittest.main()
