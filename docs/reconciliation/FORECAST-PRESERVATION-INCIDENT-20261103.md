# Forecast preservation incident — 3 November 2026

**Forensic diagnosis and acceptance-harness repair verified; full Windows release
acceptance remains incomplete.** No application formula, production code, credential,
installed file or old operation receipt was changed. The held dev.5 packages do
not require rebuilding for this tooling repair.

## Target and evidence

Frozen application: `ed78fab282599a181d4254ab65a2fc2eaa5b7f50`, version
`0.5.0-dev.5`. Disposable profile:
`core-next-b447d99ab9524197af09c235077685de`; service
`DragonhydraCoreNextcandidatec235077685de` (LocalService).
The actual bindings are **API 18860, Joomla 18861, MariaDB 18862**. Profile,
configuration, Apache configuration, listeners and service ancestry agree. The
owner's supplied API/Joomla ordering was reversed. This investigation never
substituted the primary API18821/Joomla18822 or the original18740/18744 profile.

Private evidence root:
`C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\forensics\forecast-preservation-20261103`.
It has inheritance disabled and owner/SYSTEM/Administrators access only. Original
phase receipts, driver, locks, bindings and SQLite main/WAL/SHM files were copied
with before/after hash checks. Original snapshots actually reside under
`acceptance/workflow/private/`. They were never opened by SQLite during analysis;
each analysis used separate working copies. Raw databases remain outside Git.

| Original snapshot | Bytes | SHA-256 |
|---|---:|---|
| before-reads.sqlite3 | 1,040,384 | `0fbc6c70e5bd78db53f82ba75cabd841d4e85dba152b13d4e9881954610c2c48` |
| after-reads.sqlite3 | 3,043,328 | `b7c0c52c694f1ade073dee0589985853b9b881fe81dfcba14e973f345f46c187` |

The complete [manifest](evidence/forecast-preservation-20261103/FORENSIC-MANIFEST.json)
binds every original to its preserved copy. The historical Forecast receipt stays
`failed_reconciliation_required`, `DISPOSABLE_ACCEPTANCE_FAILED`, assertion
`preservation_snapshot`, code
`WORKFLOW_CHANGED_RETAINED_INPUTS_OR_PROVIDER_SETTINGS`. It has not been rerun,
rewritten or renamed PASS. InstallFresh and ReadFresh remain their actual earlier
passes. A live owner PowerShell process does not establish an active phase.
Other Codex process-to-file ownership was not inferable; root integrated only in
the separate `forensic/forecast-preservation-20261103` worktree. No other process
was terminated and no coordination product was introduced.

## Root cause: acceptance-harness defect (classification B)

The old helper, SHA
`47d5ffc472bbb0675ab8942c77fccb14e9a780e8f40acff2e397fe5e1c197f0b`,
lines529–538 compares every non-authentication table except four workflow tables
for complete equality. Its intended invariant is sound: forecasting must preserve
retained inputs and provider configuration. Its boundary is incorrect for the
first forecast on this fresh installation.

The real workflow resolves retained evidence through the existing market store.
Its first explicit write workflow creates four empty evidence tables, their
indexes and immutable triggers. Cognitive memory creates its two append-only
tables. The job system advances the `product_updates` AUTOINCREMENT sequence as
it appends the approved jobs' events. None of these is a provider acquisition.

Five domain entries violate the old comparison: `acquisitions`, `receipts`,
`quarantine`, `quarantine_receipts`, `sqlite_sequence`. Set iteration means the
historical generic error cannot identify which was tested first. The following
unreached schema assertion would additionally reject18 legitimate canonical
objects outside its cognitive-prefix allowance. Excluding only the sequence or
deleting the preservation assertion would leave an incomplete repair.

## Database comparison

Both databases pass integrity checks and have zero foreign-key violations. The
full sqlite_master definitions, columns, indexes and triggers were compared;
backup-file schema cookies were not treated as proof of matching schemas.

| Domain | Before → after | Classification |
|---|---|---|
| Retained fixtures | 760 → 760; identities, versions and all fields equal | UNCHANGED |
| Raw sources, including BLOB bytes | 2 → 2; all fields equal | UNCHANGED |
| Provider settings | 0 → 0; table definition equal | UNCHANGED |
| Eight configuration/pairing/provider file fingerprints | All equal | UNCHANGED |
| Existing jobs and events | All original rows equal | UNCHANGED |
| New forecast/evaluation jobs | +2 approved jobs | EXPECTED_WORKFLOW_MUTATION |
| New model/prediction history and receipts | +10 records (5+5), +10 receipts | EXPECTED_WORKFLOW_MUTATION |
| Job events | 6 → 14; eight events linked to the two approved jobs | EXPECTED_WORKFLOW_MUTATION |
| `sqlite_sequence.product_updates` | 6 → 14, matching event maximum | EXPECTED_WORKFLOW_MUTATION |
| Signed bridge read nonces | 7 → 14 | EXPECTED_AUTHENTICATION_BOOKKEEPING |
| Four new evidence tables | Empty | EXPECTED_FIRST_USE_SCHEMA |
| Schema | 17 → 23 tables; six tables, seven indexes, fourteen triggers added | EXPECTED_FIRST_USE_SCHEMA |

No existing schema object was deleted or replaced. No unexplained persisted
mutation was found. File growth follows legitimate persisted results and schema;
size alone was never used as an integrity test. Snapshot evidence does not prove
that no transient concurrent writer existed, and does not justify attributing
the failure to another session.

The [complete logical diff](evidence/forecast-preservation-20261103/SQLITE-LOGICAL-DIFF.json)
contains deterministic typed fingerprints and change counts, not private values.
An initial derived summary omitted counts for newly created tables; it remains
preserved privately. The final R2 report corrects that accounting. Original
evidence was not changed.

## Repair and adversarial checks

The new [auditor](../../tests/installation/workflow_preservation.py) accepts only
the exact27 canonical schema additions independently extracted from frozen-source
DDL, two explicitly approved job IDs, ten approved cognitive IDs and their
verified receipts. It binds payloads to the official job result, protects every
pre-existing row/schema object, validates the eight linked events and their exact
sequence advance, and requires new auxiliary tables to remain empty. Auth row
bookkeeping exemptions are limited to `product_sessions` and
`product_bridge_nonces`; their schemas remain protected. Profile, source,
configuration hashes and network inactivity remain separate caller gates.

The [30 new real-SQLite tests](../../tests/test_workflow_preservation.py) include
forbidden retained/provider/BLOB changes, unrelated jobs/events/schema, old memory
mutation, sequence gaps, partial schemas, receipt tampering and an actual WAL
writer. Expected records, repeat readback, row-order changes and page allocation
growth are accepted. Twenty-two existing eligibility/API/read-only-memory/registry
cases also pass: **52 distinct Python cases, 52 PASS, zero failures/errors/skips**.
No older overlapping suite was added to that total.

Reproduction commands from the isolated forensic source root, using the existing
`LAB\tools-env\Scripts\python.exe` and `PYTHONPATH=<source>\src`:

```powershell
python -B -m unittest discover -s tests -p test_workflow_preservation.py
python -B -m unittest discover -s tests/core_next -p test_workflow_eligibility.py
python -B -m unittest discover -s tests/core_next -p test_workflow_api.py
python -B -m unittest discover -s tests/core_next -p test_memory_readonly.py
python -B -m unittest discover -s tests/core_next -p test_registry_safety.py
```

The recorded focused run loads these same52 case IDs into one suite. Use a fresh
private LAB temporary directory; no tests target a live installation. The frozen
runtime reproduction's reviewed command/runner hashes and explicit requests are
preserved privately under `proposals/isolated-runtime-r1`, with its sanitized
receipt committed here. It is not the old one-shot Forecast command.

An independent new profile ran the exact frozen server executable. It reproduced
the old contract's false failure, while the repaired contract passed. Thirteen
runtime groups verified the five persisted outputs, exact duplicate job reuse,
honest pending evaluation, clean authenticated shutdown, process restart and
readback. Both owned server processes exited0. No service, Joomla, installer,
provider import or optional local-AI/LLM runtime was started by that reproduction. Its separate
jobs are `78df2e7464644862b8544430b3378119` and
`6fc419caa6a84cf89e8d4ad63fba531f`. This is application-process persistence, not
Windows service restart acceptance.

The original snapshot audit was also rerun using independent copies and the exact
integrated auditor. The earlier proposal-auditor receipt remains preserved; their
only code difference is the original-evidence safety docstring. A diagnostic
adapter initially passed the original grouped record-ID object instead of its
explicit model/prediction lists and failed closed. The corrected adapter flattened
only those ten approved IDs; no acceptance rule was weakened.

## Original workflow and installed readback

Retained match:
`de2c0fb3d3215eb157292f0941def2d44aa520a79db77dc73e40d13f88014aea`.
Original forecast: `9cbe1c2be77d46a49c692b5cb8bf8f2b`.
Original evaluation: `c4be90b6379d44309f9faeb696975b4f`.
Both durable jobs succeeded; evaluation's result is pending
`LATER_RETAINED_OUTCOME_UNAVAILABLE`. No outcome or evaluation record was invented.
There are four base models (Frequency, Poisson, Elo, Recency) plus an ensemble,
not five independently trained models. A separate read-only semantic audit of the
original snapshots verifies all50 retained inputs, source versions and actual
availability clocks against the original cutoff `2026-11-03T07:35:11.280781Z`.
The independent reproduction has its own later cutoff; its ordered input IDs,
complete manifests and all five probability vectors agree (actual Decimal delta0).
That agreement does not establish measured predictive accuracy. Decimal probabilities
are serialized as strings and normalize within1e-12. No measured accuracy claim.

Fresh GET-only API readback verifies those original IDs and the ten history IDs
without resubmitting them. Genuine normal Joomla login, authenticated component
navigation, formatted forecast values, session continuity, logout and anonymous
protection pass seven application groups. Credentials, cookies and raw HTML were
not saved. Joomla values match the associated backend, and configuration/domain
snapshots remain unchanged except permitted authentication bookkeeping. This is
actual HTTP application acceptance, not native desktop or default-browser proof.

At08:30:13Z, a further four GET-only registry reads leave the entire SQLite snapshot and nine
configuration fingerprints unchanged. Inventory remains six engines and twelve
supporting components. Prediction/evaluation operation proofs are expired or
unverified; evaluation remains pending. Memory's fresh bounded schema/count
observation is READY while its older read/write operation proofs are EXPIRED.
The detail view correctly calls those operations "Not currently verified".
The summary filter's label "Runtime status" actually filters the observation
state; this is a documented wording ambiguity, not proof of successful expired
operations. No status evidence was renewed by the page reads.

## Windows recovery and release boundary

The original one-shot Forecast remains failed. A new hash-bound reconciliation
operation must establish a fresh read-only predecessor before Backup. It must
never rerun Forecast or replace old receipts/locks. Backup must bind the same
profile and protect runtime, configuration, SQLite and a consistent dump of only
its MariaDB schemas. Restart/repair/uninstall/reinstall remain separate explicit
operations with fresh state and receipts, never an automatic loop.

The new implementation in
[`tests/installation/forecast_continuation`](../../tests/installation/forecast_continuation/README.md)
passes25 additional Python guards and six PowerShell groups. The exact three-file
hash-bound implementation passed independent static review. Its full live
ValidateOnly preflight passed without outputs. A distinct **ReconcileForecast
actually passed once**, receipt
`f5e22d7ec3b9bf2f2b903d259c76ef2e1978b8c37b72b77310614dfd1381cc9e`;
readback receipt
`247943b1a9459fc22343b139d6756d3f5e708862ac6a7803bc02a61861872eb0`.
All original jobs/history and the complete protected database/configuration baseline
remain equal. No Forecast submission branch exists in the new reader.

Only ReconcileForecast and Backup are implemented. Restart, Repair, UninstallRetain,
ReinstallRetained and FinalUninstall deliberately refuse before any marker and
require a separate reviewed continuation adapter. This is a partial lifecycle
milestone, not an all-phase installer acceptance claim.

| Windows phase | Actual scope/status |
|---|---|
| InstallFresh | PASS, original installer exit0 |
| ReadFresh | PASS, original installed acceptance |
| Forecast | Original FAIL preserved; separate forensic/repaired tests PASS |
| ReconcileForecast | PASS, distinct actual GET-only operation; original FAIL preserved |
| Backup | BLOCKED before phase; Windows elevation launch returned cancellation text |
| Restart | NOT_RUN for disposable SCM service; isolated server process restart PASS |
| Repair | NOT_RUN |
| UninstallRetain | NOT_RUN |
| ReinstallRetained | NOT_RUN |
| FinalUninstall | NOT_RUN |

Current shell is not elevated. One new specifically scoped Backup elevation request
was attempted at08:59:36Z and returned at09:01:39Z with
`InvalidOperationException`: "The operation was canceled by the user."
No elevated child handle, Backup marker or phase receipt was returned. This is the
observed Windows launch result, not proof of a particular human action or the cause
of the older dev.4 error. No automatic retry or alternate elevation transport was
used. The old native rejection was not retried or bypassed.
Native GUI/default-browser, full lifecycle, final installed privacy and required
release gates remain distinct. Dev.5 remains **held, unpublished**. No package was
relabeled, rebuilt, tagged or released by the forensic repair. The Windows Setup
hash remains `8d5a790ac54b4cca3c51d08746db80a5551c211474bcdead7dc86a44b3a8e553`.

Next command, **only from an already elevated PowerShell7 running as the matching
owner**, after inspecting the new operation and confirming no Backup marker or
receipt exists:

```powershell
$case = 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\forensics\forecast-preservation-20261103'
$driver = Join-Path $case 'source\tests\installation\forecast_continuation\Invoke-ReconciledDev5Phase.ps1'
$bindings = Join-Path $case 'continuation-authority-r1\CODE-BINDINGS.json'
& $driver -Phase Backup -Apply -BindingsPath $bindings -ExpectedBindingsSha256 ad0faf32895c9e2c42adf647506ec2891cdfa1481159d3d11f8af71f30f90e2c
```

The controller reads the successful new predecessor's attestation automatically.
This command does not request UAC, run Forecast, restore SQL or execute later
phases. A new terminal failure must be reconciled rather than retried. The exact
[continuation record](evidence/forecast-preservation-20261103/WINDOWS-ACCEPTANCE-CONTINUATION.json)
binds the current state and the failed elevation request.

Known-value source scanning compares51 locally protected values in UTF8, UTF16,
JSON, URL and Base64 forms and reports zero matches. It covers explicit task-owned
source and sanitized receipts, not every possible secret and not a new installed
or binary privacy acceptance. The generated scan receipt is excluded from its own
inputs; private source handoffs remain local. Production inputs under `src`,
`client`, `joomla`, `packaging` and `pyproject.toml` remain equal to frozen ed78.

## Performance and recovery scope

The independent runtime's recorded queue/run durations are approximately
0.182s/3.813s for forecasting and0.034s/0.092s for pending evaluation. Five warm
read-only audit samples on the same working copies have median0.079s,
range0.075–0.091s. The host has6physical/12logical cores and about68.0GB RAM.
These are bounded observations, not comparative speedup claims.

Rollback for this repair is limited to reverting the task-owned acceptance tools
and documentation on the forensic branch. There is no deployed application or
database repair to reverse. Never restore private snapshots over a live profile
or copy live MariaDB storage files as a backup. The original operation and its
failed evidence remain the predecessor history for the separate continuation.

Machine-readable findings and remaining gates are in
[ROOT-CAUSE.json](evidence/forecast-preservation-20261103/ROOT-CAUSE.json),
[REPAIR-VERIFICATION.json](evidence/forecast-preservation-20261103/REPAIR-VERIFICATION.json)
and the current continuation receipt linked by the active handoff.

All15 held assets were freshly rehashed against the held manifest. The nine
packages retain their original versions/provenance; complete filenames, byte
sizes, SHA-256 and separately dated installation/runtime scopes are recorded in
[PACKAGE-ACCEPTANCE-STATUS.json](evidence/forecast-preservation-20261103/PACKAGE-ACCEPTANCE-STATUS.json).
The exact source ZIP matches all775 Git files at ed78. Fresh authenticated GitHub
reads confirm all10 historical releases/95assets and14 tag-reference entries are
preserved. No dev.5 tag/release exists. Earlier baseline release bodies were not
hashed, so unchanged prose is not claimed. Nothing was uploaded by this audit.
