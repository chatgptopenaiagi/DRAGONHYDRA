"""Probe package/3 preparation and assertions without any runner/API process."""
from contextlib import closing, redirect_stderr
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from dragonhydra import local_ai, source_context
from dragonhydra.connectors import statsbomb_context_parser as parser
from dragonhydra.connectors.core import Transport
from dragonhydra.product import Product
import test_statsbomb_context as fixtures
import test_statsbomb_context_parser as native


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('probe_local_ai_context_tested', ROOT/'scripts'/'probe_local_ai.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeContextTests(unittest.TestCase):
    readonly = fixtures.StatsBombContextTests.readonly
    document = fixtures.StatsBombContextTests.document
    update = fixtures.StatsBombContextTests.update

    def setUp(self):
        native.BoundParserTests.setUp(self)
        self.receipt = source_context.append(self.path, self.payload,
            validate_dependencies=parser.make_validator(self.raw))
        self.context_id = self.receipt['record_id']
        row = local_ai._retained_row(self.product.evidence(self.observation_id))
        self.match_id = self.product.present(row)['id']
        self.package2 = local_ai.build_package(self.product, self.match_id)
        self.package3 = local_ai.build_context_package(self.product, self.match_id, self.context_id)
        self.output = self.product.state/'probe-output'
        self.never_provider = patch.object(Transport, 'get', side_effect=AssertionError('provider forbidden'))
        self.never_process = patch.object(probe.subprocess, 'Popen', side_effect=AssertionError('process forbidden'))
        self.never_provider.start(); self.addCleanup(self.never_provider.stop)
        self.never_process.start(); self.addCleanup(self.never_process.stop)

    def argv(self, *extra):
        return ['--state', str(self.product.state), '--output', str(self.output), *extra]

    def test_argument_default2_and_api_browser_implication_unchanged(self):
        args = probe.arguments(self.argv())
        self.assertIsNone(args.context_record_id)
        self.assertFalse(args.verify_api)
        self.assertFalse(args.verify_browser)
        args = probe.arguments(self.argv('--verify-browser'))
        self.assertTrue(args.verify_browser)
        self.assertTrue(args.verify_api)

    def test_context_argument_requires_explicit_valid_identity_and_rejects_legacy_browser(self):
        cases = [('--context-record-id', self.context_id),
                 ('--context-record-id', 'source_context:'+'0'*63, '--match-id', self.match_id),
                 ('--context-record-id', self.context_id, '--match-id', 'wrong'),
                 ('--context-record-id', self.context_id, '--match-id', self.match_id, '--verify-browser')]
        for values in cases:
            with self.subTest(values=values), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                probe.arguments(self.argv(*values))
            self.assertEqual(error.exception.code, 2)
        self.assertFalse(self.output.exists())
        for flags in ((), ('--verify-api',)):
            args = probe.arguments(self.argv('--context-record-id', self.context_id,
                                            '--match-id', self.match_id, *flags))
            self.assertEqual(args.context_record_id, self.context_id)
            self.assertEqual(args.verify_api, bool(flags))

    def test_context_selection_uses_readonly_view_and_grounding_without_product_constructor(self):
        before = probe.source_fingerprint(self.product.state)
        statements = []
        original = sqlite3.connect
        def readonly(*args, **kwargs):
            self.assertEqual(args[0], self.path.as_uri()+'?mode=ro')
            self.assertTrue(kwargs.get('uri'))
            db = original(*args, **kwargs)
            db.set_trace_callback(statements.append)
            return db
        view = self.readonly_view()
        with (patch.object(probe, 'Product', side_effect=AssertionError('Product constructor')),
              patch.object(probe.sqlite3, 'connect', side_effect=readonly)):
            # Pure method bindings are explicit, even with constructors blocked.
            with patch.object(probe, 'readonly_product', return_value=view):
                match_id, package = probe.selected_package(self.product.state, self.match_id, self.context_id)
        self.assertEqual(match_id, self.match_id)
        self.assertEqual(package, self.package3)
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().upper().startswith(('SELECT', 'BEGIN', 'PRAGMA QUERY_ONLY=ON')) for sql in statements))
        self.assertEqual(probe.source_fingerprint(self.product.state), before)

    def readonly_view(self):
        return probe.readonly_product(self.product.state)

    def test_default2_selection_keeps_existing_constructor_and_package_path(self):
        with patch.object(probe, 'Product', return_value=self.product) as constructor:
            match_id, package = probe.selected_package(self.product.state, self.match_id)
        constructor.assert_called_once_with(self.product.state)
        self.assertEqual(match_id, self.match_id)
        self.assertEqual(local_ai.canonical(package), local_ai.canonical(self.package2))

    def backup(self):
        state = self.product.state/'isolated-api'
        state.mkdir()
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(state/'core.sqlite3')) as target:
                source.backup(target)
        return state

    def test_minimal_four_dependency_copy_preserves_receipts_clocks_and_grounding(self):
        before = probe.source_fingerprint(self.product.state)
        # This unrelated payload must never be copied by the four-role selector.
        unrelated = self.raw/('f'*64+'.payload')
        unrelated.write_bytes(b'unrelated raw file')
        before = probe.source_fingerprint(self.product.state)
        state = self.backup()
        with patch.object(probe, 'protect'):
            copied = probe.copy_context_dependencies(self.product.state, state, self.package3)
        self.assertEqual([row['role'] for row in copied], ['catalog', 'matches', 'events', 'lineups'])
        self.assertEqual(len(list((state/'raw'/'connectors').iterdir())), 4)
        for item in copied:
            body = (state/'raw'/'connectors'/(item['sha256']+'.payload')).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), item['sha256'])
            with closing(sqlite3.connect(state/'core.sqlite3')) as db:
                retained = db.execute('SELECT captured_at FROM connector_acquisitions WHERE id=?', (item['id'],)).fetchone()
            self.assertEqual(retained[0], item['captured_at'])
        self.assertEqual(local_ai.validate_grounding(probe.readonly_product(state), self.package3), self.package3)
        self.assertFalse((state/'workstation.json').exists())
        self.assertFalse((state/'local-session.json').exists())
        self.assertEqual(probe.source_fingerprint(self.product.state), before)

    def test_dependency_copy_rejects_missing_corrupt_raw_and_receipt_escape(self):
        role = self.payload['documents']['events']
        path = self.raw/(role['sha256']+'.payload')
        original = path.read_bytes()
        for failure in ('missing', 'corrupt', 'escape', 'oversize'):
            with self.subTest(failure=failure):
                state = self.product.state/('copy-'+failure)
                state.mkdir()
                with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)) as source:
                    with closing(sqlite3.connect(state/'core.sqlite3')) as target:
                        source.backup(target)
                        if failure == 'escape':
                            target.execute('UPDATE connector_acquisitions SET raw_reference=? WHERE id=?', ('../outside.payload', role['id']))
                        elif failure == 'oversize':
                            target.execute('UPDATE connector_acquisitions SET bytes=? WHERE id=?', (8*1024*1024+1, role['id']))
                        target.commit()
                if failure == 'missing':
                    path.unlink()
                elif failure == 'corrupt':
                    path.write_bytes(b'corrupt')
                try:
                    with patch.object(probe, 'protect'), self.assertRaises((ValueError, local_ai.LocalAIError)):
                        probe.copy_context_dependencies(self.product.state, state, self.package3)
                finally:
                    path.write_bytes(original)

    def test_dependency_copy_fails_if_exact_context_absent_and_refuses_reuse(self):
        state = self.backup()
        missing = deepcopy(self.package3)
        missing['evidence']['C1']['id'] = 'source_context:'+'0'*64
        with patch.object(probe, 'protect'), self.assertRaises(local_ai.LocalAIError) as error:
            probe.copy_context_dependencies(self.product.state, state, missing)
        self.assertEqual(error.exception.code, 'AI_CONTEXT_COPY_MISSING')
        with patch.object(probe, 'protect'), self.assertRaises(FileExistsError):
            probe.copy_context_dependencies(self.product.state, state, self.package3)

    def test_context_direct_and_worker_results_require_exact_fact_citations_and_full_manifest(self):
        for fact in self.package3['allowed_facts']:
            accepted = local_ai.validate_output(self.package3, json.dumps({'fact_id':fact['fact_id']}))
            self.assertEqual(probe.validate_context_result(self.package3, accepted), accepted)
            worker = dict(accepted, observations=[accepted['observation']])
            worker.pop('observation')
            self.assertEqual(probe.validate_context_result(self.package3, worker, worker=True), accepted)
            self.assertEqual(len(accepted['input_manifest']), 4)
            self.assertEqual(len(accepted['evidence']), 3 if 'C1' in fact['evidence_aliases'] else 1)
        fact = self.package3['allowed_facts'][-1]
        accepted = local_ai.validate_output(self.package3, json.dumps({'fact_id':fact['fact_id']}))
        for key, value in (('observation', 'invented'), ('package_sha256', 'f'*64),
                           ('match_id', 'e'*64),
                           ('evidence_aliases', ['E1']), ('evidence', accepted['evidence'][:1]),
                           ('input_manifest', accepted['input_manifest'][:1]), ('fact_id', 'F999')):
            changed = deepcopy(accepted); changed[key] = value
            with self.subTest(key=key), self.assertRaises(local_ai.LocalAIError):
                probe.validate_context_result(self.package3, changed)

    def test_invalid_context_fails_before_runner_check_or_start(self):
        argv = ['probe_local_ai.py', *self.argv('--context-record-id', 'source_context:'+'0'*64,
                                              '--match-id', self.match_id)]
        with (patch.object(probe.sys, 'argv', argv), patch.object(probe, 'protect'),
              patch.object(probe, 'private_directory'),
              patch.object(probe.subprocess, 'run', side_effect=AssertionError('runner version forbidden')),
              patch.object(probe.socket, 'socket', side_effect=AssertionError('network forbidden'))):
            self.assertEqual(probe.main(), 1)
        report = json.loads((self.output/'report.json').read_text())
        self.assertFalse(report['passed'])
        self.assertEqual(report['error']['code'], 'AI_CONTEXT_UNAVAILABLE')
        self.assertNotIn('runtime', report)
        self.assertTrue(report['source_unchanged'])
        self.assertTrue(report['temporary_key_removed'])


if __name__ == '__main__':
    unittest.main()
