# DRAGONHYDRA local research laboratory

The integrated `0.4.0-alpha.1` prerelease adds an authenticated server, reusable
dashboard, Windows desktop client, Joomla administration and optional Android
client connection. It remains experimental. The complete workstation installer,
permanent VPS hosting, credentialed live feeds and local LLM are not included.

Use the versioned release's `INSTALLATION.md` and artifact manifest to choose a
download. The Python wheel requires Python 3.14; install its `server` extra for
the HTTP service. `dragonhydra-server --port 18743 --state ./product-state
--init-bridge` starts the optional server with bundled documented sample inputs.
`dragonhydra-samples --directory ./samples` copies explicit CLI examples without
requiring a development checkout. Pair a client using the generated local token;
keep that token and the Joomla bridge secret private. Android localhost refers
to the phone; remote connections need a configured trusted HTTPS endpoint.

The source-locked release procedure is documented in
[packaging/release/SOURCE-LOCK.md](packaging/release/SOURCE-LOCK.md). The older
commands below describe the preserved engineering CLI and development checkout.

Run from PowerShell 7 in this directory using Python 3.14:

```powershell
py -3.14 -B dragon.py archive
py -3.14 -B dragon.py results
py -3.14 -B dragon.py forecast
py -3.14 -B dragon.py demo
py -3.14 -B dragon.py score
py -3.14 -B dragon.py train
py -3.14 -B dragon.py predict
py -3.14 -B dragon.py evaluate
py -3.14 -B dragon.py calibrate
py -3.14 -B dragon.py memory
py -3.14 -B dragon.py intelligence
py -3.14 -B dragon.py research
```

Use `--format json` on a report command for source records, clock fields, evidence
IDs, hashes, transformations and configuration. `archive` accepts `--event` for
an event identifier from `dragonhydra.football_data.list_events`; without one it
selects the first fixture in the downloaded file. `forecast --event-date YYYY-MM-DD`
selects an eligible future OpenFootball fixture on that date.

The `archive` command imports one row of the downloaded Football-Data.co.uk CSV
into the append-only local SQLite store. `B365` and `PS` are the source's column
labels, not independently verified provider mappings. The source's pre-closing
and closing-labelled values are reported as labelled differences; their individual
quote times and synchronization are unknown, so they do not establish velocity or
executable contemporaneous opportunities. Data attribution and usage terms:
<https://www.football-data.co.uk/>, <https://www.football-data.co.uk/notes.txt>,
<https://www.football-data.co.uk/contact.php>. The project records the exact file,
source URL, capture clock and SHA-256 in `data/raw`.

The same command calculates an illustrative present-time scenario from the
archived B365 home price. The default probability is 0.55; pass a different
assumption with `--probability 0.60`. `--fraction`, `--cap`, `--bankroll`,
`--stake-fraction`, `--trials`, `--steps` and `--seed` configure the scenario.
The report records whether the probability was the built-in example or supplied
by the caller. It is not represented as a prediction made before the match. The
simulation uses `--stake-fraction` independently of the calculated Kelly value.

`results` imports the OpenFootball 2025/26 Premier League file; `forecast` imports
the 2026/27 file and computes a smoothed descriptive frequency prior for a future
fixture from eligible earlier same-source, same-competition results. The prior is
an ephemeral calculation at actual run time, not a persisted historical forecast.
OpenFootball data is CC0: <https://github.com/openfootball/football.json>.

`demo` is a labelled synthetic clock example with six snapshots from two provider
identities. It computes line changes, raw implied probabilities, overround,
provider differences and a conditional expected-return, fractional Kelly and IID
bankroll scenario from a synthetic probability assumption. `score` evaluates
explicitly labelled synthetic historical forecasts with Brier and log loss.

The cognitive commands use the retained OpenFootball records. The forecast runs
smoothed outcome-frequency, team-shrunk Poisson goals, recency-weighted frequency
and Elo-style models. It reports the individual distributions, an ensemble,
expected goals, likely scorelines, over/under 2.5 and both-teams-to-score estimates.
Elo uses the frequency model's draw rate, so the models are not independent. When
there is no eligible comparable operational evaluation, the ensemble uses equal
weights. After at least 20 genuinely scored predictions per model for the same
fixture cohort, retained cutoff-eligible Brier evidence can inform weights;
corrected outcomes invalidate stale evaluation evidence.

`predict` and `intelligence` append actual model and prediction records. `memory`
shows them; `memory --outcome-evidence-id ID` attaches a later eligible source
result to an earlier prediction. `evaluate` scores such recorded forecasts and
also reports a chronological present-knowledge holdout on the retained 2025/26
data; the latter is a diagnostic computed now, not a historical strict replay.
`calibrate` shows its binned forecast and outcome frequencies. `research` saves
bounded tasks for measured gaps such as missing mapped quotes, stale results
coverage and unscored operational forecasts. No neural model is claimed.

## Local inputs

Import a user-supplied JSON or CSV snapshot and report an event:

```powershell
py -3.14 -B dragon.py import --file examples\synthetic-totals.json --db runtime\market-demo.sqlite3 --synthetic-clock
py -3.14 -B dragon.py report --db runtime\market-demo.sqlite3 --event synthetic-totals-001 --cutoff 2026-01-01T12:10:00Z --synthetic-clock
```

JSON files contain a `snapshots` array; CSV files use one row per outcome. Each
snapshot identifies source, provider, acquisition, event, participants,
competition, market, period, status, settlement and original odds text/format.
See `examples/synthetic-market.json` and `examples/synthetic-totals.json` for the
shape. Operational imports record actual local receipt and commit acknowledgment;
source-provided historical times cannot backdate system knowledge. The separate
receipt transaction's precise visibility boundary has not yet been established,
so operational reports identify themselves as `OPERATIONAL_AS_OF_RECEIPT` rather
than claiming a fully verified retrospective replay.

A local estimate file can be supplied with `report --estimate path.json`.
Operational imports treat it as a user-supplied assumption at actual receipt time;
synthetic replay requires `--synthetic-clock` and labelled synthetic evidence.
`--fraction`, `--cap`, `--bankroll`, `--trials`, `--steps` and `--seed` configure
the conditional scenario. The outputs are calculations under the stated probability
and binary-settlement assumptions; pricing and model quality are not verified by
the formulas.

For bounded local updates, poll a JSON or CSV snapshot already inside the project:

```powershell
py -3.14 -B dragon.py watch --file examples\synthetic-market.json --db runtime\watch-demo.sqlite3 --iterations 2 --interval 0
```

The watcher reports each poll as it happens, skips unchanged bytes and imports
changed acquisitions with actual receipt clocks. It stops at the requested
iteration limit; reused acquisition IDs with different content are quarantined.

## Tests

```powershell
$env:PYTHONPATH = 'src'
py -3.14 -B -m unittest discover -s tests -q
```

Tests use only project-owned files and databases under `runtime`; downloaded raw
data and receipts remain under `data/raw`.
