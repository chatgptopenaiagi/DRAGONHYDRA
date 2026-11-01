# GENESIS A8 Windows workstation — verified installation and runtime

The complete Windows installer was built, installed as a guarded upgrade in an
isolated Windows 11 x64 profile, executed through its official shortcut, and
verified through native navigation, browser links, exports and persistence.
This is local delivery evidence; no new GitHub release is claimed.

The objective is one complete Windows workstation installer with the repaired
Tauri desktop, automatic pairing to its corresponding installed local server,
all supported provider web links, and retained sports-data workflows. This
increment reuses the verified Windows components and does not produce another
Linux release. The previous desktop checkpoint is
`9cbaa79c3514c3fcaf47c8247b093c2298bebd63`.

## Source and components

The new desktop source checkpoint is
`5821b4d54a199f73ccd943215117dcfa8e38ea4b`; its scoped source-content SHA-256 is
`2c6b0607cf7d1638787f6858a29258eac1a8bd89b20c437afcba8e8ee9beeae4`.
The new 10,078,208-byte desktop executable is
`build/connections/genesis-a8-client/DRAGONHYDRA-Client.exe`, SHA-256
`f4e8fbae68c4fdc3f52c7f9baaeb98f375df26e34dced3dc87c7988d9a4c0617`.
Its actual `BUILD-INFO.json` records those identities.

| Component | Selected existing implementation |
|---|---|
| Desktop | Tauri 2.12.5, official opener 2.7.2, Windows WebView2; Rust 1.99.1 build toolchain. |
| Python API/worker | Frozen A6 private Python runtime, `/dragon/api/v1`, existing SQLite sports-data authority. All 711 packaged server files remain byte-identical to the verified A6 payload; final contents and source bindings are recorded in the build report. |
| Server EXE | Existing SHA-256 `6960835b332728672183b2953c4003119ed743a721793dd6e21a7b66181607fc`; source-content identity `886161d0a8c4f0bf3364fd6d0a9966630398bba6bfe27b84de9c5999a307acd4`. |
| Web stack | Private Apache 2.4.65, PHP 8.4.27 TS VS17 x64, MariaDB 10.11.16; versions are from the bundled web payload manifest, not the host's separate XAMPP installation. |
| Joomla | Joomla 6.2.0 with the existing DRAGONHYDRA 0.4.0-alpha.1 extension; MariaDB is its administration database. |
| Service/launcher | Existing `DragonhydraService.exe`, `DragonhydraLauncher.exe`, workstation scripts and configuration templates. |
| OS prerequisites | Build declares AMD64 Windows 10 or later and .NET Framework 4.8. This acceptance target is the current Windows 11 x64 workstation. Existing WebView2 is reused; the official Microsoft bootstrapper needs internet if that runtime is absent. |

The unified installer's declared component version remains `0.4.1-dev.1`
(Windows file version `0.4.1.1`); desktop/API declarations remain
`0.4.0-alpha.1`. GENESIS A8 identifies the verified engineering increment and
delivery filename, rather than inventing a synchronized new version for reused
components. Build/source manifests distinguish the new desktop from the frozen
server, web stack and wrapper.

## Pairing diagnosis and repair

The official workstation shortcut was already bound correctly: it targets that
installation's native launcher and passes its exact state directory. The
launcher waits for the local services to report ready, then passes the public
`client` pairing-metadata directory to the desktop. Neither shortcut nor
launcher needs a hard-coded port.

The standalone desktop's default differed: it searched
`C:\ProgramData\DRAGONHYDRA` itself, where `endpoint.json` and
`local-session.json` were absent. Both files existed under its `client`
subdirectory. This explains the manual connection screen when launching the
bare EXE outside the official path. Read-only discovery observed the default
profile at API port 18743 and the prior A6 test profile at 18746. Port 18744 was
historical and was not treated as the current production endpoint.

`src/client_state.rs` now preserves explicit `--state` arguments, resolves an
installed bare EXE through its own matching sibling `workstation/installer.ini`,
and uses the public `ProgramData/DRAGONHYDRA/client` directory for the portable
default. Installed binding checks identity, absolute paths and canonical
installation-root equality. Invalid or mismatched metadata does not silently
select another workstation. Windows INI decoding matches NSIS, including Unicode
state paths. Discovery creates no token or replacement authentication state.

Seven actual native Rust regression scenarios passed through
`tests/test_desktop_pairing.py`. Evidence and public shortcut bindings are in
`build/connections/a8-pairing-20261101/PAIRING-DIAGNOSIS.json`.

## External browser handling

The prior verified repair remains in place: the official opener handles normal
HTTP(S) anchor clicks, scoped to the main window's loopback dashboard. The
earlier 22 regressions and three installed provider-link tests are historical
checkpoint evidence, not a new A8 full-suite count. That repair did not change
the backend or API-key vault.

A8 additionally reproduced an uncovered programmatic popup path. The
Administration button calls `window.open` after reading the server's public
administration URL; it does not create the anchor click that the opener's
injected handler observes. With the previous desktop EXE, a real click against
the isolated A8 API at 18749 produced no matching default-browser window for
`http://127.0.0.1:18750/administrator/`, while the application remained open.

The new desktop uses Tauri's supported `on_new_window` callback and the official
Rust opener. It accepts only the trusted local source and credential-free HTTPS
targets or loopback HTTP administration targets, and always denies creation of
an application popup. `src/external_target.rs` rejects non-web schemes, embedded
credentials and known token/API-key/password query or fragment keys, including
percent-encoded key names. Three native predicate regressions passed through
`tests/test_desktop_popup.py`.

The exact new desktop EXE was executed against the isolated API. Clicking its
actual Administration control changed registered default Edge to
`DRAGONHYDRA - Administration`, with the expected loopback URL and unchanged
DRAGONHYDRA page; the application stayed alive. Negative and positive receipts
are `admin-probe-r1/verification.json` and `admin-probe-r2/verification.json` under
`build/connections/a8-pairing-20261101`. Their legacy generic probe label is not
the build identity: each receipt records the actual tested executable hash.

The final installed client passed all ten current Connections catalog links:
API-FOOTBALL, The Odds API, Sportmonks, football-data.org, Football-Data.co.uk,
OpenFootball, StatsBomb, nflverse, MoneyPuck and Cricsheet. These existing HTTPS
provider/documentation destinations were retained. Each real native click was
intercepted by the official opener, reached the registered default Edge browser
with a matching site title, and left DRAGONHYDRA open on the same page. Locally
stored API credentials were not appended to these URLs. No provider-account
creation, paid API acquisition or replacement provider key was needed.

## Isolated Windows installation and runtime evidence

The existing complete Windows Setup was first rehashed as 64,757,781 bytes,
SHA-256 `0f3a4aa6bcedfd29d37cb790f61d466e98e6a62a235af6b945055f28db83e135`.
It was installed once into a new authorized current-host profile:

```text
Install: C:\xampp\DRAGONHYDRA\build\workstation\test-install\genesis-a8\application files
State:   C:\xampp\DRAGONHYDRA\build\workstation\test-install\genesis-a8\state data
Service: DragonhydraGenesisA8Test
API:     http://127.0.0.1:18749
Joomla:  http://127.0.0.1:18750
DB port: 18751 (loopback)
```

These bindings were read from this installation's configuration and runtime;
they are observations rather than proposed production defaults. Existing
workstations retain separate identities, state and services.

| Executed phase | Actual result and scope |
|---|---|
| Initial complete Setup | Installer exit 0. The initial verification helper then failed trying to read the LocalService-owned kernel pairing file. The raw receipt remains `passed=false`; the installer itself had completed successfully. |
| Corrected read-only verification | Four groups passed using owner-readable client pairing metadata: API ready, Joomla HTTP 200, private MariaDB/service ownership, 760 retained records, corresponding shortcut bindings and preservation of the three existing services. No ACL takeover or credential rotation. |
| Official shortcut smoke | Two groups passed by actually executing the installed `.lnk`, native launcher and initial installed desktop `557837...1b84f`; automatic pairing reached the local dashboard and 760 records. |
| Rebuilt client pre-upgrade smoke | Two groups passed on exact new `f4e8...c0617` EXE using explicit client-state arguments; distinct from the later official-shortcut acceptance below. |
| Administration popup | New exact desktop passed the real default-browser handoff described above. |
| Final whole-installer upgrade | Six groups passed, installer exit 0, preserving 760 records, evidence identities, the existing pairing token, Joomla configuration, allocated ports and the three unrelated services. |
| Final installed native journey | Twenty groups passed through the actual official shortcut, including two application launches, dashboard, match/team browsing, 20-team standings, structured analysis, a deterministic explanation job, three export formats and all ten provider links. |
| Bare installed EXE and Administration | Three groups passed without state arguments: it resolved its own installed profile, automatically paired and opened the corresponding Joomla administrator in default Edge. |
| Owned-service restart | Six groups passed after stopping/starting only `DragonhydraGenesisA8Test`; records, pairing, Joomla configuration, ports and unrelated services stayed intact. |
| Post-service native persistence | Two groups passed through the official shortcut; all 760 match presentations, settings/pairing and three durable export jobs/files were revalidated. |

Receipts are under `build/workstation/evidence/genesis-a8/`:
`candidate-install-r1.json`, `candidate-verify-r1.json`,
`candidate-shortcut-smoke-r1/verification.json`, and
`new-client-smoke-r1/verification.json`. The failed kernel-token read is a helper
permission mistake, not evidence of a broken installed service. Its corrected
successor is retained separately.

## Final artifact and delivery

The selected final installer bytes are:

```text
File:   DRAGONHYDRA-GENESIS-A8-Windows-x64-Setup.exe
Bytes:  64769361
SHA256: 27b7b310fe78baeea76275cfc53ddacc254c99c60e7dcc641f813692398846fa
```

The tested candidate is
`dist/connections/genesis-a8-candidate/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe`.
The final delivery location is
`C:\xampp\DRAGONHYDRA\dist\windows\GENESIS-A8\DRAGONHYDRA-GENESIS-A8-Windows-x64-Setup.exe`;
the A8 delivery filename selects the exact installed and tested bytes rather
than rebuilding or relabeling an untested payload. The five-file delivery is:

```text
DRAGONHYDRA-GENESIS-A8-Windows-x64-Setup.exe
SHA256SUMS.txt
BUILD-REPORT.json
TEST-REPORT.json
README-INSTALL.txt
```

The final Setup was installed before promotion through the isolated profile's
validated upgrade path. Final source, payload and installer hashes belong to
`BUILD-REPORT.json`; executed acceptance receipts and their limits belong to
`TEST-REPORT.json`. Resolve the later preservation checkpoint from Git and
`ENGINEERING-STATE.json`; the embedded desktop source remains `5821b4d`.

The complete final receipts under `build/workstation/evidence/genesis-a8/` are:

- `final-upgrade-r1.json`: six passing groups, full installer exit 0.
- `final-native-full-r2/verification.json`: twenty passing native groups.
- `final-bare-client-r1/verification.json`: three passing bare-EXE/popup groups.
- `final-service-restart-r1.json`: six passing owned-service restart groups.
- `final-post-service-persistence-r1/verification.json`: two passing native
  persistence groups after that service restart.

The final native journey generated actual XLSX, JSON and CSV files, verified
their bytes/hashes and retained their durable jobs across application and
service restart. The Excel control was exercised natively; JSON/CSV downloads
were authenticated requests from the actual native page. This does not claim
automation of the Windows SaveAs dialog. The selected finished match correctly
returned a structured abstention: no prospective forecast had been retained.
The deterministic analysis job and 20-team standings worked; no new predictive
performance or future-match forecast is claimed.

The private test service now runs as `DragonhydraGenesisA8Test`, observed PID
17012 after its authorized restart. Its API/Joomla/database bindings remain
18749/18750/18751 on loopback. The other three service PIDs stayed unchanged
through these operations: provider-a2 23500, default 39364 and original test
22876. Those values are observations for this acceptance, not future process
ownership guarantees.

The initial kernel-token read failure remains preserved alongside the corrected
owner-readable verifier. The first full native journey also exposed a helper
pagination-selection mistake; its failed receipt was retained and the corrected
`final-native-full-r2` passed. These helper failures did not require additional
application changes. The two A8 application repairs are deterministic pairing
selection and native handling of programmatic web popups. Earlier A6/A7
installers/releases, user data and independent workstations remain preserved.

This is an isolated installation on the current Windows 11 x64 development
workstation. Clean-machine, OS reboot and publisher-signing acceptance remain
separate. Setup is an unsigned development build. The declared Windows 10+
minimum and missing-WebView bootstrap strategy are distinct from the observed
Windows 11/current-WebView workload. Private databases, browser profiles, pairing
files, provider keys and Joomla administration credentials are excluded from
delivery reports. A separate actual read-only probe against this installation's
private MariaDB at loopback port 18751 reported version 10.11.16 and returned
42 from the read-only `SELECT VERSION(), 6*7, DATABASE()` probe. That scoped SQL execution does not change the sports-data
authority: the application continues to use its existing SQLite backend.

Final focused regression receipt: `verified-reports/GENESIS-A8-REGRESSION-VERIFICATION.json`.
Five Python wrappers passed: seven native pairing cases, three native popup policy
cases and three JavaScript tests covering all ten current provider destinations.
The delivery checksum/snapshot inventory is `verified-reports/GENESIS-A8-DELIVERY-MANIFEST.json`.
