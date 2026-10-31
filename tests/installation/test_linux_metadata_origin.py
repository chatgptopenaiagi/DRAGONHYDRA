"""Release metadata must distinguish embedded and externally verified origins."""
import hashlib
import copy
import json
from pathlib import Path
import runpy
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[2]
TOOLS = runpy.run_path(str(PROJECT/'packaging/linux-native/finalize_metadata.py'), run_name='metadata_origin_tests')
ORIGIN = TOOLS['application_origin']
CONTEXT = TOOLS['context_reader_summary']
AI = TOOLS['optional_ai_summary']


def canonical(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


class OriginTest(unittest.TestCase):
    def setUp(self):
        scratch = PROJECT/'runtime/scratch/metadata-origin-tests'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.previous_root = ORIGIN.__globals__['ROOT']
        ORIGIN.__globals__['ROOT'] = self.root
        self.prefix = self.root/'build/candidate/extracted/opt/dragonhydra/api'
        self.docs = self.prefix.parents[2]/'usr/share/doc/dragonhydra-api'
        self.docs.mkdir(parents=True)
        self.files = [{'path': 'src/dragonhydra/api.py', 'bytes': 1, 'sha256': 'a'*64},
                      {'path': 'src/dragonhydra/resources/web/app.js', 'bytes': 2, 'sha256': 'b'*64}]
        self.source = {'files': self.files + [{'path': 'README.md', 'bytes': 3, 'sha256': 'c'*64}]}
        self.build = {'base_source_content_sha256': canonical(self.source['files'])}
        self.origin = {'source_sha': None, 'files': self.files,
                       'content_sha256': canonical(self.files)}
        self.origin_path = self.docs/'A4-ORIGIN-SOURCE-MANIFEST.json'
        self.proof_path = self.root/'build/proof.json'
        self.proof = {'passed': True, 'source_content_sha256': self.build['base_source_content_sha256'],
                      'windows_application_origin': self.origin['content_sha256'],
                      'checks': {'identical_application_files': 2}}
        self.write(self.docs/'SOURCE-MANIFEST.json', self.source)
        self.write(self.origin_path, self.origin)
        self.write(self.proof_path, self.proof)

    def tearDown(self):
        ORIGIN.__globals__['ROOT'] = self.previous_root
        self.temp.cleanup()

    @staticmethod
    def write(path, doc):
        path.write_text(json.dumps(doc), encoding='utf-8')

    def test_embedded_origin_verified_with_resources(self):
        self.build['application_snapshot_sha256'] = self.origin['content_sha256']
        record, path = ORIGIN(self.build, self.prefix)
        self.assertTrue(record['origin_embedded_in_software'])
        self.assertEqual(record['application_file_count'], 2)
        self.assertEqual(path, self.origin_path)

    def test_external_origin_never_labelled_embedded(self):
        record, _ = ORIGIN(self.build, self.prefix, self.origin_path, self.proof_path)
        self.assertFalse(record['origin_embedded_in_software'])
        self.assertEqual(record['application_snapshot_sha256'], self.origin['content_sha256'])
        self.assertNotIn('application_snapshot_sha256', self.build)

    def test_direct_bundle_requires_comparison_proof(self):
        with self.assertRaisesRegex(ValueError, 'separately verified'):
            ORIGIN(self.build, self.prefix, self.origin_path)

    def test_changed_resource_rejects_false_complete_application_equivalence(self):
        self.origin['files'] = [dict(item) for item in self.files]
        self.origin['files'][1]['sha256'] = 'd'*64
        self.origin['content_sha256'] = canonical(self.origin['files'])
        self.write(self.origin_path, self.origin)
        with self.assertRaisesRegex(ValueError, 'Complete application bytes differ'):
            ORIGIN(self.build, self.prefix, self.origin_path, self.proof_path)

    def test_packaged_source_hash_must_match_candidate(self):
        self.build['base_source_content_sha256'] = 'e'*64
        with self.assertRaisesRegex(ValueError, 'Packaged base source identity'):
            ORIGIN(self.build, self.prefix, self.origin_path, self.proof_path)

    def test_origin_manifest_hash_must_validate(self):
        self.origin['content_sha256'] = 'f'*64
        self.write(self.origin_path, self.origin)
        with self.assertRaisesRegex(ValueError, 'manifest identity'):
            ORIGIN(self.build, self.prefix, self.origin_path, self.proof_path)

    def test_unrelated_or_failed_comparison_cannot_authorize_origin(self):
        for change in ({'passed': False}, {'source_content_sha256': 'e'*64},
                       {'windows_application_origin': 'f'*64},
                       {'checks': {'identical_application_files': 1}}):
            with self.subTest(change=change):
                self.write(self.proof_path, {**self.proof, **change})
                with self.assertRaisesRegex(ValueError, 'does not describe this candidate'):
                    ORIGIN(self.build, self.prefix, self.origin_path, self.proof_path)

    def test_embedded_hash_cannot_be_overridden_by_external_manifest(self):
        self.build['application_snapshot_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'Embedded application origin differs'):
            ORIGIN(self.build, self.prefix, self.origin_path, self.proof_path)

    def test_origin_outside_build_rejected(self):
        outside = self.root/'unrelated.json'
        self.write(outside, self.origin)
        with self.assertRaisesRegex(ValueError, 'project-local application origin'):
            ORIGIN(self.build, self.prefix, outside, self.proof_path)


class ContextScopeTest(unittest.TestCase):
    def setUp(self):
        self.build = {'source_content_sha256': 'a'*64}
        self.proof = {'passed': True, 'checks': [{'passed': True, 'availability': 'not_requested'}],
                      'effective_source_content_sha256': 'a'*64, 'fresh_provider_http': False,
                      'retained_replay': True, 'system_service_changes': False,
                      'process': {'exit_code': 0}, 'database_readonly': {
                          'identical_schema_and_counts': True, 'context_tables_before_after': []},
                      'retained_parent': {'inserted': 64, 'repeat_inserted': 0}}

    def test_reader_scope_never_promoted_to_context_ingestion(self):
        summary = CONTEXT(self.proof, self.build)
        self.assertEqual(summary['availability'], 'not_requested')
        self.assertEqual(summary['retained_parent_records'], 64)
        self.assertFalse(summary['fresh_provider_http'])
        self.assertIn('no event/lineup context ingestion', summary['qualification'])

    def test_another_binary_cannot_reuse_reader_proof(self):
        with self.assertRaises(ValueError):
            CONTEXT(self.proof, {'source_content_sha256': 'b'*64})

    def test_ddl_duplicates_or_live_fetch_cannot_be_reported_readonly_replay(self):
        for path, value in [(('database_readonly', 'identical_schema_and_counts'), False),
                            (('database_readonly', 'context_tables_before_after'), ['cognitive_records']),
                            (('retained_parent', 'repeat_inserted'), 1),
                            (('fresh_provider_http',), True), (('system_service_changes',), True),
                            (('process', 'exit_code'), 1)]:
            with self.subTest(path=path):
                changed = copy.deepcopy(self.proof)
                target = changed
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(ValueError):
                    CONTEXT(changed, self.build)


class OptionalAIScopeTest(unittest.TestCase):
    """Synthetic proof fixtures test the validator, not actual model execution."""
    def setUp(self):
        self.build = {'version': 'tested-r8', 'source_content_sha256': 'a'*64}
        finding = {'kind': 'local_llm', 'mode': 'constrained_source_fact_selection',
                   'evidence_id': 'e'*64, 'raw_sha256': 'b'*64}
        self.proof = {'passed': True, 'api_identity': {'debian_version': 'tested-r8',
            'source_content_sha256': 'a'*64}, 'checks': [{'passed': True} for _ in range(7)],
            'first': finding, 'after_restart': dict(finding), 'restored': {
                **{key: True for key in ('canonical_raw_pairing_base_config_equal',
                    'all_retained_tables_equal', 'connector_and_cognitive_included',
                    'disabled_key_configuration_hashes_equal', 'api_dropin_absent',
                    'key_retained_root0600', 'profile_retained')},
                'records': 760, 'ownership_enabled': False,
                'api_configuration': {'configured': False, 'endpoint': '', 'credential_source': 'none'},
                'model_state': {'ActiveState': 'inactive', 'UnitFileState': 'disabled', 'MainPID': '0'}}}

    def test_actual_profile_scope_does_not_claim_bundled_runtime_or_airgap(self):
        summary = AI(self.proof, self.build)
        self.assertEqual(summary['accepted_model_jobs'], 2)
        self.assertFalse(summary['runtime_or_model_or_controller_bundled_in_api_deb'])
        self.assertIn('Not a network-isolated test', summary['qualification'])

    def test_other_api_cannot_reuse_model_compatibility(self):
        for key, value in [('debian_version', 'r7'), ('source_content_sha256', 'c'*64)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.proof)
                changed['api_identity'][key] = value
                with self.assertRaises(ValueError):
                    AI(changed, self.build)

    def test_deterministic_fallback_is_not_model_acceptance(self):
        changed = copy.deepcopy(self.proof)
        changed['after_restart']['kind'] = 'deterministic'
        with self.assertRaises(ValueError):
            AI(changed, self.build)

    def test_data_or_credential_restore_failure_rejects_compatibility_gate(self):
        for key in ('all_retained_tables_equal', 'disabled_key_configuration_hashes_equal', 'api_dropin_absent'):
            with self.subTest(key=key):
                changed = copy.deepcopy(self.proof)
                changed['restored'][key] = False
                with self.assertRaises(ValueError):
                    AI(changed, self.build)


if __name__ == '__main__':
    unittest.main()
