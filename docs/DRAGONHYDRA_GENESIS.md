# DRAGONHYDRA genesis

DRAGONHYDRA is a new sports intelligence and odds-engineering system rooted at `C:\xampp\DRAGONHYDRA`. Python 3.14 is its computational language; Conda supplies the verified interpreter; XAMPP supplies local infrastructure. The old DRAGON contributes evidence-backed ideas, not an inherited installation or a copied application.

This genesis block establishes boundaries, diagnostics, typed evidence prototypes and one limited Python-to-MariaDB proof. It does not deliver a prediction product. Execution outcomes and checkpoint locations belong in [PROGRESS.md](PROGRESS.md); this document distinguishes source implementation from architectural intent.

The preserved checkpoint `genesis-20260924T155516Z-ddf9f093` establishes a successful canonical Python 3.14 GPU operation and a SELECT-only MariaDB bridge. [Diagnostics — curated summary](evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/diagnostics.json`), [bridge evidence — curated summary](evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/bridge.json`) and [that checkpoint's tests — curated summary](evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/tests.json`) are distinct machine-readable records. Later hardening and final test totals belong to the latest checkpoint referenced by progress; earlier evidence is not overwritten.

## Two realities and a recurrent process

REALM A is external sports reality: matches, clubs, players, expected and confirmed lineups, injuries, weather, travel, rules and quoted markets. Our observation of that reality is incomplete, delayed and sometimes wrong. REALM B is the internal computational representation: evidence versions, operational projections, analytical memory, features, calculations and explanations. Internal certainty must never exceed its evidence.

The intended process is recurrent:

```text
REAL_WORLD -> HYDRA -> EVIDENCE -> MEDUSA -> PYRAMID
  -> MATH / AI-GPU -> SIMULATION -> PREDICTION_TRIBUNAL
  -> ODDS_ENGINEERING -> EXPLANATION -> UNCERTAINTY
  -> TARGETED_RESEARCH -> HYDRA -> NEW_EVIDENCE -> RECALCULATION
```

These arrows express dependencies, not a requirement to run every engine on every update. A conflict can return directly to source research; a stale lineup can stop a prediction before simulation; a new model can trigger recalculation with unchanged evidence. Every recalculation must record whether evidence, cutoff, policy or engine changed. Repeated research requires a specific question, permitted source, resource budget and stopping condition.

Hydra senses and packages assertions. Medusa validates identity, provenance, chronology and conflicts. The Pyramid assigns storage and computation responsibilities. Mathematical engines calculate through explicit interfaces. A future Math Tribunal compares numerical results and assumptions; the Prediction Tribunal compares predictions and evidence adequacy. Odds engineering interprets fair probabilities and observed prices. Uncertainty decides which unanswered question deserves the next observation.

## What exists in this block

| Boundary | Source implementation | Scope |
| --- | --- | --- |
| Configuration | [config.py](../src/dragonhydra/config.py), [genesis.toml](../config/genesis.toml) | Non-secret local settings, project-constrained paths, loopback SQL endpoint and bounded diagnostic parameters. |
| Compute diagnosis | [diagnostics.py](../src/dragonhydra/diagnostics.py) | Exact Python minor version, dependency inventory and bounded numerical CPU/GPU comparison; results must be read from an executed checkpoint. |
| Hydra / Medusa contract | [hydra/contracts.py](../src/dragonhydra/hydra/contracts.py), [medusa/evidence.py](../src/dragonhydra/medusa/evidence.py) | Immutable scalar packets, versions, in-memory as-of selection, conflicts and supersession. No collectors or production persistence. |
| Mathematical boundary | [math/contracts.py](../src/dragonhydra/math/contracts.py) | Protocol and request/result types. No concrete engine or tribunal. |
| Storage read boundary | [storage/contracts.py](../src/dragonhydra/storage/contracts.py) | AggregateReader and read-only permission proof protocols. No universal database abstraction. |
| Python / XAMPP proof | [integration/mariadb_probe.py](../src/dragonhydra/integration/mariadb_probe.py) | Fixed Joomla aggregate SELECTs through a dedicated account; Joomla is only the controlled test source. |
| Evidence regression cases | [test_evidence.py](../tests/test_evidence.py) | Synthetic delayed result, corrected event and goalkeeper confirmation, plus boundary cases. Test existence is distinct from a passing run. |

The current `hydra` package re-exports contract types; it is not a working sensing service. Prototype confidence scores carry rationale but are not calibrated probability estimates. Evidence packets currently require proven availability and immutable scalar values. Unknown-time raw observations need a future quarantine contract rather than invented timestamps.

## Invariants

1. Historical calculation at T uses only exact evidence versions demonstrably available by T. Event time, current webpages and later corrections cannot establish earlier knowledge.
2. Corrections append versions; they do not erase the assertion used in an earlier replay. Source conflicts remain visible.
3. Python must satisfy `>=3.14,<3.15` in this block. No older interpreter is installed to accommodate a dependency.
4. GPU identity, a loaded library and successful GPU computation are separate facts. A CPU fallback must be reported.
5. Only a bounded proof reads Joomla. No application account, Joomla schema or Joomla code becomes a product dependency.
6. Operational state, analytical history and presentation have separate owners. The project does not replicate every table into every database.
7. Generated secrets stay outside `htdocs` and outside non-secret configuration, reports and logs. Existing XAMPP applications and databases retain their ownership.

## Deliberate next boundary

Full Hydra collectors, web scrapers, production schemas, large neural models, real-money actions, complete tribunals, the odds engine and full UI are deferred. SQL Server, Julia, MATLAB, Wolfram, Qwen and distributed services are not integrated. No empty subsystem directory constitutes progress.

Read [PYRAMID_ARCHITECTURE.md](PYRAMID_ARCHITECTURE.md), [MATH_ENGINE_ROOM.md](MATH_ENGINE_ROOM.md), [DATABASE_ROLES.md](DATABASE_ROLES.md), [XAMPP_ROLE.md](XAMPP_ROLE.md), [PYTHON314_POLICY.md](PYTHON314_POLICY.md) and [GPU_COMPUTE_POLICY.md](GPU_COMPUTE_POLICY.md) for the chosen boundaries. [OLD_DRAGON_RECONCILIATION.md](OLD_DRAGON_RECONCILIATION.md) records what was kept, reworked and rejected. [DECISIONS.md](DECISIONS.md) and [PROGRESS.md](PROGRESS.md) record the measured decisions and next authorized block.
