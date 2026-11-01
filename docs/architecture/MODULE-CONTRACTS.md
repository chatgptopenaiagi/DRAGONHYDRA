# DRAGONHYDRA module contracts

Source audit: 2026-11-01. Versions below identify transformations and schemas,
not a claim that all installed artifacts have one release version. API namespace
is `/dragon/api/v1`; installed source and runtime provenance must be verified
separately.

## Identity, evidence and clocks

Product match identity is the SHA-256 of the existing versioned identity tuple
`('fixture', source_id, fixture_key)` in `product.py`. Team and competition IDs
also retain source scope. Matching names is insufficient to merge providers or
join a quote/result. Revisions keep their own evidence IDs, raw hash and receipts.
The authoritative sports store for the workstation is its configured Product
SQLite database; Joomla account/content state remains in its configured MariaDB.

Every calculation gates input capture, receipt, persistence and usable clocks at
its stated cutoff. Source date-only/local timestamps remain imprecise. A later
local import is not evidence that the program knew an outcome at kickoff. Current
model generation and persistence use actual operation times; callers cannot
request a backdated operational forecast. Missing, ambiguous or incompatible
evidence produces a reasoned unavailable state.

## Transport and permission boundaries

| Boundary | Authentication and authorization | Operation scope |
|---|---|---|
| Browser → Joomla | Actual site/admin session, component ACL; Joomla form token for writes | Native component pages and fixed action handlers; no privileged pairing, bridge or provider credentials in HTML, JS, URLs or browser storage. Normal Joomla CSRF hidden inputs remain required; passwords are submitted only through the existing login form. |
| Joomla → kernel | Existing server-side protected bridge secret, method/path/body hash, user/role, time and nonce HMAC | Configured loopback `/dragon/api/v1`; reader versus permitted administrator; bounded cURL and no redirects/arbitrary proxy |
| Local desktop → kernel | Existing local pairing or session mechanism, endpoint metadata from its owning installation | Shared API; no reuse of Joomla password as backend credential |
| Android → kernel | Explicit server pairing/configuration | Shared API; application launch alone does not verify paired connectivity |
| Kernel → provider | Existing provider-specific vault/configuration and approved adapter | Only explicit sync/test or enabled scheduler; private keys never become bridge/pairing credentials |
| Kernel → optional AI | Protected server settings and frozen, validated evidence package | Explicit explanation job; unsupported/missing runtime returns honest fallback |

The generic existing `/jobs` input does not gain arbitrary internal command kinds.
New forecast/evaluation submissions use their own authenticated administrator
routes with an empty typed body and server-chosen fixed payload. Owner identity
and `Idempotency-Key` continue through `Jobs.submit`; reads/status observations
never submit work.

## Module definition and observation contract: `module-registry/1`

`GET /system/modules` returns schema version, registry version, as-of time,
installation identity, core state/summary and module entries. Each entry separates
the definition from its current observation, dependency statuses and fixed
operations. Definitions declare stable module ID, display name/kind/category,
source references, actual module/build version, required/optional dependencies,
implemented capabilities, configuration requirements, data domains and
verification references. Typed validation rejects duplicate/unknown references,
unimplemented operation claims and dependency cycles.

Observations carry installation/module identity, observation/expiry clocks,
implementation state, configuration state, runtime state, last success, sanitized
reason/code/metrics and evidence references. Runtime states are
`not_implemented`, `installed_not_configured`, `configured_unverified`, `ready`,
`degraded`, `unavailable` and `not_applicable`. Installed source is not a current
runtime observation. Missing, expired or wrongly associated supervisor evidence
cannot establish Apache/Joomla/MariaDB/client readiness. A database TCP probe is
not SQL authentication/schema acceptance; a desktop executable is not proof of a
running interactive session, and Android source/APK presence is not paired device
acceptance.

| Runtime state | Exact meaning in this registry |
|---|---|
| `not_implemented` | Contract vocabulary for an explicitly absent implementation; the current 18 definitions all map to source, so none is assigned this state merely because it has not run. |
| `installed_not_configured` | Implementation exists but its required local setup is absent: for example no cognition schema yet or no optional model configuration. No setup is performed by the read. |
| `configured_unverified` | Inputs/configuration or an implementation are present, but this observation has not proved execution. Odds/models, clients and configured AI do not become ready from a status read. Missing/expired external evidence also cannot prove readiness. |
| `ready` | Fresh direct evidence meets the module-specific condition and all required dependencies are ready. API request, readable authoritative schema/counts, worker state and validated supervisor checks each prove only their declared scope. |
| `degraded` | Direct evidence exists but a required dependency is unverified, a running job lease is stale, or the bound supervisor explicitly reports degraded. Relevant unrelated modules keep their own states. |
| `unavailable` | Observed failure/invalid configuration or unreadable/incomplete required store prevents the declared capability. Unknown values remain unknown rather than becoming zero or false success. |
| `not_applicable` | A supported conditional operation is not required in this installation, currently a valid scheduler store with no enabled schedules. It does not mean missing functionality was silently waived. |

Observations are recomputed snapshots, not persistent state transitions. Missing
configuration can move to configured-unverified after an explicit setup; it can
move to ready only when fresh module-specific evidence is observed. A new failed
probe, missing dependency, invalid clock/schema or expired receipt immediately
removes the earlier ready claim. Repairs/configuration/jobs occur through their
existing explicit operations, never as a side effect of refreshing the registry.
The lifetime of an observation and the actual last-success clock are both shown;
neither extends an expired external receipt. Historical test evidence remains a
reference, not a renewable health lease.

A supervisor `ready` receipt additionally requires a real non-null
`last_success_at` that is not later than observation and no more than 90 seconds
older. An observation time cannot be substituted for missing success evidence.
The installed owner remains the producer of these observations; a stale or
incomplete receipt fails closed without starting or restarting its service.
The owning Windows `service_name` can be projected only from the top-level
instance-bound supervisor receipt and only into that supervisor's metric. Its
identifier must match `Dragonhydra[A-Za-z0-9_-]{0,60}` exactly; arbitrary strings
and service identities injected into other modules are rejected. It identifies
the owner without exposing process arguments, credentials or private settings.

Passive observations read existing SQLite metadata/counts within a bounded
read-only connection, the existing worker and an installation-bound short-lived
supervisor receipt. They do not import modules with side effects, create absent
memory tables, send network/model/provider probes, initialize clients or run
workflows. Metrics use an allowlist and reject nonfinite/unsafe values. Supported
operations are fixed registered HTTP/CLI/internal references with required role
and read-only declaration, not executable code supplied by a browser. A shown
HTTP action still passes its actual permission, CSRF, input and job checks when
invoked. Dependency readiness and stale evidence are displayed explicitly;
optional AI/clients do not falsely block the core retained-data API.

An absent cognition store and an incomplete one are different observations.
Completeness requires `cognitive_records`, `cognitive_receipts` and all four
immutable update/delete triggers. Partial schema is unavailable with
`COGNITIVE_STORE_INCOMPLETE`; the status read does not repair it. If the core store
cannot be read, memory/evaluation/scheduler remain unavailable with unknown
configuration, rather than claiming empty history or no configured schedules.
The supervisor receipt must also use the supported producer schema; a fresh
timestamp alone cannot validate an incompatible heartbeat.

## Odds contract: `market-signals/1`

Input is a retained, cutoff-eligible quote with event, competition, participants,
market, period, status, settlement, line where applicable, outcome, provider/feed,
snapshot and actual known time basis. Decimal odds must be finite and greater
than one. American/fractional conversions are validated by the existing engine.

For decimal price `d`, raw implied probability is `1 / d`. A complete compatible
market has overround `sum(1/d_i) - 1`. The explicitly named proportional removal
estimate is `(1/d_i) / sum(1/d_j)`; it is a modeling convention, not a verified true
chance. Arithmetic uses rational intermediate values with one output rounding.
Known answer: prices 2, 3, 4 imply total 13/12, overround 1/12, proportional
home/draw/away estimates 6/13, 4/13, 3/13.

Do not combine different event identities, market definitions, periods,
settlements, total/handicap lines, game states, incompatible quote times or
incomplete outcome sets. A regulation market is not an extra-time market.
Half-unit totals can have a complete over/under set; integer/quarter lines need
push/split handling that this margin operation deliberately does not invent.
Historical source-open/close labels do not prove a live price timestamp.

Output metrics carry value/units, evidence IDs, transformation formula/version
and reason when unavailable. Tests cover invalid odds, nonzero known answers,
incomplete snapshots, stale/misaligned quotes, line/settlement mismatches,
cross-feed conflicts and future evidence exclusion. Missing compatible odds does
not prevent retained match browsing or honest statistical forecasting.

## Forecast and persistence contract

The existing `football-models/1` engine takes one eligible unplayed public-result
target, same-source/competition history, cutoff, verified raw-byte resolver and
model configuration. It emits frequency/Poisson/Elo/recency model availability,
normalized home/draw/away probabilities, ensemble choices, input manifest,
configuration evidence/hash, generation time, uncertainty, abstention and reasons.
Shared data and equal weights are disclosed. Existing adaptation accepts only
verified comparable operational evaluations, with its minimum-case threshold;
absence does not invent evidence-based weights.

`system-workflow/1` introduces only Product orchestration around those functions:

| Function / API | Input | Result and mutation |
|---|---|---|
| `forecast_match(product, match_id, run_id)` / administrator `POST /matches/{id}/forecasts` | Explicit selected canonical ID; durable server-created job ID; empty HTTP body | Existing model calculation → `memory.record_model_run` → `memory.record_prediction` for each available model/ensemble. Returns immutable records, status/reason and duplicate flag. No import, provider sync, AI request or new database. |
| `match_history(product, match_id, cutoff=None)` / reader `GET /matches/{id}/cognition-history` | Selected match and permitted current/as-of cutoff | Read-only source/fixture-scoped models, predictions, outcomes and evaluation history; counts; per-match scoring of stored probabilities. Historical model diagnostics remain explicit CLI operations, with `EXPLICIT_DIAGNOSTIC_NOT_REQUESTED` on this read path. Before first write, checks `sqlite_master` and returns empty cognition records without creating tables. |
| `evaluate_match(product, match_id, run_id)` / administrator `POST /matches/{id}/evaluations` | Explicit match and durable job ID | Attempts only the selected genuine later outcome, recomputes existing observed scoring, then persists supported nonzero cohort metrics. No outcome means `pending`, not success of prediction accuracy. |

Job output has `workflow_version`, `operation`, `match_id`, `run_id`, `status`,
`reason` and `duplicate`; forecast output includes `model_runs` and `predictions`.
History has `records`/`counts` with `models`, `predictions`, `outcomes` and
`evaluations`, plus `operational`, an explicit unavailable
`present_knowledge_holdout` marker and limitations.
Models retain input IDs/cutoff/version/configuration and
`parameters.result`; `parameters.workflow` records selected match, generation,
expected model names, uncertainty and adaptation. Predictions point to their
model-run record, target evidence and exact retained probabilities.

The first explicit forecast creates the existing cognition tables/triggers if
they are absent. This is a reported schema change, not a new subsystem. Memory
history uses the backwards-compatible `memory.as_of(..., readonly=True)` path,
which opens SQLite in read-only mode and skips schema initialization. An
incomplete existing cognition schema fails with `COGNITIVE_STORE_INCOMPLETE`;
opening history never repairs missing tables or immutable triggers. Existing
CLI and write callers retain the previous initializing default.
Memory
records are append-only and fingerprinted. Natural keys bind run ID/model;
replaying the same job reads original records even after a later result arrives.
Reusing a run for another target fails. Partial model/prediction persistence is
visible as `partial / PARTIAL_RUN_REQUIRES_REVIEW`, without recomputing from newer
evidence under the original run. A new attempt needs an explicit new job.

Finished matches reject new prospective forecasts. Connector providers without
the engine's evidence-bound forecast contract return a specific unsupported
source reason. Existing Product `GET .../predictions` remains an ephemeral
calculation; it does not silently become a persistence endpoint. Joomla history
must display persisted timestamps and distinguish them from that current preview.

## Outcome and evaluation contract: `cognitive-evaluation/1`

An outcome must resolve to retained raw bytes and the same source, fixture,
participants, date, competition, market, period and settlement as an earlier
persisted prediction. Unknown kickoff timezone is handled conservatively: the
stored source date must be safely past before a result is attached, and prediction
receipt must be provably pregame. A corrected result appends a revision. It cannot
rewrite earlier cutoff views. Ambiguous revisions, source/scope conflicts, an
outcome already known at prediction time and duplicate reruns are excluded with
specific reasons. Evaluation chooses the earliest eligible pregame forecast per
source/model/version/market scope/fixture, with a stable record-ID tie-break.

For home/draw/away probability vector `p` and observed one-hot vector `y`:

- Multiclass Brier loss is `sum((p_i - y_i)^2)`.
- Natural log loss is `-ln(p_actual)`.
- Probabilities must be finite, normalized within the existing tolerance and
  strictly between zero and one. This implementation rejects boundary values;
  it does **not** silently clip them. Any future clipping policy needs an explicit
  versioned contract and tests.

Known answer `(0.5, 0.3, 0.2)` with home result has Brier 0.38 and log loss
`-ln(0.5)`. Reports include sample size, unbiased variance where defined,
coverage, cases, calibration-bin counts, exclusions, scope and evidence lineage.
Null score/sample zero is retained when no outcome qualifies. One fixture is not
a claim of model skill. Small samples remain labeled and are not proof of future
performance.

`memory.record_evaluation` recomputes its score from authoritative immutable
records; callers cannot submit an invented score or a holdout as operational
performance. It currently persists Brier/log-loss groups for the four base names
in `models.NAMES`; the ensemble can appear in read-only observed scoring, but its
performance is not persisted through this existing base-model contract.
Evaluations retain source/competition/model/version/period/settlement cohort scope,
which can contain other eligible fixtures. Attaching an outcome is selected-match
scoped; the resulting persisted cohort is not mislabeled as an isolated fixture.
A replay reuses its original retained evaluation cutoff; later evidence needs a
new command.

`PRESENT_KNOWLEDGE_CHRONOLOGICAL_HOLDOUT` partitions already retained historical
results by event date, computes a frequency diagnostic now and scores later
dates. It is explicitly separate from `OPERATIONAL_RECORDED_PREDICTIONS`. Neither
its cases nor a downloaded historical result can be substituted for a prediction
that existed before that match. No forecast is backdated to complete a demo.

## Memory, jobs and availability semantics

Memory storage preserves original entries, content hashes, model/input references
and receipt clocks. Research tasks/hypotheses can record gaps but cannot become
verified match facts or training evidence. Storing a result is not autonomous
learning. Adaptation only uses its separately verified compatible evidence.

The existing durable worker owns job claim, lease, owner, idempotency and outbox.
The new dispatch only maps fixed `forecast` and `evaluation` kinds to the adapter,
with `run_id = job.id`. No second scheduler or service was introduced. Job
execution success means the command executed: its result can still be `pending`,
`unavailable` or `partial`, and the interface must render that distinction.

Monitoring observations are not command invocations. Readiness/registry/history
reads must not initialize cognition tables, import files, synchronize a paid
provider, run a model or rotate credentials. A stale observation is not current
health; a process/port/login-page observation is not end-to-end functionality.
Startup cycles and retried engineering cycles are not an application training
loop.

## Verification and remaining limits

Focused tests reuse existing odds, model, memory, evaluation, commands and
adaptation fixtures and add `tests/test_system_workflow.py`. They verify selected
identity, schema-free initial read, durable Jobs binding, immutable replay,
partial-run reporting, retrospective refusal, unsupported connector scope,
future cutoff rejection, known odds arithmetic and the complete later-outcome
branch in an isolated fictional controlled-clock test. Existing tests cover raw
tampering, future capture/receipt leakage, incompatible scope, outcome revisions,
earliest-prediction selection and exact score formulas.

Installed real-data acceptance must separately show the selected actual retained
fixture, its input IDs, persisted records, authenticated Joomla history and
preserved data/settings. If a real later result is unavailable, operational
evaluation remains pending; the controlled test and historical diagnostic are
reported as their actual scopes. Optional odds/AI and physical Android pairing
must not be declared verified by these backend tests.
