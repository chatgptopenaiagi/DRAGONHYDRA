# Relevance is the research target

For outcome `Y`, candidate information `X` and availability cutoff `T`, the probability kernel estimates `P(Y | X,T)`. The laboratory separately investigates `R(X,Y,T)`: how much including `X` reduces held-out prediction loss. This is contextual and target-specific; a probability shift alone is not evidence of usefulness.

The operational gate asks whether an observation changes a dependency of the configured residual-time model or the data-quality state. A same-clock possession update and a routine shot are retained but avoid recalculating a model that does not consume them. Time, score, red cards, explicit status/end changes, corrections and quality changes can require new calculations. Decisions preserve action, reason codes, event/state identity and a heuristic score; `expected_information_value` remains null and `information_value_state` is `NOT_ESTIMATED`. Computation avoided is counted only when it was actually avoided, including against the forced-recomputation reference.

This choice is model-specific. In the `tempo_signal` universe, possession really is informative. The held-out experiment can demonstrate the loss of ignoring it, even though the baseline runtime model does not yet consume it. Evidence of utility does not silently change the running model: a learned policy requires a new identity and acceptance. This deliberate separation lets relevance research expose missing model dependencies instead of defining relevance as whatever the current model already uses.

## Controlled research

Five worlds share the same seeded initial features, clocks and latent random draws, while their goal-hazard assumptions vary. There are constant, card-sensitive, informative-possession, noisy-possession and clock-sensitive worlds. TRAIN is the first seventy percent of episode IDs; disjoint TEST is the final thirty percent. Only TRAIN labels fit bounded exposure-aware goal rates. Hidden simulator states and future TEST outcomes never enter observation features or model/tool context.

The estimate is `mean_TEST[loss(TRAIN-only baseline,Y) - loss(TRAIN-only feature model,Y)]`. Positive, zero and negative results are retained. The scalar binary Brier loss is `(p-y)^2`; log loss uses natural logarithms, so its improvement is nats per episode. These differ from the generic multiclass evaluator's sum over all class probabilities. Approximate paired intervals report sampling uncertainty; there is no multiple-comparison correction. Neither estimator is presented as mutual information, a causal effect or calibrated real sporting relevance.

The experiment evaluates card, possession, clock and combined features at one, five, ten, thirty and remaining-regulation-minute goal-occurrence targets. Rates are fitted on the ten-minute target only, then evaluated at each actual clipped exposure. The same response also reports a deliberately misspecified no-clipping comparison. Raw per-world reports and table rows come from the same actual calculations.

Cross-universe matching reduces random differences in starting conditions; it does not make the worlds independent datasets. Good results inside known laws do not establish transfer to an unseen universe. Predicting the value of information before that information arrives is a distinct next research increment, not an implemented or verified capability.
