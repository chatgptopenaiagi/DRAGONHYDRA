"""Explicit one-shot cognitive artifact CLI; no daemon or action dispatcher."""
from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from dragonhydra.config import PROJECT_ROOT
from . import contracts as c
from .adapters import MockQwenAdapter, UnavailableQwenAdapter
from .artifacts import ArtifactStore
from .orchestration import default_capabilities, decide_action
from .snapshot import build_parent_snapshot


def _metadata(snapshot, now):
    return c.Metadata(
        created_at=now, as_of_at=snapshot.metadata.as_of_at,
        temporal_mode=snapshot.metadata.temporal_mode,
        actor=c.ActorIdentity(actor_id='cognitive-artifact-cli', role=c.ActorRole.SYSTEM),
        source_refs=snapshot.metadata.source_refs, input_hashes=(snapshot.state_hash,),
        reason_codes=('EXPLICIT_ARTIFACT_HANDOFF',),
    )


def main(argv=None, *, project_root: Path = PROJECT_ROOT, now=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    snapshot_parser = commands.add_parser('snapshot', help='Read a fixed bounded parent view')
    snapshot_parser.add_argument('--as-of', help='Aware ISO cursor, default current UTC')
    request_parser = commands.add_parser('request', help='Publish an explicit bounded AI task')
    request_parser.add_argument('--snapshot', required=True)
    request_parser.add_argument('--task', choices=[t.value for t in c.TaskKind], default='REVIEW_EVIDENCE')
    analyze_parser = commands.add_parser('analyze', help='Mock or blocked-live Qwen adapter')
    analyze_parser.add_argument('--snapshot', required=True)
    analyze_parser.add_argument('--request', required=True)
    analyze_parser.add_argument('--mode', choices=('mock', 'unavailable'), required=True)
    decision_parser = commands.add_parser('decide', help='Decide a proposal without executing it')
    decision_parser.add_argument('--snapshot', required=True)
    decision_parser.add_argument('--proposal', required=True)
    decision_parser.add_argument('--request', required=True)
    inspect_parser = commands.add_parser('inspect', help='Validate and print a sanitized artifact')
    inspect_parser.add_argument('--kind', choices=('snapshots', 'requests', 'responses', 'actions', 'receipts'), required=True)
    inspect_parser.add_argument('--id', required=True)
    args = parser.parse_args(argv)
    clock = now if now is not None else datetime.now(timezone.utc)
    try:
        store = ArtifactStore(project_root)
        if args.command == 'inspect':
            artifact = store.read(args.kind, args.id)
            print(artifact.to_json())
            return 0
        if args.command == 'snapshot':
            cursor = datetime.fromisoformat(args.as_of) if args.as_of else clock
            snapshot = build_parent_snapshot(as_of_at=cursor, created_at=clock,
                                             capabilities=default_capabilities())
            artifact_id = str(uuid4())
            store.publish('snapshots', artifact_id, snapshot)
            result = dict(status='COMPLETE', snapshot_id=artifact_id,
                          state_hash=snapshot.state_hash, evidence_count=len(snapshot.evidence),
                          scope='BOUNDED_PARENT_VIEW', active_fixture=snapshot.fixture_id)
        else:
            snapshot = store.read('snapshots', args.snapshot, c.SystemStateSnapshot)
            metadata = _metadata(snapshot, clock)
            if args.command == 'request':
                artifact_id = str(uuid4())
                request = c.CognitiveRequest(
                    metadata=metadata, request_id=artifact_id, state_hash=snapshot.state_hash,
                    task=c.TaskKind(args.task),
                    allowed_actions=tuple(cap.action for cap in snapshot.capabilities if cap.enabled),
                )
                store.publish('requests', artifact_id, request)
                result = dict(status='COMPLETE', request_id=artifact_id, input_hash=request.digest())
            elif args.command == 'analyze':
                request = store.read('requests', args.request, c.CognitiveRequest)
                adapter = MockQwenAdapter() if args.mode == 'mock' else UnavailableQwenAdapter()
                response = adapter.analyze(snapshot, request)
                response_id, receipt_id = str(uuid4()), str(uuid4())
                store.publish('responses', response_id, response)
                receipt = c.CognitiveCycleReceipt(
                    metadata=metadata, cycle_id=receipt_id, state_hash=snapshot.state_hash,
                    request_hashes=(request.digest(),), response_hashes=(response.digest(),),
                    result_status=response.result_status, failure_state=response.failure_state,
                )
                store.publish('receipts', receipt_id, receipt)
                result = dict(status=response.result_status.value, adapter_status=adapter.status,
                              response_id=response_id, receipt_id=receipt_id,
                              output_hash=response.output_hash, failure_state=response.failure_state)
            else:
                proposal = store.read('actions', args.proposal, c.ActionProposal)
                request = store.read('requests', args.request, c.CognitiveRequest)
                decision = decide_action(snapshot, proposal, now=clock, request=request)
                # Stable ID + exclusive creation prevents CLI proposal replay.
                decision_id = str(uuid5(NAMESPACE_URL, 'dragonhydra:cognitive:decision:' + proposal.proposal_id))
                store.publish('actions', decision_id, decision)
                result = dict(status=decision.result_status.value, decision_id=decision_id,
                              permitted=decision.permitted, executed=False,
                              reason_codes=decision.reason_codes)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] == 'COMPLETE' else 2
    except (ValueError, TypeError, KeyError, OSError):
        # Never print exception text, input bytes, credentials or source prose.
        print(json.dumps({'status': 'BLOCKED', 'failure_state': 'COGNITIVE_COMMAND_REJECTED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
