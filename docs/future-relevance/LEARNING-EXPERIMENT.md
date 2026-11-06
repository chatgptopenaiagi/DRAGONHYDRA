# Learning future relevance in fictional worlds

This engine fits the expected value of acquiring an observation. Every world,
signal, goal stream, outcome, clock and cost is synthetic. Costs are virtual
credits, not money. No provider, OpenAI service, retained sporting dataset or
existing product workflow is used. The GENESIS-6 probability kernel remains
unchanged; the new adapter requests one target/horizon at a time.

## Target and fitting

`R(X,Y,T)` is expected proper-loss reduction from acquiring category X when
predicting target Y from information visible at decision cutoff T. A training
label is the sum-of-class squared Brier loss before acquisition minus that loss
after acquisition. Binary Brier is therefore twice scalar `(p-y)^2`. Both forecasts
use the identical evaluation cutoff. The outcome is read only after target
maturity plus its declared availability delay. For immediately available data,
decision, acquisition and evaluation cutoffs coincide.

For PENDING fatigue, the decision features freeze at the original time t before
the value exists. Only the trusted retrospective label generator advances a
shadow clone to t+d, its availability. Before/after acquisition forecasts share
that future cutoff, and the target outcome matures later. The learned quantity
is `E[local Brier improvement at t+d | public S_t]`; no future state or signal
enters the features. Separate AVAILABLE examples also represent legitimate later
decisions, rather than substituting for the prospective rows. An observation
arriving at/after target maturity is ineligible, not assigned an invented label.
Rows enforce `decision_at <= acquisition_at == evaluation_cutoff <
outcome_occurred_at <= label_available_at`, with pending/delay features checked
against those times. Elapsed time is never labelled an information benefit.

There are four genuine standard-library ridge regressions, one per observation
category. Each coefficient vector is fitted from TRAIN labels using a
regularized normal equation and pivoted linear solve. Separate vectors allow
category rankings to change with time, target, horizon and existing observations.
They are not a renamed static category ranking. Standardization uses TRAIN only.

The explicit feature whitelist contains playing minute, remaining and elapsed
target time, accepted score difference, budget fraction, acquisition/computation
cost, freshness/missingness, pending availability/delay, target/horizon indicators,
four acquisition masks and already revealed possession/shots/fatigue/card values.
Receipt observation/availability/receipt timestamps must all be at or before the
current decision cutoff. Unrevealed values, world family, seed, group/episode IDs,
absolute calendar date, hidden hazards and future outcomes are not features.

Ridge regularization and the cost-adjusted acquisition threshold are selected on
VALIDATION net utility; prediction-label MSE breaks utility ties. Validation does
not refit coefficients. A canonical content SHA identifies the frozen model;
mutation is rejected on use. Its `available_at` is the latest TRAIN/VALIDATION
label availability, and estimation before that cutoff fails explicitly.

Empirical TRAIN residual RMSE and root-grouped residual-mean standard error are
diagnostics. They are not probability calibration or prediction intervals.

## Probability adapter and policies

The four targets are goal occurrence, full-time home/draw/away, next goal side
including no goal, and total goals from target origin through maturity in fixed
bins 0..12 plus `13PLUS`. Supported playing horizons are 1, 5, 10, 30 and FULL_TIME;
full-time result requires FULL_TIME. On advancing time the original target and
maturity stay fixed. Already accepted goals shift total-goal bins and can resolve
occurrence/first-scorer outcomes without further information.

Visible possession maps to configured rate factor 1.8/0.65, shots to 1.3/0.8,
fatigue to 1.4/0.85 at threshold 0.5. Possession and shots are treated as redundant
proxies: their visible factors are arithmetically averaged, then multiplied by
the fatigue factor. Revealed cards use the existing card multipliers. The default
combined rates remain bounded; unsupported rates are withheld explicitly and
never silently clamped. These signal-to-rate assumptions are configured, not
learned forecast coefficients.

`choose_action(snapshot, policy, model=None, seed=42, cost_weight=1)` consumes only
the public snapshot and returns ACQUIRE_NOW, DEFER, IGNORE or
NO_ADDITIONAL_INFORMATION with category, estimate, cost, reason and candidate
scores. The five policies are acquire_all, acquire_none, random, handcrafted and
learned. They face identical budgets and available categories. Learned action
scores subtract weighted acquisition plus incremental computation cost and apply
the validated threshold. An acquisition changes visibility only. DEFER never
advances the same-time trajectory automatically.

## Held-out study

`train_model(seed=42, cases=40)` constructs TRAIN and VALIDATION only.
`train_and_evaluate` freezes that result before constructing FINAL_TEST worlds.
Cases are root seeds per family, with four targets per seed and a rotating horizon
and playing-clock design. Every policy receives an independent visibility/budget
clone of the same underlying episode and must settle its identical outcome.
Each policy also has an independent 100-credit experiment acquisition cap across
episodes, in addition to each match's budget. Actual spend, remaining credits and
initial quotes blocked by that cap are reported separately from budget violations.

TRAIN worlds are constant/card_sensitive/tempo_signal, VALIDATION is
clock_sensitive, and FINAL_TEST is noisy_signal/possession_inverse/
late_card_interaction. Disjoint seed ranges place phases on separate virtual days
and keep root groups disjoint, including related targets/branches. TRAIN labels
precede validation decisions, the frozen artifact precedes test decisions, and
all fitting/selection occurs before test access.

Reports retain Brier, natural-log loss, reliability bins/ECE, actual acquisition
and kernel costs, action counts, budget checks, target/horizon segments and paired
differences against acquire_none. Zero assigned probability produces explicit
infinite log loss, not a clipped flattering score. Paired uncertainty gives equal
weight to underlying root groups so correlated targets/worlds do not masquerade
as independent samples. Normal intervals are approximate and not adjusted for
multiple comparisons; small group counts are flagged. Mixed-target aggregate
scores are descriptive; compare matching segments.

Negative measured value, worse held-out loss and failed transfer are legitimate
results. The small development study already includes such outcomes. These
experiments establish an executable learning/evaluation boundary, not real-world
calibration, guaranteed utility, causal information value or general transfer.

After all five actions for an episode are frozen, evaluation also probes initially
eligible one-step acquisitions on coupled clones. It records missed positive
initial opportunities and positive/nonpositive actual marginal acquisitions,
both before and after incremental acquisition/computation cost. Hypothetical
analysis kernel work is counted separately and never charged to a policy budget
or fed back into its actions/model. These are realized hindsight counts from one
outcome, with a `1e-12` numerical zero tolerance. A nonpositive realization does
not prove the expected acquisition was unnecessary or the decision irrational;
the initial one-step counterfactual is not an optimal sequential oracle.

The held-out prospective probe estimates fatigue's future value from its initial
PENDING snapshot, after all five actual strategies have frozen their decisions.
A separate shadow clone then advances, acquires and settles to form the same-time
future marginal-value label. The report includes count, strict decision-before-
acquisition count, estimated/realized means, MSE versus those realized values,
TRAIN-only pending-mean baseline MSE, and root-grouped signed error/realized value.
Expected-value calibration remains `UNVERIFIED`. Probe outcomes never refit the
model, select thresholds, alter actual acquisitions or reveal information to a
policy. This evaluates anticipation independently of whether a DEFER action is
later fulfilled by an interactive caller.
