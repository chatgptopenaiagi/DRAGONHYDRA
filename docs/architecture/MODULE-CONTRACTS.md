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
`runtime_state` starts `UNVERIFIED` and derives only from an actual scoped
last-operation record, its own expiry, or explicit shutdown. None of these
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
| UNVERIFIED | Implementation/configuration exists but relevant execution has not been observed. |
| READY | The explicitly described bounded observation or operation succeeded. |
| DEGRADED | Partial data, failed observation or required dependency limits operation. |
| UNAVAILABLE | The requested feature/data/cohort is currently unavailable. |
| NOT_APPLICABLE | An adapter explicitly establishes the capability does not apply. |
| EXPIRED | Previous evidence has reached its expiry; status does not silently refresh it. |
| STOPPED | Explicit kernel shutdown completed for this engine. |

Startup performs bounded local read-only SQLite counts and redacted configuration
availability checks in required dependency order. It starts no provider, model,
installer or additional worker. Explicit operations update their scoped cached
observations. A deterministic AI package/fallback never establishes model readiness.
Empty evaluation cohorts do not establish evaluation readiness. SQLite counts
include retained revisions and are labelled accordingly.

Authenticated `GET /dragon/api/v1/modules` returns
`{schema_version, installation, items}`. `GET /modules/{id}` returns the same
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
