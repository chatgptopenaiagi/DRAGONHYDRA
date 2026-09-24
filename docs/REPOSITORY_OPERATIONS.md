# Repository operations

The local authoritative project is `C:\xampp\DRAGONHYDRA`. GitHub home: [chatgptopenaiagi/DRAGONHYDRA](https://github.com/chatgptopenaiagi/DRAGONHYDRA). The initial repository is private; `origin` is `https://github.com/chatgptopenaiagi/DRAGONHYDRA.git` and `main` is the development trunk. No GitFlow or required multi-branch bureaucracy is introduced.

## Safe workflow

1. Read AGENTS, README, the master roadmap, status, progress and decisions.
2. Select one coherent authorized block. Use `feature/<name>` when isolation helps a risky change.
3. Run portable tests and the applicable prepared-lab tiers. Review secret-scan output and staged paths before committing.
4. Update documentation and retain a new local checkpoint; never upload raw checkpoints or credentials. Stage reviewed files, then run `python scripts/check_repository_links.py` against their actual Git index contents.
5. Push only reviewed authored files, inspect Actions, and compare local/remote commit IDs. Record unavailable checks honestly.

The [data policy](DATA_POLICY.md) defines commit eligibility. [SECURITY](../SECURITY.md) defines reporting and credential handling. Source approvals expire independently of code releases. No GitHub Action acquires sports data or modifies local infrastructure.

## Visibility and ownership

Visibility remains **private** until the owner explicitly chooses otherwise. To change it later, review source/data rights, full Git history, Actions logs, artifacts, local paths and security limitations first. Then use repository **Settings → General → Danger Zone → Change repository visibility** and follow GitHub's confirmation flow. A public transition exposes the repository and workflow history; it is not a routine release step. See [GitHub's visibility documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility).

No open-source license is selected. [LICENSE_POLICY](../LICENSE_POLICY.md) records retained copyright and separate third-party data obligations. Generated local identities and credentials are not repository content. Git commit identity is configured locally for the authenticated owner using the GitHub noreply address; no global Git identity setting is changed.

## Evidence on GitHub versus local evidence

**LOCAL FORENSIC EVIDENCE = `runtime/checkpoints`. REPOSITORY-SAFE EVIDENCE = `docs/evidence`.** Historical documents retain checkpoint identifiers as explicitly local-only paths. These are not downloadable repository artifacts. [Curated evidence](evidence/README.md) contains test counts, selected measurements, source hashes, provenance boundaries and known limitations without raw captures, secrets or database dumps. Full logs and original manifests stay in ignored `runtime/checkpoints` on the local machine. Only staged target membership can validate a link for GitHub.

## Freeze boundary

A baseline may be tagged only after its commit is clean, pushed, remotely matched and checked. Follow [release strategy](RELEASE_STRATEGY.md); a prerelease is experimental, not production or betting-execution software. Tags preserve the baseline while `main` advances through reviewed coherent blocks.

NEXT_EXACT_ACTION: Freeze the GitHub baseline, then complete the first genuine successful Codex Desktop Browser handoff through a separate Codex CLI session, Python 3.14, SQL Server, MariaDB and Joomla. Do not begin V2 source-adapter expansion in this repository task.
