# System Control Center engineering report

Recorded 2026-11-01. **IMPLEMENTED / BUILT / isolated EXECUTED and TESTED;
primary NOT DEPLOYED; not published.** This is a partial milestone. Windows UAC
was canceled before the guarded upgrade helper launched. No installer process,
service restart or primary runtime replacement occurred. Authenticated execution
of the new installed Control Center remains blocked.

The earlier A9 release remains available at
https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/tag/genesis-a9-20261101.
It does not contain this new increment. Its tag/assets were not changed.

## Target, baseline and ownership

| Item | Established association |
|---|---|
| Primary service | `DragonhydraWorkstationTest`, `NT AUTHORITY\LocalService`, service PID 12904 |
| Installation | `build/workstation/test-install/application files` |
| Application state | `build/workstation/test-install/state data` |
| Joomla | `http://127.0.0.1:18740/`; site is `state data/site` |
| Administrator | `http://127.0.0.1:18740/administrator/` |
| Associated backend | `http://127.0.0.1:18744`, selected by workstation configuration and signed server-side bridge |
| Storage | Authoritative sports evidence/jobs/cognition in `state data/kernel/core.sqlite3`; Joomla users/content/configuration in MariaDB on 18741, `dragonhydra_admin`, prefix `dh_` |
| Existing owner | `dragonadmin`, Joomla user 476; existing private DPAPI credential mechanism, no password reset |
| Baseline | 760 retained records; 55 menu records, 11 articles, 48 modules |
| Other installations | Default API18743/PID39364; provider API18746/Joomla18747/PID23500; A8 API18749/Joomla18750/PID29480 |

Fresh read-only verification after the canceled upgrade passed four groups at
15:13 UTC. All 760 match ID/version pairs, pairing file, Joomla configuration and
assigned ports equal the earlier baseline. All four services retain their PIDs.
Existing administrator credentials were genuinely authenticated before upgrade;
that verifies the existing administration, not the new Control Center.

The current primary desktop is the older A5 executable, SHA-256
`17b557c7a4f2524ace5769c3bace55583ce695a0f250771a3585ce954688f94b`.
The staged installer contains the previously verified F4 repaired client. Its
presence in this candidate is not a claim that the primary already received it.

## Source, contracts and implemented changes

Backend source checkpoint: `8216126971be7aedeebe9213a5d42a00a244305f`.
All 70 frozen-server inputs match that Git snapshot. Its scoped content identity
is `fa51ebc8963b2dcdfb12a5eee13f3a41fc2b9147d11a8bdf3a78de21bf6c64bb`.
Joomla package source: `4ad188f0f36b0cca13e574084a1ddd0a32cbcecb`.
Later packaging guard, acceptance helpers and documentation do not change those
runtime inputs. Resolve the final preservation commit from Git; do not substitute
its hash for the binaries' recorded source identities.

- `src/dragonhydra/module_registry.py`: 18 typed definitions, validated dependency
  graph, operation/capability allowlists and separate fresh observations. It reads
  bounded SQLite queries and a schema-validated, installation/API-PID-bound
  supervisor receipt. It never starts work, creates a store or probes a provider.
- `api.py`, `system_workflow.py`, `jobs.py`, `cognition/memory.py`: authenticated
  module/history reads and two explicit durable forecast/evaluation commands,
  reusing existing models, memory, evaluation and job ownership/idempotency.
- `packaging/windows/workstation/Workstation.ps1`: passive owned-process checks,
  schema 2 receipt, 30-second evidence lifetime, 15-second refresh, bounded
  loopback requests and sanitized owning-service identity. No broad shell API.
- Existing Joomla administration: protected System Control Center, group/status
  navigation, module details/dependencies/evidence, safe build identity, selected
  match history and explicit CSRF-protected command forms. `core.manage` permits
  viewing; existing action permission is separately required for commands.
- `scripts/Build-Workstation.ps1` and `KernelBuild.ps1`: verified kernel selection
  now works for fresh and repackage staging. Joomla dev.3 rejects a legacy kernel
  without its matching passing frozen-registry proof. Repackage staging and
  inherited proof are revalidated. No service operation belongs to this guard.

Confirmed defects repaired during source acceptance: missing last-success clocks
could be promoted to ready; incomplete cognition triggers could appear healthy;
an unreadable store could appear to have zero schedules/history. Negative tests
now fail closed. Required failure affects its own capability; optional AI being
unavailable does not block retained browsing. R1–R3 artifacts/evidence remain
preserved and were never deployed.

Definitions and observations are different objects. `ready` means that module's
declared conditions have fresh supporting evidence, not production certification.
Unconfigured, configured-unverified, degraded, unavailable, not implemented and
not applicable have explicit contract meanings. Expired external evidence cannot
be shown as newly successful. See `docs/architecture/MODULE-CONTRACTS.md`.

## Component matrix

Status below states the demonstrated scope; it does not convert expired test
observations into current primary readiness. Full input/output, data and
configuration ownership is in `docs/architecture/MODULE-MAP.md`.

| Module | Responsibility | Canonical source | Runtime/artifact | Dependencies | Implemented capabilities | Status/evidence |
|---|---|---|---|---|---|---|
| Web server | Joomla HTTP/PHP | `packaging/windows/workstation/Workstation.ps1`, `web/manage.php` | Owned Apache/PHP/site18740 | Supervisor, configuration | Loopback website serving | Existing primary responds; new observer functions tested in PS7 and PS5.1 |
| Administration | Identity, ACL, component settings | `server/joomla/com_dragonhydra/admin` | Joomla administrator/MariaDB | Apache, MariaDB, signed bridge | Existing administration and new Control Center | Existing login PASS; new installed UI BLOCKED |
| Website | Retained sports navigation | `server/joomla/com_dragonhydra/site`, child template/media | Joomla root18740 | Joomla sessions, bridge/API | Matches/entities/analysis/exports | Earlier frontend acceptance retained; new package not deployed |
| API server | Authentication and shared contracts | `src/dragonhydra/api.py`, `server.py` | R4 frozen server | Product, jobs, SQLite | Pairing, signed Joomla requests, typed routes | Isolated frozen startup/auth/API PASS |
| Data engine | Evidence retention/normalization | `public_results.py`, `connectors/` | Same Python core/SQLite | Existing adapters/evidence | Source-scoped records, receipt clocks, imports | Real retained 760-record isolated import PASS; no live-provider request |
| Odds engine | Market arithmetic and compatibility | `market_signals.py`, `market_store.py` | Same Python core | Compatible retained quotes | Conversion, margin, proportional normalization | Known-answer/invalid-scope tests PASS; real workflow had no compatible odds branch |
| Prediction engine | Explicit statistical forecasts | `cognition/models.py`, `adaptation.py` | Same Python core | Eligible evidence/cutoff/model inputs | Frequency, Poisson, Elo, recency, ensemble | Real prospective retained target: five persisted forecasts PASS; uncalibrated research outputs |
| Optional AI | Grounded explanations | `local_ai*.py` | Existing optional adapter/runtime | Explicit model configuration | Bounded source-fact explanations/fallback | Not configured in workflow; no inference performed |
| Memory engine | Immutable research lineage | `cognition/memory.py`, `system_workflow.py` | Same core SQLite | Valid schema/evidence | Models/predictions/receipts/history | Five model and five prediction records survive isolated restart; PASS |
| Evaluation engine | Forecast/outcome scoring | `cognition/evaluation.py` | Same core SQLite | Earlier forecast and correctly scoped later outcome | Brier/log loss, exclusions, chronological diagnostics | Controlled later-outcome tests PASS; real target pending, zero operational evaluations |
| Desktop | Native access/default browser | `client/desktop`, `DragonhydraLauncher.cs` | F4 client in candidate | WebView2, owning endpoint/pairing | Existing opener and official launcher | Source regressions PASS; prior A8 native evidence only; primary new native acceptance NOT_RUN |
| Android | Explicit paired mobile access | `android/dragonhydra_mobile` | Existing Flutter APK | Configured shared API | Mobile retained views/pairing workflow | Earlier build/install evidence only; new device acceptance NOT_RUN |
| SQLite storage | Sports authority | `product.py`, `market_store.py`, `connectors/store.py` | Selected `core.sqlite3` | Local filesystem | Evidence/jobs/cognition persistence | Isolated integrity/read/restart PASS; primary online backup PASS |
| MariaDB storage | Joomla identity/content authority | Workstation `web/manage.php` | Private MariaDB18741 | Owning supervisor/configuration | Joomla schema transport | Existing Joomla auth/connectivity PASS; no new database or transfer of sports authority |
| Evidence store | Source bytes and acquisition history | `public_results.py`, `connectors/store.py`, `source_context.py` | Existing SQLite domains | Valid source receipts | Immutable raw hashes/observations/context | Existing focused tests and real retained forecast lineage PASS |
| Jobs | Durable bounded work | `jobs.py` | Existing Python worker/SQLite | Product state | Owner-bound jobs, leases, exports, idempotency | Forecast/replay/pending-evaluation/restart PASS |
| Scheduler | Explicit configured due imports | `connectors/service.py`, `Jobs.run_once` | Existing worker | Provider settings/vault/jobs | Due schedule dispatch | Source tests; status reads create no jobs; live schedule execution NOT_RUN |
| Supervisor | Own configured child lifecycle | `DragonhydraService.cs`, `Workstation.ps1` | Existing single owning Windows service | Fixed profile/configuration | Owned lifecycle and expiring passive health | Actual PS7/PS5.1 observer tests PASS; new primary supervisor NOT_DEPLOYED |

## Routes and Control Center

Authenticated API additions, under the existing `/dragon/api/v1` namespace:

```text
GET  /system/modules
GET  /matches/{match_id}/cognition-history
POST /matches/{match_id}/forecasts
POST /matches/{match_id}/evaluations
```

GETs are bounded and passive. POSTs require administrator role and the existing
durable job contract; Joomla additionally validates its own form token and ACL.
No arbitrary proxy, shell command or Windows administrator privilege is exposed.
Privileged pairing/bridge/provider credentials remain server-side; ordinary
Joomla CSRF form fields and existing login submission remain supported.

**Intended URL, not yet installed/verified:**
`http://127.0.0.1:18740/administrator/index.php?option=com_dragonhydra&section=control`

There are group/status filters, module detail panels and selected-match workflow
history. Opening/refreshing the page does not submit model/provider work. No new
Control Center screenshot exists: the canceled upgrade prevented genuine new UI
acceptance. Existing Joomla administration remains available at its verified URL.

## Real retained workflow

R4 isolated frozen-server test explicitly retained the existing 760 source-backed
records in fresh private state. It selected Nottingham Forest FC–Manchester City
FC, 2026-11-07, source `openfootball-2026-27-en1.json`:

```text
match: 07cd1d80a5a57f42dab48dd2624fec83362d3ebac48e17e7ad05a2b4b5f9d277
import job: 4106cbeb8596441da8298c7c38406990
prediction example: prediction:3566c83c3ecb27fa702c9a974cb46f17968443d4151504dd1cfaf0032dee8058
```

Fifty eligible pre-cutoff records produced five model and five prediction records.
All five prediction IDs are in the sanitized build receipt. History reads before
the first explicit forecast created no cognition schema/model job. Explicit
evaluation correctly returned `pending / LATER_RETAINED_OUTCOME_UNAVAILABLE`.
There is no real later result or retained evaluation score to display yet.
The unchanged state, records, pairing, forecast IDs and job replay identity
survived actual frozen process shutdown/restart; both shutdowns exited zero.

Controlled fictional clock fixtures separately exercise later outcomes and eight
persisted base-model metric records. They do not claim a real completed outcome,
historical forecast, live acquisition or calibrated performance. The ensemble's
existing operational metric-persistence limitation is documented in the contract.
Joomla rendering of this new persisted workflow remains BLOCKED by deployment.

## Acceptance matrix A–N

All entries are dated 2026-11-01. Source/backend gate exit codes were zero.
`BUILD` below refers to `verified-reports/SYSTEM-CONTROL-CENTER-BUILD.json`;
`UI` refers to `verified-reports/SYSTEM-CONTROL-CENTER-UI.json`.
These scopes remain separate; there is no aggregate claim of complete acceptance.

| ID | Status | Observed behavior and supporting evidence |
|---|---|---|
| A | PASS | All named responsibilities mapped to actual source and honest runtime limits; MODULE-MAP and 18 definitions |
| B | PASS | Duplicate IDs/dependencies, cycles, config/operation/capability claims, stale/future/invalid producer evidence and partial schema rejected; registry tests |
| C | BLOCKED | Versions/scoped identities verified in source and frozen API; actual new primary identity awaits upgrade; BUILD |
| D | PASS | Passive registry/history tests detect store/job/model side effects; no quota/inference/service control; 19 registry/9 workflow tests and frozen gates |
| E | PASS | Missing/unreadable required stores fail relevant state; optional AI does not gate core browsing; registry negative tests |
| F | PASS | Existing odds known answers, invalid prices, incomplete/incompatible scope exercised in 124-test gate; MODULE-CONTRACTS |
| G | PASS | Forecast identity/cutoff retained; future evidence, scope and outcome leakage rejected in focused engine tests; BUILD |
| H | PASS | Immutable history and durable replay/partial runs tested; frozen restart retains IDs; BUILD |
| I | BLOCKED | New genuine Joomla Control Center navigation/data comparison not run because upgrade never launched; UI |
| J | BLOCKED | API authorization/read-only/secret canaries and Joomla ACL/CSRF source tests pass; actual installed new CSRF rejection/HTML/privacy checks await deployment; UI |
| K | BLOCKED | Existing auth, 760 records, pairing/configuration and all service PIDs preserved; primary repaired-client/native new acceptance awaits upgrade |
| L | BLOCKED | Real retained → forecast → persistence → restart succeeds in frozen server; later outcome honestly absent; required new Joomla display not yet executed |
| M | BLOCKED | Registry definitions unique; replay/repackage guards tested; actual repeated installed extension deployment/menu comparison not run |
| N | BLOCKED | Isolated frozen reopen/restart passes; new primary service restart/browser/native reopen not run. Unrelated installations unchanged |

Executed tests: 124 focused backend tests; frozen server six groups, connector
22 groups and new workflow nine groups; 29 packaging/browser-helper/supervisor
tests in the final combined command; five existing desktop source regressions.
Joomla source/PHP counts and scope are recorded separately in UI. These are
different suites; overlapping earlier runs are not summed as unique tests.

```powershell
$env:PYTHONPATH='src'
& .\runtime\server-env\Scripts\python.exe -B -m unittest tests.test_system_workflow tests.test_market_signals tests.test_cognition_models tests.test_cognition_memory tests.test_cognition_evaluation tests.test_cognition_commands tests.test_cognition_adaptation tests.test_product_api tests.test_module_registry
& .\runtime\server-env\Scripts\python.exe -B -m unittest tests.test_workstation_kernel_override tests.test_workstation_client_override tests.test_system_control_browser_harness tests.test_workstation_observations
```

## Packages and reproducibility

Final output directory: `dist/windows/SYSTEM-CONTROL-CENTER-20261101-r4`.
Versions describe actual internal metadata; filenames do not imply a new stable
or major version. Everything is an unsigned development candidate.

| File | Bytes | SHA-256 |
|---|---:|---|
| `DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe` | 64,858,273 | `b2af820fa834645b4db3dde90a60984dcac42414b0af76cb957df523013718b6` |
| `pkg_dragonhydra-0.4.1-dev.3.zip` | 59,919 | `d1c1fd8d35d281b20fc4ffef71fc18fd207b6608a90aa3df65bbe4cb7f671abc` |
| `DRAGONHYDRA-0.4.0-alpha.1-System-Control-Server-win-x64.zip` | 19,558,270 | `9c15e196489d29b1569c64ebb61d57d9df13edaa2c2e0959e80e04017d4dc50e` |

The server EXE inside both payloads is 8,071,343 bytes, SHA-256
`3231c279aab1a3d8b3cbfe6c396dded8ced60e4fb15a42c0a04eb7144e2990a4`.
The unchanged F4 client is 10,078,208 bytes, SHA-256
`f4e8fbae68c4fdc3f52c7f9baaeb98f375df26e34dced3dc87c7988d9a4c0617`.

Full NSIS extraction verified all 10,662 staged payload files. The standalone ZIP
passed CRC and all 710 payload sizes/hashes (713 members including documentation).
The known-private-value scan inspected 21 values, 10,674 files and 1,342 archive
members before deployment: zero matches. This is a scoped known-value scan,
not a claim to detect every possible secret. Private runtime state is excluded.

Build workflow: `scripts/build_connector_server.py --work <fresh-owned-kernel>`;
run `tests/installation/system_control_frozen.py --help` then its existing retained
data gate; build the component with `scripts/build_joomla.py`; clone the preserved
verified A9 staging into a new owned `build/connections` directory and repackage
using `Build-Workstation.ps1 -RepackageOnly -KernelBuildRoot <verified-kernel>
-JoomlaPackagePath <new-zip>`, with fresh output. The tested R4 wrapper's recorded
builder SHA is `65a0be9291e5e2c226aa63b0866e30fbaed58138e9b6432bd53c0a3e90c53c84`.
The subsequent validation-only KernelBuild guard is source-tested and not
retroactively claimed as the builder of these existing bytes.

Fresh builds can now select a verified new kernel, but still extract the legacy
A5 desktop unless using the established verified repackage/client override path.
The current R4 repackage contains F4. A fresh kernel selection alone is not proof
of repaired native external links. Clean-machine, OS reboot, signing and new
physical Android operation remain separate unverified gates.

## Backups, rollback and pending deployment

Private backup: `build/system-control-center-20261101/private-backup`, restricted
to owner/SYSTEM/Administrators. It contains consistent MariaDB logical SQL and
SQLite online backups (`integrity_check=ok`), affected deployed component/template
directories, original server/client/workstation inputs and baseline metadata.
The immediate R4 SQL backup is 750,039 bytes; SQLite is 1,069,056 bytes. Earlier
versions remain preserved. Ordinary Joomla session writes explain SQL-size
changes; no sports record mutation is implied. Protected bridge content could
not be copied with the current token; its file/ACL/configuration were unchanged.

No repair/deployment changed primary configuration or database records. On a
future explicit forecast, the existing cognition tables/triggers are initialized
in the same SQLite store; normal server schema setup may add existing connector
and job columns. Record actual schema differences after deployment. The component
adds one owned administration Control Center menu entry using idempotent setup;
verify the expected 55→56 menu change and unchanged articles/home assignments.

Rollback, only if a future upgrade needs it: use the actual owning controller to
stop **only** `DragonhydraWorkstationTest`; restore its matched original runtime,
client, supervisor and scoped web files; restore the matching logical Joomla and
online SQLite backups if undoing runtime/schema writes; restart only that service
and recheck IDs/configuration/ports. Do not restore another profile, overwrite
concurrent imports without review or copy live database directories. No rollback
was needed or applied during this attempt.

The exact canceled operation was the elevated PowerShell launch of
`tests/installation/system_control_install.ps1 -Phase Upgrade -Apply` with the
R4 installer hash above. Windows returned “The operation was canceled by the
user.” No elevated helper/installer PID or upgrade receipt was created. Do not
infer success from the outer shell exit code. No privilege workaround was used.

Next: after owner-approved Windows elevation is available, take a fresh consistent
baseline as needed, run the fixed-primary guarded upgrade once, then run
`tests/installation/system_control_browser.py --apply-workflow --output <fresh
build/system-control-center-20261101/evidence/browser-directory>`. Verify the
genuine Control Center, model/history display, CSRF/ACL, logout/fresh login,
repeated supported component deployment and a scoped primary restart. Finally
use `system_control_native_preflight.py` followed by real native shortcut/default
browser acceptance. Do not retry a canceled elevation without owner readiness.

## Preservation

Task-owned source/tests/sanitized receipts are kept in the existing Git workflow.
Independent `PACKAGING-COORDINATION.md`, public-access reports, Linux helper work,
nested `source/` repository and unrelated untracked files remain outside staging.
Binary candidates remain local release-style assets, not normal Git blobs.
Final source push status is recorded in `SYSTEM-CONTROL-CENTER.md` and the existing
engineering state only after remote comparison. No new GitHub release was made.
