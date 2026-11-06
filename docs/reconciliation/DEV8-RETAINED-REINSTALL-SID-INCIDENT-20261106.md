# Dev.8 retained-data reinstallation: Windows service SID lookup

## Original failure

Source `937e054f11dd2c3e4b1ddb79b9b413f6d9ded9cc` passed genuine fresh
Windows installation, authenticated readiness, installed-service SQL archive
publication/readback, JSON/CSV/XLSX exports, native desktop and Joomla checks,
restart, repair and retained-data uninstall. The same sealed Setup then failed
during retained-data reinstallation on 2026-11-06 at 09:09 UTC.

The original `ReinstallRetained` operation remains
`failed_reconciliation_required`, Setup exit 1, with no automatic retry.
Its receipt SHA-256 is
`cc0f60ce4c2c668a76c88347f07136a45641a2876169ff2d48b17d7c3a77a844`.
The candidate is preserved with its service stopped, Manual startup and no
automatic recovery configured. No final uninstall or release publication followed.

## Demonstrated cause

The installer recreated the exact owned LocalService service and configured its
SID as UNRESTRICTED. It then called `NTAccount.Translate` in
`Resolve-CoreNextServiceSid`, before granting service access to application and
state directories. The actual production resolver reproduced
`IdentityNotMappedException` under authorized native Windows PowerShell 5.1
RemoteSigned. A read-only SCM query simultaneously returned the exact service
name, the original service SID and `STATUS: Active`.

The recreated service's deterministic SID matches the earlier actual-token,
ACL and dedicated SQL-principal evidence. The precise Windows account-name
lookup mechanism causing the failure has not been established; no cache cause,
cache flush or system-wide service reset is asserted or implemented.

The read-only production-function proof has SHA-256
`a7a8d05e8a2d47d4cfd1982a522c85e4cd02130486294b4561986316edf8f759`.
Before-reconciliation file/ACL/service evidence has SHA-256
`abf2c2bfb9cbe98d806742da703cca452caa9b15c591f98f2dbd01fdabe5b363`.

## Permanent correction

Resolve the service SID through supported, read-only SCM commands after verifying
the generated installation identity, exact executable command line and
LocalService account. Require UNRESTRICTED SID configuration, one exact service
name, one valid service SID and Active status. Reject failed, malformed,
ambiguous, inactive or foreign responses. Use the resulting typed SID directly
for ACEs and SQL SID bytes; do not depend on reverse or account-name translation.

[Microsoft's SC service configuration documentation](https://learn.microsoft.com/en-us/windows/win32/services/configuring-a-service-using-sc)
lists `showsid`. [Windows service hardening](https://techcommunity.microsoft.com/blog/askperf/ws2008-windows-service-hardening/372702)
describes per-service SID access and the same query.

SCM configuration is not effective-access proof. The existing real supervisor
preflight still requires LocalService with enabled candidate SID, unchanged
profile hash, required reads, denied immutable writes and state write/read/delete.
No broad ACL grant, owner replacement, policy relaxation or SQL-role expansion is
part of this correction.

The corrected helper was then queried read-only against the same failed
candidate under native PowerShell 5.1.29695.1001 and PowerShell 7.6.9. Both returned
the original typed service SID, preserved the profile hash and performed zero
ACL, service or SQL mutations. The service stayed stopped. These probes establish
resolution only, without claiming startup or application readiness.

## Verification and release contract

Regression fixtures must exercise the production resolver on both Windows
PowerShell 5.1 and PowerShell 7, including negative ownership, SID-type,
name/SID/status, native-failure and malformed-response cases. A read-only
comparison on the failed candidate can establish corrected resolution only.

The failed candidate and its immutable source/packages remain forensic evidence.
A new frozen source checkpoint and separate source-bound packages must undergo a
new disposable fresh installation and the established installed-service SQL,
GUI/Joomla and complete lifecycle sequence. Earlier source937 successes do not
pass those gates for different source bytes. The existing release coordinator
remains authoritative, and publication is held until genuine mandatory evidence
and final package privacy validation pass.

SQLite remains authoritative for operational records. MariaDB remains Joomla's
store. SQL Server remains the explicitly selected secondary research archive.
Forecasting code, formulas and accuracy claims are unchanged.
