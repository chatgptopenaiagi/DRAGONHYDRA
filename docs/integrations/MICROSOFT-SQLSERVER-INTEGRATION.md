# Optional Microsoft SQL Server research repository

This is an unreleased feature checkpoint derived from frozen dev.6 source795f962.
It does not change the frozen source, sealed packages, installed workstations or
release gates. Current implementation is awaiting actual application SQL acceptance.

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

## Verification status

Unit and real-application results, source identity, actual database ownership,
transaction receipts and preservation checks will be recorded after execution in
`runtime/sqlserver-evidence`. Do not infer success from this implementation document.
