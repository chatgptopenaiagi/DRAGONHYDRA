# Scientific Validation Spine — Phase A

Active roadmap: **V1**. Maturity: **EXPERIMENTAL**. This block starts the cross-cutting scientific track; it does not complete V2 or V9. Baseline `v0.1.0-alpha` remains at `4d1b4b3d1960cdd047a9c857aafdc544961b9426`. Work is isolated on `feature/scientific-validation-spine` and must be reviewed before merging.

## Observed data

The existing CLI ingestion retained 380 2023–24 English Premier League fixtures from OpenFootball, normalized in append-oriented SQL Server. The original source bytes survive in the local handoff download store with their SHA-256. Browser handoff ingestion also retains validated artifact bytes under immutable checkpoint artifacts. These are sufficient to rerun the current parsers; retention is application-controlled, not WORM storage. No old capture timestamps or records are changed.

One additional exact OpenFootball URL is reviewed for prospective collection: [2026–27 English Premier League JSON](https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/en.1.json). The upstream [README](https://raw.githubusercontent.com/openfootball/football.json/master/README.md) documents raw JSON access and public-domain data; [LICENSE.md](https://raw.githubusercontent.com/openfootball/football.json/master/LICENSE.md) provides CC0. The review preserves both hashes and extends the existing policy, not the provider count. Robots is checked separately on every fetch. Upstream update cadence is not a freshness guarantee.

A genuine current snapshot was acquired at **2026-09-24T19:35:56.703350+00:00**, containing 380 fixture entries. This is one STRICT_PIT snapshot of source state at capture, not 380 genuine historical observations at the individual match dates. Its 55,359 raw bytes have SHA-256 `bb91f0ab3e8359df163bb9ec98549bfed85e200dd4c32f3bd606b5890d932dd2`. No current odds were collected. An earlier schema/name mismatch remains a SOURCE_UNAVAILABLE failure receipt; one explicit bounded recovery produced the successful capture.

New prospective raw bodies use the small content-addressed local store `runtime/raw/<sha256>`. Receipts retain source, actual observation/retrieval/availability times, media type, byte count, parser version, policy version/hash, robots result and raw hash. The ledger is local acquisition evidence, not a replacement owner for normalized SQL intelligence. Files use exclusive creation; existing raw/policy content is verified on reuse. Hashes detect alteration when checked; they are not signatures or external time attestations.

## Reconstructed historical assumptions

STRICT_PIT permits only genuinely captured/ingested information available by the decision time. A match imported in 2026 is not strict history in 2023. RECONSTRUCTED_PIT retains `availability_mode`, policy/version, reason, confidence and source alongside unchanged actual capture times. UNKNOWN availability is excluded from every decision horizon.

The historical demonstration uses a declared **UTC calendar-day proxy**, because source kickoff timezone and original publication timestamps are not proved. It assumes the fixture schedule known one day before its recorded date and the final result available two days after that date. These are low-confidence reconstruction assumptions, not observed timestamps or a verified final-whistle delay. The decision horizon is `DAY_START_UTC_PROXY`, not a claim of real kickoff or closing-odds availability. Corrected final scores/schedules available only in the later file can still create historical reconstruction bias; this dataset does not provide their original revision histories.

Contracts also support explicit final-whistle-plus-publication-delay policies when that event time is known, evidenced provider publication/snapshot timestamps, and UNKNOWN when no defensible assumption exists. Merely knowing kickoff does not prove closing odds existed then. Five named horizons (24h, 6h, 1h, 15m before kickoff and kickoff) and generic timestamp horizons are available for future datasets with appropriate evidence.

Historical replay predictions retain simulated `prediction_issued_at`, decision horizon, fixture/model version and feature/evidence snapshot IDs. They also retain actual `computed_at` and `HISTORICAL_REPLAY`; a replay is never represented as a prediction genuinely issued in the past. Input assumption metadata survives through evaluation output.

## Entity identity

The minimal core supports competition, team and fixture IDs, immutable versioned provider crosswalks, review/confidence states and explicit UNRESOLVED results. Ambiguous names are not guessed. Effective intervals and actual mapping-recording time are separate. Fixture ID excludes scheduled datetime; postponement appends a schedule revision while preserving identity.

OpenFootball does not supply stable IDs in these files. The demonstration uses scoped, declared team names and season/round/home/away keys. These are reconstructed mappings recorded now, not globally verified cross-provider IDs. Players and database-wide entity migration remain deferred. The registry is a derived experiment artifact with replayable serialization.

The minimal entity schedule projection stores schedule versions and their availability timestamps; it is not a complete scientific evidence envelope. Evaluation must use the separate typed Availability contract with provenance and assumptions. The demonstration keeps historical schedules in FixtureTarget with full reconstruction metadata and does not treat the bare entity schedule projection as STRICT_PIT input.

## Model and benchmark

Two simple baselines share one typed walk-forward protocol: BASELINE_A uses smoothed historical league home/draw/away frequencies; BASELINE_B uses home-team home results and away-team away results shrunk toward the league prior. A uniform one-third forecast provides a declared comparison benchmark. No neural network, GPU training, Elo, Poisson, simulation or tribunal is added.

Training proceeds chronologically using only results completed and available by each decision horizon; all matches at the same horizon use the same eligible past. The protocol declares evaluation period, temporal mode, horizon, minimum training sample, smoothing, model/version and calibration bins. No random split or parameter search is used. Final outcomes are scoring targets, never inputs to their own predictions.

Metrics include natural-log loss, ranked probability score with fixed HOME/DRAW/AWAY order and division by two, multiclass Brier score with per-class components, and per-class calibration bins with counts/mean probability/observed frequency. Accuracy is secondary. Brier class components are not a Murphy reliability/resolution decomposition. Results and counts are recorded in the [safe scientific summary](evidence/scientific-spine-summary.json).

## Result, uncertainty and limitations

The retained one-season replay uses 1 competition, 20 teams, 380 fixtures and 401 declared crosswalk records. It scores 321 fixtures after 59 warm-up exclusions, producing 963 replay forecasts across the two baselines and uniform benchmark. Historical STRICT_PIT eligible records: **0**.

| Model | Log loss | RPS | Multiclass Brier |
| --- | ---: | ---: | ---: |
| BASELINE_A: league empirical | 1.058500 | 0.234043 | 0.639600 |
| BASELINE_B: venue-aware empirical | 1.021001 | 0.214819 | 0.606150 |
| Uniform benchmark | 1.098612 | 0.241433 | 0.666667 |

Lower is better for these loss functions within the same protocol. The safe summary includes all class-wise calibration buckets, their counts, mean probabilities and outcome frequencies, including empty buckets. Formulas follow the [log-loss and Brier definitions](https://scikit-learn.org/stable/modules/model_evaluation.html#log-loss) and the [ranked probability score definition](https://search.r-project.org/CRAN/refmans/verification/html/rps.html); no scoring library dependency was added.

Validation on Python 3.14.7: **233/233 portable tests** and **276/276 full local tests**, zero failures/errors/skips. This adds 69 tests to the frozen 207-test baseline. Dual database least-privilege/connectivity, GPU correctness and Joomla HTTP checks remain healthy; Web-to-SQL and bridge regressions pass. An initial portable invocation correctly rejected the newly created demo test class until it was added to the explicit tier manifest; that log is preserved. No failed test was skipped or weakened.

Every historical result is labelled **DEMONSTRATION_ONLY**, **RECONSTRUCTED_PIT**, and **INSUFFICIENT_SAMPLE_FOR_STRONG_INFERENCE**. One season cannot establish small model differences reliably. Calibration bins expose their sample counts; no statistical significance, confidence interval, model superiority, market beating or profitability is claimed. No real market benchmark exists. Negative results are retained.

The first prospective capture starts genuine evidence accumulation. Periodic invocation is supported, but no unattended scheduler or multi-day operational history is established in this block. Gate A (sustained prospective collection) is therefore PARTIAL. Gate B requires the recorded successful walk-forward/test result. Gate C (complete clean-machine laboratory reproducibility) remains NOT_DEMONSTRATED; portable Windows/Ubuntu CI establishes only the portable code tier.

The Desktop browser limitation `Browser is not available: iab` remains historical truth. Genuine Desktop success is unverified; no repeated repair attempt or Playwright dependency is introduced. The filesystem handoff remains valid and optional for research producers.

MEDUSA's deterministic schema/normalization/timestamp/content-type/deduplication boundary is retained. Entity resolution is a separate contract; long-term source scoring, historical conflict scoring and quarantine operations remain future concerns. ACCEPT_WITH_WARNING is unchanged to avoid migration; existing structured reasons remain available. Future ACCEPT/QUARANTINE/REJECT simplification must preserve those reasons.

## Run and preserve evidence

On the configured local machine, use Python 3.14 and set `PYTHONPATH` to the checkout's `src` directory. The prospective command performs at most one daily attempt, with no automatic retry:

```powershell
python -m dragonhydra.science.prospective
```

An explicitly invoked `--retry-failed` permits only one recovery after a failed attempt (at most two attempts in a rolling day). The cross-process lock fails closed; after a crash, inspect the unfinished attempt before removing a stale lock. Repeated invocation returns NOT_DUE and does not fetch. Policy expiration or unavailable/schema-changed sources produce durable failure receipts. A future owner-managed scheduler should invoke this bounded command and monitor receipts; no CI collector or background service is installed here.

Use [test tiers](TESTING.md) for portable and local regression. The historical demonstration CLI is `python -m dragonhydra.science.demo --help`; it writes only a new local checkpoint and reads the existing retained dataset. It does not update SQL, MariaDB or Joomla.

**LOCAL FORENSIC EVIDENCE:** `runtime/checkpoints/scientific-spine-a-20260924T192859Z-c463e0ca`, `runtime/prospective/openfootball-en.1` and `runtime/raw`. Full reports, reconstructed inputs and source bytes stay ignored. **REPOSITORY-SAFE EVIDENCE:** [scientific-spine-summary.json](evidence/scientific-spine-summary.json). Old checkpoint bytes and the baseline tag remain unchanged.

## NEXT_EXACT_ACTION

Commission and verify daily invocation of the one lawful OpenFootball prospective collector, including NOT_DUE, policy expiry and failure monitoring, then demonstrate a second-day immutable snapshot. Preserve genuine clocks. After sustained collection is established, the next modeling block can add independent Poisson and Dixon–Coles baselines to the same declared evaluation protocol. Do not begin broad source expansion or advanced modeling.
