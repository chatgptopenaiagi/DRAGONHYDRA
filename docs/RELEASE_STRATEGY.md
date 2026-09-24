# Release and baseline strategy

Adopted 2026-09-24. DRAGONHYDRA uses `main` as its stable development trunk. A risky future coherent block may use `feature/<name>` and a reviewed pull request. There is no GitFlow requirement or release committee.

## Version meaning

Roadmap V0–V10 identifies architectural stages; package/release versions identify repository milestones. They are separate dimensions. `pyproject.toml` currently declares `0.1.0`; this alone does not establish a Git tag, GitHub release, production readiness or completion of a roadmap gate.

Possible milestone tags include `v0.1.0-foundation`, `v0.2.0-web-sql` and `v0.3.0-desktop-cli-bridge`. These are naming examples, not tags already created. Do not backdate a release or imply a genuine Desktop proof before it exists. If a verified baseline is released, `v0.1.0-alpha` is an appropriate initial prerelease identifier.

## Release gate

1. Preserve local history and immutable checkpoints; create a new checkpoint for the release block.
2. Run the Python 3.14 portable suite and appropriate local integration checks, recording pass/fail/skip counts and unmet prerequisites honestly.
3. Audit authored and staged contents for secrets, restricted data, generated binaries, raw handoffs, database files and runtime/checkpoint inclusion.
4. Verify current README, status, changelog, policies and documentation links against the actual staged file set. Keep **LOCAL FORENSIC EVIDENCE** in ignored `runtime/checkpoints/` and link claims only to supporting **REPOSITORY-SAFE EVIDENCE** in [docs/evidence](evidence/README.md). Raw local coordinates are plain strings/inline code, not broken GitHub links.
5. Commit a coherent baseline, push `main`, and verify local/remote commit equality, default branch, private visibility and readable key files through GitHub.
6. Inspect CI results for that commit. A failed or missing run must be explained; never represent an unexecuted workflow as passing.
7. Create a prerelease only when the baseline is clean and documented. Use the exact verified commit and concise release notes. Never move an existing published tag silently.

A baseline release should summarize the measured foundation, Python 3.14, bounded dual-database proof, Web-to-SQL ingestion, synthetic Desktop/CLI bridge and local Joomla-directory observability. Cite curated summaries with historical timestamps and source hashes; do not present old measurements as a new release-time live check. State the genuine Desktop proof gap if still open. Mark it **experimental**, **not production**, and **not betting execution software**. Omit generated local credentials, database dumps, logs, private checkpoints, downloaded sports data and browser/session artifacts from assets.

## Visibility and rights

The initial repository is private by owner instruction. Later public visibility is an explicit owner decision after repository history, data rights, secrets, limitations and license policy are reviewed. The owner can use repository **Settings**, find **Change repository visibility** in **Danger Zone**, and select **Change visibility**, following the current [GitHub visibility instructions](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility). Review Actions history/logs as well as Git history before making the repository public. Do not switch automatically or infer an open-source license from public visibility. See [license policy](../LICENSE_POLICY.md) and [data policy](DATA_POLICY.md).

## Recovery and traceability

Prefer a corrective commit and a new version over rewriting published history. Preserve failed run evidence locally and summarize the correction without secrets. If sensitive material is discovered after publication, stop further distribution, notify the owner privately and rotate/revoke the affected credential; removal from a later commit does not remove historical exposure. Any history rewrite needs a deliberate, coordinated recovery decision.

## Next exact action

After the GitHub baseline is successfully pushed and remotely verified: freeze the GitHub baseline, then complete the first genuine successful Codex Desktop Browser handoff with verified evidence for Desktop Browser → handoff → Codex CLI → Python 3.14 → SQL Server → MariaDB → Joomla. Preserve a truthful blocked result if the required surface fails. Do not begin V2 Hydra Source Adapter expansion during repository engineering or this pending V1 proof.
