# GENESIS-3 offline evidence

`android/dragonhydra_mobile/assets/football-snapshot.json` is a read-only,
versioned export from the GENESIS-2 SQLite backup. It does not synchronize the
mobile app with the Python database, train models, or establish live prices.
Its `metadata` records the checkpoint commit, backup SHA-256, data origin,
source URLs and original capture/persistence receipts. It contains:

- Thirteen fixture records: an archived target and twelve actual training
  results, plus the full 50-row training manifest, retaining source-record
  paths, evidence IDs, UTC receipt/persistence/usable clocks and transformations.
- Five original model records and five original prediction records, including
  source evidence IDs, model version, model configuration and their receipts.
  The 1X2 ensemble and Poisson goals/scoreline summary are copied from those
  records. The prediction's decision cutoff was not present in its retained
  payload; it remains null. Its data cutoff and receipt are separate clocks.
- Twelve Football-Data source-labelled historical odds observations from a
  different fixture. They preserve source columns and original decimal strings,
  acquisition identities, receipt clocks, evidence IDs and the shared-feed
  label. They are neither live prices nor mapped to the forecast fixture;
  quote times, settlement, provider mappings and provider independence are
  unknown. No model-versus-market comparison is warranted between them.
- Example present-knowledge chronological holdout metrics and sample size,
  sourced to the hashed retained GENESIS-2 report. Its exact holdout cutoff was
  not exposed by that text output and is null. This is not a retrospective
  operational replay or evidence of an edge.

Source publication time remains unknown where the receipts say null. The
2026/27 OpenFootball snapshot is attributed to its CC0 source and the 2025/26
Football-Data snapshot carries its original private/academic research use
notice. Review the [Football-Data terms](https://www.football-data.co.uk/contact.php)
before any broader distribution or training use. The fixture date and source
local kickoff time must not be promoted into an invented UTC availability time.

To regenerate and verify the snapshot in the original workspace, first restore
the GENESIS-2 recovery archive's SQLite backup, original raw files, receipts and
captured report under the paths used by the script, then run:

```powershell
py -3.14 -B android/fixtures/build_snapshot.py
py -3.14 -B android/fixtures/test_snapshot.py -v
```

The snapshot generator opens the backup in read-only mode. Its generation time
will change on rerun; source capture and receipt times are retained unchanged.
Tests compare the snapshot with the preserved database and source bytes. They
need the separately restored GENESIS-2 recovery data and are not the mobile app's
standalone widget/unit tests.
