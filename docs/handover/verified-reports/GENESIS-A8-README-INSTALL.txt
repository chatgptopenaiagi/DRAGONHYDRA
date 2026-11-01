DRAGONHYDRA GENESIS A8 - Windows x64 Workstation

This package is one Windows workstation Setup. It includes the native desktop
client, local Python API server and worker, private runtime dependencies,
Apache/PHP/MariaDB, Joomla integration, Windows service, native launcher and
configuration templates. Models and private provider API keys are not bundled.

Platform and prerequisites

The acceptance target is Windows 11 x64. The build declares AMD64 Windows 10 or
later with .NET Framework 4.8; other combinations are not separately verified.
Setup reuses an installed Microsoft WebView2 runtime. If WebView2 is missing,
its official Microsoft bootstrapper requires internet access to install it.
The package is not claimed to be fully offline when WebView2 is absent.

Install or upgrade

1. Keep this folder together and check the installer against SHA256SUMS.txt.
2. Close the desktop client belonging to the installation being upgraded.
3. Run the complete Setup EXE and approve Windows elevation when requested.
4. For the normal installation, retain the selected product installation and
   data locations. Setup validates ownership and preserves application data.
   A custom test/service profile must retain its original installation path,
   state path and service identity; do not redirect it over another profile.
5. Wait for Setup to finish. It configures and starts the corresponding local
   service; there is no need to start Python, Apache or MariaDB manually.
6. Open the installed "DRAGONHYDRA Workstation" desktop or Start menu shortcut.
   Nondefault profiles have their service name in the shortcut's title.

Default binary location: C:\Program Files\DRAGONHYDRA
Default mutable data:    C:\ProgramData\DRAGONHYDRA

Automatic local connection

Use the official shortcut for your installation. Its launcher waits for that
installation's services and supplies its existing local pairing metadata to
the desktop. You should not need to type a pairing token or select a fixed port.
The installer chooses available loopback ports; do not copy a port or token
from another DRAGONHYDRA profile. A bare installed client also discovers its
own validated installation binding.

If a connection dialog appears, close that client and reopen the official
workstation shortcut. Allow service startup to finish and use its diagnostics
or Retry action if startup is still pending. Keep the existing state directory;
do not create replacement credentials merely to resolve a launch problem.

Provider links and configuration

All ten currently exposed provider registration and documentation links open
the provider's web address in the Windows default browser while DRAGONHYDRA stays open.
The Administration control opens this workstation's local Joomla page in the
browser. No provider login or account creation is needed to test link opening.
Private provider access requires the appropriate key configured through the
application's Connections screen. The package does not supply paid access.

Data, exports and upgrades

The local server retains imported football records and application settings.
The application supports structured analysis and JSON, CSV and Excel exports.
A finished match may correctly report that no prospective forecast was retained;
this is an explicit abstention rather than an invented prediction.
Retain the state directory during upgrades and keep consistent backups before
any future version changes its data schema. Do not share that directory: it
contains authentication state and private Joomla/provider configuration.
Uninstall removes the owned service and binaries while retaining product data.
Unrelated workstations, shared Windows runtimes and XAMPP remain separate.

Version and verification

GENESIS A8 is the engineering delivery name. Reused component declarations
remain workstation 0.4.1-dev.1 and desktop/API 0.4.0-alpha.1; BUILD-REPORT.json
records exact source and payload identities. TEST-REPORT.json records the
executed final installation, official-shortcut pairing, native links, navigation,
exports, application/service restart and persistence checks.

The verified complete Setup is 64,769,361 bytes. Its SHA-256 is:
27b7b310fe78baeea76275cfc53ddacc254c99c60e7dcc641f813692398846fa

The exact Setup completed a guarded upgrade in an isolated Windows 11 x64
installation. The final installed client passed twenty native acceptance groups
including all ten current provider links, two official-shortcut launches, match
and team browsing, standings, deterministic analysis and three export formats.
Bare-client pairing and Administration passed three more groups. An authorized
restart of only the isolated service and a subsequent shortcut launch verified
all 760 retained records, pairing/settings and all three exported files/jobs.
The three pre-existing workstation services were preserved.

This is current-host isolated acceptance, not a clean-machine or OS-reboot test.
The package is an unsigned development build. Use the official shortcut rather
than copying authentication state or assuming a historical port.

Delivery files:

  DRAGONHYDRA-GENESIS-A8-Windows-x64-Setup.exe
  SHA256SUMS.txt
  BUILD-REPORT.json
  TEST-REPORT.json
  README-INSTALL.txt
