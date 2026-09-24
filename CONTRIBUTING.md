# Contributing to DRAGONHYDRA

Work incrementally on one coherent, reviewable block. This is an experimental
laboratory maintained by its owner and collaborating engineers/agents. `main`
is the stable development trunk; use `feature/<name>` for a risky isolated block.
No GitFlow or mandatory process bureaucracy is required.

## Start with the architecture

Read [AGENTS.md](AGENTS.md), [README.md](README.md), the
[master roadmap](docs/DRAGONHYDRA_MASTER_ROADMAP.md),
[roadmap status](docs/ROADMAP_STATUS.md), [progress](docs/PROGRESS.md) and
[decisions](docs/DECISIONS.md) before large modifications. V1 is active. A plan,
contract or synthetic demonstration does not establish implementation of a later
version. Preserve the owner-authored `2–3` source and `3–5` item ranges exactly.

Python **3.14** is required (`>=3.14,<3.15`). Do not silently downgrade it or
replace the measured local PyTorch/CUDA stack to satisfy an optional dependency.
Put machine-specific paths in configuration or launch arguments. Portable tests
must run without local credentials, SQL Server, MariaDB, XAMPP, CUDA or Desktop.
See [test tiers](docs/TESTING.md) for exact commands and boundaries.

## Preserve the three laws

Also preserve the fourth practical law, evaluation discipline: compare predictive changes against simple baselines using a declared chronological out-of-sample protocol. Keep STRICT_PIT and RECONSTRUCTED_PIT explicit through outputs, retain actual capture clocks, and document every availability assumption. See the [scientific spine](docs/SCIENTIFIC_VALIDATION_SPINE.md). No architecture or model sophistication alone counts as predictive progress.

- **Provenance:** retain source identity and URL, retrieval and observation times,
  hash where possible, parser/version, confidence, verification and rights state.
- **Temporal discipline:** distinguish event, observation, availability,
  ingestion/knowledge and prediction times. Historical evaluation must never see
  future information. Corrections append explicit revisions; never silently
  mutate historical knowledge or backfill availability from event time.
- **Feedback-driven research:** additions should support the future loop that
  identifies uncertainty, researches the missing information, validates it and
  recalculates. Do not expand acquisition merely to collect more data.

HYDRA collects; MEDUSA validates; the Pyramid calculates; tribunals evaluate.
Keep those responsibilities distinct. Each dataset has one primary owner; a new
table or replica needs an explicit ownership and retention rationale.

## Evidence required for a change

- Run the relevant portable unit/contract/temporal tests. Run local integration
  or machine/browser tiers only when the change affects those boundaries and the
  authorized environment is available. Report failures and skipped tiers openly.
- A new source requires independent terms/license and robots review, attribution,
  timestamps, rate policy, failure states and measurable value. Uncertainty about
  rights blocks ingestion. Preserve the [source matrix](research/PUBLIC_SPORT_SOURCE_MATRIX.md).
- A new model requires a relevant simple baseline and measured calibration or
  accuracy benefit. A new math engine, service, agent or dependency needs a
  problem statement, alternatives, measurable justification, new failure modes
  and removal plan. GPU use requires measured benefit over a CPU alternative.
- Add tests for meaningful behavior and failure modes. Update documentation and
  decisions for changed contracts; preserve immutable local checkpoint evidence.
  End the block with limitations and `NEXT_EXACT_ACTION`.

## Before a commit or pull request

Run the repository audit before staging. Inspect `git diff --cached --stat` and
the staged diff. No hidden credentials, generated database/model files, raw
research downloads, runtime artifacts or private checkpoints may be committed.

After staging reviewed files, run `python scripts/check_repository_links.py`.
It reads the actual Git index; a target present only on the local disk does not
make a link valid on GitHub. Link to curated [repository-safe evidence](docs/evidence/README.md)
where a durable proof is needed. Preserve raw checkpoints locally and show their
coordinates as inline `LOCAL EVIDENCE PATH` text, never broken repository links.
Use curated synthetic fixtures and label them as synthetic. Do not copy a real
credential into a test, even in a private repository.

Use a concise commit and PR description explaining the resulting behavior,
validation and material limitations. Preserve meaningful Git history and existing
checkpoints. Do not force-push or rewrite shared history as routine cleanup.
Document failures as data rather than weakening invariants to obtain green CI.
Security reports follow [SECURITY.md](SECURITY.md); data and code licensing are
separate under [LICENSE_POLICY.md](LICENSE_POLICY.md).
