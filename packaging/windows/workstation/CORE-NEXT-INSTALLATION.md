# DRAGONHYDRA CORE NEXT {{VERSION}}

This unsigned development workstation contains the CORE NEXT Python application,
native Windows client and Joomla System Control Center built from source
`{{SOURCE_COMMIT}}`. The retained A9 third-party Apache/PHP/MariaDB/Joomla runtimes
are private application payloads. `WORKSTATION-BUILD.json` records the actual
component hashes and distinguishes these reused runtimes from new application code.

Run `DRAGONHYDRA-CORE-NEXT-{{VERSION}}-Workstation-win-x64-Setup.exe` as administrator.
Setup creates a fresh `core-next-<GUID>` profile below
`C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles`, with separate application, state and
browser directories, service, shortcuts, database schemas and free reserved ports.
It does not select the original workstation or fall back to its backend.
The installer requires x64 Windows, .NET Framework 4.8 and WebView2. A missing
WebView2 uses Microsoft's verified online bootstrapper; that case needs internet.
Current-host acceptance does not establish clean-machine or OS-reboot support.

SQL Server research storage is optional. The server includes its Python connector
and schema; Microsoft ODBC Driver18 and the SQL Server engine remain separate
prerequisites. Start with the installed `workstation\SQL-RESEARCH.md` guide and
preview `Configure-CoreNextSqlResearch.ps1` against this exact owned profile.
The matching owner provisions a dedicated database and only this service SID's
narrow SQL permissions. This does not grant access to the shared LocalService
account or change another database. Apply the protected configuration only after
owned installation, then explicitly restart this profile to load it. Verify the
authenticated research diagnostic reports the service's SQL identity. Interactive
owner connectivity alone does not establish service connectivity. SQLite and
Joomla MariaDB retain their established data responsibilities.

Open the newly named **DRAGONHYDRA CORE NEXT candidate <suffix>** shortcut. The
launcher provides this installation's first-run credentials, also stored privately
in its state directory. Keep that directory private. The Administration shortcut
opens this instance's Joomla Control Center. Provider refresh schedules are
disabled; optional local AI is not needed for ordinary browsing or calculations.
On a fresh Joomla administrator account, its welcome tour may open the Home
Dashboard first. Complete or dismiss that tour, then use Components → DRAGONHYDRA
CORE NEXT → System Control Center or reopen the Administration shortcut.

For repair, select this exact installation profile explicitly:

```powershell
& '.\DRAGONHYDRA-CORE-NEXT-{{VERSION}}-Workstation-win-x64-Setup.exe' /S '/PROFILE=C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles\core-next-<GUID>\installation-profile.json'
```

Replace `<GUID>` with the existing installation's identifier. Running Setup without
`/PROFILE` creates another isolated installation. Never supply an original edition's
state directory or service. Repair validates ownership and preserves private data.
Use this instance's registered uninstaller or its `Uninstall-Workstation.exe`.
Uninstall removes its service, shortcuts and application directory while retaining
its separate state and profile for recovery. Shared .NET/WebView2 and other editions
are preserved. Close this instance's client before repair or uninstall.

Build commands and release-specific acceptance scopes are in the exact source
archive and release reports. Do not use inherited historical installer commands
from earlier editions. Keep source snapshots, signing keys, application credentials,
provider keys and live state out of distributable packages.
