# Handoff security model v1

The shared project tree is the integration boundary. The bridge neither opens browser profiles nor inspects Codex processes, private IPC, codex-computer-use-swift pipes or private session/auth databases. Browser availability and CLI availability remain separate.

## Input gates

- Strict closed JSON schema; duplicate JSON keys/non-finite numbers/unknown fields/producers/versions fail.
- UUID filenames must match envelope IDs; fixed canonical project identity; timezone-aware timestamps; no future capture; source observations and downloads cannot follow envelope creation.
- Manifest ≤1 MB; artifacts ≤5 MB each/10 MB total; ≤10 artifacts, ≤5 sources, ≤100 observations; at most 25 handoffs per explicit batch.
- Artifact paths must be relative and inside browser_downloads. Absolute/UNC/drive paths, parent traversal, percent-encoded traversal, alternate streams, symlinks/junctions and trailing Windows-dot/space ambiguity fail. No UNC exception is enabled.
- Only JSON/plain UTF-8 text/CSV/PNG/JPEG are supported. Extension/media mismatch and executable magic/shebang fail. Image signatures are checked but images are never decoded or executed by the consumer. Unknown inbox files go to failed; temporary files and recognized legacy manifests retain their separate owners.
- SHA-256 and exact byte sizes verified; accepted bytes are archived into the attempt checkpoint before SQL. Browser evidence must reference an included hashed artifact.
- Common secret keys, cookie/auth headers, bearer/basic credentials, JWT/private-key/API-key patterns are rejected. This is a bounded protective scanner, not a proof that arbitrary encoded/steganographic data contains no secret. Producers must submit only reviewed public data. A detected secret is moved from the handoff area into the existing ACL-protected runtime/secrets/handoff-quarantine; failed/receipt/checkpoint output contains a sanitized stub, never the detected value. No evidence is deleted.
- SQL/instruction fields are forbidden. SQL-looking strings in ordinary observation values are inert data and use parameters. No subprocess, eval, SQL executor or artifact execution is exposed by ingestion.

Successful external observations additionally require a known exact URL and a current VERIFIED source policy. Envelope labels cannot override UNVERIFIED/PROHIBITED policy. Robots status is required and archived as the producer's observation; the consumer processes files and makes no external request. The producer must genuinely check robots before automated capture. Localhost HTTP development URL syntax is supported; external HTTP is rejected, and successful non-synthetic local sources would still need an explicit reviewed registry entry.

## Storage and temporal guarantees

SQL Server controls structured truth with dedicated SELECT/INSERT-only ingestion and SELECT-only reader identities scoped to the five new tables. Existing SQL/MariaDB probe users and earlier ingestion users are unchanged. The schema uses fixed object names, foreign keys, unique hashes/IDs and parameterized data. No UPDATE/DELETE grants exist on bridge history.

Observation times distinguish observed_at, effective_at, available_at and ingested_at. Effective time may be historical or future; it never proves availability. The SQL as-of reader gates observation, availability and actual ingestion times. New values append with optional predecessor links, never silent updates.

MariaDB contains two small derived presentation cache rows, not copied observations or raw artifact tables. The existing PHP identity remains SELECT-only on presentation_cache. The endpoint continues Require local, explicit REMOTE_ADDR/Host guards, GET-only operation, HTML escaping and restrictive CSP; no core Joomla changes, firewall edits or service rebinding.

Atomic claim plus an exclusive one-shot lock prevents concurrent consumers from claiming the same pending file. SQL primary key and serializable ID lookup protect replay even after a crash. SQL commit and MariaDB publication are separate: partial success is explicit and replay repairs downstream work. Filesystem receipts and checkpoints use exclusive creation; they are not WORM storage or cryptographic producer attestations. Local administrators remain trusted.

A consumer interrupted in processing is deliberately not auto-recovered by age. Inspect the claim and SQL receipt, verify no consumer is running, then deliberately recover/requeue it. Invalid envelopes may exist only in filesystem failure receipts because no valid SQL envelope exists to reference. Valid BLOCKED source failures are stored in SQL with zero observations.
