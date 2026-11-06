# DRAGONHYDRA Windows service ACL incident — verified delivery checkpoint

## Current verified checkpoint — 2026-11-06

**Result: COMPLETE for the supported explicit-profile acceptance contract on the current Windows11 host.** The permanent installer correction, genuine installed qualification and [published development prerelease](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/tag/v0.5.0-dev.8-core-next-r2) are verified for application source `2d603431aac0bd86f6ae07e07f124fdfdc0dccce`. All15 actual published asset downloads matched the sealed bytes/SHA-256 values, and no mandatory release gate remains. The mixed-legacy default-profile/no-argument Setup limitation and optional Android-device/Linux-runtime exclusions below remain explicit. This separate documentation checkpoint changes neither application source nor sealed packages.

Current machine-readable report: [DEV7-WINDOWS-ACL-INCIDENT-20261105.json](DEV7-WINDOWS-ACL-INCIDENT-20261105.json). Private evidence is under `LAB/release-evolution-20261106/dev8-acceptance-r1/genesis84` unless stated otherwise. The complete earlier November5 report is preserved verbatim below as historical evidence, including its then-blocked operations.

## Original failure and root cause

Frozen dev.7 source `c7f94787672ed96153c4c4cbe1a253bb64c2ba85`, installation `core-next-63cd93a95e8e4e1da4e7ee258463b56a`, service `DragonhydraCoreNextcandidateee258463b56a`, failed with Windows1067, supervisor1, event7031 and installer1. `CoreNextProfile.ps1:9` encountered access denied while validating the canonical `installation-profile.json`. The immutable original receipt remains `INSTALLER_FAILED_RECONCILE_NO_RETRY` / `failed_reconciliation_required`.

The actual token was LocalService (`S-1-5-19`) with enabled service SID `S-1-5-80-3359176657-272294135-2464709472-3477227934-2942367633`. The profile root lacked service read/traverse access and the profile file lacked Read. Existing application/state grants did not make the profile readable. The before/after real-token probes distinguished this failure from an Administrator read; no contributing parent deny or reparse point was observed. The original profile SHA-256 remains `ded5a1efdebdc42daca53444d677eb756de7d9686b858101b970af3ae988f60f`.

The separately hash-bound recovery preserved the original failed operation, ACLs, SCM/recovery settings, logs and receipts. Candidate-only ACL correction produced actual supervisor/backend readiness; original recovery/start configuration was then restored. No historical failed phase was replayed or relabeled successful.

## Permanent correction and further genuine failures

`Workstation.ps1` establishes the generated service SID, grants root RX/profile Read/application RX/state Modify before service startup, and delays automatic recovery until readiness. Private profile creation preserves owner/SYSTEM/Administrators. The actual supervisor checks LocalService plus enabled candidateSID, unchanged profile hash, required reads, immutable-write denial and state write/read/delete. Reparse/junction, traversal and noncanonical-path protection remains fail closed with accurate access-denied diagnostics.

Genuine installed testing exposed additional defects rather than ending at corrected ACL metadata. Source0e5 SQL maintenance failed under native PowerShell5.1; source-bound corrections cover connection-builder dictionary keys, the existing typed atomic receipt writer/primary-error preservation and binarySID handling. Later source937 passed fresh/serviceSQL/native/restart/repair/retain-uninstall, but its retained reinstall failed at `NTAccount.Translate` after SCM service recreation. That receipt remains failed (`cc0f60ce…a844`) and its candidate remains forensic, stopped/Manual/PID0.

Final source2d uses the shared strict `Get-CoreNextServiceSid` in profile ACL provisioning, actual-token verification and SQL maintenance. It verifies the canonical owned service image/account, UNRESTRICTED configuration and exactActive SCM `showsid` response, returning a typed SID without account-name translation, retries or cache reset. The precise Windows lookup mechanism behind the old translation failure remains unproven. The new source-bound retained reinstall actually passed.

The earlier Restricted-policy rejection remains preserved. Later owner authorization supplied a dedicated temporary Process RemoteSigned context for normal installer/maintenance execution; no persisted machine/user policy or elevation bypass is claimed. SQLite remains the canonical sports/cognitive/job owner, MariaDB remains the Joomla owner, and SQL Server is only the explicitly selected secondary immutable research store. Forecasting mathematics and accuracy claims are unchanged.

## Real service identity and startup

Final installation: `core-next-f786d2c973204dd2b94330b504db72cd`; service `DragonhydraCoreNextcandidate30b504db72cd`; source `2d603431aac0bd86f6ae07e07f124fdfdc0dccce`; version0.5.0-dev.8; API/web/database ports19340/19341/19342. Profile SHA-256 is `fbec5bc61927c191315845d0a643224daa0a9828f95a2a662aa5755da2af1e76`. Setup SHA-256 is `fa61249b8ee94b4d720f52c2adc3a7c2ad063b42d6250b506d8238ac3cd8d7a3`.

Actual LocalService, enabled service SID `S-1-5-80-2480845542-481575623-1313647330-996504717-1107577505` and UNRESTRICTED configuration passed real supervisor token/profile checks and authenticated backend readiness. Fresh receipt `e4fa21b0…9916e` binds source, build, installation and the760 retained records. SQL reload and subsequent real restarts produced new owned service generations; process launch alone was never accepted as readiness.

The installed SQL connection reports primary Windows account `NT AUTHORITY\LOCAL SERVICE`; grants bind the distinct `NT SERVICE\DragonhydraCoreNextcandidate30b504db72cd` SID. Actual service authentication, explicit schema permissions, publication denial, one restoration with zero-delta proof, commit/rollback/duplicate handling, archives and exports are established by the unchanged source-owned acceptance contract. Owner provisioning alone is not substituted for service authentication.

## Supported installation contract and mixed-legacy host limit

The genuine acceptance used the existing supported `/PROFILE` installation route and its reviewed one-shot controller. On this mixed-generation host, an unchanged historical dev.1 profile lacks later required fields, so the default `New-CoreNextInstallationProfile` reservation scan fails closed. Root preserved that legacy profile and its original hash; no validator was weakened and no legacy profile migration is claimed.

Root used the existing pure profile factory with a fully validated explicit profile and a recorded audit reserving all prior profile ports. The normal installer then provisioned the final candidate's service ACLs automatically, before startup; no manual ACL repair was used to make the finalf786 installation pass. **No no-argument Setup acceptance is claimed.** This is the genuine supported explicit-profile/controller contract, rather than proof of the default profile-creation route on a mixed-legacy host.

## Actual execution context and restoration

PowerShell7.6.9 and native Windows PowerShell5.1.29695.1001 were verified as x64. Root executed reviewed native5.1 `-File` SQL maintenance through the approved dedicated Process RemoteSigned tree, with the required children inheriting that scoped context. `EXECUTION-CONTEXT-FINAL.json` (`f773b66f…bcfd`) records Process RemoteSigned during execution and Process Undefined afterward in both hosts. All persisted policy scopes match their before snapshots: the pre-existing PS7 LocalMachine RemoteSigned setting remains, while native5.1 returns to its baseline Restricted effective policy with explicit scopes Undefined. The original rejected operation remains rejected; no persistent policy change, elevation bypass or alternate transport is claimed. Existing installer-internal flags were not changed by this verification.

Fresh installed readiness used servicePID31752; the genuine retained reinstall used servicePID32140. After the accepted final uninstall, the test service is absent and data is retained. No unrecorded uptime is inferred or claimed.

## Completed acceptance and regression results

| Scope | Actual result |
|---|---|
| Fresh installed Windows | PASS; registration, LocalService/SID/token/profile, supervisor/backend and authenticated source identity |
| Lifecycle5 | PASS: Restart, Repair, UninstallRetain, ReinstallRetained, FinalUninstall |
| Source-owned SQL/application11 | PASS: read-fresh, initialize, forecast, publication-denied, publish, backup-readback, restart-readback, repair-readback, uninstalled-readback, reinstall-readback, final-uninstalled-readback |
| Native GUI | PASS7 actual checks; normal own launch/pairing, retained navigation, unavailable context, Model probabilities view, Administration handoff, real error and same-client recovery |
| Joomla browser | PASS normal own CSRF login, modules/source/build/installation, retained-match navigation and logout; browser/profile cleanup |
| Source regressions | 1064 tests:1036PASS,28skipped,0 failures/errors; zero realSQL/external network attempts in this unit-suite scope |
| Android | ARM64 build/signature/source identity and15 host tests passed; optional device acceptance NOT_RUN |
| Linux | Archive/source/dependency integrity passed; optional runtime NOT_RUN/BLOCKED by the previously unavailable Docker engine; no retry/daemon workaround |
| Final artifact privacy | PASS for the exact15 final files, with 0 findings; its private receipt is bound in the JSON. |

The native aggregate `NATIVE-SID-ACCEPTANCE-R6.json` (`1a32eac1…3c6f`) binds actual client37484/window43778248, the real stopped-state error within90seconds, one service recovery25304→33072, fresh token/authenticated readiness and all10 protected identities. Raw service/controller GUI=false fields remain unchanged; separate Root error and manual-Refresh recovery observations supply the GUI evidence. The sports UI does not display the commit: compiledEXE/source and backend/Fresh bindings establish identity separately. Its Model probabilities view is not treated as durable-persistence proof; source-owned forecast/publication/backup/readback receipts supply that distinct proof.

JSON/CSV/XLSX exports, persistent jobs and retained records passed their actual source-owned chains across restart, repair and retained reinstall. FinalUninstall then passed and the source-owned final-uninstalled-readback verified retained data. The tested final service is now absent by the acceptance contract; no still-running final installation is claimed. Original NativeR1 failure and source937 successes/failure remain historical evidence.

## Release impact and preservation

All nine packages are bound to the same frozen application source `2d603431aac0bd86f6ae07e07f124fdfdc0dccce`. Source937/0e5 and dev.5/dev.6/dev.7 packages, worktrees, failed receipts and ledgers remain preserved. Final Python artifacts are the corrected `python-dev8-sid-r4b` files; preliminary functionally-tested outputs with missing generated manifest remain explicitly NOT_FINAL. Whole-source manifest870 rows has SHA-256 `354ca3671654310c602509251b6f1f15c6ffc798787f12efacf1bc43e5d89c99`.

| Kind | Final filename | SHA-256 prefix |
|---|---|---|
| wheel | dragonhydra-0.5.0.dev8-py3-none-any.whl | `23e36c69a51d0720…` |
| sdist | dragonhydra-0.5.0.dev8.tar.gz | `8a9c529e41f2ee92…` |
| android | DRAGONHYDRA-CORE-NEXT-0.5.0-dev.8-Android-arm64-development.apk | `23d40e643438a4dc…` |
| linux | DRAGONHYDRA-CORE-NEXT-0.5.0-dev.8-Linux-server-x86_64.tar.gz | `93b9c4ed7b80708d…` |
| source | DRAGONHYDRA-CORE-NEXT-0.5.0-dev.8-Source.zip | `4b0cec428f2de4ab…` |
| server | DRAGONHYDRA-CORE-NEXT-0.5.0-dev.8-Server-win-x64.zip | `7e9ef0ce7764cd9c…` |
| desktop | DRAGONHYDRA-CORE-NEXT-0.5.0-dev.8-Desktop-win-x64.exe | `470813146d6c0c01…` |
| joomla | pkg_dragonhydra-0.5.0-dev.8.zip | `f3124041a6d40b30…` |
| workstation | DRAGONHYDRA-CORE-NEXT-0.5.0-dev.8-Workstation-win-x64-Setup.exe | `fa61249b8ee94b4d…` |

Release tag: `v0.5.0-dev.8-core-next-r2`; application0.5.0-dev.8/Python0.5.0.dev8/Windows0.5.0.8/Android code11. The existing coordinator and its unchanged source/hash/primary/privacy/history guards completed `PUBLICATION_AND_DOWNLOADS_VERIFIED` at11:50:25UTC. Actual release436433261 is published, draft=false/prerelease=true, at11:48:24UTC: [release and downloads](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/tag/v0.5.0-dev.8-core-next-r2). All15 published files were actually downloaded and matched the sealed sizes/SHA-256 values. The authoritative download receipt is `6dda7bb5…e765`; the final ledger is `6b34c276…5d3d`. No sealed bytes or historical release identifier was replaced.

R7 preservation closure `285e3c81…ce1b` passed:75 sealed files across5 roots,155 named unique files and the frozen/failed-source evidence were checked with no observed differences. All10 protected service PID/account/start-mode/command-line bindings remained exact:9 running and the prior failed source937 candidate stopped/Manual/PID0. The final2d test service is absent. GitHub preservation receipt `d3299b90…74d2` verifies10 historical releases,95 historical assets and14 tag references at its prepublication checkpoint. These historical counts are not a claim about a later new release. Database ownership and retained-data proofs are scoped; no whole-live-database byte equality or historical remote asset download-byte comparison is claimed. Codex executable metadata/hash matches its baseline; these engineering operations did not execute, update or reinstall Codex CLI.

## Publication-tooling checkpoint — completed after preserved failures

The final15-file privacy check passed (`e4477f12…657ab`), and the existing coordinator validated all15 files and historical preservation. Root pushed the annotated release tag `v0.5.0-dev.8-core-next-r2`, tag object `54e605a6a072faabe31a39491e26ec6afee2facd`, peeled to application source2d.

The first staging attempt created empty draft436407881, then failed because the by-tag API lookup returned404 for that unpublished draft. Its stderr and original ledger were preserved. Root deleted only that exact empty draft and confirmed absence; no software asset had been uploaded and no historical release or ledger was rewritten.

A second staging attempt using preliminary tooling source `bf32612d651980b3e2b12a944feaa1de39be73f1` also failed when immediate post-create discovery returned no draft. Empty draft436419791 was later found and its exact zero-asset cleanup was preserved. Normal and no-cache post-delete probes both showed absence; a cache or read-after-write cause is **UNPROVEN**. Neither failed stage is relabeled successful.

Final publisher tooling source `db8414ff6a08bd0c85310564771475e71d00e8a4` is frozen and pushed on `fix/core-next-release-draft-lookup-20261106`, in the separate registered `LAB/release-source/dev8-release-draft-20261106` worktree. Its60/60 focused tooling tests passed (`661e92cc…d9c`). The existing publisher now uses an exclusive private JSON create request/raw response, validates the returned ID/tag/title/notes/draft/prerelease/zero-asset identity, records ownership from that response, and subsequently reads the numeric releaseID with no-cache. Acceptance/source/privacy/history gates remain unchanged.

This is a distinct tooling checkpoint, with application source2d and all15 sealed asset bytes unchanged and no application rebuild. Root's third operation actually completed staging, publication and verified downloads through the existing coordinator. Supplemental `PUBLICATION-CLOSURE.json` (`9ce24318…c14a`) independently compares all15 new downloaded files to the sealed artifacts and preserves the old10 releases/95 asset IDs, names, sizes, digests, classifications and14 tag-reference targets. The resulting current repository totals are11 releases/110 assets. The two earlier failed empty-draft operations remain failed and preserved. R8 local preservation (`bd06d614…4833`) and additional frozen-source preservation (`256e3c02…477d`) passed; the post-publication R9 check at11:53:02UTC again passed for all10 protected service identities and installed Codex metadata (`58d6ca37…db8d`). R8 service/Codex proof (`58b52c74…6514`) remains retained as an earlier checkpoint. No application-source/package rebuild or service/Codex mutation was needed for publication.

## Result and next engineering action

**COMPLETE within the stated current-host explicit-profile/controller acceptance scope.** The Windows ACL/SID installer repair, real service identity/readiness, SQL/application persistence and exports, all5 lifecycle/all11 source-owned phases, native/Joomla checks, final privacy/preservation and actual published15-file download verification passed. No mandatory release gate remains. No mandatory engineering action remains. This separate documentation checkpoint records the verified release without changing application source or requiring a rebuild. No no-argument Setup, legacy-profile migration, clean-machine acceptance, optional Android-device or unavailable Linux-runtime pass is implied. Historical failed operations remain preserved and must not be replayed.

## Preserved historical checkpoint — November5

The following earlier report is retained verbatim. Its source0e5, BLOCKED/NOT_RUN and publication-held statements describe that earlier checkpoint rather than the current source2d acceptance above.

<details>
<summary>Original November5 engineering report (unchanged text)</summary>

# DRAGONHYDRA Windows service ACL recovery — final delivery

## Original failure

The immutable dev.7 application source is `c7f94787672ed96153c4c4cbe1a253bb64c2ba85`.
Installation `core-next-63cd93a95e8e4e1da4e7ee258463b56a`, service
`DragonhydraCoreNextcandidateee258463b56a`, failed with SCM1067/supervisor1/event7031.
`CoreNextProfile.ps1:9` could not access the canonical installation-profile.json.
The original InstallFresh receipt remains failed_reconciliation_required and unchanged.

All private receipts below are under
`C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\release-evolution-20261105\dev7-acl-recovery`.
BEFORE-REPAIR.json preserves original receipts, logs, hashes, SDDL, parents, SCM
configuration and recovery policy. No historical failure was overwritten.

## ACL repair

Actual LocalService (`S-1-5-19`) contained enabled service SID
`S-1-5-80-3359176657-272294135-2464709472-3477227934-2942367633`.
Before repair: profile read and path validation denied; ancestor metadata, scripts
and state operations succeeded. The profile root/file lacked a service grant.
No contributing parent deny or reparse point was observed.

The separately bound recovery operation applied only candidate-SID root RX,
profile Read, application inheritable RX and state inheritable Modify. Owner,
SYSTEM and Administrator permissions remain. Real-token after checks passed,
including denied profile/script writes. Profile SHA256 remains
`ded5a1efdebdc42daca53444d677eb756de7d9686b858101b970af3ae988f60f`.
TOKEN-before.json, TOKEN-after.json and ACL-APPLIED.json distinguish actual access
from ACL metadata. Temporary diagnostic binary bindings were restored; installed
application bytes were not patched. Original recovery/start settings were restored
only after genuine readiness, without a further restart.

## Service startup

Exactly one recovered application start occurred. All10,670 installed manifest
members were checked beforehand. The first observer hit a status.json sharing
race; its failed RECOVERED-STARTUP.json remains preserved. A separate read-only
receipt used the established atomic reader and verified the same service generation.
No application startup retry occurred.

SERVICE-FINAL-READBACK.json confirms LocalService PID30700 still Running and
ready at21:36:39UTC, uptime1,895seconds, version0.5.0-dev.7/sourcec7f9478.
Backend, MariaDB and Apache started under the supervisor. Automatic recovery and
delayed-auto configuration read back exactly as before the incident. Deliberate
crash injection and restart persistence were not executed.

## Application readiness

The existing authorized client session was used only in memory. Authenticated
`/dragon/api/v1/health/ready` and `/system` matched version, source, installation
and build identity at127.0.0.1:19100. No token is included in this report.

INSTALLED-READS.json confirms760 retained matches (430finished/330scheduled),
registry18 and the existing successful import job with one attempt. Forecast
history endpoints are readable; this fresh candidate contained no forecasts.

A distinct exports-r3 operation completed exactly three JSON/CSV/XLSX export jobs
and validated actual downloads for one retained finished match. The frozen delta
auditor verified three appended jobs/twelve events; original sporting, auth,
configuration and job records were preserved. No forecast/provider job was created.
R1 first-page selection and R2 protected-kernel-secret fingerprint failures stopped
before POST and remain preserved. Service-only kernel secrets were not read or
re-ACLed. These export checks do not constitute whole-release acceptance.

## SQL Server

BLOCKED. The installed SQL helper's normal Windows PowerShell5.1 preview was
rejected before execution by the effective Restricted script policy (all explicit
policy scopes Undefined). SQL-POLICY-BLOCKED.json records zero SQL actions.
No Bypass, alternate transport or policy modification followed. Service SQL login,
scoped database provisioning, archive transactions/rollback/duplicates and SQL
restart persistence remain unexecuted. Historical interactive SQL tests are a
separate scope. SQLite and MariaDB retain their established ownership.

## Permanent installer repair

Workstation.ps1 now registers a fresh service Manual, verifies its generated SID,
provisions root/profile/application/state permissions and records the unchanged
profile hash before startup. Fresh state uses service-specific Modify access.
The actual supervisor preflight checks LocalService and enabled service SID,
profile/hash/script/binary reads, immutable-file write denial and state write/delete.
Initial automatic recovery is enabled only after readiness; legacy policy remains
explicitly preserved.

CoreNextProfile.ps1 reports exact denied paths with terminating metadata reads,
allows genuine missing future leaves, rejects unexpected provider errors,
junctions, traversal and noncanonical profile identities. Newly generated profile
roots become private to SYSTEM/Admin/owner before JSON contents are written;
existing roots are rejected without ACL mutation.

The existing installed acceptance adapter now binds version to the release matrix
from the exact frozen source commit; its other immutable-byte/security gates remain.
Forecasting source and mathematics are unchanged: the only changed path under
src/dragonhydra is version metadata build_meta.py.

## Fresh installation

NOT_RUN / BLOCKED_PENDING_APPROVED_PS51_CONTEXT. The complete corrected Setup is
built, but inherited NSIS script-policy overrides must not be used as another
transport around the recorded rejection. The separately prepared
`dev8-windows-fresh-r1/PLAN.json` binds new profile ff4b...720f, source0e5df367,
service DragonhydraCoreNextcandidate86aad1db720f and ports19150/19151/19152.
No fresh install marker or service was created. The recovered dev.7 installation
is not substituted for fresh dev.8 acceptance.

SQL, restart, repair, retained uninstall/reinstall, authenticated Joomla/native
GUI and final installed privacy still require their established genuine phases.

## Regression tests

Final source suite:1048 tests,1020PASS,28NOT_RUN,0 failures/errors; all tracked files
unchanged, zero real SQL/external network attempts. This includes final focused
ACL/path/recovery/service/adapter/version cases; overlapping counts are not added.
The earlier source1044 run and all earlier failures remain separate receipts.

New compiled Windows server0e5df367 reached authenticated readiness in a fresh
standalone profile and exited cleanly. That owner-process proof is not service
acceptance. Offline wheel/server and sdist/CLI verification passed. Android15 host
checks, ARM64 build, embedded source/code11 and signature checks passed; new device
acceptance is NOT_RUN. Linux archive integrity passed; runtime is BLOCKED because
the existing Docker engine pipe is unavailable. No daemon was started as a workaround.

## Source

Application source `0e5df36704eeeaadbbf2380cc5352473fc2ebf0b` is frozen, clean and
pushed on `fix/core-next-dev7-windows-profile-acl-20261105`; remote SHA verified.
This final report is a separate documentation-only delivery checkpoint. It is
not the source identity embedded in the packages. SOURCE-PUSH and freeze receipts
record the exact bindings. No historical commit or branch was rewritten.

## Release

Candidate0.5.0-dev.8 / Python0.5.0.dev8 / Windows0.5.0.8 / Android11.
Nine final software packages are built from0e5df367 and staged with six metadata
files at `LAB\dist\v0.5.0-dev.8-core-next-acl-held-r1`.
Manifest SHA256:
`732960068f3d262556d5f6b1638b4ca8e90019eeab4590ab6d0f86425fa2d2d3`.
Preliminary c44 builds remain separate and preserved.

The unchanged coordinator prepared the honest held manifest. Actual Setup CRC/
extraction and all10,679 decoded files passed verification. Finite privacy checks
passed with zero findings across15 assets, the decoded Setup and2,801 recognized
archive members. The unchanged validator genuinely refused publication eligibility:
Primary acceptance source/hash/pass mismatch. No mandatory condition is waived.
[Machine-readable final verification](DEV7-WINDOWS-ACL-VERIFICATION-20261105.json)
binds the measured artifacts and private receipts by SHA256. No dev.8 tag, draft, software
release, upload or public-asset download verification occurred. Source publication
is complete; downloadable software publication remains HELD.

## Preservation

PRESERVATION-FINAL.json verifies60 sealed dev.5/dev.6/dev.7 assets,43 prior profile
metadata files,9 original operation files and14 forensic copies unchanged. Six
protected services remain Running with identical PIDs/configuration since
BEFORE-REPAIR; their bindings match the original failure receipt. Historical PID
differences from the older failure baseline are recorded without attributing cause.
The recovered candidate retains its original application/profile bytes.

GitHub still has10 historical releases/95 assets, unchanged identities/digests and
stable/latest selection. Only authorized new source/documentation branches are
added. Installed Codex's SHA256 equals its recorded baseline; it was not executed,
updated or reinstalled. Protected databases were not opened or mutated; no claim
of whole-live-database byte equality is made.

## Result

PARTIALLY_COMPLETE. Actual dev.7 service recovery, application/data/export access,
permanent installer correction, source tests, nine new builds and source delivery
are complete. Installed SQL, corrected fresh installation, lifecycle/native and
mandatory release qualification remain unexecuted or blocked.

## Next engineering action

Provide a compliant, approved Windows PowerShell5.1 execution context, then review
and execute the new hash-bound fresh-install plan exactly once. Run separate
source-owned SQL provisioning and dependent lifecycle/native/privacy/coordinator
phases. Publish the unused dev.8 tag only when actual mandatory gates pass, then
download and compare the published bytes. Never replay the historical failed phases.
</details>
