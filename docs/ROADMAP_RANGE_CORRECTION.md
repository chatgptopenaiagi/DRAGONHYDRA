# Roadmap range correction — 2026-09-24

The owner clarified the intended ranges: **2–3 high-quality sources (two to three)** and approximately **3–5 closely related roadmap items (three to five)** per normal session. This is a documentation-integrity repair. V1 remains active; no implementation block was started.

## Every corrected occurrence

Seven corrupted numeric occurrences appeared in five passages. Locations below identify the original passages; original line numbers refer to the preserved before snapshots in the [correction checkpoint — curated summary](evidence/roadmap-integrity-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/roadmap-range-correction-20260924T185126Z-9eb65c7a`).

| Occurrence | File / original location | Incorrect text | Corrected meaning |
| --- | --- | --- | --- |
| 1 | DRAGONHYDRA_MASTER_ROADMAP.md, V2, line 102 | `23 HIGH QUALITY SOURCES` | `2–3 HIGH QUALITY SOURCES` |
| 2 | DRAGONHYDRA_MASTER_ROADMAP.md, section 15, line 224 | `23 GOOD SOURCES` | `2–3 GOOD SOURCES` |
| 3 | DRAGONHYDRA_MASTER_ROADMAP.md, section 17, line 232 | `35 closely related roadmap items` | approximately `3–5 closely related roadmap items` |
| 4 | ROADMAP_STATUS.md, CURRENT_LIMITATIONS, line 59 | `“23” sources` plus an instruction against interpreting it as a range | `2–3 sources (two to three)`; numeric intent resolved |
| 5 | ROADMAP_STATUS.md, CURRENT_LIMITATIONS, line 59 | `“35” related items` plus an instruction against interpreting it as a range | approximately `3–5 closely related items (three to five)`; numeric intent resolved |
| 6 | DECISIONS.md, D019, line 7 | `“23” sources` called literal owner wording | `2–3 sources (two to three)` per explicit owner correction |
| 7 | DECISIONS.md, D019, line 7 | `“35” related items` called literal owner wording | approximately `3–5 closely related items (three to five)` per explicit owner correction |

README.md, AGENTS.md and PROGRESS.md contained no corrupted copies of these quantities. They now carry the corrected scope, preservation rule or correction history. D021 records the reason and supersession; status no longer treats numeric intent as unresolved. The three original roadmap passages and the two copied passages were repaired, not merely annotated.

## Audit scope and legitimate numeric matches

The complete 29-section master roadmap and all six adoption documents were reviewed, with an additional search across project documentation for copied wording. Searches covered `23`, `35`, `13`, `01`, `V0V10`, `P0P10`, intact ranges and other numeric tokens.

- Master-roadmap section numbers 13 and 23 are legitimate; they remain integers.
- Version labels V0 through V10 and layer labels P0 through P10 are complete. No collapsed `V0V10` or `P0P10` label range was found.
- Existing ranges such as `P0-P10`, `V2–V10`, `2–4` and decision-ID ranges remain intact, with their original separators preserved.
- Matches inside CUDA/Python versions, decision IDs, SQLSTATE codes, PIDs, dates, checkpoint paths and SHA-256 hashes are genuine recorded values; no replacement is appropriate. No prose scope range was found collapsed into `13` or `01`.
- The incorrect values quoted in the occurrence table are correction evidence, not active instructions. Original checkpoint snapshots intentionally retain the prior text.

No other numeric range corruption was found in the audited roadmap or copied wording. Current source scope and session scope use en-dash U+2013 and explicit words to preserve their meanings.

## Validation and preservation

The [new correction checkpoint — curated summary](evidence/roadmap-integrity-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/roadmap-range-correction-20260924T185126Z-9eb65c7a`) contains before/after document snapshots, per-file hashes, a complete numeric-match inventory, a change diff and Python 3.14 documentation/link checks. Checks cover all 29 sections, all 11 version labels, all 11 Pyramid layers, required status fields, local links, corrected quantities and preservation of previously intact range separators.

The [original roadmap-adoption checkpoint — curated summary](evidence/roadmap-integrity-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/roadmap-adoption-20260924T184422Z-3178f45c`) is preserved byte-for-byte, including its audit and manifests. Implementation files and configuration retain their before hashes. Prior 190-test evidence is historical; application tests and live database/GPU checks were not rerun for this documentation-only repair.

NEXT_EXACT_ACTION: Use the corrected roadmap when selecting the next separately authorized V1 block. No new DRAGONHYDRA functionality is authorized by this correction.
