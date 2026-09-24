# GitHub repository baseline — 2026-09-24

The authoritative local DRAGONHYDRA laboratory has been prepared as a private, auditable GitHub repository at [chatgptopenaiagi/DRAGONHYDRA](https://github.com/chatgptopenaiagi/DRAGONHYDRA). This block builds the repository home; V1 remains active and no V2 source-adapter expansion is included.

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

The entire runtime, data and models trees, raw browser research, experiment machine evidence, logs, local configuration, credential/key patterns, caches, vendor packages and database/model binaries are excluded. Only authored source/docs and curated safe evidence are intended for Git. The first staged set must pass the secret/policy scan, file-size review and exact-index link audit before committing.

## Evidence reconciliation

**LOCAL FORENSIC EVIDENCE = `runtime/checkpoints`. REPOSITORY-SAFE EVIDENCE = `docs/evidence`.** Five historical summaries preserve measured foundation, dual-database, Web-to-SQL, bridge and roadmap-integrity claims. A separate baseline summary records this block's measurements.

Before the first commit, 74 checkpoint links and 13 other ignored-evidence links across 19 documents were reconciled. Supported historical claims link to [curated summaries](../evidence/README.md); ancillary originals appear as inline LOCAL EVIDENCE PATH text. No raw checkpoint tree was added to Git. [check_repository_links.py](../../scripts/check_repository_links.py) reads actual staged Markdown blobs and requires target membership in that index; local disk existence is insufficient.

## Remote governance and release boundary

Repository description is factual. Topics: sports-analytics, sports-intelligence, python, machine-learning, data-engineering, sql-server, mariadb, cuda, pytorch, simulation, odds and research. Labels cover architecture, hydra-source, medusa, pyramid, feature-factory, math-engine, simulation, prediction, odds, security, database, web, desktop-bridge, temporal-integrity, provenance, documentation, bug and enhancement. Existing default labels are retained. `main` is the trunk; no GitFlow or production deployment automation was introduced.

Publication verification follows the initial commit: compare local/remote SHA, verify private visibility/default branch and README/policy/workflow contents through GitHub, inspect both Actions workflows and resolve any failures. The immutable local final report and any prerelease notes record the exact verified commit; this prepublication record does not itself claim an Actions result. Create `v0.1.0-alpha` only after a clean, pushed, verified baseline. Release assets must not contain runtime artifacts.

## Limits and next action

The canonical Windows environment, bounded credentials, databases, synthetic fixtures and GPU libraries remain prerequisites for live tiers. Clean-machine recreation and production deployment are not established. Existing wildcard bindings and loopback TLS certificate exception remain. Source approval needs current review. No prediction accuracy, calibration, trading profit, complete real-browser path or unrestricted scraping capability is claimed.

NEXT_EXACT_ACTION: Freeze the GitHub baseline after successful push and remote verification, then complete the first genuine successful Codex Desktop Browser → handoff → separate Codex CLI → Python 3.14 → SQL Server → MariaDB → Joomla path. Do not begin V2 expansion during repository engineering.
