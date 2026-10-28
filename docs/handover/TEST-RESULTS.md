# Freeze test evidence

After adding the packaging entry-point tests, the final source suite was run at
2026-10-28T14:43:46.8114269Z with the same command and Python 3.14.10:

```text
----------------------------------------------------------------------
Ran 163 tests in 7.913s

OK
```

Exit code 0; 163 passed, 0 failures, 0 errors, 0 skipped; external elapsed
time 8.3989468 seconds. The final result supersedes the earlier freeze run
below. Full output and metadata are in the recovery archive's `metadata/`.

On 2026-10-28 at 14:38:20 UTC, using Python 3.14.10 and PowerShell in
`C:\xampp\DRAGONHYDRA`:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
py -3.14 -B -m unittest discover -s tests -q
```

```text
----------------------------------------------------------------------
Ran 161 tests in 7.889s

OK
```

Exit code 0; 161 passed, 0 failures, 0 errors, 0 skipped. The measured external
elapsed time was 8.3616565 seconds. This supersedes the older 138-test handoff
claim. The output and execution metadata are preserved under the recovery
archive's `metadata/`. Database backup `PRAGMA integrity_check` returned `ok`
for all three SQLite backups; this is not a SQL Server integration test.

The tests validate the behaviors they cover; they do not establish predictive
edge, calibrated probabilities or a complete production deployment.
