# A9 to CORE NEXT extraction and verification

Locked baseline: `genesis-a9-20261101`, commit
`2e6520d5b6a7874881e5de85dbb6ececaef11d8f`. The independent source and lab are
`C:\xampp\DRAGONHYDRA-CORE-NEXT` and `C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB`.

| Before | After | Compatibility boundary |
|---|---|---|
| Product retained-data/identity/navigation methods | DataEngine owns their method bodies | Product public methods delegate through composition |
| Product.odds | OddsEngine plus injected data/provider ports | Same source scope, quote provenance and timestamp distinctions |
| Product.predictions | PredictionEngine plus injected models/data | Same four models, ensemble and abstentions; finished results never become historical forecasts |
| Product.explanation | AIEngine deterministic evidence summary | Same output; optional inference remains explicit and labelled |
| Jobs.execute conditional handler selection | Explicit-callback JobDispatcher | Same supported job kinds; queue claims/retries/transactions unchanged |
| API direct local-AI package construction | AIEngine injected package adapter | Frozen package/2 and selected-context package/3 contracts preserved |
| Generic cookie | Unique installation-derived cookie | Deliberate isolation change; old-origin cookies are ignored and preserved |

Memory and evaluation engines use existing immutable-record contracts. Explicit
`PredictionEngine.persist()` computes a current eligible forecast, then writes
each genuine model run before its prediction through MemoryPort. Evaluation uses
only those actual records and subsequently retained outcomes. It never calls
`runtime.prepare()` on a read, manufactures a prior prediction for a finished
match, changes historical timestamps or labels retrospective analysis as a
prospective forecast. Existing CLI research/import orchestration remains separate.

`tests/core_next/characterization.py` was run against the isolated locked A9
source to generate `fixtures/a9-mathematics.json`. It fixes fictional inputs,
UTC clock, UUID and random seed; records baseline source hashes and hashes of
complete model, market-signal and risk-simulation reports; and preserves explicit
probabilities, scoring and validation outcomes. The candidate independently
matches these outputs. This is synthetic algorithm characterization, not
real-world predictive performance evidence.

`tests/core_next/test_kernel.py` covers graph/schema/capability validation,
optional absence, independent injected ports, lifecycle/expiry, authenticated
status without state writes/probes, unique cookies/logout, real API dispatch and
genuine fictional pre-event persistence followed by later-outcome evaluation.
Existing API, worker claim fencing, cognition, odds/scenario, local-AI and
StatsBomb suites remain relevant. Only three inherited cookie fixtures changed
to select their application's scoped cookie; their authorization assertions
remain intact. Execution receipts and regression logs belong in the private lab.


## Installed-runtime repair checkpoint

The unpublished03c6d82 checkpoint passed Linux domain/HTTP/export/status checks,
but its immediate graceful restart exposed POSIX TIME_WAIT binding. The selected
A9 source already contains the verified packaging transformation
`packaging/linux-native/server_patch.py` (`linux-listener-reuse-v1`). CORE NEXT
promotes that existing fix into the shared server: POSIX SO_REUSEADDR, unchanged
Windows SO_EXCLUSIVEADDRUSE, no SO_REUSEPORT, and preserved bind errno. The input
A9 baseline lock remains immutable. A new source freeze rebuilds all application
metadata and packages; the failed checkpoint/receipts are retained privately and
no published tag was moved.

Explicit local-model configuration writes also refresh the bounded cached AI
configuration observation without inference. Counter batches retain separate
sample/expiry timestamps, so successful ordinary reads do not renew old metrics.
