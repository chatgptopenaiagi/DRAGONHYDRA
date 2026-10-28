# Successor mission

1. Open the actual checkout at `C:\xampp\DRAGONHYDRA` and read `START-HERE.md`.
2. Verify the checkpoint tag and commit against the separately published release
   manifest; do not assume the pre-existing GitHub `main` is this checkpoint.
3. Follow `RESTORE-INSTRUCTIONS.md`; verify hashes, SQLite integrity and source
   provenance before using restored datasets or model memory.
4. Run the tests and inspect the unfinished code and `KNOWN-ISSUES.md`. Reuse
   functioning modules rather than recreating them.
5. Continue at the first unmet dependency in `REMAINING-WORK.md`: real historical
   data → past-only team features → trained neural classifier → chronological
   comparison → persisted artifact → reload verification → future prediction →
   compatible market analysis. Neural training is not yet implemented or verified.
6. Keep provenance, original data representations, availability clocks,
   transformation versions, uncertainty, append-only corrections and feedback
   tasks across all boundaries. A historical file captured now cannot prove it
   was operationally available in the past. Verify actual execution and test
   results and report limitations and sample sizes.

The recovery archive also retains source snapshots and research evidence from
earlier DRAGON donor worktrees. They are distinct from this checkout; inspect
their documented provenance before reusing their contents.
