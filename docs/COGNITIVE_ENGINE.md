# Cognitive intelligence engine

The local Python 3.14 engine builds current forecasts from the retained,
content-hashed OpenFootball captures. Its entry points are `train`, `predict`,
`evaluate`, `calibrate`, `memory`, `intelligence`, and `research` in `dragon.py`.
Add `--format json` to retain model inputs, clocks, transformations and evidence IDs.

## Model methods

The models use the same source, competition, period and settlement scope. Only
results demonstrably eligible at the decision cutoff and conservatively prior to
the target fixture are admitted. Separate outcomes are:

- Bayesian-smoothed 1X2 frequencies and exponentially recency-weighted frequencies.
- Independent Poisson home/away goal counts, with same-venue team scoring and
  concession averages shrunk toward league averages. These are expected match
  goals inferred from scores, not shot-derived xG. The output includes 1X2,
  over/under 2.5, both-teams-to-score and likely scorelines; omitted finite-grid
  probability is reported and excessive omission causes abstention. JSON also
  contains the full finite scoreline grid with shared evidence references.
- Daily-batched Elo ratings, with the draw share borrowed from the frequency model.
  Consequently the candidate models are not independent.
- A transparent ensemble. Without measured, comparable, cutoff-eligible
  operational evaluations it uses equal weights. Performance-based adaptation
  requires at least 20 genuinely scored predictions per candidate model for the
  same fixture cohort, with verified retained evidence. Outcome corrections
  invalidate old evaluation weights until they are recomputed.

All probabilities are research estimates. Counts, rate calculations, input
records, configuration and source references are present in JSON output.

## Memory and feedback

`train` appends model runs. `predict` and `intelligence` append a model run and
forecast for each available model and ensemble. Original predictions remain
immutable. `memory` lists records and accepts `--outcome-evidence-id ID` to
attach an eligible later captured result. An outcome is not accepted if it was
already usable before the forecast or cannot be matched to the exact fixture and
source scope. Source corrections append a revision; they do not rewrite older
forecasts or earlier replay results.

`evaluate` scores recorded forecasts only when later eligible outcomes exist. It
keeps the earliest pregame prediction per fixture, model and version for the
scoring cohort and labels reruns as duplicate predictions. It reports Brier score,
log loss, accuracy, calibration bins, sample sizes and variance. Nonempty
operational scores can be persisted and used for later adaptation. The present
SQLite receipt records use the acknowledgment of an earlier data transaction;
the precise visibility boundary of the subsequent receipt transaction is not yet
independently established. Reports therefore say `OPERATIONAL_AS_OF_RECEIPT` and
do not claim fully verified retrospective STRICT_PIT replay.

The same command also runs a **present-knowledge chronological holdout** on the
retained 2025/26 capture: it fits each model using earlier event dates and scores
later held-out results, but the entire source was captured by this system now.
That diagnostic is not a historical point-in-time backtest or an operational
prediction record. `calibrate` displays its observed frequencies by forecast bin;
it does not assert that any model is calibrated.

`research` records explicit gaps and bounded questions. It currently does not
assert a mapping between unrelated fixture namespaces. Therefore the intelligence
report shows archived prices independently and abstains on model-versus-market
comparisons until identity, timing and settlement compatibility are supported.
It also retains structured competing hypotheses as immutable revisions with
evidence IDs, assumptions, missing information and testable next questions.
Differently dated records for the same source and participants are treated as
ambiguous until a reschedule or separate-fixture identity is established.
