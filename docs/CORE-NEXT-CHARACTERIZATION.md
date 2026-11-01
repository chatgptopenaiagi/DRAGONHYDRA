# Baseline and candidate behavioral characterization

`scripts/core_next/characterize.py` runs the locked A9 source and CORE NEXT source
in separate processes. Each process imports only its selected tree. The baseline
must be the lab's `baseline-source`; the candidate must be this clone. No original
DRAGONHYDRA working tree, installed service or private credential is used.

Each lane requires a fresh state directory under the explicit lab. It copies the
same sanitized SQLite snapshot into that directory and verifies the common
snapshot hash before and after the run. API construction uses a synthetic local
Bearer credential, `start_worker=False` and TestClient. No service is installed or
started. Explicit `run_once` processes only jobs created by the harness.

The clock exposed through the product/API/job seams is fixed at
`2026-11-01T12:00:00.000000Z`; the random seed is 1729. Retained match/event dates,
provenance and scores are not rewritten. External socket connections and HTTP
acquisition helpers are rejected. Numeric loopback socket connects are permitted
only because Windows asyncio creates its private wakeup socketpair that way;
outbound HTTP helpers remain blocked, including local-model HTTP paths. No model
configuration or inference is requested.

## Actual proof groups

The baseline receipt records 33 semantic groups. They cover authorization and
validation errors; complete canonical match IDs/counts and source names; first and
second pages; teams/competitions; a real retained finished match and its team/form/
standings; retained odds/history and optional event/lineup/statistics responses;
finished-match forecast abstention; deterministic explanation job/idempotency and
retained evidence; JSON/CSV/XLSX export job/idempotency and actual downloaded
contents; and completed-job persistence after creating a new application over the
same private state. Read browsing creates no jobs, and canonical retained rows
remain byte-equivalent as normalized JSON after explicit jobs.

Counts and representative IDs come from the snapshot, with no assertion hardcoded
to 760. The observed A9 run contained 760 matches. An empty retained odds response
does not establish odds-pricing execution. A finished-match abstention does not
establish future-result prediction accuracy. Dedicated mathematical, module and
dependency-isolation tests remain separate acceptance.

Each artifact's actual downloaded SHA-256 is checked against its job result. JSON
and CSV are compared as parsed contents. XLSX is opened with openpyxl and compared
by sheets/cell values, since ZIP container timestamps are not domain behavior.
Job IDs and their URL/filename references are replaced consistently by named
placeholders. Only listed job operational times and intentional health version/
source identity fields are excluded; event dates, provenance, probabilities,
unavailability reasons and output data remain in the comparison.

Comparison additionally replaces only each receipt's exact private-state root
prefix with the same marker. Export result locations must reside in different
baseline/candidate state directories; their relative export paths still compare.
The first final comparison found only these six path leaves in four groups. Its
failed receipt remains intact; the subsequent comparison adds this explicit
isolation normalization without altering either frozen lane receipt.

Candidate receipts additionally record every imported product Python source-file
hash and reject source changes during a run. The supplied source commit identifies
the checkout base; these file hashes bind any still-uncommitted implementation.
Baseline goldens are written before comparison and output files refuse overwrite.

## Run and compare

Use the existing isolated `tools-env` interpreter and explicit paths under the
lab. Each invocation is a separate process:

```powershell
python -B scripts/core_next/characterize.py run --lane baseline `
  --lab <lab> --source <lab>/baseline-source --snapshot <snapshot.sqlite3> `
  --state <fresh-baseline-state> --output <new-baseline-receipt.json> `
  --source-commit <locked-A9-commit>
python -B scripts/core_next/characterize.py run --lane candidate `
  --lab <lab> --source <CORE-NEXT-clone> --snapshot <same-snapshot.sqlite3> `
  --state <fresh-candidate-state> --output <new-candidate-receipt.json> `
  --source-commit <candidate-checkout-commit>
python -B scripts/core_next/characterize.py compare --lab <lab> `
  --baseline <frozen-baseline-receipt.json> --candidate <candidate-receipt.json> `
  --output <new-comparison-receipt.json>
```

The first baseline attempt was a harness-boundary failure: the blanket socket
guard intercepted the asyncio self-pipe before any API request. Its failed receipt
and private state remain in the lab. The corrected baseline `r2` passed. The first
candidate lane preceded the explicit context/ports refactor and is historical;
the later candidate `r2` ran after the explicit context/ports refactor. Comparison
`r3` passed all 33 semantic groups with zero differences against immutable baseline
`r2`, after the narrow private-state-prefix normalization described above. Both
lanes observed 760 matches from two captured source files. Exact hashes, source
file bindings and actual artifact checks remain in the private lab receipts.

This proves source API/domain behavior on a common retained-data snapshot. It is
not native-client, installed-service, fresh-provider, inference, clean-machine or
OS-reboot acceptance. Live Joomla identity/cookies and Control Center rendering
must be verified separately against the isolated installed candidate.
