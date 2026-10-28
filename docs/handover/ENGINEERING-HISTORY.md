# Engineering history and evidence

At the start of the freeze the root repository was unborn `master`, with no commits or remote. Git history therefore does not provide a committed sequence for this root-level implementation prior to this checkpoint. Existing untracked folders and files remain preserved locally.

Documented local milestones, using repository evidence and capture receipts:

- OpenFootball 2025/26 was captured at 2026-10-28T13:45:25.604975Z and the 2026/27 file at 13:51:48.055200Z. Football-Data 2025/26 was captured at 13:52:42.828086Z. These are local receipt clocks, not original publication or quote clocks. See the individual `data/raw/*.receipt.json` records.
- A local price-analysis and results pipeline was implemented, followed by cognitive models, append-oriented memory, scoring, evidence-based adaptation and research-task/hypothesis handling. Exact modules are listed in [ARCHITECTURE.md](ARCHITECTURE.md).
- At 2026-10-28T14:37:31Z the main DB held 70 model records, 60 prediction records for one distinct fixture, 44 tasks and 10 hypothesis revisions; no attached outcomes or evaluation records were present. This is a snapshot, not a longitudinal performance result.
- Three SQLite backups were taken at approximately 14:38:03Z and reported `integrity_check: ok`; see [database-backups.json](../../release/genesis2/metadata/database-backups.json).
- The frozen test command `py -3.14 -B -m unittest discover -s tests -q` recorded 161 tests, 0 failures, errors or skips, exit 0 and 7.889 seconds at 14:38:20Z. See [test output](../../release/genesis2/metadata/test-output.txt) and [run metadata](../../release/genesis2/metadata/test-run.json).

The prior root audit reported that the remote was previously public and later changed to private; historical public copies may still exist. This handover did not independently contact the remote or establish the absence of copies.

An independent audit found that a fixture rescheduled to a different date could
be conflated with another event. The bounded repair detects same-source,
competition and participant identities with conflicting dates, quarantines the
ambiguity only after the conflicting evidence becomes usable, and propagates
that uncertainty through forecasting, memory, evaluation and adaptation. Tests
include `test_public_results.py`, `test_cognition_evaluation.py` and
`test_cognition_adaptation.py`. These checks cannot distinguish every genuine
repeat fixture from a reschedule without additional identity evidence; real
cross-source mappings remain unresolved.
