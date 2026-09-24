# Python 3.14 policy

Python `>=3.14,<3.15` is mandatory for this genesis environment. The canonical interpreter is `C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe`, configured in [genesis.toml](../config/genesis.toml). The observed baseline is Python 3.14.7 in the existing `codex-pytorch` Conda environment. Python is a normal GIL build; free-threaded-wheel availability is not interchangeable with the installed interpreter ABI.

The interpreter is an explicit existing tool outside the project root; project work, downloads and generated evidence stay under `C:\xampp\DRAGONHYDRA`. There is no Python 3.12 environment, downgrade or replacement install in this block. An active shell's environment label is not sufficient proof: record `sys.executable`, `sys.version`, environment context and the actual import/operation results.

The [executed genesis diagnostic — curated summary](evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/diagnostics.json`) reports the exact configured executable, Python 3.14.7, `codex-pytorch`, NumPy 2.5.3 and PyTorch 2.14.0+cu132, with the matrix check passing on CUDA. This is a measured checkpoint, not an assumption from the owner baseline.

## Runtime selection and dependency policy

[diagnostics.py](../src/dragonhydra/diagnostics.py) rejects a Python minor version other than 3.14 and reports whether the resolved executable matches configuration. Launchers/tests must use the configured executable rather than depend on bare `python` PATH resolution. Changing the canonical environment or moving the project is an explicit future decision, never an implicit package-install side effect.

Classify every proposed dependency before adoption:

| Classification | Meaning | Next action |
| --- | --- | --- |
| PY314_NATIVE | Python 3.14 itself, bundled code or explicit selected-build support | Still run import and relevant behavior tests. |
| PY314_COMPATIBLE | Local execution or suitable universal/stable-ABI/protocol evidence | Distinguish measured execution from packaging-only evidence. |
| PY314_COMPATIBLE_WITH_NEWER_VERSION | A selected old version is replaced by a specific newer compatible candidate | Record old/new versions and behavior changes. |
| PY314_REQUIRES_BUILD | No suitable selected-platform artifact; source build is necessary | Evaluate toolchain, reproducibility and maintenance before building. |
| PY314_REQUIRES_REPLACEMENT | Selected dependency cannot satisfy this platform/interface | Compare an adapter-compatible replacement or rewrite. |
| PY314_UNKNOWN | Insufficient evidence for the intended path | Investigate or defer; do not pretend missing means incompatible. |

[TECHNOLOGY_COMPATIBILITY_MATRIX.md](TECHNOLOGY_COMPATIBILITY_MATRIX.md) and [the source register](../research/genesis-compatibility-sources.md) separate local versions, official package evidence and pending tests. Wheel availability is not a complete compatibility certificate. Native libraries require the right ABI/platform; external languages may work through a protocol even when an in-process Python binding does not.

For a needed dependency: verify official metadata and Windows/Python 3.14 artifacts; inspect transitive constraints against NumPy/PyTorch; select the minimum useful scope; preserve the previous state; run import and task-specific known-answer tests; record installation/version/source and any failures. If the attempt fails, investigate, upgrade, replace, adapt, isolate or rewrite. A downgrade is not the default remedy.

## Genesis changes and deferred libraries

The existing NumPy, PyTorch and SymPy packages are retained. This block adds only project-local PyMySQL 1.2.3 under `runtime/vendor/pymysql-1.2.3` for the SQL proof. It does not modify Conda's package set. The adapter verifies the imported driver path and installed distribution version, preventing an unexpected system driver from silently satisfying the probe.

DuckDB, Polars, PyArrow, SciPy, statsmodels and scikit-learn remain candidates until their concrete feature is implemented and tested. No Python 3.12 donor lock file, uv installation script or bulk dependency list is adopted. [OLD_DRAGON_RECONCILIATION.md](OLD_DRAGON_RECONCILIATION.md) records the old metadata constraint separately from individual dependency compatibility.

Julia, MATLAB, Wolfram, SQL Server, Qwen and other large integrations are deferred. If a future binding conflicts with Python 3.14, evaluate a bounded subprocess/HTTP adapter, a newer supported binding, a replacement engine or a rewritten operation. An isolated external runtime does not change the canonical Python orchestrator and must not hide untested serialization or lifecycle behavior.

## Validation and reconciliation

Required genesis checks include exact minor version/executable, NumPy/PyTorch imports, CUDA availability, a bounded GPU matrix operation, the read-only SQL proof and write rejection, evidence chronology/supersession, and secret-free configuration. Tests must run through Python 3.14 and avoid unrelated databases. Results belong in [PROGRESS.md](PROGRESS.md); a test file or metadata declaration does not establish a pass.

OWNER_INTENT: keep Python 3.14 while preserving old DRAGON's strongest ideas. TECHNICAL_CONSTRAINT: old package metadata requires 3.12 and some future dependencies are untested. OPTIONS: port compatible code, modernize a dependency, use a protocol boundary, rewrite a narrow component or defer it. CHOSEN_COMPROMISE: a new Python 3.14 project, standard-library typed prototypes and one isolated driver. REASON: preserve a proven compute baseline while making each new dependency's cost and compatibility measurable.
