# ADR-007: Desktop and CLI exchange explicit filesystem artifacts

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D013 and D016–D018.

**Decision:** Desktop research publishes a strict BrowserHandoffEnvelope and hashed, bounded artifacts. The Python 3.14 one-shot consumer validates, claims, archives, appends to SQL Server and publishes a bounded MariaDB summary. Capture origin and processing status remain separate.

**Reason:** Files provide an inspectable interface between independent browser/research and engineering surfaces. A successful CLI fetch cannot establish a genuine Desktop observation.

**Alternatives:** Share live memory/browser sessions, rely on informal copied notes, or use a closed versioned file contract. Choose the explicit contract with atomic publication, replay identity and immutable receipts.

**Evidence:** [D013/D016–D018](../DECISIONS.md), [bridge specification](../CODEX_DESKTOP_CLI_BRIDGE.md), [schema](../../config/browser-handoff-envelope.schema.json), and [synthetic proof report](../DESKTOP_CLI_BRIDGE_FINAL_REPORT.md).

**Trade-offs:** The protected local filesystem is a trust boundary; envelopes are not browser-signed attestations. SQL and MariaDB commits are independent, interrupted claims require deliberate recovery, and Desktop availability cannot be assumed. The synthetic end-to-end demonstration does not close the pending genuine Desktop plus separate Codex CLI session proof gate.
