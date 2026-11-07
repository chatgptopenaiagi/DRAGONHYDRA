# GENESIS-6.2 cognitive logistics research

DRAGONHYDRA is a modular mathematical research platform. This component is a
100% virtual domain experiment, not an ERP, WMS, POS, TMS or commercial inventory
system. Component version is `0.3.0-virtual-experimental`; the reused host API
keeps its existing version contract. No real provider, external AI or credential
is required or contacted.

## Implemented boundaries

`state.py` owns integer FEFO lots, reservations, backorders, capacity, orders and
single-owner transit. Every operation checks physical conservation and records
an idempotent typed receipt. Inventory position is OH+OO-BO; ATP is OH-reserved.
In-transit units are already within OO, not added twice. Production is an explicit
inflow; customer fulfillment and spoilage are explicit outflows. Capacity and
future-production shelf-life interventions never silently rewrite quantities.

`network.py` owns a bounded directed graph, distance/cost/time/reliability and
combined cost-reliability paths, shared edge capacities and greedy allocation
from available suppliers. There is no general vehicle-routing or multi-echelon
optimality claim. `costs.py` records holding, ordering, shortage, transport,
spoilage, information acquisition and computation in fictional credits.

`forecast.py` provides eight actual demand estimators and a completed-receipt
lead-time mixture with processing/transport/receiving/disruption marginals.
`policies.py` implements five replenishment policies and distinct CSL/fill
constraints. Probabilistic cost searches a finite feasible quantity set under a
declared one-period surrogate. Capacity, supply and route clipping can make
service targets infeasible; predicted service is not a realized guarantee.

`world.py` generates hidden seeded demand, noisy observable proxies and hidden
individual arrival schedules. Policies receive only a public inventory snapshot.
Privileged truth is available only to the simulator and later evaluator.
`computation.py` caches exactly the history, eligible evidence, model, horizon and
clock dependencies of forecasts; stock-only events need not recompute demand.
Reference calculation bypasses the cache for numerical comparison.

`relevance.py` fits category-specific regularized regressions for five-day gross
relevant-cost reduction, reusing only the prior pure small-matrix solver. It does
not map inventory into sporting-event schemas or reuse football intensities.
Past-only features include inventory, censored observed history, completed lead
times, time, shelf life, public topology, acquired values, freshness and budget.
Family names, seeds, future outcomes and actual hidden arrivals are excluded.
The learned policy is trained for order-up-to and rejects unsupported inventory
policy contexts. Acquire/defer/ignore/do-nothing are actual bounded actions.

`experiments.py` freezes the selected model before final rule families are
constructed. `analytics.py` executes registered past-only comparisons, bounded
scale/blend candidates and paired virtual interventions. It distinguishes facts,
mathematical results, associations and unverified hypotheses. No text is executed
as Python, SQL, shell, stock modification or probability override.

`journal.py` stores current derived views separately from immutable events,
decisions, acquisitions, forecasts, outcomes, evaluations, analyses, models and
experiments. `service.py` uses SQLite transactions and revision guards, enforces
shared acquisition budgets, reconciles duplicate request IDs and evaluates all
mature unevaluated receipts rather than only a recent display page. Passive GET
does not run a forecast, acquire information or advance time.

`router.py` adds authenticated domain operations to the existing opt-in host.
Default registry remains eighteen modules, replay nineteen, future relevance
twenty, logistics twenty-one when explicitly configured. `server.py` and
`Start-Genesis62.ps1` own a new foreground loopback19400 runtime and OS lock.
Protected ports19380/19390 and legacy reserved ports are rejected. The seven
dashboard sections use actual service values and explicit mutation controls.

## Simulation and cost assumptions

The operational sample has one SKU, supplier/warehouse/two retailers, plus an
extra supplier and distribution-center route in the multi-location family.
The generic inventory/network primitives accept larger bounded configurations;
the dashboard selects six declared templates rather than acting as a commercial
network editor. Initial day28 has explicit fictional warm-up records0..27;
those records predate the new physical stock ledger.

Families are stable, intermittent, seasonal, supplier_disruption, perishable and
multi_location. Default product shelf life is14days; perishable uses8. Initial
supplier stock1000, warehouse40 and retailers12each are fictional assumptions.
The primary source replenishes exogenously by1000 when below500; production is
recorded as an inflow. Secondary source availability is finite. These rules can
produce large upstream waste and are not optimized manufacturing policies.

The operational objective prices all network OH plus transit at0.02/unit-day,
each accepted shipment order at0.5, newly unfulfilled units at5, actual route-unit
transport quotes, spoilage at1/unit, actual sensor quotes and registered
computation work. Matrix-value estimates, forecast calls, optimizer candidates,
routing calls and explicit analytical work have declared virtual prices. CPU and
wall time are measured separately; the credit model is not a real economic model.
The replenishment surrogate uses the same basic prices and a disclosed observed
shelf-life risk proxy; it is not an exact dynamic solution of the full trajectory
objective. All service/cost trade-offs remain measurable against strong baselines.

Demand observations are sales plus censoring flags for lost-sales mode, or known
customer orders in backorder mode. Missing demand is never relabelled as zero.
The evaluator may inspect later actual virtual demand; the decision policy cannot.
Supplier reliability includes all supplier-origin promises due by the cutoff,
including spoiled/overdue failures. Completed-delivery on-time metrics and bounded
analytic-window reliability are separately labelled to avoid survivor confusion.

## Preservation and limitations

The baseline is GENESIS-6.1 documentation commit67c531, containing accepted
application0e09db6, published as `v0.2.0-genesis61-virtual.1`. Its negative result
remains: learned acquisition did not establish superiority over acquire-nothing.
This increment measures an independent inventory question and cannot reinterpret
that earlier result. All old mathematical modules, sealed distributions,
installations, databases, releases and Codex are preserved.

Single-SKU templates, configured Poisson approximations, finite horizons, greedy
network allocation and virtual costs limit interpretation. Better tests, fewer
forecast calls or attractive explanations are not proof of better decisions.
No real-world accuracy, commercial readiness or global optimum is claimed.
