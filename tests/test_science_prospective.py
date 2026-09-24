"""Synthetic prospective receipts and raw bytes; acquisition is always mocked."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra.config import PROJECT_ROOT
from dragonhydra.science.prospective import (
    ProspectiveSnapshot, RawEvidenceStore, collect_once, validate_fixture_document,
)
from dragonhydra.web.contracts import PipelineError
from dragonhydra.web.provenance import digest, encode


class ProspectiveEvidenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=PROJECT_ROOT / 'runtime/tmp')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.url = 'https://example.org/synthetic-fixtures.json'
        self.source = {
            'policy_version': 'synthetic-policy-v1',
            'prospective': {
                'competition': 'Premier League', 'season': '2026/27',
                'document_name': 'English Premier League 2026/27',
                'interval_hours': 24, 'url': self.url,
            },
        }
        self.body = encode({
            'name': 'English Premier League 2026/27',
            'matches': [{'round': 'Synthetic round 1', 'date': '2026-09-26',
                         'team1': 'Synthetic Team A', 'team2': 'Synthetic Team B'}],
        })
        self.clock = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        self.evidence = {
            'retrieved_at': self.clock, 'content_hash': digest(self.body),
            'content_type': 'application/json', 'source_id': 'openfootball',
            'source_url': self.url, 'robots': {'robots_status': 'ALLOWED', 'synthetic': True},
        }
        sources_patch = patch('dragonhydra.science.prospective.load_sources',
                              return_value={'openfootball': self.source})
        policy_patch = patch('dragonhydra.science.prospective.allow_source')
        fetch_patch = patch('dragonhydra.science.prospective.fetch', return_value=(self.body, self.evidence))
        self.load = sources_patch.start()
        self.allow = policy_patch.start()
        self.fetch = fetch_patch.start()
        self.addCleanup(sources_patch.stop)
        self.addCleanup(policy_patch.stop)
        self.addCleanup(fetch_patch.stop)

    @property
    def ledger(self):
        return self.root / 'runtime/prospective/openfootball-en.1'

    def receipts(self):
        return {path.name: path.read_bytes() for path in self.ledger.glob('*.json')}

    def snapshot(self):
        return ProspectiveSnapshot(
            'a' * 32, 'synthetic', self.url, self.clock, self.clock, self.clock,
            digest(self.body), digest(self.body), len(self.body), 'application/json',
            'synthetic-parser-v1', 'synthetic-policy-v1', digest(encode(self.source)),
            'Premier League', '2026/27', 1,
        )

    def test_raw_store_deduplicates_and_detects_corruption_without_overwrite(self):
        store = RawEvidenceStore(self.root / 'raw')
        key = store.put(self.body)
        self.assertEqual(store.put(self.body), key)
        self.assertEqual(list(store.directory.iterdir()), [store.directory / key])
        self.assertEqual(store.get(key), self.body)
        path = store.directory / key
        path.write_bytes(b'synthetic corrupted bytes')
        for action in (lambda: store.get(key), lambda: store.put(self.body)):
            with self.assertRaisesRegex(ValueError, 'RAW_HASH_MISMATCH'):
                action()
        self.assertEqual(path.read_bytes(), b'synthetic corrupted bytes')

    def test_raw_store_rejects_unsafe_keys_empty_or_oversized_content(self):
        store = RawEvidenceStore(self.root / 'raw')
        for value in ('../../outside', 'A' * 64, 'not-a-hash'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'RAW_HASH_INVALID'):
                store.get(value)
        for body in (b'', 'not bytes', b'x' * 2_000_001):
            with self.assertRaisesRegex(ValueError, 'RAW_SIZE_INVALID'):
                store.put(body)
        self.assertFalse(store.directory.exists())

    def test_snapshot_preserves_strict_clock_and_hashes(self):
        snapshot = self.snapshot()
        result = json.loads(json.dumps(asdict(snapshot)))
        self.assertEqual(result['temporal_mode'], 'STRICT_PIT')
        self.assertEqual(result['observed_at'], self.clock)
        self.assertEqual(result['retrieved_at'], self.clock)
        self.assertEqual(result['content_hash'], result['raw_artifact_hash'])
        for changes in (
            {'available_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
            {'available_at': (datetime.fromisoformat(self.clock) - timedelta(seconds=1)).isoformat()},
            {'observed_at': datetime.now().replace(tzinfo=None).isoformat()},
            {'raw_artifact_hash': 'f' * 64}, {'source_policy_hash': 'invalid'},
            {'temporal_mode': 'RECONSTRUCTED_PIT'}, {'fixture_count': 0},
            {'fixture_count': True}, {'byte_count': True}, {'source_id': ' '},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(snapshot, **changes)

    def test_policy_rejection_happens_before_acquisition_and_is_durable(self):
        self.allow.side_effect = PipelineError('TERMS_UNVERIFIED')
        receipt = collect_once(self.root)
        self.assertEqual(receipt['status'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(receipt['reason'], 'TERMS_UNVERIFIED')
        self.fetch.assert_not_called()
        self.assertEqual(len(self.receipts()), 1)
        self.assertNotIn('snapshot', receipt)
        self.assertFalse((self.root / 'runtime/raw').exists())
        self.assertFalse((self.ledger / '.collector.lock').exists())

    def test_source_unavailable_receipt_does_not_invent_a_snapshot(self):
        self.source.pop('prospective')
        result = collect_once(self.root)
        self.assertEqual(result['status'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(result['reason'], 'SOURCE_UNAVAILABLE')
        self.allow.assert_not_called()
        self.fetch.assert_not_called()
        recorded = json.loads(next(iter(self.receipts().values())))
        self.assertEqual(recorded, result)
        self.assertNotIn('raw_artifact_hash', recorded)

    def test_success_appends_receipt_then_not_due_preserves_it(self):
        order = []
        self.allow.side_effect = lambda *args: order.append('policy')

        def fetched(*args):
            order.append('fetch')
            return self.body, self.evidence

        self.fetch.side_effect = fetched
        result = collect_once(self.root)
        self.assertEqual(result['status'], 'CAPTURED')
        self.assertEqual(order, ['policy', 'fetch'])
        snapshot = result['snapshot']
        self.assertEqual(snapshot['competition'], 'Premier League')
        self.assertEqual(snapshot['fixture_count'], 1)
        self.assertEqual(snapshot['temporal_mode'], 'STRICT_PIT')
        self.assertEqual(snapshot['observed_at'], self.clock)
        self.assertEqual(snapshot['raw_artifact_hash'], digest(self.body))
        self.assertEqual(RawEvidenceStore(self.root / 'runtime/raw').get(snapshot['raw_artifact_hash']), self.body)
        policy_path = self.ledger / 'policies' / (snapshot['source_policy_hash'] + '.json')
        self.assertEqual(digest(policy_path.read_bytes()), snapshot['source_policy_hash'])
        original_receipts = self.receipts()
        self.assertEqual(collect_once(self.root)['status'], 'NOT_DUE')
        self.assertEqual(collect_once(self.root, retry_failed=True)['status'], 'NOT_DUE')
        self.assertEqual(self.receipts(), original_receipts)
        self.assertEqual(self.fetch.call_count, 1)

    def test_schema_failure_retains_raw_bytes_and_acquisition_metadata(self):
        body = encode({'name': 'Wrong synthetic competition', 'matches': []})
        evidence = {**self.evidence, 'content_hash': digest(body)}
        self.fetch.return_value = body, evidence
        receipt = collect_once(self.root)
        self.assertEqual(receipt['status'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(receipt['reason'], 'SCHEMA_CHANGED')
        self.assertEqual(receipt['raw_artifact_hash'], digest(body))
        self.assertEqual(receipt['acquisition'], evidence)
        self.assertEqual(RawEvidenceStore(self.root / 'runtime/raw').get(digest(body)), body)
        self.assertNotIn('snapshot', receipt)

    def test_network_failure_records_controlled_reason_without_retry(self):
        self.fetch.side_effect = PipelineError('NETWORK_ERROR')
        result = collect_once(self.root)
        original = self.receipts()
        self.assertEqual(result['reason'], 'NETWORK_ERROR')
        self.assertEqual(collect_once(self.root)['status'], 'NOT_DUE')
        self.assertEqual(self.fetch.call_count, 1)
        self.assertEqual(self.receipts(), original)

    def test_manual_failed_retry_appends_and_maximum_is_two_attempts_per_day(self):
        self.fetch.side_effect = [PipelineError('NETWORK_ERROR'), (self.body, self.evidence)]
        first = collect_once(self.root)
        original = self.receipts()
        self.assertEqual(collect_once(self.root)['status'], 'NOT_DUE')
        second = collect_once(self.root, retry_failed=True)
        self.assertEqual(first['status'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(second['status'], 'CAPTURED')
        self.assertNotEqual(first['attempt_id'], second['attempt_id'])
        self.assertEqual(len(self.receipts()), 2)
        for filename, content in original.items():
            self.assertEqual(self.receipts()[filename], content)
        self.assertEqual(collect_once(self.root, retry_failed=True)['status'], 'NOT_DUE')
        self.assertEqual(self.fetch.call_count, 2)

    def test_second_failure_cannot_trigger_another_manual_retry(self):
        self.fetch.side_effect = PipelineError('NETWORK_ERROR')
        self.assertEqual(collect_once(self.root)['status'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(collect_once(self.root, retry_failed=True)['status'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(collect_once(self.root, retry_failed=True)['status'], 'NOT_DUE')
        self.assertEqual(self.fetch.call_count, 2)
        self.assertEqual(len(self.receipts()), 2)

    def test_next_day_appends_without_changing_earlier_receipt(self):
        self.ledger.mkdir(parents=True)
        older = {'attempt_id': 'a' * 32, 'status': 'SOURCE_UNAVAILABLE',
                 'reason': 'NETWORK_ERROR',
                 'attempted_at': (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()}
        path = self.ledger / ('a' * 32 + '.json')
        path.write_bytes(encode(older))
        original = path.read_bytes()
        self.assertEqual(collect_once(self.root)['status'], 'CAPTURED')
        self.assertEqual(len(self.receipts()), 2)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.fetch.call_count, 1)

    def test_operating_system_failure_records_type_without_message_content(self):
        self.fetch.side_effect = OSError('synthetic private diagnostic must not enter receipt')
        result = collect_once(self.root)
        self.assertEqual(result['status'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(result['reason'], 'OSError')
        self.assertNotIn('synthetic private diagnostic', json.dumps(result))

    def test_hash_mismatch_does_not_claim_verified_raw_or_snapshot(self):
        self.fetch.return_value = self.body, {**self.evidence, 'content_hash': 'f' * 64}
        result = collect_once(self.root)
        self.assertEqual(result['reason'], 'CONTENT_HASH_MISMATCH')
        self.assertNotIn('snapshot', result)
        self.assertNotIn('raw_artifact_hash', result)
        self.assertFalse((self.root / 'runtime/raw').exists())

    def test_existing_lock_blocks_acquisition_and_is_not_removed(self):
        self.ledger.mkdir(parents=True)
        lock = self.ledger / '.collector.lock'
        lock.write_text('synthetic incomplete attempt', encoding='utf-8')
        result = collect_once(self.root)
        self.assertEqual(result['status'], 'COLLECTOR_LOCKED')
        self.load.assert_not_called()
        self.fetch.assert_not_called()
        self.assertTrue(lock.exists())
        self.assertEqual(self.receipts(), {})

    def test_modified_policy_artifact_cannot_be_claimed_by_its_original_hash(self):
        policy_path = self.ledger / 'policies' / (digest(encode(self.source)) + '.json')
        policy_path.parent.mkdir(parents=True)
        policy_path.write_bytes(encode({'synthetic': 'tampered policy'}))
        original = policy_path.read_bytes()
        result = collect_once(self.root)
        self.assertEqual(result['status'], 'SOURCE_UNAVAILABLE')
        self.assertNotIn('snapshot', result)
        self.assertEqual(policy_path.read_bytes(), original)

    def test_fixture_shape_rejects_wrong_competition_and_invalid_rows(self):
        self.assertEqual(validate_fixture_document(self.body, 'English Premier League 2026/27'), 1)
        original = json.loads(self.body)
        invalid = [b'not json', encode([]), encode({**original, 'name': 'Other league'}),
                   encode({**original, 'matches': []}),
                   encode({**original, 'matches': [{**original['matches'][0], 'date': 'unknown'}]}),
                   encode({**original, 'matches': [{**original['matches'][0], 'team2': 'Synthetic Team A'}]})]
        for body in invalid:
            with self.subTest(body=body), self.assertRaisesRegex(PipelineError, 'SCHEMA_CHANGED'):
                validate_fixture_document(body, 'English Premier League 2026/27')


if __name__ == '__main__':
    unittest.main()
