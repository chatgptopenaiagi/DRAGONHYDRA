# ADR-002: SQL Server owns structured intelligence

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D014, D017 and D020.

**Decision:** SQL Server is the primary owner of versioned structured intelligence: validated external observations, provenance, conflicts and processing history. Runtime writers use fixed operations and narrowly scoped SELECT/INSERT grants.

**Reason:** One authoritative owner prevents competing truth stores and preserves reproducible evidence history. Local SQL Server capability was measured before the dedicated sports schema and bridge tables were added.

**Alternatives:** Store the same observations in MariaDB too, make a universal SQL executor, or keep explicit dataset ownership and typed adapters. Choose explicit ownership; summaries are derived artifacts with their own timestamps.

**Evidence:** [D014/D017/D020](../DECISIONS.md), [sports schema](../SQLSERVER_SPORTS_INTELLIGENCE.md), [Web-to-SQL report](../WEB_SQL_FINAL_REPORT.md), and [bridge report](../DESKTOP_CLI_BRIDGE_FINAL_REPORT.md). D020 explicitly supersedes D005's older deferred SQL Server role.

**Trade-offs:** SQL storage and MariaDB cache publication are separate commits requiring observable recovery. The present relational/JSON schema is not a completed warehouse or cross-provider entity-resolution system. SQL Server's existence does not justify automatic replication or greater grants.
