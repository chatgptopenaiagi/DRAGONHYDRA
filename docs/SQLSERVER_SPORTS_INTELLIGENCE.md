# SQL Server sports intelligence

Database: existing DRAGONHYDRA_LAB. New schema: dragonhydra.

Tables: sources, source_terms, web_observations, fixtures, entities, markets, odds_observations, scrape_runs, processing_runs, conflicts, handoff_items.

Every table contains record_id, natural_key, version, supersedes_id (self-reference), source_id, available_at, created_at, dedup_key and JSON payload. Unique (natural_key, version) and dedup_key constraints plus serializable key-range locks prevent silent overwrites and concurrent duplicates. SQL rejects invalid JSON. Odds adds a finite decimal conversion / >1 check and computed fixture, market, selection and price columns. Fixtures expose fixture and team identity projections. The independently typed Python contract carries the complete odds schema; JSON retains all provenance without lossy flattening.

Runtime identities are object-granted only: dragonhydra_ingest SELECT/INSERT; dragonhydra_read SELECT. The existing probe schema and probe user are unchanged. No broad SQL credentials are provided to PHP. The live tests prove runtime UPDATE/DELETE and reader INSERT fail, while literal SQL-like text safely round-trips inside a rolled-back append/version test.

Entity identity is source-qualified. OpenFootball has no native IDs in the chosen file, so team keys hash normalized names, and fixture keys hash competition, round and participating team keys. No cross-source team-name equivalence is asserted. Fixture date revisions retain the same identity. Same-observation contradictory scores are quarantined into conflicts; later observations produce superseding versions. All history remains available.

MariaDB owns only `dragonhydra_web.job_state`, `presentation_cache` and `integration_metadata`. It does not contain a replicated fixture/odds warehouse. The metadata table records endpoint integration information. SQL has structured run evidence while MariaDB has operational job status: these are distinct purpose-specific contracts, not dataset replication.

As-of replay selects the latest version satisfying available_at, created_at and payload updated_at ≤ target time. An old match retrieved today cannot become knowledge available at its historical kickoff. These constraints are regression tested.

The initial migration failed on a CHECK referencing a non-persisted computed column. Inspection showed no new schema, logins, MariaDB database or secret files survived. The CHECK was corrected to validate the JSON price expression directly, and the migration then succeeded. No existing tables/accounts were dropped or reset.
