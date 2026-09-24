# Explicit Desktop ↔ CLI handoff

The bridge is `runtime/handoff`, never internal Codex IPC or shared live memory.

| Directory | Contract |
|---|---|
| browser_inbox | Pending manifest JSON; write last after payload is complete |
| browser_downloads | Exact permitted downloaded bytes, retained after processing |
| browser_notes | Structured rendered-browser notes linked by handoff ID |
| cli_inbox | Explicit processor lock / future operator requests |
| processed | Original processed manifests and separate receipts |
| failed | Original failed manifests and reason receipts |
| manifests | Immutable original manifests, fetch evidence and bridge event receipts |

`config/handoff.schema.json` documents the manifest; the Python dataclass enforces runtime rules. Required fields are handoff_id, created_at, created_by, source_url, source_title, source_type, capture_method, download_path, content_hash, observed_at, event_time_if_known, terms_note, robots_note, license_note, confidence and processing_status. This implementation also requires source_id and content_type. Times are timezone-aware ISO 8601; unknown event time is null; confidence is finite 0–1; initial status is PENDING. Download paths resolve strictly inside browser_downloads. URL credentials, query strings and non-HTTPS destinations are rejected in this initial adapter.

For a Desktop handoff, use `capture_method=DESKTOP_BROWSER_RENDERED`. Save `browser_notes/<handoff_id>.json` with SOURCE_URL, TITLE, OBSERVATIONS, DATA_AVAILABLE, UPDATE_BEHAVIOR, VISIBLE_ODDS_FIELDS, VISIBLE_TIMESTAMPS, PUBLIC_API_LINKS, TERMS_PAGE, ROBOTS_PAGE, DOWNLOAD_LINKS, ENGINEERING_IMPLICATIONS, CONTENT_HASH, DESKTOP_STAGE=CONFIRMED and BROWSER_EVIDENCE identifying the actual rendered capture. An authored note is trusted local operator evidence, not a browser-attested signature. Do not fabricate a note to unblock the demonstration.

The processor checks note/source/hash association, rechecks source policy and robots, verifies bytes, normalizes, validates and appends. Failures move to `failed` with sanitized reasons. The source payload remains archived. A reused handoff ID with different manifest bytes is rejected. Replay of the same data produces no duplicate normalized fixture rows.

## Dynamic bridge state

`web/bridge.py` reads the most recent immutable bridge event by aware timestamp and event ID. It supports NO_HANDOFF, DESKTOP_CONFIRMED, CLI_FETCHED, BLOCKED_BROWSER_UNAVAILABLE, PROCESSING, PROCESSED and FAILED. Events retain handoff ID, capture origin, receipt path and optional Desktop evidence path. Origin remains DESKTOP_BROWSER, CLI_FETCH or NONE independently of processing state.

The summary includes `browser_handoff`, `bridge.state`, `bridge.origin`, `bridge.desktop_result`, and last confirmed Desktop handoff ID. A successful CLI fetch and a PROCESSED state never create Desktop confirmation. Explicit fetch/process CLI commands rebuild the cache; `summary` can refresh it independently. The page identifies its snapshot build time.

## Actual experiment

- DESKTOP_STAGE: BLOCKED_BROWSER_UNAVAILABLE. In-app browser and Chrome unavailable; browser inventory request-header policy failed. See `research/browser_research/browser_note.json`.
- CLI_STAGE: Python command-line processor executed successfully; separate Codex CLI app session unverified.
- SQL_STAGE: 380 real OpenFootball fixture observations accepted in an append transaction.
- WEB_STAGE: localhost PHP endpoint returned HTTP 200 and rendered the SQL-derived MariaDB DTO.

The initial failure event is retained. The later actual state is PROCESSED / CLI_FETCH / Desktop NOT_CONFIRMED. Unit tests exercise a Desktop-confirmed processing path only in temporary test directories with mocked SQL; they are not claims that Stage A happened.
