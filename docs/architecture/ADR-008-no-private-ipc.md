# ADR-008: Do not integrate through private Codex IPC

**Date:** 2026-09-24. **Status:** ACCEPTED; indexes D015 and D020 and the bridge security boundary.

**Decision:** Use supported browser surfaces and the explicit project handoff. Do not inspect or depend on private Codex pipes, process memory, session/auth databases, browser profiles or undocumented IPC. Do not transfer browser credentials into the project.

**Reason:** Private interfaces and session internals create fragile coupling and unnecessary access to authentication material. They do not improve the auditable evidence contract.

**Alternatives:** Reverse-engineer private messaging, share authenticated profiles, or use public capture artifacts and supported commands. Choose artifacts and supported commands; record a truthful blocked result when a required surface is unavailable.

**Evidence:** [D015/D020](../DECISIONS.md), [handoff security model](../HANDOFF_SECURITY_MODEL.md), [bridge specification](../CODEX_DESKTOP_CLI_BRIDGE.md), and the owner's permanent Desktop/CLI role boundary in the [roadmap](../DRAGONHYDRA_MASTER_ROADMAP.md).

**Trade-offs:** The operator may need separate Desktop and CLI steps. Convenience does not justify reading private internals or relabelling a CLI fetch as Desktop proof. Existing local application/service settings remain outside this integration's scope.
