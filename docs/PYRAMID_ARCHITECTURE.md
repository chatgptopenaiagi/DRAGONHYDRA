# Pyramid architecture

The Pyramid is a responsibility model for DRAGONHYDRA, not eleven deployed services. Layers may share a Python process while retaining typed boundaries. Dependencies should flow through evidence, request and result contracts; engine-specific objects do not become the universal domain model.

## Layer ownership

| Layer | Responsibility | Inputs and outputs | Genesis status |
| --- | --- | --- | --- |
| P0_XAMPP_FOUNDATION | Apache, PHP, MariaDB, local HTTP, configuration and future ingestion/admin surfaces | Local requests, service configuration, SQL connections and operational records | Existing XAMPP retained; Python SQL proof implemented. New HTTP adapter not implemented. |
| P1_OPERATIONAL_STATE | Current fixtures, clubs, players, lineups, events, odds, source state, jobs and live state | Validated evidence becomes version-referenced current projections | Role designed; no DRAGONHYDRA production schema or migrations. |
| P2_ANALYTICAL_MEMORY | Immutable revisions, event/feature history, research/training datasets | Append-oriented Parquet manifests and DuckDB analytical views with lineage | Role designed; analytical packages/pipelines deferred. |
| P3_FEATURE_FACTORY | Strict temporal/as-of form, player availability, lineup strength, market state, weather, travel, injuries, suspensions and quality/freshness features | Evidence-version set + cutoff + feature definition -> values, missingness and provenance | Donor concept retained; feature port deferred. |
| P4_MATH_ENGINE_ROOM | Statistics, probability, Poisson, Dixon-Coles, Elo, Glicko, Bayesian methods, calibration, optimization, time series, graphs and useful symbolic math | Comparable typed requests/results with assumptions and precision | Protocol/result prototypes implemented; concrete engines deferred. |
| P5_AI_GPU | PyTorch tensors, embeddings, sequence/event/odds/meta models under Python 3.14 | Versioned datasets and model artifacts -> predictions/representations | Existing compute stack diagnosed; no new trained model. |
| P6_SIMULATION | Match, season, scenario and uncertainty simulation | Engine distributions, constraints, random seeds and scenario definitions -> sampled outcomes | Design only. |
| P7_PREDICTION_TRIBUNAL | Model comparability, disagreement, staleness, missing evidence, calibration, weighting and explanation | Prediction records with evidence/cutoff lineage -> assessment and research needs | Design only; distinct from numerical Math Tribunal. |
| P8_ODDS_ENGINEERING | Fair probability/odds, implied probabilities, overround, market comparison/movement, disagreement, value gaps and uncertainty bands | Calibrated model distributions + eligible comparable market observations -> interpretable differences | Design only; no execution or guaranteed-profit claim. |
| P9_EXPLANATION | Reasons, source lineage, model disagreement, timelines, visualization and web presentation | Results plus reason codes and evidence versions -> human-readable account | Documents and diagnostic JSON only; no product UI. |
| P10_UNCERTAINTY_FEEDBACK | KNOWN, UNKNOWN, STALE, CONFLICTING, MISSING, SUSPICIOUS and targeted questions | Unresolved evidence/model findings -> bounded Hydra research request | Evidence-state prototype exists; automated question prioritization deferred. |

MariaDB is suited to appropriate P1 transactions. DuckDB and Parquet serve P2/P3 analysis. Python orchestrates P3–P10; NumPy/SciPy/SymPy/PyTorch are candidate engines with different responsibilities. Apache/PHP present or adapt requests; they do not execute a long training job in an HTTP request. See [DATABASE_ROLES.md](DATABASE_ROLES.md) and [MATH_ENGINE_ROOM.md](MATH_ENGINE_ROOM.md).

## Evidence boundary and identities

Implemented prototypes reside in [medusa/evidence.py](../src/dragonhydra/medusa/evidence.py), with Hydra-facing exports in [hydra/contracts.py](../src/dragonhydra/hydra/contracts.py).

| Contract | Present meaning | Future extension boundary |
| --- | --- | --- |
| SourceIdentity | Stable source ID and name | Authorized acquisition route, source dependence, coverage and contextual quality. |
| EntityIdentity | Entity type and stable ID | Cross-provider mapping, aliases and ambiguity resolution; never infer identity solely from display name. |
| HydraEvidencePacket | Packet ID, source/entity, predicate, scalar value, expected/confirmed/observed kind, temporal evidence, confidence and provenance IDs | Structured payload schema/version, receipt hash and ingestion policy. No collection code yet. |
| TemporalEvidence | Five evidence timestamps and explicit availability-proof reference | Timestamp precision/origin policy and a distinct quarantine contract for unknown chronology. |
| EvidenceConfidence | Finite score in [0,1] and rationale | Contextual, independently assessed uncertainty; current score is not statistical calibration. |
| MedusaEvidenceVersion | Immutable version ID, packet, validation reasons and intrinsic status | Durable append-only version store, validation policy/version and content fingerprint. |
| EvidenceConflict | Two same-claim versions, conflict availability/proof and reason | Resolution workflow preserving both claims and the resolution's own chronology. |
| EvidenceSupersession | Same-source/entity/predicate replacement link | Durable audit metadata; unrelated sources cannot silently supersede one another. |
| AsOfRequest | Entity/predicate, optional source, target_as_of_at and an explicit availability boundary | The target and cutoff policy belong to the query, not mutable evidence. |

The in-memory ledger forbids cycles and branching/merging supersession chains in this prototype. A replacement must advance availability. Once a replacement expires, an older superseded assertion does not become current again. Independent sources remain independent claims; disagreement has no automatic winning source.

## Six temporal meanings

| Timestamp | Meaning | Historical use |
| --- | --- | --- |
| event_at | When the assertion concerns real-world activity; may concern a future planned fixture | Does not prove that its value was known. |
| observed_at | When this exact assertion was observed/received | Preserves receipt chronology, not inferred publication history. |
| available_at | First proven time this system could use this exact revision | Must be at or before the query cutoff. |
| updated_at | Revision/update time represented by this version | Does not mutate or backdate older versions. |
| expires_at | Optional policy-derived end of freshness | Current eligibility uses an exclusive upper boundary. None means no expiry is encoded, not an assertion of eternal factual validity. |
| target_as_of_at | Evaluation/replay cutoff on AsOfRequest | Changes per request without rewriting evidence. |

All prototype timestamps require timezone awareness. The implemented conservative receipt policy requires `available_at >= max(observed_at, updated_at)`. It does not support asserting historic availability earlier than its recorded observation. A future archival-proof model would need separate verified historical receipt semantics and tests before permitting that case.

Default eligibility is `available_at <= target_as_of_at < expires_at` when an expiry exists. Exact-boundary availability is accepted with `AvailabilityBoundary.AT_OR_BEFORE`; the implemented `STRICTLY_BEFORE` request policy instead requires availability strictly before the target. The same policy applies to conflict availability and which replacements can supersede earlier versions. Expiry is always evaluated at the target. Unknown availability is excluded rather than filled using event time. The current packet constructor requires availability and proof; incomplete raw observations need future quarantine storage.

For future score-derived pre-kickoff features, retain the donor's stricter explicit policy `result_available_at < target kickoff_at`, including equality rejection, using the implemented `STRICTLY_BEFORE` option. Generic default eligibility does not weaken that feature policy. Feature metadata must identify the policy and cutoff so an auditor can reproduce the difference. The FeatureFactory itself is still deferred.

## Three synthetic cases

The code fixtures in [test_evidence.py](../tests/test_evidence.py) use synthetic UTC times relative to 2026-09-24 12:00. They contain no external sports data.

| Case | Event / observation / update / availability | Query outcome specified by tests |
| --- | --- | --- |
| Delayed final score | Event +0 min; observation +12; update +1; availability +15; no expiry | At +14 the result is missing and future evidence is rejected. At +15 the generic ledger may select it. |
| Corrected goal | Original event +0, available +2; corrected same event, observation +7, update +6, available +8 | Earlier queries retain original value 1; from +8 the replacement value 0 applies. Original version remains in the ledger. |
| Expected becomes confirmed goalkeeper | Expected assertion available +0 for event +60, expires +60; confirmation available +30 for event +60 | At +29 use only the expectation. At +30 select the confirmation. A future event time does not make the already-known expectation invalid. |

These examples test contracts; they do not establish a live replay database or an external source's chronology. Executed test results are recorded in [PROGRESS.md](PROGRESS.md).

## Uncertainty and the return to Hydra

| State | Interpretation | Future targeted question |
| --- | --- | --- |
| KNOWN | Selected version is eligible and passes this prototype's validation | Is the relevant evidence coverage sufficient for the intended decision? |
| UNKNOWN | An assertion exists but validation remains unresolved | Which fact or definition would make this assertion usable? |
| STALE | Relevant active evidence is outside its freshness interval | Has the permitted source published a newer version? |
| CONFLICTING | Eligible sources/claims disagree or an explicit conflict is known | Which independent, relevant source can explain the difference? |
| MISSING | No eligible evidence satisfies the request | Is the field not yet published, uncovered or inaccessible? |
| SUSPICIOUS | Validation raises a provenance/quality concern | Can the specific assertion and its provenance be independently checked? |

Only KNOWN selections are marked usable by the prototype. STALE, MISSING and CONFLICTING are query-context results rather than permanent labels written onto a version. The other states may be intrinsic version annotations. A query's state is not a universal verdict about a real-world fact.

Future research requests should carry question ID, originating assessment, entity/predicate, target cutoff, missing/conflicting evidence references, permitted source candidates, priority rationale, deadline, resource budget and stopping rule. Newly obtained evidence creates a new version and recalculation record. It must never silently improve an already-completed historical forecast with later knowledge.
