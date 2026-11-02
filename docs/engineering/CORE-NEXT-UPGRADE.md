# Same-profile CORE NEXT development upgrade

The dev.2 entry point is `scripts/Upgrade-CoreNextWorkstation.ps1`. It is scoped
to a verified dev.1 CORE NEXT installation and the immediately next development
increment. It never selects the original DRAGONHYDRA workstation. Existing NSIS
and `CoreNext-InstallerChecks.ps1` same-build guards remain strict: a separate
explicit operator transition changes the owned metadata before invoking Setup.

The new server, native desktop, Joomla package and unified installer must first
be built from the frozen dev.2 source and inspected. Historical dev.1 and A9
assets stay unchanged. The desktop rebuild is required because its embedded
shared dashboard assets changed. Android's unchanged dev.1/code5 identity is not
renamed to dev.2. Reusing verified Cargo dependencies permits only a changed own
application lockfile version; all dependency records, checksums, toolchain and
architecture checks remain strict and application outputs are excluded.

## Preview before Windows elevation

Use the existing profile, never a newly generated installation profile. Resolve
all hashes and the complete new source commit from the verified final build
receipts. Public artifact hashes and identifiers are arguments; passwords,
pairing tokens and provider keys are not.

```powershell
$upgrade = 'C:\xampp\DRAGONHYDRA-CORE-NEXT\scripts\Upgrade-CoreNextWorkstation.ps1'
$parameters = @{
    ProfilePath = '<existing CORE NEXT installation-profile.json>'
    ExpectedInstallationId = '<that profile installation_id>'
    Installer = '<verified dev.2 Workstation Setup.exe>'
    ExpectedInstallerSha256 = '<full verified Setup SHA-256>'
    NewSourceCommit = '<full frozen dev.2 Git commit>'
    ExpectedNewServerSha256 = '<new installed server EXE SHA-256>'
    ExpectedNewClientSha256 = '<new installed client EXE SHA-256>'
}
& $upgrade @parameters
```

Without `-Apply`, the script only validates and prints a sanitized plan. It checks
the exact installation/profile, source/version, old installed bytes, SCM binding,
old ownership validator, owning listener ancestry and new package receipt/hash.
It creates no backup directory, changes no metadata and controls no service.
The current owner token is not assumed elevated.

## Apply is a separate owner-authorized operation

Only after the concrete candidate and preview have passed, the owner may approve
one Windows elevation. In that elevated PowerShell session, use the same
parameters plus `-Apply -BackupRoot '<fresh private LAB backup directory>'`.
Do not automatically retry canceled elevation or an uncertain installer result.

The apply phases are deliberately ordered:

1. Create a fresh owner/SYSTEM/Administrators-only backup directory outside the
   live profile. Capture complete runtime bytes with hashes, profile/configuration,
   private state, paired identity, provider settings and retained match identifiers.
2. Take an SQLite online backup with `integrity_check=ok`. Dump only the owned
   MariaDB instance through a private temporary client configuration, with no
   password in arguments. Its Joomla schema includes MEMORY tables, so the
   consistent dump uses a short own-instance read lock. No live database storage
   directory is copied.
3. Complete protected-file backups before stopping anything. If ordinary access
   is denied, only the three existing kernel JSON files (`local-session.json`,
   `joomla-bridge.json`, `local-ai.json`) may use Windows `robocopy /B /R:0 /W:0
   /COPY:DAT` under the authorized elevated token. No ACL, owner, service or task
   is changed to bypass access. Exit code 8 or higher, missing/empty output and
   path/ACL violations abort before the service stop. Backup payload hashes and
   OS-copy results are private; an unreadable source is never claimed rehashed.
4. Recheck stable, unique match identifiers, the four protected original
   services and the original profile/configuration fingerprints. An owner edit
   during backup aborts before stopping anything. Stop only the current CORE
   NEXT service through its old installed owning controller. Its Windows
   PowerShell invocation uses the same process-local execution-policy flag as
   the supported service/installer; machine policy is not changed.
5. Atomically replace profile/workstation JSON metadata fields only: version,
   source commit, build ID and product version. Preserve every other identity,
   port, schema, credential and owner value. Recheck the original snapshot before
   writing and each file's expected bytes immediately before replacement. A
   two-file partial failure restores only this operation's exact metadata if no
   independent change occurred; detected concurrent edits require reconciliation.
6. Invoke the new Setup with the same explicit `/PROFILE`. The new installer now
   sees its exact release binding and performs the supported same-profile repair.
7. Verify new server/client hashes, profile/source/version, owning listeners,
   authenticated backend identity, all retained ID/version pairs, existing
   configuration/credentials, provider settings, protected vault bytes and four
   original services. This is followed by separate genuine browser/native,
   persistence and authorized service-lifecycle acceptance.

`upgrade-receipt.json` inside the private backup records each phase. A still
running or failed Setup is a reconciliation condition, not permission to resend.
No automatic SQL restore or blind database rollback is performed. If recovery is
needed, first reconcile the recorded installer PID; stop only the owning service,
restore the matched runtime and original profile/configuration backups, and
separately review whether any database migration requires its consistent backup.
Never restore another profile or overwrite concurrent imports.

The initial non-elevated backup in LAB on 2026-11-02 preserved 760 fixtures,
10 cognitive records/receipts, provider configuration and source recovery data.
Three protected kernel files were correctly reported blocked. That partial
credential backup is not substituted for the complete apply-phase backup.
`tests/test_core_next_upgrade.py` exercises pure metadata preservation, wrong
identity/version/source rejection, original-project refusal, junction rejection,
partial-write recovery and mocked backup-copy failure paths. These fixtures do
not claim that a live upgrade or elevated backup operation has run.
