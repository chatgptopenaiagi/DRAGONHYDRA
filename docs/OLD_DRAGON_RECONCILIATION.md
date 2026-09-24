# Old DRAGON reconciliation

Inspection date: 2026-09-24. Status: read-only donor review completed; no donor code copied, installed, executed or modified by this review.

## Donor identity and provenance

The discovered donor is `C:\xampp\CODEX-WORKSPACE\DRAGON`. Discovery and project inspection stayed inside `C:\xampp`. It is a modern DRAGON foundation (PR #0 / PR #1 plus a PySide6 desktop shell), not a recovered historical prediction engine. Its `legacy/README.md` and `docs/migration_from_legacy.md` explicitly say original historical assets were absent when the foundation was created. No FANN algorithm or historical field mapping can therefore be claimed as recovered.

The checked-out Git commit is `1d044992d36962359dfe46b4caedef750a3c0043`. Tracked files had no changes at inspection. Nine pre-existing, untracked Markdown documents exist under `research/competitive_intelligence/`; their findings are separately identified below and are not attributed to the committed baseline. The donor's `AGENTS.md` was read before its implementation. No `AGENTS.md` was present in the target project or target docs directory at this review's write checkpoint.

Paths in the tables below are relative to the donor. They are source evidence, not a claim that the donor test suite was run in this genesis session. No old setup script or Python 3.12 interpreter was invoked. Only this document was written by the donor-review task.

Key donor file fingerprints (SHA256, computed during inspection):

| File | SHA256 |
| --- | --- |
| `pyproject.toml` | `B153741FE63DB7FEF7308786185D16C5BC273C0DA8FD8F6B5B3C858389E3C5DB` |
| `src/dragon/data_engine/features/factory.py` | `D389B6013A1B43F21E0C28C98210D0ECC49522E854CAA19FC9510CACE501466C` |
| `src/dragon/models/base.py` | `027882944447C87EDC89D4DBD31FBD5A297C22BEA72DA7BE05335C6485E41A07` |
| `src/dragon/db/schema.sql` | `A7E25D746D0C9F451B2E9420A8EA3E9942A53247E5C120263AFEC92E8A459A84` |
| `src/dragon/runtime/cuda.py` | `D97F6A70657971B1CDC433306BC37A5B312B0CCD931602F1F8CD12B011AE3BC6` |

## Classification meanings

`KEEP` retains a principle. `PORT` is a candidate for a later deliberate migration with tests. `REWRITE` preserves a purpose but changes implementation. `MODERNIZE` extends a sound boundary. `REFERENCE_ONLY` informs future work without runtime adoption. `REJECT` excludes an unsafe inference or behavior. `OBSOLETE` applies to old project-specific constraints that no longer govern this project. `INCOMPATIBLE_WITH_PYTHON314` requires concrete evidence; here it applies to old packaging metadata, not a blanket judgment about its dependencies. `CONFLICTS_WITH_NEW_ARCHITECTURE` identifies a real difference in system responsibilities.

## Component decisions

| Donor concept or implementation | Classification | Evidence | DRAGONHYDRA treatment |
| --- | --- | --- | --- |
| Typed, compact domain boundaries; business logic independent of presentation | KEEP | `AGENTS.md` rules 8–10, 17; `docs/architecture.md`; `src/dragon/desktop/application.py` | Domain contracts remain independent of PHP, Qt, web delivery and engines. |
| Explicit legacy provenance and evidence-backed positional adapter | KEEP | `src/dragon/data_engine/features/legacy_adapter.py`; `tests/test_legacy_adapter.py`; `docs/migration_from_legacy.md` | No invented source mapping. Preserve donor provenance; any future code port gets a recorded diff and tests. |
| Score availability rather than earlier kickoff as evidence boundary | KEEP | `factory.py` completed filter and `_join_team_history`; `tests/test_feature_factory.py` | No future information in historical features, training, backtests, simulation or evaluation. Preserve the stricter pre-kickoff result policy described below. |
| Polars `FeatureFactory` rolling goals, goal difference, points form and history counts | MODERNIZE | `src/dragon/data_engine/features/factory.py`; `tests/test_feature_factory.py` | Retain deterministic lazy feature computation as P3 design. Later add arbitrary as-of cutoffs, immutable evidence-version inputs, entity IDs, missingness, lineage and feature-definition versions. It is not ported in genesis. |
| Raw team strings as identity; history ordered only by result availability | REWRITE | `factory.py` groups by `team`; `src/dragon/data_engine/schemas.py` | Explicit club/entity IDs and an audited feature ordering policy are required before production features. Availability ordering is not automatically competition chronology. |
| Missing feature values filled with zero | MODERNIZE | `factory.py` `fill_null(0.0)` and zero counts | Preserve history counts; add explicit missing/unknown states. Zero history must not become evidence of zero ability or performance. |
| `ModelInterface`, finite/nonnegative/normalized 1X2 probability validation | PORT | `src/dragon/models/base.py`; `tests/test_model_interface.py` | Candidate for a later tested port, generalized to typed market outcomes and evidence/cutoff metadata. No model code is copied now. Valid probabilities alone do not prove calibration. |
| Model name/version and deterministic tie breaking | KEEP | `src/dragon/models/base.py` | Preserve deterministic identity and explicit tie policy when prediction interfaces are implemented. |
| DuckDB analytical queries with configurable memory and thread budgets | KEEP | `src/dragon/db/connection.py`; `src/dragon/config.py` | DuckDB belongs in P2 research/analytics. Measure budgets for this host rather than adopting old 40 GB / 14-thread defaults unchanged. |
| DuckDB as the sole durable relational store | CONFLICTS_WITH_NEW_ARCHITECTURE | `docs/architecture.md`; `docs/data_model.md`; three-table DuckDB schema | MariaDB owns appropriate P1 operational state. DuckDB and Parquet own P2 analysis. Use adapters, not duplicated tables everywhere. |
| Idempotent schema creation and database constraints | KEEP | `src/dragon/db/schema.sql`; `tests/test_database.py` | Future schema migrations preserve identity and valid states; genesis does not import the old schema. |
| Fixture upsert overwrites scores, kickoff, availability and source | REWRITE | `src/dragon/data_engine/ingestion/fixtures.py` `seed_fixtures` / `ON CONFLICT DO UPDATE` | Preserve immutable evidence revisions before changing current operational projections. Old upsert is not a historical evidence ledger. |
| `feature_vectors.as_of_at` and feature version identity | MODERNIZE | `src/dragon/db/schema.sql`; `docs/data_model.md` | Extend with input evidence-version lineage, model/engine versions and replay policy. A schema column alone does not implement cutoff-safe replay. |
| Timestamped odds snapshots | MODERNIZE | `src/dragon/data_engine/schemas.py`; `src/dragon/db/schema.sql` | Retain appendable observation history; later add canonical market/line identity, source availability, market status, revision and freshness. |
| Polars lazy scans and Parquet / Arrow boundary | KEEP | `src/dragon/data_engine/ingestion/fixtures.py`; `docs/architecture.md`; `src/dragon/cli.py` | Prefer columnar P2/P3 pipelines when Python 3.14 packages are verified. No blind dependency installation or assumed compatibility. |
| Generic fixture, odds and team-stat records | MODERNIZE | `src/dragon/data_engine/schemas.py` | Generalize source identity, exact evidence versions, temporal proof and metric definitions. These records do not already implement player/lineup/live-event intelligence. |
| Optional hardware doctor and injected probes for tests | REWRITE | `src/dragon/runtime/hardware.py`; `src/dragon/runtime/cuda.py`; `tests/test_runtime.py` | New diagnostics must verify canonical interpreter, package provenance, actual Torch CUDA execution and cuDNN separately. Preserve injectable/testable boundaries. |
| `cuda_available=True` when only `nvidia-smi` detects hardware | REJECT | `src/dragon/runtime/cuda.py` fallback branches; `test_nvidia_device_can_be_reported_without_pytorch` | GPU identity is not proof that PyTorch can execute CUDA. Report device detection, runtime availability and successful matrix operation independently. |
| CPU fallback and configured VRAM thresholds | KEEP | `AGENTS.md` rules 11–12; `CudaMemoryPolicy`; `src/dragon/config.py` | Future eligible workloads fall back explicitly with reason codes. Detection is not an implemented GPU computation fallback. Thresholds are policy, not enforced reservations. |
| PowerShell orchestration and exit-code propagation | REWRITE | `Invoke-DragonCore.ps1`; `scripts/Init-Database.ps1`; `scripts/Seed-Database.ps1` | Keep narrow wrappers, but target the verified Conda Python 3.14 interpreter without uv-managed Python replacement. |
| Old runtime installer and locked Python 3.12 project metadata | INCOMPATIBLE_WITH_PYTHON314 | `.python-version` is `3.12.13`; `pyproject.toml` requires `>=3.12,<3.13`; `Setup-Environment.ps1` installs the pinned runtime | Do not execute or adopt this installation path. Write new Python 3.14 metadata and evaluate each desired dependency independently. |
| Old release/PR numbering, package name and uv setup workflow as governing policy | OBSOLETE | `README.md`; `docs/roadmap.md`; `pyproject.toml`; `Setup-Environment.ps1` | Useful donor history only. DRAGONHYDRA uses its own genesis decisions and Conda environment. |
| PySide6 widgets backed by shared UI-independent services and workers | REFERENCE_ONLY | `docs/desktop.md`; `src/dragon/desktop/application.py`; `workers.py`; `tests/test_desktop_application.py` | Useful later presentation pattern; full UI is outside this block. PySide6 Python 3.14 packaging is not certified by reading old source. |
| Packaged application defaults under `%LOCALAPPDATA%/DRAGON` | CONFLICTS_WITH_NEW_ARCHITECTURE | `src/dragon/desktop/application.py` `RuntimePaths.resolve`; `docs/desktop.md` | New project work remains under `C:\xampp\DRAGONHYDRA`; do not inherit an external writable project home. |
| Temporary-database tests, explicit validation and bounded scope | KEEP | `AGENTS.md` rules 15–19; `tests/test_database.py`; `tests/test_ingestion.py` | New tests use isolated state and never modify unrelated XAMPP databases. Runtime results must come from actual execution. |
| Prediction Tribunal, Market Radar, backtesting and Monte Carlo simulation | REFERENCE_ONLY | `docs/roadmap.md`; `README.md`; `scripts/Run-Tribunal.ps1` exits with unavailable status | These are donor roadmap concepts, not recovered working subsystems. Map to P6–P8; Math Tribunal remains a distinct new concept. |
| Public sports research evidence classes, contextual confidence, six timestamps and bounded re-search | KEEP | untracked `research/competitive_intelligence/README.md`, `00_RESEARCH_BOUNDARIES.md`, `13_DRAGON_GAP_ANALYSIS.md` | Carry forward evidence/inference distinctions, shared-source dependence, correction concerns and targeted questions. Prior research is context, not a collector implementation or current external verification. |
| Linear files → features → prediction flow as the entire system | CONFLICTS_WITH_NEW_ARCHITECTURE | `docs/architecture.md` data-flow diagram | Retain the useful local analytical path inside the larger two-realm Hydra → Medusa → Pyramid → uncertainty → research loop. |
| Assumed access to competitor feeds or recovered proprietary algorithms | REJECT | `legacy/README.md`; research `00_RESEARCH_BOUNDARIES.md`; no collector implementation in inspected source | No inferred feed access, scrapers or proprietary reconstruction in genesis. |

## Temporal law retained and extended

The donor implements a concrete conservative result feature rule:

```text
result_available_at < target kickoff_at
```

`join_asof(..., allow_exact_matches=False)` excludes equality. Its regression tests cover a future score changing without affecting earlier features, an earlier match whose result arrives after the target, and exact-boundary rejection. This is a useful guarantee and must not be silently weakened.

DRAGONHYDRA general evidence eligibility requires proof that the exact version was available by the prediction cutoff (`available_at <= target_as_of_at`), with timezone, precision and provenance explicit. A pre-kickoff score-derived feature may apply the donor's stricter `<` result policy on top. The policy must be named in replay and feature metadata; general eligibility does not silently substitute for strict pre-kickoff result eligibility.

Every relevant evidence contract must distinguish `event_at`, `observed_at`, `available_at`, `updated_at`, `expires_at`, and the query's `target_as_of_at`. They have different meanings; event time is not availability, ingestion today is not historic availability, and source correction time must not backdate a corrected assertion. Unknown availability remains unknown and cannot supply historical predictive evidence. Planned/expected events may have future event times even when the assertion is already known.

Three donor-research examples directly motivate the new prototypes:

1. A final result occurs before the cutoff but is published/received later: reject it at that cutoff.
2. A match event is corrected later: retain the original version for earlier eligible replays; apply the correction only once that version becomes available. `superseded` does not mean erase history.
3. An expected goalkeeper becomes confirmed: preserve expectation and confirmation as distinct assertions/versions with their own availability. Confirmation must not leak into earlier forecasts.

The donor's fixture overwrite path, arbitrary-cutoff gap and absence of immutable revision storage mean it does not establish full temporal replay. Genesis must build and test that boundary before connecting collectors, feature engines or models.

## Python 3.14 reconciliation

OWNER_INTENT: canonical Python 3.14 in `codex-pytorch`, no downgrade.

TECHNICAL_CONSTRAINT: the donor's packaging explicitly excludes 3.14 and its setup selects 3.12.13. Donor dependency ranges mention DuckDB, NumPy, Polars, PyArrow, PySide6, Pydantic, psutil and other libraries. These old declarations do not establish whether current releases run on 3.14.

OPTIONS: port specific tested contracts; upgrade individual compatible dependencies; replace small dependencies with standard-library contracts where suitable; defer large optional packages. Running the old installer is outside the chosen architecture.

CHOSEN_COMPROMISE: new package and contracts, no donor runtime copied; retain proven ideas and test cases as requirements. Dependency compatibility is decided by the new [technology matrix](TECHNOLOGY_COMPATIBILITY_MATRIX.md), current package metadata and executable checks.

REASON: preserving historical principles does not require preserving an obsolete interpreter constraint. Neither dependency failure nor success is inferred merely from a version pin.

The donor research `PROGRESS.md` records a previous Python 3.14 attempt with eight test collection errors, including missing DuckDB/Polars, and a later 12-test configuration/model subset pass. Those are historical donor records, not tests rerun by this read-only review, and missing packages are not proof of language incompatibility.

## Reuse accounting and next boundary

- Reused ideas: typed adapters, strict temporal result eligibility, evidence provenance, probability validation, analytical engine separation, lazy/columnar pipelines, CPU-aware diagnostics, configured resource budgets, UI-independent services, isolated tests and explicit failure reporting.
- Copied source files: **none**.
- Rewritten for genesis: evidence/time/version contracts, configuration/runtime verification and a bounded database adapter/bridge are new DRAGONHYDRA work; the main [progress record](PROGRESS.md) is authoritative for execution status.
- Deferred ports: FeatureFactory, ModelInterface, operational schemas, full analytical pipelines and UI. No old code has been described as a newly passing Python 3.14 implementation.
- Not implemented in donor or genesis: full collectors, prediction/math tribunals, market radar/odds engine, large models, backtesting execution and simulation services.
- Next donor-related action: before a future FeatureFactory port, create synthetic revision-aware parity cases and compare strict pre-kickoff results under Python 3.14 with explicit entity, missingness and cutoff policies. Do not initialize or mutate the donor database.
