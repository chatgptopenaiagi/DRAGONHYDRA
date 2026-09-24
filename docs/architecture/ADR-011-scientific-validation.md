# ADR-011: evaluation discipline and explicit temporal reconstruction

Date: 2026-09-24. Status: ACCEPTED for experimental V1 Scientific Validation Spine Phase A.

Decision: introduce explicit STRICT_PIT and RECONSTRUCTED_PIT contracts, a small canonical identity registry, chronological baseline evaluation and bounded prospective acquisition. Keep actual capture clocks separate from assumed historical availability and simulated prediction issuance. Add evaluation discipline as the fourth practical law.

Reason: the 380 historical fixtures were captured in 2026; their original publication history cannot be recovered from final scores. Later modeling needs falsifiable evaluation before sophistication. Current raw bytes are retained, so historical replay can use existing evidence without another source fetch.

Alternatives: backdate imports (rejected as false provenance); wait until V9 to evaluate (rejected because earlier models would lack a test); build a feature store, new database or model framework now (deferred without measured need).

Evidence: [scientific report](../SCIENTIFIC_VALIDATION_SPINE.md), [safe summary](../evidence/scientific-spine-summary.json), temporal/entity/evaluation tests. Existing SQL normalized observations remain authoritative and unchanged. Local identity/report artifacts are experimental derived research, not a second intelligence warehouse.

Trade-offs: date-only reconstruction supports a demonstration, not genuine historical decision proof. Scoped name/round identity cannot resolve arbitrary cross-provider ambiguity. A filesystem acquisition ledger is sufficient for one bounded source; it is append-only by application convention, not tamper-proof storage. A first capture does not demonstrate sustained scheduled operation. No dependency or storage technology is added.

This decision supplements the master roadmap; it does not supersede historical evidence, advance the conceptual stage beyond V1, or change v0.1.0-alpha.
