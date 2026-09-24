# Dual database architecture

DRAGONHYDRA uses Python 3.14 to address MariaDB and SQL Server through separate, bounded adapters. The engines already coexisted when this block began. The work adds application access and evidence of isolation; it does not migrate Joomla, duplicate domain data, or establish replication.

## Measured starting point

The diagnosis checkpoint (LOCAL EVIDENCE PATH: `runtime/checkpoints/sql-diagnosis-20260924T162551Z/diagnosis-summary.json`) records MariaDB on TCP 3306 and SQL Server 2022 on static TCP 1433 at the same time. SQL Server's default instance `MSSQLSERVER` was Running, version `16.0.1200.5`, Enterprise Edition. All seven existing databases were ONLINE. Windows-integrated TCP queries succeeded. No current engine startup failure or shared-port conflict was found.

Seven available SQL ERRORLOG files each contained a successful startup. Existing SSIS Scale Out login failures and historical PolyBase/Launchpad interruptions concern optional subsystems. They are recorded, not represented as a MariaDB conflict. Historical evidence is bounded; it cannot establish that no earlier failure ever happened.

## Ownership and Pyramid layers

| Engine or format | Assigned role | Layer | Current workload |
| --- | --- | --- | --- |
| MariaDB | Operational relational owner for deliberately assigned web, source/job metadata and state workloads | P0/P1 | Read-only aggregates from the controlled Joomla laboratory |
| SQL Server 2022 | Optional owner for a separate structured integration or relational workload when justified | P1; other layers only by explicit decision | Dedicated laboratory with synthetic capability rows |
| DuckDB | Analytical execution and research joins over versioned inputs | P2/P3 | Architecture retained; no new installation in this block |
| Parquet | Versioned analytical files and durable historical batches | P2 | Architecture retained; no new dataset in this block |

Every future dataset declares exactly one authoritative owner. `OPERATIONAL_OWNER` maintains current transactional truth. `ANALYTICAL_OWNER` maintains a reproducible analytical dataset and its derivation. `CACHE` is disposable. `DERIVED_COPY` records provenance, cutoff and refresh policy. `ARCHIVE` retains immutable history under a retention policy. A database being available is not a reason to copy a dataset into it.

## Adapter boundary

[storage/contracts.py](../src/dragonhydra/storage/contracts.py) defines engine identity, health, read-only results, connection diagnostics and capability reports. [mariadb.py](../src/dragonhydra/storage/mariadb.py) and [sqlserver.py](../src/dragonhydra/storage/sqlserver.py) own driver-specific connections and fixed proof operations. No shared API accepts arbitrary SQL from callers.

Reports identify engine/version, configured endpoint, database, driver, connection status, measured latency, read/write capability and transaction support. Secret values and connection strings never belong in these reports. Transaction support means the engine/adapter can use a transaction; it does not grant permission to write. Health is measured with the runtime identity, separately from administrative provisioning.

Configuration refers to private credential files. Runtime access uses a different bounded identity for each engine. Administrative setup credentials are not runtime defaults. Joomla remains a controlled test source outside DRAGONHYDRA's product architecture.

## Verification and boundaries

The [completed capability checkpoint — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/capabilities.json`) independently proves both bounded runtime connections healthy. MariaDB returned 76 tables, zero published articles, one user and 248 extensions in a complete probe taking 173.3862 ms. SQL Server returned two synthetic rows with quantity sum 30 in a complete probe taking 72.4702 ms. These timings include permission checks and transactions; they are observations, not comparative database benchmarks.

Both database listeners and Apache were present simultaneously, and Joomla returned HTTP 200. [All 92 tests passed — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/tests.json`), with zero failures, errors or skips. The [GPU regression — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/gpu-regression.json`) retained the canonical stack and passed an actual RTX 3050 matrix calculation. Initial diagnosis and the first failed SQL permission classification remain separate historical evidence; the final proof did not require a server restart or a privilege increase.

Existing service/network settings remain in place because no repair is justified and existing applications have active connections. New DRAGONHYDRA endpoints are explicit loopback addresses. SQL Server's local certificate-trust exception and the retained broader server listeners are documented in [DATABASE_SECURITY_BOUNDARIES.md](DATABASE_SECURITY_BOUNDARIES.md).

## Next exact action

Both adapters now pass. The next block should design and implement one typed storage-router experiment: create a dedicated MariaDB laboratory operation for synthetic operational state and route a separate synthetic structured workload to SQL Server. Specify operation types, owner and least-privilege identities before provisioning. Preserve the current read-only probes; use a separate narrowly writable identity if the next experiment requires insertion. Demonstrate explicit selection and rejection of unsupported routes. Do not replicate records automatically or load production sports data.
