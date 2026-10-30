# DRAGONHYDRA integrated build checkpoint

Updated 2026-10-30. Development root: `C:\xampp\DRAGONHYDRA`.
This is a verified Windows x64 development checkpoint. The complete-workstation
installer and the full requested product remain unfinished.

## Verified delivery and next increment

- [x] Preserve the existing Python 3.14 sports kernel, statistical models, watcher and CLI.
- [x] Add authenticated `/dragon/api/v1`, persisted jobs, import, match/team/standings navigation, evidence summaries and real Excel export.
- [x] Connect the reusable dashboard and compiled Tauri client; exercise actual controls.
- [x] Install the Joomla package on a product-owned Apache/PHP 8.4/MariaDB instance; verify identity bridge, ACL, typed import and the same canonical match.
- [x] Rebuild the private-runtime server after API/job repairs and exercise the frozen executable.
- [ ] Next: assemble the complete Windows product bootstrapper, private web/database payloads, service lifecycle and MariaDB migration; verify clean install, restart, repair and retained-data uninstall.
- [ ] Credentialed live sources, compatible cross-provider odds, local LLM inference, external SQL/Google operations, Linux/x86 packages and APK verification remain unverified or unfinished.

The ten connector targets are registered; OpenFootball is the integrated public
adapter. Its real network capability probe retrieved 380 records. Retained imports
normalize 760 fixtures/results from the two bundled source files. These are
separate proofs; OpenFootball is not a live stream. SQLite remains authoritative.
Standings are labelled reconstructions, unavailable lineups/odds remain explicit,
and explanations are labelled deterministic rather than local-LLM output.

## Tests and evidence

| Check | Actual result | Evidence |
| --- | --- | --- |
| Original baseline | 163 tests passed on Python 3.14.10 | Initial session execution |
| Current full regression | 188 passed, no failures/errors/skips, 12.577 s in pinned server environment | `runtime/evidence/build/full-regression.log` |
| Preserved CLI | `score --format json`, exit 0 | `runtime/evidence/build/preserved-cli-score.json` |
| Shared web UI | 13 assertion groups passed in installed Edge through Playwright; intentional 503 recovery exercised | `runtime/evidence/dashboard/journey.json` |
| Joomla | Eight groups passed: login, signed status, capability action, CSRF rejection, import, canonical fixture, seven sections and reader ACL | `runtime/product-evidence/joomla/journey.json` |
| Native Tauri client | Five actual interaction groups passed through Microsoft UI Automation for both portable and installed binaries | `runtime/evidence/installation/portable-native-uia.json`, `installed-native-uia.json` |
| Client installer | NSIS install, notices, native interaction, uninstall and retained server state passed on this host | `runtime/evidence/installation/client-install.json` |
| Server lifecycle | Reuse, unrelated-listener coexistence, readiness, graceful restart and retained pairing passed | `runtime/evidence/installation/development-lifecycle.json` |
| Rebuilt frozen server | Six groups passed: private runtime, auth/Unicode regression, idempotent 760-record import, canonical browsing, XLSX and graceful shutdown | `runtime/evidence/installation/frozen-server.json` |
| Packaged ZIP round trip | Extracted into separate project scratch and repeated all six frozen-server groups successfully | `runtime/evidence/installation/frozen-server-archive.json` |

The frozen server started with Python environment variables removed and PATH
restricted to Windows system directories. Its loaded `python314.dll` was observed
inside the packaged `_internal` directory. This is current-host execution proof;
a clean machine and every native dependency combination have not been tested.
The separate Tauri/Edge WebDriver attempt failed because `DevToolsActivePort` was
missing; its evidence is retained. Native UI success used Microsoft UI Automation.

## Artifacts and tested versions

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `dist/DRAGONHYDRA-Server-0.3.0-windows-x64-checkpoint.zip` | 23,004,834 | `2327fb56947905f3643c41d7d86aed780b4594eae2fca523854e10df08b3d8c1` |
| `dist/DRAGONHYDRA-Client-0.3.0-windows-x64-setup.exe` | 1,882,284 | `d8b9060792a1a42c2c62f585a770c664221189d9bb9cfc4ebc9d97313baab87c` |
| `dist/DRAGONHYDRA-Client-x64.exe` | 8,227,328 | `a94b061242d19f80f08bb5de42c04037495df136a1f1e4c4a9a76e2662d12e90` |
| `dist/pkg_dragonhydra-0.3.0.zip` | 13,208 | `0f31d35c1f35c6b2418f3fbc95a10094671d158f9987fcc02627fdaa17f946bd` |

All distributables are unsigned development builds. The server ZIP contains the
kernel, private Python runtime, dashboard and retained public inputs; it is not a
web/database installer. The client NSIS installer contains only the client and
uses the Evergreen WebView2 download bootstrapper; missing-runtime offline setup
is not verified. Detailed file hashes and evidence are in the three `dist/*manifest.json`
records. The server executable is `dist/DRAGONHYDRA-Server-x64/DRAGONHYDRA-Server.exe`.

Tested host: Windows 11 Pro Insider Preview 10.0.29695 x64, WebView2 156.0.4314.50.
Server: Python 3.14.10, PyInstaller 6.22.3, FastAPI 0.162.0, Uvicorn 0.42.0,
Pydantic 2.14.2, Starlette 1.10.0, openpyxl 3.1.5, tzdata 2026.2.
Client: Tauri 2.12.5, build crate 2.7.4, CLI 2.12.4, Rust 1.99.1.
Joomla integration: Joomla 6.2.0, PHP 8.4.27 TS VS17 x64, Apache 2.4.65 x64,
MariaDB 10.11.16 x64. These latter services were tested in an isolated product
instance using existing Apache/MariaDB binaries; they are not inside the server ZIP.

## Reproduce and demonstrate

From PowerShell 7 in the development root:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
& .\runtime\server-env\Scripts\python.exe -B -m unittest discover -s tests -q
py -3.14 -B dragon.py score --format json
$env:PYTHONPATH = (Join-Path $PWD 'src') + [IO.Path]::PathSeparator + (Join-Path $PWD 'runtime\genesis2-pyinstaller-builder')
& .\runtime\server-env\Scripts\python.exe -B -m PyInstaller --noconfirm --distpath dist --workpath build\product-server packaging\windows\product-server.spec
& .\runtime\server-env\Scripts\python.exe -B tests\installation\frozen_server.py
& .\scripts\Build-Desktop.ps1
& .\tests\installation\client_install.ps1
& .\scripts\Start-Dragonhydra.ps1
```

The last command reuses the verified project server and opens Tauri when built.
Use **Browse retained matches**, select a fixture, open a team, return, open
standings and return to the same fixture. Open Odds to inspect its compatibility
state, then Analysis and **Explain this match**. Open the cited retained evidence.
Return to Overview, choose **Export to Excel**, then **Download report** for a
real workbook with Match and Metadata sheets. Administration opens the configured
private Joomla instance; its import action queues a kernel job and opens the same
canonical fixtures. A current empty Today/Live schedule remains an honest empty state.

Public demonstration and permanent deployment records belong under
`deployment/public-access`; their running gateway and tunnel were left untouched
by the artifact rebuild. No Codex update or existing application replacement was performed.
