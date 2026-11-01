# DRAGONHYDRA complete workstation development installer

`DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe` bundles the desktop client, private Python server runtime, private Apache/PHP/MariaDB, Joomla, the DRAGONHYDRA extension, and a Windows service and launcher. It is an unsigned development build. Its installer version remains 0.4.1-dev.1. Immutable baseline inputs are from commit `a1380545bd3bb225f400e7e328535ff692c0123a`; explicitly selected, separately verified kernel/client/Joomla overrides replace the corresponding installed payloads. `WORKSTATION-BUILD.json` records those identities and wrapper source hashes separately. A retained baseline input is not claimed as an installed component when an override replaces it.

Run Setup as an administrator, then open **DRAGONHYDRA Workstation**. The Administration shortcut opens the same instance's Joomla administrator. Initial administration credentials are displayed by the launcher and stored in protected product state; they are not embedded in Setup. The service starts the database, kernel and web server, chooses available loopback ports, imports the bundled documented public sample and retains state across restarts. It does not require the user to start Apache or run Python commands.

The declared platform is AMD64 Windows 10 or later with .NET Framework 4.8. Other OS/architecture combinations are not verified. Setup reuses an installed WebView2 runtime. If it is missing, the bundled Microsoft Authenticode-verified Evergreen bootstrapper downloads it from Microsoft; that case requires internet access. This is not a fully offline edition when WebView2 is missing. Developer-machine installation tests do not establish clean-machine compatibility.

Default locations are `C:\Program Files\DRAGONHYDRA` for binaries and `C:\ProgramData\DRAGONHYDRA` for protected mutable state. The development checkout and existing XAMPP installation are separate. All installed component processes are supervised by the product-owned Windows service `DragonhydraWorkstation`; optional local AI is not required for browsing. This increment uses the preserved SQLite kernel backend and MariaDB for Joomla administration. A MariaDB kernel migration, large model weights, private provider credentials, permanent VPS hosting, and Google credentials are not included.

Re-running this installer against the same owned paths stops only its validated service before replacing binaries. A conflicting nonempty installation/data directory, service, or unowned shortcut is rejected. Uninstall removes the exact owned service and binaries while retaining product data. Keep the data directory for reinstall/recovery. Uninstall does not remove shared WebView2/.NET, unrelated services, or XAMPP. Back up retained data consistently before a future version changes its schema.

Build with the already installed tools from the project root in PowerShell 7.
For the current Control Center, first obtain the verified kernel/client build
receipts and matching component ZIP through their existing build workflows.
Joomla dev.3 requires the kernel's matching passing frozen-registry proof; the
builder rejects the legacy kernel before creating a fresh output. A fresh kernel
selection alone does not replace the baseline A5 desktop. Select the verified F4
client explicitly to retain the external-browser repair.

```powershell
$sccStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$buildParameters = @{
    BuildRoot = ".\build\connections\system-control-fresh-$sccStamp"
    OutputRoot = ".\dist\windows\system-control-fresh-$sccStamp"
    KernelBuildRoot = '.\build\connections\system-control-center-20261101-kernel-r4'
    ClientBuildRoot = '.\build\connections\genesis-a8-client\verified-payload'
    JoomlaPackagePath = '.\dist\system-control-center-r3\pkg_dragonhydra-0.4.1-dev.3.zip'
}
& .\scripts\Build-Workstation.ps1 @buildParameters
```

These paths identify the verified local development inputs. On another checkout,
build those inputs and substitute their actual receipt-backed paths. They are not
downloaded or invented by this command. Fresh build/output roots must be new and
inside this project; the kernel and client inputs must be separate from staging.
The source route has fixture/integrity tests; the existing R4 installer was built
by the earlier verified repackage route, so this example does not claim a newly
executed fresh installer or clean-machine acceptance.

The builder verifies the immutable released component hashes, extracts full payloads, calls the workstation runtime and web payload builders, verifies the official WebView2 bootstrapper's Microsoft signature, creates a per-file payload manifest, and compiles one NSIS EXE. Build logs and `BUILD-REPORT.json` live under `build\workstation\0.4.1-dev.1\<run>`. Setup and a report copy live under `dist\workstation\0.4.1-dev.1`. No services are started during the build.

To recover packaging after a report/installer repair, use `-BuildRoot <existing-run> -RepackageOnly`. This first verifies every prior staged file, the exact file count, and the immutable input releases, then retains the old development EXE under that run's `candidates` directory before rebuilding metadata and Setup. Client replacement in an existing staging tree still requires its original verified copied-stage provenance. A fresh tree uses the same verified client-copy implementation without inventing old-stage provenance. Add `-RefreshRuntime` only for an intentional runtime source repair; the verified old staging is checked before the current runtime is rebuilt. `-RefreshWebHook` refreshes only the provisioning `manage.php`, its entry in the private web manifest, and the containing manifests; it preserves the verified web binaries and Joomla archive. Payload changes outside these controlled steps require a fresh build directory.

For an authorized isolated installation test, use dedicated product-owned paths and a unique service name. `/D` must be the final NSIS argument. The state directory must be outside the binary directory:

```powershell
$setup = '.\dist\workstation\0.4.1-dev.1\DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe'
& $setup /S /STATE=C:\xampp\DRAGONHYDRA\build\workstation\isolated-example\state /SERVICE=DragonhydraExampleTest /D=C:\xampp\DRAGONHYDRA\build\workstation\isolated-example\product
```

Wait for the Setup process and check its exit code. Silent installation does not launch the client. Launch the installed `workstation\DragonhydraLauncher.exe --state <state-directory>` to open the integrated product; add `--administration` for Joomla. A nondefault service name also gives shortcuts a distinct suffix so tests preserve the normal installation's links. Runtime status and diagnostic logs are in the protected state directory. Do not upload that directory: it contains local session and administration credentials.

Installation, reboot, repair, UI, and uninstall evidence must be recorded against the final Setup hash. `BUILT`, `INSTALL_TESTED`, and `CLEAN_MACHINE_TESTED` are separate claims. Refer to the integration report delivered with the artifact for observed results.
