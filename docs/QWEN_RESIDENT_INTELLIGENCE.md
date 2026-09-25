# Qwen resident intelligence

**Adapter status: MOCK_ONLY. Live inference: BLOCKED.** Read-only discovery on 2026-09-25 did not establish an approved working Qwen-compatible runtime/model. No inference result is claimed.

Qwen's intended role is local, private analytical intelligence over the same bounded state used by Codex. It may summarize temporal changes, compare patterns, critique model assumptions, identify anomalies, interpret uncertainty and suggest hypotheses, features or research questions. Valid conclusion types are HYPOTHESIS, INTERPRETATION, CRITIQUE, RESEARCH_PROPOSAL, FEATURE_PROPOSAL and ANOMALY_REPORT. These types are non-evidence conclusions.

## Adapter contract

The [project-side interface](../src/dragonhydra/cognitive/adapters.py) is `analyze(snapshot, CognitiveRequest) -> CognitiveResponse`; the request carries an allow-listed task enum. Each response identifies actor, model and runtime/version when known, input/state hashes, output hash, completion/failure status and provenance. Unknown model/runtime metadata stays unknown. The default context/output limits are 65,536/8,192 bytes, with hard configuration ceilings of 131,072/16,384 bytes. The timeout setting defaults to 2 seconds and cannot exceed 30 seconds. Current mock/unavailable adapters return locally without a live inference operation; live transport timeout enforcement is a future adapter requirement. Failure closes the operation with no fabricated conclusions.

A deterministic mock exercises serialization, identity, failure and HYPOTHESIS preservation. Its model identity must make the mock visible. A mock response, valid interface or installed GPU is not live Qwen proof. The foundation does not install a model, change the canonical Python 3.14 environment, start a server or grant a runtime filesystem, web or database tool.

`MockQwenAdapter` identifies model `deterministic-mock-not-qwen`, runtime `stdlib-mock`, version `1`; its operational status is MOCK_ONLY. `UnavailableQwenAdapter` returns BLOCKED with `QWEN_RUNTIME_UNAVAILABLE` and no conclusions. Its model is UNKNOWN, not a guessed Qwen version. Neither adapter performs network, filesystem, SQL, subprocess or model-loading operations.

## Discovery boundary

The machine checks found no `ollama`, `lms` or `llama-server` command, no matching active Qwen/Ollama/Llama process, and no local listeners on the checked common runtime ports 11434, 1234, 8000, 8080, 14345, 11540 or 11500. A residual Ollama directory has no model inventory. An installed LlamaFarm launcher exists, but its inspected project/runtime directories provided no configured Qwen service. The inspected Hugging Face cache contained other models, not Qwen. Existing credentials were not opened. A dormant launcher is not an approved working inference endpoint.

These checks are bounded discovery, not proof that every disk location or possible custom port lacks a model. No runtime was started or modified. A later activation block must identify an already approved local endpoint/model or establish explicit runtime approval, verify actual identity/version and resource bounds, then record a genuine inference receipt. Keep MOCK_ONLY and live BLOCKED until that succeeds.

See [separation law](COGNITIVE_SEPARATION_LAW.md), [data contracts](COGNITIVE_DATA_CONTRACTS.md) and [current progress](COGNITIVE_PROGRESS.md).
