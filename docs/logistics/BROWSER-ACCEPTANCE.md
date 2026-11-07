# Actual logistics browser acceptance

`scripts/browser_genesis62.py` is an existing-Edge/Playwright acceptance driver for
the new virtual foreground server. It never starts/stops a server, controls SCM,
installs dependencies or touches an older lane. Preparing or parsing this script
does not constitute browser acceptance. Root runs it only after source freeze and
the genuine owned server is ready.

The script accepts only `http://127.0.0.1:19400`, blocks external page requests and
uses a new headless Edge context. It never adopts a user's browser profile. The
fixed GENESIS-6.2 simulation token is public; real account/provider credentials are
not read. Normal acceptance pairs through the actual UI. Read-only resume instead
uses the virtual Bearer header so even a session-creation POST is avoided.

## Preconditions and execution

Use the already verified Python environment, Playwright and exact installed Edge.
The source root must have the `GENESIS-6.2-COGNITIVE-LOGISTICS/source` layout. Its
exact clean Git identity or fully verified GENESIS62 package seal must agree with
the running backend source and component `0.3.0-virtual-experimental`. The executed
controller and every served web asset are byte-compared with that bound source.
No dirty-source exception, skipped-training switch or acceptance waiver exists.

From the source directory, after root authorizes the actual run:

```powershell
& '<existing Python executable>' -B scripts/browser_genesis62.py `
    --url http://127.0.0.1:19400 `
    --output '<lane>\evidence\browser-r1' `
    --expected-source '<full frozen source commit>'
```

`--source-root` can bind the actual extracted package when the controller is
invoked from another location; controller bytes must still be identical. Output
must be a new, ordinary descendant of that bound lane's `evidence` tree. Existing
output, traversal and reparse paths are refused. A lock and checkpointed atomic
receipt preserve partial progress. A failed operation is not silently replayed.

The full journey requires its canonical stable/lost-sales, seed-400042, 60-day
episode to be new. A previous partial run is therefore visible rather than adopted
as a fresh creation. Owner reconciliation/new isolated runtime is required before
another attempt. Unrelated preexisting domain counters are not assumed zero.

## Full UI journey

The driver records actual checks and rejects a failed assertion:

- Pairing, simulation disclosure, source/component and optional package-seal
  binding, plus exact served bytes for all ten local web assets.
- A newly created canonical logistics episode and all seven real dashboard panels.
  Every rendered SKU row is compared with authenticated readback. ATP, inventory
  position, capacities and global physical conservation are checked from public
  quantities.
- Explicit order-up-to/no-acquisition replenishment: no acquired information is
  mistaken for no ordering. Actual shipment quantities are matched to real retained
  virtual orders. One explicit day advance changes world time and returns actual
  demand forecasts and all seven cost components.
- One explicit acquire-all plan. Acquisitions must be an eligible, uniquely priced
  subset within the quoted budget. A second zero-budget episode accepts none/all
  as empty acquisition subsets, retaining valid physical state.
- Invalid budget/duration/universe/hidden-truth requests are rejected without a
  domain-state delta. A real visible UI validation error is exercised separately.
- All three registered local analysis methods execute and retain their actual
  completed, hypothesis-labelled evidence and positive computation counters.
- The UI requests training seed42/cases10 exactly once and waits for genuine HTTP
  completion, up to 620 seconds. The browser transport itself has a 600-second
  limit. It requires a newly retained frozen model and a nine-arm report explicitly
  marked as a small, two-root-per-family dashboard preview. This is separate from
  the predeclared offline scientific study. The earlier GENESIS-6.1 negative result
  and lack of established superiority remain visible facts.
- Learned acquisition in an unsupported inventory-policy context must produce a
  visible error without changing that episode. A fresh supported order-up-to
  learned plan must bind the real frozen model. ACQUIRE, DEFER, IGNORE or DO_NOTHING
  can all be valid actual outcomes; the test never forces a positive estimate or
  fabricates an information benefit.
- Refresh remains passive. Older `#future` and `#research` navigation still works
  and leaves those namespaces unchanged, using baselines captured immediately
  before that navigation. It does not execute old one-shot workflows or contact
  the old servers at ports19380/19390.
- Real panel screenshots and a 520-pixel viewport verify visible UI and absence
  of document overflow. Browser errors and attempted external requests fail the
  receipt. Headless Edge is closed in `finally`.

An explicit advance uses the retained policy/control plan when that day has no
manual decision. A fresh episode starts at order-up-to/no acquisition; a later
manual selection replaces its retained control. Learned control retains its bound
frozen model until explicitly replaced. No GET advances time or submits a plan.

## Read-only comparison after a genuine owner restart

Root separately stops/restarts only the owned foreground server and records the
actual old/new process identity. Then:

```powershell
& '<existing Python executable>' -B scripts/browser_genesis62.py `
    --output '<lane>\evidence\browser-restart-r1' `
    --resume '<lane>\evidence\browser-r1\BROWSER.json' `
    --expected-source '<same full frozen source commit>'
```

Resume requires a successful prior receipt with the same source and binds its
SHA256. It blocks any mutating page request, creates no login session and compares
every recorded episode's inventory/snapshot, immutable decisions/evaluations,
metrics, forecasts, network, analyses, day/revision, budget and model identity.
Global model/experiment hashes, acquisition spending and decision count must also
match. Served bytes and new screenshots are rechecked. No decision, time advance,
analysis or training is executed in resume.

Stable hashes alone do not prove a process restart; the receipt explicitly binds
this scope to separate owner PID/orchestration evidence. A failed comparison must
remain failed and be investigated before another operation. Resume is a state
comparison, not an installation repair or a guarantee of future policy behavior.

## Evidence and uncertainty

`BROWSER.json` names each passing/failing check and records actual source/build,
browser version, served hashes, retained-state fingerprints, preview scope and
learned actions. Nine viewport screenshots cover panels, overview and narrow
layout. The receipt excludes the virtual token and does not serialize private
world descriptors or future schedules. These outputs are synthetic acceptance
evidence, not operational data or real-world accuracy claims.

A timeout or connection loss can leave genuine server-side training in progress;
the receipt retains its active operation and the user must inspect retained
results before another attempt. No automatic retry manufactures completion.

For preparation only, `--self-test` exercises endpoint/canonical-hash and acquisition
budget guards without browser, server, network or source-identity operations.
Passing that mode must never be reported as actual Edge acceptance.
