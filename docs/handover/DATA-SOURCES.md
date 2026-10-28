# Data sources and provenance

The exact source URLs, file hashes, capture timestamps and byte counts are in [software-inventory.json](software-inventory.json) and the adjacent `.receipt.json` files under `data/raw`. At the read-only snapshot of 2026-10-28T14:37:31Z, the main DB held 760 OpenFootball fixture records: 380 from 2025/26 with 380 outcomes and 380 from 2026/27 with 50 outcomes. These are records available after local acquisition, not proof of historical availability before capture.

| Local source | Use and boundary |
| --- | --- |
| `data/raw/openfootball-2025-26-en1.json` | 2025/26 fixtures and full-time results; OpenFootball repository declares CC0-1.0. |
| `data/raw/openfootball-2026-27-en1.json` | Current fixture/result snapshot; same CC0 source. Unknown source-local kickoff timezone remains unknown. |
| `data/raw/football-data-2025-26-E0.csv` | Historical result and source-labelled `B365`/`PS` 1X2 price columns. The source labels pre-closing and closing prices but does not provide a per-quote timestamp in this file. |
| `data/raw/tipsaudit-predictions-all.csv` | Previously retained CC-BY-4.0 source and receipt; not the current default archive source. |

Source documentation: [OpenFootball](https://github.com/openfootball/football.json), [Football-Data notes](https://www.football-data.co.uk/notes.txt) and [Football-Data usage policy](https://www.football-data.co.uk/contact.php). The Football-Data receipt records private or academic research usage; review current rights before model training, commercial use or redistribution. The root `.gitignore` excludes `data/raw`.

Capture and persistence timestamps are actual local times in the receipts. Source publication is unknown where recorded as `null`. A match date, kickoff label, provider label or closing label must not be promoted to a proven system-availability or synchronized quote time. Same-name fixtures from different sources or conflicting dates require a verified mapping.
