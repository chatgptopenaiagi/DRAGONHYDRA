# Virtual neural bridge

`dragonhydra.realtime.bridge.NeuralBridge` investigates synthetic event packets using bounded local tools and a simulated Responses-compatible reasoner. All sporting observations, histories, outcomes and provider responses in this lane are virtual. There is no network client, OpenAI SDK dependency, paid request, real API credential, real sporting record or automatic provider acquisition in this module.

The only accepted credential is the public inert string `virtual-only-not-a-real-openai-key`. It is a test marker and grants no access. The module never reads environment variables or credential files. An injected transport must explicitly declare `virtual_only = True`; this injection boundary is for trusted test code, not an authorization mechanism for external plugins. No production transport is supplied.

```python
bridge = NeuralBridge(context_provider, config={"state": previously_exported_state})
result = bridge.investigate(packet)
persist_result_and_budget(result, bridge.export_state())  # caller-owned storage
```

`context_provider(match_id)` returns the caller's bounded snapshot with `state`, `current_forecast`, `timeline`, `events`, `analyses` and `calibration_report`. The current forecast is the normal wrapper containing `forecast_id` and `forecast`; the forecast contains `model_id` and `full_time_result`. The bridge checks the synthetic mode, virtual match identity, state revision, observed score, model identity and exact probability vector against the packet. It accepts evidence only when its event, forecast or evidence identifier exists in that snapshot and belongs to the same match and mode.

The context provider must supply only the accepted prefix and information available at the selected forecast's cutoff. Identity and revision checks cannot independently prove that an injected provider has excluded every future record. The composed service supplies filtered state, events, timeline, analyses and calibration metadata; future fixture bodies and generator labels stay outside this context.

The packet schema is `dragonhydra.neural-packet/1`. Its exact fields and nested objects are defined by `PACKET_FORMAT`; `validate_packet` rejects extra or missing fields, duplicate JSON keys, nonfinite numbers, unnormalized vectors, inconsistent deltas, nonvirtual identities and encoded payloads over 16 KiB. Modes are `DEMONSTRATION` and `REPLAY`. This boundary does not turn a caller's unverified sporting claim into real evidence.

The default simulated model first requests model comparison, a bounded counterfactual, quality flags and evidence. The bridge actually calls the shared deterministic math functions with the trusted snapshot's `model_config`. When a forecast records `model_configuration`, it must exactly match that supplied configuration. This keeps sensitivity calculations tied to the primary forecast's assumptions. The next simulated response consumes those tool results before producing its structured explanation. It does not simply declare a model call successful. Changing the primary forecast is outside every tool contract.

Result schema `dragonhydra.neural-analysis/1` exposes `analysis_id`, `status`, `summary`, `hypotheses`, `evidence_ids` and `tool_results`, plus the structured `analysis`. The three classifications remain separate:

| Classification | Meaning |
|---|---|
| `OBSERVED_FACT_IN_SIMULATION` | A supplied virtual observation or stored synthetic snapshot |
| `DETERMINISTIC_MATH` | Actual output of a bounded local calculation |
| `AI_HYPOTHESIS` | A simulated reasoner's interpretation, not an observed event or causal result |

No model output can supply a replacement probability vector. Unknown evidence, unsupported tools, cross-match requests, unexpected output fields or invented usage leave an `uncertain` result. Actual math tool results remain available for inspection. `usage` and `cost` are null; `real_network_call_count` is zero. Virtual request and tool counts are measured separately and do not imply billed tokens or model performance.

The default limits are three Responses rounds, four total tool calls, eight investigations per match per UTC day, twenty-four per day overall, one concurrent investigation, a two-second transport deadline, a sixty-second circuit window after two failures, and thirty-two cached results. Hard round/call caps cannot be increased beyond three/four. Snapshot, response and tool payloads are also bounded. A timed-out transport may finish its daemon worker later; that worker cannot write sporting state, and its active slot blocks new work at the concurrency cap. There is no retry of the uncertain packet.

`export_state()` returns JSON data for caller-owned atomic persistence. Restoring it preserves day/match counters, packet hashes, cached results and circuit state. Changed contents under a reused packet identity are rejected. Cache eviction preserves a bounded seen-packet ledger; a seen packet without its cached body requires the caller's receipt instead of a new model call. Ledger exhaustion refuses new work. Restart persistence requires the caller to save the exported state. Crash safety also requires the caller to record a pending packet intent before investigation and to reconcile an unresolved intent without automatic replay.

`tests/test_realtime_bridge.py` exercises the public tool loop with real local model calculations while socket creation is denied. It covers all nine tools, wire schema, reasoning-item preservation, evidence/identity rejection, probability-override rejection, deduplication across state restoration, limits, timeout uncertainty and circuit behavior. These tests establish virtual integration behavior, not an OpenAI service connection or real forecasting quality.
