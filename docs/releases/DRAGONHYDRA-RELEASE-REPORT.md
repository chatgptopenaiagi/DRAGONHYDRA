# DRAGONHYDRA GENESIS A9 — release report

**PUBLISHED AND REMOTELY VERIFIED — development prerelease.**

- Release: [genesis-a9-20261101](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/tag/genesis-a9-20261101)
- Source commit: [`2e6520d5b6a7874881e5de85dbb6ececaef11d8f`](https://github.com/chatgptopenaiagi/DRAGONHYDRA/commit/2e6520d5b6a7874881e5de85dbb6ececaef11d8f)
- Published: 2026-11-01T13:09:12Z; final verification: 2026-11-01T13:14:02.813256+00:00.
- GitHub release ID: 430590555; **21 assets**, 120,602,205 bytes.
- Repository landing branch: `continuity/genesis-20261031-a6`.
- Historical `main` remains at `4d1b4b3d1960cdd047a9c857aafdc544961b9426`.

The annotated tag and source archive are immutable. This verification report is a
follow-up documentation commit after publication; the tag contains its prepublication
report. Metadata revision2 is sourced from `981f7c94a21964d7db0eeb08f9403ca8f2b12dd9`.
It labels the Windows worker's initial pending fields as historical and describes
Joomla's HMAC Python-backend integration accurately. No software binary, source
archive or tag changed. Original metadata remains in the tag and local first-download
receipts. No historical release asset was replaced.

## Frontend checkpoint finalized first

The initial `site_menus_same=false` assertion was investigated before release builds.
Only managed Home 142 parameters were normalized to Joomla's native defaults: ten
default fields were added and an unused migration marker removed. Visible owned
fields, unrelated menus, original Home 101,11 articles and48 modules remained intact;
55 menu records total. The actual database comparison passed. Seven semantic
regressions still reject unrelated, unknown, duplicate and visible-field changes.
Repeat deployment remains idempotent. See [frontend report](../../JOOMLA-FRONTEND-REPORT.md)
and `JOOMLA-FRONTEND-MENU-SEMANTICS.json` in the verified reports.

Frontend preservation checkpoint: `4a08f873429e338d30031be321a0c63ccfe196a7`.
This was committed and remotely pushed before assembling the master release.

## Architecture and component provenance

Joomla/Apache/PHP owns presentation, accounts and MariaDB. Its protected server-side
HMAC bridge reads the correctly associated Python API; SQLite remains authoritative
sports storage. Desktop and Android use their own endpoint/pairing workflow. Joomla
login, bridge authentication, local pairing and provider keys remain distinct.

| Component | Actual version | Source and readiness |
|---|---|---|
| Unified Windows workstation |0.4.1-dev.1 / file0.4.1.1|Packaging 4a08f87; exact A8 desktop, A6 server and new Joomla package. All 10,662 payload members verified; full isolated upgrade and genuine Joomla sessions passed. Unsigned.|
| Windows desktop |0.4.0-alpha.1|5821b4d54a199f73ccd943215117dcfa8e38ea4b; byte-identical earlier A8 binary. Native link/pairing evidence is historical.|
| Android ARM64 |0.4.0-alpha.1+4|4a08f873429e338d30031be321a0c63ccfe196a7; fresh release-optimized development-signed APK. Build/install/cold Home passed; connected pairing unverified.|
| Joomla |0.4.1-dev.2|55997de0a3997a10d12c6271795289a5d147e1ab; native site/admin views, HMAC bridge, assets and Cassiopeia child template. No separate Joomla REST component is shipped.|
| Frozen Windows server |0.4.0-alpha.1|Original A6 content-addressed snapshot; embedded Git SHA null is preserved. Source-content 886161d0a8c4f0bf3364fd6d0a9966630398bba6bfe27b84de9c5999a307acd4;68 scoped inputs/61 product files match current source.|
| Python wheel and sdist |0.4.0a1|46ba85c091230213189ffed679294b80019841a2; Python3.14. Fresh offline installation and runtime acceptance; rebuilding wheel from sdist yields identical bytes.|
| Linux preparation |A7 / Python0.4.0a1|2ca96e94213cc6f516b6963052ef68ff1948af94; unchanged archive and61 identical product files. Earlier Docker Linux proof only.|
| Complete source |GENESIS A9|Exact tag commit above;672 files match Git blobs. Private runtime state excluded.|

Android, desktop, Joomla component and child-template source subtrees were compared
with the release tag and have identical Git tree objects. The parent Joomla README
differs only as documentation. Versions were not changed by renaming binaries.

## Asset inventory and checksums

All packages live under `dist/master-release-20261101/assets` locally. Click a filename
below for its actual public download. The [machine-readable manifest](GENESIS-A9-RELEASE-MANIFEST.json)
records dependencies, source identity, build configuration, installation, tests and
limits per asset. Build timestamps are retained in platform reports; unavailable
original compiler times are explicitly unknown, not inferred from copy timestamps.
[SHA256SUMS](GENESIS-A9-SHA256SUMS.txt) covers all release files except itself; its own
remote digest is recorded below and in the publication receipt.

| Asset | Bytes | Version | SHA-256 |
|---|---:|---|---|
| [ANDROID-BUILD-REPORT.json](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/ANDROID-BUILD-REPORT.json) | 9,057 | GENESIS A9 | `f67ccc58bcebf75793ab8c91901f1038d1e77e9fd35058a1d12249a551269f28` |
| [DRAGONHYDRA-0.4.0-alpha.1-Android-arm64-development.apk](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/DRAGONHYDRA-0.4.0-alpha.1-Android-arm64-development.apk) | 17,345,938 | 0.4.0-alpha.1+4 | `d06d3886cf9813fa256fd0179b27ce2e8d1c8022027878f9a48a83180d5da0e1` |
| [DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-BUILD-INFO.json](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-BUILD-INFO.json) | 300 | 0.4.0-alpha.1 | `2487445a3cf80fae5f9828c7b20fefb93c998c5a5b513b64b0fad235eb23eba4` |
| [DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-NOTICES.txt](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-NOTICES.txt) | 2,607,816 | 0.4.0-alpha.1 | `c9a9aa3b22d84020bf45350656c3b3aa6bef0ee8258d58abc1b047ba1a3a7eb6` |
| [DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-README.txt](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-README.txt) | 1,558 | 0.4.0-alpha.1 | `f1b25e430a394c57a25ab652ebe5f09d92bb6ccb03d24e61aabe9be56ceb8011` |
| [DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64.exe](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64.exe) | 10,078,208 | 0.4.0-alpha.1 | `f4e8fbae68c4fdc3f52c7f9baaeb98f375df26e34dced3dc87c7988d9a4c0617` |
| [DRAGONHYDRA-0.4.0-alpha.1-Server-win-x64.zip](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/DRAGONHYDRA-0.4.0-alpha.1-Server-win-x64.zip) | 19,953,545 | 0.4.0-alpha.1 | `46ced87c0be6500dc75b01797599b57aef92fc91215342e1c54813c1b83d375b` |
| [DRAGONHYDRA-GENESIS-A9-Source.zip](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/DRAGONHYDRA-GENESIS-A9-Source.zip) | 3,000,651 | GENESIS A9 | `13d6eaee8d9ba136fd5ba2174d979f7823a7e117bda44f47163ed9b69ef1fed8` |
| [DRAGONHYDRA-GENESIS-A9-Workstation-win-x64-Setup.exe](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/DRAGONHYDRA-GENESIS-A9-Workstation-win-x64-Setup.exe) | 64,801,813 | 0.4.1-dev.1 | `51950fdd70559f35dadf7161bb511363ebb88faad3a04c913721c283fb5a816a` |
| [GENESIS-A9-RELEASE-NOTES.md](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/GENESIS-A9-RELEASE-NOTES.md) | 6,484 | GENESIS A9 | `f4f60b3b824dfede8491d9c87e4913f3365a5af6a0386439dff7968e1602b6f5` |
| [JOOMLA-FRONTEND-REPORT.md](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/JOOMLA-FRONTEND-REPORT.md) | 16,968 | GENESIS A9 | `46b9470c3a4579be68295a612cc90c631d60bbfa9f3298ec083a55546dcf0ac5` |
| [README-INSTALL.txt](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/README-INSTALL.txt) | 10,560 | GENESIS A9 | `f6fd37409c61f91c602f538d27041a2ee415367d28afcf8fa1cef871bb8aea68` |
| [RELEASE-MANIFEST.json](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/RELEASE-MANIFEST.json) | 25,636 | GENESIS A9 metadata | `9d4dac86133f6303c64bc51256fa03ba2722d331305a9c87e42fcf44ecb4d869` |
| [RUNTIME-BUILD-REPORT.json](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/RUNTIME-BUILD-REPORT.json) | 22,065 | GENESIS A9 | `b7b1e399da7bd96264498acdb227cada875385d1fb301ac2a0eee5107d4c3758` |
| [SHA256SUMS.txt](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/SHA256SUMS.txt) | 2,067 | GENESIS A9 metadata | `c9d932084eef666fad706781ba1f81eca522470e23e5a464354fe3f84d15bfc7` |
| [TEST-REPORT.json](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/TEST-REPORT.json) | 6,727 | GENESIS A9 | `92493764355717bd08e136682f5c67d4eb0bb07e59489c61f2817a3e36fdb786` |
| [WINDOWS-BUILD-REPORT.json](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/WINDOWS-BUILD-REPORT.json) | 16,698 | GENESIS A9 | `70c27dc935f27e03cc7935e09d89be0a5cbe8e99d5eea007ab3ad5a9e81aec5b` |
| [dragonhydra-0.4.0a1-py3-none-any.whl](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/dragonhydra-0.4.0a1-py3-none-any.whl) | 301,616 | 0.4.0a1 | `ddfa346c1c1c915018388f077fa07e82b6c538d00fdbc32d80f9f7464af95792` |
| [dragonhydra-0.4.0a1.tar.gz](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/dragonhydra-0.4.0a1.tar.gz) | 2,046,747 | 0.4.0a1 | `81875f950b6d58caeee46db6b4822cf11421d7154ca624b63da1211ff7be3af4` |
| [dragonhydra-linux-dev-8f170de1559b.tar.gz](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/dragonhydra-linux-dev-8f170de1559b.tar.gz) | 304,065 | GENESIS A7 / Python0.4.0a1 | `a146186c9a1416059fbd6e9978a3da7a62ec8592b8ed9dae6989a04a934ca05a` |
| [pkg_dragonhydra-0.4.1-dev.2.zip](https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/pkg_dragonhydra-0.4.1-dev.2.zip) | 43,686 | 0.4.1-dev.2 | `8b639f154d086af6616d04ddbec40ad280d772577a0e7fba176cb8958c502a49` |

## Build commands and reproducibility

Exact recorded commands/tool versions are in [Windows](WINDOWS-BUILD-REPORT.json),
[Android](ANDROID-BUILD-REPORT.json) and [runtime](RUNTIME-BUILD-REPORT.json) reports.
The release used installed tools and project-local state; no redundant toolchain or
Codex process was installed/launched.

- Joomla: `python scripts/build_joomla.py --output dist/pkg_dragonhydra-0.4.1-dev.2.zip --source-sha 55997de0a3997a10d12c6271795289a5d147e1ab`.
- Windows: `scripts/Build-Workstation.ps1` with `-RepackageOnly`, approved `build/connections/master-release-20261101-workstation` staging, and the verified explicit `-JoomlaPackagePath`. Its complete argument array is in the Windows report.
- Android: `scripts/release_android.ps1` on the clean 4a08 checkout, with explicit source SHA, release version, version code 4, work root and artifact path. Flutter analyze, 14 tests and ARM64 release build ran offline.
- Python: `scripts/release_wheel.py --source-root <clean-S2-export> --work <fresh-work> --assets <release-assets> --build-info <S2-build-info.json> --wheelhouse <verified-existing-cache> --sdist`.
- Source: `git archive --format=zip --prefix=DRAGONHYDRA-GENESIS-A9/ --output=<Source.zip> 2e6520d5b6a7874881e5de85dbb6ececaef11d8f`.
- Manifest: `scripts/master_release_manifest.py --assets <release-assets> --source-sha 2e6520d5b6a7874881e5de85dbb6ececaef11d8f --metadata-source-sha 981f7c94a21964d7db0eeb08f9403ca8f2b12dd9`.
- Full public verification: `scripts/verify_master_publication.py --assets <release-assets> --source-sha 2e6520d5b6a7874881e5de85dbb6ececaef11d8f --before <releases-before.json> --downloads <fresh-owned-directory> --output <fresh-receipt.json>`.

Frozen server and Linux archives were reused only after scoped source equality;
neither was needlessly rebuilt. The public Python dependency lock now survives Git,
source staging and sdist packaging. The Windows redirector PID harness now proves
owned ancestry while preserving POSIX exact-PID checks. Four focused regressions
cover these repairs. Earlier failed receipts remain local and are labeled as harness
or packaging failures rather than application runtime failures.

## Acceptance and preservation

The new installer upgraded only the isolated `DragonhydraGenesisA8Test` installation:
Joomla 18750, API 18749, MariaDB 18751. Installer exit 0 and six guards passed, followed
by six real HTTP checks: separate Site/admin login, CSRF/cookies, session navigation,
native homepage and a real retained match through Joomla. All 760 records, representative
match/version, pairing, Joomla configuration and ports persisted. Its owning service
changed from PID 17012 to 29480 during upgrade. The other three services retained
PIDs 12904/23500/39364 and all four remained Running as LocalService.

The primary Joomla 18740/API 18744 association remains unchanged. Its earlier 17 frontend
requirements include 760 matches, 40 source-scoped teams, two competitions, search,
filters, pagination, entities, existing analysis and actual JSON/CSV/XLSX downloads.
The initial external-document timeout is preserved with a successful hash-linked
continuation; provider-link handoff does not claim provider website uptime.

| Check | Status | Evidence / observed behavior |
|---|---|---|
| FRONTEND_MENU | PASS | 55 menus: only owned Home 142 native-default normalization; unrelated menus/articles preserved;7negative regressions; repeated deployment idempotent |
| FRONTEND_ACCEPTANCE | PASS | 17required criteria; actual site/admin sessions,760matches,40teams,2competitions; JSON/CSV/XLSX;7isolated states. Earlier raw external timeout is preserved with successful hash-linked continuation. |
| REGRESSION | PASS | 47focused tests: Joomla packaging/model/setup/templates/transport/menu plus4runtime-packaging/PID regressions; command exit 0 |
| WINDOWS_PAYLOAD | PASS | 10662payload paths; critical9extracted entries match; unchanged A8 desktop/A6 server; new Joomla extension/hook verified |
| WINDOWS_UPGRADE | PASS | Full installer exit 0,6guards;760records+representative version/pairing/config/ports retained;3protectedPIDsunchanged |
| WINDOWS_JOOMLA_HTTP | PASS | 6checks: real site/admin login,CSRF,cookies,sessionnavigation,newhome,realretainedbackendmatch |
| WINDOWS_NEW_NATIVE_UI | NOT_RUN | Unchanged client f4e8... retains earlier A8 native links/pairing evidence; no new UI input after user stop |
| WINDOWS_CLEAN_MACHINE_REBOOT | NOT_RUN | Current-host isolated upgrade is not clean-machine or OS-reboot acceptance |
| ANDROID_BUILD | PASS | Fresh ARM64 release-optimized APK from4a08; analyze0issues,14tests,APKmetadata/ABI/signature verified |
| ANDROID_INSTALL_LAUNCH | PASS | Fresh owned emulator install Success,coldlaunch Statusok,nativeHome rendered;API 37 x86_64withARM64translation |
| ANDROID_CONNECTED_PAIRING | BLOCKED | User stopped nativeUI with Escape; no further input or secretentry; connecteddata/upgrade/persistence NOT_RUN |
| ANDROID_PRODUCTION_SIGNING | BLOCKED | Five existing publisher-keystore/certificate inputs unavailable; APK explicitly establisheddevelopment signed |
| WINDOWS_SERVER | PASS | Immutable710filepayload rehashed; actual portableEXE fresh6groups and retained-state restart5groups;760matches/XLSX/normalexit 0 |
| PYTHON_WHEEL_SDIST | PASS | Offline freshisolatedinstall/CLI/API4groups; fresh760import+restart7groups; sdist rebuild byte-identicalwheel;publiclockincluded |
| LINUX_ARTIFACT_INTEGRITY | PASS | ExactimmutableA7archive+61 productfiles byte-identical current; earlier Docker12retained+7fresh evidence retained |
| LINUX_NEW_NATIVE_ACCEPTANCE | NOT_RUN | No new A9Linuxbuild/runtime or nativeWSL/desktop/systemd/reboot claim |
| FULL_INSTALLER_CONTENTS | PASS | All10662manifested payload members rehashed after full NSIS extraction |
| PREPUBLICATION_PRIVACY | PASS | 21known privatevalues,10692files,3475decompressedarchive members,zero matches; actual tagged source/metadata finalscan follows |
| FINAL_PUBLICATION | PASS |21 current assets; remote names/sizes/digests and anonymous public bytes verified.|
| AUTOMATIC_SOURCE | PASS |Both GitHub ZIP and tar contain exactly672 tagged Git blobs.|
| HISTORICAL_PRESERVATION | PASS |All 8 earlier releases and 59 assets retain IDs, names, sizes and digests.|

Consistent pre-upgrade SQL/config/component backup:
`build/master-release-20261101/private-a8-backup`, restricted to owner/SYSTEM/Admin.
Rollback uses the preserved A8 installer and original service/paths; stop only that
profile through its owning controller before restoring scoped Joomla SQL/files.
Preserve sports/pairing state. No rollback was needed. Secret-bearing backups are
local only. Historical Setup/staging and independent working-tree changes remain.

## GitHub verification

Initial publication verification downloaded **all 21 assets** anonymously and rehashed
them, then downloaded both automatic source formats and compared their contents to
Git. After metadata clarification, the three changed metadata files were freshly
downloaded; 18 unchanged assets were rehashed against their prior public downloads,
unchanged remote IDs and digests. All current names/sizes/SHA256s were checked again.
No binary was downloaded again solely for a documentation correction.

Receipts:

- `docs/handover/verified-reports/GENESIS-A9-PUBLIC-DOWNLOADS-R1.json`
- `docs/handover/verified-reports/GENESIS-A9-PUBLICATION-VERIFICATION.json`
- `docs/handover/verified-reports/GENESIS-A9-FINAL-PRIVACY.json`
- `docs/handover/verified-reports/GENESIS-A9-COMPONENT-SOURCE-EQUALITY.json`
- `docs/handover/verified-reports/GENESIS-A9-SERVICES-FINAL.json`

The final known-value scan compared 21 private values across source, 10,692 files and
3,480 decompressed archive members, including the full NSIS payload: zero matches.
Previously inspected sanitized screenshots are reused. This is not a claim of
universal secret detection. No passwords, tokens, private databases or signing keys
are distributed. Source archives are exact tag snapshots; automatic-archive observed
hashes are in the first verification receipt, with Git content identity authoritative.

## Limitations and next objectives

- Android uses the established development certificate. Five publisher signing
  inputs are unavailable. Fresh emulator install/cold Home passed on API 37 x86_64
  with ARM64 translation; physical ARM64 acceptance is unverified.
- The user stopped native UI with Escape. Pairing is BLOCKED; connected mobile
  navigation, upgrade and restart/persistence were NOT_RUN. No further UI input or
  emulator shutdown was attempted. Resume only with renewed authorization.
- Windows is unsigned. Current-host isolated upgrade is verified; clean-machine,
  absent-prerequisite, OS-reboot and new native-client UI acceptance are not.
- Linux evidence is historical isolated Docker. No new A9 native WSL, R8, desktop,
  systemd/reboot or production Linux deployment is claimed.
- No paid/live-provider or language-model production claim. Statistical forecasts
  remain separate from results and honest about unavailable/uncalibrated outputs.
- Formal screen-reader/main-landmark and broader accessibility acceptance is pending.

Next release-engineering objective: an explicitly owned clean Windows target and
publisher signing inputs, then authorized Android connected-session acceptance.
Do not reinstall the primary Joomla site,rotate credentials, repoint profiles or
rebuild unchanged components to repeat completed checks.
