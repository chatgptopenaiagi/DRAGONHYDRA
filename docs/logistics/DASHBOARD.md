# Cognitive logistics dashboard

Component `0.3.0-virtual-experimental` adds `#logistics` beside the existing
GENESIS-6 and GENESIS-6.1 pages. Every company, SKU, demand series, inventory unit,
shipment, provider and credential used by this domain is fictional. No operational
warehouse or live supply chain is connected. Experimental comparisons do not imply
a universally superior inventory or acquisition policy.

The seven sections use public service responses:

1. **Inventory:** on-hand, reserved, available-to-promise, on-order, in-transit,
   backorder and inventory position by location/SKU, with conservation evidence.
   Repeated capacity values describe one physical location limit. Choose lost-sales
   or backorder semantics explicitly when creating an episode.
2. **Demand:** forecasts by retail location, total horizon units versus daily
   expectation, predictive variance, uncalibrated intervals and probability support.
   Sales history retains censorship/availability labels; it is not silently
   relabelled as total unobserved demand.
3. **Replenishment:** reorder point, order-up-to, base stock, `(s,S)` and
   probabilistic-cost policies, with none/all/random/handcrafted/learned information
   acquisition. Decisions submit a fresh request ID and expected snapshot revision.
4. **Network:** current nodes, edges, quoted lead times/reliability/cost/capacity,
   committed shipments and public timing. The graph is a schematic of fetched
   topology, not a geographic or optimal-route claim.
5. **Relevance:** candidate availability, quote timing/cost, acquired evidence,
   actual estimate/action records and the remaining information budget.
6. **Analytics:** actual metrics, frozen-model identities, explicit training,
   five-policy acquisition comparisons and inventory-policy comparisons. Reports
   retain costs, fill rate, cycle service level, MAE and paired baseline differences.
   Bounded method comparison/search/counterfactual results retain their service
   evidence classification and uncertainty; they cannot execute arbitrary code.
7. **Time:** accepted day, remaining duration/revision and explicit bounded daily
   advances with eligible retrospective evaluations. Initial history is synthetic
   warm-up; the first operational decision occurs at the service's declared day.

Navigation and refresh make passive GET requests only. Creating an episode,
deciding, advancing, training and analyzing are separate explicit admin actions.
A manual decision executes replenishment once. A fresh episode starts with the
order-up-to/no-acquisition control. On explicit advance, a day without a manual
decision executes the retained policy/control plan. A later manual selection
replaces that control; learned control retains its originally bound frozen model
until an explicit new decision replaces it. No browser
timer advances the world. Failed or uncertain mutations are not automatically
replayed. UI data comes from the service; no probabilities, gains, statuses or
passing acceptance results are invented by the browser.

Interactive episodes use 10–120 operational days and a 0–100 fictional information
budget. Only the explicit logistics training request gains a ten-minute browser wait;
ordinary API requests keep twenty seconds and existing future-training behavior
remains unchanged. An uncertain training
completion requires inspecting the retained experiment list before another attempt.

## Shared authenticated API

`create_app(..., realtime_config={}, future_config={}, logistics_config={})`
registers the concrete `cognitive_logistics` engine through the existing kernel
before startup. All three opt-ins must be explicit for the twenty-one-module host.
Default eighteen-module behavior, realtime nineteen and future twenty are retained.
The logistics engine depends on the host SQLite storage contract, not sporting
data. The host adapters create only a new empty virtual source and disable legacy
mutations, real-provider configuration and optional external inference.

Base: `/dragon/api/v1/logistics`.

- Authenticated passive GET: `/status`, `/episodes`, `/episodes/{id}`, `/models`,
  `/experiments`, `/experiments/{id}`.
- Admin POST: `/episodes`, `/episodes/{id}/decisions`, `/episodes/{id}/advance`,
  `/episodes/{id}/analyses`, `/training`.

Inputs are strict and reject extra fields, hidden demand/truth, unsupported policy
or analysis names and malformed identities/revisions. The existing loopback-host,
origin, session/role and 32 KiB body guards apply. The browser reuses the same-origin
authenticated transport, text-safe DOM construction and local assets. It loads no
CDN or external connector and stores no new credentials.

## New owned foreground lane

Use PowerShell 7 with `scripts/Start-Genesis62.ps1` and the existing Python
environment. No installer, dependency download, SCM control or database migration
is invoked. The server requires `GENESIS-6.2-COGNITIVE-LOGISTICS/source` and a new
marked state below its sibling `runtime` tree. A GENESIS-6/6.1-only marker or an
unmarked nonempty directory is refused. Its own `.genesis62-runtime.json` is
required; a separate exact GENESIS-6 compatibility marker enables unchanged host
virtual-state validation inside that newly owned directory only.

The default endpoint is `127.0.0.1:19400/#logistics`. Ports 18740–18751, 19380 and
19390 are refused. An occupied selected port fails without stopping its listener;
an OS lock protects one owned runtime. The printed pairing marker is public,
fictional and distinct from earlier lanes. No original profile or secret is read.

Source identity uses the exact Git root and reports dirty state. Without Git
metadata, extracted startup requires the complete bounded `GENESIS62-BUILD.json`
and `GENESIS62-PAYLOAD.json` inventory, full commit/component version/prefix,
length/SHA256/Git-blob agreement and ordinary paths. The builder shares the server's
finite file policy. Missing, changed, extra, reparse-linked or unsealed bytes are
rejected. Use Python `-B` to keep source free of bytecode caches. External package
digest/build receipts supply origin trust; local seals are not signatures.

The API guard suite uses a synthetic service spy for routing, authentication,
passivity and exact delegation. Node tests probe passive opening, all seven
sections and one revision-bound decision under a double-click. These are distinct
from mathematical and inventory-conservation acceptance. A separate authenticated
TestClient test uses the actual service to create a fresh marked backorder episode,
execute order-up-to/no-acquisition replenishment, advance one day and verify actual
metrics. Passive GETs leave the journal hash unchanged while forecast/view building
and world execution are trapped. Actual packaged browser acceptance still requires
its own recorded execution. Existing sports/native/
Android integrations are not claimed as new logistics feature acceptance.
