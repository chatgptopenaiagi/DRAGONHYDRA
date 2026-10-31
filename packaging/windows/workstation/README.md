# DRAGONHYDRA complete workstation development installer

`DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe` bundles the desktop client, private Python server runtime, private Apache/PHP/MariaDB, Joomla, the DRAGONHYDRA extension, and a Windows service and launcher. It is an unsigned development build. Its installer version is 0.4.1-dev.1; the reused, verified server/client/extension are 0.4.0-alpha.1 from commit `a1380545bd3bb225f400e7e328535ff692c0123a`. `WORKSTATION-BUILD.json` records the new wrapper source file hashes separately.

Run Setup as an administrator, then open **DRAGONHYDRA Workstation**. The Administration shortcut opens the same instance's Joomla administrator. Initial administration credentials are displayed by the launcher and stored in protected product state; they are not embedded in Setup. The service starts the database, kernel and web server, chooses available loopback ports, imports the bundled documented public sample and retains state across restarts. It does not require the user to start Apache or run Python commands.

The declared platform is AMD64 Windows 10 or later with .NET Framework 4.8. Other OS/architecture combinations are not verified. Setup reuses an installed WebView2 runtime. If it is missing, the bundled Microsoft Authenticode-verified Evergreen bootstrapper downloads it from Microsoft; that case requires internet access. This is not a fully offline edition when WebView2 is missing. Developer-machine installation tests do not establish clean-machine compatibility.

Default locations are `C:\Program Files\DRAGONHYDRA` for binaries and `C:\ProgramData\DRAGONHYDRA` for protected mutable state. The development checkout and existing XAMPP installation are separate. All installed component processes are supervised by the product-owned Windows service `DragonhydraWorkstation`; optional local AI is not required for browsing. This increment uses the preserved SQLite kernel backend and MariaDB for Joomla administration. A MariaDB kernel migration, large model weights, private provider credentials, permanent VPS hosting, and Google credentials are not included.

Re-running this installer against the same owned paths stops only its validated service before replacing binaries. A conflicting nonempty installation/data directory, service, or unowned shortcut is rejected. Uninstall removes the exact owned service and binaries while retaining product data. Keep the data directory for reinstall/recovery. Uninstall does not remove shared WebView2/.NET, unrelated services, or XAMPP. Back up retained data consistently before a future version changes its schema.

Build with the already installed tools from the project root:

```powershell
pwsh -NoProfile -File .\scripts\Build-Workstation.ps1
```

The builder verifies the immutable released component hashes, extracts full payloads, calls the workstation runtime and web payload builders, verifies the official WebView2 bootstrapper's Microsoft signature, creates a per-file payload manifest, and compiles one NSIS EXE. Build logs and `BUILD-REPORT.json` live under `build\workstation\0.4.1-dev.1\<run>`. Setup and a report copy live under `dist\workstation\0.4.1-dev.1`. No services are started during the build.

To recover packaging after a report/installer repair, use `-BuildRoot <existing-run> -RepackageOnly`. This first verifies every prior staged file, the exact file count, and the immutable input releases, then retains the old development EXE under that run's `candidates` directory before rebuilding metadata and Setup. Add `-RefreshRuntime` only for an intentional runtime source repair; the verified old staging is checked before the current runtime is rebuilt. `-RefreshWebHook` refreshes only the provisioning `manage.php`, its entry in the private web manifest, and the containing manifests; it preserves the verified web binaries and Joomla archive. Payload changes outside these controlled steps require a fresh build directory.

For an authorized isolated installation test, use dedicated product-owned paths and a unique service name. `/D` must be the final NSIS argument. The state directory must be outside the binary directory:

```powershell
$setup = '.\dist\workstation\0.4.1-dev.1\DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe'
& $setup /S /STATE=C:\xampp\DRAGONHYDRA\build\workstation\test-install\state /SERVICE=DragonhydraWorkstationTest /D=C:\xampp\DRAGONHYDRA\build\workstation\test-install\product
```

Wait for the Setup process and check its exit code. Silent installation does not launch the client. Launch the installed `workstation\DragonhydraLauncher.exe --state <state-directory>` to open the integrated product; add `--administration` for Joomla. A nondefault service name also gives shortcuts a distinct suffix so tests preserve the normal installation's links. Runtime status and diagnostic logs are in the protected state directory. Do not upload that directory: it contains local session and administration credentials.

Installation, reboot, repair, UI, and uninstall evidence must be recorded against the final Setup hash. `BUILT`, `INSTALL_TESTED`, and `CLEAN_MACHINE_TESTED` are separate claims. Refer to the integration report delivered with the artifact for observed results.
