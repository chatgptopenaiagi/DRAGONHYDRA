# Desktop / CLI data bridge v1

Desktop inspects public rendered pages and publishes explicit files. The command-line consumer validates those files, appends evidence to SQL Server and publishes a small MariaDB DTO for the existing localhost endpoint. This integration does not share browser sessions, authentication, live memory or private IPC.

The built-in browser is a Desktop surface. Its availability does not imply browser availability in standalone Codex CLI. The current [official browser documentation](https://learn.chatgpt.com/docs/browser?surface=app) expressly separates browser support from CLI/IDE and documents Windows Ctrl+Shift+B. It now describes the Desktop app hosting Codex; UI availability depends on installed app/workspace support. This boundary is not a defect in DRAGONHYDRA.

## Contract and ownership

Authoritative schema: `config/browser-handoff-envelope.schema.json`; Desktop copy: `runtime/handoff/schemas/browser-handoff-envelope.schema.json`. Runtime and published schema derive from `handoff/contracts.py`; tests check equality. Additional properties and unknown schema versions are rejected at every object level.

Producer values are codex-desktop, human-browser, python-fetch and test-fixture. Provenance is DESKTOP_CONFIRMED, MANUAL, CLI_FETCHED and SYNTHETIC respectively. A Desktop BLOCKED report is DESKTOP_BLOCKED, never a successful browser claim. Test-fixture is explicitly supported for the required synthetic verification and requires synthetic sources and labelled observations. Per-observation synthetic flags remain separate from capture origin, so synthetic odds within a genuine capture remain synthetic.

The envelope requires schema_version, canonical UUID handoff_id, producer, created_at, task, project_root, capture_method, status, sources, artifacts, observations, notes, reason, observed_failure and browser_evidence. Nullable fields remain present. All requested source/artifact/observation fields are required; observations additionally require `synthetic`. Values are bounded JSON scalars; future structured adapters need a new reviewed schema, not arbitrary extra fields.

| Classification | Owner |
|---|---|
| HANDOFF_RAW | Project filesystem / immutable checkpoint |
| STRUCTURED_INTELLIGENCE | SQL Server |
| WEB_PRESENTATION_CACHE | MariaDB |
| ANALYTICAL_DERIVED | Future DuckDB/Parquet; no writer implemented |

The consumer never executes artifact content, SQL strings, code or page instructions. Its Medusa-style validation consists of strict schema, source-policy, provenance, temporal and security gates before any structured insert. Unknown producer, unverified successful source, missing Desktop artifact evidence and unsafe input are rejected.

## Atomic protocol

Save the payload first into browser_downloads, then a draft into browser_notes. Run the publish helper; it validates the envelope and artifact bytes, writes/fsyncs a temporary file and atomically renames to `<UUID>.handoff.json`. Existing names are not overwritten. Direct final-file writers are also supported: the consumer checks size/mtime stability across 200 ms and around its bounded read, then rejects stable partial JSON.

```powershell
$env:PYTHONPATH='C:\xampp\DRAGONHYDRA\src'
& 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe' -m dragonhydra.handoff.publish --draft 'runtime/handoff/browser_notes/<UUID>.draft.json'
```

The consumer claims files via rename into processing under a single exclusive lock, reads/verifies again, archives exact accepted manifest/artifact bytes and processes a bounded batch. It skips `.tmp` files and recognizes legacy v0 manifests belonging to the earlier processor. Other unknown inbox files are quarantined into failed and receive rejection receipts. The consumer does not execute any file extension.

```powershell
& 'C:\xampp\DRAGONHYDRA\scripts\Run-HandoffOnce.ps1'
# Equivalent, with PYTHONPATH configured:
& 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe' -m dragonhydra handoff consume --once
```

The batch defaults to 10, hard maximum 25. It exits, with no permanent daemon. An interrupted run leaves processing evidence and possibly a lock. Inspect the abandoned claim/SQL receipt and verify no consumer is running before explicitly recovering the lock and requeuing the original filename; no automatic age-based stealing occurs.

## Persistence and replay

Five new tables exist in the existing dragonhydra schema: HandoffEnvelope, Source, Artifact, Observation, ProcessingReceipt. The new `dragonhydra_ingest_sqlserver` login has SELECT/INSERT only on those objects; `dragonhydra_bridge_read_sqlserver` has SELECT only. Existing probe and earlier web-ingestion accounts retain their original grants. SQL records keep envelope/source foreign keys, source times, availability/ingestion times, hashes, confidence and optional observation predecessor IDs.

The same handoff ID and exact manifest hash is a replay: no envelope/source/artifact/observation insert. A changed payload under an existing ID is rejected. Duplicate artifact hashes/paths and repeated observation payloads within an envelope are rejected. New handoff IDs represent new evidence even when a source value repeats. Observations append; an existing eligible source/entity/observation key supplies supersedes_id. The source rows are versioned by handoff, never overwritten.

SQL commits first. MariaDB receives only `desktop_cli_bridge` and the refreshed existing `intelligence` DTO in presentation_cache. No tables are replicated. There is no distributed transaction: cache/receipt failure after commit is explicitly reported with `sql_committed=true`; replay repairs publication without duplicating observations. Every attempt receives an immutable receipt, and SQL receives separate ingestion/final receipt phases for successful storage.

Receipts live in `runtime/handoff/receipts/<id>.receipt.json`. Later attempts use `<id>.<attempt>.receipt.json` rather than overwriting. Each contains exact manifest hash when safely bounded, artifact hashes, normalized payload hashes, Python/consumer versions, validation result, inserted SQL rows by table, MariaDB summary writes, rejected records, warnings and checkpoint path. Oversized inputs are rejected without reading beyond the cap; their full hash is unavailable rather than guessed. cli_outbox contains a small completion notice.

## Measured readiness

The synthetic envelope traversed the real filesystem, validator, dedicated SQL identity, MariaDB and HTTP endpoint. Replaying it inserted zero new observations. No actual Desktop browser research is claimed. A real Desktop task is now the next step, using CODEX_DESKTOP_HANDOFF_INSTRUCTIONS.md. Failure is a valid captured outcome: BLOCKED requires reason, observed_failure, URL-bearing source, and timestamps, and carries no observations.
