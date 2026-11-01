# Windows desktop external-link repair — 2026-11-01

The original installed Windows client silently ignored provider registration
links. The repaired native client opens those same URLs in the registered
Windows default browser while retaining the DRAGONHYDRA Connections view.
This report distinguishes the rebuilt executable's actual execution from
replacement of a protected installed executable.

Source checkpoint: `391150787611433d9ad6d665fc52269214cd4637`.
Embedded desktop source-content SHA-256:
`64df2084eabfe0ae35a1551e0969603ad15f4b7b6b9d8799368fcd3d2f728d94`.
Later evidence/packaging commits must be resolved from Git and the aggregate
receipt; the embedded build identity describes these exact compiled inputs.

## Cause and correction

The desktop is Tauri 2.12.5 using Windows WebView2. Its shared dashboard already
created valid HTTP(S) links with `target="_blank"` and `rel="noopener noreferrer"`.
The original native builder registered neither an external opener nor a
new-window handler. Cached Wry 0.57.1's WebView2 new-window implementation marks
an unhandled request handled, producing the observed no-op. The original client
never dispatched a request to the Windows browser; this was not a broken API
key, provider configuration, or Windows URL association.

The correction registers the official pinned `tauri-plugin-opener = 2.7.2`.
Its supplied click handler sends `_blank` web links through Tauri's supported
default-application URL opener. A named capability grants only
`opener:allow-open-url` for HTTP(S), from the `main` window's paired
`http://127.0.0.1:*` dashboard. It grants no file opening, arbitrary application,
shell command, or unrelated remote-page permission. See the
[official opener documentation](https://tauri.app/plugin/opener/).

The shared dashboard `app.js`, Python backend, API contracts, vault and provider
settings were not changed. Existing provider URL values were preserved.

## Changed files

- Native client: `client/desktop/src-tauri/Cargo.toml`, `Cargo.lock`,
  `src/main.rs`, `tauri.conf.json`, and `capabilities/external-browser.json`.
- Third-party attribution: `client/desktop/THIRD-PARTY-OPENER-NOTICES.txt`.
- Guarded installer packaging: `scripts/Build-Workstation.ps1` and
  `packaging/windows/workstation/ClientBuild.ps1` permit an explicitly verified
  replacement client in new staging while retaining the frozen A6 server.
- Guarded installed repair: `scripts/Repair-InstalledDesktopClient.ps1` applies
  the verified client and inventory metadata with backups and rollback guards.
- Regression and native acceptance: `tests/test_desktop_external_links.py`,
  `tests/test_workstation_client_override.py`, and
  `tests/test_installed_desktop_client_repair.py`, plus
  `tests/installation/desktop_external_links.py`.

Generated Tauri capability schemas are build output associated with the new
permission. Their preservation status is recorded by the final checkpoint.

## Executed verification

The same final native acceptance helper exercised the original installed client
bytes and the repaired executable in separate byte-exact copies, against the
existing installed A6 server on loopback port 18746. Each copy used a private
WebView2 profile and an owned loopback CDP listener. This was the real native
Tauri/WebView2 client, not a substitute browser or mocked Windows shell.

| Provider | Exact clicked URL | Repaired browser receipt |
|---|---|---|
| API-FOOTBALL / API-SPORTS | `https://www.api-football.com/documentation_v3` | Registered default Edge window changed to API-Football documentation. |
| The Odds API | `https://the-odds-api.com/liveapi/guides/v4/` | Same default Edge window changed to Odds API Documentation V4. |
| Sportmonks | `https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures` | Same default Edge window changed to Fixtures / API 3.0. |

Original negative receipt: `original-r3/verification.json` under
`build/connections/external-links-20261101/evidence/`. All three real anchor
clicks lacked the opener handler, were not intercepted for native opening, and
left the default browser's matching window titles unchanged. Original EXE
SHA-256: `17b557c7a4f2524ace5769c3bace55583ce695a0f250771a3585ce954688f94b`.

Repaired positive receipt: `fixed-r4/verification.json` in the same evidence
root. All three real clicks were intercepted by the actual shipped opener
handler and produced matching provider titles in registered default Edge
(`MSEdgeHTM`, `msedge.exe`, HWND 525844). DRAGONHYDRA remained alive at
`http://127.0.0.1:18746/#connections` after each click. Connection settings hash,
provider record counts, endpoint and pairing metadata stayed unchanged; no
provider retrieval, credential write, model request or service control occurred.

The coordinator additionally inspected the actual Edge address bar for
API-FOOTBALL and observed
`https://www.api-football.com/documentation_v3#section/Introduction`.
`VISUAL-RECEIPT.json` attributes that observation. The other two address bars
were not separately inspected because of concurrent user input; their exact
native clicked URLs and registered-browser title receipts remain recorded.

Focused automated regressions passed: three desktop opener tests, twelve
guarded client-packaging tests and seven installed-repair transaction tests,
twenty-two total. The desktop regression executes
the pinned plugin's real injected JavaScript against the dashboard's real link
helpers, checking three providers, rejected schemes, origin scope and unchanged
application navigation. Native OS browser delivery is established separately
by the positive receipt above.

Diagnostic attempts are preserved. An initial observer incorrectly required a
new Edge process, although the existing default browser received the request.
A later diagnostic tried to wrap Tauri's deliberately non-writable `invoke`
property; its zero-call result was an invalid instrumentation assumption, not a
client failure. Read-only event-handler inspection, actual click interception
and default-browser window receipts replaced those assumptions. A process
snapshot ctypes race in the optional observer was serialized before the final
passing run. No additional product repair was needed for these helper defects.

## Artifacts and installation status

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `dist/connections/external-links-20261101/DRAGONHYDRA-Client-x64.exe` | 10046464 | `557837ee832896c5d81b46222c701d4d7ddb771f9dc7ed22e3e2e5d222a1b84f` |
| `dist/connections/external-links-20261101/DRAGONHYDRA-Client-ExternalLinks-windows-x64-setup.exe` | 2334424 | `c14c9975acde78ed0568ec6ab082ba763ba0e65bcb358c81e76cf903ca38e175` |
| `dist/connections/external-links-workstation-20261101/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe` | 64757781 | `0f3a4aa6bcedfd29d37cb790f61d466e98e6a62a235af6b945055f28db83e135` |

The standalone NSIS installer contains a distinct 10046464-byte client EXE,
SHA-256 `c0faef9340d6a98942b1aa79d6a1a7c9e3388dc71c50902bd19182061a289056`.
That exact extracted payload also passed all three actual native link checks
in `evidence/client-installer-r1/verification.json`, with default-browser title
receipts, unchanged connection state and a live application after each click.
Its separately captured `BUILD-INFO.json` matches source checkpoint and content
hash above. The portable EXE and installer payload are not claimed byte-identical.

The rebuilt EXE and unified installer were built in separate new output
directories. Extraction confirmed the unified installer's client is the exact
portable `557837...1b84f` EXE and its server kernel remains the A6 binary
SHA-256 `6960835b332728672183b2953c4003119ed743a721793dd6e21a7b66181607fc`.
Their complete extraction/packaging checks belong to the aggregate receipt;
no previous release or installer was overwritten. Building the unified installer
is distinct from applying that whole installer to a workstation.

The guarded client-only repair subsequently completed with Windows elevation.
`build/connections/external-links-20261101/installed-client-backup-r1/repair-result.json`
records `passed=true`, `applied=true`, the backup and exact replaced files.
It replaced only the installed client/attribution/build metadata and corresponding
installation inventory metadata, without state/vault access or service controls.
All three service PIDs remained unchanged: A2Test 23500, default 16848 and
original test 22876. The public repair receipt is
`verified-reports/DESKTOP-EXTERNAL-LINKS-INSTALLED-REPAIR-20261101.json`.

The actual installed executable at
`build/workstation/test-install/provider-a2/application files/client/DRAGONHYDRA-Client.exe`
was then executed **in place**, rather than via a test copy. Its SHA-256 is the
portable `557837...1b84f` value above. `evidence/installed-r1/verification.json`
records `actual_installed_binary_executed=true`, the exact process image/PID
26692 and three passing native provider-link checks. Each click reached the
registered default Edge browser while the installed application stayed open on
Connections; settings, retained counts, pairing and endpoint remained unchanged.
Only that owned test process was terminated after verification. The previously
left-open portable test copy PID 39864 was available for coordinator review;
earlier owned diagnostic copies were cleaned separately.

The original and portable receipts bind archived helper SHA-256
`fe6c5ab786afb307e78f08ac43f8f40a1d76dd60c16f95dc50b4b03ed2a8c763`.
The installed execution adds a path-restricted `--run-in-place` option and binds
helper SHA-256 `d8fa09f21223270a7479a3904f0cd6f471111af25bc19e266bf9dc803b5d9efc`;
the earlier helper bytes are retained as `evidence/harness-before-installed.py`.
No application rebuild was needed for this test-only option. This verifies the
named current Windows installation, not clean-machine operation or a backend
service upgrade.

Reviewed public evidence is preserved separately as
`verified-reports/DESKTOP-EXTERNAL-LINKS-ORIGINAL-20261101.json`,
`verified-reports/DESKTOP-EXTERNAL-LINKS-REPAIRED-20261101.json`, and
`verified-reports/DESKTOP-EXTERNAL-LINKS-INSTALLED-ACCEPTANCE-20261101.json`, with
`verified-reports/DESKTOP-EXTERNAL-LINKS-VERIFICATION-20261101.json`.
Existing A6/A7 releases and independently managed Windows services remain
preserved; those releases are not replaced by this desktop increment.
