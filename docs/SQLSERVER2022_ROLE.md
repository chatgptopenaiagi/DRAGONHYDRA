# SQL Server 2022 role

SQL Server is an optional relational engine for explicitly assigned structured workloads. Availability alone does not make it the owner of every DRAGONHYDRA dataset.

## Discovery and diagnosis

| Property | Measured value |
| --- | --- |
| Service / instance | `MSSQLSERVER` / default instance |
| Instance ID | `MSSQL16.MSSQLSERVER` |
| Version / level | `16.0.1200.5` / RTM-GDR, KB5122771 in ERRORLOG |
| Edition / engine edition | Enterprise Edition (64-bit) / 3 |
| Collation | `SQL_Latin1_General_CP1_CI_AS` |
| Service account | `NT Service\MSSQLSERVER` |
| Initial state / startup | Running / Automatic |
| Initial PID | 13136 |
| TCP configuration | Enabled; static 1433; dynamic port field blank |
| Authentication | Existing mixed Windows/SQL authentication |

The diagnosis record (LOCAL EVIDENCE PATH: `runtime/checkpoints/sql-diagnosis-20260924T162551Z/diagnosis-summary.json`) establishes successful local TCP queries and ONLINE system/application databases before provisioning. Master, model, msdb and tempdb files were present in the instance's existing DATA directory. No system database recovery, service-account or engine port repair was justified.

The actual new-client failure was TLS certificate validation: an ODBC Driver 18 connection to the loopback endpoint rejected the existing untrusted certificate chain with SQLSTATE `08001`. With `Encrypt=yes;TrustServerCertificate=yes`, the administrative local connection succeeded and the server reported `encrypt_option=TRUE`. This is a bounded client configuration exception, not a repair of server startup. See [security boundaries](DATABASE_SECURITY_BOUNDARIES.md).

Repeated `18456`, state 5, messages name the missing `NT Service\SSISScaleOutMaster160` login. Historical PolyBase/Launchpad service failures and SPN warnings were also found. These remain separate existing subsystem issues; this block does not grant those services new access or restart them.

## Dedicated capability workload

Provisioning created `DRAGONHYDRA_LAB` after establishing that the database and proposed login did not already exist. Its files are under `runtime/sqlserver-lab`, with the required SQL service filesystem access. Existing database files were not relocated. The provisioning record (LOCAL EVIDENCE PATH: `runtime/checkpoints/sqlserver-provision-20260924T163241Z/provision.json`) records two synthetic rows and no overwritten objects.

The runtime identity is `dragonhydra_probe_sqlserver`. Its explicit grants are CONNECT to the laboratory and SELECT on `probe.CapabilitySample`, containing two synthetic rows. No fixed server/database roles or database-wide write grants were added. SQL Server's inherited public permissions require separate inspection; the intended application workload is restricted to the laboratory.

The first runtime proof (LOCAL EVIDENCE PATH: `runtime/checkpoints/sqlserver-provision-20260924T163241Z/bounded-connection.json`) connected with encryption, read two rows with quantity sum 30, and received UPDATE denial 229 with counts unchanged. Its overall health was nevertheless `unhealthy` because permission classification did not yet establish `bounded_identity`. This failed classification is retained. The validator was corrected to deduplicate equivalent SELECT permissions reported at object/column scopes and explicitly recognize inherited public metadata permissions. No grants were added to make the test pass.

The [final runtime proof — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/capabilities.json`) reports healthy and bounded_identity=true at `127.0.0.1:1433`. It confirms exactly the intended two direct grants, SELECT-only object permission, no elevated role memberships, no writable schemas and only `probe.CapabilitySample` visible as a user object. UPDATE was rejected with native error 229 in a normal transaction; counts stayed at two rows and quantity sum 30. The complete proof took 72.4702 ms. This permission proof covers server privileges and the controlled laboratory, not hypothetical future mappings in other databases.

[SQLServerAdapter](../src/dragonhydra/storage/sqlserver.py) uses fixed metadata and aggregate queries, reports database identity and driver/server version, checks the intended permission boundary, and performs a guaranteed zero-row write-rejection probe. No arbitrary SQL executor, replication, real sports dataset or enterprise ingestion is introduced.

## Future use

A separate synthetic structured workload is suitable for the next typed-router experiment. Production event/state ownership, SQL Server schemas and migrations require their own justification, transaction semantics and temporal tests. MariaDB and SQL Server must not maintain untracked authoritative copies of the same state. SQL Server's analytical features may be useful later, but they do not automatically displace DuckDB/Parquet research storage.
