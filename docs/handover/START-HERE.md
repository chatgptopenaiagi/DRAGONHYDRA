# DRAGONHYDRA GENESIS-2 checkpoint

DRAGONHYDRA is a local sports-intelligence research laboratory. This checkpoint
preserves its Python CLI, market analysis, statistical football forecasts,
append-only cognitive memory, public input receipts and test evidence. It is
an engineering checkpoint, not a claim of profitability or production readiness.

The original working directory is `C:\xampp\DRAGONHYDRA`. Run with PowerShell 7
and Python 3.14 (`py -3.14`; the tested interpreter was 3.14.10). Raw source
files and their original receipts are in `data/raw`; SQLite stores are in
`runtime`. The recovery archive provides backups in those same relative paths.
Use the checkout and its restored data for development; the wheel and Windows
executable are alternate CLI delivery methods, with external workspace/data
requirements documented in the release build evidence.
For installed and packaged CLI use, launch from the restored checkout or set
`$env:DRAGONHYDRA_HOME` to its absolute path so the CLI finds external data,
examples and the runtime database. `dragon score` is a synthetic read-only
smoke check. Frozen executable dependencies and verification are recorded in
the separately published release manifest and build metadata.

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRA'
git status --short --branch
git log -1 --oneline
py -3.14 --version
$env:PYTHONPATH = Join-Path $PWD 'src'
py -3.14 -B -m unittest discover -s tests -q
py -3.14 -B dragon.py --help
py -3.14 -B dragon.py intelligence
```

`intelligence` appends model and prediction records. Use a restored copy of the
database if you need to preserve a pristine backup. See `TEST-RESULTS.md` for
the recorded test and `RESTORE-INSTRUCTIONS.md` for recovery and integrity
checks. `README.md` documents individual commands and the distinction between
retrospective archive values and genuinely time-stamped observations.

The frequency, Poisson, recency and Elo forecasts are statistical models;
trained neural modeling is not implemented or verified. Current historical
holdout diagnostics are present-knowledge calculations, not a demonstrated
historical operational replay. No scored genuine operational forecasts or
synchronized real multi-provider price sequences have been established. The
precise SQLite receipt visibility boundary still requires verification.

Preserve UTC capture, persistence and earliest-usable times, immutable source
content and hashes, evidence links, corrections and explicit uncertainty. Never
backdate imported evidence. Restore the release tag and inspect the release
manifest, then follow `NEXT-CODEX-INSTRUCTIONS.md`. The existing private GitHub
repository has a separate pre-checkpoint `main` history; the checkpoint is on
its own branch and tag so that existing history is not overwritten.

The next priority is past-only feature construction and a genuinely trained,
saved and reloaded neural classifier, compared chronologically with existing
baselines. See `REMAINING-WORK.md` for dependencies and acceptance criteria.
