# Frozen forecast-preservation reference

`jobs-ed78.py.txt` is the exact, non-executable test-data copy of
`src/dragonhydra/jobs.py` at historical source
`ed78fab282599a181d4254ab65a2fc2eaa5b7f50`. SHA-256:
`bccb8f08caf58df333942bcc5c527def1a18c1acd09cc01f6dadb95565c16296`.

The preservation tests parse its SQL schema through AST; they never import or run
this historical implementation. This preserves the original forensic hash pin
while current jobs add SQL-research operations. A separate assertion verifies
the current jobs schema still matches this reference. No historical source,
receipt or Git ref is changed. Keeping the data in source avoids requiring a
private laboratory worktree or Git history when running these fixture tests.
