/* Virtual-only future relevance. Decisions, predictions and costs come from the API. */
"use strict";
(function () {
  const PREFIX = "/future";
  const UNIVERSES = ["constant", "card_sensitive", "tempo_signal", "noisy_signal", "clock_sensitive", "possession_inverse", "late_card_interaction"];
  const TARGETS = ["GOAL_OCCURRENCE", "FULL_TIME_RESULT", "NEXT_GOAL_SIDE", "REMAINING_GOALS"];
  const HORIZONS = ["1", "5", "10", "30", "FULL_TIME"];
  const POLICIES = ["acquire_all", "acquire_none", "random", "handcrafted", "learned"];
  let generation = 0;
  let selectedEpisode = "";
  function stop() { generation += 1; }
  function obj(x) { return x && typeof x === "object" && !Array.isArray(x) ? x : {}; }
  function list(x) { return Array.isArray(x) ? x : []; }
  function label(x) { return String(x).replaceAll("_", " ").toLowerCase().replace(/\b\w/g, c => c.toUpperCase()); }
  function el(tag, attrs = {}, ...children) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k === "on") for (const [event, fn] of Object.entries(v)) n.addEventListener(event, fn);
      else if (k.startsWith("aria-")) n.setAttribute(k, String(v));
      else if (v !== null && v !== undefined && v !== false) n.setAttribute(k, v === true ? "" : String(v));
    }
    n.append(...children.flat(Infinity).filter(x => x !== null && x !== undefined && x !== false).map(x => x instanceof Node ? x : document.createTextNode(String(x))));
    return n;
  }
  function number(x) { return typeof x === "number" && Number.isFinite(x) ? x.toLocaleString(undefined, {maximumFractionDigits: 7}) : "Not supplied"; }
  function pct(x) { return typeof x === "number" && Number.isFinite(x) ? `${(100*x).toFixed(2)}%` : "Not supplied"; }
  function hint(s) { return el("p", {class: "note"}, s); }
  function panel(title, ...children) { return el("section", {class: "panel fu-panel"}, el("h2", {}, title), children); }
  function inspect(value, depth = 0) {
    if (depth > 14) return "Display depth limited";
    if (Array.isArray(value)) return value.slice(0, 500).map(x => inspect(x, depth + 1));
    if (!value || typeof value !== "object") return value;
    return Object.fromEntries(Object.entries(value).filter(([key]) => !/(?:^hidden|^latent|seed|secret|credential|token|api.?key|family.?rules)/i.test(key)).map(([key, val]) => [key, inspect(val, depth + 1)]));
  }
  function details(title, value) { return el("details", {class: "fu-details"}, el("summary", {}, title), el("pre", {}, JSON.stringify(inspect(value), null, 2))); }
  function table(rows, columns) {
    if (!rows.length) return hint("No retained rows are available for this section.");
    return el("div", {class: "table-wrap"}, el("table", {}, el("thead", {}, el("tr", {}, columns.map(([key, name]) => el("th", {scope: "col"}, name)))), el("tbody", {}, rows.slice(0, 400).map(row => el("tr", {}, columns.map(([key, , formatter]) => el("td", {}, formatter ? formatter(row[key]) : row[key] === null || row[key] === undefined ? "Not supplied" : typeof row[key] === "object" ? JSON.stringify(inspect(row[key])) : String(row[key]))))))));
  }
  function distributions(forecast, title) {
    const f = obj(forecast), probabilities = f.probabilities;
    const rows = Array.isArray(probabilities) ? probabilities.map((p, index) => typeof p === "object" ? p : {outcome: index === 13 ? "13PLUS" : String(index), probability: p}) : Object.entries(obj(probabilities)).map(([outcome, probability]) => ({outcome, probability}));
    return panel(title, hint(`${f.target ?? f.prediction_target ?? "Target not supplied"} · horizon ${f.horizon ?? "not supplied"} · model ${f.model_id ?? "not supplied"}`),
      rows.length ? table(rows, [["outcome", "Outcome"], ["probability", "Probability", pct]]) : hint("The service has not supplied an eligible forecast distribution."), details("Forecast identity and cutoff", f));
  }
  async function view({request}) {
    stop(); const ownGeneration = generation;
    const host = el("div", {class: "fu-workspace"});
    const root = el("div", {}, el("div", {class: "fu-banner", role: "note"}, el("strong", {}, "SIMULATION · SYNTHETIC FUTURE RELEVANCE ONLY"), hint("Fictional evidence, outcomes, providers and credentials. Experimental information estimates are not calibrated real-world value. No external API calls.")), host);
    const model = {status: {}, episodes: [], models: [], experiments: [], episode: null, report: null, frozen: null, busy: false, error: "", universe: UNIVERSES[0], target: TARGETS[0], horizon: "10", seed: 400042, minute: 60, budget: 0.12, policy: "acquire_none", advance: 10, trainingSeed: 42, trainingCases: 30};
    const alive = () => generation === ownGeneration;
    const get = path => request(PREFIX + path);
    const post = (path, body) => request(PREFIX + path, {method: "POST", body: JSON.stringify(body)});
    function synthetic(value) { if (value?.synthetic !== true) throw new Error("The service did not establish a synthetic-only response."); return value; }
    async function refresh() {
      const [status, episodes, models, experiments] = await Promise.all([get("/status"), get("/episodes"), get("/models"), get("/experiments")]);
      if (!alive()) return;
      model.status = synthetic(status); model.episodes = list(synthetic(episodes).items); model.models = list(synthetic(models).items); model.experiments = list(synthetic(experiments).items);
      if (!selectedEpisode && model.episodes.length) selectedEpisode = model.episodes[0].episode_id;
      if (selectedEpisode) model.episode = synthetic(await get(`/episodes/${encodeURIComponent(selectedEpisode)}`));
      else model.episode = null;
    }
    async function command(fn) {
      if (model.busy || !alive()) return;
      model.busy = true; model.error = "";
      try { draw(); await fn(); if (alive()) await refresh(); }
      catch (error) { if (alive()) model.error = error.code ? `${error.code}: ${error.message}` : error.message; }
      finally { model.busy = false; if (alive()) draw(); }
    }
    function button(text, fn, id, primary = false) { return el("button", {type: "button", class: primary ? "primary" : "secondary", disabled: model.busy, "data-action": id, on: {click: () => command(fn)}}, text); }
    function select(name, choices, value, update) {
      const input = el("select", {id: `future-${name}`, disabled: model.busy, on: {change: event => update(event.target.value)}}, choices.map(([id, text]) => el("option", {value: id}, text)));
      input.value = value;
      return el("label", {for: `future-${name}`}, label(name), input);
    }
    function numeric(name, value, minimum, maximum, step, update) {
      return el("label", {for: `future-${name}`}, label(name), el("input", {type: "number", id: `future-${name}`, value, min: minimum, max: maximum, step, disabled: model.busy, on: {change: event => { const n = Number(event.target.value); if (!Number.isFinite(n) || n < minimum || n > maximum || (step === 1 && !Number.isInteger(n))) { model.error = `Invalid ${label(name)}.`; draw(); return; } update(n); }}}));
    }
    function revision() {
      const value = model.episode?.snapshot?.revision;
      if (!Number.isInteger(value) || value < 0) throw new Error("A current accepted snapshot revision is required; refresh before submitting.");
      return value;
    }
    function creation() {
      const horizons = model.target === "FULL_TIME_RESULT" ? ["FULL_TIME"] : HORIZONS;
      if (!horizons.includes(model.horizon)) model.horizon = horizons[0];
      return panel("Create an isolated virtual episode", el("div", {class: "fu-form"},
        select("universe", UNIVERSES.map(id => [id, label(id)]), model.universe, value => { model.universe = value; }),
        select("target", TARGETS.map(id => [id, label(id)]), model.target, value => { model.target = value; draw(); }),
        select("horizon", horizons.map(id => [id, id === "FULL_TIME" ? "Full time" : `${id} playing minutes`]), model.horizon, value => { model.horizon = value; }),
        numeric("seed", model.seed, 0, 2147483647, 1, value => { model.seed = value; }),
        numeric("minute", model.minute, 45, 89, 1, value => { model.minute = value; }),
        numeric("budget", model.budget, 0, 100, 0.01, value => { model.budget = value; })),
        button("Create virtual episode", async () => { const created = synthetic(await post("/episodes", {universe: model.universe, seed: model.seed, target: model.target, horizon: model.horizon, minute: model.minute, budget: model.budget})); selectedEpisode = created.episode_id; }, "future-create", true),
        hint("Opening this view only reads retained public state. Creation, information decisions, time advancement and training are explicit actions."));
    }
    function evidence() {
      const e = model.episode, s = obj(e?.snapshot);
      const known = s.acquired ?? s.known ?? s.known_categories ?? s.known_evidence ?? [];
      const candidates = s.candidates ?? s.candidate_categories ?? [];
      return panel("Known evidence and candidate information", hint("Only the service's public decision-time snapshot is shown. Hidden rules, seeds and future labels are not available to the decision view."),
        details("Known categories at this revision", known), table(list(candidates), [["category", "Information category"], ["availability", "Availability"], ["cost", "Acquisition cost", number], ["computation_cost", "Computation cost", number], ["available_at", "Available at"], ["freshness_seconds", "Freshness seconds", number]]),
        table(list(e?.estimates), [["category", "Category"], ["estimated_value", "Estimated value", number], ["estimated_cost", "Estimated cost", number], ["state", "Estimate status"]]),
        hint("Estimates are experimental, not observed utility. Realized information value is evaluated later against an eligible virtual outcome."), details("Public snapshot and provenance", s));
    }
    function decisions() {
      const e = model.episode, items = list(e?.decisions), last = items.at(-1), d = obj(last?.decision ?? last);
      return panel("Acquire information and execute a revision-bound decision",
        select("policy", POLICIES.map(id => [id, label(id)]), model.policy, value => { model.policy = value; }),
        button("Execute information decision", async () => {
          const expected_revision = revision();
          const request_id = `future-request-${crypto.randomUUID()}`;
          await post(`/episodes/${encodeURIComponent(selectedEpisode)}/decisions`, {policy: model.policy, request_id, expected_revision});
        }, "future-decide", true), hint("Each click has a new request identity and the displayed accepted revision. Failed or uncertain requests are not automatically replayed."),
        last ? el("div", {class: "fu-grid"}, distributions(d.before, "Before acquisition"), distributions(d.after, "After acquisition")) : hint("No information decision has been retained for this episode."),
        last ? table([d], [["acquisition_cost", "Acquisition cost", number], ["computation_units", "Computation units", number], ["computation_cost", "Computation cost", number], ["budget_remaining", "Budget remaining", number]]) : null,
        details("Immutable decisions, actual actions and estimates", items));
    }
    function outcomes() {
      const evaluations = list(model.episode?.evaluations);
      const measured = evaluations.flatMap(e => list(e.deferred_future_relevance).map(row => ({...row, decision_id: e.decision_id})));
      return panel("Advance virtual time and evaluate eligible outcomes", numeric("advance-minutes", model.advance, 1, 50, 1, value => { model.advance = value; }),
        button("Advance virtual time", async () => { await post(`/episodes/${encodeURIComponent(selectedEpisode)}/advance`, {minutes: model.advance, expected_revision: revision()}); }, "future-advance"),
        measured.length ? table(measured, [["category", "Delayed information"], ["predicted_at", "Predicted at"], ["acquired_at", "Acquired at"], ["predicted_relevance", "Predicted Brier improvement", number], ["observed_local_improvement", "Later measured improvement", number]]) : null,
        evaluations.length ? details("Eligible retrospective paired evaluations", evaluations) : hint("No retrospective evaluation is available yet. Future outcomes are withheld until the service's eligibility cutoff."),
        hint("Proper-score changes, virtual acquisition and computation costs are separate quantities. An explicit time advance may resume a retained deferred policy using its original frozen model. Net usefulness can be negative."));
    }
    function training() {
      const report = model.report?.report ?? model.report;
      const comparison = list(report?.policy_comparison).map(row => ({...row,
        paired_brier_improvement: row.paired_vs_acquire_none?.brier_improvement,
        paired_net_utility_improvement: row.paired_vs_acquire_none?.net_utility_improvement}));
      const comparisonColumns = [["policy", "Policy"], ["episode_count", "Episodes", number],
        ["brier_score", "Brier score", number], ["log_loss", "Log loss", number], ["ece", "ECE", number],
        ["mean_acquisition_cost", "Mean acquisition cost", number], ["mean_computation_cost", "Mean computation cost", number],
        ["mean_total_cost", "Mean total cost", number], ["mean_cost_adjusted_utility", "Mean cost-adjusted utility", number],
        ["paired_brier_improvement", "Paired Brier improvement vs none"],
        ["paired_net_utility_improvement", "Paired net utility improvement vs none"]].filter(([key]) => comparison.some(row => row[key] !== undefined));
      return panel("Train a frozen policy and inspect held-out evidence", el("div", {class: "fu-form"},
        numeric("training-seed", model.trainingSeed, 0, 2147483647, 1, value => { model.trainingSeed = value; }),
        numeric("training-cases-per-family", model.trainingCases, 10, 1000, 1, value => { model.trainingCases = value; }),
        button("Train frozen policy and evaluate held-out report", async () => { model.report = await post("/training", {seed: model.trainingSeed, cases_per_family: model.trainingCases}); }, "future-train", true)),
        hint("Training is an explicit synthetic experiment. Held-out outcomes do not automatically update a frozen policy. Five policies are compared; measured gains are research results, not a real-world accuracy claim."),
        model.models.length ? details("Retained frozen models and identities", model.models) : hint("No frozen model has been retained. The service determines learned-policy availability."),
        model.models.length ? el("div", {class: "fu-actions"}, model.models.map(item => button(`Inspect frozen model ${item.model_id}`, async () => { model.frozen = await get(`/models/${encodeURIComponent(item.model_id)}`); }, "future-model"))) : null,
        model.frozen ? details("Selected frozen model and training provenance", model.frozen) : null,
        model.experiments.length ? el("div", {class: "fu-actions"}, model.experiments.map(item => button(`Inspect report ${item.experiment_id}`, async () => { model.report = await get(`/experiments/${encodeURIComponent(item.experiment_id)}`); }, "future-report"))) : null,
        comparison.length ? table(comparison, comparisonColumns) : null,
        report ? details("Actual training, validation, held-out report and limitations", report) : hint("No experiment report has been selected in this view."));
    }
    function draw() {
      if (!alive()) return;
      const focus = host.contains(document.activeElement) ? document.activeElement.id : null;
      host.replaceChildren(el("div", {class: "page-heading"}, el("div", {}, el("p", {class: "eyebrow"}, "GENESIS 6.1 · VIRTUAL RESEARCH"), el("h1", {}, "Future relevance research"), hint("Decide what to observe before it arrives. Compare usefulness after the outcome becomes eligible.")), button("Refresh public state", async () => {}, "future-refresh")));
      if (model.error) host.append(el("div", {class: "fu-error", role: "alert"}, model.error));
      if (model.busy) host.append(el("p", {role: "status"}, "Waiting for the requested virtual operation…"));
      host.append(details("Actual future-relevance service status", model.status), creation());
      if (model.episodes.length) host.append(select("episode", model.episodes.map(item => [item.episode_id, item.episode_id]), selectedEpisode, value => { selectedEpisode = value; command(async () => {}); }));
      if (model.episode) {
        host.append(panel("Accepted decision-time state", hint(`Episode ${model.episode.episode_id} · revision ${model.episode.snapshot?.revision ?? "not supplied"} · virtual minute ${model.episode.snapshot?.now_minute ?? "not supplied"}`), details("Declared virtual episode metadata", model.episode.universe), details("Observed synthetic match state", model.episode.snapshot?.observed_state)),
          distributions(model.episode.current_forecast, "Current target forecast"), evidence(), decisions(), outcomes());
      } else host.append(hint("No virtual episode is selected. Create one explicitly to inspect a decision-time snapshot."));
      host.append(training());
      if (focus) document.getElementById(focus)?.focus({preventScroll: true});
    }
    try { await refresh(); draw(); }
    catch (error) { model.error = error.message; draw(); }
    return root;
  }
  window.DragonFuture = Object.freeze({view, stop});
}());
