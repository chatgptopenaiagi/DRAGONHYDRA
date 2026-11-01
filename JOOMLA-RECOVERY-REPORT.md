# DRAGONHYDRA Joomla administration and integration recovery

Verified 2026-11-01T11:05:12.651945+00:00. Result: **18/18 acceptance requirements PASS**. This is access
case **A**: valid credentials and the existing owner-access workflow were available.
No Joomla authentication, component-registration or bridge product defect was found.
The account was not reset, an extra Super User was not created, and no reinstall was
performed. The original installation was tested directly, including a scoped restart.

## Owner access — ready to use

- Administrator: http://127.0.0.1:18740/administrator/
- Component: http://127.0.0.1:18740/administrator/index.php?option=com_dragonhydra
- Account: **dragonadmin**, existing user ID **476**, Super Users, unblocked.
- Open Start menu **DRAGONHYDRA Workstation - DragonhydraWorkstationTest →
  DRAGONHYDRA Administration**. Its existing native launcher is already open as
  **DRAGONHYDRA Administration** (observed PID36008, responsive). The password is
  masked by default. The owner can select **Show initial password** locally, then
  **Open Joomla**, and sign in with the displayed existing credential.
- This protected handoff was compared in memory with the credential verified by
  Joomla and used successfully in genuine HTTP and Edge logins. No password is
  included here, in command arguments, logs or Git. No reset was necessary.
- After login, use **Components → DRAGONHYDRA → Data sources**, or the direct
  component URL. The owner can change the password through Joomla's normal account
  editor; the initial-password handoff describes the original credential and should
  not be mistaken for a password vault that tracks later account changes.

Open the verified administrator URL from PowerShell 7:

```powershell
Start-Process 'http://127.0.0.1:18740/administrator/'
```

Reopen the correct protected credential window with the existing launcher:

```powershell
& 'C:\xampp\DRAGONHYDRA\build\workstation\test-install\application files\workstation\DragonhydraLauncher.exe' --state 'C:\xampp\DRAGONHYDRA\build\workstation\test-install\state data' --administration
```

Do not choose the similarly named A8, provider-a2 or default-profile Administration
shortcut. Their databases, credentials, document roots and ports are separate.

## Compact installation map

| Item | Verified binding |
|---|---|
| Identity | Original `build/workstation/test-install` profile |
| Service/account | `DragonhydraWorkstationTest` / `NT AUTHORITY\LocalService` |
| Service PID | 22876 before acceptance restart; **12904** afterward |
| Apache listener | 127.0.0.1:18740; current PID **40396**, parent **40308** |
| Apache EXE | `application files/web/apache/bin/httpd.exe`, Apache2.4.65 |
| Active configuration | `state data/web-config/httpd.conf` (explicit `-f` in running process) |
| Document root | `state data/site` |
| Joomla | **6.2.0** |
| PHP EXE | `application files/web/php/php.exe`, CLI **8.4.27** |
| Web PHP | Authenticated Joomla System Information: **8.4.27 / apache2handler** |
| Effective PHP configuration | `state data/web-config/php.ini`; Apache `PHPIniDir` selects this directory |
| MariaDB | 127.0.0.1:**18741**, version10.11.16, PID **40260**, parent **40308** |
| Joomla DB/prefix | `dragonhydra_admin` / `dh_` |
| Sports authority | **SQLite**, `state data/kernel/core.sqlite3` |
| Reserved MariaDB schema | `dragonhydra_core`, empty; not the sports authority |
| Associated API | **http://127.0.0.1:18744/dragon/api/v1**, PID **24532**, parent **40308** |
| API state | `state data/kernel` |
| Bridge | `state data/kernel/joomla-bridge.json`, existing LocalService-protected HMAC secret |

Paths in the table are relative to
`C:\xampp\DRAGONHYDRA\build\workstation\test-install`.
The [structured map](docs/handover/verified-reports/JOOMLA-RECOVERY-INSTALLATION-MAP.json)
contains full process, parent, supervisor, executable and configuration paths.
Workstation configuration, launcher shortcut state, client endpoint metadata,
Joomla extension parameters and Apache proxy all agree on **18744**. Port18743
belongs to `C:\ProgramData\DRAGONHYDRA` / `DragonhydraWorkstation`; its authenticated
health was checked separately, and Joomla was not repointed to it.

## Findings and root causes

1. Anonymous HTTP200 and the administrator page title proved only that the login
   page was reached. Joomla intentionally renders login for an unauthenticated
   component request. Missing component text was normal access control.
2. Existing `dragonadmin` credentials work. The provisioning script writes the
   protected `first-run.json`; the native Administration shortcut already presents
   that handoff locally. The missing practical step was using the correct profile's
   owner-access workflow, not repairing a broken account.
3. Medium-token CIM inspection returned empty process executable/command lines.
   Elevated scoped inspection populated the same processes and proved their
   LocalService ownership, supervisor and explicit configuration. These inspection
   permissions did not indicate an Apache malfunction. No security ACL was weakened.
4. Apache's exact executable returned **exit0 / Syntax OK** for the active
   configuration. Logs contain normal historical notices/warnings, no fatal/error
   word matches; the PHP error log was absent. Current authenticated/browser
   behavior, rather than historical word counts, establishes runtime success.
5. Component252 is enabled, administrator client1, version0.4.0-alpha.1, with the
   expected namespace, service provider, ACL asset and eight menu entries. The
   frontend/API directories are intentionally empty: this version is administrator
   only. Component SQL files define no sports tables; the kernel owns those records.
6. Joomla and Python already use a working HMAC bridge. Joomla login, local desktop
   pairing, bridge signatures and external provider keys are separate mechanisms.
   The bridge was not rewritten, copied over another profile or replaced with a
   pairing/provider token.

## Preservation, changes and rollback

Source revision before recovery: `d0f517e49968b587bef83a043d6783447000ad74`, branch
`continuity/genesis-20261031-a6`. Independent files were left outside task commits.

Private backup: `C:\xampp\DRAGONHYDRA\build\joomla-recovery-20261101\private-backup`.
Its ACL is restricted to the workstation owner, SYSTEM and Administrators. It holds:

- `joomla-and-core.sql`, **375368 bytes**: actual private MariaDB `mysqldump`
  `--single-transaction --skip-lock-tables --hex-blob --databases` backup, exit0.
  Persistent Joomla tables use InnoDB; the two MEMORY search-token work tables
  are transient and are outside InnoDB snapshot semantics.
- Copies of the active site/workstation/first-run/Apache/PHP/MariaDB configuration
  and the administrator component tree; secret values are excluded from public
  manifests. The dump-client credential file was removed after use.
- Private acceptance cookies and one raw diagnostic HTML response. These are
  access-restricted and are not included in public evidence or source control.

The protected bridge content could not be read even by the scoped administrative
copy attempt. That attempt stopped before any service operation; its failed receipt
is preserved locally. No bridge content change was planned, so subsequent acceptance
left its ACL and contents alone. File size/timestamp remained unchanged, and signed
Joomla requests worked after restart. **A backup of this protected secret is not
claimed.**

Product source/configuration/database repairs: **none**. The only installation
operation was an authorized Stop/Start of **DragonhydraWorkstationTest** through
its owning Windows service controller. Normal Joomla login/logout creates/removes
session records and updates login metadata; this is not a database repair. No
password/group/plugin/menu/extension/schema/provider mutation was requested.

Added task-owned reusable helpers/tests:

- `tests/installation/joomla_recovery.py`: guarded backup, real form/cookie login,
  inventory/configuration checks and existing-session restart replay.
- `tests/installation/joomla_recovery_audit.php`: scoped read-only JConfig/PDO and
  native Joomla password verification with userId0 (no rehash write).
- `tests/installation/joomla_recovery_browser.py`: actual Edge menu, component,
  logout, close/reopen and fresh-login acceptance.
- `tests/installation/joomla_recovery_service.ps1`: explicit `-Apply`, fixed-profile
  inspection/restart and protection of unrelated services; refuses receipt overwrite.
- `tests/test_joomla_recovery.py`: five focused diagnostic regressions.

No repair rollback is required. If a future authorized repair needs these snapshots,
first stop **only** DragonhydraWorkstationTest, restore only the matching backed-up
configuration/component files, and use the matching private MariaDB client and a
protected defaults file to restore the consistent SQL dump only when needed. Resume
that service and rerun authenticated acceptance. Do not restore this dump into A8,
provider-a2 or the default profile, replace SQLite with the reserved MariaDB schema,
or relax bridge ACLs. No restore was executed or claimed tested in this recovery.

## Authenticated backend evidence

Joomla's actual match page and its rendered **Technical details and evidence** JSON
were compared with the associated authenticated backend response. **Every field
matched**, including:

- Fixture: **Liverpool FC — AFC Bournemouth**, English Premier League2026/27.
- Event date/status: **2027-05-30 / scheduled**, no score supplied; no completed-result
  or prediction claim is made.
- Canonical ID: `de2c0fb3d3215eb157292f0941def2d44aa520a79db77dc73e40d13f88014aea`.
- Source: `openfootball-2026-27-en1.json`.
- Evidence/version: `f5cea7eb01404a18ebeceebc36e0bf961635abbbbd606e57640eb5e09a3a5492`.

All **760** retained match presentations/identifiers, provider response fingerprint,
and six configuration/pairing file hashes equal the pre-authentication baseline,
including after service restart. Ten providers render their existing actual states;
this original profile has760OpenFootball records and no claimed acquisitions for
unconfigured/unimplemented providers. No paid/provider fetch, import or model run
was performed. See [match correlation](docs/handover/verified-reports/JOOMLA-RECOVERY-MATCH-CORRELATION.json),
[Sources screenshot](docs/handover/verified-reports/JOOMLA-RECOVERY-SOURCES.png), and
[match screenshot](docs/handover/verified-reports/JOOMLA-RECOVERY-MATCH.png).

## Acceptance matrix

Each requirement below is PASS. The [structured matrix](docs/handover/verified-reports/JOOMLA-RECOVERY-ACCEPTANCE-MATRIX.json)
records the expected/observed behavior, exact action, timestamp, exit code and
sanitized evidence path for each ID.

| ID | Expected behavior | Status | Observed behavior |
|---|---|---|---|
| 01 | Correct installation, document root and service ownership established | PASS | 18740 Apache is owned by original DragonhydraWorkstationTest/LocalService; explicit config and all18740/18741/18744 listener images match its install root |
| 02 | Joomla administrator login page loads | PASS | HTTP200 with current login form and nonempty PowerShell7 final URI |
| 03 | Intended owner-administrator account identified | PASS | Existing dragonadmin, id476, unblocked, Super Users; Joomla verifies existing credential with userId0 |
| 04 | Owner has a usable local login or recovery procedure | PASS | Existing primary-profile Administration launcher opens; generated initial credential matches account and stays masked locally; no reset |
| 05 | Genuine administrator authentication succeeds | PASS | Actual login-form CSRF, credentials and cookies succeed; authenticated component/menu/sysinfo prove identity permissions |
| 06 | Authenticated session survives subsequent navigation | PASS | Five actual browser navigations; earlier HTTP cookie also survives owning-service restart |
| 07 | com_dragonhydra registered and enabled | PASS | Extension252 client1 enabled, version0.4.0-alpha.1, namespace valid; eight administrator menu entries |
| 08 | Actual administrator interface renders | PASS | Sources, Matches, Odds, Models, Research, Databases and System render; actual browser has zero JS errors |
| 09 | Intended administrator menu entry opens component | PASS | Normal Components > DRAGONHYDRA > Data sources click sequence succeeds, twice |
| 10 | Joomla database connectivity works | PASS | Private MariaDB10.11.16 at18741; correct datadir, dragonhydra_admin, prefixdh_; real sessions and pages work |
| 11 | Correct associated backend responds | PASS | All supervisor/endpoint/component/proxy bindings agree on18744; authenticated ready response.18743 separately ready using its own profile |
| 12 | Joomla displays a real retained backend record | PASS | Liverpool FC-AFC Bournemouth canonical id, source/evidence and ALL rendered technical fields equal associated backend JSON |
| 13 | Applicable component API routes pass authenticated checks | PASS | Existing PHP HMAC transport reads connections/matches/system; unsigned data401 and CSRF-free action403. No separate Joomla webservices routes are implemented |
| 14 | Logout and anonymous protections work | PASS | Actual User Menu CSRF logout; component then shows login; fresh anonymous context denied |
| 15 | Existing provider settings, pairing and retained data preserved | PASS | All760 full record presentations/IDs, provider response fingerprint and six configuration/pairing file hashes unchanged |
| 16 | Focused regression tests pass | PASS | Five diagnostic regression tests pass; noscript/login false positives and cross-profile login action rejected |
| 17 | Application close/reopen and fresh login succeed | PASS | Edge closed, new Edge process/context without imported storage requires login, then login/menu/provider table succeed |
| 18 | Required service restart persistence tested | PASS | Only owning DragonhydraWorkstationTest restarted; ready again, old Joomla session and760records intact; other three service PIDs unchanged |

Executed groups: final HTTP **19**, pre-restart-cookie post-service replay **17**,
actual Edge browser **17**, scoped service/inspection **9**, unit regressions **5**.
These overlap in scope and are not advertised as independent product-test totals.
The browser used genuine form submission, normal administrator menu clicks and
CSRF-protected logout; it closed/reopened a fresh process/context and logged in again.
Joomla session storage is database-backed, cookie domain/path are empty defaults,
HttpOnly/SameSite=Lax and strict PHP sessions remain configured. Existing enabled
Joomla authentication/user plugins and Super User permissions were preserved.

This component's implemented API path is its PHP HMAC client reading Python
`/connections`, `/matches`, `/matches/<id>` and `/system`. It has no Joomla
webservices plugin/REST controllers to invent or test as if implemented. Existing
mutation actions reject missing Joomla CSRF tokens with403, and unsigned backend
data requests return401. Successful protected reads, denied writes and logout prove
applicable routing and access boundaries without triggering imports.

The other services retain their original running PIDs: default39364,
provider-a2 23500 and A8 17012. The target is Running12904 after its single actual
restart. Their releases, data and artifacts were not modified. No installer rebuild,
software installation, Codex version change, OS reboot or unrelated project action
was needed.

## Diagnostic failures and remaining limits

Preserved failed receipts are helper diagnostics, not established application faults:
HTTP r1 treated a normal noscript alert as a component error; HTTP r2 omitted the
separate18743 profile's required authentication; the first elevated helper tried an
unnecessary protected-secret backup and stopped before restart. Browser r2/r3 needed
more precise System Information/logout locators. Corrected final receipts pass; no
raw credential-bearing error strings were published. The five regressions protect
against login-page/noscript false positives and cross-profile form submission.

PowerShell7 final-response URI is available through
`$response.BaseResponse.RequestMessage.RequestUri`; the recorded value is the correct
administrator URL. An empty legacy `ResponseUri` property is not a routing defect.

The installed Joomla CLI help confirms `user:list` and `user:reset-password` using
this site's matching PHP runtime. No user operation/reset was invoked. Future reset
work must retain user476 and use Joomla's supported flow; the installed Windows
hidden-input helper was absent, so a blind CLI password prompt is not claimed usable.
[Joomla's CLI guide](https://guide.joomla.org/user-guide/command-line-interface/command-line-interface-using-the-cli)
documents the command family; the installed source/help and current authenticated
behavior are the acceptance authority here.

No recovery success criterion remains blocked. A future owner-selected password
change is an interactive account-management choice. OS reboot/clean-machine
acceptance, database restore drills, provider activation and model runs were outside
this scoped recovery and are not claimed. The owner-access window remains open;
use its existing masked handoff and **Open Joomla** control to sign in normally.
