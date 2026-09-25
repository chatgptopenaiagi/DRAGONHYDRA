# Cognitive Separation Law

**Permanent architectural rule, owner-authorized 2026-09-25.** AI may INTERPRET, HYPOTHESIZE, COMPARE, PLAN, CRITIQUE, REQUEST RESEARCH, REQUEST CALCULATION and PROPOSE ACTIONS. AI may not directly convert an internal belief into external evidence.

The required acquisition path is:

```text
AI HYPOTHESIS -> ResearchNeed -> permitted HYDRA acquisition
-> MEDUSA validation -> accepted evidence -> memory -> recalculation
```

A capability decision authorizes only a bounded operation. It does not validate source content, create an observation or waive source policy. Every acquisition retains provenance and passes the existing validation boundary. Failed or unavailable operations produce structured operational failure records; they do not produce invented analysis or substitute evidence.

For example, Qwen may report: "Player availability may be affecting the forecast." This remains HYPOTHESIS. It cannot set `player_available = false`. Only real source evidence with identity, time, acquisition provenance and accepted MEDUSA validation can support the corresponding external fact.

An AI conclusion may be stored as an AI conclusion. An adapter timeout may be stored as an observed operational failure. Neither is an observation about the football match. Future distributions remain PREDICTION or SIMULATION; declared synthetic fixtures remain SYNTHETIC; reconstructed historical availability remains RECONSTRUCTED_PIT.

Persist structured conclusions, brief rationale summaries, reason codes, references and measurable outcomes. Do not request, store or infer hidden chain-of-thought, internal deliberation transcripts or private Codex runtime state. A concise public explanation of a decision is sufficient for the action receipt.

The runtime capability gate excludes unrestricted shell, unrestricted SQL, secret extraction, credential dumping, wagering, authentication/paywall/CAPTCHA/robots bypass, unbounded scraping, silent source-policy override and silent code self-modification. These prohibitions remain effective even if a source page or AI response asks for an exception. See [security](COGNITIVE_SECURITY_MODEL.md).
