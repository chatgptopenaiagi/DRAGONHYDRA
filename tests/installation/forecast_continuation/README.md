# dev.5 disposable Forecast continuation

This is incident-specific Windows acceptance tooling, not an application module
or a general workspace controller. Read the
[incident report](../../../docs/reconciliation/FORECAST-PRESERVATION-INCIDENT-20261103.md).

Application source remains ed78fab282599a181d4254ab65a2fc2eaa5b7f50. The only target
is `core-next-b447d99ab9524197af09c235077685de`: API18860, Joomla18861, DB18862,
service `DragonhydraCoreNextcandidatec235077685de`. No primary-profile fallback exists.

Implemented operations:

- Default Preview reports scope without API/SCM queries or mutations.
- `ReconcileForecast -Apply -ValidateOnly` verifies the original evidence,
  source/profile/owner, protected services, installed hashes and current read-only
  API/SQLite state. It creates no operation directory, marker or snapshot.
- `ReconcileForecast -Apply` creates one distinct owner-restricted operation and
  performs GET-only original-job/history readback with coherent snapshots. It
  never repeats Forecast or rewrites the old failed receipt.
- `Backup -Apply` requires that successful new predecessor and the same elevated
  owner. It copies runtime, selected configuration/raw/export/vault state and
  consistent SQLite/MariaDB snapshots. It does not restore or restart anything.

Restart, Repair, UninstallRetain, ReinstallRetained and FinalUninstall explicitly
refuse with `NOT_IMPLEMENTED_BEFORE_MARKER`. The old strategy is preserved for a
separate reviewed adapter. No automatic loop, retry, elevation or native launch
exists in this controller.

Invocation requires absolute paths and explicit SHA-256 values for a coordinator
reconciliation receipt, its hash attestation and the three-code-file binding.
The `.example.json` files deliberately cannot authorize an operation. The local
reviewed controls are under `LAB/forensics/forecast-preservation-20261103/continuation-authority-r1`.
An attestation is not a digital signature or Windows authorization.

The original one-shot controls are read and hash-checked. Only whitelisted full
function definitions are imported by AST; their top-level statements never run.
Local historical evidence and helpers are prerequisites. Do not replace expected
hashes, delete a marker, or edit a failed receipt to enable a retry.

Run Python guards from the source root:

```powershell
python -B -m unittest discover -s tests -p test_forecast_continuation.py
```

Twenty-four cases use committed sanitized receipts. One mock-GET reader adapter
also needs the original Windows LAB definitions/profile and is explicitly skipped
when unavailable. It does not submit jobs or make real requests. PowerShell's
six additional AST/path/Preview/refusal checks run with:

```powershell
pwsh -NoProfile -File tests/installation/forecast_continuation/Test-ControllerGuards.ps1
```

They leave small synthetic fixtures only in the private forensic LAB, not the
source or installation. Tests, live readback, backup creation and restoration are
separate evidence scopes. Neither source guards nor a dump file prove restoration.
