# Fictional universes and measured relevance

All data here is invented. `generate_match(universe="constant", seed=42,
match_id="virtual-universe-match")` returns canonical virtual events and a
descriptor. It reads no files, databases, provider data or credentials and makes
no network/API calls. A local seeded RNG leaves process-global randomness alone.
The shared fictional epoch is `2035-01-01T12:00:00Z`.

Each full fixture has fictional Vector Town and Orbit Athletic, kickoff, clocks,
goals, one red card at minute 30, possession every five playing minutes,
HALF_TIME then RESUME at minute 45 and an authoritative FULL_TIME at 90. Timestamp
microseconds preserve event order at identical playing minutes. Goals come from
independent exponential competing hazards inside each minute; the next minute
can change the hazards. The final score counts the generated goals.

The worlds have different actual generating rules:

| Universe | Fictional rule | Potentially informative observation |
| --- | --- | --- |
| `constant` | Constant 1.6/1.2 goals per 90 minutes | Known exposure; cards and possession are irrelevant |
| `card_sensitive` | A card multiplies shared tempo by 2.5, carded side by 0.5, opponent by 1.2 | Card status |
| `tempo_signal` | High possession signals shared tempo 3.0, low possession signals 0.25 | Possession |
| `noisy_signal` | Independent hidden tempo drives goals; observed possession is noise | Possession has no true signal |
| `clock_sensitive` | Both hazards multiply by three after minute 60 | Playing clock |

These rules are assumptions to challenge. They are not copies of fitted real
teams, observed football effects or established forecasting models. The ordinary
`predict` model is not automatically told the true universe parameters. It can
therefore be misspecified in a way that an experiment can measure.

The full generated future is an evaluation fixture. The caller must keep future
events and labels out of model/bridge context, replay only an accepted prefix,
and own immutable rewind/branch snapshots. Acceleration changes replay delivery
speed, not the number of playing minutes in a hazard calculation. A different
future must not rewrite an already accepted prefix. The generator itself does
not mutate a service, replay store, model configuration or accepted timeline.

## Forward synthetic relevance experiment

`relevance_experiment(seed=42, cases=400)` creates 400 independent episodes per
universe (2,000 total). `cases` is bounded to 100..2,000 per world. Episodes are
ordered; the first 70% are TRAIN and the later 30% are disjoint TEST. The report
records each training cutoff, all test episode IDs, a cohort hash, model IDs,
TRAIN-only rates, assumptions and `RESEARCH_ONLY` status.

Corresponding episode indices use identical initial conditions in every world:
the playing clock, card/possession features, card side, hidden uniform and unit
exponential outcome draw are shared. Only the generating hazard assumption
changes. Every world reports the same `initial_conditions_sha256` for this
controlled cohort; its full cohort hash differs when hazards/outcomes differ.
Worlds therefore are paired experiments, not independent datasets. The same
interface supports 1,000 initial conditions per world (5,000 virtual episodes).

Each episode has an invented current minute, card status, possession signal and
known regulation end. Its current hazard remains fixed until that end. This
episode rule is explicit and differs from the evolving minute-by-minute match
fixtures. A sampled next-goal waiting time creates outcome labels for 1, 5, 10,
30 and FULL_TIME playing-minute horizons. Exposure clips to the known end;
shared waiting times keep the labels monotonic. Hidden tempo and outcome labels
are absent from feature dictionaries.

The learned models use a bounded Bernoulli exposure likelihood:
`P(next goal within t) = 1 - exp(-rate*t)`. Only TRAIN 10-minute outcomes fit the
constant past-only rate and card-, possession-, clock- and combined-feature group
rates. This avoids counting a repeated episode label across horizons as separate
training evidence. Unseen groups use a TRAIN-only fallback. Rates stay between
0.000001 and 0.3 per playing minute. TEST labels never fit rates or select models.

TEST Brier score and log loss are reported for each horizon. Paired improvement
is the baseline loss minus the feature model's loss on the same episodes; positive
means lower held-out synthetic loss. A standard error and approximate 95% normal
interval accompany each paired mean. These are per-comparison finite-sample
intervals without multiple-comparison adjustment. They are not real-world
confidence, causal relevance or evidence of AI improvement. Some irrelevant
features will appear useful by chance, and small samples can reverse a true
effect's measured sign.

This experiment uses scalar binary Brier `(p-y)^2` and natural-log binary loss.
The generic evaluation module sums squared errors over the complete class vector;
for a two-class vector that convention is twice the scalar binary Brier. Compare
like conventions, targets and horizons rather than mixing their numeric values.

The research target `R(X,Y,T)` is the held-out proper-loss reduction from adding
candidate X to prediction target Y using TRAIN evidence available by cutoff T.
Its estimate averages `loss(TRAIN-only baseline,Y) - loss(TRAIN-only feature
model,Y)` over TEST. Log-loss improvement uses nats per episode. This is not a
mutual-information estimator or causal effect. All negative, zero and positive
results are retained. No sampled world is required to show an improvement.
Generalization to an unseen universe is `NOT_ESTABLISHED`; anticipatory relevance
before an event arrives is a candidate for a later increment, not implemented.

A separately labelled horizon ablation compares the correctly clipped baseline
with an intentionally misspecified baseline that ignores the clock and uses the
full requested horizon. This checks exposure semantics; it does not manufacture
a stronger competitor or replace the proper past-only baseline. The true signal
mechanisms differ by world; measured utility and uncertainty may support or fail
to support those mechanisms in a particular finite sample. The report never
changes application probabilities or claims real calibration.
