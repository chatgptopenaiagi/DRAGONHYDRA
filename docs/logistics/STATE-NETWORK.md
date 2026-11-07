# Virtual inventory, transport graph and cost ownership

These standard-library foundations own invented logistics data only. They do not
load retained software state, call services/providers, estimate demand or change
older forecasting mathematics. Root's world owns the clock and any private actual
arrival schedule. Inventory orders store placement, promised day, status and
observed departure/receipt days; future actual arrivals are not accepted fields.

## Physical state

`InventoryState(config)` accepts nodes `{id:{kind,capacity}}`, initial quantities
`{location:{sku:qty}}`, shelf_life (default 14) and initial_day (default 0, supporting
28 for warmed-up scenarios). Quantities/capacities are nonnegative integer units;
orders, reservations and production require positive units. The bounded catalog
allows 32 nodes/SKUs and 100,000 operation receipts. Configuration is copied.

`place_order(orderid, source, dest, sku, qty, day, promised_day)` reserves source
stock by first expiry, then creation day and stable lot ID. `dispatch` removes
those units from source on-hand and creates exactly one transit owner. `receive`
moves surviving transit lots to destination without changing their expiry. Whole
receipts must fit physical destination capacity before backorder fulfillment;
there is no implicit crossdock. Customer demand consumes unreserved FEFO stock.
Unfilled demand becomes either lost sales or explicit oldest-first backorders.
Receive, production and reservation release fulfill existing backorders, recording
both fulfilled backlog and units fulfilled on a later day.

The per-location/SKU summary exposes:

| Field | Definition |
| --- | --- |
| on_hand | Physical local units, including reserved stock |
| reserved | Local units earmarked for a reservation/order |
| atp | on_hand minus reserved |
| on_order | Outstanding incoming reservations plus shipped units, counted once |
| in_transit | The shipped subset of on_order |
| backorder | Unfulfilled customer units |
| inventory_position | on_hand plus on_order minus backorder |
| capacity | Current shared physical node capacity, repeated in each SKU row |

`verify_conservation()` returns checked global totals and raises on a failed
identity. Physical global on-hand plus transit equals initial plus production
minus fulfilled demand minus spoilage. Reservations and open orders never add
physical units. Demand equals cumulative fulfillment plus lost sales plus active
backorders. `spoilage` and `spoiled` are equal aliases for the same cumulative
destroyed units and must not be added together.

Expiry at `expiry_day <= day` destroys both local and transit lots, reduces any
affected reservation/open incoming quantity, and marks wholly spoiled orders.
Partly surviving orders can ship/arrive with their explicitly reduced physical
quantity. Every accepted operation first expires unusable lots, so an omitted
explicit daily expiry call never revives expired goods. Failed operations roll
back all their effects, including automatic expiry; an explicit successful
`expire(day)` advances the owned inventory clock independently.

`set_capacity(location,new_capacity,day,operation_id)` rejects capacity below
current physical on-hand. `set_shelf_life(days,day,operation_id)` changes future
production only, preserving every existing lot's expiry. They are explicit
interventions with typed receipts, never a stock overwrite.

`to_dict()` is flat: schema_version, config, day, skus, lots, reservations, orders,
capacities, production_shelf_life, backorders, totals, events and operations.
Orders are keyed by order ID and include original qty/ordered_qty, source/dest/SKU,
status, placed_day, promised_day, departed_day/dispatched_day, received_day,
received/spoiled/cancelled quantities and current transit slices. `from_dict`
revalidates physical conservation and identities. Snapshots are independent copies.

Explicit operation IDs make repeated requests return their original receipt;
changed payloads under the same ID fail without mutation. Order lifecycle IDs are
derived from the order ID. Demand/production accept optional operation_id; absent
IDs use the payload/day hash, so distinct identical same-day events require
different explicit IDs. Mutations require nondecreasing days; exact retries may
return earlier immutable receipts without rewinding current state.

The complete inventory ledger is simulator-owned truth. A policy/public view must
apply its declared observation boundary: censor unavailable demand/lost-sales
counters and any private world metadata. This module does not claim that every
owned accounting counter is an observation available to a policy.

## Graph and allocation

`Network({nodes,edges})` supports up to 32 nodes and 256 directed edges. Each edge
has id, source, dest, distance, lead_time, unit_cost, reliability in `(0,1]` and
integer capacity. Add a separate reverse edge when desired. Lead time is the
declared promise, not a future realized arrival. Stock capacity belongs to the
inventory; edge capacity limits the caller's planning-period flow.

`shortest_path(source,dest,metric,edge_usage=None,weights=None,
reliability_penalty=1)` uses nonnegative additive weights. Metrics are distance,
cost, time, reliability (`-log(r)`), cost_reliability
(`unit_cost + penalty * -log(r)`) and an explicit weighted combination. It returns
nodes/edge IDs, aggregate distance/lead time/unit cost, product reliability and
residual bottleneck capacity, or null when no feasible path exists.

`allocate(sources,dest,qty,metric='cost',edge_usage=None)` repeatedly chooses a
feasible residual path and caps its quantity by source availability, path capacity
and remaining request. It returns allocations, unallocated units and updated edge
usage without mutating inputs. The caller commits usage for its declared period
and uses inventory reservations for FEFO stock. This bounded greedy allocator is
not a global max-flow/min-cost-flow or vehicle-routing optimum. Static shortest
paths solve only the stated additive route objective. A separate validated Network
instance represents an explicit graph intervention.

## Seven-component costs

`CostLedger(rates=None)` records holding, ordering, shortage, transport, spoilage,
acquisition and computation in nonnegative finite virtual credits. `record(id,
component,amount,day)` records a charge; `charge` multiplies a declared quantity
and unit rate. `summary()` always exposes all seven component keys and total at
the top level. Idempotent repeats do not double-charge; conflicting IDs, negative
or nonfinite amounts fail. Serialization reconstructs the ledger and rejects
duplicate cost records. Root owns when costs accrue and atomic persistence of the
combined world; the ledger performs no real payment or resource acquisition.
