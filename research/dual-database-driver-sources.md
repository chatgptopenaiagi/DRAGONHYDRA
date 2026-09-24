# Dual database driver audit

Research date: 2026-09-24. This read-only audit recorded initial driver state before the parent task's installation and runtime tests. It made no package, service, registry or database changes. Evidence: driver-audit.json (LOCAL EVIDENCE PATH: `runtime/checkpoints/driver-audit-20260924T162719Z-5a6f1d6d/driver-audit.json`). Later dual-database runtime checkpoints determine the final operational state.

## Local observations

| Component | Initial observation | Meaning |
|---|---|---|
| Canonical interpreter | `C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe`, Python 3.14.7, 64-bit Anaconda | Use this interpreter for installation and execution; do not downgrade |
| CPython ABI | `cp314-win_amd64`; GIL enabled | Use the ordinary `cp314-cp314` Windows x64 wheel, not `cp314t` |
| NumPy / PyTorch | Metadata versions 2.5.3 / 2.14.0+cu132 | Baseline unchanged by this audit; the full mission reruns actual GPU computation |
| PyMySQL in canonical site-packages | Absent at initial audit | Does not imply the established project-local driver is absent |
| Existing project PyMySQL | Distribution version 1.2.3, imported successfully under Python 3.14.7 from `runtime/vendor/pymysql-1.2.3` | Reuse this tested minimal implementation |
| pyodbc in canonical site-packages | Absent at initial audit | A compatible wheel is required for the SQL Server adapter |
| Microsoft ODBC Driver 18 | Registered for 64-bit and 32-bit; 64-bit DLL at `C:\Windows\system32\msodbcsql18.dll`; product version 18.6.2.1 | Existing modern Windows driver can be used; no ODBC installer is needed for this proof |
| Older ODBC drivers | Driver 17 and legacy SQL Server also registered | Discovery only; prefer existing Driver 18 |

The installed ODBC DLL file version is `2018.0186.0002.01 ((DS_Main).170626-2112)`. Product version is a separate field and is the clearer runtime version identifier. Driver registration and DLL presence do not alone prove a successful SQL Server connection.

## Official compatible wheel

[PyPI's pyodbc 5.3.0 release](https://pypi.org/project/pyodbc/5.3.0/) publishes the ordinary CPython 3.14 Windows x64 wheel. The [version-specific JSON metadata](https://pypi.org/pypi/pyodbc/5.3.0/json) reports `Requires-Python >=3.9` and no mandatory Python distribution dependencies. This means installing the pinned wheel with dependency resolution disabled does not require NumPy, PyTorch, CUDA or cuDNN changes.

| Field | Verified value |
|---|---|
| Package | pyodbc |
| Version | 5.3.0 |
| Wheel | `pyodbc-5.3.0-cp314-cp314-win_amd64.whl` |
| Size | 72,177 bytes |
| Publisher upload time | 2025-10-17T18:03:57.296742Z |
| SHA256 | `58635a1cc859d5af3f878c85910e5d7228fe5c406d4571bffcdd281375a54b39` |
| Download | [Publisher-hosted wheel](https://files.pythonhosted.org/packages/b8/79/c48be07e8634f764662d7a279ac204f93d64172162dbf90f215e2398b0bd/pyodbc-5.3.0-cp314-cp314-win_amd64.whl) |
| Classification | PY314_NATIVE packaging; actual import/connection remains a separate runtime test |

Use the canonical interpreter, a hash-verified local wheel, and `--no-deps` for any approved install. Keep downloads, temporary data and installation records under the project. The chosen installation location must be described honestly: a package installed in `runtime/vendor` is project-local and is available to the canonical interpreter only when explicitly loaded; it is not installed into Anaconda site-packages.

PyMySQL 1.2.3 is already pinned and locally verified. Its local metadata requires Python >=3.9; cryptography and PyNaCl are optional authentication extras, not requirements of the existing MariaDB password flow. The official [PyMySQL package page](https://pypi.org/project/PyMySQL/) and [installation documentation](https://pymysql.readthedocs.io/en/latest/user/installation.html) are the upstream references. Do not add authentication extras without a measured need.

## Connection policy

The maintained [pyodbc Windows connection guide](https://github.com/mkleehammer/pyodbc/wiki/Connecting-to-SQL-Server-from-Windows) documents Windows and SQL authentication. The mission should use administrative identity only for bounded provisioning, then a separate minimal SQL login for runtime probes.

Microsoft documents that ODBC Driver 18 defaults to encrypted connections. `TrustServerCertificate=yes` skips server-certificate validation while encryption can remain enabled. If the local SQL Server uses its generated certificate, any such exception must be explicit, confined to the loopback laboratory configuration, and reported as a limitation. Prefer valid certificate verification for future remote/production adapters. [Microsoft connection keyword documentation](https://learn.microsoft.com/en-us/sql/connect/odbc/dsn-connection-string-attribute?view=sql-server-ver17)

Use explicit `tcp:127.0.0.1,<port>` connections. Static addressing avoids dependence on SQL Browser resolution. Keep secrets out of connection diagnostics and driver exception logs; ODBC connection strings must never be printed. Escape braces correctly when constructing an ODBC password value, or use a driver mechanism that handles connection-string values safely.

## Existing code worth preserving

- `integration/mariadb_probe.py` implements fixed controlled aggregates and an actual zero-row UPDATE permission rejection. A normal transaction is used for the denial test so transaction read-only mode cannot conceal excessive identity permissions. The write statement cannot change rows even if wrongly granted.
- MariaDB privilege diagnostics strip the authentication suffix from `SHOW GRANTS`; retain that protection. Unrestricted grant output can contain a password hash.
- `config.py` validates loopback hosts, the exact controlled Joomla database, bounded timeouts, secret paths under `runtime/secrets`, and a pinned project-local driver. Keep the existing genesis restrictions while adding separate SQL Server settings.
- `load_driver()` checks both distribution version and the loaded module's physical location. Installing PyMySQL into Anaconda alone will not change which implementation the existing bridge loads.
- `storage/contracts.py` already exposes `AggregateSnapshot`, `AggregateReader` and `ReadOnlyPermissionProbe`. Extend the contract without removing compatibility with existing genesis tests. No unrestricted SQL executor is necessary.
- `.gitignore` already excludes runtime secrets, vendor files, downloads, temporary files and checkpoints. Secret scanning should cover both credentials and the new checkpoint files; ignored files still require careful handling.

No Python, GPU, MariaDB or SQL Server behavior was declared repaired solely from this initial audit. The independently executed outcome is recorded below; initial observations remain intact as provenance.

## Executed dual database outcome

The parent task installed only hash-verified pyodbc 5.3.0 into `runtime/vendor/pyodbc-5.3.0`, documented by driver-install.json (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-baseline-20260924T162756Z/driver-install.json`). Canonical Anaconda site-packages were not modified. Both Python drivers are deliberately project-local and loaded by the canonical Python 3.14.7 interpreter. The pre-existing Microsoft ODBC Driver 18 installation was reused unchanged.

Both database engines were already running at baseline on different ports; no MariaDB/SQL Server port conflict or SQL Server startup failure was reproduced. The actual client failure observed was strict ODBC certificate validation: SQLSTATE 08001, untrusted issuer chain. TLS diagnostic evidence (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-baseline-20260924T162756Z/tls-diagnostic.json`) records successful encrypted TCP with the explicitly scoped loopback certificate-trust exception. No engine configuration or service restart was needed. Loopback client addressing does not change inherited wildcard listener bindings; those remain visible in the listener evidence.

The final [capabilities checkpoint — curated summary](../docs/evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/capabilities.json`), measured at 2026-09-24T16:37:51.568829+00:00, records:

- MariaDB 10.4.32 on `127.0.0.1:3306`, existing `dragonhydra_probe` SELECT-only proof: 76 tables, 0 published content, 1 user, 248 extensions. Actual zero-row UPDATE denied with 1142; counts unchanged. Reported 173.3862 ms measures the complete bounded proof, not query-only latency.
- SQL Server Enterprise Edition (64-bit) 16.0.1200.5, default MSSQLSERVER instance, on `127.0.0.1:1433`. `DRAGONHYDRA_LAB` contains two synthetic sample rows with quantity sum 30. Explicit grants for `dragonhydra_probe_sqlserver` are database CONNECT and SELECT on one sample object; no added server/database roles or writable schemas. Default public metadata permissions are retained in the evidence. Actual zero-row UPDATE denied with 229; rollback and unchanged counts verified. Reported 72.4702 ms covers connection, inspection, query, denial and rollback.
- pyodbc 5.3.0 imported and connected using existing ODBC Driver 18. Its native runtime version string is `18.06.0002`; the Windows DLL product version remains `18.6.2.1`.
- `Encrypt=yes` resulted in encrypted SQL Server TCP. `TrustServerCertificate=yes` deliberately bypassed certificate verification only in loopback lab configuration. MariaDB TLS state was not measured and is reported as unknown.
- MariaDB and SQL Server listeners existed simultaneously; both services and Apache were running. SQL Browser was stopped/disabled and explicit static-port connections worked without it. Joomla frontend returned HTTP 200 with expected markers and no exposed PHP source.

[92 tests passed — curated summary](../docs/evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/tests.json`), with zero failures/errors/skips. The [GPU regression checkpoint — curated summary](../docs/evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/gpu-regression.json`) retained Python 3.14.7, NumPy 2.5.3, PyTorch 2.14.0+cu132, CUDA 13.2, cuDNN 9.24 and NVIDIA GeForce RTX 3050. A 96x96 GPU matrix operation matched NumPy float64 with maximum absolute error 5.763398931435404e-06, below 1e-4; no CPU fallback was used.

pyodbc is now **PY314_NATIVE, measured for the bounded SQL Server adapter**. PyMySQL remains **PY314_COMPATIBLE, measured**. These outcomes do not establish untested SQL types, authentication methods, production workload suitability or throughput. SQL Server's role remains an optional separate structured workload; the laboratory proof assigns no production sports dataset and creates no automatic replication. Dataset ownership is governed by [DATABASE_ROLES.md](../docs/DATABASE_ROLES.md).
