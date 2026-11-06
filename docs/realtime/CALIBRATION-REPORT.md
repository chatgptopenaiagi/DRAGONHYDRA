# Synthetic evaluation boundaries

`dragonhydra.realtime.evaluation` provides pure scoring of explicitly synthetic forward episodes. No real sporting records, original installation databases, live provider responses or historical owner forecasts are read. The result always states `SYNTHETIC_FORWARD_EPISODES`, `synthetic: true`, `calibration_state: UNVERIFIED` and `real_calibration_claim: false`.

`evaluate_forecasts(predictions, outcomes, cutoff=..., bins=10, horizon=None)` takes bounded lists of exact-schema records. Prediction fields are `prediction_id`, `match_id`, `forecast_target`, `horizon`, `probabilities`, `decision_at`, `available_at`, `source_mode` and `synthetic`. Outcome fields are `match_id`, `forecast_target`, `horizon`, `label`, `occurred_at`, `available_at`, `source_mode` and `synthetic`. Timestamps require UTC offsets; modes are `DEMONSTRATION` or `REPLAY` and `synthetic` must be true.

Target and horizon must match exactly. Outcomes must be available by the evaluation cutoff; predictions must have been available strictly before target maturity. `occurred_at` means target maturity, not an early goal timestamp. Numeric horizons represent continuous synthetic windows and score only when maturity is exactly decision time plus the specified minutes. A later maturity is excluded as `NOT_ELIGIBLE_PLAYING_CLOCK_MAPPING_UNAVAILABLE`; an earlier one is rejected. Paused or half-time playing-clock windows require a separately verified mapping and are not qualified by this evaluator. Full-time outcomes require their authoritative virtual maturity time.

Duplicate target/horizon records, reused prediction identifiers, unknown outcome labels, mode mismatches, future availability, invalid timestamps, nonfinite values and malformed probability vectors cannot silently enter the scored cohort. No missing outcome is treated as a negative label. No future result can be used to construct a past forecast.

Scores are multiclass Brier sum of squared errors, un-clipped natural-log loss and top-label equal-width expected calibration error. Confidence ties use lexicographic label order. Bins are left-inclusive and right-exclusive, except the final bin includes confidence one. A zero probability assigned to the observed label yields `log_loss: null`, `log_loss_infinite: true` and a zero-probability event count. It is never clipped into a finite favorable score. Empty eligible cohorts have null metrics and `status: pending`.

The report gives both forecast count and independent match count. Multiple horizons or models for one fixture do not create independent matches. A mixed target/horizon aggregate is explicitly marked; compare like cohorts rather than interpreting that descriptive aggregate as a uniform quality benchmark. Fewer than twenty scored episodes receive a small-sample warning. Neither twenty samples nor a lower synthetic ECE establishes real calibration.

The deterministic unit checks below are arithmetic and boundary examples, not a calibration experiment:

| Synthetic example | Brier | Log loss | ECE |
|---|---:|---:|---:|
| One goal outcome; assigned goal probability 0.25 | 1.125 | 1.3862943611198906 | 0.75 |
| One goal outcome; assigned goal probability zero | 2 | infinite, represented explicitly as null plus flag | 1 |
| One correctly certain goal outcome | 0 | 0 | 0 |
| Outcome unavailable at cutoff | null | null | null |

`evaluate_baseline_vs_assisted` compares exact matched input/cutoff cohorts. It rejects any assisted probability change. Since the assistant only selects and explains evidence, same-data Brier, log-loss and ECE differences must be zero when finite and eligible. It never claims AI quality improvement. Null or infinite scores remain explicit and do not become a fabricated zero delta.

New synthetic universes, relevance fits or evidence-aware models need separate training/test episode identities, immutable source bytes, declared data-availability cutoffs and forward label maturation. Changing evidence and enabling AI simultaneously cannot identify an AI effect. Compare retained/no-AI with retained/AI, and new-evidence/no-AI with the same-new-evidence/AI; the AI-on/off probability deltas remain zero. A separately trained numeric model can be assessed against an appropriate baseline only on held-out synthetic worlds, with leakage and shared assumptions disclosed.

The inherited chronological holdout remains `PRESENT_KNOWLEDGE_CHRONOLOGICAL_HOLDOUT`; it is not historical STRICT_PIT evidence. The original failed dev.5 Forecast receipt and its retained inputs remain unchanged. No old failed operation is rerun or relabeled successful by this scoring module.

Verification: `tests/test_realtime_evaluation.py` has twelve deterministic test methods covering arithmetic, cutoff/pending behavior, exact target/horizon matching, paused-window exclusion, probability boundaries, strict synthetic records, UTC ordering, duplicate rejection, independent-match counts and unchanged assisted vectors. Together with fourteen bridge test methods, the assigned focused suites pass twenty-six tests with socket creation denied. These counts describe the local unit suites, not release acceptance, a real AI model, live data or real calibration.

The executed synthetic study is recorded in [vertical-r2/RELEVANCE.json](../../../evidence/vertical-r2/RELEVANCE.json), SHA-256 `80359979cfe780b2ad4c296638e6970ccc7669aa3fe12f125a5e36f2036392a1`. It generates 1,000 episodes per world, split into 700 TRAIN and 300 TEST, across five rule sets. Corresponding worlds share initial conditions and latent draws. Rates are fitted only on TRAIN data; TEST labels score the fitted alternatives. The report retains all 100 feature/horizon rows, including negative and uncertain results.

| Synthetic world and feature, ten-minute target | Actual Brier reduction, baseline minus feature model | Approximate paired 95% interval |
|---|---:|---|
| `tempo_signal`, POSSESSION | 0.04724380025543053 | [0.029190458044189065, 0.06529714246667201] |
| `noisy_signal`, POSSESSION | 0.0000015873717663184826 | [−0.0006438116661891583, 0.0006469864097217953] |
| `card_sensitive`, CARD | 0.009013696757653141 | [−0.002731016123079029, 0.020758409638385312] |
| `clock_sensitive`, CLOCK | 0.009519476618780998 | [−0.007333339128927981, 0.026372292366489976] |

Possession carries predictive information under the declared tempo-signal rule, while its noisy-signal result is compatible with zero benefit. The positive card and clock point estimates have intervals crossing zero; this run does not establish their improvement. These intervals use paired TEST loss differences and a normal approximation without multiple-comparison adjustment. They are not independent confirmation across 100 rows, real-world calibration, mutual information, causal relevance or evidence of AI improvement. No positive outcome is forced, no real sporting quality is claimed, and this report does not automatically alter the configured forecast probabilities.
