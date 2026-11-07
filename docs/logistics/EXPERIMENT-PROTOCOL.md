# Predeclared inventory experiment

Primary run: seed **8821**, **40 independent root groups**, 20 operational days
per final episode, model target five-day gross relevant-cost reduction. This
configuration is recorded before the final results are generated. Debug seed42
and tiny dashboard previews are separate, not final scientific evidence.

TRAIN rule families: stable and intermittent. VALIDATION: seasonal. Final
familiar rules are stable/intermittent on new roots; final unfamiliar rules are
supplier_disruption, perishable and multi_location. Training, validation and final
seed ranges and availability phases are disjoint. Family variants share a root
and are dependent. There are200 final root/family contexts and1,800 policy
rollouts, not1,800 independent worlds. Familiar/unfamiliar results are reported
separately with equal-root paired approximate intervals.

Generated training contexts occur at initialday28 and after seven baseline days.
Some later contexts already contain one legitimately acquired observation, so
known evidence and redundancy are not all-zero training features. Budget varies
among0.25/2/10credits. Customer accounting includes lost-sales and backorder
contexts. Labels are coupled future cost contrasts, not handcrafted importance.
For pending information the public feature snapshot freezes before availability;
both branches share their prefix through eligibility and settle at the same
original t+5 target. Acquisition cost is removed from the gross-value label and
subtracted explicitly by the decision rule. Future state never becomes a feature.

Regularization is selected using VALIDATION only. Every TRAIN label must be
available by the first validation decision; the frozen model availability is no
earlier than either phase's labels. Group overlap, future receipt dates and
modified parameters are rejected. The model is frozen before any final world is
constructed. No final result feeds fitting, selection or later predictions.

Nine arms share underlying demand and comparable budgets: five inventory
policies with acquire-none, plus order-up-to with acquire-all, seeded random,
handcrafted and learned acquisition. Each episode gets10acquisitioncredits; the
arm experiment budget is the explicit sum of these allocations. Source demand
does not change when information is acquired. Orders can change observed sales,
censoring and completion histories; that endogeneity is retained.

The fixed inventory forecasting method for policy comparison is SBA. Eight
forecast baselines are separately evaluated on one common acquire-none observed
history per root/family. Those diagnostic forecasts do not enter decisions.
Daily forecasts are issued before the later actual demand outcome. MASE uses
only a positive TRAIN naïve-error scale; otherwise it is undefined.

All final contexts also receive an evaluation-only pending-intent probe, after
actual policy trajectories have been frozen. Its pre-reveal gross-value estimate
is compared with the coupled subsequently measured benefit and a TRAIN-only
constant reference. This measures relevance prediction separately from actual
service and net cost; no favorable cases are cherry-picked.

Primary comparisons are total relevant cost and immediate fill rate against
order-up-to/acquire-none, with CSL, stockout frequency, backlog/lost sales,
inventory/turns, delivery reliability, bias/MAE/MASE, pinball/calibration/coverage,
acquisition and computation reported separately. Lower cost accompanied by worse
service is a trade-off, not automatic decision success. Approximate intervals
have no multiplicity adjustment. A negative research result is acceptable.

Actual source identity, mathematical-file hashes, frozen model, virtual training
examples, full record hashes and later results belong in fresh evidence paths.
The package replay can import that actual fitted model and reproduce the first
predeclared root without rerunning model selection. That is reproducibility,
not a second untouched test. GitHub remains HELD until software, browser,
restart, benchmark, preservation and package acceptance genuinely pass.
