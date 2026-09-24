# Security policy

DRAGONHYDRA is an experimental local laboratory. A private repository limits
distribution; it does not make credentials safe to commit or establish production
security. No supported production release or response-time guarantee exists.

## Reporting a vulnerability

Contact the repository owner, `chatgptopenaiagi`, through an existing owner-approved
private channel. Establish a private channel before sending sensitive details;
this private repository does not promise a GitHub private-reporting button or a
monitored security email. Do not open an issue containing exploit details or
private data. Ordinary issues may describe a sanitized symptom only.

Include the affected commit, component, impact and minimal reproduction using
synthetic data. Never include passwords, tokens, cookies, authorization headers,
browser profiles, database dumps, connection strings with credentials, raw handoff
captures, private checkpoints or unredacted logs. If a credential was exposed,
revoke or rotate it through its owner; deleting a file alone is insufficient.

## Credentials and repository boundary

Generated local credentials are **not repository content**. Python credentials
belong in ACL-protected `runtime/secrets`, outside the web root, with application
configuration referencing their paths. Historical Joomla experiment credentials
and private configuration also remain local and ignored. Never copy credentials
into source code, workflow variables, fixtures, issues, PRs or documentation.

The entire `runtime/`, `data/` and `models/` trees are ignored, including handoff
payloads, downloads, receipts, checkpoints, vendor wheels, temporary files and
SQL Server database files. Only reviewed, curated schemas and synthetic examples
belong in authored source/config/tests. Raw browser research and experiment
machine evidence remain local. See [DATA_POLICY.md](docs/DATA_POLICY.md).

LOCAL FORENSIC EVIDENCE remains in `runtime/checkpoints`; REPOSITORY-SAFE
EVIDENCE is limited to reviewed summaries in [docs/evidence](docs/evidence/README.md).
Whitelist exported fields, retain source-artifact hashes and historical limits,
and never copy raw logs or credentials into the curated layer.

Before staging, run `python scripts/repository_audit.py --all-local --check`.
This read-only audit compares known local credential values in memory without
printing them. GitHub CI runs `--tracked --check` without reading local secrets.
The scanner prints paths, rule identifiers and line numbers only. Its bounded
patterns cannot establish that arbitrary encoded or novel secrets are absent;
review the staged file list and changes as well. Active database files may be
OS-locked; they must remain ignored. Three existing negative security-test lines
are explicitly reviewed using exact source-line digests, not blanket test skips.

## Database and local service boundaries

Use dedicated least-privilege identities. SQL Server owns structured intelligence;
its ingestion and read identities have bounded object permissions. MariaDB owns
operational/presentation state; the dashboard reader is SELECT-only on its small
presentation cache. Do not reuse Joomla's writable application account for probes
or provide generic SQL execution. Provisioning scripts are deliberate local admin
tools, never CI steps. They do not justify committing administrative credentials.

New interfaces are localhost-first. The dashboard uses Apache and PHP local
guards; current shared database/service bindings are documented, not claimed to
be globally loopback-only. Do not widen firewall rules, expose database ports or
publish the dashboard as an incidental repository change. The existing SQL TLS
certificate exception is constrained to loopback and is not certificate
validation. See [database boundaries](docs/DATABASE_SECURITY_BOUNDARIES.md).

## Browser handoff and external sources

Treat browser input as untrusted. Require the closed envelope schema, bounded
sizes, safe paths, hashes, timestamp validation and source-policy gates. Do not
execute downloaded content. Secret-bearing input goes to protected quarantine
with sanitized failure records. Desktop and CLI cooperate through explicit
filesystem artifacts; no private Codex IPC, browser credential store or session
database extraction is permitted. Local producer labels are not cryptographic
browser attestation. See [handoff security](docs/HANDOFF_SECURITY_MODEL.md).

Use public sources only within reviewed terms, licensing and rate policies.
Robots information and terms/license approval are separate. No authentication,
paywall or CAPTCHA bypass, unauthorized private API extraction or rate-limit
evasion is authorized. Uncertain rights block ingestion. CI tests code and
synthetic fixtures; it does not scrape bookmaker sites, use private sessions,
alter live infrastructure or place bets. DRAGONHYDRA has no gambling-execution
mandate. See [RESEARCH_POLICY.md](docs/RESEARCH_POLICY.md).
