# GENESIS-6.1 future relevance laboratory

Component `0.2.0-virtual-experimental` is a separate, wholly fictional increment
on GENESIS-6 application `c269cf00e712340977b97985eb27ec23c7709ab0`, with delivery
baseline `4f17ccde30a9598f05ac200464d2e45e44885db1`. Its branch is
`research/genesis61-future-relevance-20261106`. It neither installs a Windows
service nor promotes a CORE NEXT release. Source, runtime, evidence and dist live
under the new `GENESIS-6.1-FUTURE-RELEVANCE` lane.

## Executable boundaries

`environment.py` owns seeded private worlds and reveals only eligible quoted
observations. `forecast.py` adapts the unchanged GENESIS-6 residual-time probability
kernel to one requested target/horizon. `learning.py` fits category-specific
regularized regression using whitelisted decision-time features. `policies.py`
implements acquire-all, acquire-none, seeded random, handcrafted and learned
actions. `experiments.py` fits and selects before constructing final-test worlds.
`service.py` validates actions, costs and forecasts; `journal.py` stores immutable
decisions, acquisitions, predictions, evaluations, models and experiments. Derived
episode views and credit ledgers remain mutable. `router.py` exposes the opt-in
authenticated API; `server.py` owns a foreground loopback process and marked state.

The policy receives a public snapshot, not a `VirtualEpisode`, universe name,
random seed, simulator hazard law, hidden observation, future goal or outcome.
Visible scores advance only with virtual time. Public snapshots explicitly mark
unobserved card effects as a baseline assumption rather than a verified absence.
The trusted simulator/evaluator can inspect privileged state only to generate
observations and later labels. This is an application boundary, not a sandbox
against an administrator editing Python.

## Temporal and numerical contract

An episode fixes target origin and maturity. Advancing time never rolls a horizon
forward or changes its outcome. Supported targets are GOAL_OCCURRENCE,
FULL_TIME_RESULT, NEXT_GOAL_SIDE and REMAINING_GOALS. Horizons are 1, 5, 10, 30
minutes and FULL_TIME when valid; FULL_TIME_RESULT requires FULL_TIME.
NEXT_GOAL_SIDE includes a no-goal class; goal counts include a 13PLUS tail.
All exhaustive vectors must be finite, bounded and sum to one within 1e-12.

Candidate categories are possession, shots, fatigue and red_cards. Fatigue is
unavailable until two virtual minutes after the initial decision. A pending
observation can be ranked and deferred, but never read early. A retained DEFER
may resume on an explicit eligible clock advance using its original frozen model.
Passive GET, restart and status inspection neither advance time nor acquire data.
An advance that passes maturity does not retroactively acquire information.

Initial decision-time features remain immutable. Later evaluation links the
earlier estimate with the actual acquisition and its same-cutoff marginal loss
change. This distinguishes the benefit of new information from time passage.
Outcome labels become available only after maturity plus the declared delay.
Forecasts and decisions are never rewritten after evaluation.

## Costs, persistence and compatibility

Acquisition debits use actual seeded quotes in virtual credits. Each actual
requested-horizon kernel call costs 0.001 additional computation credits. Policy
CPU latency is measured separately and is not monetized. Limits include the
match budget and a transactional shared experiment acquisition cap of 100 by
default. An exhausted budget or negative estimated net value can produce no action.

SQLite BEGIN IMMEDIATE and revision checks serialize decisions; request identity
replay returns the exact historical receipt without another debit. Failed
trajectories commit no observations or charges. Evidence tables reject UPDATE
and DELETE. The new database cannot adopt a foreign nonempty database or reparse
path. Runtime ownership requires the new lane marker and OS process lock.

The original default module registry remains eighteen modules. GENESIS-6 replay
is opt-in nineteen; future relevance is opt-in twenty. Existing replay,
corrections, branching, nine virtual mathematical tools and mock Responses bridge
remain available at `#research`. Future research is additive at `#future`.
No paid requests, external credentials, provider acquisition, sporting database
read, Joomla change, SCM operation or release publication is part of this lane.

## Remaining research limits

These finite worlds do not establish sporting accuracy, real calibration or
general intelligence. The learned policy can be worse than no acquisition. The
batch five-arm study compares same-cutoff trajectories: DEFER is retained but not
automatically resumed in that batch. The separate interactive acceptance tests
the full prospective defer/resume/outcome journey. Estimates of pending value are
evaluated independently using later same-time shadow acquisitions. These scopes
must not be combined into a claim of sequential-policy superiority.
