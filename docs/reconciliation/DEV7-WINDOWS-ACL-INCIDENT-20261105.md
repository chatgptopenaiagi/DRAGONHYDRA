# Windows profile access incident — November 5, 2026

## Original failure

Frozen application `c7f94787672ed96153c4c4cbe1a253bb64c2ba85`, version
`0.5.0-dev.7`, installation `core-next-63cd93a95e8e4e1da4e7ee258463b56a`:
service `DragonhydraCoreNextcandidateee258463b56a` exited with Windows1067,
supervisor1, SCM7031. `CoreNextProfile.ps1:9` raised UnauthorizedAccessException
while testing the canonical `installation-profile.json`. Original InstallFresh
remains `INSTALLER_FAILED_RECONCILE_NO_RETRY` / failed_reconciliation_required.

Private evidence is under
`C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\release-evolution-20261105\dev7-acl-recovery`.
`BEFORE-REPAIR.json` binds original receipts, scripts, logs, ACLs, parents, service
configuration, recovery actions and event records with SHA256. Original evidence
was copied before changing the service. No historical receipt was overwritten.

## ACL repair

The actual LocalService token (`S-1-5-19`) contains enabled candidate SID
`S-1-5-80-3359176657-272294135-2464709472-3477227934-2942367633`.
Before repair, this token could read workstation scripts, inspect all ancestors
and write state, but could neither read the profile nor validate its path. The
installation root and profile granted only SYSTEM, Administrators and the owner.
No contributing parent deny or reparse point was observed.

Operation `DEV7-WINDOWS-ACL-RECOVERY-20261105-R1` binds the exact failed predecessor.
Only this service was disabled and its recovery actions suspended. Windows cannot
cancel a queued restart merely by changing failure actions; disabling the service
and waiting beyond300 seconds controlled the previously queued actions.
See [Microsoft's SCM contract](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-changeserviceconfig2a).

Before/after probes used the same registered service, account and enabled SID:
its unchanged service EXE was copied to a private diagnostic directory, its binary
binding temporarily changed and then restored. This was explicitly a token probe,
not application acceptance. Installed application bytes were not patched.

The production ACL function adds only candidate-SID permissions: installation root
RX (noninheriting), profile Read, application inheritable RX, state inheritable
Modify. Existing owner/SYSTEM/admin grants and protected ACLs remain. The recovered
old state's preexisting LocalService grant is preserved as forensic history; fresh
installs use the service SID for state access.

`TOKEN-after.json` proves profile read, ancestor metadata, script read, state
create/read/delete, denied profile/script write and original path-validator success.
Profile SHA256 remains
`ded5a1efdebdc42daca53444d677eb756de7d9686b858101b970af3ae988f60f`.

## Service startup

Exactly one application startup was executed after verifying10,670 installed
manifest members. The original observer encountered a sharing violation reading
`status.json` during atomic replacement; its failed receipt is retained as
`RECOVERED-STARTUP.json`. This was an observer failure, not a second service crash.

The separate, read-only `RECOVERED-READBACK-R1.json` uses the existing atomic reader
and confirms the same service generation: PID30700, started21:05:04UTC,
LocalService, running for99.87 seconds at21:06:44UTC. Backend31024,
MariaDB31720 and Apache9692 were alive. No startup retry occurred. The original delayed-auto/restart policy was restored after successful readback,
without stopping or restarting this generation; RECOVERY-RESTORED.json records
exact recovery-configuration readback. Crash injection remains NOT_RUN.

## Application readiness

The existing local-session token was used only in memory for authenticated
`/dragon/api/v1/health/ready` and `/system` at127.0.0.1:19100.
Readiness, version0.5.0-dev.7, sourcec7f9478, installation identity and build
`dev7-workstation-c7f94787672e` matched. No credential is included in this report.
INSTALLED-READS.json confirms all760 retained matches (430finished/330scheduled),
registry18 and one successful persisted import job with one attempt. Historical
forecast endpoints are readable but this fresh candidate has no forecasts or
exports at that read checkpoint. A distinct exports-r3 operation subsequently
created exactly three JSON/CSV/XLSX exports of one retained finished match and
validated actual downloads. All original sporting/auth/config/job records remained
unchanged; the frozen delta auditor verified three jobs/twelve events. Earlier r1
(first-page selection) and r2 (intentional kernel-secret denial) stopped before POST
and remain failed. No forecast was created; forecast persistence remains NOT_RUN.

## SQL Server

SQL provisioning is a separate explicit owner operation. Its installed PowerShell5.1
preview was rejected by script execution policy before the helper ran. All policy
scopes were Undefined, resulting in the Windows default Restricted policy. No SQL
provisioning, alternate transport, policy change or service-SQL claim followed.
Service SQL authentication, archive transactions, duplicate handling and SQL restart
persistence remain BLOCKED. Interactive historical SQL proof does not satisfy them.
SQLite and MariaDB retain their established ownership.

## Permanent installer repair

`packaging/windows/workstation/Workstation.ps1` provisions the generated service
SID and ACLs before startup and records the unchanged profile hash. Fresh services
are registered Manual until provisioning completes. Fresh state no longer receives
shared LocalService FullControl. A bounded Run preflight requires actual LocalService
and enabled installation SID, profile/hash and application reads, immutable-file
write denial, and state write/delete. Automatic failure restarts are configured
only after initial readiness. Legacy profiles keep their explicit existing policy.

`CoreNextProfile.ps1` now uses terminating metadata reads: genuine absence is
allowed for future paths, permission denial reports the exact path, other provider
errors propagate, and every ancestor remains checked for reparse points. Canonical
profile, installation-ID and containment checks remain in force. New profile roots
receive private inheritable SYSTEM/Admin/owner permissions before the JSON is
written; existing roots are rejected without ACL changes. This closes the default
generator inherited-write gap demonstrated beneath the lab parent.

## Fresh installation

NOT_RUN at this source checkpoint. Recovered dev.7 is not proof of a corrected
fresh installer. New same-source server, desktop, Joomla and workstation outputs
are required before a new identity/port triple can undergo the existing Windows,
SQL, persistence, repair, retained uninstall and native/Joomla acceptance sequence.
The existing release coordinator remains authoritative; no parallel release pass
is issued by the recovery contract.

## Regression tests

The original focused39 tests passed. Subsequent review added file-specific write
denial, Manual-registration sequencing and a PowerShell7 timestamp normalization
regression. The discoverable wrapper executes both NTFS/path fixtures under
PowerShell7 and Windows PowerShell5.1. Recovery-contract behavior rejects tampered
receipts/profiles, wrong identities, unauthorized directories, denial and junctions.
Original failed fixture/observer receipts remain private and immutable.
The c44 source checkpoint passed1044 tests:1016PASS/28NOT_RUN/0FAIL; all tracked
files stayed unchanged. The final acceptance adapter also binds the release version
to the exact frozen source matrix, replacing its dev.7-only literal with four new
behavioral tests. This tooling correction requires another source freeze and new
identity-bearing outputs; c44 builds remain preserved as preliminary evidence.
Final source-suite and build results belong to new source-bound receipts; they
must not be inferred from earlier runs or added as overlapping test totals.

## Source

Repair worktree `release-source/dev7-acl-repair-20261105`, branch
`fix/core-next-dev7-windows-profile-acl-20261105`, derived from immutablec7f9478.
The actual new commit is recorded in the private source-freeze/build receipts.
Forecasting implementations and sporting calculations are unchanged.

## Release

Next candidate:0.5.0-dev.8 / Python0.5.0.dev8 / Windows0.5.0.8 / Android11.
The exact remote dev.8 tag was absent during read-only audit. The coordinator binds
each immutable release tag to one source, so sealed dev.7 is not reused. All
required packages must be built from the new frozen source. GitHub software
publication remains HELD until genuine mandatory gates pass. A source push is
separate from downloadable release publication.

## Preservation

`PRESERVATION-AFTER.json` verifies frozen dev.7 clean atc7f9478; all15 dev.7 assets
(nine software packages), both15-asset dev.6 seals and all15 dev.5 assets unchanged;
43 prior profile metadata files unchanged; nine original operation files and14
preserved evidence copies unchanged. All six protected services remained Running
with identical current PIDs/configuration since BEFORE-REPAIR and bindings equal
to the original failure receipt. Their historical PIDs differ from that older
receipt; the difference is recorded without attributing a cause. No protected
database was opened or mutated; no whole-live-database equality is claimed.

## Result

PARTIALLY_COMPLETE: actual token ACL repair and recovered application readiness
PASS; permanent source correction implemented. Fresh corrected installation,
installed SQL and full lifecycle/native/privacy/release qualification are pending.

## Next engineering action

Freeze verified repair source and build new source-bound candidate. Resolve the
recorded Windows script-policy prerequisite through an approved owner context
before the existing SQL provisioning phase; do not retry it through Bypass or a
different transport. Then execute the established fresh-install acceptance and
coordinator gates. No historical failed phase may be replayed.
