# Repository-safe evidence

DRAGONHYDRA separates **LOCAL FORENSIC EVIDENCE** from **REPOSITORY-SAFE EVIDENCE**. The original checkpoint tree remains authoritative local history under ignored `runtime/checkpoints/`. This directory contains small, reviewed summaries that can be read from a clean GitHub checkout without exposing that tree.

These records summarize historical measurements. They do not rerun tests, prove present service health, reproduce a private machine, authenticate an external fact or attest that a browser performed an action. A source-artifact hash identifies exact local bytes; readers without those bytes cannot independently recompute that hash from the summary.

| Curated summary | Supported historical proof | Local checkpoint coordinates |
| --- | --- | --- |
| [Foundation](foundation-summary.json) | Initial 43-test run and distinct final 53-test run; Python 3.14, selected GPU correctness and bounded MariaDB probe results | `genesis-20260924T155516Z-ddf9f093`, `genesis-20260924T155954Z-3065e1ef` |
| [Dual Database](dual-database-summary.json) | 92 passing tests, simultaneous engine capability checks, selected permission/transport facts, GPU correctness and Joomla HTTP result | `dual-database-20260924T163749Z-e9b792e6` |
| [Web-to-SQL](web-sql-summary.json) | 141 passing tests, 380 real fixture records, separate synthetic counts, CLI origin, SQL/HTTP result and blocked Desktop stage | `web-sql-20260924T174531Z` |
| [Desktop/CLI Bridge](desktop-cli-bridge-summary.json) | 190 passing tests, synthetic two-observation insertion, replay with zero additional observations and local presentation with Desktop NOT_CONFIRMED | `desktop-cli-bridge-20260924T183316Z` |
| [Roadmap integrity](roadmap-integrity-summary.json) | Historical adoption/correction audits, seven corrected numeric occurrences, 2–3/3–5 ranges and recorded preservation of twelve original checkpoint files | `roadmap-adoption-20260924T184422Z-3178f45c`, `roadmap-range-correction-20260924T185126Z-9eb65c7a` |
| [Repository baseline](repository-baseline-summary.json) | 207 full local and 164 portable tests, live database/GPU/HTTP checks, preserved initial failures, blocked Desktop state and evidence-link reconciliation | `github-baseline-20260924T185739Z-2960f29d`, `dual-database-20260924T191146Z-3b110eb1` |
| [Initial GitHub publication](repository-publication-summary.json) | Exact initial commit/tree equality, private visibility, key file API checks, staged secret/link audit and successful Windows/Ubuntu CI | `github-baseline-20260924T185739Z-2960f29d` plus linked GitHub Actions runs |

The 53-test foundation claim belongs to the later genesis run; the earlier run has 43 tests. Actual measurement timestamps are copied from artifacts and may differ from directory-name timestamps. The adoption audit's earlier numeric interpretation is explicitly superseded by the owner's correction.

## Summary contract

Historical milestone JSON summaries contain:

- `schema_version`, milestone, evidence classification and curation time.
- A fixed statement distinguishing historical evidence from a new live check.
- `source_artifacts` with an ID, exact `local_evidence_path` string, SHA-256 and available source-recorded time.
- Selected measurements referring to their source-artifact IDs, including explicit test pass/fail/error/skip counts where applicable.
- Limits that prevent a narrow result from becoming a broader capability claim.

The repository-baseline summary adds current preparation measurements. The publication summary uses `verified_at` and an exact Git commit to record remote tree/content checks and linked Actions results; it does not claim those results for subsequent commits.

`local_evidence_path` is a plain string, never a Markdown link or promise that the file exists in Git. It is relative to the authoritative local project root. Ancillary logs, configuration backups, original downloads and diagnosis artifacts may be referenced elsewhere as **LOCAL EVIDENCE PATH** followed by inline code. Their absence from these summaries is deliberate; the index does not claim that every private artifact has been curated.

## Publication boundary

Only explicitly selected safe fields are exported. Do not copy raw checkpoints wholesale or include usernames, credential material, browser/session content, machine-specific private configuration, logs, data rows or unrestricted database inventories. Raw artifacts remain ignored. Preserving a local source does not authorize publishing it.

When preparing a summary, read source artifacts without modifying them, hash their exact bytes, choose the minimum fields supporting the documented claim, and verify source hashes remain unchanged. Inspect the summary and staged contents for secrets and generated artifacts. Documentation checks for GitHub must resolve links against the **actual staged file set**, not merely against files present in the local filesystem.

An ordinary checkout can inspect these JSON results and run portable tests. Repeating live proofs requires the documented local infrastructure and credentials supplied outside Git. New tests and current repository-baseline evidence must retain their own time and scope rather than overwrite these historical counts. See the [data policy](../DATA_POLICY.md), [testing tiers](../TESTING.md), [current status](../ROADMAP_STATUS.md) and [release strategy](../RELEASE_STRATEGY.md).
