# Resume DRAGONHYDRA CORE NEXT — active dev.4 r2

**Current unpublished dev.4 r2 status (2026-11-02):** the running primary has
Joomla component/template/package **dev.4, source `3cae11e4d44c2ffa2b7ad7c03b6c9ff6b4696d32`**, installed and
reapplied through the supported Joomla CLI. Its backend, native client, launcher,
service and profile remain **dev.3, source `3af173d0248e95f7d76aeabed1095aa4f3e97af3`** at
API `18821`, Joomla `18822`, MariaDB `18823`; service PID `32192` was preserved.
The new PHP presentation rule makes `UNVERIFIED` and `EXPIRED` neutral, with
matching legend/render/expiry regressions. That change is **source only** until
a new frozen source and fresh r2 packages are built and deployed. Version/tag
remain dev.4; no dev.4 tag, draft or public release has been created.

The full dev.4 Windows elevation/launch ended in `InvalidOperationException`,
native code unavailable, with no returned child, operation receipt or one-shot
marker. Cancellation versus launch failure is not established. It was not retried;
no new Windows attempt is authorized before owner acknowledgement. Preserve all
nine r1 packages/source `3cae11e4d44c2ffa2b7ad7c03b6c9ff6b4696d32` and their receipts. R1 source verification was
302 unique cases: 295 PASS, 7 NOT_RUN; this is not the pending r2 source gate.

Actual browser r2 retained 159 PASS and one logout assertion FAIL caused by a
navigation race in the LAB harness. The corrected r3 run is terminal **PASS:
186 PASS, 2 NOT_RUN**, using the existing five job IDs without resubmission.
This verifies deployed Joomla r1 on backend dev.3, not the pending neutral-state
source or a dev.4 Windows runtime. Native dashboard pairing and service restart
are the two NOT_RUN scopes in this browser harness. No eligible later retained
outcome was observed, so pending evaluation is not an accuracy/learning claim.

Local evidence: [nine-package inventory](<C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/evidence/dev4-partial-deployment-package-inventory.json>),
[package checksums](<C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/evidence/dev4-package-SHA256SUMS.txt>),
[Joomla install/repeat receipt](<C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/continuation-20261102/joomla-only-dev4-r1/verification.json>),
[browser r3](<C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/acceptance/dev3-joomla4-browser-r3/verification.json>).
Recoverable backups: [Joomla scoped rollback](<C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/continuation-20261102/joomla-only-dev4-r1/ROLLBACK.md>)
and the owner-restricted `joomla-only-dev4-r1/private` plus
`dev3-windows-operation-r1/private-upgrade-backup` directories. Never publish
their SQL, runtime state or credential-bearing contents.

Next: finish the neutral-state source gate, freeze the new r2 source, then
build/verify fresh source-bound dev.4 r2 packages in new directories. Preserve all
r1 attempts. Resolve owner Windows approval before any new privileged operation;
keep full Windows/browser/privacy/publication gates separate and fail closed.

Work only in `C:\xampp\DRAGONHYDRA-CORE-NEXT`; LAB owns private runtime/evidence.
Read `ENGINEERING-STATE.json`, `docs/handover/CONTINUATION-20261102.md` and the
current release-report section first. Original DRAGONHYDRA and all other
workstation profiles remain protected. Do not reset credentials, acquire providers
or automatically rerun historical lifecycle commands. The primary owner opens
http://127.0.0.1:18822/ and its existing Administration shortcut; use the local
protected credential workflow, never this documentation as a credential store.

## Historical handoff retained below

The following text records previous dev.3/dev.1 checkpoints. Published dev.1
claims apply only to its immutable 953 source/tag; its commands and next-objective
text are not the active r2 instructions above.

ACTIVE UPDATE — dev.3/source3af173d is installed; NOT published.
Primary upgrade/workflow/restart and disposable install/repair/restart/uninstall
passed. Actual kernel Edge standings/skip/reload tests passed. Authenticated Joomla
narrow-screen acceptance found persistent Atum header-title overflow (539px at
390px after settling); component content itself fits. Dev.4 is the justified
scoped presentation repair. Preserve all dev.3 artifacts and failure receipts.
Read active_continuation_20261102 and docs/handover/CONTINUATION-20261102.md.
Original DRAGONHYDRA source/services/A9 remain read-only and preserved.

# Resume DRAGONHYDRA CORE NEXT

Read AGENTS.md, BASELINE-LOCK.json, ENGINEERING-STATE.json and docs/releases/CORE-NEXT-RELEASE-REPORT.md.

Independent source `C:\xampp\DRAGONHYDRA-CORE-NEXT`; private runtime/evidence `C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB`. Preferred E: unavailable. Original `C:\xampp\DRAGONHYDRA` remains a separate project; do not execute its installers or modify its services/state/source. Its concurrent external local commits/index changes are observed separately.

Baseline `genesis-a9-20261101`, exact `2e6520d5b6a7874881e5de85dbb6ececaef11d8f`. Candidate branch `release/core-next-20261101T1400Z`. Frozen compiled source `953b67fa50dfa9d705f060f97b8a1af5d317c001`. Tag `v0.5.0-dev.1-core-next` pins that source. A later documentation commit is not the package source and must not move a published tag.

Actual implementation: composed six engines, explicit ports, real API/Product/Jobs dispatch, authenticated cached registry and native Joomla Control Center. Final candidate33 semantic groups match the baseline using the same retained snapshot and fixed clocks/seeds. The final installed Linux archive passes11 groups, including the same-endpoint restart. SourceZIP matches722 Git blobs. Windows primary PASS, desktop PASS, Android emulator PASS; publication PUBLICATION_AND_DOWNLOADS_VERIFIED. Scope and evidence are in the release report.

Installation `core-next-7ac520727b85456cac4a3a92a8dd62da`:

- Application: `C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles\core-next-7ac520727b85456cac4a3a92a8dd62da\application`.
- State: `C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles\core-next-7ac520727b85456cac4a3a92a8dd62da\state`.
- Service: `DragonhydraCoreNextcandidate3a92a8dd62da`.
- API/Joomla/MariaDB ports: `18821` / `18822` / `18823`.
- System Control Center: http://127.0.0.1:18822/administrator/index.php?option=com_dragonhydra.
- Private profile: `C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles\core-next-7ac520727b85456cac4a3a92a8dd62da\installation-profile.json`.


```powershell
Set-Location C:\xampp\DRAGONHYDRA-CORE-NEXT
$profilePath = 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles\core-next-7ac520727b85456cac4a3a92a8dd62da\installation-profile.json'
. .\packaging\windows\workstation\CoreNextProfile.ps1
$profile = Read-CoreNextProfile $profilePath -CheckService
Start-Service -Name $profile.service_name
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -File 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles\core-next-7ac520727b85456cac4a3a92a8dd62da\application\workstation\Workstation.ps1' -Action Status -ProfilePath $profilePath
```


All runtime credentials remain in this edition's private state/first-run design; never print them. Pair clients with this edition only. Status refresh must not acquire providers, infer or start jobs. A historical finished-match report is not a pre-event forecast. Optional AI failure must remain scoped.

Next unfinished objective: Broaden acceptance on a clean Windows system and a physical Android ARM64 device; production signing remains unavailable.
