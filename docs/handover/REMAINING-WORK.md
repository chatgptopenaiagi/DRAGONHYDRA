# Remaining work

1. Capture and validate additional source snapshots with provider and settlement identity, actual receipt/persistence clocks and verifiable original quote times. Retain raw source bytes, corrections and lineage. Resolve fixture crosswalk ambiguity before model-versus-market calculations.
2. Strengthen storage evidence to establish a conservative, verifiable receipt-visibility boundary for operational STRICT_PIT replay, including late arrivals, crashes, corrections and exact-cutoff tests. Preserve the existing receipt-bounded labels until proven.
3. Collect genuine future outcomes for persisted forecasts, attach them only after availability and score them with Brier/log loss, calibration, coverage, sample size and variance. Do not present the present-knowledge holdout as prospective performance.
4. After sufficient comparable recorded predictions and outcomes, verify adaptation on the same fixture cohorts, compare with stable baselines and run ablations. Preserve negative and inconclusive results.
5. Expand calibrated probability models, coherent multi-market settlement handling, real multi-provider streams and actual live game-state identity. Add a neural model only when implemented and validated; current code is statistical.
6. Design independently scoped ledger, staking, drawdown, hedging and correlation-aware risk features. No automatic wagering is currently provided.
7. Validate clean-machine setup, backup restoration, source licensing, security and any SQL Server integration as separate evidence-backed work. Respect existing untracked project and evidence trees.

## Acceptance details

| Priority and task | Current status and files | Dependencies and acceptance | Existing and missing tests |
| --- | --- | --- | --- |
| P0: receipt visibility and replay | Partial; `market_store.py`, `public_results.py`, `cognition/memory.py` | Prove commit visibility and exact-cutoff, correction and crash behavior before calling operational replay STRICT_PIT | Temporal tests exist; multi-connection visibility and crash tests are missing |
| P0: fixture identity | Partial; `public_results.py`, `cognition/runtime.py` | Preserve rescheduled-match ambiguity and require evidence-backed cross-source mappings | Ambiguity quarantine tests exist; broader real-world reschedules and cross-source correction cases are needed |
| P1: operational outcomes | Partial; `cognition/memory.py`, `cognition/evaluation.py` | Attach outcomes only when available, evaluate actual persisted prior predictions; record coverage, variance and cohort | Memory and evaluation unit tests exist; a prospective end-to-end scored cohort is missing |
| P1: past-only features and neural classifier | Not implemented; `cognition/models.py` is statistical | Versioned features, training, updated weights, saved artifact, reload, untouched chronological holdout, baselines and independently assessed calibration | Statistical model tests exist; neural training, leakage, save/reload and holdout tests are missing |
| P2: compatible markets and risk | Partial; `market_signals.py`, `estimate_store.py`, `research.py` | Demonstrably compatible event, line and settlement mapping; verified timed quotes; explicit policies and model uncertainty | Synthetic odds and risk tests exist; live provider, real timestamp alignment and settlement integration tests are missing |
| P2: research and watcher feedback | Partial; `research.py`, `watch.py`, `cognition/research.py` | Bound acquisition budgets and show measured gap resolution with eligible evidence | Local polling and research tests exist; triggered inference and acquisition feedback tests are missing |
| P3: paper ledger and portfolio | Not implemented | Position identity, exposure, settlement and bankroll reconciliation under explicit assumptions | Ledger, correlation and reconciliation tests are missing |
| P3: infrastructure and broader feeds | Partial; `market_store.py`, `public_results.py`, `football_data.py` | Proven recovery and versioned migrations; validate optional SQL Server and provider integrations separately | SQLite tests exist; real provider and SQL Server integration tests are missing |
