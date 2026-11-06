# Virtual Responses tool contracts

This module implements an offline simulation of the Responses function-calling exchange. It has no implementation that calls OpenAI. The wire shapes follow the official [OpenAI function-calling documentation](https://developers.openai.com/api/docs/guides/function-calling), consulted on 2026-11-06. Documentation compatibility does not prove remote execution or model capability.

Function declarations use the flat Responses shape: `type`, `name`, `description`, `parameters` and `strict: true`. Every object schema lists all its fields as required and rejects additional properties. The final structured result uses `text.format` with a strict JSON schema. Requests set `store: false`. No Chat Completions request or response format is used.

A simulated response can contain reasoning items and `function_call` items. Requests permit multiple calls in a response; the local handlers execute sequentially within the shared total cap of four. The bridge appends every returned output item to the next request before appending any tool results. Each result has exactly `type: function_call_output`, its original `call_id`, and a JSON-encoded `output` string. Call identifiers cannot repeat. A final answer is accepted only after at least one actual deterministic math tool result and must cite that result's call identifier.

Every tool requires `match_id`, which must exactly match the packet. The following arguments are the only additional permitted fields:

| Tool | Additional required fields | Operation |
|---|---|---|
| `get_current_match_state` | none | Read the synthetic state copy |
| `get_forecast_distribution` | none | Read the existing forecast wrapper |
| `compare_model_predictions` | none | Call `models.compare_models(state, model_config)` using the bound primary configuration |
| `get_data_quality_report` | none | Read quality status and flags |
| `get_recent_event_history` | `limit` integer 1–20 | Read a bounded event suffix |
| `get_historical_analogues` | `limit` integer 1–5 | Read explicitly supplied synthetic analogues; empty if none exist |
| `run_bounded_counterfactual` | `minute_advance` number 0–10, `score_delta` and `red_card_delta`, each exactly `{home, away}` with integer deltas −1–1 | Call `models.bounded_counterfactual` on a copy with translated absolute values |
| `get_calibration_report` | none | Read the supplied synthetic report or null |
| `get_prediction_evidence` | `evidence_ids`, at most 32 identifiers | Read existing, same-snapshot evidence only |

The counterfactual's minute advance stops at the known current period end. The shared math layer additionally enforces valid score/card bounds and supported match states. It cannot change match identity, source, status, revision, period or end-time policy. Score/card scenarios are hypothetical calculations and never append observed events or overwrite persisted probabilities.

Tool results label their provenance and include the actual returned data. The final strict schema has only summary, observed simulation facts, mathematical findings, hypotheses, evidence identifiers and limitations. Extra fields such as `probabilities`, a forecast mutation instruction or invented token usage are rejected. Mathematical findings must reference a real math call; evidence identifiers must belong to the packet's validated evidence set.

The shipped `VirtualResponsesTransport` emits a bounded simulated reasoning item and four allowed calls, then reads their actual outputs. It reports null usage. Tests may inject a different explicitly virtual transport to exercise failure paths. Such tests are synthetic protocol tests; they do not establish behavior of any real reasoning model, actual token costs, remote privacy guarantees or real sporting predictions.
