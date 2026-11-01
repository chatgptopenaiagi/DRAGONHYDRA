FRESH PACKAGING VERIFIED — 2026-11-01; primary still NOT DEPLOYED.
Fresh source93c1138 build now supports explicit verified F4 client selection.
Setup: dist/windows/SYSTEM-CONTROL-CENTER-20261101-fresh-r1/
DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe,64854364B,
SHA c217d0450595ed4c1a9548b5904ba71ce300077afa4250725f8f88c3a64c6460.
Full10662file inspection/13recordedGitwrapperinputs PASS; same tested backend,
client,Joomla and observer bytes. R4 untouched. Client/kernel/helper guards20+12+6
PASS; helper also rejects receipt junction escapes and preserves old temp evidence.
Fresh privacy21values/10676files/2227members zero; primaryread4groupsPASS,
760records/pairing/config/ports/all4PIDs unchanged. Native UAC was not retried.
Read existing SystemControlCenter handoff/report and FRESH-BUILD receipt.
NEXT: owner ready for Windows elevation → fresh guarded primary upgrade once →
new authenticated Control Center/workflow/idempotent deploy/scoped restart/native
acceptance. No new primary UI screenshots or publication claim.

# System Control Center — resumable partial checkpoint

2026-11-01: IMPLEMENTED, BUILT, isolated EXECUTED/TESTED. **Primary NOT DEPLOYED**.
Windows UAC was canceled before elevated helper launch. No installer process or
service mutation occurred; do not infer success from the outer shell's exit0.
Do not retry elevation or work around it until the owner is ready to approve.

Read [engineering report](SYSTEM-CONTROL-CENTER-REPORT.md),
[build receipt](verified-reports/SYSTEM-CONTROL-CENTER-BUILD.json),
[UI receipt](verified-reports/SYSTEM-CONTROL-CENTER-UI.json),
[artifact manifest](verified-reports/SYSTEM-CONTROL-CENTER-ARTIFACTS.json),
[module map](../architecture/MODULE-MAP.md) and
[contracts](../architecture/MODULE-CONTRACTS.md).

## Source and payload identity

- Branch `continuity/genesis-20261031-a6`; backend source
  `8216126971be7aedeebe9213a5d42a00a244305f`; all70 frozen inputs equal that Git tree.
- Backend content `fa51ebc8963b2dcdfb12a5eee13f3a41fc2b9147d11a8bdf3a78de21bf6c64bb`.
  R4EXE8071343B SHA3231c279aab1a3d8b3cbfe6c396dded8ced60e4fb15a42c0a04eb7144e2990a4.
- Joomla dev.3 source `4ad188f0f36b0cca13e574084a1ddd0a32cbcecb`,59919B,
  SHAd1c1fd8d35d281b20fc4ffef71fc18fd207b6608a90aa3df65bbe4cb7f671abc.
- Final output `dist/windows/SYSTEM-CONTROL-CENTER-20261101-r4` contains Setup,
  extension, standalone server ZIP, ARTIFACT-MANIFEST.json and SHA256SUMS.txt.
- Setup64858273B SHAb2af820fa834645b4db3dde90a60984dcac42414b0af76cb957df523013718b6.
  Standalone19558270B SHA9c15e196489d29b1569c64ebb61d57d9df13edaa2c2e0959e80e04017d4dc50e.
- Existing actual versions retained: workstation0.4.1-dev.1, server0.4.0-alpha.1,
  Joomla0.4.1-dev.3. Unsigned development candidates, not a stable release.
- R1–R3 superseded candidates preserved, never deployed. A9 release/tag/assets
  unchanged; A9 does not include this new implementation. No new binary upload.
- Follow-up packaging proof guard/helpers/docs are later source than the built
  runtime snapshots. They do not retroactively change binary build provenance.
  Fresh kernel selection still retains legacyA5 client; F4 needs the established
  verified repackage/client override path. Final R4 already contains F4.

## Primary and preservation

Fixed service DragonhydraWorkstationTest/LocalService; root
build/workstation/test-install, state `state data`. Joomla18740 → configured
signed bridge → API18744 → authoritative kernel/core.sqlite3. Joomla MariaDB18741
dragonhydra_admin/dh_. Other installations are distinct;18743 is not this backend.

After cancellation, read-only four-group verification exited0 at15:13UTC:
760records/allID-versionpairs, pairing/configuration/ports and all four service
PIDs preserved: primary12904/default39364/provider23500/A829480. Existing primary
administrator credentials genuinely authenticated before upgrade; no reset.
Private DPAPI owner mechanism remains in build/joomla-frontend-20261101/private-backup.
Do not print or distribute values. Primary still has older A5 client; new F4/native
acceptance in this primary is NOT_RUN even though A8 previously verified F4.

Restricted backups: build/system-control-center-20261101/private-backup.
Consistent SQL/online SQLite integrityPASS, scoped deployed files and original
server/client/workstation/webinputs; immediate-predeploy-r4 preserved too. Baseline
55menus/11articles/48modules. No private bridge ACL weakening. Rollback scope and
concurrent-data caveat are in report; no rollback applied.

## Evidence and remaining acceptance

124 focused backend tests PASS. Frozen6+22+9 groups PASS; actual isolated760-record
workflow produces five models/five predictions from50inputs. Selectedmatch:
07cd1d80a5a57f42dab48dd2624fec83362d3ebac48e17e7ad05a2b4b5f9d277
(NottinghamForest–ManchesterCity,2026-11-07,OpenFootball). Job/record IDs in build
receipt. Real evaluation is pending LATER_RETAINED_OUTCOME_UNAVAILABLE; scores not
invented. Pairing/data/history/idempotency survive isolated process restart.

Latest Joomla source/harness27PASS; earlier45broader batch separate/overlapping.
Final packaging/helper/supervisor29PASS includes actualPS7+PS5.1 observer functions.
Existing desktop source5PASS. Full10662installerfiles and710standalonepayloadmembers
verified. Final known-private-value scan21values/10678files/2223members zero; no apply.

New installed Control Center URL is intended, **not yet verified/installed**:
http://127.0.0.1:18740/administrator/index.php?option=com_dragonhydra&section=control
Authenticated new UI/workflow, CSRF/HTML scan, repeated extension deployment,
new primary restart and native shortcut/default-browser checks remain blocked or
NOT_RUN. No new real installed Control Center screenshot exists.

## Exact next action after owner readiness

1. Refresh consistent private baseline if stale; confirm four service ownerships.
2. Launch one elevated exactPS7 invocation of
   tests/installation/system_control_install.ps1 -Phase Upgrade -Apply,
   with finalR4 Setup/hash above and a fresh primary-upgrade evidence path.
   Fixed target is primary only; guard preserves the other three services.
3. Inspect helper receipt, installed hashes/system.build and 18-module schema.
4. Execute tests/installation/system_control_browser.py --apply-workflow
   --output build/system-control-center-20261101/evidence/browser-r1
   (choose fresh suffix if needed). Private credentials stay DPAPI/inmemory.
5. Verify actual repeated supported extension update: owned admin menu may add
   one record55→56; existing Home/articles/module assignments must persist.
6. Scoped primary restart through actual owning controller/helper -Phase Restart
   -NewPayload -Apply; compare persisted workflow/data/pairing and unrelatedPIDs.
7. Run read-only system_control_native_preflight.py for exact repaired F4 identity,
   then official shortcut/default-browser acceptance via fresh native observation.
   Do not resume Android UI or automate UAC/security authentication dialogs.
8. Update A–N matrix/report/state on actual evidence; publish only accurately
   scoped packages. Preserve independent files and historical A9 assets.

Preservation source2529b173f0a20955b4db732b39de35d5e2bc2603 was pushed; a fresh
remote branch comparison returned that exact commit. Later sanitized metadata
updates are separately checkpointed; use `git log` for final HEAD. This task is not complete while primary
deployment, authenticated new Control Center and required integration are unverified.
