# Database roles

DRAGONHYDRA assigns ownership by workload. A technology being installed does not justify a second copy of every table. Adapters expose domain-level capabilities; SQL dialects, client classes and Joomla table names do not become the shared domain contract.

## Storage ownership

| Technology | Role | Owns | Does not own | Current status |
| --- | --- | --- | --- | --- |
| MariaDB | P1 operational relational state | Future source registry, current fixture/player/club projections, jobs, metadata, live state and transactional configuration | All historical analytics or GPU work | Existing XAMPP server at 3306; bounded adapter and controlled Joomla read proof verified alongside SQL Server. No DRAGONHYDRA production schema created. |
| DuckDB | P2 analytical memory and research SQL | Analytical views/queries, reproducible research joins and feature dataset selection | Concurrent transactional application ownership by default | Candidate; no new install/schema in genesis. |
| Parquet | P2 immutable or append-heavy datasets | Historical evidence/feature/event batches with schema and content manifests | Current transactional locks or job state | Planned file format; no production dataset written. |
| SQLite | Small isolated local utility state | A future narrowly justified cache/catalog/tool state | A duplicate operational system | Bundled Python capability only; persistent use deferred. |
| SQL Server 2022 | Optional structured enterprise adapter | Current synthetic DRAGONHYDRA_LAB sample; future structured workload only after explicit ownership decision | Automatic copies of MariaDB tables or unassigned production sports state | Enterprise 16.0.1200.5, default MSSQLSERVER instance at 1433; bounded Python 3.14 lab adapter measured. No production ownership or replication. |

An operational projection may point to immutable evidence version IDs. Analytical export is a deliberate one-way artifact with a manifest, not implicit replication. If synchronization is later needed, define source ownership, transaction/cutoff semantics, idempotency, lag and conflict behavior before implementation.

Every future dataset declares its role and authoritative owner:

| Ownership role | Required meaning |
| --- | --- |
| OPERATIONAL_OWNER | Engine that accepts authoritative transactional state changes for this dataset; MariaDB is the initial operational choice, and an independently justified structured SQL Server workload may have its own owner. |
| ANALYTICAL_OWNER | Authority for a reproducible analytical dataset/version, with source lineage and cutoff; DuckDB computation and versioned Parquet are candidates. |
| CACHE | Disposable acceleration state with an explicit origin, expiry and rebuild rule; never silently promoted to authority. |
| DERIVED_COPY | Deliberately materialized output with provenance, transformation version and refresh semantics; no implicit bidirectional synchronization. |
| ARCHIVE | Retained immutable history with retention, schema, integrity and replay rules; does not accept current-state writes. |

The same dataset must not acquire competing operational owners merely because two engines are available. The two current laboratory sources are separate: Joomla remains its application's dataset, and SQL Server holds only the new synthetic capability sample.

## Current adapter boundary

[storage/contracts.py](../src/dragonhydra/storage/contracts.py) preserves `AggregateReader.snapshot()` returning `AggregateSnapshot(source_id, measured_at, counts)`, plus `ReadOnlyPermissionProbe.verify_write_rejection()`. The dual phase adds frozen, validated `DatabaseEngineIdentity`, `DatabaseHealth`, `ReadOnlyQueryResult`, `ConnectionDiagnostic` and `CapabilityReport` contracts. [MariaDBAdapter](../src/dragonhydra/storage/mariadb.py) and [SQLServerAdapter](../src/dragonhydra/storage/sqlserver.py) expose fixed capability operations with engine/endpoint/driver identity, latency, transaction/read/write evidence and TLS state. These are narrow proof interfaces; they are not an ORM or a completed repository layer for every Pyramid entity. Neither adapter offers arbitrary SQL execution.

Future interfaces should follow concrete needs, such as source registry lookup, append evidence revision, fetch an as-of evidence set or open a versioned analytical dataset. Each interface must state consistency, transaction ownership, ordering, timestamp precision, resource lifetime and error behavior. A database-specific connection stays inside its adapter.

## Live Python 3.14 / MariaDB proof

[integration/mariadb_probe.py](../src/dragonhydra/integration/mariadb_probe.py) uses the configured loopback endpoint and `joomla_codex_lab` as a controlled source. It requests only table count, published content count, user count and extension count. Names, passwords and content bodies are not selected.

The dedicated identity is `dragonhydra_probe`. It must have SELECT only on this one database, with no grant option or write privilege. It does not reuse Joomla's writable application identity. The driver is project-local PyMySQL 1.2.3 under `runtime/vendor/pymysql-1.2.3`; [genesis.toml](../config/genesis.toml) stores only its version/location and the private credential-file path. [config.py](../src/dragonhydra/config.py) loads the credential from `runtime/secrets`, outside `htdocs`, and excludes the password from its representation.

Normal aggregate reads use a read-only transaction. Permission verification uses a separate normal transaction and a guaranteed zero-row `UPDATE ... SET id=id WHERE 1=0`. Expected result is MariaDB permission error 1142. This deliberately checks the account grant rather than allowing transaction read-only mode to mask excess privileges. Even unexpected acceptance changes no row, triggers rollback and is reported as failure. The adapter also checks privilege metadata and compares aggregate counts before/after; matching counts alone would not prove every row was untouched, so the zero-row SQL and grants remain the primary safeguards.

The probe result is structured JSON with endpoint, driver, aggregate counts, privilege summary and pass/fail flags. The [executed bridge checkpoint — curated summary](evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/bridge.json`) passed at `127.0.0.1:3306`: 76 tables, 0 published content rows, 1 user and 248 extensions. The zero-row write was rejected with 1142; grants were SELECT on the exact database plus global USAGE, with no table/column/role grants or grant option. Aggregate counts remained unchanged. Account identity was recorded without reading Joomla usernames or exposing authentication hashes. Final checkpoint references belong in [PROGRESS.md](PROGRESS.md). Joomla remains outside the product architecture after the proof.

## Live dual engine proof

Checkpoint [dual-database-20260924T163749Z-e9b792e6 — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/capabilities.json`) verifies both running engines and listeners together: MariaDB 10.4.32 at `127.0.0.1:3306`, SQL Server Enterprise 16.0.1200.5 at `127.0.0.1:1433`, Apache running and Joomla frontend HTTP 200. Both services were healthy before the task; no port conflict or engine startup failure was reproduced. No engine configuration or restart was needed. The configured client endpoints are loopback; existing wildcard server listeners remain and must not be misrepresented as loopback-only server bindings.

SQL Server's `dragonhydra_probe_sqlserver` identity accesses only the controlled `DRAGONHYDRA_LAB` operation. Explicit database grants are CONNECT and SELECT on `probe.CapabilitySample`; it has no added server/database roles or writable schemas. Default public metadata visibility is reported separately rather than hidden. Two synthetic rows produce quantity sum 30. An actual guaranteed zero-row UPDATE is rejected with native error 229; rollback completes and counts remain unchanged. This permission proof covers server privileges and the controlled database, not hypothetical future mappings elsewhere.

The SQL adapter loads hash-verified pyodbc 5.3.0 from `runtime/vendor/pyodbc-5.3.0` under the canonical interpreter and uses the already-installed Microsoft ODBC Driver 18 product version 18.6.2.1. Anaconda packages and the GPU stack were unchanged. Strict certificate validation initially failed with SQLSTATE 08001 because the chain was not trusted. The recorded TLS diagnosis (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-baseline-20260924T162756Z/tls-diagnostic.json`) distinguishes this client issue from an engine failure. `Encrypt=yes;TrustServerCertificate=yes` is an explicit loopback laboratory exception: traffic encryption was measured, server-certificate validation was bypassed. It is not a remote or production security policy.

[92 automated tests passed — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/tests.json`), with zero failures/errors/skips. [GPU regression — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/gpu-regression.json`) retained Python 3.14.7, NumPy 2.5.3, PyTorch 2.14.0+cu132, CUDA 13.2, cuDNN 9.24 and the RTX 3050, including numerical matrix agreement. This promotes SQL Server from an untested future adapter to a measured bounded laboratory adapter; production storage selection remains deferred.

Next scoped experiment: implement one typed router operation for a tiny MariaDB operational laboratory state and a different typed operation for a SQL Server structured laboratory workload. Each dataset declares one owner; no replication or production sports data is implied.

## Future evidence persistence

The in-memory Medusa ledger is not durable storage. A future persistence block must preserve packet/version identity, source/entity identity, assertion kind, all temporal evidence fields, proof references, validation reasons and supersession/conflict records. `target_as_of_at` belongs to a stored calculation/replay request, not an overwritten column on evidence.

Required properties before real data: append revisions; never backdate a correction; preserve queryable earlier versions; constrain linked entity/predicate/source scope; ensure crash/transaction behavior; make migrations explicit; and test round trips of timezone/precision/null values. Parquet manifests must identify schema version, content hash, row counts and availability boundaries. No schema or replicated pipeline is implemented by this document.
