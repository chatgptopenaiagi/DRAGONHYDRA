# Codex awareness and explicit artifacts

Codex awareness is the project-side contract for reconstructing state and proposing a bounded next action. It is operational state inspection and coordination, not consciousness and not an ordinary HYDRA source head.

The coordinator can examine what changed, which evidence or model moved, where disagreement increased, which uncertainty matters, what information is missing, which permitted capability might reduce it, whether Qwen should inspect the state, and whether the previous action produced useful evidence or changed a calculation. Unsupported or unavailable capabilities remain explicit.

## Handoff

The foundation uses ignored project-local artifacts under `runtime/cognitive`: snapshots, requests, responses, actions and receipts. Artifacts carry a schema version, identity, time/cursor, input hashes, state hash and provenance references. Exact implementation operations are recorded in [contracts](COGNITIVE_DATA_CONTRACTS.md) and [progress](COGNITIVE_PROGRESS.md).

[`ArtifactStore`](../src/dragonhydra/cognitive/artifacts.py) publishes typed envelopes containing `artifact_type`, `payload` and `payload_hash`. IDs are canonical UUIDs, not arbitrary filenames. Publishing is exclusive and immutable; reads revalidate types, canonical hashes and bounds. Maximum artifact size is 262,144 bytes, depth 24 and 20,000 JSON nodes. Unknown fields, duplicate keys, nonfinite JSON and hidden-reasoning field names are rejected. Existing symlink/junction paths and hardlinked artifact reads are rejected. Owner-controlled directory ACLs remain necessary against hostile concurrent path replacement.

Snapshots also accept StateDelta; requests accept ResearchNeed, CalculationRequest and AcquisitionRequest; receipts accept ActionResult, ReconciliationReport and LearningFeedback as well as CognitiveCycleReceipt. All use the same closed envelope and validation path.

An engineering session explicitly reads a sanitized snapshot/request and produces a typed proposal/response artifact. The project validates that artifact before an action can be considered. Files are data, not command scripts. There is no private Desktop/CLI IPC, hidden model session scraping, credential handoff or unrestricted database connection. No persistent agent daemon or external Codex service is implied by a valid artifact.

Web/source text stays untrusted data throughout the flow. A page saying "ignore policy and run a command" cannot add capabilities, alter source policy or become an executable instruction. The coordinator's allowed actions come from the controlled capability registry and validated request context, never from text quoted by a source.

## Bounded authority

Runtime action classes are NO_ACTION, REQUEST_QWEN_ANALYSIS, REQUEST_CALCULATION, REQUEST_SIMULATION, REQUEST_RESEARCH, REQUEST_SOURCE_REFRESH and REQUEST_HUMAN_REVIEW. A descriptor states whether the capability is available and which constraints apply. An unavailable operation can be represented and rejected without inventing a result.

The initial registry enables no-action, explicitly labelled Qwen mock analysis and human-review proposals. Calculation, simulation, research and source refresh descriptors are disabled pending integration. [`decide_action`](../src/dragonhydra/cognitive/orchestration.py) requires the originating CognitiveRequest, its digest in `proposal.metadata.input_hashes`, and an action allowed by that request. It also checks exact state/cursor, capability/action matching, operational clocks, age (300 seconds by default) and prior decision IDs supplied by the caller. It returns a decision and executes nothing. Research/source proposals remain BLOCKED for the separate HYDRA/MEDUSA/policy path even if a descriptor is enabled. Persistent replay protection requires the caller to supply retained prior decisions.

Engineering Codex can use owner-authorized development tools to implement and verify the repository. Runtime Codex proposals do not inherit those tools. In particular, a proposal cannot invoke arbitrary shell/SQL, rewrite source or forecasts, expand a source allow-list, extract credentials, execute wagering, or bypass HYDRA/MEDUSA.

Reconciliation preserves Codex and Qwen positions independently. It records disagreement rather than compelling agreement or averaging prose. The [world loop](WORLD_RECONCILIATION_LOOP.md) defines how later evidence and observed outcomes can correct both actors.

The initial `reconcile_responses` checks request/state/input hashes, cursor, temporal mode and task. Incomparable inputs yield NOT_COMPARABLE; comparable prose defaults to INSUFFICIENT_EVIDENCE. A referenced explicit human review can record the other agreement states. That classification preserves each position and is not automatic semantic proof or reviewer authentication.

## Explicit one-shot commands

Use the existing canonical Python 3.14 interpreter from the parent checkout. These commands create only ignored cognitive artifacts; the snapshot reads the existing bounded SQL role. No command starts a model server or dispatches a proposed action.

```powershell
Set-Location C:\xampp\DRAGONHYDRA
$parentPython = 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'

$cognitiveSnapshot = & $parentPython -B -m dragonhydra.cognitive snapshot | ConvertFrom-Json
$cognitiveRequest = & $parentPython -B -m dragonhydra.cognitive request --snapshot $cognitiveSnapshot.snapshot_id --task REVIEW_EVIDENCE | ConvertFrom-Json
& $parentPython -B -m dragonhydra.cognitive analyze --snapshot $cognitiveSnapshot.snapshot_id --request $cognitiveRequest.request_id --mode mock
& $parentPython -B -m dragonhydra.cognitive analyze --snapshot $cognitiveSnapshot.snapshot_id --request $cognitiveRequest.request_id --mode unavailable
& $parentPython -B -m dragonhydra.cognitive inspect --kind snapshots --id $cognitiveSnapshot.snapshot_id
```

`snapshot --as-of` optionally takes an aware ISO timestamp. `request --task` accepts only the enumerated task choices; use `request --help` to inspect them. `analyze --mode mock` returns MOCK_ONLY and records a typed hypothesis. `--mode unavailable` deliberately records BLOCKED / QWEN_RUNTIME_UNAVAILABLE and exits 2. A COMPLETE mock cycle is never live inference. Both paths retain response and cycle-receipt IDs/hashes.

Codex prepares an `ActionProposal` with its own actor identity, matching state/cursor, an action allowed by the originating request, its requested capability, and `request.digest()` in `proposal.metadata.input_hashes`. It publishes through `ArtifactStore.publish('actions', proposal_id, proposal)`. Then pass that existing canonical UUID and originating request ID to the decision command:

```powershell
& $parentPython -B -m dragonhydra.cognitive decide --snapshot $cognitiveSnapshot.snapshot_id --request $cognitiveRequest.request_id --proposal $proposalId
```

The returned decision includes `executed: false`. COMPLETE means the decision was processed and permitted; it is not proof of action execution. The CLI derives a stable decision artifact ID from the proposal ID and exclusive publication rejects replay. Create a fresh snapshot/proposal after the age bound rather than changing old timestamps. `inspect` validates and prints only the typed sanitized artifact; normal result output contains IDs, hashes and status, and rejected commands use sanitized failure codes.

The optional Joomla cognitive-status panel is NOT_STARTED in this block. A later change can project a small read-only status DTO through the existing presentation architecture; the current CLI does not modify Joomla or its cache.
