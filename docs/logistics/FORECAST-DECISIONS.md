# Logistics forecasts and inventory decisions

This module operates on fictional inventory counts and completed supplier receipts. It does not import sports state schemas, open files, contact a provider, invoke AI or modify inventory. Public functions return detached numerical evidence. Old forecasting implementations remain unchanged.

The existing goal-count Poisson helper has a maximum rate of 20 and support limit of 100, with goal-specific validation. Those bounds do not fit inventory quantities. The new domain kernel therefore uses standard-library `math` recurrence/log-PMF arithmetic and `statistics`; it introduces no dependency or external solver.

## Demand and availability

```python
forecast_demand(history, method='sba', horizon=5, cutoff=28,
                season=7, alpha=.2, window=7)
```

Each history record contains exactly `day`, `sales`, `censored` and `available_day`. Sales are bounded nonnegative numbers; day and availability are integer simulation days. A record cannot be available before its observation day. Duplicate days are rejected. Records whose observation or availability is after the forecast cutoff are excluded, with their count disclosed; their values do not enter estimation. Missing days are not fabricated as zero demand.

The result contains `schema_version`, `model_id`, `method`, `cutoff`, `horizon`, `mean`, `daily_mean`, `variance`, `quantiles`, `interval90`, `distribution`, `state` and `assumptions`. **Mean is total demand over the requested horizon.** It is not the one-day rate. Quantile keys are `0.1`, `0.5`, `0.9`; the central 90% interval uses the 0.05 and 0.95 discrete quantiles. State records eligible/excluded counts, the actual used days, estimator settings and cold-start status.

| Method | Actual estimator |
|---|---|
| `naive` | Last eligible uncensored sales |
| `moving_average` | Arithmetic mean of the last `window` eligible uncensored observations |
| `ses` | First eligible sales initializes the level; each following level is `level + alpha*(sales-level)` |
| `seasonal_naive` | Last eligible observation for each day modulo `season`; absent seasonal positions use the eligible overall mean. The next horizon's daily rates are explicitly recorded |
| `croston` | Positive-demand size and positive-arrival interval are separately exponentially smoothed; rate is size/interval |
| `sba` | Croston rate multiplied by `1-alpha/2`, the usual intermittent-demand bias adjustment |
| `tsb` | Every observed period updates occurrence probability; positive periods update nonzero size. Their product is the rate, so a run of observed zeros can reduce it |
| `censored_poisson` | Bounded grid maximum of the observed-count and stockout lower-bound likelihood |

Croston's first positive observation initializes its size and its interval to the number of observed periods through that first arrival. Later positive intervals count eligible uncensored observation periods. This is an explicit observed-exposure convention, not an assertion that missing or censored calendar periods had zero demand. TSB initializes occurrence from the first observation and size from the first positive value. With no informative observations, the declared cold-start prior is 0.5 units/day. An observed all-zero uncensored series can instead produce a zero point rate; that is not proof that rare demand is impossible.

Stockout sales are lower bounds on demand. The seven standard estimators omit censored records instead of treating them as true zeros. Their output is therefore conditional on observed uncensored periods. Because stockouts are informative missingness, this can bias their rate downward. Omission is an honest baseline, not a statistical correction.

For `censored_poisson`, an uncensored count `k` contributes `log P(D=k)` and a censored count contributes `log P(D>=k)`. A censored zero contributes zero log likelihood and reveals no demand information. The count fit requires integer units. Its 201-point grid spans 0 through `min(1000, max(10, 3*largest informative sales))`; step, upper bound, selected log likelihood and a boundary-fit flag are returned. All-positive censoring without any uncensored count has no finite unrestricted maximum: the bounded result explicitly reports that lack of identification. The grid is a bounded numerical estimate, not an exact continuous optimizer or recovery of hidden true demand.

## Predictive uncertainty and coherent updates

All eight point estimators currently use an independent Poisson predictive count distribution with the forecast total mean. The finite vector retains support through `ceil(mean + 12*sqrt(mean) + 30)`, normalizes the retained mass and discloses omitted tail probability. The supported total mean is at most 10,000 units. The zero-mean case is a point mass at zero. Mean, variance, normalized probability mass, quantiles and interval are checked for consistency; nonfinite values, enormous integers, boolean count quantiles and inconsistent moments are rejected.

This predictive assumption omits rate-estimation uncertainty, overdispersion, temporal dependence and censoring-induced selection. Intermittent demand may violate it substantially. The intervals are **UNVERIFIED_SYNTHETIC**, not calibrated coverage guarantees. Empirical interval coverage and quantile coverage are later measurements; they do not retroactively turn these assumptions into validated probabilities.

`rescale_demand(forecast, factor, evidence=None)` rebuilds the whole probability vector, mean, variance, quantiles and interval after a declared visible-signal adjustment. Seasonal next-day rates are scaled coherently too. It does not merely replace a displayed mean. The function cannot justify the factor: root's acquired fictional sensor and its pre-cutoff provenance must do that. Evidence metadata is bounded and must serialize without nonfinite values. A declared sensor adjustment is not an oracle or an accuracy claim.

`combine_demand(forecasts)` sums matching-cutoff, matching-horizon forecasts and rebuilds one coherent Poisson vector. Source model IDs and methods remain in its state. A zero-rate retailer can be combined with a nonzero retailer without dividing by zero or pretending the aggregate is a sensor multiplier. The aggregate assumes conditional count independence; it does not silently recover cross-location dependence.

## Lead-time components

```python
forecast_leadtime(completed, cutoff=28, prior=None, prior_weight=2.)
```

Each completed record has exactly `ordered_day`, `received_day`, `available_day`, `processing`, `transport`, `receiving` and `disruption`. Component integer durations must sum to the actual received-minus-ordered duration, bounded to 1 through 14 days. Receipt availability cannot precede completion. Future completions or unavailable receipts are excluded. A pending order's hidden future actual duration is never used.

The result contains a normalized total-duration `pmf` of `{days, probability}` rows, mean, population variance, component marginal PMFs/moments, completed/excluded counts and assumptions. With no custom prior, processing is 1/2 days with probabilities 0.7/0.3; transport is 1/2/3 days with 0.6/0.3/0.1; receiving is 0/1 with 0.25/0.75; disruption is 0/2 with 0.9/0.1. The prior components are independent. A custom prior supplies those four named PMF lists and must keep every positive-mass total in 1..14.

The default prior has the weight of two completed observations. The total predictive distribution mixes that prior with **empirical total durations**, preserving dependence seen in completed receipts. It does not reconstruct the total by multiplying fitted component marginals. Thus total variance need not equal the sum of component variances. Completed-receipt sampling can still underrepresent long outstanding orders; lack of a completed delay is not evidence of reliable future arrival.

## Service objectives and order decisions

`safety_stock(demand, lead, service_level=.95, objective='cycle_service_level', review_period=0)` mixes Poisson demand across the forecast lead-time PMF plus the declared review period. It assumes demand rate and lead time are independent. A cycle-service objective chooses the protection-demand quantile. A fill-rate objective instead finds the smallest integer target with expected shortage at most `(1-service_level)*expected protection demand`. Output exposes both implied unit fill rate and achieved no-stockout probability. They are different quantities; undefined zero-demand fill rate is null.

```python
recommend(inventory_summary, demand_forecast, lead_forecast,
          policy='order_up_to', params=None)
```

Inventory input requires `on_hand`, `on_order`, `backorder`, `inventory_position`, `capacity`, `reserved`, `atp`; `in_transit` is optional. Inventory position is exactly `on_hand + on_order - backorder`. ATP is exactly `on_hand - reserved`. Reservations are not subtracted a second time from inventory position, and in-transit units are a subset of on-order units. Recommendations conservatively enforce `on_hand + on_order + new quantity <= capacity`; they respect minimum order and order multiples. An infeasible minimum order can produce quantity zero.

| Policy | Rule |
|---|---|
| `reorder_point` | At or below the lead-time threshold, order a fixed quantity; default quantity is one review period's mean demand rounded upward |
| `order_up_to` | Order toward the lead-plus-review protection target |
| `base_stock` | Order toward the lead-only protection target |
| `s_S` | At or below `s`, order toward `S`; reject `S < s` |
| `probabilistic_cost` | Enumerate feasible bounded integer quantities, retain those achieving the configured forecast service target, then minimize declared expected one-period cost. If none meet the target, prioritize highest achievable service and then lower cost |

Default parameters are service level .95, cycle-service objective, one review day, minimum/multiple one and maximum order 500. Threshold overrides are `reorder_point`, `order_up_to`, `base_stock`, `s`, `S`, `fixed_quantity`. Maximum order is bounded to 1,000. Candidate evidence records actual quantities, costs and forecast service. Capacity can prevent a target being reached; no achieved real service guarantee is inferred.

Every policy reports `requested_service_objective`, `requested_service_level`, `achieved_CSL`, `expected_fill_rate`, `service_target_feasible` and `service_target_met`. Feasibility asks whether any quantity allowed by capacity, order bounds and multiples could meet the forecast target. Target met describes the selected recommendation; a heuristic can miss the target even when a different permitted quantity could achieve it. All comparisons use the configured lead-plus-review protection distribution. An undefined zero-demand fill objective is marked not applicable, with null feasibility/met values and null expected fill rate, rather than manufactured perfect service.

For the cost policy, a service-feasible set is mandatory when one exists. If it is empty, selection maximizes the configured service value before comparing cost, and `service_target_feasible:false` remains explicit. For example, Poisson protection demand of mean four requires eight units for 95% CSL but six units for 95% expected fill. Those quantities remain required even when a zero order would have the lowest unconstrained cost. A capacity of three makes either target infeasible; the fallback does not relabel a complete enumeration as target success. Service calculations use new-window usable stock `max(0, inventory_position + quantity)` so an existing backlog does not produce a negative fill fraction. Existing backlog still contributes to the cost shortfall.

This service disclosure assumes the recommended quantity becomes available as represented by the protection-stock surrogate. A later route, supplier, warehouse-ATP or shipment-capacity limit can reduce the physically executable quantity. Recommendation-level forecast feasibility therefore does not claim realized service or feasible network-wide delivery. The caller must retain the actual shipment quantities alongside recommendations.

The seven cost names are `holding`, `ordering`, `shortage`, `transport`, `spoilage`, `acquisition`, `computation`. The probabilistic policy charges expected excess for holding/spoilage, expected shortfall for shortage, a fixed positive-order charge and a per-unit transport charge. Root supplies the actual virtual ledger rates and observable route quote through `params.costs`; any spoilage charge here is an explicit excess-inventory risk proxy, not privileged future spoilage. Acquisition and actual computation costs are measured by the surrounding experiment, not invented inside this order-cost calculation. Their externally charged amounts remain in the actual seven-component ledger. This service-constrained bounded static search is not a general dynamic optimum. Shelf age, dynamic supply allocation and downstream interaction remain the simulation/decision layer's responsibility. Ordering nothing can be the cost minimum when existing stock already meets the forecast target or when no demand exists; a service-targeted policy can still lose after actual cost.

## Outcome metrics

`evaluate_outcomes(rows, cutoff=..., naive_scale=None)` reads only outcomes available by the cutoff. An eligible daily aggregate row contains exactly:

```text
day, available_day, demand, fulfilled, backordered, lost_sales, on_hand,
stockout, cycle_complete, deliveries, forecast, costs
```

`fulfilled` means immediate fulfillment, with `fulfilled + backordered + lost_sales == demand`. Newly unfilled demand must mark a stockout. Clearing an old backlog later does not increase that earlier day's immediate fill rate. Deliveries have `promised_day`, `received_day`, `lead_time`; only actually completed deliveries can appear. Costs contain all seven named nonnegative components.

The optional daily forecast has exactly `mean`, `quantiles`, `interval90`, `horizon:1`, `cutoff:day-1`; otherwise it is null. Sum the two retailers' one-day forecasts before comparing with aggregate daily demand. A five-day policy forecast cannot be scored against a one-day outcome. MASE is computed only with a positive caller-supplied past TRAIN naive-MAE scale. A scalar cannot prove its own provenance: the experiment must bind that scale to TRAIN, not derive it from held-out outcomes.

Metrics include immediate unit fill rate; completed-cycle service level; stockout days; cumulative new backorders and lost sales; mean observed daily on-hand inventory; study-horizon unit turns; seven cost totals; completed-delivery on-time fraction/reliability; lead-time mean/variance; signed forecast bias, MAE, eligible MASE, three pinball losses, central interval coverage and empirical quantile coverage. A cycle fails if any stockout occurred since the preceding synchronized cycle completion. Trailing incomplete cycles are excluded. Missing days are not imputed, and turns are not annualized. Undefined denominators produce null rather than a manufactured perfect score. Outstanding unreceived orders do not become successful delivery observations.

## Executed focused verification

At this implementation checkpoint, the two assigned focused files pass 25 tests: 12 forecast tests and 13 policy/metric tests, with socket creation denied. They exercise all eight real estimators, the known censored likelihood optimum near `log(2)`, zero-stock censoring, future/delayed availability, cold starts, huge/nonfinite numbers, false moments and quantiles, completed-component correlation, distinct CSL/fill targets, coherent visible-signal scaling and aggregate demand, actual service-constrained cost search, feasible and infeasible targets, inventory identities, capacity/MOQ constraints, cost accounting and outcome-horizon leakage. The separate nine analytics tests also pass. No system/browser/packaged acceptance or learned-policy superiority is inferred from these unit tests. Root-owned integration and held-out experiments remain separate evidence.
