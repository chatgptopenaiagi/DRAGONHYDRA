# Registered logistics investigations

`analyze(world, method='compare_methods')` performs one of three finite computations: `compare_methods`, `bounded_method_search` or `counterfactual`. It accepts the trusted fictional `World` owned by this laboratory. A policy still receives only a public snapshot, never the simulator or hidden future demand. No analysis text becomes Python, shell, a database command, an HTTP request or an arbitrary callback.

Each result records a versioned analysis ID, cutoff, summary, observed facts in simulation, mathematical results, untested hypotheses, numerical candidates or intervention results, a proposed next experiment and explicit work counters. The original private world metadata is hashed before and after. Analysis does not mutate its inventory, control, cost ledger, cache, decisions or history. The surrounding service separately records the analysis and explicitly prices its work; such later service accounting is not silently performed by the pure analyzer.

## Method comparison and bounded invention

The analyzer takes at most five past eligible target dates across the two retailers. For each one-day forecast at day `d`, its observation cutoff is exactly `d-1`. The target sales must be uncensored and already available by the current analysis cutoff. Hidden true demand during a stockout is not substituted as a label. All eight existing baseline estimators run on their actual pre-cutoff history. The censored-Poisson method can use earlier known stockout lower bounds in fitting while still rejecting hidden true target demand.

The first chronological three dates form TRAIN and the last two VALIDATION when all five dates are available. Fewer dates produce correspondingly smaller cohorts; without both cohorts no candidate is selected. Forecasts use an expanding available history at each origin. The method/configuration registry is fixed in code before evaluation. The diagnostic chooses a proposal by past VALIDATION MAE, with a stable configuration-ID tie break. It never adopts a forecast method or changes a policy automatically.

`compare_methods` returns all eight baselines with TRAIN/VALIDATION MAE, signed bias, three pinball losses, counts and failures. `bounded_method_search` also tests exactly these five versioned configurations:

| Registered configuration | Numerical operation |
|---|---|
| `sba-scale-080/1` | SBA rate times 0.8 |
| `sba-scale-120/1` | SBA rate times 1.2 |
| `naive-ses-blend-025/1` | 0.25 naive rate plus 0.75 SES rate |
| `naive-ses-blend-050/1` | Equal naive and SES rates |
| `naive-ses-blend-075/1` | 0.75 naive rate plus 0.25 SES rate |

These are bounded method invention as registered configurations, not generated algorithms. The blend creates a Poisson law at the weighted mean; it is not a mixture-model posterior or a recovered hidden demand law. Scaling and combination rebuild the numerical distribution and its intervals coherently. Failed candidates retain their reasons and null metrics. Every evaluated candidate remains in the output, including those with zero or negative validation improvement versus SBA. A failed method cannot be selected using fabricated zero error.

With five dates and both retailers, the actual complete baseline comparison makes 80 forecast calls. The complete 13-candidate search makes those same 80 calls through a local memo and 110 probability-constructor invocations, with 130 scored candidate cases. Cached Poisson vectors may be reused; a constructor invocation is not a claim of cold numerical work. This is a tiny exploratory past diagnostic, **not an untouched held-out test**. Method selection and its observed validation result cannot be presented as independent evidence of future superiority. Censoring and distribution assumptions remain the limitations documented in [FORECAST-DECISIONS.md](FORECAST-DECISIONS.md).

## Counterfactual computations

`counterfactual` creates one baseline clone and five intervention clones from the identical current state and group. Every arm advances at most five virtual days with the same seeded exogenous stream mechanism. Registered interventions are:

| Intervention | Fixed change |
|---|---|
| `supplier_delay` | Add two configured supplier-delay days to eligible future schedules |
| `capacity_reduction` | Warehouse capacity times 0.75; reject when physical inventory makes that infeasible |
| `demand_shock` | Future virtual demand intensity times 1.5 |
| `policy_change` | Future control becomes `base_stock` |
| `shelf_life` | Shelf life eight days for the registered future-production mechanism |

The world owns each intervention's physical validation and exact semantics. The analyzer does not patch inventory or rewrite prior decisions. A decision already sealed at the current day is not retrospectively replaced. An invalid capacity intervention remains rejected in the output; it is not labelled a successful branch. A closed episode has no future window and performs no counterfactual steps.

Each successful branch reports future-window cost, immediate service and other eligible metrics plus paired differences from the baseline. Any known stockout since the last pre-window cycle completion carries into the window's cycle-success calculation, preventing a partial cycle from being reset to success. The cost difference uses actual clone-ledger changes over that window. Step attempts, completed steps, new forecast-cache misses, optimization candidates and routing calls are counted. A later branch failure retains completed work counts rather than erasing work already performed.

Counterfactual `supplier_reliability_scope` is explicitly `COMPLETED_WINDOW_DELIVERIES_ONLY_NOT_ALL_DUE_ORDERS`. Its `completed_delivery_on_time_rate` aliases that window's `on_time_rate`: outstanding orders are not part of this particular fraction. The main world's broader `World.metrics()` supplier-reliability measure instead considers all supplier-origin promises already due, including overdue and spoiled failures. These denominators differ and must not be presented as interchangeable. This delivery-scope label does not change paired future-window cost or immediate fill calculations.

The intervention is causal **only inside the declared simulator mechanism**, conditional on this one starting state and its configured exogenous streams. A demand shock intentionally changes demand; paired streams do not imply identical outcomes. Arms from the same root are not independent replications. No real-world supplier, market, operational accuracy or general optimality claim follows from these five-day comparisons.

## Experiment design and cost interpretation

`select_next_experiment(snapshot)` uses only eligible historical sales variance, observed censoring and completed lead-time variability. It selects a bounded cold-start, censor-aware, intermittent-method, supplier-delay or demand-shock investigation proposal. It ignores injected family, seed and future-outcome metadata. The result says `PROPOSED_NOT_EXECUTED`, has no calibrated information-gain value and cannot trigger acquisition or policy adoption.

Result classes remain separate: `OBSERVED_FACT_IN_SIMULATION`, `MATHEMATICAL_RESULT`, `HYPOTHESIS_UNTESTED` and `TESTED_INTERVENTION_IN_SIMULATION`. Neither a heuristic uncertainty statistic nor a conditional counterfactual is relabelled as observed future truth.

Computation units are a transparent virtual pricing proxy across explicit operations. `priced_work_counters` names the counters included. Completed world steps are an audit subtotal and are excluded from that sum because their attempts are already counted; there is no duplicate step billing. Forecast calls, constructor invocations, candidate scoring, cache misses and route/optimization work are distinct recorded counters, not hardware instructions. Real process CPU and elapsed milliseconds are separately observed. The analyzer does not claim API-token usage, paid-AI cost or exact machine-energy accounting.

## Executed checks

The nine analytics tests pass with sockets denied, alongside the 25 forecast/policy/metric tests. They check actual forecast-call counts, chronological cutoffs, future/unavailable-label exclusion, exclusion of censored target labels, all registered transformations, retained numerical failures/nonimproving results, immutable original worlds, five actual paired interventions, physical capacity rejection, past-only experiment proposals and rejection of unregistered executable text. A real stable-world probe completed all three analyses, including 30 actual cloned world steps for baseline plus five intervention arms. These checks do not substitute for root-owned service, journal, browser, held-out experiment or packaged acceptance.
