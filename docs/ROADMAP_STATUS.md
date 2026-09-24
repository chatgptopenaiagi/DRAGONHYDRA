# DRAGONHYDRA roadmap status

As of 2026-09-24. Authority: [master roadmap](DRAGONHYDRA_MASTER_ROADMAP.md). Evidence and implementation history: [PROGRESS](PROGRESS.md) and [DECISIONS](DECISIONS.md).

## CURRENT_VERSION

VERSION: V1 — WEB → MEDUSA → SQL → JOOMLA. V0 is the preserved, largely implemented foundation.

## STATUS

IN_PROGRESS. The CLI-source ingestion path has a real historical-data demonstration. The Desktop/CLI bridge is implemented and synthetically demonstrated; genuine successful Desktop capture and a separate Codex CLI application-session demonstration remain unverified. A newer actual BLOCKED Desktop envelope is consistent across SQL, immutable receipt, MariaDB and Joomla; it contributes zero observations and does not close the success gate. Initial scope remains 2–3 sources and approximately 3–5 closely related items per normal session.

## COMPLETION_EVIDENCE

The [repository baseline report](reports/GITHUB_BASELINE.md) and [curated baseline evidence](evidence/repository-baseline-summary.json) record the new Python 3.14.7 validation: 207 full local tests and 164 portable tests passed, zero failures/errors/skips. SQL/MariaDB capability checks, GPU correctness and Joomla HTTP checks passed. The first full run's two stale presentation assertions and the initial relocated-schema failure remain recorded, along with their fixes; no production source changed.

[Historical milestone evidence](evidence/README.md) separately preserves foundation 53, dual database 92, Web-to-SQL 141 and bridge 190-test results. LOCAL FORENSIC EVIDENCE remains in ignored `runtime/checkpoints`; REPOSITORY-SAFE EVIDENCE is curated under `docs/evidence`. Publication status is recorded in the baseline report and subsequent release/remote verification.

[Initial publication verification](evidence/repository-publication-summary.json): private `main` at `36db6f1bbbf229e3d47bf8a690f730c39f076fc4` matched local and remote; CI passed 164 portable tests on Windows and Ubuntu, and Repository safety passed all 358 links with no findings. This evidence is tied to that commit, not assumed for later changes.

## COMPLETION_PERCENTAGE

UNMEASURED for V0, V1 and the overall roadmap. No agreed weighted acceptance denominator exists; test counts and file counts are not completion percentages. No numeric estimate is claimed. Future updates must define acceptance items, denominator and evidence before reporting a percentage.

## COMPLETED

COMPLETED_COMPONENTS:

Within the documented local laboratory scope:

- Canonical Python 3.14 foundation, temporal/evidence contracts, bounded dual-database connectivity, GPU correctness diagnostics, secrets boundaries and unique checkpoints. [Foundation evidence — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/checkpoint.json`).
- Controlled OpenFootball CLI ingestion: 380 real historical fixtures accepted through validation, append/version SQL storage, derived MariaDB cache and local PHP endpoint under Joomla's directory. [Web-to-SQL report](WEB_SQL_FINAL_REPORT.md).
- BrowserHandoffEnvelope v1, atomic publishing, bounded one-shot ingestion, artifact hashes, append-only SQL observations, recoverable publication and replay receipts. Synthetic handoff stored two observations; replay inserted zero additional observations. [Bridge report](DESKTOP_CLI_BRIDGE_FINAL_REPORT.md).
- Final existing regression record: 190/190 passed, zero failures/errors/skips under Python 3.14.7. [Test evidence — curated summary](evidence/desktop-cli-bridge-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/desktop-cli-bridge-20260924T183316Z/tests.json`). Inspected during adoption, not rerun.
- Master roadmap, status file, resumption guidance and dated decision records adopted.

## PARTIAL

PARTIAL_COMPONENTS:

- V0 reproducibility: local environment and reference-checked compute evidence exist; a clean-machine rebuild is not established by these records. GPU correctness does not establish speed benefit.
- V1 gate: real sports data reached the local Joomla-directory display by CLI; native Joomla extension/content integration is not implemented or required by the current endpoint design. Genuine Desktop browser provenance and visual UI verification remain pending.
- MEDUSA: bounded validation, temporal checks, deduplication, conflicts and rejection paths exist; cross-provider entity reconciliation and measured long-term source reliability do not.
- Source policy metadata exists; source trust/performance histories and continuing terms review are not a mature scoring system.
- Math contracts and synthetic odds helpers predate this roadmap. They are prototypes, not evidence that V4 or V7 success gates have been achieved.

## NOT_STARTED

NOT_STARTED_COMPONENTS:

Roadmap-level implementations and success gates remain unproved for V2 specialist adapter coverage of one competition, V3 reproducible feature snapshots, V4 competing engines on shared features, V5 historical simulations, V6 Prediction Tribunal, V7 real historical market reconstruction, V8 targeted uncertainty reduction, V9 continuous historical benchmarks and V10 broad multi-head operation. Existing primitive contracts/helpers do not change this classification. DuckDB/Parquet analytical workloads, production prediction models and live odds acquisition are not established by current evidence.

| Version | Evidence-based stage status |
| --- | --- |
| V0 | Largely implemented local foundation; preserve verified boundaries |
| V1 | Active; CLI demonstration and synthetic bridge validated, genuine Desktop proof pending |
| V2–V10 | Deferred; stage success gates not demonstrated |

Maturity: local ingestion and synthetic bridge paths are VALIDATED only within their recorded demonstrations; full browser integration remains EXPERIMENTAL; later stage systems remain CONCEPT. No blanket production/STABLE claim.

## CURRENT_BLOCK

GitHub repository architecture and engineering baseline: private repository, professional entry point, lightweight ADR/policy structure, portable CI, explicit test tiers, curated evidence and Git-index link validation. No V2 expansion or new product functionality. The earlier [range correction](ROADMAP_RANGE_CORRECTION.md) and all original checkpoints remain preserved. Repository publication verification is separate from V1's pending genuine Desktop success gate.

## CURRENT_LIMITATIONS

- No real Desktop research or separate Codex CLI app session demonstrated; prior browser unavailability is a historical observation, not a claim about current tool availability.
- StatsBomb terms/license remain UNVERIFIED, UEFA TERMS_BLOCKED and The Odds API AUTH_REQUIRED in existing records. OpenFootball is the sole enabled external demo dataset; review current source policy before future acquisition.
- Historical fixture timezone is unknown; do not invent UTC kickoff or backdate evidence availability.
- Local producer claims are trusted-file provenance, not cryptographic browser attestation. SQL and cache writes are separate commits, with explicit recovery rather than a distributed transaction.
- Existing broader service bindings and loopback SQL certificate-trust exception remain documented; adoption does not revalidate or change them.
- New live tests and GPU/database correctness probes passed for the repository baseline; no performance benchmark or fresh external sports fetch was performed. Prior 190-test results retain their original timestamp.
- Numeric intent is resolved: **2–3 sources (two to three)** and approximately **3–5 closely related items (three to five)** per normal session. Preserve the range separators exactly; these are small ranges, not two-digit task or source counts. No further numeric clarification is pending.
- Source reliability, calibration, research benefit and full reproducibility remain unmeasured; no composite architecture score is claimed.

## NEXT_EXACT_ACTION

After successful push and remote verification, freeze the GitHub baseline, then complete the first genuine successful Codex Desktop Browser handoff: Desktop Browser → handoff → separate Codex CLI session → Python 3.14 → SQL Server → MariaDB → Joomla. Follow [Desktop instructions](CODEX_DESKTOP_HANDOFF_INSTRUCTIONS.md) and the [envelope schema](../config/browser-handoff-envelope.schema.json), review current source policy and preserve actual provenance/timestamps. A blocked attempt remains evidence of failure, not successful capture. Do not begin V2 Hydra Source Adapter expansion during this repository task.
