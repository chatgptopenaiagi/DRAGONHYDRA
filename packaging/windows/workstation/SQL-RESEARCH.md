# Optional SQL research archive after workstation installation

SQLite remains the canonical sports evidence, cognition and job store. SQL Server holds only explicit research publications and versioned notes. Installing this workstation does not configure or initialize SQL Server automatically.

New CORE NEXT installations record `service_sid_policy=unrestricted` and configure their own service SID before the first service start. They retain the LocalService account. Repair verifies the declared SID policy. An older CORE NEXT installation without that policy and with SQL disabled keeps its previous service configuration. Enabling SQL on such an older installation requires a separate reviewed migration; repair does not retrofit its security settings.

The workstation installer still needs Windows administrator rights. The SQL provisioning helper does not create, stop, restart or reconfigure Windows services and does not require Windows administrator membership. It requires the same owner SID recorded by the installed workstation, write access to that owner's state, and actual SQL permissions to initialize the dedicated database and create its Windows login/database user. Windows elevation and SQL permissions are distinct.

Use PowerShell 7 to orchestrate an explicit native Windows PowerShell 5.1 child. `.NET Framework 4.8` is already an installer prerequisite. The owner helper uses its built-in ADO.NET SQL client only for maintenance; application acceptance must use the frozen application's ODBC connection under the actual service identity.

After the exact new candidate is installed, prepare a protected fresh receipt path and the source/server/schema hashes from the reviewed release manifest. Preview first:

```powershell
$ps51 = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
& $ps51 -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File "$InstallRoot\workstation\Configure-CoreNextSqlResearch.ps1" `
  -ProfilePath $ProfilePath -ExpectedInstallationId $InstallationId `
  -ExpectedSourceCommit $SourceCommit -ExpectedServerSha256 $ServerSha256 `
  -ExpectedSchemaSha256 $SchemaSha256 -SqlServer $VerifiedLocalLpcEndpoint
```

Only after the bounded plan is reviewed, use the same arguments with `-Apply -ReceiptPath $FreshPrivateReceipt`. Certificate validation is the default. `-TrustServerCertificate` must be an explicit decision for the verified local instance; it does not establish certificate identity validation. No password or API token is accepted as a helper argument.

The helper accepts one database name derived from the candidate's own UUID suffix: `DRAGONHYDRA_CORE_NEXT_SQL_<LAST12UUIDUPPER>`. It rejects other installations, baseline profiles and alternate databases. A newly created database receives the exact bundled canonical SQL schema, ownership marker and migration checksum. An existing database must already pass those ownership/schema checks; an unowned database is never adopted or repaired.

Only `NT SERVICE\<that candidate's service name>` receives a SQL login/database user. The grant set is CONNECT, SELECT on the eight archive tables, INSERT on archives/models/predictions/inputs/notes and UPDATE on notes. The audit trigger relies on ownership chaining; it receives no explicit INSERT grant. No shared LocalService login, server role, database role, database-creation permission or global metadata permission is granted. Existing unexpected direct grants or role memberships cause a failure for review.

The helper writes `state/kernel/research-storage.json` only after successful owner provisioning. Conflicting existing settings are preserved and rejected. A successful receipt ends at `stage=configured_restart_required`, with `passed=true`, the profile/source/service/SID/database bindings, exact schema/server/configuration hashes and the 15 selected grants. This proves owner provisioning only. The owning controller must restart only this candidate, then acceptance must verify actual `connection_identity` from ODBC health: login, database user, database, transport and Windows authentication scheme. Do not infer service authentication from the owner connection or a configured service name.

An uncertain or failed operation leaves its receipt and started marker for inspection; it does not retry, drop a database or remove a login automatically. Uninstalling the workstation retains its state and the external SQL database. Reinstalling the same profile recreates the same service name/SID, and its retained SQL configuration must be verified again. SQL archive cleanup is a separate owner action and is not part of workstation uninstall.
