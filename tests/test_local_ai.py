"""Offline package grounding and fail-closed local inference contracts."""
from contextlib import closing
from copy import deepcopy
import io
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from dragonhydra import local_ai, public_results
from dragonhydra.product import Product

ROOT = Path(__file__).resolve().parents[1]


class LocalAITests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / 'runtime' / 'scratch'
        directory.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=directory, prefix='local-ai-test-')
        self.addCleanup(temporary.cleanup)
        self.product = Product(Path(temporary.name))
        raw = json.dumps({'name': 'Test competition', 'matches': [
            {'date': '2026-10-31', 'team1': 'First', 'team2': 'Second'}]}).encode()
        with closing(self.product.connect()) as db:
            public_results.ingest_bytes(db, raw, source_id='synthetic-contract-test',
                                        source_url='https://example.test/fixture')
        self.match = self.product.matches()['items'][0]
        self.package = local_ai.build_package(self.product, self.match['id'])
        self.content = json.dumps({'observation': self.package['allowed_observations'][0], 'evidence_alias': 'E1'})

    def test_package_resolves_exact_retained_evidence_and_contains_no_credentials(self):
        self.assertEqual(self.package['evidence']['E1']['id'], self.match['evidence_id'])
        self.assertEqual(self.product.evidence(self.match['evidence_id'])['source_hash'],
                         self.package['evidence']['E1']['source_sha256'])
        self.assertEqual(local_ai.validate_package(self.package), self.package)
        self.assertNotIn('token', local_ai.canonical(self.package).decode())
        self.assertEqual(self.package['event']['status'], 'scheduled')

    def test_mutated_package_is_rejected(self):
        changed = deepcopy(self.package)
        changed['event']['home']['name'] = 'Different'
        with self.assertRaisesRegex(local_ai.LocalAIError, 'changed'):
            local_ai.validate_package(changed)

    def test_output_citation_is_resolved_by_application(self):
        result = local_ai.validate_output(self.package, self.content)
        self.assertEqual(result['evidence_id'], self.match['evidence_id'])
        self.assertEqual(result['match_id'], self.match['id'])
        self.assertEqual(result['mode'], 'constrained_source_fact_selection')
        self.assertIn('no new analysis', result['limitation'])

    def test_malformed_or_unsupported_output_is_rejected(self):
        cases = ['not JSON', 'null', '[]', '{}', self.content[:-1],
                 self.content.replace('E1', 'E２'), self.content.replace('scheduled', 'finished'),
                 self.content.replace('scheduled', 'scheduled with guaranteed winning odds'),
                 self.content[:-1] + ', "extra": "unexpected"}',
                 self.content[:-1] + ', "evidence_alias": "E1"}']
        for content in cases:
            with self.subTest(content=content), self.assertRaises(local_ai.LocalAIError):
                local_ai.validate_output(self.package, content)

    def test_request_uses_direct_schema_and_short_evidence_alias(self):
        body = local_ai.request_body(self.package)
        self.assertLessEqual(body['n_predict'], 192)
        self.assertNotIn(self.match['evidence_id'], body['prompt'])
        self.assertNotIn(self.match['id'], body['prompt'])
        self.assertNotIn(self.match['home']['id'], body['prompt'])
        self.assertEqual(body['json_schema']['properties']['evidence_alias']['const'], 'E1')
        self.assertEqual(body['json_schema']['properties']['observation']['enum'],
                         self.package['allowed_observations'])

    def test_remote_endpoints_and_invalid_keys_are_rejected_before_network(self):
        for url in ('https://127.0.0.1:1234', 'http://localhost:1234', 'http://192.168.1.1:1234',
                    'http://127.0.0.1:1234/proxy', 'http://user@127.0.0.1:1234', 'http://127.0.0.1',
                    'http://127.0.0.1:invalid', 'http://127.0.0.1:99999'):
            with self.subTest(url=url), self.assertRaises(local_ai.LocalAIError):
                local_ai.infer(self.package, url, 'test-local-secret-key-long-enough')
        with self.assertRaises(local_ai.LocalAIError):
            local_ai.infer(self.package, 'http://127.0.0.1:1234', 'bad')

    def test_inference_bounds_response_and_rejects_truncation(self):
        class Opener:
            def __init__(self, raw): self.raw = raw
            def open(self, request, timeout): return io.BytesIO(self.raw)
        for response in ({'content': self.content, 'stopped_limit': True},
                         {'content': self.content, 'truncated': True},
                         {'wrong': 'shape'}, [], None):
            with self.subTest(response=response), patch('dragonhydra.local_ai.build_opener',
                    return_value=Opener(json.dumps(response).encode())), self.assertRaises(local_ai.LocalAIError):
                local_ai.infer(self.package, 'http://127.0.0.1:1234', 'test-local-secret-key-long-enough')
        with patch('dragonhydra.local_ai.build_opener', return_value=Opener(b'x' * 65537)), self.assertRaises(local_ai.LocalAIError):
            local_ai.infer(self.package, 'http://127.0.0.1:1234', 'test-local-secret-key-long-enough')

    def test_inference_accepts_only_completed_supported_fact(self):
        response = io.BytesIO(json.dumps({'content': self.content, 'stop_type': 'eos', 'tokens_predicted': 32}).encode())
        with patch('dragonhydra.local_ai.build_opener') as opener:
            opener.return_value.open.return_value = response
            result = local_ai.infer(self.package, 'http://127.0.0.1:1234', 'test-local-secret-key-long-enough')
            self.assertEqual(result['evidence_id'], self.match['evidence_id'])
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:1234/completion')

    def test_network_and_auth_errors_expose_no_secret(self):
        for error in (TimeoutError('secret'), HTTPError('https://secret', 401, 'secret', {}, None)):
            with self.subTest(error=type(error).__name__), patch('dragonhydra.local_ai.build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(local_ai.LocalAIError) as caught:
                    local_ai.infer(self.package, 'http://127.0.0.1:1234', 'test-local-secret-key-long-enough')
                self.assertNotIn('secret', str(caught.exception))

    def test_local_redirects_are_rejected(self):
        self.assertIsNone(local_ai.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://outside.test'))

    def test_non_ascii_model_key_is_rejected_before_network(self):
        with patch('dragonhydra.local_ai.build_opener') as opener:
            with self.assertRaises(local_ai.LocalAIError) as caught:
                local_ai.infer(self.package, 'http://127.0.0.1:1234', 'test-local-key-with-nonascii-\u00e9')
            self.assertEqual(caught.exception.code, 'AI_KEY_INVALID')
            opener.assert_not_called()

    def test_rehashed_malformed_packages_are_rejected_before_request_construction(self):
        cases = [('event', 'home', None), ('event', 'competition', None),
                 ('event', 'time_precision', 'instant'), ('event', 'score', {'home': True, 'away': 0}),
                 ('event', 'kickoff_utc', '2026-10-31T12:00:00'),
                 ('evidence', 'source_url', 'https://user:secret@example.test/data'),
                 ('evidence', 'usable_at', '2026-10-31T12:00:00')]
        for group, field, value in cases:
            changed = deepcopy(self.package)
            target = changed['event'] if group == 'event' else changed['evidence']['E1']
            if value is None:
                target.pop(field)
            else:
                target[field] = value
            changed['package_sha256'] = hashlib.sha256(local_ai.canonical(
                {key: value for key, value in changed.items() if key != 'package_sha256'})).hexdigest()
            with self.subTest(group=group, field=field), self.assertRaises(local_ai.LocalAIError) as caught:
                local_ai.request_body(changed)
            self.assertEqual(caught.exception.code, 'AI_PACKAGE_INVALID')


if __name__ == '__main__':
    unittest.main()
