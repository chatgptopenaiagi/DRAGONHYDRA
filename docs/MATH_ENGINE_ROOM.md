# Math Engine Room

The Math Engine Room supplies multiple forms of calculation through Python 3.14. PyTorch is one engine. Mathematical authority depends on the question, assumptions, data and numerical evidence; no engine receives universal precedence.

Genesis implements only the types in [math/contracts.py](../src/dragonhydra/math/contracts.py). Concrete adapters, model fitting, optimizers, simulation engines and both tribunals are deferred. Current package availability is recorded in [TECHNOLOGY_COMPATIBILITY_MATRIX.md](TECHNOLOGY_COMPATIBILITY_MATRIX.md).

## Engine boundary

`MathEngine` declares `engine_id`, `engine_version`, a set of supported `MathCapability` values and these operations:

| Operation | Intended use |
| --- | --- |
| solve() | Equation/system solutions or a named mathematical problem. |
| fit() | Estimate parameters using an explicitly eligible training dataset. |
| predict() | Apply a fitted/versioned engine to eligible inputs. |
| simulate() | Sample an identified distribution or scenario with a recorded seed. |
| optimize() | Search a stated objective under explicit constraints. |
| differentiate() / integrate() | Symbolic or numerical operations with assumptions, domain and precision. |
| calibrate() | Fit/evaluate calibration using a held-out temporal split. |
| explain() | Describe the calculation, assumptions, warnings and traceable reasons. |

An adapter advertises only real capabilities. Unsupported methods must reject explicitly; they must not silently substitute a different operation. The current Protocol lists all method signatures but does not implement capability dispatch. That behavior needs tests with the first adapter.

`MathEngineRequest` carries operation, JSON-like inputs, input fingerprint, timezone-aware target_as_of_at and optional integer seed. An engine must never infer the cutoff from the current clock. The contract validates operation/time/seed and defensively freezes JSON-like containers, rejecting unsupported objects, cycles, non-string mapping keys and non-finite floats. Fingerprints remain caller-supplied provenance references, not verified hashes. The first executable adapter must establish canonical serialization, operation-specific payload schemas, fingerprint consistency and advertised operation support. Frozen mappings/tuples require an explicit serialization boundary.

## Result contract

| MathEngineResult field | Required interpretation |
| --- | --- |
| engine_id / engine_version | Stable implementation identity; distinguish model artifact, adapter and library versions in later provenance. |
| inputs | Reviewed input summary or safe references; no secrets or unrestricted raw datasets. |
| result | The primary mathematical answer, with an operation-specific schema. |
| distribution | Optional outcome distribution/parameters with defined support, units and normalization. |
| confidence | Optional finite [0,1] quantity; None means unspecified. An adapter must state its statistical meaning, not assign an unexplained score. |
| numerical_precision | Dtype, numerical precision policy and relevant tolerances. |
| warnings / assumptions | Domain restrictions, convergence failures, approximations and applicability limits. |
| runtime | Finite nonnegative elapsed seconds; identify whether transfers/loading are included. |
| hardware | CPU/GPU/device information and fallback context. |
| reason_codes | Stable machine-readable explanations for decisions and limitations. |

The implemented result validates runtime, optional confidence, nonempty engine identity/version/precision/hardware and textual warnings/assumptions/reasons. It defensively freezes inputs, result and distribution payloads and rejects non-finite float values and unsupported container contents. This is a lightweight boundary, not complete mathematical schema validation. Future adapters must check distribution support/normalization, units, serialization and error semantics before a result becomes usable. Failed convergence remains a failed or qualified result; it cannot be converted to unexplained confidence.

## Engine candidates and workload routing

| Engine | Intended calculations | Present decision |
| --- | --- | --- |
| NumPy | Array operations, CPU reference calculations, sampling foundations | Existing Python 3.14 package; no separate MathEngine adapter yet. |
| SciPy | Probability distributions, optimization, integration and numerical routines | Candidate with packaging evidence; installation/adaptation deferred. |
| SymPy | Symbolic equations, differentiation and assumptions | Existing import/small-operation evidence; production adapter deferred. |
| statsmodels | Classical statistical and time-series models | Deferred until a specific model/evaluation design requires it. |
| scikit-learn | Calibration, preprocessing and classical estimators | Deferred; preprocessing and calibration must respect temporal fit boundaries. |
| PyTorch | Tensor/autodiff, GPU kernels and learned models | Preserve existing stack; measure operation-specific CPU/GPU correctness. |
| DuckDB SQL | Set-based statistics and analytical aggregation near data | Planned P2/P4 boundary; no universal numerical authority. |
| Julia / MATLAB / Wolfram | Future specialist numerical or symbolic adapters | No installation or integration in genesis. Prefer bounded external protocols when native Python 3.14 bindings are unavailable. |

Poisson, Dixon-Coles, Elo, Glicko and Bayesian models are methods, not interchangeable library labels. Each needs an explicit task, data eligibility policy, calibration procedure and validation design. Monte Carlo requires seed, sample size and sampling-error reporting. Graph/time-series methods require identity and chronological semantics before algorithm selection.

## Future Math Tribunal

The Math Tribunal compares comparable engine calculations: for example a Poisson implementation, a Dixon-Coles correction, a Bayesian posterior, Monte Carlo estimates, a PyTorch model output or an external symbolic result. Different assumptions may produce legitimately different answers. They must not be averaged merely because all are numbers.

Proposed comparison sequence:

1. Check task, input fingerprint, target cutoff, output support, units and conditioning assumptions.
2. Validate finite values, normalization, convergence, uncertainty definitions and numerical precision.
3. Separate deterministic numerical differences from model/assumption differences and Monte Carlo sampling error.
4. Report agreement, disagreement, numerical instability, assumption conflict and unresolved uncertainty with engine references.
5. Recommend a more precise calculation, alternative assumption test or targeted evidence question; preserve all original results.

Candidate output fields are comparison ID, request fingerprint, engine result references, comparability failures, tolerance policy, numerical differences, assumption conflicts, uncertainty and reason codes. This is design only; no new tribunal class or execution is claimed.

The Prediction Tribunal at P7 instead evaluates predictions in context: model calibration, stale/missing evidence, disagreement, shared sources, model dependence and the explanation of divergence. It may consume a Math Tribunal assessment, but a numerically stable calculation is not automatically a well-calibrated prediction. Odds engineering subsequently compares compatible market quantities and preserves uncertainty.

## First-adapter acceptance boundary

Before implementing an engine, select one narrow operation with known-answer cases. Test numerical limits and invalid inputs, versioned serialization, time/fingerprint validation, CPU behavior, bounded execution, declared hardware and unsupported operations. GPU speed claims require warmed repeated measurements with transfers reported separately; a smoke timing is insufficient. No future engine installation is needed merely to keep the interface open.
