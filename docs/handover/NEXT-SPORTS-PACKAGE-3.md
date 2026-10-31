# Optional grounded context in offline sports packages

2026-10-31. This design has a source implementation: exact context `by_id`, explicit `build_context_package`, strict version dispatch, three grounded count facts, fact-ID output and trusted service citations. API/UI defaults retain package/2, with separate explicit context selectors/actions. Full548 source tests,9 probe tests and8 synthetic Edge groups passed. One actual existing Qwen/source API-worker probe accepted package/3 and selected F1 (finished-status, E1-only citation/full4-IDmanifest); real model selection of a C1 count remains unproven. No persistent model settings changed; owned runner/API stopped cleanly and retained source hashes stayed exact. A5-r2 installed repair/context verification belongs to the preceding snapshot and does not establish installed package/3 acceptance. Source evidence is under `build/connections/sports-package-3-20261031`, actual model proof in `qwen-api-r1/report.json`; exact-reader independent receipt is under `build/connections/context-record-reader-20261031/acceptance-r1`.

Prefer an additive, opt-in package constructor and strict version dispatch. Keep `build_package(product, match_id)` and `sports-evidence-package/2` unchanged, including package bytes/hash, existing prompt/output grammar, default Explain, local-model settings and deterministic fallback. The first new constructor should require an explicit verified `context_record_id`; automatic discovery and UI opt-in can follow after grounding tests pass.

**Useful smallest payload.** Add exactly three contextual facts: the retained event-row count and the source squad-entry count for each native team. These describe rows in verified public documents. They establish no official match statistic, starting role, possession, xG, score, winner, settlement or prediction. Keep the current 16 KiB package limit. Do not copy the complete 181-group projection, event pages, player lists, parent `original` row or raw response bodies into the model package.

Proposed package/3 shape (field layout, with verified-data examples):

```text
schema_version: sports-evidence-package/3
event: existing package/2 event fields, reconstructed from exact E1
evidence:
  E1: unchanged parent observation metadata
  C1:
    kind: source_context
    id: exact source_context:<sha256> record ID
    record_sha256: immutable cognitive-record content hash
    parent_observation_id: E1.id
    parser_version: statsbomb-context/1
    received_at, persisted_at, usable_at: exact context receipt clocks
    documents:
      events: exact provider/acquisition ID/hash/URLs/capture clock
      lineups: exact provider/acquisition ID/hash/URLs/capture clock
context_summary:
  event_rows: 4407
  squad_sizes: [{team_id: 771, team_name: France, entries: 24}, ...]
allowed_facts:
  - {fact_id: F1, observation: existing status fact, evidence_aliases: [E1]}
  - ... existing event facts in their existing order ...
  - {fact_id: Fn, observation: trusted event-row-count template,
     evidence_aliases: [E1, C1]}
  - ... one trusted squad-entry-count template per native team ...
scope: fixed source-scoped limitations
package_sha256: canonical hash of all other package fields
```

The numeric examples are from the verified retained match, not constants in implementation. Recompute counts from the exact parser-validated context. Require integer types (`True` and `24.0` cannot stand in for `24`), event rows 0–20,000, exactly the two native team IDs and squad-entry counts 0–100. Preserve source team names and ordering. No current clock or new acquisition ID is invented during packaging.

**Grounding and immutable lookup.** Current [`validate_grounding`](../../src/dragonhydra/local_ai.py) reconstructs package/2 from the cited E1, so later match corrections do not replace queued facts. Apply the same rule to C1. [`source_context`](../../src/dragonhydra/source_context.py) currently exposes `latest`, not an exact record reader; [`statsbomb_context_view.context`](../../src/dragonhydra/connectors/statsbomb_context_view.py) is also a current-parent view. Neither is a valid queued-package resolver.

First add a pure SELECT, read-only exact context reader. Verify kind, canonical payload/hash, record-ID/natural-key identities, predecessor chain through the selected revision, receipt and clock ordering. Then run the existing full [`statsbomb-context/1` validator](../../src/dragonhydra/connectors/statsbomb_context_parser.py) on the selected record's exact parent and two retained acquisition IDs. Walk its predecessor references directly; unrelated later revisions, a later pending head or a later corrupt document must not substitute for or invalidate an otherwise intact selected revision. Missing/corrupt selected evidence fails closed. No schema creation, repair, provider GET, import or model call belongs in this reader.

Construction requires C1's parent observation ID to equal E1 exactly. Queued validation reconstructs the whole package from E1 + C1, without consulting latest match/context projections. C1 includes the two original role bindings even after identical bytes are captured again. A new context revision changes the package hash; old queued packages remain bound to their old IDs. A → B → A remains three revisions.

**Selection and citations.** Preserve package/2's output contract. For package/3, constrain the model to `{"fact_id":"F4"}` with a short ID enum and no extra properties. Resolve wording, numbers and citations from the trusted package after validation. Independent observation and citation enums would allow a true count to be paired with the wrong source.

E1 facts cite the existing immutable parent evidence URL. C1 facts cite the context record ID/hash, parent ID, and both role-labelled acquisition metadata URLs, hashes and capture clocks. Events/lineups clocks must never borrow the parent match-list receipt time. The current `/matches/{id}/source-context` URL is a mutable latest view: do not label it an immutable C1 citation. A separate authenticated exact-record route is a useful follow-up; stable parent/acquisition links plus the explicit context ID/hash suffice for the first core contract.

[`local_ai_service.explain`](../../src/dragonhydra/local_ai_service.py) currently initializes citations to E1 and ignores accepted-output citation metadata. It must resolve the selected package/3 fact's dependency citations into `evidence`, with all supplied input IDs represented in `input_manifest`. Keep `kind=local_llm`, `mode=constrained_source_fact_selection`, `observations` and existing UI badge semantics. Deterministic fallback still selects the first E1 status fact; missing configuration, timeout or rejected model output retain their current actionable codes. Grounding failure remains an error before inference, rather than a deterministic response carrying untrusted context facts.

If no verified matching context is selected, callers retain package/2. Do not represent unavailable context as zero counts. If an explicitly selected C1 cannot be verified, return a specific context/grounding error; never silently attach another revision. No new credential or runtime setup is needed to implement or test this contract.

Suggested first implementation gates:

- Existing package/2 tests and byte/hash/grammar fixtures remain unchanged, even when context is available.
- Package/3 adds only the three reconstructed context facts, stays below 16 KiB, and contains no raw arrays, private paths, keys or unsupported metrics.
- Rehashed count/type/name/parent/context/hash/role/clock/URL tampering, another match from the same match-list file, missing bytes and cross-provider receipts fail before settings decryption or inference.
- Exact queued E1/C1 remain valid after legitimate newer corrections and pending future revisions; selected evidence loss fails without substitution. Same-byte resync retains the original binding and hash.
- Fact-ID output rejects unknown IDs, duplicate keys, extra prose/fields and citation injection; accepted context selection returns the correct parent and two document citations.
- Optional-context reads perform no DDL/HTTP/model work and do not initialize the eighteen-table profile in an untouched sixteen-table state. Existing deterministic fallbacks and ordinary Explain remain unchanged.

Only after these synthetic/core gates should root select an API/UI opt-in and a fresh bounded probe using the existing offline Qwen runner. Do not claim package/3 runtime acceptance from package/2's prior LocalService tests.
