# DRAGONHYDRA Web-to-SQL pipeline

## Desktop / CLI bridge v1 extension

The strict BrowserHandoffEnvelope path is now `python -m dragonhydra handoff consume --once` or `scripts/Run-HandoffOnce.ps1`. It uses five dedicated append-only SQL bridge tables and the new `dragonhydra_ingest_sqlserver` identity, preserving all older identities. Its separate presentation DTO is read by the existing localhost dashboard. See [CODEX_DESKTOP_CLI_BRIDGE.md](CODEX_DESKTOP_CLI_BRIDGE.md) for the schema, ownership, claim/replay/receipt protocol and failure evidence; [CODEX_DESKTOP_HANDOFF_INSTRUCTIONS.md](CODEX_DESKTOP_HANDOFF_INSTRUCTIONS.md) contains the exact genuine Desktop task prompt. Synthetic end-to-end and replay verification do not claim actual Desktop browsing. Legacy manifests remain owned by the earlier processor described below.

The demonstrated path is one permitted OpenFootball public JSON download → SHA-256 handoff → explicit Python CLI processing → bounded validation → SQL Server append history → Python summary → MariaDB cache → localhost PHP dashboard.

Desktop browser automation was attempted through the supplied browser tools and was unavailable. No rendered Desktop observations are claimed. The shared-file contract supports Desktop captures, and the real processor path is tested with isolated Desktop test fixtures. Those test fixtures are not live browser evidence. A separate Codex CLI executable was not available on PATH; the implemented Python CLI can be invoked from either Codex surface or PowerShell without private IPC.

## Run explicitly

From `C:\xampp\DRAGONHYDRA`:

```powershell
.\scripts\Run-WebPipeline.ps1 fetch-demo
.\scripts\Run-WebPipeline.ps1 process
.\scripts\Run-WebPipeline.ps1 synthetic-demo
.\scripts\Run-WebPipeline.ps1 summary
```

The launcher uses the configured Anaconda `codex-pytorch` Python 3.14 interpreter. It starts no daemon. `fetch-demo` makes one exact approved data request plus robots verification. `process` scans at most ten inbox manifests and independently rechecks robots. A manifest payload is capped at 32 KB; downloads at 2 MB; the OpenFootball file at 500 fixtures. The first demo processed all 380 fixtures in the 2023/24 English Premier League file. HTTP 404 on robots is recorded as ABSENT, not as legal permission.

The allowlist is `config/web_sources.json`. Source approval expires after 30 days and is independent of robots. StatsBomb remains UNVERIFIED; its data was not ingested. OpenFootball is the only active external data source. Synthetic odds have a separate source and fixture.

## Contracts and ownership

- `web/contracts.py`: URL, fetch and manifest contracts.
- `web/fetch.py`: bounded HTTPS, global-IP DNS validation and IP-pinned TLS, no redirects/auth/cookies/proxies.
- `web/terms.py`, `web/robots.py`, `web/license_evidence.py`: separate permission, crawler and extraction evidence.
- `web/json_api.py`, `web/html.py`: bounded parsing; HTML never executes scripts.
- `web/validation.py`: ACCEPT, ACCEPT_WITH_WARNING, QUARANTINE, REJECT with reasons.
- `web/pipeline.py`: explicit fetch/import/synthetic/summary jobs.
- `storage/intelligence.py`: fixed parameterized database operations.
- `storage/router.py`: typed single-owner routing. OPERATIONAL/CACHE → MariaDB; STRUCTURED_INTELLIGENCE → SQL Server; ARCHIVE → filesystem; ANALYTICAL → reserved future Parquet, not implemented.

The router never mirrors SQL datasets into MariaDB. Only a small DTO (counts, five fixtures, ten quotes, recent run status) is cached. Presentation is an explicit derived artifact with a build timestamp.

Every import has a job ID, type, start/finish, status, source, seen/accepted/rejected/error counts and checkpoint path. The SQL transaction commits before the processed receipt is moved. A crash after commit can be replayed idempotently. SQL append rows carry unique deduplication hashes, increasing versions and predecessor IDs. A processor lock prevents concurrent inbox scans; a crash leaves the lock for deliberate inspection, not automatic reset.

Failure codes include NETWORK_ERROR, HTTP_ERROR, TERMS_BLOCKED, ROBOTS_BLOCKED, CAPTCHA_PRESENT, AUTH_REQUIRED, RATE_LIMITED, PARSE_FAILED, SCHEMA_CHANGED, INVALID_ODDS, UNKNOWN_MARKET, STALE_DATA and CONFLICTING_DATA. No failure is automatically bypassed. Retry count is a maximum; this first implementation retries no failures.

## Evidence and limits

Unique `runtime/checkpoints/web-*.json` artifacts cover source research, extraction, provisioning, fetch, ingestion and presentation. The full regression runner writes a separate immutable checkpoint directory. These are application-immutable files, not cryptographic signatures or operating-system WORM storage.

The database schema uses versioned JSON envelopes with relational version/source keys and selected computed projections. It is not yet a fully flattened sports warehouse. Cross-source identity reconciliation and corroboration, authenticated odds adapters, predictive models and feature materialization remain future work. No betting execution exists.
