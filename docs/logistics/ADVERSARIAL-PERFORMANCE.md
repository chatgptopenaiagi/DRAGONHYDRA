# Adversarial and performance scope

All records in these checks are invented. The suite creates new disposable
inventory and SQLite journals; it reads no historical installation database,
provider, network endpoint or Windows service. It changes no earlier forecasting
kernel. This document records development checks, not release acceptance.

`tests/test_logistics_adversarial.py` covers exact duplicate versus conflicting
operations, negative/insufficient stock, physical capacity, transit conservation,
nonfinite costs and probability vectors, zero acquisition budgets, unavailable
information, reversed/future observation times, hidden fields, censored sales,
TRAIN/VALIDATION group separation, model availability, independent serialization,
immutable journal records, restart persistence and rollback after actual journal
writes. Two independently constructed service instances race from the same
revision through separate SQLite connections: exactly one may commit. Public
reads must reuse committed views without forecasting or actions.

Development probes found two concrete defects before these tests: reversed
observation chronology admitted a future observed day, and serialized world/cache
containers shared live references. The owner corrected shared chronology checks
and deep copying. The external `adversarial-discovery-r1` evidence preserves the
observed pre-fix probe summary; it is explicitly a summary, not a reconstructed
traceback. A benchmark self-test also exposed and corrected a reporting-only
attempt to sum the cost unit's text label with numeric components.

## Reproducible benchmark

Run the existing Python environment from this source directory:

```powershell
& C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe scripts\benchmark_genesis62.py --self-test
& C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe scripts\benchmark_genesis62.py --output <fresh-lane-evidence-subdirectory> --sizes 100 1000 10000
```

The driver refuses an existing output directory and writes a source-hashed plan
before running. It compares cached and uncached demand horizons 1 and 5 for both
retail locations plus lead time after every actual inventory event. Every
100-event cohort starts a new seeded virtual world. Ordinary events reserve or
release one warehouse unit, falling back to a supplier unit when warehouse ATP is
zero; each 25th event advances the world, demand, orders, clock and history.
Unavailable stock at both nodes is an explicitly counted skip. Exact full
forecast/disclosure hashes, public input hashes and physical inventory hashes
must agree at every corresponding checkpoint. Both modes run the same internally
cached simulation; only the external forecast request cache is bypassed in the
reference. This isolates forecast cache effects without comparing different
inventory trajectories.

Independent lightweight wrappers count real demand and lead kernel calls and
cross-check cache accounting. The driver reports median/p95/p99 latency per five
forecast requests (wall and process CPU), aggregate wall/CPU time, Python allocation peak, hits, actual
inventory operation rows, status counts and conservation checks. Forecast latency
excludes world construction, inventory mutation, snapshot creation and result
hashing. Aggregate time includes them. Tracemalloc and instrumentation run in
both modes. Internal Poisson memoization resets at each mode's start. There is
one sequential cached-then-reference run per size; no repeated-run confidence or
universal speed claim follows.

Per-checkpoint process CPU observations on this Windows host occur in coarse
15.625 ms increments: the canary's median is zero in both modes. This is clock
quantization, not zero computational work. Aggregate process CPU is more useful
than individual checkpoint CPU percentiles for this short-request workload.

The acquisition price is zero because this workload acquires no information.
Forecast execution is additionally priced at the declared virtual rate of 0.001
credit per actual kernel invocation. These operation credits measure a configured
computation cost, not commercial profit. The simulator's separate seven-part cost
ledger is reported without changing its operation prices.

The first 100-request canary passed exact distribution and physical checkpoint
equivalence: 52 accepted inventory requests and 48 explicitly skipped reservations
after the warehouse ran out of available stock, with 81 underlying inventory
operation rows. It made 25 cached kernel calls versus 500 reference calls. Its measured
median five-request latency was 1.883 ms cached and 4.427 ms reference under
tracemalloc. That r1 development canary remains historical. Workload r2 explicitly
adds supplier fallback to exercise actual inventory events even after warehouse
depletion. The r2 canary accepted all 100 requests without skips (48 releases,
24 warehouse reservations, 24 supplier reservations and four world steps),
produced 129 physical inventory operation rows, and passed all 100 conservation
and exact equivalence checks. It made 25 versus 500 kernel calls; median
five-request latency was 1.613 ms cached and 4.602 ms reference. Each canary is
bound to its own recorded source pins. The final
100/1,000/10,000-event run is **NOT_RUN** until source stabilization and owner GO.
No service, SQLite throughput, UI, real-world calibration or decision superiority
is established by this in-memory cache workload.


## Final qualified execution — 2026-11-07

The earlier NOT_RUN/held statements above describe the pre-final checkpoint.
Actual final receipts now pass: source110 logistics tests plus12 package tests,
all220 prior tests, and342 extracted-package tests. Final100/1000/10000 event
workloads accept all requests with zero skips and exact full reference equality.
Cached/reference calls are25/500,217/5000 and2142/50000. The10k medians are
2.254/5.755ms per five-request checkpoint; shared-host and tracing limitations
are recorded. This is not API throughput or proof of predictive improvement.
The27-check source study,28-check packaged replay,64-check package browser
journey and28-check real-process restart pass. First45 final policy records
match exactly; historical failure evidence is retained. Read the delivery report
for measured mixed research findings and explicit preservation/privacy scope.
