# DRAGONHYDRA MASTER MACRO ROADMAP

## Long-Term Codex Journey

PROJECT_ROOT: `C:\xampp\DRAGONHYDRA`

Owner roadmap received 2026-09-24. Formatting consolidated for project documentation; architectural requirements and stage gates retained. Current implementation evidence belongs in [ROADMAP_STATUS.md](ROADMAP_STATUS.md), not in this long-term plan.

Owner range correction, 2026-09-24: initial scope is **2–3 sources (two to three)** and a normal session covers approximately **3–5 closely related roadmap items (three to five)**. Preserve owner-authored range separators exactly; never collapse a dash or en-dash into an integer. This corrected document supersedes the numeric wording in the original adoption checkpoint, which remains historical evidence.

PURPOSE: This document is a long-term architectural plan. It is NOT a single-session implementation task. It is NOT authorization to implement every stage immediately. Codex must use this roadmap to understand the intended evolution of DRAGONHYDRA and to select future coherent implementation blocks. The system must evolve gradually. Every layer must prove measurable value before greater complexity is added.

## 1. CENTRAL MISSION

DRAGONHYDRA shall evolve into a sports intelligence, mathematical analysis, simulation, prediction and odds-engineering laboratory. It must not become merely a scraper, odds collector, database warehouse, AI model, betting bot or collection of unrelated agents.

The central architecture is a controlled intelligence loop:

```text
REAL WORLD → HYDRA → EVIDENCE → MEDUSA → TIME CONSISTENCY → STORAGE
→ FEATURE FACTORY → MATH ENGINE ROOM → AI / GPU → SIMULATION
→ PREDICTION TRIBUNAL → ODDS ENGINEERING → UNCERTAINTY MAP
→ TARGETED HYDRA RESEARCH → NEW EVIDENCE → RECALCULATION
```

## 2. THREE PERMANENT LAWS

### LAW A — PROVENANCE

Every important external fact must retain source, source URL, retrieval time, observation time, content hash where possible, parser/version, confidence, verification state, and license/terms state where relevant. No important intelligence should appear inside a prediction without knowing where it came from.

### LAW B — TEMPORAL DISCIPLINE

Always distinguish what happened, when it happened, when it was observed, when it became available, when the system learned it, and when the prediction was made. Historical predictions may never use information that became available later. This rule must survive every future model, feature engine and AI architecture.

### LAW C — FEEDBACK-DRIVEN RESEARCH

HYDRA must not permanently operate as SCRAPE EVERYTHING. Its long-term design is CALCULATE → FIND UNCERTAINTY → IDENTIFY INFORMATION GAP → RESEARCH THAT GAP → VALIDATE NEW INFORMATION → RECALCULATE. This is a defining property of DRAGONHYDRA.

## 3. PERMANENT ROLE SEPARATION

| Role | Responsibility and boundary |
| --- | --- |
| HYDRA | External intelligence acquisition. Future heads may cover fixtures, lineups, players, injuries, clubs, coaches, weather, travel, news, odds, market movement and historical data. HYDRA collects; it does not decide final truth. |
| MEDUSA | Evidence gate: schema validation, normalization, deduplication, entity resolution, timestamp validation, source scoring, freshness analysis, conflict detection, provenance validation, confidence assignment, quarantine and rejection. MEDUSA validates; it does not predict match outcomes. |
| PYRAMID | Calculation architecture transforming verified evidence into progressively higher-level mathematical and analytical representations. |
| SQL SERVER | Primary structured intelligence memory: versioned external observations, entities, fixtures, markets, odds observations, source history, conflicts, processing history, provenance relationships and structured intelligence. Prefer append/version-oriented storage. |
| MARIADB | Operational and presentation state: XAMPP applications, Joomla integration, job state, local dashboard state, presentation cache and small operational queues. Do not duplicate SQL Server. |
| DUCKDB | Analytical laboratory: large joins, feature research, backtesting, historical analysis, model evaluation and analytical experiments. |
| PARQUET | Large-scale historical analytical storage: immutable history, large observation datasets, feature snapshots, simulation results and model evaluation archives. |
| PYTHON 3.14 | Primary orchestration language coordinating data contracts, validation, storage adapters, feature engineering, math engines, AI, simulation, testing and research orchestration. Architectural invariant unless the owner explicitly changes it. |
| PYTORCH / CUDA | GPU computational layer, only where measurable computational benefit exists. GPU presence is not justification for GPU use. |
| XAMPP / JOOMLA | Local human presentation: system health, source status, evidence, predictions, uncertainty, historical evaluation, model diagnostics and market observations. |
| CODEX DESKTOP | Research and GUI surface: browser research, rendered webpage inspection, Computer Use, manual/public source investigation, visual verification and research handoff. |
| CODEX CLI | Engineering and automation: coding, Python execution, SQL, tests, filesystem, data processing, Git, automation, diagnostics and checkpointing. |

Desktop and CLI cooperate through explicit project artifacts, not fragile private IPC hacking.

## 4. PYRAMID LAYERS

```text
P10  UNCERTAINTY / RESEARCH FEEDBACK
P9   EXPLANATION / HUMAN PRESENTATION
P8   ODDS ENGINEERING
P7   PREDICTION TRIBUNAL
P6   SIMULATION ENGINE
P5   AI / GPU
P4   MATH ENGINE ROOM
P3   FEATURE FACTORY
P2   ANALYTICAL MEMORY
P1   OPERATIONAL / STRUCTURED STATE
P0   INFRASTRUCTURE / INGESTION / XAMPP
```

Each layer may depend downward. Avoid hidden upward dependencies.

## 5. VERSION ROADMAP

### V0 — FOUNDATION AND EVIDENCE CONTRACTS

Owner baseline: largely implemented. Mission: stable physical and logical foundation.

Core requirements: Python 3.14 invariant, XAMPP root, SQL Server connectivity, MariaDB connectivity, GPU diagnostics, evidence contracts, temporal contracts, database boundaries, secrets policy and checkpoint system.

Required proof: environment reproducible, tests pass, databases coexist, credentials bounded, GPU healthy, temporal rules tested. V0 remains stable while later layers evolve.

### V1 — WEB → MEDUSA → SQL → JOOMLA

Owner baseline: current major development area. Mission: complete evidence ingestion path.

```text
PUBLIC SOURCE → HYDRA SOURCE INPUT → MEDUSA VALIDATION → SQL SERVER
→ PRESENTATION SUMMARY → MARIADB → XAMPP / JOOMLA
```

Core capabilities: source contracts, web fetching, browser handoff, content hashing, terms/robots metadata, provenance, append-only observations, source reliability, conflict handling and Joomla display.

Success gate: a real public sports fact travels from source to Joomla while preserving complete provenance. No prediction requirement yet.

### V2 — REAL HYDRA SOURCE ADAPTERS

Mission: controlled specialist source adapters instead of generic web ingestion.

Initial discipline: ONE SPORT, ONE LEAGUE, **2–3 HIGH QUALITY SOURCES**, ONE ODDS SOURCE. Begin with only two to three high-quality sources to prove one complete auditable intelligence loop before expanding source count. Do not create dozens of adapters before the first few prove value.

Possible classes: FixtureSourceAdapter, LineupSourceAdapter, PlayerSourceAdapter, InjurySourceAdapter, WeatherSourceAdapter, OddsSourceAdapter.

Every adapter exposes source identity, supported data classes, fetch policy, rate policy, license/terms state, parser version, timestamp quality, reliability metrics and failure states.

Success gate: HYDRA reliably reconstructs the external state of one controlled competition.

### V3 — FEATURE FACTORY

Mission: convert validated evidence into model-ready variables.

Examples: recent form, home/away performance, rest days, travel distance, injury impact, lineup continuity, player availability, goal rates, shot rates, xG, discipline, coach tenure, weather influence and market movement.

Every feature contains feature name, feature version, input evidence, calculation method, available_at, target_as_of_at, unit and missing-data behavior. Feature lineage must be reconstructable; no hidden transformations.

Success gate: historical feature snapshots can be recreated exactly for a given prediction timestamp.

### V4 — MATH ENGINE ROOM

Mission: typed mathematical calculation layer. Possible engines: NumPy, SciPy, SymPy, statsmodels, PyTorch, future Julia, future MATLAB, future Wolfram. Possible capabilities: solve, fit, predict, simulate, optimize, differentiate, integrate, calibrate and explain.

No engine is added simply because it exists. Each justifies the problem solved, why existing engines are insufficient, and accuracy, speed or interpretability improvement. A future MATH TRIBUNAL compares competing mathematical methods.

Success gate: several different statistical/mathematical approaches operate on the same typed feature contracts and produce comparable outputs.

### V5 — SIMULATION ENGINE

Mission: move beyond single-point estimates. Possible methods: Monte Carlo, Poisson simulation, bivariate Poisson, score-distribution simulation, player-state simulation, lineup, injury, weather and market scenarios.

Outputs include distributions, not merely winners: home goals, away goals, scoreline, Win/Draw/Loss probability, Over/Under distribution and confidence intervals.

Success gate: reproduce historical matches using only information available at historical prediction time.

### V6 — PREDICTION TRIBUNAL

Mission: never trust one model automatically. Participants may include statistical, Poisson, rating, machine-learning, neural, simulation and market-derived models.

Evaluate calibration, historical accuracy, sample relevance, freshness, data completeness, model stability, agreement, disagreement and uncertainty. Outputs may include home/draw/away probability, confidence interval, model disagreement and evidence quality. Do not hide model disagreements.

Success gate: multiple models disagree transparently and the system explains why.

### V7 — ODDS ENGINEERING

Mission: compare calculated probabilities with observed market prices. Components: decimal odds validation, implied probability, overround, normalized market probability, fair probability, fair odds, odds movement, price history, market consensus and disagreement.

Example: model Home 47%, Draw 29%, Away 24%; normalized market Home 44%, Draw 30%, Away 26%. Mathematical differences do not automatically represent profit.

Success gate: every market observation can be reconstructed historically with its exact timestamp and source.

### V8 — UNCERTAINTY-DRIVEN RESEARCH LOOP

Mission: the defining intelligence feedback system. Example: confidence falls because a starting goalkeeper's status is unknown. Create ResearchNeed with entity=goalkeeper, team=Team A, question=availability, deadline=before kickoff, importance=HIGH. HYDRA searches relevant sources only; MEDUSA validates the answer; PYRAMID recalculates.

CALCULATE → MEASURE UNCERTAINTY → IDENTIFY MISSING INFORMATION → RESEARCH → VALIDATE → RECALCULATE.

Success gate: demonstrate reduced uncertainty through targeted evidence acquisition.

### V9 — CONTINUOUS HISTORICAL EVALUATION

Mission: measure continuously. Track prediction accuracy, Brier score, log loss, calibration, odds calibration, feature usefulness, source usefulness, model usefulness, simulation quality, latency, GPU benefit, database performance and research benefit.

Measure every layer: did a source improve predictions, injury data improve calibration, Medusa reduce bad records, GPU models outperform CPU alternatives, weather matter, or the uncertainty loop reduce error? Create historical benchmark suites.

Success gate: architectural decisions are defensible through measurements rather than intuition.

### V10 — FULL MULTI-HEAD HYDRA

Mission: expand into a broader autonomous intelligence system only after earlier stages prove reliable. Potential heads: MATCH, PLAYER, TEAM, INJURY, LINEUP, COACH, WEATHER, TRAVEL, TACTICAL, NEWS, ODDS, MARKET and HISTORICAL.

Every head has scope, data contracts, allowed sources, reliability score, rate limits, failure policies, provenance and tests. No head receives unrestricted authority over final predictions. HYDRA collects; MEDUSA validates; PYRAMID calculates; TRIBUNALS evaluate.

## 6. COMPLEXITY CONTROL LAW

The main architectural threat is uncontrolled complexity. Always ask: DOES THIS COMPONENT PRODUCE MEASURABLE VALUE?

Before adding a database, AI model, web source, scraper, language, agent, math engine, service or framework, answer:

1. What problem does this solve?
2. What current component cannot solve it?
3. How will improvement be measured?
4. What new failure modes are introduced?
5. How will it be removed if it fails?

Without convincing answers: DEFER THE COMPONENT.

## 7. MODULARITY RULE

Avoid 100 modules, 15 databases, 20 agents, 8 math engines or 50 scrapers without clear ownership. Prefer small, typed, measurable, replaceable, testable and observable components.

## 8. DATA OWNERSHIP LAW

Every important dataset has one primary owner. Ownership classes: RAW_EVIDENCE, STRUCTURED_INTELLIGENCE, OPERATIONAL_STATE, ANALYTICAL_DATA, DERIVED_FEATURE, SIMULATION_OUTPUT, PREDICTION, MARKET_OBSERVATION, PRESENTATION_CACHE, ARCHIVE.

SQL Server owns STRUCTURED_INTELLIGENCE; MariaDB owns OPERATIONAL_STATE / PRESENTATION_CACHE; DuckDB owns ANALYTICAL_DATA; Parquet owns ARCHIVE / LARGE HISTORY. Avoid automatic duplication. Replication requires an explicit reason.

## 9. SOURCE QUALITY MODEL

Evaluate authority, freshness, timestamp quality, historical reliability, coverage, correction behavior, machine readability, terms compatibility, availability and latency. Sources acquire measurable performance histories. Fame does not automatically make a source useful.

## 10. MEDUSA QUALITY METRICS

Track accepted/rejected records, duplicates removed, conflicts detected, stale records detected, entity-resolution accuracy, timestamp anomalies, source disagreement and correction frequency. Prove MEDUSA improves the evidence stream.

## 11. FEATURE VALUE METRICS

Measure predictive gain, calibration gain, stability, missingness, latency, acquisition cost, source dependency and historical availability. Features without measurable value may be removed.

## 12. MODEL VALUE METRICS

Benchmark every model against simple baselines: league average, historical home/away rate, simple Poisson, market implied probability and simple rating model. Complex AI must beat or meaningfully complement simpler methods. Complexity itself is not intelligence.

## 13. GPU VALUE LAW

Justify PyTorch/CUDA through measured training speed, inference speed, simulation speed, memory use, accuracy and CPU comparison. Without material GPU improvement, CPU methods remain valid.

## 14. RESEARCH VALUE METRIC

Measure uncertainty before/after research, for example 0.31 before lineup confirmation and 0.18 after, or prediction entropy before/after. These are illustrative values, not results. Learn which research actions are worthwhile.

## 15. INITIAL SCOPE DISCIPLINE

Before expansion: ONE SPORT, ONE LEAGUE, **2–3 GOOD SOURCES**, ONE ODDS SOURCE, ONE PREDICTION PIPELINE. First prove a complete, auditable intelligence loop, not world coverage. Earn expansion from one league to multiple leagues, one sport to multiple sports.

## 16. EXPERIMENTAL VS PRODUCTION STATES

Every component has a maturity state: CONCEPT, EXPERIMENTAL, VALIDATED, STABLE, DEPRECATED or RETIRED. Experimental code must not be treated as production architecture.

## 17. CODEX SESSION DISCIPLINE

Implement only one coherent block per development session. Prefer approximately **3–5 closely related roadmap items** rather than entire future versions in one session. This means three to five related items in a bounded, coherent, testable and reviewable block, not dozens of unrelated tasks.

Each session: inspect current state; identify roadmap stage; choose one coherent block; implement; test; benchmark where appropriate; update documentation; create an immutable checkpoint; state limitations; define NEXT_EXACT_ACTION.

## 18. ROADMAP STATUS FILE

Maintain `docs\DRAGONHYDRA_MASTER_ROADMAP.md` and `docs\ROADMAP_STATUS.md`. Status contains VERSION, STATUS, COMPLETION_PERCENTAGE, COMPLETED_COMPONENTS, PARTIAL_COMPONENTS, NOT_STARTED_COMPONENTS, CURRENT_BLOCK, CURRENT_LIMITATIONS and NEXT_EXACT_ACTION. Do not inflate percentages. Use evidence.

## 19. DECISION LOG

Maintain `docs\DECISIONS.md`. Architectural decisions record decision, reason, alternatives, evidence, trade-offs, date and status.

Important examples: why SQL Server owns structured intelligence; MariaDB owns operational/presentation state; Python 3.14 is mandatory; future leakage is prohibited; source provenance is mandatory; Desktop/CLI integration uses handoff artifacts.

## 20. ARCHITECTURE SCORECARD

Periodically evaluate DATA QUALITY, TEMPORAL INTEGRITY, PROVENANCE COVERAGE, MODEL CALIBRATION, SOURCE RELIABILITY, SYSTEM LATENCY, TEST COVERAGE, SECURITY BOUNDARIES, REPRODUCIBILITY and COMPLEXITY. Keep independent health dimensions; do not collapse them into one meaningless score.

## 21. HUMAN OBSERVABILITY

The owner should eventually open Joomla/XAMPP and understand which match is analyzed, what evidence exists, its origin, missing information, conflicting sources/models, each model's probability, market implications, uncertainty and HYDRA's next research. Human observability is architectural.

## 22. EXPLANATION LAYER

Predictions must not be unexplained numbers. Illustrative future display:

```text
HOME WIN: 47%
Major positive factors:
+ stronger recent xG
+ home advantage
+ opponent defensive absences
Major negative factors:
- uncertain starting goalkeeper
- short recovery period
Model disagreement: moderate
Evidence confidence: high
Market disagreement: +3 percentage points
Primary uncertainty: goalkeeper availability
```

Explain evidence and uncertainty, not hidden chain-of-thought.

## 23. FAILURE AS DATA

Preserve meaningful failure states: SOURCE_BLOCKED, SOURCE_OFFLINE, TERMS_BLOCKED, RATE_LIMITED, SCHEMA_CHANGED, ENTITY_UNRESOLVED, CONFLICTING_DATA, STALE_DATA, MODEL_FAILURE, DATABASE_FAILURE, GPU_FAILURE, BROWSER_UNAVAILABLE and INSUFFICIENT_EVIDENCE. Failures must not disappear silently; they inform system reliability.

## 24. TESTING PHILOSOPHY

Tests evolve with architecture: unit, contract, temporal, source adapter, database, security, historical replay, feature reproducibility, model calibration, simulation, performance, failure recovery and end-to-end tests. A larger system without corresponding tests is not progress.

## 25. CHECKPOINT PHILOSOPHY

Every important milestone creates immutable evidence under `runtime\checkpoints`, e.g. `v1-web-sql-...`, `v2-hydra-source-...`, `v3-feature-factory-...`, `v4-math-engine-...`, `v5-simulation-...`.

Include configuration fingerprint, test results, environment fingerprint, database capability evidence, model metrics where relevant, files manifest and known limitations. No secrets.

## 26. FUTURE END-TO-END IDEAL

MATCH DISCOVERED → HYDRA collects evidence → MEDUSA validates → SQL Server stores versioned intelligence → Feature Factory reconstructs time-correct state → math engines calculate → AI models calculate → simulation creates distributions → Prediction Tribunal compares models → Odds Engine compares market → Uncertainty Engine identifies missing information → HYDRA performs targeted research → MEDUSA validates new evidence → Pyramid recalculates → Joomla displays prediction, evidence, uncertainty, market, provenance and model disagreement.

## 27. DEFINITION OF SUCCESS

Success is not many files, databases, AI models, scrapers or technologies. It means better evidence, temporal integrity, calibration, reproducibility, explanation, uncertainty measurement, targeted research and measurable computational efficiency.

## 28. FINAL DEVELOPMENT PRINCIPLE

```text
HYDRA COLLECTS.
MEDUSA QUESTIONS.
THE PYRAMID CALCULATES.
MATH ENGINES COMPETE.
AI CONTRIBUTES.
SIMULATION EXPLORES.
THE PREDICTION TRIBUNAL JUDGES.
THE ODDS ENGINE COMPARES.
UNCERTAINTY ASKS WHAT IS MISSING.
HYDRA RETURNS TO THE WORLD.
THE LOOP CONTINUES.
```

Above all: PROVENANCE + TEMPORAL DISCIPLINE + FEEDBACK-DRIVEN RESEARCH. These pillars define DRAGONHYDRA. Do not sacrifice them for speed, complexity or novelty.

## 29. CODEX ROADMAP INSTRUCTION

Whenever Codex resumes DRAGONHYDRA:

1. Read this roadmap.
2. Read current PROGRESS and DECISIONS.
3. Determine the active roadmap version.
4. Do not jump arbitrarily into later stages.
5. Select one coherent implementation block.
6. Preserve existing verified architecture.
7. Measure improvement.
8. Test completely.
9. Record what changed.
10. Define NEXT_EXACT_ACTION.

The journey is incremental. The architecture may evolve. The three permanent laws remain.

END OF DRAGONHYDRA MASTER MACRO ROADMAP.
