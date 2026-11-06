# Synthetic residual-time probability model

`dragonhydra.realtime.models.predict(state, config=None)` is a pure experimental
calculation. All states must declare `synthetic: true`, use a `virtual-` match ID,
and have source mode `REPLAY` or `DEMONSTRATION`. REPLAY means fictional replay;
it does not authorize historical or provider data. No model is trained, no API is
called, and the established forecasting mathematics/workflow is unchanged.

The configured examples are 1.6 home and 1.2 away goals per 90 playing minutes.
Each remaining goal process has constant independent intensity. A team's own red
card multiplies its intensity by 0.75 and its opponent's by 1.10. These are
invented assumptions to explore, not estimated football effects. Configuration
can neutralize those multipliers. Current goals shift future score cells and are
never subtracted from the future intensity.

For exposure `t` and intensities `r_home`, `r_away`, future means are `r_i*t`.
The existing pure `cognition.models.poisson_distribution` computes the marginal
Poisson vectors. The probability of any goal is `-expm1(-(r_home+r_away)*t)`.
Next-scorer home/away probabilities include the no-goal outcome. Conditional
scorer shares are separately labelled; they are null if exposure or both
intensities are zero. Summing future score cells above/on/below the current score
diagonal gives home/draw/away probabilities.

## Clock contract

The keys `1`, `5`, `10`, `30`, `FULL_TIME` mean playing minutes. The scheduled
regulation duration is 90; extra-time periods and different scheduled lengths
are unsupported. Fixed horizons stop at the current explicit period end. During
period one, FULL_TIME includes the known first-half remainder plus 45 second-half
playing minutes. During period two, it stops at the explicit period end. Announced
stoppage advances `period_end_minute`, for example 95, while `duration_minutes`
remains 90. Unannounced stoppage is not invented.

SCHEDULED predictions are conditional on kickoff. HALF_TIME predictions cover
the next half's playing minutes, explicitly conditional on resumption; they do
not predict how long the break lasts. SUSPENDED, unknown end times, unsupported
periods and an IN_PLAY clock at/beyond its end withhold future probabilities.
Clock 90 does not establish finality. An authoritative FINISHED status yields an
observed current-score point mass, zero future goals and no next scorer. The
final observed score is not an accuracy claim or an extra-time settlement model.

## Numerical contract

Marginal supports adapt to a finite tail tolerance (default `1e-12`) with a hard
configured maximum (default 64; allowed 1..100). Score rows are conditioned on
the included joint support; `tail_mass` records omitted mass before this
conditioning. For any score event, the absolute conditioning error is at most
that mass. Home/draw/away and the score rows sum to one within `1e-12` numerical
rounding. `remaining_goals.distribution[n]` is the unconditioned probability of
exactly n total future goals; its explicit `tail_bucket` starts at the list's
length and completes probability one. Its `mean` is the full analytic mean,
not the mean of a truncated vector.

If the requested tail bound cannot be met, the horizon withholds rather than
silently dropping or renormalizing a large tail. Means above the existing pure
primitive's supported total mean 20 also withhold; rates are not clamped.
Different horizons may therefore have different availability. Bounded caches
hold immutable numeric supports only. Returned lists/dictionaries are fresh.

## Interfaces and bounds

`predict` returns schema `dragonhydra.realtime-probability/1`, experimental and
unverified labels, match/state revision, full-time result or null, the five
horizons, uncertainty and explicit assumptions. Each horizon contains boolean
`availability`, reason, effective minutes, next-goal probabilities, total-goal
vector/tail, bounded score rows/tail and entropy. An unavailable value is null,
not a zero-probability assertion.

Configuration accepts only `home_rate`, `away_rate` (0..5),
`rate_basis_minutes` (45..120), `own_red_card_multiplier` (0..1),
`opponent_red_card_multiplier` (1..1.5), `tail_tolerance` (`1e-14`..`1e-6`),
`max_goals` (integer 1..100), `comparison_low_scale` (0.1..1) and
`comparison_high_scale` (1..2). Values must be finite numeric values, not strings
or booleans. Unknown configuration fields fail closed.

`compare_models(state, config=None)` recomputes baseline, low-tempo and high-tempo
distributions. It returns compact per-horizon summaries and actual probability
spread. These variants share the same assumptions; they are not independent
trained models.

`bounded_counterfactual(state, changes, config=None)` returns compact baseline
and changed summaries plus deltas. Allowed absolute changes are `score` and
`red_cards` with home/away subsets, and `minute`. Each score/card side may change
by at most one, staying in 0..100 / 0..4. Time can advance by at most ten minutes
without crossing the current period end. Identity, source mode, status, period,
revision and end policy cannot change. FINISHED states are immutable here.
Counterfactuals do not mutate their inputs and do not estimate causal effects.
