# DRAGONHYDRA connectors

This describes the current source increment, verified on 2026-10-31. It does not
change the frozen v0.4.0-alpha.1 release or original C7 workstation artifact.
Separately versioned source snapshots and the verified A4 candidate are described
below; their exact hashes distinguish builds sharing the development version.

In **Connections**, open the provider's registration/documentation link, complete
registration in its own browser flow when required, then **Configure connection →
Save connection → Test connection → Sync now → Open imported data**. Public
downloads require no provider account. Provider keys held only on a phone are not
automatically available to this server.

## Source catalog and defaults

These are the implemented adapter selections, not every capability sold by each
provider. Four account-based adapters require a key even when a provider offers a
free plan. Coverage, odds access, quotas and live support depend on that account.

| Provider / API identifier | Key | Default dataset configuration | Automatic interval floor |
|---|---|---|---|
| [API-FOOTBALL / API-SPORTS](https://www.api-football.com/documentation_v3) / `api-football` | Required | `{"league_id":39,"season":2026,"include_odds":false,"max_records":500,"max_pages":5}` | 60 seconds |
| [The Odds API](https://the-odds-api.com/liveapi/guides/v4/) / `the-odds-api` | Required | `{"sport":"soccer_epl","regions":"uk","markets":"h2h","include_scores":true,"max_records":500}` | 60 seconds |
| [Sportmonks](https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures) / `sportmonks` | Required | `{"include_odds":false,"max_records":500,"max_pages":5}` | 60 seconds |
| [football-data.org](https://docs.football-data.org/general/v4/index.html) / `football-data-org` | Required, including free-plan use | `{"competition":"PL","max_records":500}` | 60 seconds |
| [Football-Data.co.uk](https://www.football-data.co.uk/notes.txt) / `football-data-couk` | None | `{"season":"2526","division":"E0","max_records":1000}` | 3,600 seconds |
| [OpenFootball](https://github.com/openfootball/football.json) / `openfootball` | None | Existing onboarding sync: `{"mode":"retained"}`; `fresh` fetches the two configured English Premier League files | Existing manual import workflow |
| [StatsBomb Open Data](https://github.com/hudl/open-data) / `statsbomb` | None | `{"competition_id":43,"season_id":106}` | 3,600 seconds |
| [nflverse schedules](https://nflreadr.nflverse.com/reference/load_schedules.html) / `nflverse` | None | `{"seasons":[2025]}` | 3,600 seconds |
| [MoneyPuck](https://moneypuck.com/data.htm) / `moneypuck` | None | `{"season":2025,"season_type":"all"}` | 86,400 seconds |
| [Cricsheet](https://cricsheet.org/downloads/) / `cricsheet` | None | `{"dataset":"blz"}` | 3,600 seconds |

Optional fixture windows use `date_from` and `date_to`, at most 31 days. Omitted
windows are evaluated at execution time: UTC today through tomorrow for
football-data.org, whose end date is exclusive; UTC today for API-FOOTBALL and
Sportmonks. Explicit windows remain explicit. Provider-native league/season IDs
are not interchangeable.

The Odds API accepts supported comma-separated `regions` and `markets` (`h2h`,
`totals`, `spreads`); optional scores remain coverage-dependent. This adapter does
not implement its separate historical-odds product. API-FOOTBALL and Sportmonks
accept `include_odds:true` for their implemented prematch markets when authorized.
No credentialed live service was verified in this increment. Sportmonks' upstream
documentation distinguishes fixture endpoints from dedicated livescores endpoints;
fixture polling is not proof of a working in-play feed.

nflverse also accepts one `season`, or `start_season`/`end_season`, with at most five
selected seasons. MoneyPuck `season_type` is `all`, `regular` or `playoffs`.
Cricsheet supports complete published `blz`, `cec` and `frb` JSON archives; `blz`
is the manageable Women's T20 Blaze default. Custom URLs are rejected.

## Credentials and scheduling

API keys are entered in the connection's password field and submitted to the
authenticated administrator API. They are encrypted on Windows with **current-user
DPAPI in the actual server process** and stored under `<state>/vault/*.dpapi` with
restricted file permissions. The server may run as LocalService or a selected
account; saving through that running server uses that identity. Creating vault
files under a developer account does not make them decryptable by LocalService.
Clients receive configured/masked status, not the key.

Changing machine, service account or its DPAPI profile can require reauthorization.
Retain a consistent protected state backup, but do not assume copying encrypted
files alone provides cross-machine vault recovery. Resave the provider key through
the newly authorized server if `VAULT_IDENTITY_MISMATCH` is reported.

For a headless service, the implemented fallback reads its protected process
environment: `DRAGONHYDRA_API_FOOTBALL_KEY`, `DRAGONHYDRA_THE_ODDS_API_KEY`,
`DRAGONHYDRA_SPORTMONKS_KEY`, or `DRAGONHYDRA_FOOTBALL_DATA_ORG_KEY`. Environment
credentials take precedence over stored DPAPI entries. On non-Windows hosts,
saving a key through this API is unsupported; supply a restricted service
environment instead. This is not a portable encrypted Linux vault. Removing a
stored key does not unset an environment credential; remove that service setting
and restart the owned service when appropriate. Never put keys in dataset JSON,
URLs, command histories, APK assets or installer payloads.

Automatic synchronization defaults to **Manual only** (`interval_seconds:0`).
Configured periodic work is persisted and scheduled centrally, with no second
poller per client. Allowed intervals run from each provider's floor to seven days;
the floor is not a promise that the account quota supports that cadence. Date
coverage, pages and optional odds can increase request cost. The scheduler avoids
another periodic sync while that provider already has queued/running/recoverable
work. Explicit manual commands remain real requests; repeated Test clicks can
download the dataset again.

Jobs have a 120-second attempt deadline, cancellation checks and persisted
heartbeats/leases. Temporary network failures and rate limits receive at most
three attempts. Backoff honors a supplied `Retry-After` where available and bounded
exponential delay otherwise. Authentication failures, incompatible schemas and
oversized downloads fail specifically; cached browsing remains available.
Interrupted reads and declared-length truncation retry without publishing partial
payloads. HTTP 500/502/503/504 retain their complete response evidence and use the
same bounded retry path; permanent HTTP errors remain distinct.

## API and source-run example

Normal workstation users open the application. Engineers testing this source
increment can use the existing Python 3.14 environment and a separate state:

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRA'
$env:PYTHONPATH = Join-Path $PWD 'src'
& '.\runtime\server-env\Scripts\python.exe' -B -m dragonhydra.server `
  --port 0 --state '.\runtime\connections\product'
```

Reuse an already running coordinator for that state; do not launch a duplicate.
Its chosen URL is in `runtime/connections/product/endpoint.json`. Pair using the
owner's protected session flow. The following uses a placeholder, not a real key
or published token:

```powershell
$origin = (Get-Content '.\runtime\connections\product\endpoint.json' -Raw | ConvertFrom-Json).url
$base = $origin + '/dragon/api/v1'
$headers = @{ Authorization = 'Bearer <OWNER_SESSION_TOKEN>' }
Invoke-RestMethod "$base/connections" -Headers $headers
Invoke-RestMethod "$base/connections/cricsheet/configuration" -Method Put `
  -Headers $headers -ContentType 'application/json' `
  -Body '{"config":{"dataset":"blz"},"interval_seconds":0}'
$job = Invoke-RestMethod "$base/connections/cricsheet/sync" -Method Post `
  -Headers $headers -ContentType 'application/json' -Body '{}'
Invoke-RestMethod "$base/jobs/$($job.id)" -Headers $headers
Invoke-RestMethod "$base/connections/cricsheet/records?limit=20&offset=0" -Headers $headers
```

For the nine new adapters, `POST /connections/{id}/test` and `/sync` return HTTP
202 and a job ID. Test retrieves and normalizes; Sync also commits records.
`GET /connections/{id}/attempts` exposes redacted diagnostics; `/records` supports
`limit` (1–200), `offset` and `status`. Cancel through
`POST /jobs/{job_id}/cancel`. Retry a command with the same `Idempotency-Key` to
reuse its job. OpenFootball retains its existing `import_public` job flow and
immediate bounded connection-test response; it does not use the new configuration
endpoint. Reads do not silently import data.

## Identity, time and market limits

Source/native IDs, source URLs, resolved URLs, exact payload bytes and hashes are
retained. Corrections create observations rather than overwriting earlier
evidence. Source-record browsing currently selects the latest retained revision
per source/native ID. Capture, persistence acknowledgement and a completed reader
response are distinct boundaries; capture time is not source publication time.
Cross-source identity candidates require review. Similar names do not merge
fixtures, participants or markets automatically.

Football-Data.co.uk dates and local clocks do not establish UTC kickoff or quote
times. Its bookmaker-labelled opening/closing columns are archival endpoints, not
an intraday curve. `Avg`/`Max` aggregates are not individual bookmakers. Source
warnings remain attached. Compatible markets keep provider/feed, selection, period,
line and settlement scope; archive prices are not attached to an unrelated match.

StatsBomb's original repository redirects to Hudl; receipts preserve both the
original and resolved URLs. This adapter retrieves the competition catalog and
match/team metadata, not its full event/lineup corpus. Naive kickoff clocks retain
their unknown timezone. nflverse uses documented **America/New_York** game times
and daylight-saving rules; ambiguous/nonexistent times, or a missing timezone
database, remain explicitly unresolved instead of inventing UTC. See its
[schedule dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html).

MoneyPuck pairs matching game/team rows, or uses the explicitly supplied opponent
and side on a single row. Native team codes remain native. Reported all-situation
goals do not establish treatment of a shootout deciding goal; no betting
settlement or winner is inferred. The official team-game download uses gzip,
with **32 MiB compressed / 128 MiB decoded** limits. The verified transfer was
31,523,477 bytes. Future growth can produce `DOWNLOAD_LIMIT` or
`DECOMPRESSION_LIMIT`; partial imports and unverified replacement URLs are not used.

Cricsheet teams are **source-order participants**, not asserted home/away teams.
Separate innings, super overs, penalty runs and wicket-event kinds remain
separate; retired-hurt events are not labelled wickets lost. Two-number match
scores and kickoff times are left unavailable. The in-memory ZIP parser checks
paths, duplicate/encrypted/symlink members, CRC integrity, member count and expanded
sizes, and processes the complete selected archive. Supported
[JSON formats](https://cricsheet.org/format/json/) are 1.0–1.3.

## Observed verification

| Source | Fixture coverage | Real public retrieval | API-ingested records |
|---|---|---|---|
| OpenFootball | Existing regression path | Existing retained/fresh path | 760 retained baseline records |
| Football-Data.co.uk | Parser/error/odds fixtures | Passed | 380 |
| StatsBomb | Parser/error/redirect/time fixtures | Passed | 64 |
| nflverse | Parser/error/Eastern-time fixtures | Passed | 285 |
| MoneyPuck | Parser/error/provenance fixtures | Passed, full selected season | 1,394 |
| Cricsheet | Parser/error/ZIP/provenance fixtures | Passed, complete Blaze archive | 17 |
| Four credentialed APIs | Fixture-tested adapters and missing-key diagnostics | Not run without authorized keys | 0 |

Counts were read from the authenticated development API on 2026-10-31. They are
source-scoped, not a deduplicated total of unique sporting events. MoneyPuck and
Cricsheet have 19 fixture tests; repeated verification runs are not extra unique
tests. Useful local evidence includes
`runtime/scratch/connectors-multisport/real-adapter-verification.json`,
`runtime/scratch/connectors-football-live/RESULTS.json`, and
`runtime/scratch/research-connectors-20261031T105457Z/summary.json`.
Their adapter-fetch receipts and the later API ingestion results are separate.

The current source regression passed **384 tests in 45.312 seconds**, including
transport, worker retries, local-model configuration, quote provenance and
legacy hash compatibility. The real
Edge/Playwright Connections journey passed **13 groups**, including actual
StatsBomb retrieval, unchanged Football-Data.co.uk synchronization, source-scoped
navigation, an Excel download, multisport browsing and missing-key diagnostics.
Evidence: `build/connections/evidence/provenance-and-signing-regression.log` and
`build/connections/evidence/local-ai-connections-regression/journey.json`. This verifies the
source server and browser; the existing workstation installer is still separate.

The isolated connector + optional-AI server build is
`build/connections/payload-20261031-a2/dist/DRAGONHYDRA-Server-x64/DRAGONHYDRA-Server.exe`.
Build command:
`runtime/server-env/Scripts/python.exe -B scripts/build_connector_server.py --work build/connections/payload-20261031-a2`.
Its PyInstaller and two private-runtime smoke suites all exited 0; **16 groups**
passed. This payload contains the optional package/API/UI increment, with
deterministic fallback when no local model is configured. Build/source/file hashes
are in the sibling `BUILD-REPORT.json`, `SOURCE-MANIFEST.json` and
`PAYLOAD-MANIFEST.json`. The earlier a1 payload separately verified four actual
public imports; its evidence remains under
`build/connections/evidence/frozen-live-20261031`.

The development launchers can select this exact verified payload without Python
being installed on the target process path. From the project, run:

```powershell
.\scripts\Start-Dragonhydra.ps1 -NoOpen `
  -State .\runtime\connections\your-state `
  -ServerBinary .\build\connections\payload-20261031-a2\dist\DRAGONHYDRA-Server-x64\DRAGONHYDRA-Server.exe
```

Remove `-NoOpen` to use the existing native client. Stop through
`Stop-Dragonhydra.ps1` with the same explicit `-State` and `-ServerBinary`.
Launchers verify payload file hashes and exact process ownership, and reject a
different live coordinator for that state. The launcher verification passed five
groups covering eleven commands; evidence:
`build/connections/evidence/a2-launcher/attempt2/verification.json`. These wrapper
scripts are recorded separately from the immutable payload snapshot.

A separate full-workstation candidate now incorporates A2:
`dist/connections/workstation-a2/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe`.
It is unsigned, 64,207,524 bytes, SHA-256
`a22dcb583036c5106c0cb63cbb17784b5d8d62d13c8493c5713e79d3a6504597`.
NSIS exited 0. Extraction verified all 10,662 payload files and the exact A2
kernel. `EXTRACTION-VERIFICATION.json` beside the installer records this scope.
The candidate was subsequently installed and verified on this host: 23 full
workstation groups and six optional-model UI groups passed. Its LocalService
imports stored Football-Data.co.uk380, StatsBomb64 and Cricsheet17 with no
quarantine. The new `DragonhydraProvidersA2Test` service uses API18746,
Joomla18747 and MariaDB18748. `TEST-REPORT.json` beside the installer records
the installed scope and original-instance preservation. Clean-machine and
Windows reboot tests remain unperformed; the original C7 artifact and
installation remain separate.

The latest **A4** installer is under `dist/connections/workstation-a4`:
64,230,183 bytes, unsigned, SHA-256
`03941aacb8cc4a447f727ec8d5e1a00b6d4f810c0ebc59725c7a8cf7c19ac1ab`.
It passed 21 frozen smoke groups and was repaired into the same isolated test
service with all 1,221 source records, pairing and ports retained. Fresh public
resyncs kept 380/64/17 records unchanged. Exact receipt metadata was verified for
168 archive quotes; nine LocalService/Qwen groups and five passive health checks
passed. The temporary runner/key/endpoint were cleaned up. Its `TEST-REPORT.json`
distinguishes current checks from earlier A2/A3 tests and clean-machine limits.

New observations validate every declared quote, catalog and score-document
dependency against its exact receipt-backed acquisition. Quote capture time,
source URL and hash come from that acquisition; parent match evidence is retained
separately. Inspect safe metadata through
`GET /connections/{provider}/acquisitions/{acquisition_id}`. This authenticated
endpoint omits raw response bytes and filesystem references. Legacy secondary
quotes without a stored binding report unresolved provenance and no capture time.
Whole-invalid Sync jobs retain quarantine and fail; Test cannot label an orphan
dependency Working. Each complete document is hashed once per operation.

An independent retained-data replay preserved all 2,140 records across five
providers, including old StatsBomb/NFL hashes and IDs, without revisions or
quarantine: six original documents, 34,139,139 bytes, 4.744 seconds, zero HTTP
attempts. Evidence:
`build/connections/evidence/provenance-retained-20261031-r3/verification.json`.
This is retained-byte validation, separate from the actual installed HTTP resyncs.

`working` means actual payload retrieval and normalization succeeded, with import
time and stored count shown separately. Endpoint reachability, credential presence,
successful retrieval, committed import and verified display are distinct states.

The source tree now includes an explicit StatsBomb context operation for native
match **3869685** (Argentina–France, 18 December 2022). This is newer than the
packaged A4 installer. The ordinary StatsBomb adapter continues to import match
metadata; context remains a separate immutable record and cannot inflate match
counts or disappear during an unchanged metadata sync.

Relative to `/dragon/api/v1`, the authenticated routes are:

- `POST /matches/{match_id}/source-context`: admin-only, empty JSON body; queues
  one job with an exact frozen parent. Idempotency keys are supported.
- `GET /matches/{match_id}/source-context`: retained projection and safe source
  receipts, or explicit unsupported/not_requested/parent_changed/unavailable.
- `GET /matches/{match_id}/source-events?offset=0&limit=200`: bounded native event
  pages regenerated from verified retained bytes. Reads create no schema and
  perform no provider request, model call or import.

Each explicit acquisition job has two durable GET intents, one events file and
one squad file, at most 8 MiB each. Redirects are rejected. Restarts, cancellation
and stale worker claims cannot reset the budget. An uncertain request outcome
requires a fresh explicit job. Acquisition receipts and journal completion commit
together; a durable publication marker preserves the original context revision
across a crash and later jobs. Normal provider test/sync retries remain unchanged.

Context uses the exact optional eighteen-table migration profile. Same-byte
duplicates preserve original bindings and receipts; corrections append revisions.
The full validator reconstructs the parent, both source documents and the entire
projection. A new content hash alone cannot legitimize changed counts.

The Lineups and Statistics tabs show source squad entries, counts of retained
event rows and native paginated fields. Missing team/player/period/time fields
remain missing. The operation supplies no inferred starting roles, possession,
xG, winner, UTC kickoff or settlement.

Verified before actual dataset acquisition: **497 unit/regression tests**, an
independent eleven-group/fourteen-case fault harness, and seven real Edge journey
groups using in-process provider responses. These checks made no external
provider HTTP request. Evidence is under
`build/connections/statsbomb-context-job-20261031`, including
`job-api-dashboard-regression.log`, `acceptance-r1/verification.json` and
`browser-r3/journey.json`.

The real two-file job subsequently passed in the isolated state
`runtime/scratch/statsbomb-real-20261031-1`: exactly two application fetches and
two HTTPS GETs, both successful, retained **4,407 events**, 29 event types and
181 count groups, with **24 France and 26 Argentina squad entries**. Twenty-nine
events omit a player field. The existing 3:3 match score and all original rows
remain unchanged. Independent read-only checks and a retained-only Edge journey
passed six groups each, without further provider requests. Those receipts are in
`real-r1`, `real-r1/independent-readonly` and `real-browser-r1` under the same
evidence directory. This isolated real-data proof is separate from the installed
A4 workstation and earlier match-metadata retrieval.
