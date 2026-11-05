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