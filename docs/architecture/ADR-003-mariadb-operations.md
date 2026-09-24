# ADR-003: MariaDB owns operational and presentation state

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D014, D018 and D020.

**Decision:** MariaDB owns local job/integration state and bounded presentation caches. SQL Server owns the underlying structured sports intelligence. The local PHP endpoint receives only its dedicated cache-reader capability.

**Reason:** XAMPP/Joomla can display human-readable state without duplicating the intelligence store or exposing SQL Server credentials to PHP. Operational writes remain distinct from append-only evidence history.

**Alternatives:** Replicate all SQL observations, query SQL Server directly from the page, or publish a bounded DTO. Choose the bounded DTO with explicit build time and recovery behavior.

**Evidence:** [D014/D018/D020](../DECISIONS.md), [pipeline](../WEB_SQL_PIPELINE.md), [dashboard](../JOOMLA_INTELLIGENCE_DASHBOARD.md), and [handoff security](../HANDOFF_SECURITY_MODEL.md). The bridge reuses two small cache rows rather than replicating observations.

**Trade-offs:** A cache can lag after a successful SQL commit. Receipts expose partial success and replay repairs publication without duplicating SQL observations. Joomla integration currently means a custom localhost-only endpoint under its directory, not a native Joomla extension or edits to core/content tables.
