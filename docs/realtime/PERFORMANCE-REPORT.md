# Synthetic performance measurement

The standalone benchmark is `scripts/benchmark_genesis6.py`. It uses the existing
tools environment Python, standard library and the isolated research service.
No installed Windows service, provider, HTTP endpoint, SQL Server, real dataset
or AI transport is exercised. The benchmark's owned SQLite stores contain only
fresh fictional events. Output must be a new directory below this lane's
`evidence` directory; existing evidence is never overwritten.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe' scripts/benchmark_genesis6.py --output ..\evidence\benchmark-r1
```

`scripts/Verify-Genesis6.ps1 -OutputDirectory <fresh-evidence-path>` runs the
realtime test modules and pure benchmark guards with process-only PYTHONPATH.
Add `-Benchmark` to execute all three benchmark sizes. No execution-policy or
machine configuration is changed by this wrapper.
Both receipts record Git HEAD, whether the working tree has changes, and hashes
of selected input files. Changing a selected input during execution fails the
run. Git HEAD alone is not presented as the identity of uncommitted code.

For each size 100, 1,000 and 10,000, both modes ingest the exact same input bytes.
Smaller cases are prefixes of the same deterministic fixture. Kickoff/resumption
establish second-half play; most observations are same-clock possession changes
that the configured goal model does not use. Periodic clocks, four possible goals
and one card create supported mathematical input changes. Every event must be
accepted in both modes. Input hashes, final-state hashes and shared revision
checkpoints make the comparison inspectable.

The incremental mode recomputes when supported inputs change. The comparison
mode forces recomputation after every accepted event, with otherwise identical
configuration. Both disable automatic investigations and dense score-row
persistence. Dropping dense persisted rows does not change scalar probabilities.
Common checkpoints compare full-time results and all non-dense horizon output,
including probabilities, goal vectors/tails and uncertainty. A drift above
`1e-12`, a changed source input, an unaccepted event or an AI investigation fails
the run. A forecast's state revision can remain earlier after an irrelevant event;
the current supported inputs and scalar forecast must still agree.

The report measures actual per-ingest p50/p95/p99/mean/max latency, aggregate wall
and CPU time, events per second, traced Python peak allocation, SQLite bytes,
stored forecast updates, semantic relevance counters and AI investigations.
Aggregate timing includes initialization and checkpoint reads; per-ingest timing
does not. Event generation and test-report formatting are excluded. Numeric
caches begin cold in each mode. Queue depth is reported only if exposed by the
service; the caller always has at most one synchronous ingestion in flight.

These are single local synthetic runs, with tracemalloc overhead, in a fixed mode
order. OS/filesystem caching, antivirus and machine load can affect timing. They
do not establish production capacity, replay wall-clock speed, network latency,
real predictive quality or a calibration result. Store semantic "avoided" counters
describe relevance decisions; the report separately counts actual stored forecast
updates so the forced mode is not credited with work it still performed.

The initial pure-math microbenchmark (before the service benchmark) measured
100/1,000/10,000 direct `predict` calls at roughly 0.023/0.217/2.182 seconds on
this Windows host. These calls deliberately recomputed even when only revision
and irrelevant possession metadata changed. This is a scoped working-tree
observation, not a frozen-source release witness. The final service benchmark
results belong in their external `BENCHMARK.json`; this document does not invent
or predeclare them.

The first 100-event service probe is preserved under
`evidence/benchmark-preliminary-r1`. It failed the explicit source-stability
guard when `service.py` changed during the run; it is not a successful benchmark
witness. The inputs and owned stores remain available for inspection. A later
run must use a different evidence directory and stable selected source bytes.

## Measured service benchmark R2

`evidence/benchmark-r2/BENCHMARK.json` completed with `PASS` and process exit 0.
Its SHA-256 is
`cc2fcbb66e1b762c9c59221523087f8f0d4d2a270a2ae62d688b0460615f2dc7`.
The frozen plan SHA-256 is
`b360967b7423ecf089c00922b31dc93e394af342a430ea2119ee7af6ce0e0f92`.
Standard output and the empty standard-error file are preserved beside the
directory as `benchmark-r2.stdout.txt` and `benchmark-r2.stderr.txt`.

Measurement identity is the plan's twelve selected runtime/script file hashes,
which stayed unchanged through both modes of all three cases. Recorded Git HEAD
was `db8414ff6a08bd0c85310564771475e71d00e8a4` with working-tree changes present.
The selected hashes identify the measured implementation; HEAD alone does not.

| Events | Mode | Forecast updates | Wall s | CPU s | Events/s | p50 ms | p95 ms | p99 ms |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | Incremental | 3 | 1.188 | 0.719 | 84.198 | 10.984 | 12.982 | 22.366 |
| 100 | Forced | 100 | 2.129 | 1.656 | 46.969 | 20.351 | 23.577 | 26.295 |
| 1,000 | Incremental | 13 | 13.005 | 7.750 | 76.896 | 11.736 | 18.726 | 28.026 |
| 1,000 | Forced | 1,000 | 20.317 | 15.391 | 49.220 | 19.511 | 25.166 | 29.136 |
| 10,000 | Incremental | 107 | 119.681 | 72.703 | 83.555 | 11.300 | 15.533 | 22.752 |
| 10,000 | Forced | 10,000 | 213.867 | 154.641 | 46.758 | 19.970 | 28.893 | 41.859 |

| Events | Mode | Traced Python peak MiB | Final SQLite MiB |
| ---: | --- | ---: | ---: |
| 100 | Incremental | 0.592 | 0.387 |
| 100 | Forced | 0.454 | 1.531 |
| 1,000 | Incremental | 1.232 | 2.629 |
| 1,000 | Forced | 1.221 | 14.297 |
| 10,000 | Incremental | 7.176 | 27.957 |
| 10,000 | Forced | 6.953 | 144.953 |

All events were accepted. Final state hashes matched between modes, and maximum
scalar/distribution drift was exactly zero at 3, 14 and 112 shared checkpoints
for the respective sizes. Both modes observed the same semantic relevance counts:
3/13/107 relevant and 97/987/9,893 irrelevant events. The incremental mode avoided
97/987/9,893 actual forecast updates; the forced mode avoided zero. Synchronous
maximum queue depth was one, terminal depth zero, and AI investigations zero in
every run.

The measured 10,000-event wall-time ratio was 1.787 in favor of the incremental
mode. Its smaller persisted history follows directly from storing 107 forecasts
instead of 10,000 while preserving all accepted observations/states. These
measurements establish equivalent configured-model output on this fixture and
quantify its avoided work. They do not establish predictive accuracy, utility of
ignoring possession in another universe, or production capacity. Tracemalloc
measures traced Python allocations; native SQLite memory and total process RSS
were not measured. The single-run, fixed-order and local-load limitations above
continue to apply.

After this terminal measurement, the authenticated router enum was extended to expose `clock_sensitive` and the already implemented `universe` scenario. The benchmark directly used RealtimeService and did not import that router. Its measured model/service/store/bridge bytes remain unchanged. The final-source binding records the one unused-router input difference instead of relabeling the original measurement as an exact twelve-file final-source run. Appropriate API regression tests pass separately.

The closing whitespace check also removed a trailing blank line from `realtime/__init__.py`; its parsed Python AST and component constants are unchanged. This byte-level formatting difference is recorded separately from the HTTP enum change.
