# GitHub repository baseline — 2026-09-24

The authoritative local DRAGONHYDRA laboratory has been published as a private, auditable GitHub repository at [chatgptopenaiagi/DRAGONHYDRA](https://github.com/chatgptopenaiagi/DRAGONHYDRA). This block builds the repository home; V1 remains active and no V2 source-adapter expansion is included.

Initial commit `36db6f1bbbf229e3d47bf8a690f730c39f076fc4` was pushed and verified against remote `main`. All 164 remote file blobs matched the audited local tree; twelve key files were independently fetched through the GitHub contents API. [CI](https://github.com/chatgptopenaiagi/DRAGONHYDRA/actions/runs/36047122468) passed 164 portable tests on each of Windows and Ubuntu. [Repository safety](https://github.com/chatgptopenaiagi/DRAGONHYDRA/actions/runs/36047122504) passed with zero findings and 358 staged-documentation links. [Publication evidence](../evidence/repository-publication-summary.json) identifies that exact verified commit. This follow-up documentation commit records the result; its own remote checks remain part of the release gate.

## Initial state and scope

Authenticated GitHub CLI checks returned repository-not-found for the exact owner/name before creation. The local project had no `.git`, commits or remotes. Created the repository private, initialized `main`, and configured `origin` to `https://github.com/chatgptopenaiagi/DRAGONHYDRA.git`. Existing project files and checkpoints were preserved. No earlier Git history existed to squash or rewrite.

The repository now contains a current README with Mermaid architecture and V0–V10 status; source/tests/scripts/config/web; documentation index; ten short ADRs referencing original decisions; security, contribution, license, data, research and release policies; changelog; issue/PR templates; and conservative CI/security workflows. Package metadata still requires Python 3.14. Source rights remain retained under LICENSE_POLICY; no open-source license was selected.

## Validation

| Check | Recorded result |
| --- | --- |
| Canonical interpreter | Python 3.14.7 |
| Full local regression | 207 run, 207 passed, 0 failures, 0 errors, 0 skips |
| Portable tier | 164 run, 164 passed, 0 failures/errors/skips; 0 live dependency attempts |
| Local-only tier classification | 43 tests explicitly outside portable CI, not skipped as passing |
| SQL Server and MariaDB | Capability/permission/coexistence checks passed |
| GPU | Actual reference-checked operation passed, no CPU fallback; no speedup claim |
| Joomla | HTTP 200 and existing local endpoint tests passed |
| PHP presentation source | Syntax check passed |
| Production Python source | Unchanged from the preflight hash manifest |

[Curated current validation](../evidence/repository-baseline-summary.json) retains exact source hashes and historical limits. Full logs remain local: `runtime/checkpoints/dual-database-20260924T191146Z-3b110eb1` and `runtime/checkpoints/github-baseline-20260924T185739Z-2960f29d`.

Two real preparation failures were resolved without changing production behavior. A relocated checkout exposed the deployment-specific schema root: original exact-root verification remains local, while a new portable test compares the entire schema after changing only that explicit root. The initial full suite passed 202/204; two assertions assumed the latest presentation was always SYNTHETIC. Current authoritative evidence instead records a blocked Desktop attempt, zero observations and no Desktop confirmation. Test-only repairs now compare SQL, archived envelope/hash, immutable final receipt, MariaDB and HTTP presentation. Historical synthetic insertion/replay checks remain strict. Failed evidence is retained locally.

## Secret and generated-data boundary

The repository-wide audit searched recognized text and byte-compared known local credential values without printing them. No authored credential leak was found and no credential correction was required. Local secrets exist only in protected ignored credential/config files. Active MDF/LDF files are OS-locked, ignored and not publishable; arbitrary encoded-secret absence cannot be proved by a heuristic scanner.

The entire runtime, data and models trees, raw browser research, experiment machine evidence, logs, local configuration, credential/key patterns, caches, vendor packages and database/model binaries are excluded. The initial staged set passed secret/policy and known-local-secret byte checks against its exact Git blobs, file-size review and exact-index link validation: 164 files, 791,399 bytes, largest file 25,243 bytes, zero forbidden paths/binaries or secret findings. Two pre-existing blank-at-EOF whitespace warnings were retained to preserve production source bytes; other Git whitespace checks passed.

## Evidence reconciliation

**LOCAL FORENSIC EVIDENCE = `runtime/checkpoints`. REPOSITORY-SAFE EVIDENCE = `docs/evidence`.** Five historical summaries preserve measured foundation, dual-database, Web-to-SQL, bridge and roadmap-integrity claims. A separate baseline summary records this block's measurements.

Before the first commit, 74 checkpoint links and 13 other ignored-evidence links across 19 documents were reconciled. Supported historical claims link to [curated summaries](../evidence/README.md); ancillary originals appear as inline LOCAL EVIDENCE PATH text. No raw checkpoint tree was added to Git. [check_repository_links.py](../../scripts/check_repository_links.py) reads actual staged Markdown blobs and requires target membership in that index; local disk existence is insufficient.

## Remote governance and release boundary

Repository description is factual. Topics: sports-analytics, sports-intelligence, python, machine-learning, data-engineering, sql-server, mariadb, cuda, pytorch, simulation, odds and research. Labels cover architecture, hydra-source, medusa, pyramid, feature-factory, math-engine, simulation, prediction, odds, security, database, web, desktop-bridge, temporal-integrity, provenance, documentation, bug and enhancement. Existing default labels are retained. `main` is the trunk; no GitFlow or production deployment automation was introduced.

Initial publication verification passed: local/remote SHA equality, private visibility, default branch `main`, README/policy/workflow contents and both Actions workflows. A documentation follow-up retains the evidence without rewriting initial history. The immutable local final report and any prerelease notes record the exact final verified commit. Create `v0.1.0-alpha` only after that clean, pushed commit is also verified. Release assets must not contain runtime artifacts.

## Limits and next action

The canonical Windows environment, bounded credentials, databases, synthetic fixtures and GPU libraries remain prerequisites for live tiers. Clean-machine recreation and production deployment are not established. Existing wildcard bindings and loopback TLS certificate exception remain. Source approval needs current review. No prediction accuracy, calibration, trading profit, complete real-browser path or unrestricted scraping capability is claimed.

NEXT_EXACT_ACTION: Freeze the GitHub baseline after successful push and remote verification, then complete the first genuine successful Codex Desktop Browser → handoff → separate Codex CLI → Python 3.14 → SQL Server → MariaDB → Joomla path. Do not begin V2 expansion during repository engineering.
