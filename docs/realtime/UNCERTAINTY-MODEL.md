# Uncertainty in fictional probability experiments

Every model output is `EXPERIMENTAL` with calibration `UNVERIFIED`. All events,
states, assumptions, outcomes and market examples are virtual. No historical
training, live observation, provider or OpenAI call is part of this calculation.

Outcome entropy is `-sum(p*ln(p))` over home/draw/away. Normalized outcome entropy
divides by `ln(3)`; next-goal entropy covers home, away and no goal. Entropy
describes the spread of the configured distribution. A low entropy value does
not establish correctness, data quality, predictive skill or confidence. A
FINISHED point mass has zero entropy because it is an observed fictional score.

`model_comparison` measures actual differences after independently recomputing
configured low/base/high tempo variants. Shared assumptions, evidence and model
form make their errors dependent. Variant spread is neither a confidence interval
nor an empirical estimate of parameter uncertainty. Constant hazards, independent
increments and arbitrary card multipliers omit score feedback, tactics, fatigue,
correlated goals and unannounced stoppage. The separate virtual-universe relevance
experiment can test some assumptions under invented rules; it cannot validate
real-world calibration or establish AI improvement.

Numerical uncertainty is separately visible. `tail_mass` bounds conditioning
error from omitted score cells; the total-goal vector has an explicit tail
bucket. Failing the requested tail bound yields unavailable probabilities.
Unknown ends, suspended play, unsupported periods and unresolved period
boundaries also withhold. No unavailable value is replaced with a confident
fallback. Data quality is a separate caller-owned observation contract; extra
metadata, future outcomes and market values never become model features here.

All calculations are deterministic from the validated state/configuration. No
wall-clock reads, random draws, provider acquisition, training, storage or legacy
forecast requests occur. This makes correction/replay comparisons inspectable
without claiming that a synthetic replay is a historical point-in-time forecast.
