# Frozen held-out experiment 7331

The recorded experiment uses seed 7331, 200 cases per family and cost weight 1.
It was specified before its final held-out results were read. The software was
not tuned against these outcomes. Full machine output is
`evidence/offline-r2/STUDY.json` in the isolated engineering lane.

TRAIN uses constant, card_sensitive and tempo_signal; VALIDATION uses
clock_sensitive. FINAL_TEST uses noisy_signal, possession_inverse and
late_card_interaction. The latter two introduce different governing rules, not
just different random seeds. All branches with a shared root are grouped across
targets/families. Train, validation and test roots and their virtual phase times
are disjoint. Root groups are dependent within each group; 2,400 scenario-target
cases per policy represent **200 independent test roots**, not 2,400 independent
matches.

The four category-specific ridge regressions fit 20,358 TRAIN rows, including
3,183 genuinely pending fatigue examples. VALIDATION has 6,665 rows, including
1,090 pending examples. Scaling, labels and coefficients are TRAIN-only;
regularization selection uses VALIDATION. Model identity is
`ridge-future-relevance/1-1d7d8ec18549e44fd85ff281`, content SHA256
`1d7d8ec18549e44fd85ff28168ae7c99b5d0c4f085456da4c10600d83d4606c7`.
Its availability is `2036-01-03T13:30:11.99Z`, before FINAL_TEST decisions on Jan 5.

## Five-arm result

The Brier score is the sum across outcome classes, including two classes for a
binary outcome. These aggregate numbers mix targets/horizons and are descriptive;
the report retains matching target/horizon segments and calibration bins.

| Policy | Brier | Log loss | Mean acquisition credits | Mean computation credits | Mean utility |
|---|---:|---:|---:|---:|---:|
| Acquire all | 0.390351 | 0.701196 | 0.041665 | 0.002580 | -0.434596 |
| Acquire none | 0.376065 | 0.676305 | 0 | 0.001000 | -0.377065 |
| Random | 0.383977 | 0.687978 | 0.024052 | 0.001862 | -0.409891 |
| Handcrafted | 0.392654 | 0.702916 | 0.018659 | 0.001866 | -0.413180 |
| Learned | 0.377242 | 0.677977 | 0.000209 | 0.001015 | -0.378466 |

Utility is negative Brier minus weighted actual acquisition and computation costs.
Each policy receives its own equal 100-credit experiment acquisition budget and
the same match-specific constraints. Coupled clones have the same public initial
information and underlying outcome. Acquisition changes visibility, never goals.

Learned versus acquire-none mean net-utility difference is **-0.001401** with
approximate paired root-group 95% interval **[-0.002957, 0.000155]**. The learned
policy avoided most acquisitions but did not establish superior net usefulness.
These normal intervals have no multiplicity adjustment and do not establish
transfer beyond the specified virtual laws. No policy superiority is claimed.

## Predicting relevance before availability

There are 1,875 eligible pending-fatigue probes. Every estimate was made strictly
before the observation became available. Shadow acquisitions compare before/after
forecasts at the identical later acquisition cutoff. Outcomes are read only after
all five actual decisions have been frozen and the target becomes eligible.

Mean predicted local Brier improvement was -0.001827; realized mean was 0.014694.
Prediction MSE was 0.007250 versus 0.007269 for the constant TRAIN-pending-mean
reference. This small numerical MSE difference is not evidence of established
generalization superiority. The grouped signed prediction error was -0.016100,
95% interval [-0.024014, -0.008186]. Calibration remains unverified.

The interactive mechanism additionally demonstrates a frozen policy predicting
pending fatigue, deferring, resuming after two virtual minutes and later linking
the realized marginal change to that original decision. It is a software
acceptance fixture, not an independently selected predictive success example.

## Next increment

Study a predeclared sequential policy, including deferral execution and a learned
value model for redundant evidence, on another untouched rule family. Preserve
this experiment; do not reuse its final-test outcomes as an untouched test after
further training or selection.
