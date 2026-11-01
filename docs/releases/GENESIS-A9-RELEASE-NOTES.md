# DRAGONHYDRA GENESIS A9

Development prerelease combining the native Joomla sports workspace, repaired
Windows desktop and complete Windows workstation Setup with separately identified
server, Android, Python and Linux-preparation artifacts. The milestone name does
not overwrite component versions or imply that every platform has the same source
commit or operational readiness.

| Component | Declared version | Provenance and verification scope |
|---|---|---|
| Windows workstation Setup | Product0.4.1-dev.1 / file0.4.1.1 | New unified package assembled from checkpoint4a08f873429e338d30031be321a0c63ccfe196a7 packaging inputs, exact A8 desktop and A6 server, plus frontend package0.4.1-dev.2. Build/archive verification, guarded isolated A8 upgrade6 and genuine Site/administrator HTTP6 checks passed;760records preserved. Unsigned; no clean-machine, new native-desktop UI rerun or OS-reboot claim. |
| Windows desktop | 0.4.0-alpha.1 | Exact A8 repair binary, source5821b4d54a199f73ccd943215117dcfa8e38ea4b; official Tauri opener and installed-profile pairing retained. Copied without rebuilding or changing its internal version. |
| Windows server | 0.4.0-alpha.1 | Reused complete A6 private-runtime payload, source-content886161d0a8c4f0bf3364fd6d0a9966630398bba6bfe27b84de9c5999a307acd4; not relabeled internally. Fresh current-host portable-server acceptance and retained-state restart passed. |
| Joomla | 0.4.1-dev.2 | Package source55997de0a3997a10d12c6271795289a5d147e1ab; native frontend plus preserved administrator component and Cassiopeia child template. Genuine Site/admin authentication, retained data, exports, responsive views and isolated failure states verified in the primary installation. |
| Android | 0.4.0-alpha.1 / version code4 | Built from4a08f873429e338d30031be321a0c63ccfe196a7, ARM64 release-optimized/non-debuggable, established development signer. Analyze/14 tests, fresh test-AVD installation, cold launch and native Home passed. Pairing and subsequent connected-data/restart/upgrade acceptance remain unverified after the native UI test was stopped. |
| Python wheel and sdist | 0.4.0a1 | New source checkpoint46ba85c091230213189ffed679294b80019841a2 includes packaging-lock/README corrections. Exact hashes and final fresh-environment runtime scopes are recorded in their build/test reports. Python3.14 required. |
| Linux preparation | GENESIS A7 / Python0.4.0a1 | Preserved `dragonhydra-linux-dev-8f170de1559b.tar.gz` bytes and original embedded wheel. Earlier isolated Linux Docker runtime proof only; no new native Linux desktop, WSL, systemd, reboot or production-deployment claim. |

The annotated `genesis-a9-20261101` tag and release manifest identify the final
preservation checkpoint. Artifact source identities above remain independent;
later report/tag commits do not rewrite the provenance embedded in reused binaries.

The Windows Setup is **64,801,813 bytes**, SHA-256:

```text
51950fdd70559f35dadf7161bb511363ebb88faad3a04c913721c283fb5a816a
```

Only four staged files differ from the verified A8 baseline: the Joomla extension
ZIP, provisioning hook, private web-payload manifest and workstation build metadata.
All 10,662 payload paths remain, the client/server binaries are unchanged, and nine
critical archive entries were independently extracted and compared with staging.
The existing A8 Setup and stage manifest remain unchanged. No Python server or
desktop rebuild was performed for this unified package.

The Joomla homepage is now the actual `com_dragonhydra` workspace. It presents
retained matches, teams, competitions, supported analysis, exports and provider
status through the existing server-side bridge. Anonymous users receive a branded
sign-in shell; private information requires the real Joomla Site session and
permissions. Administrator and frontend sessions are verified separately. The
administrator component remains available, provider synchronization/model calls
are not triggered by browsing, and unsupported predictions are explicitly unavailable.
Provider status and registration/documentation links are available in Joomla;
API-key editing remains in the existing desktop/dashboard Connections vault,
not a newly implemented Joomla provider-key form.

Home/template/module setup is idempotent. Original articles/menu records and
other-page module behavior are preserved. Joomla core/vendor files remain intact,
sports data stays in the existing Python authority, and no private database or
credential is distributed. Existing administrator credentials, local pairing,
HMAC bridge authentication and provider keys remain separate protected mechanisms;
normal rotation requires no source edits or application rebuild.

Use `README-INSTALL.txt` for platform-specific installation. The complete Windows
Setup is the route for a local service, Python runtime, Joomla and private web/DB
stack; the standalone desktop EXE is only the client, and the portable server ZIP
must be extracted completely with its `_internal` directory. Windows loopback
ports are selected per installation, not copied from the demonstrated test profiles.
WebView2 installation requires internet only if that runtime is absent.

Android is **development signed, not production-publisher signed**. A fresh
authorized test-AVD launch is proven; mobile pairing, retained backend navigation
and persistence are not. No new signing identity, token, emulator profile or
public service endpoint is created by these release files. Physical devices need
their supported authorized connection path; installing an APK does not expose a
Windows loopback server.

The preserved Linux archive intentionally contains its earlier wheel. Its filename
version matches the separately built A9 wheel, but their bytes/source identities
are different. Use each archive's own instructions and hash rather than silently
substituting one for another. Earlier Docker server checks are not proof of native
Ubuntu/R8 ownership, host-browser behavior or service/reboot recovery.

`RELEASE-MANIFEST.json`, `SHA256SUMS.txt`, the platform build reports and
`TEST-REPORT.json` provide exact filenames, sources, commands/results and remaining
limits. Publication is established by the coordinator's separate GitHub verification
receipt, not by the existence of these local release notes. Historical releases,
private user state and independently managed services are preserved.
