# DRAGONHYDRA Joomla sports intelligence homepage

Verified 2026-11-01T12:07:36.925738+00:00. The original Joomla homepage is now the installed **com_dragonhydra**
site workspace. All **17 frontend acceptance requirements pass**. The administrator
component and Python server are reused. No iframe, external-workstation redirect,
second sports database, prediction engine or API service was introduced.

## Owner access

Homepage: http://127.0.0.1:18740/

Choose **Sign in to your workspace**, then use **dragonadmin** and the owner's
current Joomla password. The supplied password passed a genuine Joomla administrator
login, and the deployed workspace passed a separate genuine **Site** login. An
administrator session is not assumed to authenticate the frontend. Logout and a fresh
browser login work. Password changes use normal Joomla account management and need
no source edit or application rebuild.

Administration: http://127.0.0.1:18740/administrator/

Existing component: http://127.0.0.1:18740/administrator/index.php?option=com_dragonhydra

The value described as a token was identified by an in-memory configuration
comparison: it matches the workstation's stored generated **initial administrator
password** field. It is not one of the four known local-pairing tokens. It was not
used as a backend/provider/Joomla API credential or network-probed. The owner's
current supplied Joomla password authenticated successfully; the initial-password
metadata is not a replacement for that current login. The original narrower
pairing-only check is preserved alongside this later purpose correction.
Acceptance credentials remain owner-bound DPAPI data in the restricted local backup
area, or process memory. They are absent from source, packages and public receipts.
The application's runtime login uses Joomla itself and does not depend on that test file.

## Target and preserved baseline

- Original profile: `C:\xampp\DRAGONHYDRA\build\workstation\test-install`.
- Joomla site/state: `state data/site`, `state data`; loopback **18740**.
- Owning service: **DragonhydraWorkstationTest**, LocalService. Baseline PID12904.
- Correct associated backend: **http://127.0.0.1:18744/dragon/api/v1**. Workstation
  configuration, endpoint metadata and existing component parameters agree.
- Bridge: `state data/kernel/joomla-bridge.json`; secret stays server-side, PHP signs
  requests as the actual Joomla user with **reader** role for site data/exports.
- Joomla **6.2.0**, private PHP **8.4.27**, private MariaDB **18741** with
  `dragonhydra_admin`/`dh_`. Sports authority stays **SQLite**, `kernel/core.sqlite3`.
- Port18743/default,18747/provider-a2 and18750/A8 are separate profiles. Their data,
  credentials, ports, services and releases were not used as substitutes.
- Starting Git checkpoint: `1c983cfa0886b65ed2afb0892f259643b4a3ffc7`;
  package source: **55997de0a3997a10d12c6271795289a5d147e1ab**.

Before changes, the existing backup routine produced a private **736622-byte**
MariaDB SQL dump using `--single-transaction --skip-lock-tables`; persisted Joomla
InnoDB tables are transaction-consistent. Transient MEMORY search-token tables are
outside InnoDB snapshot semantics. No live storage files were copied as a database
backup. Configuration, original component and Cassiopeia/template assets were copied
under `build/joomla-frontend-20261101/private-backup`, restricted to the owner,
Administrators and SYSTEM. The protected bridge was not modified or copied.
Menu/module/style/extension records and representative sports IDs/counts were captured
in sanitized baseline receipts before deployment.

## Implementation and Joomla changes

The existing component now has Site MVC controllers, a presentation model and seven
server-rendered sections: **Overview, Matches, Teams, Competitions, Analysis, Reports,
Connections**. It reuses the administrator ApiClient/HMAC transport, adding only a
bounded, owner-checked export-download operation. Scoped WebAssetManager CSS and
native Joomla routes/forms provide responsive tables/cards, focus indicators, labels,
skip links and keyboard navigation. No privileged API client or credential is added
to JavaScript. A **Cassiopeia child template** supplies clean application chrome;
Joomla core/vendor and the Cassiopeia parent are unchanged.

The supported package installer creates/reuses **Home142**, alias
`dragonhydra-workspace`, language`*`, with template style**13** /
`cassiopeia_dragonhydra`. Original Home**101** remains published but is no longer
the default. Original **11 articles** and **48 modules** remain, including their
published states and content. Sample modules are excluded only from managed Home
assignments. Original module behavior elsewhere is preserved.

Reapplying the same package completed successfully. Home142/style13 and all site menu
settings, modules/assignments, styles, component bridge params, articles, owner identity
and groups are identical after the repeat. Menu count remains**55**. Joomla normally
regenerates its eight administrator menu row IDs on extension upgrade; their links,
parents and count are unchanged. That is not duplication of menus.

Protected data requires a non-guest Joomla Site identity, positive user ID and existing
`core.manage` permission. Export creation checks a Joomla POST CSRF token. Backend job
ownership is checked with reader identity before downloads. Guests see a branded
sign-in shell with no private counts/records. Provider synchronization, key editing
and administration remain in the existing protected administrator interface.

## Real data and actual operations

The observed totals are **760 retained matches**, **40 source-scoped teams** and
**two competitions**, fetched from this backend and compared with rendered totals;
these numbers are not hard-coded into the interface. Search, competition/status
filters, pagination, team form, competition standings and match source/receipt IDs
were exercised through actual Joomla pages.

Finished-match analysis correctly reports unavailable prospective forecasts. The
selected scheduled-match statistical forecast displayed **39.2% / 30.4% / 30.4%**,
matching the backend response; model identities, version/cutoff/supporting information
are shown when supplied. This is existing uncalibrated statistical analysis, not a
new prediction engine or a performance claim. Overview loads perform retained-data
reads only. Explicit Analysis navigation calls existing statistical calculation and
package reads; no provider sync, paid request, language-model job or model download
was triggered.

Actual frontend exports created exactly three authorized backend jobs, owned by
`joomla:476`, and downloaded valid files through Joomla:

| Format | Bytes | SHA-256 |
|---|---|---|
| JSON | 2566 | `b7c25b12b4f8984ab03dde32550e6e9176223fbd6fac5b0acc9f8c9ae1641272` |
| CSV | 379 | `6be9f875c60c49d28192ca77f8cc3265c1369cf216897fc0c251fb91014f57fe` |
| XLSX | 6159 | `bcde155a912358d2b12abb2b243deadd27ade930b10c637b740ddb1b58f5af7d` |

No new imports were performed. The full760record presentation/ID fingerprints,
provider settings and private configuration/pairing file hashes equal the pre-change
baseline; expected export-job/auth-session metadata changes are accounted for.

All ten provider registration/documentation links produce actual browser new tabs
with the correct configured HTTPS destination and preserve the workspace. The first
attempt timed out waiting for an external document. The final handoff test controlled
only external document responses to bound network/WAF delays; it proves browser URL
handoff and workspace preservation, **not remote provider website availability**.
Joomla/backend responses and exports were not mocked.

## Packages and repair inputs

Installable package: `C:\xampp\DRAGONHYDRA\dist\pkg_dragonhydra-0.4.1-dev.2.zip`

- **43686 bytes**; SHA-256
  **8b639f154d086af6616d04ddbec40ad280d772577a0e7fba176cb8958c502a49**.
- Component/package/child-template version **0.4.1-dev.2**; unsigned development package.
- Source55997de is embedded in build metadata. The child template installs before
  the component's idempotent Home/module setup. Package39nested file members match
  canonical source, with the expected injected build-info/manifest transformation.
- Built, installed/upgraded, executed and tested on this existing primary Joomla
  site. It is not a new clean Windows installation or OS-reboot result.

A separate verified web-payload refresh under
`build/joomla-frontend-20261101/web-payload` reuses all existing Apache/PHP/MariaDB/Joomla
runtime binaries. It changes only `extension.zip`, `manage.php`, `README.md` plus the
manifest/provenance metadata. All **9940 manifested entries** rehashed successfully.
Final web-manifest SHA-256:
`f54572ad63f2f6a7b8467a4fc96c8fad72d203357e57d958641fca517b884304`.

Fresh Windows build inputs now select this hash-verified package; the same Home setup
is called by workstation configuration/repair. The primary installation's cached web
inputs were also refreshed successfully with elevation: **15 guards passed**. Four
web inputs plus the two outer build/payload manifests were backed up and atomically
updated, ACLs preserved, and existing server/client bytes verified unchanged. All four
service PIDs/states/controllers remained unchanged. The official refreshed management
`install` action then returned exit0, retained the existing Joomla core and recorded
the new package hash. No service restart or credential rotation was performed. The
six-file backup is under `private-backup/installed-web-inputs-r1`; corresponding
installed-input and management-action receipts are preserved.

No Python server, Tauri client or whole Windows Setup EXE was rebuilt. Historical A6,
A7 and A8 artifacts/releases remain intact. A later complete Windows installer build
must identify and accept its new contents separately; this package does not claim a
fresh-workstation or clean-machine installer test.

## Acceptance and evidence

| ID | Requirement | Result |
|---|---|---|
| 01 | Root homepage uses DRAGONHYDRA, not sample blog | PASS |
| 02 | Home item and child-template assignments correct | PASS |
| 03 | Owner signs in normally to protected site workspace | PASS |
| 04 | Anonymous users cannot read private data or mutate exports | PASS |
| 05 | Totals/records equal the correct associated backend | PASS |
| 06 | Retained match source identity and timestamps verified | PASS |
| 07 | Search, filters, pagination and entity navigation work | PASS |
| 08 | Existing analysis and unavailable states are honest | PASS |
| 09 | JSON, CSV and XLSX exports are actual valid downloads | PASS |
| 10 | Provider links open correct new tabs and preserve workspace | PASS |
| 11 | Existing administrator login/component still work | PASS |
| 12 | Empty, errors and backend-unavailable states render in isolation | PASS |
| 13 | Desktop/narrow layouts and keyboard navigation are usable | PASS |
| 14 | No supplied credentials or private keys in browser/public artifacts | PASS |
| 15 | Retained data/provider settings/pairing/other profiles preserved | PASS |
| 16 | Reload, logout and fresh login preserve expected access | PASS |
| 17 | Redeployment creates no duplicate presentation or data records | PASS |

The [structured matrix](docs/handover/verified-reports/JOOMLA-FRONTEND-ACCEPTANCE-MATRIX.json)
records actions, timestamps, exit codes, observations and receipt paths. Browser r1
preserves**17 successful checks** and its raw failed overall timeout status. The
hash-linked r2 continuation passes**13 further checks**; it does not relabel r1 or
recreate the three export jobs. Empty/offline/missing-record/no-analysis/anonymous/
permission-denied templates passed **seven isolated browser checks** without
stopping production services. **36 focused tests** pass, covering package/HMAC/ACL,
PHP model/templates, export transport, setup/idempotence/by-reference, payload reuse
and tamper rejection, PowerShell provenance gates. These are scoped overlapping
checks, not a combined claim of independent test totals.

Screenshots: [desktop](docs/handover/verified-reports/JOOMLA-FRONTEND-DESKTOP.png),
[mobile](docs/handover/verified-reports/JOOMLA-FRONTEND-MOBILE.png),
[retained match](docs/handover/verified-reports/JOOMLA-FRONTEND-MATCH.png),
[anonymous homepage](docs/handover/verified-reports/JOOMLA-FRONTEND-ANONYMOUS.png).
Credential-entry forms, trace/HAR, browser cookies and private runtime files are not
published. The final privacy scan compared all six distinct supplied/local secret values,
including the value identified as the initial-password field, in raw/JSON-escaped/
URL-encoded/base64 forms. It found **zero matches** across seven authenticated pages,
three local script resources, local/session storage, 66 source/report files and
40 archive members including nested package contents. Needles were compared only in
Python memory and were not inserted into browser JavaScript. An initial scanner
launch from the Node orchestration environment failed before any page was scanned;
the normal existing Python execution path passed. The failed diagnostic is retained.

## Repairs, rollback and limits

The first deployed setup hook failed on Joomla's by-reference `insertObject` contract.
The two-line object-variable repair and a real by-reference regression resolved it;
corrected package installs/reapplies with exit0. A template regression also corrected
healthy-backend labeling for a missing record. A metadata review caught and corrected
a stale inherited provisioning-hook digest before payload publication. Earlier helper
schema/ID comparisons and external-document timeouts remain separate diagnostics.

Rollback instructions were recorded **before deployment** in
`build/joomla-frontend-20261101/evidence/deployment-plan.json`. Preserve newer owner
changes first, stop only the owning service for a coordinated restore, restore the
matching private SQL/config/component/template snapshot, quarantine only this task's
new site/child-template files after path checks, and restore original Home101 and its
module/style assignments. Restart only that controller and recheck login/root/data.
A restore drill was not performed. Do not restore into the default/A8/provider-a2
profiles, replace SQLite with MariaDB, or weaken bridge credential ACLs.

Remaining limits: no formal WCAG/screen-reader audit (child-template/component main
landmark consolidation is a semantic follow-up), no clean-machine/OS reboot/restore
drill, no claim that remote provider websites are available, and no use of the supplied initial-password value as a service credential. Owner credential rotation uses normal Joomla settings;
no app rebuild is required.

Current result: **17/17 frontend requirements PASS; installed repair-input maintenance
also VERIFIED**. The homepage is ready for normal owner use. The later preservation
checkpoint is the Git commit containing this report; the package's exact embedded
source remains55997de. No GitHub release upload is claimed.

Final preservation observation: after the exact repeat-install check, Home142's
parameter JSON later contained Joomla native menu-form fields and no unused internal
marker. Its Home/link/style/visibility/title/class are still correct; other site menu
fields, original articles/modules, owner identity/groups, bridge parameters, all760
sports records and all four services remain intact. The exact writer was not
established, so no corrective overwrite was made. See the final preservation receipt.

## Completed Home-menu assertion review

The failing `site_menus_same` check was investigated field by field. Only Home142's
parameter serialization differed: ten native menu-form fields were added at their
exact default values, and the unused undeclared `dragonhydra_workspace_home=1`
marker was omitted. The retained title, CSS class and heading flag are identical.
All unrelated original site menu rows/parameter hashes, all article fingerprints,
Home142/link/style13 and the55record count match. The exact writer was not observed;
no broad data-corruption or reinstall conclusion follows from this byte-hash change.

A narrow semantic comparator now fills only those ten known defaults and ignores
only that validated unused marker. It preserves every other key/value and still
rejects title/visibility changes, an unrelated menu edit, an added/duplicate menu,
unknown changed parameters or unexpected marker values. **Seven new regressions
pass**, and comparison against the actual database snapshots passes. The earlier
immediate package-repeat test also passes exactly. Evidence:
`docs/handover/verified-reports/JOOMLA-FRONTEND-MENU-SEMANTICS.json`.
