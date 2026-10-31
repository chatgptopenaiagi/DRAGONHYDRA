# Optional offline model integration

The current source supports an explicit local-model action and structured sports
packages. The standard explanation remains deterministic. Frozen releases and
the original C7 installer remain separate. The installed A6 workstation contains
the optional action, package/3 path and persistent setup. Its current-host report
is `dist/connections/workstation-a6/TEST-REPORT.json`. One repair and the installed
Edge default/2, explicit/3 export, unconfigured fallback and idempotent replay
checks passed with old data and model settings preserved. This upgrade performed
no model inference or provider acquisition.

In current source, open **Configure local model** in Analysis. Save the existing
local runner's loopback endpoint and its password-field key. The running Windows
server encrypts that key with its own DPAPI identity and saves only the endpoint
in protected `local-ai.json`. Configuration reads return source/configured status
without the key. Saving does not start a runtime, download a model or make an
inference request. **Remove saved key** removes the stored credential explicitly.
A3 source and frozen-runtime tests pass. The A3 installer was repaired into the
separate test workstation, and all **nine installed acceptance groups passed**:
UI save through LocalService, key-free reads, persisted vault configuration after
restart, real offline Qwen selection with exact citation, UI key removal,
endpoint cleanup, runner shutdown and deterministic fallback after another restart.
The stored data/schema and original C7 services remained intact. Evidence:
`build/workstation/evidence/local-ai-service-a3-20261031/journey.json`.

The accepted request used 159 prompt tokens and 27 generated tokens; prompt and
generation took 2.941 and 2.297 seconds. The owned runner ran under a separate
interactive Windows identity, with LocalService as its authenticated caller.
Accepted inference after service restart proves that the running service could
decrypt its saved key; it does not claim the product automatically launches a
model process or that LocalService loaded the model file. The temporary key and
endpoint were removed, the owned runner exited 0 and its port was released.

A4 repeated the installed nine-group proof after the provenance/health update,
with five additional passive health assertions. Configured status is
`configured_not_tested`, with `runtime_health:not_checked`; health reads do not
decrypt a key, start a runtime or request inference. Broken optional settings
report `misconfigured` while the SQLite service remains ready. An accepted job
remains separate evidence of an actual successful request. A4 cleanup restored
the exact unconfigured state and kept the service ready.

Open a football match's **Analysis** tab. **Export sports package** downloads its
retained facts, evidence reference and SHA-256. **Use local model** queues a
separate durable job. Missing configuration, unavailable inference or rejected
output produce a labelled deterministic summary with a diagnostic code.

The implemented contract is deliberately small: the model selects one supplied
source fact. Application code checks the exact allowed statement and resolves
`E1` to its full retained evidence ID. This is not free-form analysis, forecasting,
an evaluation of predictive quality or a claim that model-generated new facts
are trustworthy. The UI labels accepted output **LOCAL MODEL · SOURCE FACT
SELECTION**. A source correction after job submission does not replace the
package's original evidence reference.

## Optional exact context package

The programmatic constructor
`local_ai.build_context_package(product, match_id, context_record_id)` explicitly
selects `sports-evidence-package/3`. Existing package exports, empty-body
local-explanation commands and ordinary UI actions still use package/2. The default constructor's package,
prompt and accepted-output format remain unchanged when context is available.

Package/3 adds exactly three facts: the retained StatsBomb event-row count and
each native team's source squad-entry count. It contains no event arrays, player
lists or inferred sporting metrics, and retains the 16 KiB limit. These are counts
of source rows, not official match statistics or starting-team claims. C1 binds
the immutable context record ID/hash, exact parent E1, parser version, context
receipt clocks and the two original document acquisition IDs/hashes/URLs/clocks.

Construction requires C1 to match the selected current parent. Queued grounding
reconstructs its exact older E1/C1 without consulting a newer match or context.
`source_context.by_id` verifies the selected predecessor prefix structurally and
reconstructs source bytes for the selected snapshot only. A later pending or
corrupt revision cannot replace queued facts; missing selected evidence fails
closed. These reads neither initialize context tables nor repair records or
fetch providers.

The package/3 model output is only `{"fact_id":"F1"}` with a constrained ID enum.
The application resolves wording and citations. A context fact cites E1 and both
role-labelled acquisition metadata links, retaining C1's explicit ID/hash and
clocks; it never labels the mutable latest-context URL as an immutable citation.
All four supplied IDs remain in `input_manifest`, including when unavailable or
rejected inference returns the existing status fact with an E1-only citation.
Invalid grounding is rejected before settings access or inference.

Source unit and independent acceptance results are recorded under
`build/connections/sports-package-3-20261031`. Synthetic fact-ID selections prove
the context-count citation path. Analysis offers separate **Use local model with source counts**
and **Export package with source counts** actions when verified context matches
the displayed parent. Opening Analysis reads retained context only. Missing or
changed context keeps the ordinary actions available; acquisition remains the
separate explicit action in Statistics. A6 includes this contract; installed
acceptance reused the existing real context without another acquisition. The
one UI job returned the expected AI_NOT_CONFIGURED deterministic fallback with
one parent citation and all four input IDs. Model configuration stayed blank.

One actual existing Qwen/API probe passed in `qwen-api-r1/report.json`, with the
3,167-byte real-retained package/3 (4,407 event rows, France24/Argentina26 and the
original3:3). The model selected F1, the supplied finished-status fact: one E1
citation and all four input IDs were preserved. It did not select a context count;
real model selection of the three-citation count path is unproven. No repeated
request was made to force a different selection. The actual interactive source
API/worker request took7.792s, with4.385s model startup. Both owned processes
exited0 without forced termination, their ports were released, temporary
credentials were removed and source DB/sidecar/raw/marker hashes stayed exact.
This is source API/worker acceptance, not installed LocalService/package/3 or an
air-gap claim.

`scripts/probe_local_ai.py` accepts `--context-record-id` with an explicit
`--match-id`, either directly or with `--verify-api`. It grounds the selected
record before starting the runtime and copies only the four verified document
dependencies into its exclusive API backup. The existing `--verify-browser`
journey remains package/2-specific; the opt-in flag rejects that combination.
The separate `tests/ui/local_ai_context_journey.py` verified eight real Edge/API
groups with clearly labelled synthetic selections and no model process.

## Packages and API

Authenticated endpoints:

- `GET /dragon/api/v1/matches/{match_id}/analysis-package` returns
  `sports-evidence-package/2`, with one source-scoped football event, evidence
  mapping, allowed observations and an independently recomputable package hash.
  The explicit query `?context_record_id=source_context:<64 lowercase hex>`
  selects package/3 and must match that current parent exactly.
- `POST /dragon/api/v1/matches/{match_id}/local-explanations` accepts `{}` or
  `{"context_record_id":"source_context:<64 lowercase hex>"}` and
  returns HTTP 202 with a durable job. Reuse its `Idempotency-Key` to retrieve the
  same command. Explicit package/3 replay returns its original frozen job after
  later source changes; another match/context/kind with that key conflicts.
  Poll or cancel through the existing jobs API.
- `POST /dragon/api/v1/matches/{match_id}/explanations` retains its standard
  deterministic behavior.

The optional worker uses stored setup, with `DRAGONHYDRA_LOCAL_AI_URL` and
`DRAGONHYDRA_LOCAL_AI_KEY` independently overriding their stored fields in the
server process. Configuration shows which source is effective. Removing a stored
key does not unset an environment key; change that service environment separately
when appropriate. Non-Windows servers use the protected environment for the key;
this is not a portable encrypted Linux vault. The URL must be an explicit
`http://127.0.0.1:<port>` origin with no path, credentials, query or fragment.
System proxies and redirects are disabled for inference. Inference requests cannot
provide an endpoint, model key or substitute package. Use protected process or
service configuration; do not put model keys in URLs, datasets, logs or APKs.

The separate administrator setup endpoints are
`GET/PUT /dragon/api/v1/local-model/configuration`. A PUT supplies `endpoint`,
optional password-field `credential`, or `remove_credential:true`; save and remove
are separate actions. Inference requests accept only the optional context ID and
cannot replace the server's selected endpoint or supply an evidence package. Windows vault files
must be decryptable by the same server identity; changing account/machine can
require saving the key again through that running server.

The adapter calls the existing llama.cpp `/completion` interface with a JSON
schema, a 192-token cap, deterministic sampling and a bounded request timeout.
The worker uses 25 seconds so an unavailable model cannot indefinitely occupy
the existing worker. Requests may still fall back on slower hardware. No model
starts automatically when reading packages or requesting standard explanations.

## Existing Windows runtime proof

The bounded probe reuses the existing installation:

- Runner: `D:\LocalAI\runtime\llama-b10665\llama-server.exe`, build 10665,
  commit `ca3d5a3e1`.
- Model: `D:\LocalAI\models\Qwen3-4B-Q4_K_M\Qwen3-4B-Q4_K_M.gguf`,
  2,497,280,256 bytes, SHA-256
  `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.

Run from the project using a fresh evidence directory:

```powershell
.\runtime\server-env\Scripts\python.exe -B scripts\probe_local_ai.py `
  --state runtime\connections\product `
  --output build\connections\evidence\local-ai-<fresh-name>
```

The probe checks runtime/model integrity and available RAM, launches only its
owned hidden CPU runner with `--offline`, uses a protected temporary model key,
and removes that key and stops its process afterward. It verifies authentication,
the structured contract and exact citation resolution. It does not enable an
always-running model service or modify the installed workstation.

Add `--verify-api` to also create an independent SQLite backup, launch its own
temporary API server and exercise the actual authenticated package/job/citation
path. The original coordinator and database remain separate. On 2026-10-31 this
passed as `API_CONSTRAINED_OFFLINE_INFERENCE_VERIFIED`; the durable job completed
in 8.338 seconds, and a fresh SQLite reader confirmed its terminal result. Both
temporary servers exited 0, both ports were released and the model key and API
token were removed. Evidence:
`build/connections/evidence/local-ai-20261031-probe3-api/report.json`.

Add `--verify-browser` to include the real Edge journey before those temporary
servers shut down. This also implies `--verify-api`. Six browser groups passed
with the actual Qwen result, its accepted fact-selection label, package download,
independent hash calculation, citation popup and repeatable standard explanation.
Evidence: `build/connections/evidence/local-ai-20261031-probe4-ui/report.json`
and `browser/journey.json`. The first API job took 12.630 seconds; browser checks
took 20.347 seconds, including another real inference request. Both temporary
servers exited 0 and temporary credentials were removed.

On 2026-10-31, this command passed with
`CONSTRAINED_OFFLINE_INFERENCE_VERIFIED`, 4.577-second startup and a 20.808-second
request. It accepted “The retained source labels this match as scheduled.” and
resolved the exact retained source evidence. The model exited 0, the temporary
key was removed and its port was released. Evidence:
`build/connections/evidence/local-ai-20261031-probe1/report.json`.

The runner used an existing local model with `--offline`; no external model
provider, download or installation was used. This is not a machine-wide air-gap
test. The earlier rejected chat-based attempts remain under
`build/workstation/evidence/optional-ai*`; the new direct completion contract
does not retroactively validate their malformed output.
