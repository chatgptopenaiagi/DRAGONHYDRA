# Restore and verify

Download the private release's recovery archive and `SHA256SUMS.txt` using an
authorized GitHub account. Compare the archive and other artifact hashes with the
published checksum file before extraction. Extract to a new directory inside the
project, inspect its contents, and do not overwrite an existing live database.

The archive contains a source snapshot in `source/` and a Git bundle for the tagged
checkpoint, `data/raw` with acquisition receipts, `runtime` SQLite backups,
backup/test metadata, and separately labeled donor snapshots and evidence where
listed in its inventory. The release manifest outside the archive records the
archive's hash; it cannot be embedded in the archive without self-reference.

For a fresh destination, restore the checkpoint from the included Git bundle or
release tag, then copy `data/raw` and `runtime` from the extracted recovery
content to their relative locations in that checkout. Keep the recovered backup
files unchanged; copy them before running commands that append records.
`python -m zipfile -t` verifies ZIP structure; use `Get-FileHash -Algorithm
SHA256` for artifact hashes and Python's SQLite `PRAGMA integrity_check` for
each restored database. Compare database hashes and row counts with the archived
`metadata/database-backups.json`. Data source terms and receipt times remain
part of the evidence; restoration is not a new historical capture.

For example, after placing the verified ZIP under `release/genesis2` in the
original workspace, this creates a separate project-local checkout without
overwriting the live one:

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRA'
Expand-Archive -LiteralPath 'release\genesis2\DRAGONHYDRA-GENESIS2-RECOVERY.zip' -DestinationPath 'release\genesis2\recovered-content'
git clone 'release\genesis2\recovered-content\DRAGONHYDRA-source.bundle' 'release\genesis2\recovered-checkout'
Copy-Item -Recurse 'release\genesis2\recovered-content\data' 'release\genesis2\recovered-checkout\data'
Copy-Item -Recurse 'release\genesis2\recovered-content\runtime' 'release\genesis2\recovered-checkout\runtime'
Set-Location 'release\genesis2\recovered-checkout'
$env:PYTHONPATH = Join-Path $PWD 'src'
py -3.14 -B -m unittest discover -s tests -q
py -3.14 -B dragon.py --help
```

Use new destination names if either destination already exists. Check the
release asset's recorded SHA-256 and compare the restored SQLite hashes before
running write-capable commands. Bundle clone checks out the checkpoint branch;
`git rev-parse HEAD` must match the release manifest.

Then run the commands in `START-HERE.md`. A source checkout needs Python 3.14
and the restored files; the wheel provides installed Python modules and a CLI;
the executable is a separately packaged Windows CLI. Neither packaging format
replaces the external raw data and mutable databases. Review the generated
release manifest and build-verification evidence for actual artifact names and
any packaging-specific workspace options.

Separate pre-existing `source/`, `commander-visual-v1/`,
`commander-living-data-v1/`, their evidence directories and the old desktop
build belong to a different DRAGON donor history. They remain in the original
workspace and are not part of this release archive: their binary evidence and
history have not been reviewed for credentials or unrelated private data. A
locally verified donor history bundle is kept at
`release/genesis2/DRAGON-donor-history.bundle`; do not treat it as part of the
DRAGONHYDRA release. The donor worktree `.git` links were not usable at freeze.
