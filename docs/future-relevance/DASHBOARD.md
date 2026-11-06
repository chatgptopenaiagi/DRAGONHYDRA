# Future relevance research dashboard

Component `0.2.0-virtual-experimental` is an opt-in virtual research extension.
The new `#future` page is separate from the preserved GENESIS-6 `#research` page.
All observations, outcomes, costs, provider responses and credentials are fictional.
This increment does not establish live availability or real-world predictive value.

The four selectable targets are goal occurrence, full-time result, exhaustive next
goal side (home/away/no goal), and remaining goals (0–12 plus the 13PLUS tail).
Full-time result requires the full-time horizon; the other targets support
1/5/10/30/full-time playing-minute horizons where the service permits them.
Seven synthetic universe configurations are selectable. The public snapshot never
supplies hidden family rules, latent values, seeds or ineligible future outcomes.

Opening or refreshing the page only reads retained public state. Creation is
explicit. The page shows the accepted revision, observed synthetic state, acquired
categories, candidate availability and quoted acquisition/computation costs, and
the service's experimental relevance estimates. Possession, red cards, shots and
fatigue are candidate information categories, not automatically known evidence.
An unavailable estimate remains unavailable; the UI invents no probabilities,
utility numbers, green statuses or passing reports.

Choose acquire all, acquire none, random, handcrafted or learned policy. Executing
a decision sends the current snapshot revision and a fresh random request ID.
The server determines which information is eligible, enforces the budget, and
retains the decision. The UI does not retry uncertain requests automatically.
Before/after forecasts, actual actions, paid costs and remaining budget come from
the retained response. A later explicit time advance makes outcomes eligible;
retrospective paired evaluation remains separate from decision-time estimates.

The training button requests a frozen policy and train/validation/held-out report.
Inspect retained model identities and reports independently. The five-policy
comparison displays fetched Brier/log loss, acquisition/computation costs, net
usefulness and paired difference against acquire none. Negative results are
retained. Detailed returned reports expose uncertainty and split limitations;
the dashboard does not turn held-out observations into automatic model updates.

## Authentication and API

`create_app(..., realtime_config={}, future_config={})` registers the concrete
`future_relevance` kernel extension before startup, after the same virtual-state
barriers as realtime. Default application inventory remains eighteen modules;
realtime alone remains nineteen; both opt-ins produce twenty. Read routes share
the existing authenticated router. Mutations also require the existing admin role,
loopback host/origin checks and 32 KiB request bound. Requests forbid extra fields,
real provider inputs, unsupported target/horizon pairs and malformed revisions.

Base: `/dragon/api/v1/future`.

- Passive GET: `/status`, `/models`, `/models/{id}`, `/episodes`, `/episodes/{id}`,
  `/experiments`, `/experiments/{id}`.
- Admin POST: `/episodes`, `/episodes/{id}/decisions`, `/episodes/{id}/advance`,
  `/training`.

The dashboard uses the existing same-origin authenticated request function. It
adds no browser credentials, external scripts or CDN dependencies. Text renders
through DOM text nodes; the packaged web files exactly mirror desktop web sources.

## Isolated launcher and package identity

Use PowerShell 7 with `scripts/Start-Genesis61.ps1` and an existing Python
environment. No installer or dependency download is invoked. The foreground
server requires the `GENESIS-6.1-FUTURE-RELEVANCE/source` lane and creates only a
new marked descendant of that lane's `runtime` directory. An old unmarked state
or a GENESIS-6-only marker is refused. Its own `.genesis61-runtime.json` is required
first; an exact `.genesis6-runtime.json` compatibility marker exists only inside
that newly owned state so unchanged virtual API restart validation remains active.

Default port is loopback `19390`. The launcher refuses ports 18740–18751 and the
GENESIS-6 port 19380. It does not inspect or stop other listeners or SCM services.
An exclusive OS lock protects the owned runtime. The printed pairing token is a
public simulation marker, distinct from the old lane's marker.

Git identity comes from this exact checkout and reports dirty bytes honestly.
An extracted curated package may fall back only without any Git metadata and
after complete verification of `GENESIS61-BUILD.json` and `GENESIS61-PAYLOAD.json`:
full source commit, component version, exact prefix/inventory, bounded file policy,
lengths and SHA256/Git-blob hashes must agree. Changes, extras, missing files,
reparse links, invalid seals and Git failures are errors. Use Python `-B` to keep
bytecode out of sealed source. The external ZIP digest/build receipt supplies
origin trust; local seal verification is not a signature or continuous monitoring.

The new API guard tests use a synthetic service spy to verify real authentication,
module binding, passivity and one-time delegation. A separate test uses the actual
service through authenticated TestClient: creation, a baseline information
decision and time advancement produce a retained eligible retrospective
evaluation. Its passive reads neither forecast nor change the journal hash.
Detailed algorithm and hidden-data privacy tests belong to the service/policy
suites. Node syntax/DOM tests verify
passive initial navigation and explicit revision-bound decisions. Actual packaged
server and browser acceptance require separate execution; no native client,
Android, SQL or live-provider acceptance follows from these tests.
