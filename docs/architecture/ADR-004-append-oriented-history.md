# ADR-004: Evidence corrections append immutable versions

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D004, D014 and D018.

**Decision:** Retain original evidence and append corrections with version/predecessor identity and their own availability. Preserve receipt/checkpoint attempts instead of overwriting failed or earlier evidence. Operational caches may be rebuilt; historical intelligence must not silently mutate.

**Reason:** Overwriting a result can change what a historical prediction appears to have known. Preserved versions allow replay, provenance review and explicit recovery.

**Alternatives:** Mutable fixture upserts, replacement of old checkpoint files, or versioned appends. Choose versioned appends and explicit supersession.

**Evidence:** [D004/D014/D018](../DECISIONS.md), [temporal contracts](../../src/dragonhydra/medusa/evidence.py), [sports storage](../SQLSERVER_SPORTS_INTELLIGENCE.md), and [bridge persistence/replay](../CODEX_DESKTOP_CLI_BRIDGE.md). Recorded synthetic replay inserted zero additional observations.

**Trade-offs:** History needs storage, identity and replay rules. A same-ID handoff with changed bytes fails; an identical replay may create a new processing receipt. File immutability is an application convention and SQL runtime permissions are bounded controls, not proof against a trusted administrator. Retention or migration changes require explicit review rather than silent deletion.
