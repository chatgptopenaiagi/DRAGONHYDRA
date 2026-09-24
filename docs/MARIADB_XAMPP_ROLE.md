# MariaDB in XAMPP

MariaDB is the local relational component of XAMPP. It supports existing web applications and is the planned owner of selected DRAGONHYDRA operational state. Python performs numerical, analytical and GPU computation elsewhere in the Pyramid.

## Existing service preserved

The initial inspection found MariaDB `10.4.32` running as Windows service `mysql`, process `mysqld.exe`, PID 5496, listening on TCP 3306. The listener was not exclusive to loopback. DRAGONHYDRA connects to `127.0.0.1:3306`; this client choice must not be described as a server binding change. No port move, database reset, credential reset or MariaDB service restart is needed for coexistence with SQL Server on 1433.

The initial listener evidence (LOCAL EVIDENCE PATH: `runtime/checkpoints/sql-diagnosis-20260924T162551Z/simultaneous-listeners.json`) predates the integration changes. The [final capability checkpoint — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/capabilities.json`) confirms that both engines remain Running and listening simultaneously with the same PIDs and ports.

## Controlled read source

The probe uses `joomla_codex_lab` through `dragonhydra_probe@localhost`. This existing account has SELECT-only access to the controlled database. It does not reuse Joomla's writable application account and does not read user names, password hashes, article bodies or private profile fields.

The fixed result contains server version and aggregate counts: tables, published content, users and extensions. Both genesis and the independent final dual-database checkpoint measured 76 tables, zero published articles, one user and 248 extensions. The final complete MariaDB capability probe took 173.3862 ms and reported healthy, read=true, write=false, transaction=true and write_rejected=true.

[MariaDBAdapter](../src/dragonhydra/storage/mariadb.py) retains the proven PyMySQL implementation in [mariadb_probe.py](../src/dragonhydra/integration/mariadb_probe.py). It reports the complete proof latency, including its connection and permission checks. Driver `PyMySQL 1.2.3` stays project-local under `runtime/vendor/pymysql-1.2.3`.

## Permission and regression checks

Normal aggregate reads run in a read-only transaction. A separate normal transaction attempts a fixed `UPDATE ... SET id=id WHERE 1=0`. It cannot match a row. Expected permission error 1142 proves write rejection independently of transaction read-only mode. Unexpected acceptance is a failed permission test and is rolled back. Grant metadata and before/after aggregate comparisons provide additional evidence.

The final block verified MariaDB's service/listener and Joomla's frontend HTTP 200, including the Joomla marker and site name with no exposed PHP source. This exercises Apache, PHP, Joomla and its existing database configuration. Permission denial 1142 and unchanged aggregate counts passed. Joomla tables and application credentials were preserved. No MariaDB write laboratory was required for this block.

## Future ownership

Potential `OPERATIONAL_OWNER` datasets include source registry, ingestion-job metadata, version references and current-state projections. Evidence history and analytical extracts require explicit temporal semantics and provenance. DuckDB/Parquet retain their analytical roles; SQL Server receives only a separately justified workload. The next router experiment must create its own small synthetic operational dataset rather than turning the Joomla probe into application storage.
