# Integrated development checkpoint packaging

This checkpoint adds a Windows x64 Tauri client and a project-owned server launcher.
It does not yet include the complete-workstation Apache/PHP 8.4/Joomla/MariaDB
installer. Existing XAMPP services are not changed.

Launch from PowerShell 7 in `C:\xampp\DRAGONHYDRA`:

```powershell
& .\scripts\Start-Dragonhydra.ps1
```

The launcher starts the isolated Python 3.14 server environment on an available
loopback port and opens the compiled Tauri client when present, otherwise the
system browser. Relaunch reuses the same verified product PID and endpoint.
Tokens stay in the product state file and are never printed by the launcher.
Use `-Browser` to deliberately open the web dashboard, or `-NoOpen` for headless
development. `Stop-Dragonhydra.ps1` requests authenticated graceful shutdown and
verifies the PID belongs to this project before acting.

The client-only installer uses the Evergreen WebView2 download bootstrapper. It
requires Internet access if a compatible WebView2 runtime is absent. This is not
an offline installer. First run without product configuration opens the server
address/pairing screen. Remote servers require HTTPS; the local development
endpoint uses loopback HTTP. No Node.js, Rust, or Python runtime is required by
the compiled client itself; a configured DRAGONHYDRA server is required.

Build with existing Node/Rust/MSVC:

```powershell
& .\scripts\Build-Desktop.ps1
```

Tauri CLI is pinned by `package-lock.json`; Rust dependencies are pinned by
`src-tauri/Cargo.lock`. Server and frontend builds remain separate. The client
exposes no custom native commands or privileged shell plugin. Windows 11 Pro
Insider Preview 10.0.29695 x64 is the local execution target. Other Windows,
Linux and x86 compatibility remains untested. Consult the generated artifact
manifest for actual build, launch, native WebDriver and installation results.

Native-driver tests use project-owned `tauri-driver` 2.0.4 and Microsoft Edge
WebDriver 156.0.4314.50. The downloaded EdgeDriver archive SHA-256 is
`DFB627983FCDAA076266619E5CFDA0C654093CE1B320165574C4A08D5FDCA357`.
Upstream: <https://msedgedriver.microsoft.com/156.0.4314.50/edgedriver_win64.zip>.
Driver tools are development dependencies and are not included in the product
client installer.

Verified current-host checks:

```powershell
& .\tests\installation\check_lifecycle.ps1
& .\tests\installation\native_uia.ps1
& .\tests\installation\client_install.ps1
& .\packaging\genesis2\Write-ClientManifest.ps1
```

The isolated client installer test completed setup, five native interaction
checks, notices verification and uninstall while retaining the server pairing
state. Native interactions used Microsoft's UI Automation API against the actual
compiled WebView2 window. The separate `tauri-driver` 2.0.4 attempt failed because
EdgeDriver did not find `DevToolsActivePort`; that failed evidence is retained.
Neither native success nor the current-host NSIS test establishes clean-machine,
offline prerequisite, reboot, upgrade, x86 or Linux installation support.
