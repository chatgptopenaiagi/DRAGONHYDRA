# DRAGONHYDRA GENESIS A9 release report

GENESIS A9 is an unsigned/development **prerelease**, tag `genesis-a9-20261101`.
Release: https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/tag/genesis-a9-20261101

This source checkpoint records completed local assembly/acceptance. Publication is
pending at this checkpoint; the coordinator will append the independently retrieved
GitHub verification receipt after publication. Resolve the annotated tag for the
exact complete-source commit. Artifact provenance is intentionally independent.

## Frontend checkpoint

`site_menus_same=false` was explained and tested before release assembly. Only Home142
parameters changed through Joomla native-default normalization: ten default fields
were added and an unused migration marker removed. Visible owned fields, all other
menu rows, original Home101,11articles and48modules stayed intact;55menus total.
Seven semantic regressions reject real/unrelated/unknown changes. Repeat deployment
remains idempotent. See `JOOMLA-FRONTEND-REPORT.md` and its menu-semantics receipt.
Frontend source/package:55997de0a3997a10d12c6271795289a5d147e1ab; preservation checkpoint
4a08f873429e338d30031be321a0c63ccfe196a7.

## Source and architecture

Release source is the existing continuity branch, not the separate historical `main`
tree. The final tag identifies its exact source archive. No historical release/tag
is replaced. Large packages remain Release assets, not normal Git objects.

Joomla/Apache/PHP owns accounts,presentation and MariaDB; its protected HMAC bridge
connects to the associated Python service. SQLite remains authoritative sports
storage. Desktop/mobile use their own local pairing and endpoint workflow. Provider
keys and Joomla passwords never substitute for bridge/pairing authentication.

## Packages and provenance

| Package | Version / source | Actual verification |
|---|---|---|
| Unified Windows Setup |0.4.1-dev.1;packaging4a08f87,desktop5821b4d,Joomla55997de,A6servercontent886161d0...|10662entries;fullisolatedupgrade exit0,6guards +6authenticated JoomlaHTTPchecks;760retained|
| Standalone Windows desktop |0.4.0-alpha.1;5821b4d54a199f73ccd943215117dcfa8e38ea4b|Exact earlier A8binary; native links/pairing historical proof,not newA9UI|
| Android ARM64 APK |0.4.0-alpha.1+4;4a08f873429e338d30031be321a0c63ccfe196a7|Freshbuild/analyze/14tests/signature/install/coldlaunch/Home; connectedpairing BLOCKEDuserUIstop|
| Joomla package |0.4.1-dev.2;55997de0a3997a10d12c6271795289a5d147e1ab|Installedprimary/reappliedidempotently;17frontendrequirements;newisolatedinstallerprofileHTTP|
| Frozen Windows server ZIP |0.4.0-alpha.1; originalcontent-addressedA6snapshot|710payloadfiles rehashed;fresh6+restart5groups;61productfilesmatchcurrent|
| Python wheel + sdist |0.4.0a1;46ba85c091230213189ffed679294b80019841a2|Freshisolatedofflineinstall/CLI/API4groups;fresh+restart7groups;sdistrebuildbyte-identicalwheel|
| Linux archive |A7,source2ca96e94213cc6f516b6963052ef68ff1948af94|Exactimmutable304065Barchive;61productfilesmatch;earlierDocker12+7groups,no newLinuxrun|
| Complete source ZIP / GitHub source |Exactannotatedtagcommit|Gitarchive,snapshot/contentverification;private-stateexclusion|

All package filenames,sizes,SHA256s,dependencies,installation methods,source IDs,
build configurations and limits are in downloadable `RELEASE-MANIFEST.json` and
`SHA256SUMS.txt`. Component versions were not renamed merely to match A9.

Windows Setup:64,801,813 bytes; SHA256
`51950fdd70559f35dadf7161bb511363ebb88faad3a04c913721c283fb5a816a`.
Joomla ZIP:43,686 bytes; SHA256
`8b639f154d086af6616d04ddbec40ad280d772577a0e7fba176cb8958c502a49`.
Android APK:17,345,938 bytes; SHA256
`d06d3886cf9813fa256fd0179b27ce2e8d1c8022027878f9a48a83180d5da0e1`.

## Build and test evidence

Exact commands/tool versions/results are preserved in `WINDOWS-BUILD-REPORT.json`,
`ANDROID-BUILD-REPORT.json`,`RUNTIME-BUILD-REPORT.json` and `GENESIS-A9-TEST-REPORT.json`.
Reproduce with the existing source-locked platform scripts: `Build-Workstation.ps1`
with approved staging and explicit verified Joomla ZIP, `release_android.ps1` on a
cleancheckout, `release_wheel.py --sdist --wheelhouse <existing-cache>` with exact
build_info/source, and `build_joomla.py --source-sha <commit>`. Frozen server/Linux
payloads were reused after scoped source equality; neither was needlessly rebuilt.

47focused regression tests passed. The public dependency lock now survives Git,
source staging and sdist packaging. An initial Windows PID harness failure was
reproduced and repaired with owned descendant checks; Linux exactPID behavior stays.
Earlier raw failed receipts remain; they are not silently rewritten.

## Installation/data preservation

The new Setup upgraded only `DragonhydraGenesisA8Test` at the existing isolated
A8profile (Joomla18750/API18749/database18751). Owner/admin sessions genuinely
signed in; the native homepage displayed the representative retained backend match.
760records,pairing,Joomlaconfiguration andports persisted. The owning service restarted
as part of this installer upgrade; the three protected otherservicePIDs stayed
unchanged. Primary Joomla18740 remains paired with API18744. No mixedprofiletokens.

Consistent SQL/config/component backup before upgrade:
`build/master-release-20261101/private-a8-backup` (restricted owner/SYSTEM/Admin ACL).
Rollback: use the preserved A8installer and original paths/service; through its
owning controller stop only thatprofile before restoring its scoped Joomla SQL/files.
Keep sports/pairing state; no rollback was applied. Existing A8Setup/staging and all
historical releases are preserved. No secret-bearing backup is distributed.

## Security and limits

Private runtime state,DPAPI/passwords,tokens,providerkeys and publisherkeys stay out
of assets/source. Known-value scanning recursively inspects archives and the complete
NSIS payload; previously sanitized real screenshots are reused. This does not claim
universal secret detection. Final receipts record its actual outcome before upload.

Android uses its established development certificate,not a production publisher.
Five required production-signing inputs are unavailable. Pairing/data/upgrade/restart
remain unverified after the user stopped UI; no further UI input was attempted.
Windows is unsigned; clean-machine,OSreboot and newnativeUI acceptance remainunrun.
Linux evidence is historical Docker,not nativeWSL/desktop/systemd/reboot. No livepaid
provider or language-model production claim. Screen-reader/main-landmark audit is
pending. Statistical predictions remain separated from results and unavailable
outputs stay explicit.

## Remaining objectives

1. Resume Android connected-session acceptance only with renewed UI authorization.
2. Provide authorized publisher signing inputs; do not create substitute identities.
3. Verify exact WindowsSetup on a separately authorized cleanmachine andOSreboot.
4. Scope frontend screen-reader/main-landmark and broader accessibility review.
5. Verify native Linux ownership/runtime only when its isolated environment is available.
