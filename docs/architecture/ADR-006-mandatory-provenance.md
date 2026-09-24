# ADR-006: Important external facts require provenance

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D012, D016 and D020.

**Decision:** Carry source identity and URL, retrieval/observation times, available content hashes, parser/version, confidence, verification state and applicable terms/license metadata through validation and storage. Preserve links from derived results to input evidence. HYDRA collects; MEDUSA validates.

**Reason:** An unexplained number or source name cannot establish what was observed, whether it was permitted, or which revision supported a calculation. Provenance is a permanent project law.

**Alternatives:** Keep only normalized values, trust brand reputation, or preserve verifiable acquisition and transformation context. Choose the latter and retain uncertainty explicitly.

**Evidence:** [D012/D016/D020](../DECISIONS.md), [source policy](../SPORT_SOURCE_POLICY.md), [envelope schema](../../config/browser-handoff-envelope.schema.json), and [pipeline](../WEB_SQL_PIPELINE.md). Corrupt license extraction remained UNVERIFIED and did not authorize StatsBomb ingestion.

**Trade-offs:** Metadata and artifact retention add storage and validation cost. A hash proves byte identity, not external truth or permission. Local producer labels and receipts are trusted-file provenance, not cryptographically attested browser capture. Confidence scores do not automatically represent calibrated probabilities.
