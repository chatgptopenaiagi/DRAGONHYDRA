# Data and generated-artifact policy

Adopted 2026-09-24. The local project is authoritative; Git contains reviewed source, contracts and documentation. The initial GitHub baseline is private. Privacy of the repository never makes secrets or restricted data suitable for a commit.

Repository source-code rights **are not** sports-data rights. The [license policy](../LICENSE_POLICY.md) grants no general open-source license. Each external dataset retains its own attribution, license, terms, scope and redistribution conditions independently.

| Category | Git policy | Required treatment |
| --- | --- | --- |
| Authored source, scripts and schemas | Commit after review | No embedded credentials; document dependencies and ownership |
| Configuration templates | Commit only safe reviewed configuration | References to protected local files are allowed; values containing secrets are not |
| Curated test fixtures | Allowed when necessary, small and safe | Prefer synthetic input; preserve explicit labels and expected temporal/provenance behavior |
| Synthetic data | Only curated examples by default | Label generator, capture origin and observations; do not claim live evidence |
| Public/open external data | No automatic inclusion | Review redistribution rights, attribution, exact scope and value; record source URL, retrieval time, license and hash |
| Restricted or unverified external data | Do not commit | Block acquisition where policy is uncertain; never publish merely because bytes are accessible |
| Runtime database files and dumps | Do not commit | Local `runtime/sqlserver-lab/`, other runtime data and `data/` remain excluded |
| Checkpoints, handoff manifests, receipts and downloads | Do not commit by default | Preserve immutable local evidence; curate a sanitized report separately if needed |
| Curated evidence summaries | Commit after explicit field/content review | Small JSON under `docs/evidence/` with source hashes, historical scope and plain-string local coordinates; never raw artifact copies |
| Secrets, cookies, tokens, credentials and browser profiles | Never commit | Protected local storage only; secrets are not release assets or issue attachments |
| Models, weights and generated simulations | Do not commit by default | Keep `models/` and large derived output outside Git; future distribution requires licensing, size, provenance and reproduction review |
| Machine logs, caches, vendor packages and temporary files | Do not commit | Rebuild or retain locally as appropriate; preserve relevant failures in sanitized reports |

## Dataset ownership

SQL Server owns structured intelligence. MariaDB owns operational state and bounded presentation caches. DuckDB is the planned analytical laboratory; Parquet is planned large-history/archive storage. These future roles do not claim implemented workloads. Every materialized copy needs a declared purpose, source version, transformation, refresh/cutoff semantics and recovery rule. No automatic whole-dataset replication.

## Evidence and temporal integrity

Preserve source identity, URL, retrieval and observation times, hashes where available, parser/version, confidence, verification and terms/license state. Keep event time distinct from observation, availability, revision, ingestion and analysis cutoff. Corrections append versions with their own availability; historical replay cannot use later knowledge. Unknown timezone or historical availability remains unknown.

The [source matrix](../research/PUBLIC_SPORT_SOURCE_MATRIX.md) and [source policy](SPORT_SOURCE_POLICY.md) are the research entry points. A permitted local acquisition does not automatically authorize copying that dataset into GitHub. Curated third-party notices or license evidence retain attribution and do not become the repository's source-code license.

## Local evidence and publication

Ignore `runtime/` generated evidence, `data/`, `models/`, local credential files and downloaded binaries. Version-controlled examples and schemas belong in reviewed authored paths such as `tests/` and `config/`, not an exception exposing the runtime tree. Preserve existing local checkpoints when changing ignore rules; exclusion from Git does not authorize deletion.

Before staging, audit actual file contents and the staged set, including ignored/generated boundaries and unexpected large files. `.gitignore` is a selection aid, not a security guarantee. **LOCAL FORENSIC EVIDENCE** is the original ignored `runtime/checkpoints/` tree; **REPOSITORY-SAFE EVIDENCE** is the reviewed [docs/evidence](evidence/README.md) directory. Curated summaries select only small safe measurements, retain exact source SHA-256s, identify limitations and store `local_evidence_path` as a string. They are historical summaries, not a live rerun or an independent attestation.

Do not turn ignored checkpoint paths into broken GitHub Markdown links. Link to an appropriate curated summary when it actually supports the claim; preserve other source coordinates as explicitly local inline-code paths. Validate repository links against the actual staged file set, not the machine's broader local filesystem. Never upload raw runtime artifacts as Actions or release artifacts.
