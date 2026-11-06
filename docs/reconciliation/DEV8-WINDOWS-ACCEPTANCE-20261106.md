# GENESIS-8.3 — dev.8 installed Windows acceptance

## Source and package identity

Application source remains `0e5df36704eeeaadbbf2380cc5352473fc2ebf0b` on the pushed
repair branch. No application source changed and no software was rebuilt.
All nine dev.8 packages and six metadata files match their sealed hashes; no
package differences were found. Existing decoded Setup host, scripts, server,
Python314, pyodbc5.3 and SQL migration bindings were checked without re-extraction.
Installer ordering remains private profile creation, Manual service registration,
service SID, scoped ACL provisioning, then startup; the actual token preflight
precedes database/backend launch. These are integrity/source checks, not fresh
installation acceptance.

## Installation and service

Recorded target: `core-next-ff4b47d263f2405fa77286aad1db720f`, service
`DragonhydraCoreNextcandidate86aad1db720f`, ports19150/19151/19152.
Application/state directories, service, listeners and phase markers remain absent.
No fresh installation attempt was made.

Recovered dev.7 remains Running as LocalService/PID30700. Authenticated ready and
system identities match its originalc7f9478 installation. All three existing
JSON/CSV/XLSX exports retain their hashes and successful single-attempt jobs.
No new jobs or mutating API requests were made.

## Exact execution-context blocker

Native x64 Windows PowerShell5.1 is effectively Restricted: every configured
scope is Undefined, so the Windows client default applies. PowerShell7 separately
uses LocalMachine RemoteSigned. The frozen SQL helper supports a read-only PS7
preview by source flow, but its Apply path explicitly requires native x64 PS5.1.
The helpers are unsigned and have no remote Zone.Identifier; neither signing
status nor Administrator elevation makes Restricted accept scripts.

No approved Apply context or supported alternate product provisioner was found.
Existing signed SQLCMD is not a substitute for the product provisioning contract.
No policy was changed, no rejected helper was loaded by another technique, and
no existing NSIS/service policy flags were used as an alternate route.
See [Microsoft's policy-scope/default contract](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1).

The owner decision is pending for a temporary dedicated Process-scope RemoteSigned
acceptance context, leaving CurrentUser/LocalMachine policies unchanged and using
the exact sealed installer's normal entry point. No exception is inferred from
elapsed time or the UI's preselected answer. The project rule remains
AGENTS.md:11: “Never bypass elevation or policy rejection.”

## New reviewable fresh-install controller

The Nov5 fresh plan was plan-only. The already-failed dev.7 controller cannot be
replayed. A new external controller reuses that established one-shot contract
for the exact recorded ff4/0e identity under the Nov6 `windows-fresh-r2` operation.
It adds no installer flags, elevation, policy override, SQL or GUI operation.
It binds the sealed packages/profile/owner, seven protected services and current
script eligibility before any CreateNew marker. Actual installed file hashes,
service SID/token preflight, listener ancestry, atomic status reads and
authenticated readiness remain required after an actual successful installer.
The existing source-owned acceptance adapter/coordinator remain authoritative.

Fifteen guard groups passed with fake runtime controls and bounded read-only
metadata/atomic-file fixtures. Independent review passed. Two preparation defects
were corrected before execution: enum policy JSON must contain a symbolic label;
AllSigned must reject unsigned frozen scripts. Inherited PS7 module lookup is
normalized only for the native metadata child, without modifying policy.
R1 preparation and all receipts are retained. Actual r2 Preview reports Restricted
and blocks before the marker; no Apply/installer/SCM/SQL action occurred.

Bindings SHA256:
`960fd0f73445244c7eadc6f63bdf44f54ad02852cff5f54ccc63acac2fabe9bc`.

## SQL Server

One reviewed read-only R3 operation reused the exact frozen product identity
SELECT under the interactive owner: DESKTOP-44UK3UB\LOVE, dbo/master, Shared Memory,
NTLM. Seven user-database metadata records and95 server configuration records
were unchanged across that operation. The expected target database and service
principal are absent. This does not establish installed service authentication.
No provisioning, DDL, grants or SQL configuration changes occurred.

Earlier read-only harness failures remain preserved: inherited module autoload,
a metadata-query syntax assumption, and a decoded HTTP body byte-cast assumption.
They did not involve installation or provisioning. No failed receipt was promoted.

## Lifecycle, native GUI and Joomla

Fresh install, new service startup, SQL service authentication, restart persistence,
repair, retained uninstall/reinstall and final uninstall are NOT_RUN because their
predecessors are absent. No destructive lifecycle action occurred.
The supported Computer Use interface successfully listed nine open windows and no
DRAGONHYDRA client window; no app was launched or controlled. Actual installed
dev.8 native GUI and Joomla acceptance are NOT_RUN. No source or standalone test
is substituted for these requirements.

## Tests, GitHub and preservation

The unchanged application source retains its prior1020PASS/28NOT_RUN/0FAIL suite;
it was not unnecessarily rerun. The new controller's15 guard groups passed;
they are not counted as installed application tests.

Seven existing services retain recorded Running state, PIDs and bindings. Original
plans/receipts, frozen source and sealed software remain unchanged. Codex's file
SHA256 still matches the recorded baseline; no CLI execution/update occurred.
Existing SQL metadata checks were read-only; no whole-live-database equality is
claimed.

GitHub still has10 historical releases/95 assets with unchanged identity/hash
metadata. The dev.8 tag/release are absent; no upload or public download occurred.
The release coordinator was not rerun without new mandatory Windows evidence;
its prior authentic primary-gate refusal remains applicable. No passing gate was
created and no acceptance requirement was relaxed.

## Result and next action

BLOCKED. Independent current verification and the missing controller preparation
are complete; actual fresh Windows acceptance is not complete.

The smallest unresolved requirement is the owner's explicit decision on a compliant
native PS5.1 execution context. After approval, review the r2 bindings and run that
controller exactly once, then separate SQL provisioning, lifecycle, native/Joomla,
installed privacy and authoritative release validation. Publish/download/hash
verification remains conditional on those genuine results.

[Machine-readable verification](DEV8-WINDOWS-ACCEPTANCE-20261106.json) binds the
private reports and reviewed controller bundle by SHA256. Private evidence root:
`C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\release-evolution-20261106\dev8-acceptance-r1`.