# CORE NEXT module ownership

The composition root is `src/dragonhydra/kernel/composition.py`. It binds real
application engines, their narrow ports and the existing canonical domain code.
`Product` remains a compatibility facade. Registration itself establishes no
runtime readiness or data availability.

| Module | Actual engine owner | Canonical algorithms/storage reused | Required / optional dependencies |
|---|---|---|---|
| data | `kernel/engines.py:DataEngine` | `public_results`, `connectors.store`, existing source-scoped identities | None |
| odds | `kernel/engines.py:OddsEngine` | `market_signals`, `scenario`, retained connector quote provenance | data |
| prediction | `kernel/engines.py:PredictionEngine` | `cognition.models` and retained-source resolver | data / memory for explicit persistence |
| memory | `kernel/engines.py:MemoryEngine` | `cognition.memory` immutable records and receipts | data |
| evaluation | `kernel/engines.py:EvaluationEngine` | `cognition.evaluation`; existing memory persistence validation | memory / prediction implementation may be absent when evaluating older records |
| ai | `kernel/engines.py:AIEngine` | frozen `local_ai`/`local_ai_context` packages, `local_ai_service`, protected settings | data; external configured model is optional |

`domain.py` supplies shared pure API/identity/clock definitions. Engines receive
`ApplicationContext`, `StoragePort`, `ProviderReadPort`, `DataReadPort`,
`ModelPort` and `MemoryPort` as applicable. They neither import Product nor use
an unrestricted service locator. Existing mathematical modules are unchanged.
Composition owns concrete adapter selection; independently injected test ports
exercise engines without constructing Product or Kernel.

The durable queue remains `jobs.py`. `kernel/job_dispatch.py` receives explicit
callbacks, dispatching the same supported job kinds. Claim generation, fencing,
lease/heartbeat, retries, cancellation, scheduler and publication transactions
remain in their existing owner. No second queue, database, provider schedule or
authentication system was introduced.

Source, profile and live state are separate. This edition uses its independently
validated installation profile, private lab state, unique installation-scoped API
cookie and existing Joomla HMAC identity mechanism. Original DRAGONHYDRA paths,
services and accounts are never a backend fallback.
