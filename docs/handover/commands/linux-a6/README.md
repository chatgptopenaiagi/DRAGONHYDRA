# Exact Linux A6 verification helpers

These are byte-identical archival copies of the final helpers executed from
build/linux/prep-20261031-a6. They are fixed-path proof snapshots, not general
installation commands. The tested builder/product source remains unchanged.

Do not execute them from this documentation directory. To reconstruct an absent
local evidence workspace, first read LINUX-A6-CHECKPOINT.md and its frozen build
manifest, retrieve the exact archive/wheel and retained licensed input files,
then review paths and restore these copies to the original work directory.
No raw data, secrets, source database or model is included here. Contract/parser
helpers require actual Ubuntu /usr/bin/python3 -I -B and assert wheel origins.

verify_integrity.py is a one-shot local file-only receipt writer and asserts
that its output does not exist. Its original receipt already exists: read it;
do not delete or overwrite it to force a rerun. Prior helper/report iterations
remain locally under supplemental-history/pre-sql-sidecar-guard-r1.

Final helper hashes are in LINUX-A6-INTEGRITY-VERIFICATION.json. Both supplemental
reports bind the final wheel_guard.py SHA56f9a4...2aec. Successful synthetic F3
selection does not establish real model inference or database grounding.
