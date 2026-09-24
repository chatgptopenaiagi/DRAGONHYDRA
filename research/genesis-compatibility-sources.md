# Genesis compatibility evidence and sources

Research date: 2026-09-24. Local extended smoke timestamp: `2026-09-24T15:47:10.970590+00:00`. Work and writes remained under `C:\xampp`; the explicitly authorized canonical interpreter was invoked at `C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe`. No project search outside XAMPP was made. Node/Go/Java discovery used accessible commands, not a filesystem scan. This research did not install packages or alter configuration.

## Method and limits

1. Read installed distribution metadata using `importlib.metadata` in the canonical interpreter, then independently attempt each available import with `PYTHONDONTWRITEBYTECODE=1`.
2. Read current publisher-maintained PyPI project pages and their JSON metadata over HTTPS. Compare `Requires-Python`, classifiers and concrete Windows AMD64 wheel filenames. Universal wheels and ABI3 wheels are distinguished from version-specific cp314 wheels.
3. Run tiny, in-memory, harmless SymPy and SQLite operations. These are illustrative operation checks, not comprehensive engine validation.
4. Keep runtime results separate from published packaging support. Dependencies absent from this environment were not imported or benchmarked. Current PyPI releases are research candidates; they are not automatic upgrade instructions.

Initial local observations:

| Component | Observed value | Test scope |
|---|---|---|
| Python | 3.14.7, Anaconda, MSC v.1942 64 bit AMD64 | Executable/version read |
| GIL build | `Py_GIL_DISABLED=0` | `sysconfig` read; select ordinary cp314 wheels |
| NumPy | 2.5.3; requires Python >=3.12; metadata lists 3.14 | Import PASS |
| PyTorch | 2.14.0+cu132; requires Python >=3.10; metadata lists 3.14 | Import PASS; genesis runtime diagnostics own GPU proof |
| SymPy | 1.14.0; requires Python >=3.9; installed classifiers end at 3.13 | Import PASS; derivative of x squared is 2*x; roots of x squared minus 4 are -2 and 2 |
| SQLite | 3.53.4 | `:memory:` connection and `SELECT 6*7` returned 42 |
| Node.js | v26.8.1 | `node --version` |
| Go | go1.27.0 windows/amd64 | `go version` |
| Java | Temurin OpenJDK 21.0.12.1 LTS | `java -version` |
| Initially absent Python distributions | Polars, DuckDB, PyArrow, SciPy, statsmodels, scikit-learn, PyMySQL, mysql-connector-python, mariadb, pytest, PySide6 | `importlib.metadata.PackageNotFoundError`; not assumed system-wide absence |

## Official package evidence snapshot

URLs below were opened on the research date. Their JSON equivalents are `https://pypi.org/pypi/<project>/json`; version-specific records should be pinned when a candidate is selected. Metadata is publisher evidence and is not an execution test.

| Package/source | Candidate version | Python requirement | Observed suitable wheel evidence |
|---|---|---|---|
| [PyMySQL](https://pypi.org/project/PyMySQL/) | 1.2.3 | >=3.9 | `pymysql-1.2.3-py3-none-any.whl` |
| [Polars](https://pypi.org/project/polars/) | 1.44.2 | >=3.10 | `polars-1.44.2-py3-none-any.whl`; requires matching runtime |
| [Polars runtime](https://pypi.org/project/polars-runtime-32/) | 1.44.2 | >=3.10 | `polars_runtime_32-1.44.2-cp310-abi3-win_amd64.whl` |
| [DuckDB](https://pypi.org/project/duckdb/) | 1.5.5 | >=3.10.0 | `duckdb-1.5.5-cp314-cp314-win_amd64.whl` |
| [PyArrow](https://pypi.org/project/pyarrow/) | 25.0.1 | >=3.10 | `pyarrow-25.0.1-cp314-cp314-win_amd64.whl` |
| [SciPy](https://pypi.org/project/scipy/) | 1.18.1 | >=3.12 | `scipy-1.18.1-cp314-cp314-win_amd64.whl` |
| [SymPy](https://pypi.org/project/sympy/) | 1.14.0 | >=3.9 | `sympy-1.14.0-py3-none-any.whl` |
| [statsmodels](https://pypi.org/project/statsmodels/) | 0.15.0 | >=3.10 | `statsmodels-0.15.0-cp314-cp314-win_amd64.whl` |
| [scikit-learn](https://pypi.org/project/scikit-learn/) | 1.9.1 | >=3.11 | `scikit_learn-1.9.1-cp314-cp314-win_amd64.whl` |
| [MariaDB Connector/Python](https://pypi.org/project/mariadb/) | 1.1.14 | >=3.8 | `mariadb-1.1.14-cp314-cp314-win_amd64.whl` |
| [MySQL Connector/Python](https://pypi.org/project/mysql-connector-python/) | 26.7.0 | >=3.10 | `mysql_connector_python-26.7.0-cp314-cp314-win_amd64.whl`; universal alternative also present |
| [pytest](https://pypi.org/project/pytest/) | 9.1.1 | >=3.10 | `pytest-9.1.1-py3-none-any.whl`; 3.14 classifier |
| [PySide6](https://pypi.org/project/PySide6/) | 6.11.2 | >=3.10,<3.15 | `pyside6-6.11.2-cp310-abi3-win_amd64.whl`; 3.14 classifier |

DuckDB, PyArrow, SciPy, statsmodels, scikit-learn, mariadb and mysql-connector-python publish explicit Python 3.14 classifiers. Polars currently uses ABI3 packaging despite classifier listings ending at 3.13; that is a reason to run actual import/pipeline tests, not to downgrade Python. [CPython's Stable ABI documentation](https://docs.python.org/3.14/c-api/stable.html) explains why an earlier `cp310-abi3` wheel can be a candidate for a later CPython, while warning that ABI compatibility does not guarantee behavioral correctness.

SciPy 1.18.1 metadata constrains NumPy to `>=2.0.0,<2.8`, which includes installed NumPy 2.5.3. statsmodels also needs SciPy, pandas, patsy, packaging and formulaic; scikit-learn needs SciPy, joblib, narwhals and threadpoolctl. PySide6 requires matching shiboken6, Essentials and Addons. None of those transitive installation/runtime combinations was tested in this research.

## Minimal database driver decision

PyMySQL is preferred for the initial bounded query because its wheel is pure Python, its base install has no mandatory compiled dependency, and its [official installation documentation](https://pymysql.readthedocs.io/en/latest/user/installation.html) describes CPython >=3.9 and MariaDB >=10.3. The local server is 10.4.32. The current PyPI description instead refers broadly to MariaDB LTS versions; this difference is recorded rather than treated as proof of every server combination. The live connection and permission tests determine support for the actual local server.

The PyMySQL 1.2.3 wheel publisher SHA256 is `14f1c68e2ed859243ae5ca41ffbe677027fc46bc136a9f0be8a4e928e5e7415a`. Source: [release file metadata](https://pypi.org/project/PyMySQL/1.2.3/#files). Authentication with sha256/caching_sha2 or ed25519 can require optional cryptography/PyNaCl dependencies; this experiment should not install those extras without an actual authentication need. MariaDB Connector/Python has a suitable current Windows wheel and remains an alternative; the choice of PyMySQL is about the minimal proof surface, not a claim that the official connector is incompatible with Python 3.14.

The initial driver inventory was empty. Subsequent genesis checkpoint: the root agent installed the hash-verified PyMySQL 1.2.3 wheel only in `runtime/vendor/pymysql-1.2.3`, retaining its wheel and metadata under `runtime/downloads`. Installation used `--no-deps --no-compile --no-cache-dir --no-index` from the local verified wheel, with TEMP/TMP inside the project. The canonical Conda stack was unchanged. Initial observations remain historical evidence.

## First measured genesis checkpoint

Checkpoint `genesis-20260924T155516Z-ddf9f093` was inspected after execution. These results supersede the earlier pending runtime status, without changing the initial inventory evidence.

- [Diagnostics JSON — curated summary](../docs/evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/diagnostics.json`), checked at `2026-09-24T15:55:18.835674+00:00`: canonical Python 3.14.7, NumPy 2.5.3 and PyTorch 2.14.0+cu132; CUDA 13.2 available; cuDNN integer version 92400 available; NVIDIA GeForce RTX 3050, capability 8.6 and 6,441,795,584 bytes reported GPU memory. A 96x96 float32 CUDA matrix operation matched the independent NumPy float64 reference with maximum absolute error `5.763398931435404e-06`, below `1e-4`. No CPU fallback was used. Reported runtime includes transfers and is a smoke result, not a performance benchmark. cuDNN availability is verified; a convolution was not tested.
- [Bridge JSON — curated summary](../docs/evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/bridge.json`), checked at `2026-09-24T15:55:19.752312+00:00`: PyMySQL 1.2.3 connected to `127.0.0.1:3306`, reporting `10.4.32-MariaDB`. Aggregates: 76 tables, zero published content, one user, 248 extensions. Identity was `dragonhydra_probe@localhost`, with SELECT only on the exact Joomla database and global USAGE; zero table/column grants, no applicable or active roles, no grant option. A zero-row UPDATE was denied with error 1142 and aggregate counts were unchanged. No identities or passwords were returned in the aggregate result.
- [Tests JSON — curated summary](../docs/evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/tests.json`), checked at `2026-09-24T15:55:23.183114+00:00`: 43 tests run and passed; zero failures, errors or skips. The recorded suite covers canonical compute, configuration boundaries/secrets, six-timestamp evidence, future-information exclusion, supersession/conflict replay, live read-only database behavior and small math-contract validation.

PyMySQL is therefore promoted from packaging candidate to **PY314_COMPATIBLE, measured, KEEP project-local**. Its bounded query proof does not certify untested authentication plugins, SQL features or workload performance. Deferred analytical packages remain packaging-only candidates, and no new environment upgrade follows from this checkpoint.

The final [genesis-20260924T155954Z-3065e1ef checkpoint — curated summary](../docs/evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155954Z-3065e1ef/checkpoint.json`) revalidated compute and database results after contract hardening. Its [test report — curated summary](../docs/evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155954Z-3065e1ef/tests.json`) records **53 passed, zero failures/errors/skips**, including additional immutable math-payload and explicit CPU-fallback tests. The first checkpoint is preserved as historical evidence.

## GPU/platform boundary

The [official Polars GPU guide](https://docs.pola.rs/user-guide/gpu-support/) lists Linux or WSL2, NVIDIA compute capability 7.0+ and CUDA 12 or 13. The ordinary `polars[gpu]` extra currently resolves to the CUDA 12 cuDF package; CUDA 13 is a separate dependency choice. Native Windows CPU Polars is therefore a candidate; native Windows Polars GPU is not established by the available CPU wheel or by successful PyTorch CUDA operations. No RAPIDS, WSL2 or CUDA changes were performed.

The [NVIDIA CUDA compatibility guide](https://docs.nvidia.com/deploy/cuda-compatibility/latest/index.html) treats driver/runtime compatibility as a constrained relationship, not a reason to install the largest version number. DRAGONHYDRA retains the existing measured PyTorch 2.14.0+cu132 / CUDA 13.2 / cuDNN 9.24 / RTX 3050 baseline. The local GPU diagnostic, not this research table, provides operation and numerical evidence. A matrix operation does not cover cuDNN convolution behavior, large model fitting or workload speedup.

## Deferred unknowns

No Julia, MATLAB, Wolfram or SQL Server integration was attempted. No claim is made that their Python bindings support 3.14. SQL Server was not searched for outside the allowed project scope. Their future adapters must establish runtime availability, official binding compatibility, serialization/precision, timeout behavior and licensing where applicable. Node/Go/Java version commands show installed standalone runtimes; they do not prove a Python bridge or justify using a second language for a task Python already handles.
