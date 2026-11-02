# Module contracts and evidence states

`KernelConfig` binds product, edition, installation ID, environment ID, build ID,
source commit, version, observation lifetime and explicitly disabled modules.
The deployment loader validates canonical private roots and ports before passing
this configuration. The source/test default creates a distinct state-path-derived
identity; it never resolves another installation or copies its credentials.

Each immutable definition declares ID/name/description/category/origin, actual
application build version, implementation reference, required and optional
dependencies, configuration requirements, supported operations, data domains,
capability-to-operation/dependency mappings and verification-reference locations.
Schema and engine contract versions, missing implementations, unsupported
capabilities, duplicate IDs, missing required dependencies and required dependency
cycles are rejected before startup. Missing optional modules limit only the
capabilities that declare them; unrelated modules can start.

The single registry has `layer=engine` or `layer=supporting`. Supporting bindings
use `core-next.support/1`; engines retain `core-next.engine/1`. IDs, configuration
reference names, duplicate dependencies and supported callable operations validate
before startup. A module's success is scoped evidence, not blanket verification
of its capabilities. `capability_status` lists each operation's state, timestamp,
expiry, observation ID and scope. `verified_operations` contains only fresh
successful explicit operations (or the actual supporting status probe). Successful
reads cannot verify writes, forecasts, provider acquisition or model inference.
The deterministic AI package can be verified while optional inference remains
unconfigured. Dependency failures limit only the applicable operation.

Definitions are not observations. Observations carry installation/module IDs,
state/reason, bounded observation and expiry times, last successful observation,
flat scalar metrics and evidence scope labels. Tests referenced in a definition
are reproducible checks, not a claim those checks ran for a deployment.

The canonical read view also provides `module_id`, `display_name`, `kind`,
`responsibility`, `actual_version_or_build` and `implemented_capabilities` while
retaining the older aliases. `implementation_state=BOUND` means the concrete
implementation, schema and declared operation binding validated; it does not mean
the operations ran. `configuration_state` remains `UNVERIFIED` unless cached
configuration availability was explicitly observed (`CONFIGURED` or
`NOT_CONFIGURED`), or the profile explicitly disabled the module (`DISABLED`).
`runtime_state` starts `UNVERIFIED`. For engines it derives only from an actual
scoped last-operation record, its own expiry, or explicit shutdown. Supporting
modules expose their actual bounded status observation through the same field,
with exact profile/build/module binding and `runtime_verification_scope` set to
`SUPPORTING_STATUS_OBSERVATION_ONLY`. This is reachability/schema evidence, not
full administrator, device or service acceptance. Engine operation evidence is
labelled `EXPLICIT_ENGINE_OPERATION_ONLY`. Missing configuration evidence remains
separately `UNVERIFIED`; a successful storage schema read does not invent a
configuration measurement. None of these
substates implies that every configuration requirement or domain workflow passed.

`reason_code`/`human_readable_reason`, `last_success_at`, `evidence_expires_at`,
`sanitized_metrics` and `evidence_reference` appear both on the module and nested
observation. Counts retain their separate `metrics_sampled_at`,
`metrics_expires_at` and `metrics_state`; ordinary reads cannot renew old counter
evidence. Actual last-operation state/time/evidence is retained separately.

| State | Meaning |
|---|---|
| NOT_IMPLEMENTED | A declared optional implementation is absent. |
| NOT_CONFIGURED | Required configuration for the selected optional feature is absent. |
| UNVERIFIED | Implementation/configuration exists but relevant execution has not been observed; neutral, not fresh success or observed failure. |
| READY | The explicitly described bounded observation or operation succeeded. |
| DEGRADED | Partial data, failed observation or required dependency limits operation. |
| UNAVAILABLE | The requested feature/data/cohort is currently unavailable. |
| NOT_APPLICABLE | An adapter explicitly establishes the capability does not apply. |
| EXPIRED | Previous evidence reached expiry; neutral current readiness, with original clocks retained and no silent refresh. |
| UNKNOWN | Relevant current state has not been established; neutral. |
| STOPPED | Explicit kernel shutdown completed for this engine. |

Startup performs bounded local read-only SQLite counts and redacted configuration
availability checks in required dependency order. It starts no provider, model,
installer or additional worker. Explicit operations update their scoped cached
observations. A deterministic AI package/fallback never establishes model readiness.
Empty evaluation cohorts do not establish evaluation readiness. SQLite counts
include retained revisions and are labelled accordingly.

Authenticated `GET /dragon/api/v1/modules` returns
`{schema_version, installation, inventory, items}` (six engines by default).
`?scope=all` returns six engines plus twelve supporting bindings;
`?scope=supporting` returns only supporting bindings. `GET /modules/{id}` returns the same
identity with a flattened selected module. Both only render cached state. They
never refresh observations, read sports tables, acquire providers, perform
inference, enqueue jobs, install software or restart anything. Standard Joomla
HMAC authentication retains its existing nonce replay journal. The API cookie
uses an installation-derived name; original `dragon_session` is ignored.
`POST /session/logout` revokes only the current installation's presented session.

`GET /system` preserves the existing backend/capabilities keys and adds
installation identity and module-state counts. Internal engine commands are not
arbitrary public HTTP dispatch. The Control Center exposes supported status
reads; mutations require a separately specified typed/authorized operation.

## Observation lifecycle and operation classes

Class A status reads are passive. Class B local observations run on the existing
job worker, not a new process/thread: default cadence 30 seconds, expiry 300
seconds, configurable within KernelConfig's bounded interval/TTL. Startup and an
authorized `POST /dragon/api/v1/modules/observe` with an empty body may also run
that bounded check. Joomla requires administrator permission and its form token.
The worker advances without any open dashboard. Cycles do not overlap; a failed
probe uses at most twice the configured cadence (capped at 300 seconds), records
a sanitized failure and does not stop unrelated probes. SQLite probes have a
250 ms instruction deadline and 100 ms lock timeout; no schema is initialized.

The existing owning PowerShell supervisor observes its own children every 15
seconds and atomically writes `state/runtime-observations.json` with a 45-second
TTL. HTTP/TCP checks are bounded and loopback-only. Python requires matching
installation, source, build, service and API PID, genuine success clocks and
valid UTC timestamps. Upstream expiry is preserved when the kernel reads the
receipt: rereading a 45-second proof never makes it valid for 300 seconds.
Anonymous Joomla bootstrap is explicitly limited evidence; it is not a login.

The kernel atomically caches same-build observations in
`state/kernel/module-observations.json`. Cache files and ancestors must be
ordinary, owned profile paths. Restart can restore historical last success and
metric sample clocks, never fresh READY. Missing, null, malformed, future, stale,
foreign-build or foreign-installation evidence cannot become current success.
Per-operation evidence cannot renew a previous metric sample. Expired evidence
is neutral unknown current readiness, not proof of a broken engine.

Class C work remains explicit: provider synchronization, forecast persistence,
exports, scoring and inference use their narrow authenticated operations and
existing durable queue. `POST /matches/{id}/forecasts` and `/evaluations` accept
empty typed bodies, preserve owner/idempotency keys and use the durable job ID as
run identity. `GET /matches/{id}/cognition-history` reads immutable history without
initializing the store. No client-supplied cutoff, run ID, arbitrary URL or shell
command is accepted. A no-outcome evaluation is a successful pending workflow,
not evidence of numerical performance.

Presentation uses a visible label/icon plus the exact state mapping: `READY`
is green; `DEGRADED` and `NOT_CONFIGURED` are amber; `UNAVAILABLE` and `STOPPED`
are red; `UNVERIFIED`, `EXPIRED`, `UNKNOWN`, `NOT_APPLICABLE` and
`NOT_IMPLEMENTED` are neutral. Unknown/default input is neutral. Neither an
unobserved operation nor an expired receipt is a newly ready engine. Colour,
navigation, rerender and a cache read never renew `observed_at`, `last_success_at`
or expiry. The legend states this distinction rather than grouping unverified
proof with degraded capability. No optional model dependency gates retained
browsing.

This neutral PHP mapping is a source-only dev.4 r2 presentation correction pending
the next freeze/build/deployment. The currently deployed Joomla dev.4 r1 package
is source 3cae; its Atum-width fix and backend dev.3 compatibility have separate
actual acceptance. Do not relabel that installed package as the new r2 source.
