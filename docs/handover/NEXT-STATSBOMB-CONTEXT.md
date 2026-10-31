# Proposed single-match StatsBomb context

2026-10-31 — Selected next-cycle contract. Persistence/migration foundation is verified: 415 regression tests, 14 independent acceptance groups and a real synthetic 18-table MariaDB staging roundtrip passed. Exact retained parent/document binding validation also passed 22 tests and five independent real-parent checks. The packaged A4 source snapshot, installers and existing migration artifacts remain frozen; no event/lineup dataset was downloaded. Bounded parsing/projection reconstruction and worker claim fencing are active; acquisition follows after those gates pass.

Prefer reusing the generic append/receipt mechanism and two table definitions in [cognition/memory.py](../../src/dragonhydra/cognition/memory.py#L61), with a small context wrapper and narrowly scoped persistence improvements. Do not create a second raw-payload store or put context into ordinary match observations. This introduces an opt-in eighteen-table schema profile while retaining the existing sixteen-table migration path.

| Existing capability | Reuse and limits |
|---|---|
| [memory._append](../../src/dragonhydra/cognition/memory.py#L196), cognitive records/receipts | Canonical payload hash, immutable rows, idempotent natural keys and receipt after the record commit. `_record_hypothesis` already demonstrates numbered revisions and predecessor links. |
| [market_store._import_records](../../src/dragonhydra/market_store.py#L244) | Reuse its recovery pattern: an existing durable record with no receipt can receive a later, verified receipt. Its market normalization and correction scopes are unsuitable for event context. |
| [connectors.Store](../../src/dragonhydra/connectors/store.py#L198) and retaining Transport | Keep exact raw files and same-provider acquisition verification. Reuse once-per-document body/hash checks and immutable acquisition metadata bindings; do not copy the raw JSON into another database table. |
| Ordinary connector observations, public fixture records, job results | Not context stores. Enriching the latest match observation is erased by a subsequent metadata import; fabricating another match changes match counts. Job results are mutable workflow state. Public fixture and cognitive hypothesis APIs impose unrelated domain contracts. |

The memory primitive is **not a drop-in API**: `_append`, `_existing` and `_as_of` call schema DDL; `_as_of` recognizes only six cognitive kinds; `UNIQUE(kind,natural_key)` rejects changed content under one unchanged key; a missing receipt raises `MEMORY_RECEIPT_MISSING`. [Hypothesis revision handling](../../src/dragonhydra/cognition/memory.py#L621) is a useful pattern, but allocating a revision outside the write transaction is insufficient for concurrent context writers. Existing cognition behavior must keep its tests and public response shape.

**Bounded acquisition contract.** Accept only explicitly selected native match `3869685`, competition `43`, season `106`, teams Argentina `779` / France `771`. Resolve and freeze the actual parent observation ID from the chosen state; do not substitute the latest observation later. Reconstruct that parent from its retained match-list bytes/native match ID and verify its source hash and participant IDs.

Use only these registry-owned resource templates:

- `https://raw.githubusercontent.com/hudl/open-data/master/data/events/3869685.json`
- `https://raw.githubusercontent.com/hudl/open-data/master/data/lineups/3869685.json`

The proposed limit is two application GETs **per job**, each at most 8 MiB, no bulk traversal, no 360 data. Use the existing bounded Transport. Disable automatic HTTP retries for this new job kind, leaving current provider-sync retries unchanged; an explicit new job can retry. A strict two-network-request ceiling also requires rejecting redirects for this context operation rather than following them. Both complete documents must validate before a context revision is written. A missing/invalid document leaves the previous context and base match untouched; retained complete acquisition bytes remain diagnostic evidence.

Validate a bounded event array (proposed 20,000 rows), unique native event UUIDs and indexes, exact native participant IDs, and the two native lineup team IDs (proposed 100 squad entries per team). Preserve optional player IDs and source period/timestamp/minute/second fields without inventing absent values. The first statistic is explicitly **counts of retained event rows by native team, period and source event type**, not an official match statistic. Show source squad entries; infer no starting role, possession, xG, score, winner, UTC instant or betting settlement. Keep the base match's existing status and scores. Unknown format/type shapes fail specifically; missing context never means zero.

**Context record contract.** Kind `source_context` uses the generic `source-context/1` envelope and a source-specific `statsbomb-context/1` parser/projection version. The immutable payload contains:

- provider/native match ID, context scope hash, positive revision number and `supersedes_record_id`;
- exact parent observation ID plus its retained source hash and validated native identity snapshot;
- exactly two role-labelled bindings (`events`, `lineups`), each with acquisition ID, SHA-256, original/resolved URL and capture clock;
- parser/transformation version, observed row counts and bounded native projections; event pages can be regenerated from the hash-verified retained document rather than creating event-row tables.

The raw acquisitions already live in `connector_acquisitions`; the payload references those existing rows. As with A4 quote bindings, validate and later re-resolve exact acquisition IDs/provider/hash/metadata, never a newest matching hash. The generic JSON tables do not provide SQL foreign keys into those three parent/acquisition references: application validation and fail-closed reads are required. If physical cross-table FKs are required, choose a dedicated context relation design instead; that is a larger schema contract, not an incidental extra table.

Compare the **latest revision only** using a semantic fingerprint of parent ID, parser version and both role-specific payload hashes/native projections. Exclude job ID, new acquisition IDs and capture/receipt clocks from this comparison. Same bytes under the same parent reuse the original context ID/receipt/bindings. Different content advances the revision, including A → B → A. Hash the scope and revision into the natural key; do not use lifetime content uniqueness or order revisions by wall-clock/hash tie-breaking. Scope lookup, pending-receipt checks, predecessor validation and record insertion must share one `BEGIN IMMEDIATE` transaction through the reused persistence primitive.

Commit the record first; take its acknowledgement clock afterward; append and commit the immutable receipt separately. Return a second acknowledgement after receipt commit. GET joins only records with receipts. After a crash between commits, validate the durable pending record and original bindings and append a receipt at the recovery time, without another GET or backdating. Do not advance a scope past an unresolved pending revision. These remain receipt-bounded operational clocks: the stored acknowledgement precedes the receipt transaction's exact visibility, so do not claim STRICT_PIT replay. This is the limitation already stated in the [memory module](../../src/dragonhydra/cognition/memory.py#L1).

**Independent reads.** Separate initialization/write helpers from pure SELECT readers. A context GET must perform no schema creation, HTTP, model call or import. A missing context table returns `not_requested`; proposed context availability values are `available`, `not_requested`, `parent_changed`, `unavailable`. Workflow statuses remain existing queued/running/succeeded/failed/cancelled/interrupted values; base record statuses remain unchanged. Preserve the existing cognitive six-kind response by filtering its reader explicitly, and provide a separate source-context reader rather than treating context as a model/hypothesis.

Store context independently of the metadata-sync path. Unchanged metadata imports preserve its parent ID and context. If a genuine metadata revision changes the parent, retain the old context at its immutable ID and report `parent_changed` for the new parent until an explicit context job revalidates it. Never delete or silently attach context from a different parent revision.

**Migration compatibility must precede enabling writes.** Current [preparation validation](../../src/dragonhydra/migration.py#L118), [SQL schema signature](../../src/dragonhydra/mariadb_migration.py#L176) and [PHP verifier](../../tests/installation/mariadb_roundtrip.php) deliberately accept only the audited core profile. Do not expand a permissive table allowlist and assume compatibility.

| Profile | Required handling |
|---|---|
| `core-1` | Existing sixteen tables and ten immutable triggers. Continue reading historical preparation/staging v1 manifests without a profile field. Preserve their existing regeneration output and hashes; do not rewrite old bundles. |
| `core-context-1` | Exact core profile plus existing `cognitive_records` and `cognitive_receipts` definitions and their four immutable triggers: eighteen tables, fourteen immutable triggers. Emit a version-two preparation/staging manifest declaring the profile. Reject partial or unknown extensions. |

The proposed new indexed-text capacities are kind 64 bytes, record ID 128 bytes, natural key 64 bytes, and receipt record ID 128 bytes; the natural key is a SHA-256 scope/revision key, not an unbounded JSON string. The complete unique `(kind,natural_key)` key plus primary-key suffix is at most 256 bytes, below the existing 3,072-byte budget. Preserve the receipt FK, exact trigger messages and the existing typed INTEGER/REAL/TEXT/BLOB mappings. Update both Python and PHP profile dispatch, literal/statement validation and metadata/parity checks. Keep `cutover:false`; this adds no MariaDB application backend.

Before payload retrieval, verify synthetic context roundtrips for both profiles, old v1 bundle/script hashes, all existing cognition tests, unknown-kind isolation, read-only GETs, duplicate bytes/new receipts, correction/reversion, competing writers, crash between commits, missing/corrupt/raw/out-of-provider dependencies and metadata-sync retention. Only afterward run the single selected match's two bounded GETs and verify its API projections. Existing A4 installed checks and the [five-source retained replay](../../build/connections/evidence/provenance-retained-20261031-r3/verification.json) remain historical evidence, not proof of this proposed context feature.

Official source layout: [StatsBomb Open Data README](https://github.com/hudl/open-data/blob/master/README.md), with events/lineups named by match ID. Format references: [Open Data specification](https://github.com/hudl/open-data/blob/master/doc/StatsBomb%20Open%20Data%20Specification%20v1.1.pdf) and [lineup specification](https://github.com/hudl/open-data/blob/master/doc/Open%20Data%20Lineups%20v2.0.0.pdf). Preserve StatsBomb attribution. Their general event and squad fields were inspected from project-local copies extracted by the existing Tika 4.1.0 / Java 21.0.8 tools. Evidence is in `build/connections/statsbomb-binding-20261031/official-specs/verification.json`. These are two documentation GETs, with no event/lineup dataset retrieval. The event specification explicitly permits absent team/player fields when inapplicable; preserve absence rather than assigning a participant. The lineup documents contain inconsistent name-type labels; retain textual names as established by the main player-name specification, existing match adapter and official SDK examples. Event-specific sporting metrics remain outside this feature.

Foundation scope: a required trusted dependency validator is an internal extension
point, not proof that StatsBomb parent/raw bindings have been implemented. There
is no context route, scheduled operation or automatic live-state schema change
in this increment. Source-specific validation and acquisition still require their
own tests. `Transport(..., follow_redirects=False)` is now available: sixteen
transport tests passed, including actual urllib redirect processing with one
request for each rejected redirect and unchanged default redirect behavior. These
tests use an in-process HTTPS fixture; they make no provider network request.

The foundation exposes `source_context.append`, `recover` and read-only `latest`
with generic payload version `source-context/1`; a trusted callback is mandatory.
It preserves original receipts/bindings for same-byte duplicates, allocates
correction/reversion revisions atomically, recovers missing receipts and rejects
backward acknowledgements before a predecessor's usable clock. Existing six-kind
cognition responses remain isolated. Exact schema definitions are reused through
`cognition.memory.SCHEMA_SQL`. Evidence and remaining boundaries are recorded in
`CONTINUOUS-PROGRESS.md` and
`build/connections/context-foundation-20261031/acceptance-r2/verification.json`.

**Worker integration design, not yet enabled.** Disabling transient retries alone
does not enforce the two-request budget: interrupted/stale jobs can be reclaimed.
Capture the existing job attempt counter inside the claim transaction and fence
heartbeats, journal writes, context publication and finalization by job ID,
running state and that counter. An obsolete worker cannot finalize a newer claim.
An implementation of this general worker fix is in progress without schema changes.

The later context operation needs one deterministic `connector_attempts` journal
per job, with a distinct operation. Reserve each of the two role intents under
`BEGIN IMMEDIATE` before HTTP; an incomplete reservation never permits another
request. Commit the exact acquisition row and role completion together after raw
retention. Lost ownership rolls both back and leaves the intent consumed. Check
claim/cancellation again inside context persistence transactions. Recover pending
context and reuse completed role receipts before any GET. Uncertain outcomes
require an explicit fresh job; they never reset the old budget. Ordinary provider
test/sync retains its existing three-attempt behavior. Provider health must filter
the context journal because current successful retrievals assume `retrieved_rows`.
Tests must cover lease races, cancellation and crashes at every commit boundary.
