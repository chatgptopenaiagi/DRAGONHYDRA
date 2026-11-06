# GENESIS-6 virtual relevance laboratory — delivery

**Result: COMPLETE for the first virtual vertical slice.** The broader research roadmap remains experimental. Every sporting observation, history, outcome, provider and credential used in this acceptance is fictional. No real sporting data or external AI request was needed or used.

Accepted application source: `c269cf00e712340977b97985eb27ec23c7709ab0`, branch `research/genesis6-realtime-20261106`. The initial implementation freeze was `33ad7d7c34e818e9e4d80780c14207d1ca5a8914`; the accepted source adds a measured display-readability correction. The preserved integration parent is `db8414ff6a08bd0c85310564771475e71d00e8a4`. This follow-up document records acceptance and does not change the sealed application bytes.

## Objective and implementation

The working capability investigates `R(X,Y,T)`: how including candidate information changes held-out prediction loss for a particular outcome and time. Probability calculation remains a mathematical function; an explanation cannot replace its output.

The implemented modules under `src/dragonhydra/realtime` provide strict virtual event contracts, correction-aware normalization, an append-only SQLite journal, model-dependency relevance decisions, incremental conditional forecasts, uncertainty, probability-change detection, server-owned replay controls, immutable branches, synthetic universe generators, proper scoring, a virtual Responses exchange and bounded mathematical tools. The opt-in `realtime_research` module and authenticated additive API reuse the existing application composition. Default registry behavior remains eighteen modules; virtual research adds one implemented module.

The mirrored web client provides fictional match state, horizon distributions, an interactive probability timeline, event/receipt clocks, provenance, uncertainty, actual tool results, relevance tables and explicit replay/fork controls. It never creates a scenario from a passive read. The verified display rounds numeric table cells to six significant digits, keeps full precision in cell titles and retains unrounded API values.

## Data and virtual time

The standard fictional match contains kickoff, routine possession/shot, duplicate delivery, goal, equalizer, halftime/resumption, red card, substitution, late goal cancellation, card correction, stoppage, disconnect/reconnect and delayed full time. Nineteen deliveries produce eighteen unique accepted observations, fourteen forecasts and seven completed virtual investigations. The final observed synthetic score is 0–1 after correction. All of those numbers come from execution receipts.

Time can be stepped, accelerated, paused and resumed. Rewind creates a separately identified match from an accepted prefix; the parent evidence remains immutable. Alternative futures are seeded. Restart pauses active virtual playback and reconstructs retained state. An actual child-process abrupt exit before forecasting also recovers a committed event without duplicating its forecast.

Five universes use different declared goal-hazard laws: constant, card-sensitive, informative possession, noisy possession and clock-sensitive. Corresponding episode indices share initial features, clocks and latent random draws. Changing the laws changes possible outcomes. This pairing is controlled simulation, not independent real-world replication.

## Mathematics and relevance

The baseline is a configured residual-time Poisson/competing-risk calculation, reusing the existing pure Poisson primitive. It computes full-time result, goal occurrence, conditional/unconditional next-scoring side, remaining-goal counts and score distributions for 1/5/10/30/full-time playing-minute horizons when meaningful. Known boundaries and stoppage are respected; suspended, unknown-end and unsupported states withhold unavailable forecasts. Finished matches become observed point masses. Rate effects are invented experimental assumptions, not fitted sporting effects.

The multi-world study ran **5,000 episodes: 1,000 per universe, 700 TRAIN and 300 disjoint TEST per world**. Only TRAIN labels fitted the exposure-aware rates. It retained all positive, zero and negative TEST utility estimates. The ten-minute scalar binary Brier-loss reductions include:

| World and candidate information | Mean loss reduction | Approximate paired 95% interval |
|---|---:|---:|
| Informative possession world / possession | 0.0472438 | [0.0291905, 0.0652971] |
| Noisy possession world / possession | 0.00000158737 | [−0.000643812, 0.000646986] |
| Card-sensitive world / card | 0.00901370 | [−0.00273102, 0.0207584] |
| Clock-sensitive world / clock | 0.00951948 | [−0.00733334, 0.0263723] |

Possession improved predictions under the law where it carries information and showed essentially zero measured benefit under the noise law. The card and clock intervals cross zero; those point estimates do not establish improvement in this finite run. Intervals are approximate and unadjusted for multiple comparisons. Shared worlds/horizons are correlated. No mutual-information, causal, unseen-universe or real sporting accuracy claim is made.

The operational gate remains an explicit dependency heuristic, with numerical information value marked NOT_ESTIMATED. It does not automatically change the running model after examining TEST results. The relevance experiment can expose missing baseline dependencies—for example, ignoring possession in the informative world—without defining all useful information as whatever the current baseline already consumes.

## Incremental computation

The actual persistent-service benchmark used equivalent 100, 1,000 and 10,000-event fixtures. At 10,000 events it made **107 forecasts versus 10,000**, avoiding 9,893 calculations. Shared checkpoints had **zero numerical drift**. Wall time was **119.681 versus 213.867 seconds**; p95 ingestion latency was **15.533 versus 28.893 milliseconds**. Maximum synchronous queue depth was one and no AI investigations ran in that benchmark.

These are single-machine, fixed-order synthetic measurements with tracemalloc overhead, not production capacity. The complete [performance report](PERFORMANCE-REPORT.md) includes memory, storage, CPU and timing limitations. The benchmark recorded pre-freeze file hashes. Final binding explicitly records the unused HTTP-router enum change and an AST-identical trailing-blank-line cleanup; measured probability/service/store/bridge bytes did not change. The later readable-table fix changes only mirrored web assets.

## Neural Bridge and uncertainty

The virtual reasoner performs a real bounded two-round exchange, requests local calculations, consumes their actual results and emits schema-validated evidence-backed output. All nine advertised tools have working handlers: current state, forecast, model comparison, quality, recent events, historical analogues, counterfactual, calibration report and prediction evidence.

The default investigation executes four tools. Tests also exercise all nine handlers, invalid evidence, unsupported tools, malformed output, timeouts, concurrency, budgets, lost context and pending-intent recovery. Requests are deduplicated, resource-bounded and never retried automatically after uncertain completion. Reasoning cannot submit shell commands, modify SQL, acquire providers, install software or override probabilities.

The API credential is the inert public marker `virtual-only-not-a-real-openai-key`. There is no real OpenAI SDK transport in this increment. Responses wire conventions follow the [official function-calling documentation](https://developers.openai.com/api/docs/guides/function-calling); protocol compatibility is separate from remote API verification. Real API calls are zero; actual billed tokens/cost remain null. These are not estimates of a real model's usefulness.

Statistical entropy, configured-rate sensitivity, parameter uncertainty, data flags and operational availability stay separate. The configured variants are not independently trained models. Real-world calibration remains UNVERIFIED. Same-data baseline versus mock-assisted probabilities are identical, so their proper-score improvement is zero. The explanation is not reported as improved forecasting accuracy.

## Executed acceptance

| Scope | Actual outcome |
|---|---|
| Final extracted package unit suites | **142 passed, 0 failed, 0 skipped**, 15.216 seconds |
| Checkout virtual-focused suite | 130 passed; 12 package-verifier tests passed separately |
| Benchmark guards | 7 passed |
| Final packaged offline journey | **18 checks passed**, 5,000 generated episodes |
| Final packaged Edge journey | **18 checks passed**, actual Edge 156.0.4314.58 |
| Final packaged restart journey | **7 checks passed**, server PID 37288 → 41000 |
| Existing-installation preservation | PASS, separate closing receipt |

Actual browser checks cover pairing, simulation labels, passive reads, explicit scenario creation, time controls, observed finish, historical timeline, horizon selection, real local tools, evidence, relevance table, visible validation error and immutable rewind. They verify served UI bytes and the sealed backend source identity. Saved wide/narrow screenshots and the final relevance table were visually inspected.

The complete [adversarial A–Z mapping](GENESIS-6-ACCEPTANCE.md) names executed tests for all requested failure classes. Earlier failing receipts remain: the initial metric-field typo in the acceptance harness, null-analysis rendering, invalid ARIA boolean rendering, an API enum-exposure gap and the preliminary benchmark's input-change rejection. They were not overwritten or converted into passes. The old data-bearing global suite is NOT_RUN in this virtual-only mission.

## Package and operation

The accepted package is `GENESIS6-VIRTUAL-0.1.0-c269cf0-development.zip`, **473,784 bytes**, containing **115 curated payload files** plus build metadata. Its SHA-256 is:

```text
4a93586e64b3d8bcde8ec0e47649ccce2e608804c894b57c0c28f657db4a76ab
```

Two independently collected builds from the clean committed source have identical bytes. CRC, exact inventory, per-file SHA-256/Git-blob identity, extracted launch and served application identity pass. The package excludes inherited sporting data, examples, real fixtures, original databases, credentials and runtime state. Dependencies are reused, not downloaded or installed. This is a runnable Python/web development ZIP, not a new native installer, EXE or APK. See [package instructions](../GENESIS6-DEVELOPMENT-PACKAGE.md).

The accepted extracted process is currently available at **http://127.0.0.1:19380/#research**, PID **41000**, with authenticated backend readiness and `payload_verified: true`. Its source is exactly `c269cf00e712340977b97985eb27ec23c7709ab0`. It is an owned foreground development process, not an SCM service. The simulation pairing token is `virtual-session-only-not-a-real-account-1234`; it is public, inert and restricted to this loopback laboratory. A stopped process can be relaunched with the extracted `scripts/Start-Genesis6.ps1` and the existing Python environment.

## Preservation and scope

Closing verification preserves ten protected service states/PIDs/accounts/start bindings, twenty-seven sealed package hashes across three generations, thirteen prior worktree bindings, eleven historical releases, 110 assets and sixteen tag references. Original failed dev.5 phase/lock/plan/bindings and detailed workflow evidence match their hashes. The installed Codex executable hash matches; it was not executed, replaced, updated or reinstalled. Existing forecasting mathematics remains byte-identical. No original SQLite, MariaDB or SQL Server sporting database was opened or modified by the workflow. Active database bytes are not falsely asserted static.

No new GitHub software release or installed-generation promotion was attempted. The previously published dev.8 release remains intact. New Joomla research integration, native WebView/Android feature acceptance, actual live feeds, real OpenAI inference, real-world calibration, market comparison, pre-arrival relevance and transfer to unseen universes are not established. The working web-first virtual slice does not claim those capabilities.

## Evidence and next increment

Private machine-readable closure is `LAB/GENESIS-6-REALTIME-INTELLIGENCE/evidence/FINAL-DELIVERY.json`. It binds the accepted source/package, separate documentation commit and individual receipt hashes. Final package receipts are beneath `runtime/package-r2/GENESIS-6-REALTIME-INTELLIGENCE/evidence`; final unit output and preservation receipts remain in the lane's root evidence directory. These paths are outside the sealed source. The frozen package retains its pre-build checkpoint documentation; this delivery follow-up supplies the later acceptance result without silently changing that package.

The smallest next research increment is a target/time-specific acquisition policy trained on past-only virtual evidence and evaluated on an unseen universe, with shared-prefix branches grouped correctly. Predicting relevance before an observation arrives remains a research question, not a verified result of this delivery.
