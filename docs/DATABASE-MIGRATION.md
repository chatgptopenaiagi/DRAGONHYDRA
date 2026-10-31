# SQLite migration preparation

The SQLite preparation command creates a checked private bundle from an
explicitly selected product `core.sqlite3`. It uses Python's existing SQLite
online backup and does not require a database driver or new software. It does
not connect to MariaDB, generate a MariaDB restore script or change authority.

The product database and the older research database are separate. In particular,
`runtime/connections/product/core.sqlite3` is not
`runtime/dragonhydra.sqlite3`. The preparation currently accepts only the known
product core tables, or the exact optional context profile described below.
Unknown tables, unsupported schema features, broken foreign
keys or incomplete raw evidence stop preparation with a diagnostic.

Use a fresh project-local output directory outside the selected live state:

```powershell
.\runtime\server-env\Scripts\python.exe -B scripts\prepare_database_migration.py `
  --database runtime\connections\product\core.sqlite3 `
  --output runtime\migrations\product-<fresh-name>

.\runtime\server-env\Scripts\python.exe -B scripts\prepare_database_migration.py `
  --verify-bundle runtime\migrations\product-<fresh-name>
```

Preparation opens the source with `mode=ro` and `query_only=ON`, establishes a
read transaction and uses `sqlite3.backup` to retain one committed snapshot,
including committed WAL data. Other source writers can continue. The source
transaction ends with rollback; source files may still change from those other
writers. The bundle records its own snapshot identity instead of claiming the
live source stayed byte-identical.

The bundle contains:

- A standalone SQLite snapshot with integrity and foreign-key checks.
- Exact table, index and trigger definitions from `sqlite_master`.
- Primary-key-ordered JSONL rows with explicit NULL, decimal integer, hexadecimal
  float, UTF-8 text and base64 BLOB types, plus row and table hashes.
- SQLite sequence high-water marks, including values beyond the highest
  remaining row after deletions.
- Every referenced raw connector payload, checked against its retained SHA-256
  and byte count. Missing, corrupt or unsafe references fail the candidate.
- A manifest and independently recomputed verification result.

All bundle files are private: job payloads and session hashes can be present in
the selected database. Windows uses the existing owner/SYSTEM ACL protection;
POSIX uses owner-only file and directory permissions. Vault files and sibling
pairing credentials are not copied. Hashes detect changes; they do not encrypt or
authenticate a bundle against an attacker who can replace all its contents.

A successful result says `migration_preparation_only`, `source_access:read_only`
and `backend_changed:false`. Preserve a failed candidate's protected diagnostics
and select a new directory for a retry. Existing bundles are never overwritten.

Observed on 2026-10-31: the explicit preparation command against
`runtime/connections/product/core.sqlite3`, followed by a separate
`--verify-bundle` invocation, passed for
`runtime/migrations/connections-20261031-prepare-1`: **16 tables, 3,121 rows,
six raw payloads totaling 34,139,139 bytes**, integrity and foreign-key checks
`ok`, backend unchanged. Its manifest and verification remain private under that
directory. Fourteen migration tests passed, including a committed WAL snapshot
with a concurrent source commit, exact typed rows and sequence allocation after
deletion. This is a point-in-time bundle, not a count of distinct sporting events.

## MariaDB staging and remaining work

The offline SQL writer is now available for the exact audited sixteen-table
product schema. It consumes a successfully revalidated preparation bundle:

```powershell
.\runtime\server-env\Scripts\python.exe -B scripts\build_mariadb_migration.py `
  --bundle runtime\migrations\connections-20261031-prepare-1 `
  --output runtime\migrations\connections-20261031-mariadb-sql-1 `
  --schema dragonhydra_migration_connections_20261031_a

.\runtime\server-env\Scripts\python.exe -B scripts\build_mariadb_migration.py `
  --verify-sql runtime\migrations\connections-20261031-mariadb-sql-1
```

Those example output/schema names identify the already-created candidate; choose
new names when generating another candidate. This command never connects to a
database. Fourteen writer tests passed, and independent regeneration verified the
real candidate: sixteen tables, 3,121 rows, five foreign keys, ten immutability
triggers and 3,159 ordered statements. Its status is
`mariadb_staging_script_only`, with `executed:false` and `cutover:false`.
SQL SHA-256:
`ac7801123b0eb48b4ed341fcea37b651cd6d9f2e7484f26b5d73618bbac8d82b`.

The writer preserves complete UTF-8 identity bytes as bounded VARBINARY, refuses
oversized keys or incompatible SQLite storage types, uses signed BIGINT and
round-trip-checked DOUBLE literals, retains nullable uniqueness and restores
AUTO_INCREMENT high-water marks. It produces hashed `migration.sql` and
`statements.json`; verification recomputes their contents from the original
snapshot rather than trusting new file hashes alone. It refuses an unaudited
schema or trigger. Creating/loading a schema remains a separate explicit test.

That separate roundtrip was executed successfully on the existing project-owned
MariaDB 10.11.16 instance, port 18741, using the protected configuration through
PHP mysqli. Only the newly created
`dragonhydra_migration_connections_20261031_a` schema received the reviewed
statements. The original admin/core schemas and SQLite authority remained in
place. The exact command and source bindings are recorded in
`build/connections/evidence/mariadb-roundtrip-20261031-a/verification.json`.

The test compared all **3,121 rows across sixteen tables**, including 27,634 text
values, 3,176 integers, 126 NULLs, 111 binary64 values and two BLOBs. Prepared
binary-protocol reads preserved exact text/BLOB bytes and double bits. It also
verified five foreign keys, ten triggers, complete indexes and sequence values
2141/135. Seven rollback-only probes tested duplicate keys, a missing composite
foreign key, immutable updates/deletes, idempotency uniqueness, multiple NULLs,
and case/trailing-space identity. The private test schema is retained for review;
this proves the staging roundtrip, not an application backend switch.

The existing MariaDB 10.11.16 CLI is available; the Python server environment has
no installed MySQL driver. The verified test uses the existing private PHP runtime
and creates no plaintext credential defaults file or password command argument.
A future application backend must
preserve binary identity comparisons, nullable uniqueness, full key lengths,
signed 64-bit integers, exact text/BLOB bytes, immutable-table behavior and sequence
allocation. The application also uses SQLite-specific transactions, placeholders
and upserts. The staging test proves retained values and constraints survive the
import. Application read/write semantics, worker recovery on MariaDB and a
controlled authority switch remain unverified.

## Optional context profile

Preparation and staging retain the original `core-1` sixteen-table format and
also accept `core-context-1`: the exact core schema plus the existing
`cognitive_records` and `cognitive_receipts` tables and their four immutable
triggers. Both tables and all expected definitions must be present. A partial or
changed extension fails validation. Reads do not initialize this profile.

The optional profile emits version-two manifests with an explicit
`schema_profile`; historical version-one manifests remain readable and their
SQL regeneration is byte-identical. The context key capacities are 64 bytes for
kind and natural key and 128 bytes for record/receipt IDs. Oversized identities
fail without truncation. The receipt foreign key and the distinct cognitive
immutability messages survive migration. Parent and acquisition references
inside JSON require application validation; they do not acquire SQL foreign keys.

On 2026-10-31 the private synthetic candidate under
`runtime/migrations/context-foundation-20261031-synthetic-{prepare,sql}` passed
Python and PHP offline verification, followed by a real staging import into the
new `dragonhydra_migration_context_foundation_20261031` schema on the existing
owned MariaDB port 18741. All **18 tables, 17 synthetic rows, 14 triggers and 14
rollback probes** passed native value, index, receipt-FK and exact-trigger checks.
An independent review confirmed unchanged SQLite source tables and all five
historical bundle/script artifact hashes. Evidence is in
`build/connections/context-foundation-20261031/mariadb-roundtrip-r1`.

This fixture verifies optional persistence and migration. It contains no real
StatsBomb event or lineup acquisition, and application authority remains SQLite.
