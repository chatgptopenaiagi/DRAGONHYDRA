# Architecture decision records

Recorded 2026-09-24. These short ADRs index and clarify accepted decisions; they do not replace or rewrite the chronological [DECISIONS.md](../DECISIONS.md). The [master roadmap](../DRAGONHYDRA_MASTER_ROADMAP.md) and [current status](../ROADMAP_STATUS.md) determine stage and scope. Recording a decision is not proof of full implementation.

| ADR | Decision | Original record |
| --- | --- | --- |
| [ADR-001](ADR-001-python-314.md) | Python 3.14 is invariant | D001, D020 |
| [ADR-002](ADR-002-sql-server-intelligence.md) | SQL Server owns structured intelligence | D014, D017, D020 |
| [ADR-003](ADR-003-mariadb-operations.md) | MariaDB owns operational/presentation state | D014, D018, D020 |
| [ADR-004](ADR-004-append-oriented-history.md) | Evidence corrections append versions | D004, D014, D018 |
| [ADR-005](ADR-005-no-future-leakage.md) | Historical analysis prohibits future leakage | D004, D020 |
| [ADR-006](ADR-006-mandatory-provenance.md) | Important external facts retain provenance | D012, D016, D020 |
| [ADR-007](ADR-007-filesystem-handoff.md) | Desktop/CLI exchange explicit files | D013, D016–D018 |
| [ADR-008](ADR-008-no-private-ipc.md) | No private Codex IPC integration | D015, D020 |
| [ADR-009](ADR-009-labelled-synthetic-data.md) | Synthetic evidence remains labelled | D010, D016 |
| [ADR-010](ADR-010-independent-source-policy-gates.md) | Terms/license review is independent of robots | D012, D016 |

All ten decisions are ACCEPTED within their stated scope. The original D005 describes a historical genesis state; D014/D020 supersede its deferred SQL Server and Joomla-role statements. No historical record is deleted. New substantive changes should add a decision with reason, alternatives, evidence, trade-offs, date and status, then identify any superseded record explicitly. Avoid inventing new ADRs for routine edits.

Evidence links lead to tracked documentation or code. Original checkpoint paths remain available only in the authoritative local project under ignored `runtime/checkpoints/`; they are not repository contents.
