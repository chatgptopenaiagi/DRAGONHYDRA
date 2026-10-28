# Model status

The model implementation is [cognition/models.py](../../src/dragonhydra/cognition/models.py), version `football-models/1`. It runs four candidate models on currently eligible same-source, same-competition, same-period and same-settlement results:

1. Smoothed league outcome frequencies.
2. Independent Poisson home/away goals, using same-venue attack and concession averages shrunk toward league means; it reports finite-grid mass, expected goals, scorelines, 1X2, totals and BTTS. These are goal-count estimates, not shot-derived xG.
3. Recency-weighted league outcomes with an explicit half-life.
4. Same-day-batched Elo-style team ratings; its draw share comes from the frequency model.

The ensemble reports each model and weights. [adaptation.py](../../src/dragonhydra/cognition/adaptation.py) requires cutoff-eligible operational Brier evidence for every model, at least 20 scored cases per model and the same fixture cohort; stale or conflicting outcomes do not qualify. Otherwise the documented fallback is equal weights. The snapshot has zero stored operational evaluation records, so measured adaptive weighting is not yet established.

`evaluate` and `calibrate` can show a chronological **present-knowledge holdout** using data already captured by the system. Its historical outcomes were already known at evaluation time: it is a model diagnostic, not a live or historical STRICT_PIT backtest. Calibration bins are descriptive and may be small. No evidence establishes improved predictive performance, calibrated probabilities or an edge. No neural network model is implemented.

An independent execution on a copy of the frozen database at 2026-10-28
14:41 UTC selected the 2026-10-31 Bournemouth–Leeds fixture. The ensemble
reported home/draw/away 0.3595/0.3082/0.3323, based on 50 eligible training
results and equal weights. The 2025/26 present-knowledge frequency holdout
scored 76 matches: Brier 0.6470057659868708 (sample variance
0.018331170927197042), log loss 1.0706730837607508 (sample variance
0.03850355477407646), and accuracy 0.4605263157894737. There were zero
operationally scored predictions and zero matching market quotes. Full text
output is retained in the recovery archive's `metadata/intelligence-output.txt`.
