# ADR-001: Python 3.14 is the canonical orchestrator

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D001 and D020.

**Decision:** Require Python `>=3.14,<3.15`. Local machine checks use the configured `codex-pytorch` interpreter. Portable checks must also use Python 3.14; CI availability cannot justify a silent downgrade.

**Reason:** The owner made Python 3.14 an architectural invariant and the local compute/database stack has executed under it. Donor metadata requiring an older runtime does not override that decision.

**Alternatives:** Downgrade Python, import the donor environment, or evaluate compatible dependencies and narrow adapters. Use the last approach; defer unsupported work if necessary.

**Evidence:** [D001/D020](../DECISIONS.md), [Python policy](../PYTHON314_POLICY.md), [project metadata](../../pyproject.toml), and the recorded [bridge regression](../DESKTOP_CLI_BRIDGE_FINAL_REPORT.md). The historical local interpreter was Python 3.14.7; this is not a clean-machine reproduction claim.

**Trade-offs:** New native dependencies need explicit Python 3.14/Windows compatibility evidence and task-specific execution checks. The existing GPU stack is preserved rather than resolved opportunistically from generic package requirements. Machine paths remain configuration/launcher concerns, outside evidence contracts.
