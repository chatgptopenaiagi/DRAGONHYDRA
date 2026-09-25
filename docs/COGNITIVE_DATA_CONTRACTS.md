# Cognitive data contracts

The [contract implementation](../src/dragonhydra/cognitive/contracts.py) uses frozen typed dataclasses, strict deserialization and canonical JSON hashes. Contracts are project-side data; they do not create unrestricted AI tools or make AI conclusions external evidence. See [progress](COGNITIVE_PROGRESS.md) for measured status.

| Contract | Meaning and required boundary |
| --- | --- |
| SystemStateSnapshot | Deterministic sanitized current state, explicit cursor/context, validated input summaries, permitted capabilities, provenance and state hash. |
| StateDelta | Prior/current snapshot comparison preserving the two input identities and temporal context. |
| EvidenceDelta | Added/changed/removed evidence references or hashes; a detected change is not independently accepted new evidence. |
| ModelDelta | Comparable model outputs and movement with model identity and input references. |
| UncertaintyDelta | Comparable uncertainty before/after with metric/reason context; reduction alone is not accuracy gain. |
| CognitiveRequest | Explicit actor/task, bounded state input and requested/allowed capability context. |
| CognitiveResponse | Actor/model/runtime identity, input/output hashes, non-evidence conclusions, short rationale, reason codes and structured failure/result. |
| Hypothesis | Explicit HYPOTHESIS conclusion and supporting/contradicting references; never an observation setter. |
| ResearchNeed | Missing knowledge/question, state hash, hypothesis references, provenance and requested capability. Priority/deadline scheduling remains a later integration concern. |
| CalculationRequest | Named permitted calculation, exact input references and reproducibility context. |
| AcquisitionRequest | Bounded proposed HYDRA acquisition subject to independent source policy and MEDUSA. |
| ActionProposal | Typed desired action, reason codes, references and requested capability without execution authority. |
| ActionDecision | Allow/reject/blocked decision, capability constraints and explicit reasons. |
| ActionResult | Actual operation status, provenance references, failure state and OPERATION epistemic label. Cost/latency measurements belong in LearningFeedback. |
| ReconciliationReport | Separate actor positions, comparable state/metric references and AGREEMENT/PARTIAL_AGREEMENT/DISAGREEMENT/INSUFFICIENT_EVIDENCE/NOT_COMPARABLE status. |
| LearningFeedback | Before/after predictions/uncertainty, observed outcome when available, measurable evaluation and usefulness context. |
| CapabilityDescriptor | Allow-listed action, availability, bounds, required evidence/policy gates and failure behavior. |
| CognitiveCycleReceipt | State hash, request/response/action hashes and explicit completion/failure status; future cycle integration links further result/feedback records. |

Relevant structures carry `schema_version`, `created_at`, `as_of_at`, `temporal_mode`, source/provenance references, input/state hashes, actor, epistemic state, bounded confidence where meaningful, reason codes, allowed actions, requested capability, result status and failure state. Metadata is shared where that prevents contradictory duplicate fields. Unknown values are explicit and never guessed.

`Metadata` owns schema version, creation/as-of timestamps, temporal mode, `ActorIdentity`, source references, input hashes and reason codes. `ActorIdentity` owns role and model/runtime identity/version. Records expose `to_dict()`, `to_json()`, `from_dict()`, `from_json()` and `digest()`. `SystemStateSnapshot.state_hash` is derived rather than caller-invented; `CognitiveResponse.output_hash` identifies its canonical serialized response. Helper records include EvidenceSummary, SourceSummary, ModelSummary, UncertaintySummary, StatusSummary, Position, ObservedOutcome, CalibrationBin and CalibrationMeasurement.

Serialization must preserve enum meanings, reject unexpected executable/hidden-reasoning fields and use deterministic canonical content for hashes. A newly generated timestamp is an explicit input; deterministic output is claimed only for identical controlled inputs including timestamps. Reference order and canonical ordering rules must not leak secret values or silently relabel evidence.

The snapshot can describe SYSTEM, TEMPORAL CURSOR, FIXTURE, EVIDENCE, SOURCES, FEATURES, MODEL FORECASTS, TRIBUNAL DISAGREEMENT, SIMULATION, MARKET, UNCERTAINTY, RESEARCH NEEDS, CHAIN BREAKS, ACTION HISTORY, CAPABILITIES and HEALTH. Missing parent stages stay unavailable. Persist only concise conclusions and reason summaries; hidden chain-of-thought is prohibited.

[`state_delta(previous, current, created_at=...)`](../src/dragonhydra/cognitive/snapshot.py) compares compatible snapshots with the same fixture and temporal mode and a nondecreasing as-of cursor. It retains prior/current hashes, added/removed/changed evidence references, changed model forecasts, uncertainty values and changed section names. It compares structured values rather than interpreting source prose or inferring causality.

The initial LearningFeedback validates HOME/DRAW/AWAY distributions and the declared `MULTICLASS_BRIER` metric. Reported before/after model errors and accuracy gain must equal the calculated scores for its validated observed outcome. Accuracy/quality claims require matching fixture identity, both distributions, immutable forecast references and ordered forecast clocks before the outcome event. Outcome availability must respect the feedback cursor and temporal mode. `both_wrong` compares the highest-probability outcomes with the actual result; tied maxima require UNKNOWN. Usefulness attributions require action/new-evidence references; a positive usefulness flag also requires measured uncertainty reduction or score gain. These conditions do not prove causal attribution or a calibrated source reliability score.

CalibrationMeasurement records model/evaluation/protocol identity, outcome class, unique observed-outcome references and bounded bin counts/mean probabilities. It computes binned one-vs-rest expected calibration error (ECE). The minimum two-outcome cohort is a structural gate, not an adequate sample-size or statistical-significance claim. A reported calibration gain must equal the before/after ECE difference on the identical cohort/protocol/class and respect the feedback cursor. Neither calibration arithmetic nor changed AI prose triggers automatic model adaptation.
