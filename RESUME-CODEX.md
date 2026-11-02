ACTIVE UPDATE — dev2 source343de81 is installed and lifecycle verified; NOT published.
Real18821 keyboard skip link loses standings route. Source fix is tested; preparing dev3.
Read active_continuation_20261102 and docs/handover/CONTINUATION-20261102.md.

ACTIVE CORE NEXT CONTINUATION — 2026-11-02.
Owner settled18822/18821 and profilecore-next-7ac520727b85456cac4a3a92a8dd62da.
Read docs/handover/CONTINUATION-20261102.md and active_continuation_20261102 state.
Dev2 source verified: 290 unique cases, 283 PASS, 7 explicit NOT_RUN; installed953/dev1 remains untouched.
Consistentprivatebackup-r2done; protectedkernel files needelevatedbackupbeforelivewrite.
OriginalDRAGONHYDRA source/services/A9 are READ ONLY and preserved.

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
