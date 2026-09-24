# Python 3.14 database drivers

The canonical interpreter remains `C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe`. Python 3.14 executes both adapters. Driver loading is project-local so this block does not replace the environment's NumPy, PyTorch, CUDA or cuDNN packages.

| Component | Version | Source / location | Reason | Python 3.14 relation |
| --- | --- | --- | --- | --- |
| Python | 3.14.7 baseline | Existing `codex-pytorch` environment | Canonical orchestration runtime | Required 3.14.x; no downgrade |
| PyMySQL | 1.2.3 | Existing verified package under `runtime/vendor/pymysql-1.2.3` | Retain tested MariaDB protocol adapter | Proven by genesis; recheck live capability |
| pyodbc | 5.3.0 | Official PyPI distribution; hash-verified wheel under project-local `runtime/vendor/pyodbc-5.3.0` | Python interface to installed Microsoft ODBC driver | Python 3.14-compatible Windows wheel imported locally |
| Microsoft ODBC Driver 18 for SQL Server | 18.6.2.1 product version | Existing Windows driver installation | Modern SQL Server transport and encryption | Native external driver used by pyodbc; not a Python package |

The driver audit (LOCAL EVIDENCE PATH: `runtime/checkpoints/driver-audit-20260924T162719Z-5a6f1d6d/driver-audit.json`) and installation record (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-baseline-20260924T162756Z/driver-install.json`) retain exact discovery, source, wheel and digest evidence. No Microsoft ODBC installer or Conda package replacement was needed. Existing SQLCMD used ODBC 17 for an initial administrative read; the runtime SQL Server adapter deliberately selects ODBC Driver 18.

## TLS compatibility finding

The first ODBC 18 attempt requiring certificate validation failed with SQLSTATE `08001`, reporting an untrusted certificate chain. This is a certificate trust problem, not Python 3.14 incompatibility or a port collision.

The local adapter retains encryption and uses the explicit loopback-only development setting `Encrypt=yes;TrustServerCertificate=yes`. The successful administrative probe observed `encrypt_option=TRUE`; the independent [final runtime proof — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/capabilities.json`) also reports encrypted=true and certificate_validated=false. The trust setting skips server certificate validation. It does not prove server identity, and it must not become a default for remote endpoints. [Microsoft encryption troubleshooting](https://learn.microsoft.com/en-us/sql/connect/odbc/connection-troubleshooting?view=sql-server-ver16) describes this driver behavior.

## Loading and reproducibility

Launcher/configuration paths identify the intended interpreter and package directories. Do not silently fall back to a different Python or an unexpected system driver. Fail with a non-secret diagnostic if a required package, configured version, endpoint or ODBC driver is unavailable. Configuration contains locations and policy, while credentials remain in private files under `runtime/secrets`.

The [live GPU regression — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/gpu-regression.json`) passed with Python 3.14.7, NumPy 2.5.3, PyTorch 2.14.0+cu132, CUDA runtime 13.2, cuDNN 9.24 (encoded 92400), and the NVIDIA GeForce RTX 3050. A 96-by-96 matrix multiplication ran on CUDA and differed from the NumPy float64 reference by at most `5.763398931435404e-06`, within the `1e-4` tolerance. No CPU fallback was used. The [92-test suite — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/tests.json`) passed with zero failures, errors or skips. Conda and the compute packages were unchanged.

## Change rule

If a future driver lacks Python 3.14 support, investigate a maintained compatible version or isolate/replace the adapter. Never create Python 3.12 to conceal the conflict. Driver changes need a bounded connection/permission test and the same compute regression. SQL drivers do not justify changing PyTorch or the CUDA stack.
