# ADR-010: Terms and license review is independent of robots

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D012 and D016.

**Decision:** Evaluate access authorization, source terms, data licensing and robots state independently. Successful external ingestion requires the current reviewed policy to permit the exact source and scope. UNVERIFIED terms or license block ingestion. An absent/permissive robots file does not grant data rights.

**Reason:** Machine readability and access do not establish permission to acquire or redistribute content. Damaged extraction cannot be treated as successful legal-text review.

**Alternatives:** Infer permission from public availability or robots, accept unreadable license extraction, or require explicit independent review. Choose review with source URL, retrieval time, hash, method and uncertainty retained.

**Evidence:** [D012/D016](../DECISIONS.md), [source policy](../SPORT_SOURCE_POLICY.md), [source matrix](../../research/PUBLIC_SPORT_SOURCE_MATRIX.md), and [Web-to-SQL report](../WEB_SQL_FINAL_REPORT.md). Recorded outcomes differ: OpenFootball enabled for a bounded demo, StatsBomb UNVERIFIED, UEFA TERMS_BLOCKED and The Odds API AUTH_REQUIRED.

**Trade-offs:** Research may stop despite accessible data. Historical permission records are not perpetual approval: review freshness and source changes before acquisition. Repository source-code rights and external data rights remain independent under the [data policy](../DATA_POLICY.md); GitHub publication is a separate redistribution decision.
