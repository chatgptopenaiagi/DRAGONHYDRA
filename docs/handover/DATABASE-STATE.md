# Database state

The primary local database is `runtime/dragonhydra.sqlite3`. A read-only, immutable snapshot check at 2026-10-28T14:37:31Z observed:

| Record class | Count |
| --- | ---: |
| Public fixture records | 760 |
| Public source captures / receipts | 2 / 2 |
| Market acquisitions / receipts | 18 / 18 |
| Raw source blobs | 4 |
| Quarantine / quarantine receipts | 6 / 6 |
| Cognitive model records | 70 |
| Cognitive prediction records | 60 |
| Cognitive research tasks | 44 |
| Cognitive hypothesis revisions | 10 |
| Cognitive outcomes / measured evaluations | 0 / 0 |

The 60 prediction records cover one distinct fixture and 12 prediction run IDs; they are not 60 independent events. The six main-store quarantine rows report acquisition-identity collisions. Counts are a point-in-time observation, not a guarantee of current contents.

Three SQLite backups were recorded with `integrity_check: ok`: `release/genesis2/database/dragonhydra.sqlite3`, `market-demo.sqlite3` and `watch-demo.sqlite3`. Their times, exact SHA-256 hashes, byte counts and table counts are in [database-backups.json](../../release/genesis2/metadata/database-backups.json). SQLite backup consistency is not a claim of a tested disaster-recovery restore or SQL Server integration.

Cognitive tables contain immutable payloads and separate receipts; model and prediction IDs link retained input evidence. An outcome can be attached only after a matching genuinely earlier prediction and a later eligible source result. Earlier reports must not be changed by later corrections. Receipt timestamps use post-data-commit acknowledgment; exact receipt-transaction visibility is not proven.
