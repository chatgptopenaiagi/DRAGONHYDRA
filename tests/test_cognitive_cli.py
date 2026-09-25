from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from dragonhydra.cognitive import contracts as c
from dragonhydra.cognitive.__main__ import main
from dragonhydra.cognitive.artifacts import ArtifactStore
from dragonhydra.cognitive.orchestration import default_capabilities
from dragonhydra.cognitive.snapshot import build_snapshot
from dragonhydra.science.temporal import TemporalMode


class CognitiveCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 9, 25, tzinfo=timezone.utc)
        self.metadata = c.Metadata(created_at=self.now, as_of_at=self.now,
            temporal_mode=TemporalMode.STRICT_PIT,
            actor=c.ActorIdentity(actor_id='system', role=c.ActorRole.SYSTEM))
        self.snapshot = build_snapshot(metadata=self.metadata, capabilities=default_capabilities())
        self.snapshot_id = str(uuid4())
        ArtifactStore(self.root).publish('snapshots', self.snapshot_id, self.snapshot)

    def run_command(self, arguments):
        out = StringIO()
        with redirect_stdout(out):
            status = main(arguments, project_root=self.root, now=self.now)
        return status, json.loads(out.getvalue())

    def test_explicit_artifact_roundtrip_and_honest_mock_receipt(self):
        status, request = self.run_command(['request', '--snapshot', self.snapshot_id])
        self.assertEqual(status, 0)
        status, result = self.run_command(['analyze', '--snapshot', self.snapshot_id,
                                           '--request', request['request_id'], '--mode', 'mock'])
        self.assertEqual(status, 0)
        self.assertEqual(result['adapter_status'], 'MOCK_ONLY')
        response = ArtifactStore(self.root).read('responses', result['response_id'])
        receipt = ArtifactStore(self.root).read('receipts', result['receipt_id'])
        self.assertEqual(receipt.response_hashes, (response.digest(),))
        self.assertIs(response.conclusions[0].epistemic_state, c.EpistemicState.HYPOTHESIS)

    def test_live_unavailable_writes_failure_receipt(self):
        _, request = self.run_command(['request', '--snapshot', self.snapshot_id])
        status, result = self.run_command(['analyze', '--snapshot', self.snapshot_id,
                                           '--request', request['request_id'], '--mode', 'unavailable'])
        self.assertEqual(status, 2)
        self.assertEqual(result['adapter_status'], 'BLOCKED')
        receipt = ArtifactStore(self.root).read('receipts', result['receipt_id'])
        self.assertEqual(receipt.failure_state, 'QWEN_RUNTIME_UNAVAILABLE')

    def test_snapshot_command_uses_controlled_builder(self):
        with patch('dragonhydra.cognitive.__main__.build_parent_snapshot', return_value=self.snapshot) as builder:
            status, result = self.run_command(['snapshot'])
        self.assertEqual(status, 0)
        self.assertEqual(result['state_hash'], self.snapshot.state_hash)
        builder.assert_called_once_with(as_of_at=self.now, created_at=self.now,
                                        capabilities=default_capabilities())

    def test_codex_proposal_decision_never_executes_and_cli_replay_rejected(self):
        proposal_id = str(uuid4())
        _, request_result = self.run_command(['request', '--snapshot', self.snapshot_id])
        request = ArtifactStore(self.root).read('requests', request_result['request_id'])
        metadata = c.Metadata(created_at=self.now, as_of_at=self.now,
            temporal_mode=TemporalMode.STRICT_PIT,
            actor=c.ActorIdentity(actor_id='codex', role=c.ActorRole.CODEX),
            input_hashes=(request.digest(),))
        proposal = c.ActionProposal(metadata=metadata, proposal_id=proposal_id,
            state_hash=self.snapshot.state_hash, action=c.ActionClass.REQUEST_HUMAN_REVIEW,
            requested_capability='human-review-proposal', rationale_summary='Review missing data.')
        ArtifactStore(self.root).publish('actions', proposal_id, proposal)
        command = ['decide', '--snapshot', self.snapshot_id, '--proposal', proposal_id,
                   '--request', request_result['request_id']]
        status, decision = self.run_command(command)
        self.assertEqual(status, 0)
        self.assertTrue(decision['permitted'])
        self.assertFalse(decision['executed'])
        status, _ = self.run_command(command)
        self.assertEqual(status, 2)

    def test_invalid_artifact_path_fails_without_echo(self):
        status, result = self.run_command(['inspect', '--kind', 'responses', '--id', '../../secrets'])
        self.assertEqual(status, 2)
        self.assertNotIn('secrets', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
