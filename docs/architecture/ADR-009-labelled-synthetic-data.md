# ADR-009: Synthetic data must remain visibly labelled

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D010 and D016.

**Decision:** Keep synthetic examples, generated odds and test-fixture handoffs explicitly synthetic at observation and capture-origin levels. Synthetic demonstrations may prove code paths but cannot establish external fact accuracy, live-market quality or genuine Desktop research.

**Reason:** A successful pipeline can process invented input just as successfully as real evidence. Unlabelled synthetic records would inflate capability claims and contaminate future model evaluation.

**Alternatives:** Reuse real-looking examples without labels, silently mix examples with observed data, or retain generator provenance and separate classifications. Choose explicit labels through storage, reports and presentation.

**Evidence:** [D010/D016](../DECISIONS.md), [odds model](../ODDS_OBSERVATION_MODEL.md), [bridge report](../DESKTOP_CLI_BRIDGE_FINAL_REPORT.md), and [envelope schema](../../config/browser-handoff-envelope.schema.json). The recorded synthetic bridge inserted two observations and its replay inserted none; neither result is a browser capture claim.

**Trade-offs:** Labels need to survive every transformation and selection. Synthetic confidence describes generation/provenance, not outcome accuracy. Curated safe fixtures may be version-controlled under the [data policy](../DATA_POLICY.md); generated runtime datasets and receipts remain outside Git by default.
