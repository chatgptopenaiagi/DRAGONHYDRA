# Database security boundaries

Administrative setup and application runtime use different identities. A successful administrator connection is useful for diagnosis but cannot establish that a bounded adapter works.

## Identity and data boundaries

| Engine | Runtime identity | Authorized data | Allowed operation | Forbidden scope |
| --- | --- | --- | --- | --- |
| MariaDB | `dragonhydra_probe@localhost` | Existing controlled `joomla_codex_lab` database | Fixed aggregate SELECT and read-only permission proof | Writes, user/profile data disclosure, Joomla application credentials, unrelated databases |
| SQL Server | `dragonhydra_probe_sqlserver` | Dedicated `DRAGONHYDRA_LAB`, object `probe.CapabilitySample` | CONNECT and object-specific SELECT over synthetic rows | Fixed administrative roles, `db_owner`, general DDL/DML, unrelated application datasets |

SQL Server's provisioning record (LOCAL EVIDENCE PATH: `runtime/checkpoints/sqlserver-provision-20260924T163241Z/provision.json`) confirms creation of the identity/table and the two explicit grants. The [final effective-permission proof — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/capabilities.json`) confirms those exact grants, no elevated roles, zero writable schemas, and only the sample object visible as a user object. Inherited public permissions include CONNECT SQL, VIEW ANY DATABASE and column-encryption-key definition metadata visibility; they are explicitly classified rather than mistaken for data-write grants. The proof covers server privileges and `DRAGONHYDRA_LAB`; it makes no claim about future mappings to other databases. The laboratory contains synthetic values, with no copied Joomla or sports data. Existing databases and passwords were retained.

Adapters expose named proof operations rather than unrestricted SQL execution. Driver-specific connections, error handling and query text stay inside the adapter. Reported latency and capability status are non-secret. Reports must never contain passwords, authentication hashes, raw connection strings, result bodies from unrelated tables or environment dumps.

## Write-rejection proof

Each write probe uses a fixed zero-row UPDATE in a normal transaction. Its WHERE clause cannot match any row, even if the identity unexpectedly possesses a write grant. A read-only transaction would mask that grant, so the permission probe uses its own transaction and rolls back.

The final normal-transaction probes received MariaDB permission error 1142 and SQL Server UPDATE denial 229. Counts remained unchanged. Unexpected acceptance would be a failed boundary test, not permission success. Metadata checks independently examine effective permissions and privileged roles; count comparisons supplement the proof. No test deletes a database or changes unrelated data.

The first SQL permission classifier reported unhealthy despite the denied UPDATE because it did not correctly classify duplicate object/column SELECT entries and inherited metadata permissions. Its checkpoint is retained. Correcting the validator, without increasing privileges, produced the final healthy bounded result. The [92-test suite — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/tests.json`) passed with zero failures, errors or skips, including source/configuration/checkpoint secret checks.

## Secret and filesystem handling

Runtime secrets live only under `runtime/secrets`, outside `htdocs`, source, configuration and checkpoints. Configuration records secret locations. Files use restrictive Windows ACLs, and project ignore rules exclude secrets, downloaded wheels and runtime artifacts. Provisioning writes generated credentials directly to their private file without displaying them. A secret scanner checks authored source/configuration/checkpoints while reporting only file names and findings, never matched values.

SQL Server laboratory data/log files live under `runtime/sqlserver-lab`. The SQL service account receives only the path access required for those files; do not broaden ACLs on existing system database paths. Database binaries, data/log files and secrets are not source artifacts.

## Connection encryption and retained listeners

An observed ODBC 18 certificate-chain failure is addressed locally with `Encrypt=yes;TrustServerCertificate=yes`. This preserves encrypted transport but skips certificate validation. The exception is scoped to explicit loopback clients. A remote adapter must require validated trust and an appropriate certificate instead. [Microsoft's certificate trust guidance](https://learn.microsoft.com/en-us/troubleshoot/sql/database-engine/connect/certificate-chain-not-trusted?view=sql-server-ver16) explains the distinction.

The original SQL Server and MariaDB listeners were broader than loopback and remain unchanged to protect existing workloads. DRAGONHYDRA did not open firewall rules or add remote listeners. Local connection policy does not establish server-wide network isolation. Before any future remote use, inventory current clients, review firewall/binding policy, supply trusted TLS certificates, and assign a new explicit access scope.

MariaDB TLS status was not measured and remains explicitly unknown in the final diagnostic. SQL Server's runtime connection was encrypted, with certificate validation bypassed only for the configured loopback endpoint. Loopback routing and SELECT-only grants are independently measured boundaries.

## Remaining risks and next checks

The current Windows operator remains an administrator for provisioning; runtime probes must never inherit that authority through integrated authentication. Existing SSIS/PolyBase/Launchpad issues are separate and remain recorded. Certificate validation and listener narrowing need their own non-disruptive follow-up if the laboratory moves beyond loopback use. The next router experiment must use separate minimum write identities if required, leaving these read-only probes intact.
