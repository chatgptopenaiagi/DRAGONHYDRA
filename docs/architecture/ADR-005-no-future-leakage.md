# ADR-005: Historical analysis must not use future information

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D004 and D020.

**Decision:** Distinguish real-world event time, observation, proven availability, revision, ingestion and prediction/replay cutoff. Select only evidence eligible at the requested cutoff. A historical event date cannot prove historical availability or justify backdating a new observation.

**Reason:** Later results and corrections otherwise contaminate historical predictions, evaluation and training. Temporal discipline is a permanent project law.

**Alternatives:** Gate only by kickoff/event time, use latest values in replay, or use explicit as-of contracts and immutable versions. Choose the latter. Generic availability permits equality at the cutoff; score-derived kickoff features can request the explicit strict-before policy.

**Evidence:** [D004/D020](../DECISIONS.md), [Pyramid temporal meanings](../PYRAMID_ARCHITECTURE.md), [evidence tests](../../tests/test_evidence.py), and [bridge security/storage rules](../HANDOFF_SECURITY_MODEL.md). Historical fixture timezone remains unknown where the source does not establish it.

**Trade-offs:** Unknown availability must remain unusable or quarantined instead of guessed. Current conservative contracts do not establish a generalized archival-proof model or completed historical Feature Factory. Every future feature, model and simulation must preserve these boundaries and test cutoff/correction behavior.
