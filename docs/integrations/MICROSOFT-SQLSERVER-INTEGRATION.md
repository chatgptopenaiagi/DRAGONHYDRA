# Optional Microsoft SQL Server research repository

This is an unreleased feature checkpoint derived from frozen dev.6 source795f962.
It does not change the frozen source, sealed packages, installed workstations or
release gates. Application SQL acceptance passed on November 4, 2026. This is a host source-run
feature, not a rebuilt or published dev.6 installer.

## Storage ownership

The current product uses SQLite for canonical retained source evidence, validated
cognitive records, authentication, provider configuration and durable jobs.
MariaDB serves Joomla accounts/content/configuration; its reserved sports schema
has not replaced SQLite. There is no implemented MariaDB sports-storage provider.

This increment adds one optional **secondary research repository**. Its provider
is explicitly selected as `sqlite` or `sqlserver`. It stores a distinct immutable
publication, linked to original forecast/model/input IDs, and versioned notes.
It does not turn SQL Server into the owner of existing source rows or silently
copy every record. The existing prediction workflow first persists its original
validated forecast. A separate authorized publication job archives that exact
stored result. Failure of publication cannot be reported as successful SQL
persistence and never redirects the operation to SQLite. Recovery reads the
stable archive ID before any insert. Original forecasts are not recomputed by
publication or readback.

The SQL transaction atomically stores an archive, models, predictions and input
snapshots. It is not a distributed transaction with the SQLite job queue. A
recovered job checks the immutable SQL identity/hash, allowing a SQL commit that
preceded a lost job acknowledgment to be read back without creating duplicates.

## Configuration and operations

Set `<profile-state>/kernel/research-storage.json` before starting a dedicated
profile. Missing configuration selects the optional SQLite archive, initialized
only by an explicit operation. See `config/research-storage.example.json`.
SQL uses Windows Integrated authentication, ODBC Driver18, mandatory encryption,
bounded connection/query timeouts and parameterized queries. The local lab's
explicit certificate-trust setting does not prove certificate-chain validation.
The actual SQL login is the application process's Windows identity; existing
LocalService installations have not been granted SQL access or reconfigured.

Authenticated API namespace: `/dragon/api/v1`.

- `GET /research/storage`: bounded, read-only diagnostic; no schema creation.
- `POST /research/storage/initialize`: explicit admin durable initialization job.
- `POST /matches/{id}/research/archives`: explicit admin publication job with
  `forecast_run_id`; it must identify an already complete retained forecast.
- `GET /research/archives/{id}`: read the selected repository directly.
- `GET /research/archives/{id}/match`: Data Engine read of the stored target snapshot.
- `GET /matches/{id}/research/archives`: bounded research history.
- `POST /research/notes`, `PUT /research/notes/{uuid}`: admin note creation and
  optimistic revision update with audit history.
- `GET /matches/{id}/research/notes`: scoped research notes.

All mutations retain the current authentication, admin and same-origin boundaries.
Configuration is server-side, contains no SQL password, and is not editable from
these browser operations. No arbitrary SQL or URL proxy is exposed.

## Schema and compatibility

Only initialization may create the configured database/schema. Existing databases
must have the exact product ownership marker and migration checksum; unrelated
databases are refused. Schema1 contains eight `dh_research_*` tables and nine
integrity/audit triggers. Identifiers are scoped and binary-collated; source/model
IDs retain their original values. Probability projections use DECIMAL(38,28),
with exact readback checks and original decimal text in canonical JSON. UTC clocks
use DATETIME2(7), hashes VARBINARY(32), note IDs UNIQUEIDENTIFIER, counts BIGINT,
synthetic flag BIT and sporting names/notes NVARCHAR. Source date precision is
preserved; no missing kickoff is invented. Original target snapshots are never
enriched with later scores during publication.

The `sqlserver` package extra pins pyodbc5.3.0. The application remains usable
without it when SQLite is selected. Windows Authentication in containers, guests,
Android or other service accounts is outside the current host verification scope.
No prediction-skill, new model, live conditional forecasting or AI claim is made.

## Executed acceptance — November 4, 2026

Implementation source: `03f52fbcffd774cabbb01bb9acc8373d952bf396`, branch
`feature/dragonhydra-sqlserver-20261104`, isolated worktree
`C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\sqlserver-integration-20261104`.
Later test/documentation commits are separate from that executed source identity.

SQL Server default instance `MSSQLSERVER` on `DESKTOP-44UK3UB` reported
16.0.1210.3 Enterprise Edition: Core-based Licensing (64-bit). The current
Windows user's source-run process used ODBC Driver 18.6.2.1 / pyodbc 5.3.0,
Windows authentication over `lpc:DESKTOP-44UK3UB`; the server reported encrypted
shared-memory transport with NTLM. TCP, guest, container and service-account
Windows authentication were not established by this test.

An authenticated application job created the previously absent
`DRAGONHYDRA_CORE_NEXT_SQL_LAB`. Schema version1 contains eight product-owned
tables and nine enabled integrity/audit triggers. A second explicit initializer
preserved every SQL row and DDL definition. Initialization is never a passive
health operation.

The new profile `core-next-254b30ff0a0242b8bc90bd2fe789fbeb` used API19006.
No Windows service was installed; its two source-run process lifetimes stopped
cleanly. Its state and SQL database remain available for readback.

| Verification scope | Actual result |
|---|---|
| Source/SQLite/API/driver-double/model regression | 156 distinct methods PASS; 0 failures/errors/skips; no real SQL calls |
| Actual authenticated application + SQL Server | 25 acceptance assertions PASS, including initialization, duplicate reuse, original forecast publication, typed SQL readback, source-preservation, notes, transactions and restart |
| Actual unavailable local SQL instance | 5 assertions PASS through the real driver and in-process API; sanitized 08001/HTTP503, original retained reads still work, no silent fallback |
| Existing SQL archive replay and immutable UPDATE | 3 assertions PASS against actual SQL; archive reused, rejected update and replay leave all68 SQL rows unchanged |
| Optional SQLite research archive | Actual old persisted forecast published/read back; repeat publication returns the same immutable archive |
| Native installer, GUI, VMware guest, Android SQL authentication | NOT_RUN; these are separate scopes |

Do not add these overlapping source and application assertions together as a
single unique software-test count. The original unsuccessful preflight and
first live attempt remain failed historical evidence. The preflight exposed a
new adapter's `Decimal(float)` conversion mismatch; using the existing memory
contract `Decimal(str(value))` fixed it without changing models or probabilities.
The first live attempt exposed a test-driver boolean bug. It stopped cleanly;
the initialization job was interrupted and a subsequent master-catalog query
confirmed no SQL database existed. That profile remains stopped. A fresh profile
and new one-shot acceptance identity produced the passing result; no uncertain
operation was blindly resubmitted.

### Traceable retained-data workflow

- Match: `de2c0fb3d3215eb157292f0941def2d44aa520a79db77dc73e40d13f88014aea`.
- Canonical forecast job/run: `3c7372ab4fd240e89a7898593db1533a`.
- SQL publication job: `b1da73082eb94ea3876bcb5c62264ba0`.
- SQL archive: `db1f5485749ecebfc019100e5ead5732699d1c9d99744cf1d7ad5de470d218e7`.
- Input cutoff: `2026-11-04T08:27:17.589916Z`; 50 original retained input references.
- Five outputs: Frequency, Poisson goals, Elo, Recency and ensemble;
  original model version `football-models/1`.
- Pending evaluation is preserved; no later eligible outcome or measured skill
  is manufactured by this archive.

Final SQL counts in this scope: owner1, migrations1, archives1, models5,
predictions5, inputs50, notes2, note_audit3. The forced division-by-zero test
returned SQLSTATE22012 with `uncertain_write=false`; its inserted note and
trigger audit were both absent after rollback. A committed Unicode note and its
audit survived reconnect and application restart. Stale note updates return409.
Passive reads and unauthorized requests changed neither domain SQL rows nor
canonical source/job/memory records within the test's declared authentication
bookkeeping exclusions.

### Evidence and reproduction

Private raw SQLite snapshots, source rows and detailed payloads stay under
`runtime/sqlserver-evidence`, outside version control and release inputs.
The sanitized machine summary is `docs/integrations/evidence/sqlserver-20261104.json`.

Actual SQL receipt: `runtime/sqlserver-evidence/live-r2/verification.json`, SHA256
`b8c43cdbebb25fd02f49e3c65ebd3e1d3ef2d30a17980e92b5252495222607d0`.
Source-test receipt: `runtime/sqlserver-evidence/final-unit-r2/verification.json`,
SHA256 `133defa40cfe117ba5fd9a71490707e3b9bc86d3def090fe8e5fe686e4686557`.

Use the existing isolated Python at `runtime/sqlserver-env/Scripts/python.exe`
and set `PYTHONPATH` to this checkout's `src`. Reuse of the original live plan is
intentionally refused: it is one-shot and hash-bound. Prepare a new isolated
profile and reviewed plan before another mutating acceptance run. The checked-in
`tests/integrations/sqlserver_acceptance.py` previews by default and requires
`--apply --expected-plan-sha256` for execution. Existing SQL databases must already
carry the exact ownership marker; this helper never drops a database.

For normal readback of the retained profile, run the existing server entrypoint:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& .\runtime\sqlserver-env\Scripts\python.exe -m dragonhydra.server --installation-profile 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles\core-next-254b30ff0a0242b8bc90bd2fe789fbeb\installation-profile.json'
```

Use the existing protected local pairing/session mechanism; never put its token
in a URL or public command. The authenticated diagnostic is
`http://127.0.0.1:19006/dragon/api/v1/research/storage` while that profile runs.
The generated build metadata identifies the executed feature source and explicitly
labels it an unreleased source build. Do not reuse this development launch as a
claim that the frozen dev.6 executable contains SQL support.

### Preservation and rollback

The original coherent760-record baseline is preserved in the forensic laboratory;
only its isolated copy was used. Seven old authentication bridge nonces were
explicitly cleared in that copy before the baseline. The first preparation's
premature main-file hash was reconciled against a fully closed SQLite snapshot;
all protected logical tables matched. Original evidence was not replaced.

All forecasting/cognitive/public-results/workflow source bytes remain equal to
frozen795. Existing Joomla/MariaDB schemas and services are not migrated to SQL.
No existing service identity, login or SQL permission was changed. Revert this
optional repository by stopping only its owning source-run profile and selecting
`sqlite` explicitly (or restoring its previous settings) before the next start.
Existing canonical forecasts remain readable. This does not migrate SQL archives
back to SQLite; each provider's data remains in its own explicit repository.
Retain the SQL database and profile for recovery; there is no automatic DROP or
uninstall action. Integration work is isolated on its feature branch, leaving the
original source branches, historical tags and sealed release packages unchanged.

### Remaining limits

This is a secondary research repository, not a replacement for the complete
SQLite sports/jobs/authentication store, and not a MariaDB sports adapter.
SQL Server health proves a bounded read, not successful forecast generation;
forecast publication success does not prove evaluation success. LocalService SQL
permissions, production certificate chains, native installer payloads and VM/mobile
Windows Authentication require separate verification before deployment in those
contexts. No public release is created by this integration increment.
