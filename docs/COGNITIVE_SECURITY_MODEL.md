# Cognitive security model

The cognitive layer receives a bounded sanitized derivative of controlled project state. It does not own source truth, source policy, credentials, database administration or the operating system.

| Boundary | Required behavior |
| --- | --- |
| State input | Select permitted fields; retain temporal/provenance metadata; reject or exclude secret-bearing/unexpected content. Raw database records and arbitrary files are not AI context. |
| Temporal state | Enforce as-of eligibility; keep future hypotheses/predictions/simulations distinct from observations and retain reconstruction/synthetic labels. |
| AI output | Closed typed structure, explicit actor/model identity, hashes, bounded short rationale and non-evidence conclusion types. No hidden chain-of-thought field or executable code payload. |
| Source text | Treat all acquired content as untrusted data. It cannot issue instructions, create capabilities or override policy. |
| Action decision | Originating request hash/scope, snapshot/cursor and allow-listed capability must match; unsupported, unavailable, stale or invalid requests fail closed. |
| Research | A proposal cannot bypass permitted HYDRA acquisition, MEDUSA validation, accepted evidence memory and recalculation. |
| Local runtime | Explicit timeout/context/output limits; no automatic web/filesystem/DB tools. Missing runtime is BLOCKED; mock remains labelled. |
| Artifact store | Project-local bounded paths, validated serialized artifacts and immutable/hash-referenced history. Runtime files remain ignored and outside htdocs. |
| Presentation | Sanitized read-only status only; no web controls for arbitrary cognitive actions or credential exposure. |
| Learning | Measured, referenced, temporally replayable feedback; no claimed accuracy gain without observed outcome and valid comparison. |

No runtime capability grants unrestricted shell or SQL, secret extraction, credential dumping, authentication/paywall/CAPTCHA/robots bypass, wagering, unbounded scraping, silent policy override or silent self-modification. Engineering Codex is a separate owner-authorized development role and does not transmit its tool authority to runtime proposals.

Hashes detect changes relative to retained artifacts; they are not trusted timestamps, signatures or independent source attestation. A local typed validator is not an operating-system sandbox. A future live adapter still needs explicit runtime/model approval and transport/resource validation. Existing service binding and loopback SQL TLS limitations remain as documented in [security](../SECURITY.md); this layer does not certify the host perimeter.

Secret-like text rejection is defense in depth, not proof that every encoded or novel secret can be detected. The primary protection is the fixed field projection and opaque source/provenance references: credentials and raw source prose are not selected for the snapshot. Trusted engineering producers must still obey the same data boundary when supplying goals, short summaries or other allowed text fields.

Only small sanitized summaries belong in Git. Secrets, model weights, raw captures, generated cognitive artifacts and full checkpoints remain ignored. Before publication, audit exact staged blobs, forbidden paths, sizes, Markdown links and the relevant Python 3.14 tests. See [data policy](DATA_POLICY.md) and [test tiers](TESTING.md).
