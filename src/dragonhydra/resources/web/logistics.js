/* Synthetic logistics only. The service owns inventory, forecasts and decisions. */
"use strict";
(function () {
  const PREFIX = "/logistics";
  const UNIVERSES = ["stable", "intermittent", "seasonal", "supplier_disruption", "perishable", "multi_location"];
  const POLICIES = ["reorder_point", "order_up_to", "base_stock", "s_S", "probabilistic_cost"];
  const ACQUISITIONS = ["none", "all", "random", "handcrafted", "learned"];
  const METHODS = ["compare_methods", "bounded_method_search", "counterfactual"];
  let generation = 0, selectedEpisode = "";
  function stop() { generation += 1; }
  const obj = x => x && typeof x === "object" && !Array.isArray(x) ? x : {};
  const list = x => Array.isArray(x) ? x : [];
  const label = x => String(x).replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
  const number = x => typeof x === "number" && Number.isFinite(x) ? x.toLocaleString(undefined, {maximumFractionDigits: 6}) : "—";
  function node(tag, attrs = {}, ...children) {
    const n = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "class") n.className = value;
      else if (key === "on") for (const [event, fn] of Object.entries(value)) n.addEventListener(event, fn);
      else if (key.startsWith("aria-")) n.setAttribute(key, String(value));
      else if (value !== undefined && value !== null && value !== false) n.setAttribute(key, value === true ? "" : String(value));
    }
    n.append(...children.flat(Infinity).filter(x => x !== undefined && x !== null && x !== false).map(x => x instanceof Node ? x : document.createTextNode(String(x))));
    return n;
  }
  function inspect(x, depth = 0) {
    if (depth > 14) return "Display depth limited";
    if (Array.isArray(x)) return x.slice(0, 500).map(v => inspect(v, depth + 1));
    if (!x || typeof x !== "object") return x;
    return Object.fromEntries(Object.entries(x).filter(([k]) => !/(?:^hidden|^latent|seed|credential|secret|token|api.?key|actual_arrival|future_demand|world_rules)/i.test(k)).map(([k, v]) => [k, inspect(v, depth + 1)]));
  }
  const hint = text => node("p", {class: "note"}, text);
  const details = (title, value) => node("details", {class: "lg-details"}, node("summary", {}, title), node("pre", {}, JSON.stringify(inspect(value), null, 2)));
  const panel = (id, title, ...children) => node("section", {class: "panel lg-panel", id: `logistics-${id}`}, node("h2", {}, title), children);
  function table(rows, columns) {
    if (!rows.length) return hint("No retained rows are available in this section.");
    return node("div", {class: "table-wrap"}, node("table", {}, node("thead", {}, node("tr", {}, columns.map(([key, title]) => node("th", {scope: "col"}, title)))), node("tbody", {}, rows.slice(0, 400).map(row => node("tr", {}, columns.map(([key, , format]) => node("td", {}, format ? format(row[key]) : row[key] === undefined || row[key] === null ? "—" : typeof row[key] === "object" ? JSON.stringify(inspect(row[key])) : String(row[key]))))))));
  }
  function scalarRows(value) { return Object.entries(obj(value)).filter(([, v]) => v === null || ["number", "string", "boolean"].includes(typeof v)).map(([key, value]) => ({key: label(key), value})); }
  async function view({request}) {
    stop(); const own = generation, alive = () => generation === own;
    const host = node("div", {class: "lg-workspace"});
    const root = node("div", {}, node("div", {class: "lg-banner", role: "note"}, node("strong", {}, "SIMULATION · SYNTHETIC COGNITIVE LOGISTICS"), hint("Fictional companies, SKUs, demand, shipments, providers and credentials. Experimental policies and relevance estimates; no live supply-chain connection or superiority claim.")), host);
    const model = {status: {}, episodes: [], models: [], experiments: [], episode: null, report: null, analysis: null, busy: false, error: "", universe: "stable", demandMode: "lost_sales", seed: 400042, days: 60, budget: 10, policy: "order_up_to", acquisition: "none", advance: 1, trainingSeed: 42, cases: 10, method: "compare_methods"};
    const get = path => request(PREFIX + path);
    const post = (path, body) => request(PREFIX + path, {method: "POST", body: JSON.stringify(body)});
    function synthetic(value) { if (value?.synthetic !== true) throw new Error("The service did not establish a synthetic-only response."); return value; }
    async function refresh() {
      const [status, episodes, models, experiments] = await Promise.all([get("/status"), get("/episodes"), get("/models"), get("/experiments")]);
      if (!alive()) return;
      model.status = synthetic(status); model.episodes = list(synthetic(episodes).items); model.models = list(synthetic(models).items); model.experiments = list(synthetic(experiments).items);
      if (!selectedEpisode && model.episodes.length) selectedEpisode = model.episodes[0].episode_id;
      model.episode = selectedEpisode ? synthetic(await get(`/episodes/${encodeURIComponent(selectedEpisode)}`)) : null;
    }
    async function command(fn) {
      if (!alive() || model.busy) return;
      model.busy = true; model.error = "";
      try { draw(); await fn(); if (alive()) await refresh(); }
      catch (error) { if (alive()) model.error = error.code ? `${error.code}: ${error.message}` : error.message; }
      finally { model.busy = false; if (alive()) draw(); }
    }
    function button(text, fn, action, primary = false) { return node("button", {type: "button", class: primary ? "primary" : "secondary", disabled: model.busy, "data-action": action, on: {click: () => command(fn)}}, text); }
    function select(name, choices, value, update) {
      const input = node("select", {id: `lg-${name}`, disabled: model.busy, on: {change: event => update(event.target.value)}}, choices.map(id => node("option", {value: id}, label(id))));
      input.value = value; return node("label", {for: `lg-${name}`}, label(name), input);
    }
    function numeric(name, value, min, max, step, update) {
      return node("label", {for: `lg-${name}`}, label(name), node("input", {id: `lg-${name}`, type: "number", value, min, max, step, disabled: model.busy, on: {change: event => { const n = Number(event.target.value); if (!Number.isFinite(n) || n < min || n > max || (step === 1 && !Number.isInteger(n))) { model.error = `Invalid ${label(name)}.`; draw(); return; } update(n); }}}));
    }
    function revision() { const r = model.episode?.snapshot?.revision; if (!Number.isInteger(r) || r < 0) throw new Error("Refresh to obtain an accepted inventory revision before submitting."); return r; }
    const path = suffix => `/episodes/${encodeURIComponent(selectedEpisode)}${suffix}`;
    function create() {
      return panel("create", "Create a virtual logistics episode", node("div", {class: "lg-form"},
        select("universe", UNIVERSES, model.universe, v => { model.universe = v; }), select("demand-mode", ["lost_sales", "backorder"], model.demandMode, v => { model.demandMode = v; }), numeric("seed", model.seed, 0, 2147483647, 1, v => { model.seed = v; }),
        numeric("duration-days", model.days, 10, 120, 1, v => { model.days = v; }), numeric("information-budget", model.budget, 0, 100, 0.1, v => { model.budget = v; })),
        button("Create logistics episode", async () => { const result = synthetic(await post("/episodes", {universe: model.universe, demand_mode: model.demandMode, seed: model.seed, days: model.days, budget: model.budget})); selectedEpisode = result.episode_id; model.analysis = null; }, "logistics-create", true),
        hint("Opening and refreshing this page only read retained public state. All world creation, decisions, time changes, training and analysis require an explicit action."));
    }
    function inventory() {
      const inv = obj(model.episode?.snapshot?.inventory), rows = [];
      for (const [location, skus] of Object.entries(obj(inv.by_location))) for (const [sku, state] of Object.entries(obj(skus))) rows.push({location, sku, ...obj(state)});
      return panel("inventory", "Inventory", hint(`Demand mode: ${model.episode?.snapshot?.demand_mode ?? "not supplied"}. Lost sales and backorders are distinct physical/accounting contracts.`), table(rows, [["location", "Location"], ["sku", "SKU"], ["on_hand", "On hand", number], ["reserved", "Reserved", number], ["atp", "Available to promise", number], ["on_order", "On order", number], ["in_transit", "In transit", number], ["backorder", "Backorder", number], ["inventory_position", "Inventory position", number], ["capacity", "Location capacity", number]]),
        hint("Capacity is a physical location limit, repeated on SKU rows for context; it is not an independent allowance per SKU."), details("Actual conservation evidence", inv.conservation ?? inv.global));
    }
    function demand() {
      const history = obj(model.episode?.snapshot?.history), forecasts = obj(model.episode?.current_forecasts), sections = [];
      for (const [location, forecast] of Object.entries(forecasts)) {
        const distribution = obj(forecast.distribution), support = list(distribution.support), probabilities = list(distribution.probabilities);
        const rows = support.map((units, i) => ({units, probability: probabilities[i]}));
        sections.push(node("div", {class: "lg-card"}, node("h3", {}, label(location)),
          table([{horizon: forecast.horizon, total_units: forecast.mean, daily_units: forecast.daily_mean, variance: forecast.variance, method: forecast.method}], [["horizon", "Forecast horizon days", number], ["total_units", "Expected total horizon units", number], ["daily_units", "Expected daily units", number], ["variance", "Predictive variance", number], ["method", "Actual method"]]),
          hint(`Uncalibrated synthetic predictive interval (90%): ${JSON.stringify(forecast.interval90 ?? null)}. Reported tail probability: ${number(distribution.tail_probability)}.`),
          rows.length ? table(rows, [["units", "Horizon demand units", number], ["probability", "Probability", number]]) : null,
          details("Forecast distribution, methods and uncertainty", forecast), table(list(history[location]), [["day", "Observed day", number], ["sales", "Observed sales", number], ["censored", "Censored"], ["available_day", "Available day", number]])));
      }
      return panel("demand", "Demand forecasts and observed sales", hint("Forecasts use the service's available evidence. Observed sales can be censored by stockouts and are not silently relabelled as total demand. Future demand is withheld."), node("div", {class: "lg-grid"}, sections.length ? sections : hint("The service has not retained location demand forecasts yet.")));
    }
    function replenishment() {
      const receipts = list(model.episode?.decisions), last = receipts.at(-1);
      const recommendations = Object.entries(obj(last?.recommendations)).map(([location, value]) => ({location, ...obj(value), expected_cost_total: obj(value?.expected_cost).total}));
      return panel("replenishment", "Replenishment decisions", node("div", {class: "lg-form"}, select("inventory-policy", POLICIES, model.policy, v => { model.policy = v; }), select("acquisition-policy", ACQUISITIONS, model.acquisition, v => { model.acquisition = v; })),
        button("Execute replenishment decision", async () => { await post(path("/decisions"), {policy: model.policy, acquisition: model.acquisition, request_id: `logistics-request-${crypto.randomUUID()}`, expected_revision: revision()}); }, "logistics-decide", true),
        hint("Each explicit click uses a fresh request identity and the displayed revision. The service executes the bounded replenishment action once; uncertain requests are not automatically retried."),
        recommendations.length ? table(recommendations, [["location", "Location"], ["policy", "Policy"], ["quantity", "Recommended order units", number], ["allocated_quantity", "Actually allocated units", number], ["inventory_position", "Inventory position", number], ["reorder_point", "Reorder point", number], ["target_level", "Target level", number], ["expected_cost_total", "Expected model cost", number], ["achieved_CSL", "Forecast cycle service", number], ["expected_fill_rate", "Forecast fill rate", number], ["service_target_feasible", "Forecast target feasible"]]) : null,
        last?.lead_forecast ? details("Actual predictive lead-time components and dependence limits", last.lead_forecast) : null,
        last ? details("Latest immutable replenishment receipt", last) : hint("No manual replenishment decision has been retained."), details("Retained decision history", receipts));
    }
    function network() {
      const net = obj(model.episode?.network), raw = net.nodes, nodes = Array.isArray(raw) ? raw : Object.entries(obj(raw)).map(([id, data]) => ({id, ...obj(data)})), edges = list(net.edges), positions = new Map();
      nodes.forEach((item, i) => positions.set(item.id, {x: 75 + (i % 3)*230, y: 55 + Math.floor(i/3)*115}));
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", `0 0 620 ${Math.max(150, Math.ceil(nodes.length/3)*115)}`); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Current public logistics network"); svg.setAttribute("class", "lg-network");
      function shape(tag, attrs, text) { const el = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value)); if (text !== undefined) el.textContent = text; svg.append(el); return el; }
      for (const edge of edges) { const a = positions.get(edge.source), b = positions.get(edge.dest); if (a && b) shape("line", {x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "lg-edge"}); }
      for (const item of nodes) { const p = positions.get(item.id); shape("circle", {cx: p.x, cy: p.y, r: 20, class: "lg-node"}); shape("text", {x: p.x, y: p.y + 38, "text-anchor": "middle"}, item.id); }
      return panel("network", "Supply network", nodes.length ? svg : hint("No public network nodes have been supplied."), table(nodes, [["id", "Node"], ["kind", "Kind"], ["capacity", "Capacity", number]]),
        table(edges, [["id", "Edge"], ["source", "From"], ["dest", "To"], ["distance", "Distance", number], ["lead_time", "Quoted lead time", number], ["unit_cost", "Unit transport cost", number], ["reliability", "Quoted reliability", number], ["capacity", "Capacity", number]]),
        details("Public shipments and promised timing", net.shipments), hint("Only public quotes, committed shipments and eligible statuses are shown. Hidden actual future arrival dates are not planning evidence."));
    }
    function relevance() {
      const s = obj(model.episode?.snapshot);
      return panel("relevance", "Information relevance and acquisition", table(list(s.candidates), [["category", "Candidate information"], ["availability", "Availability"], ["available_day", "Available day", number], ["cost", "Quoted acquisition cost", number]]),
        details("Acquired evidence available at this revision", s.acquired), details("Actual relevance estimates and acquisition actions", model.episode?.relevance ?? model.episode?.estimates ?? list(model.episode?.decisions).map(d => ({actions: d.actions, value_estimates: d.value_estimates, acquisitions: d.acquisitions}))),
        hint(`Current information budget remaining: ${number(s.budget_remaining)}. Estimates are experimental; retrospective costs and service measures do not establish a universally superior policy.`));
    }
    function analytics() {
      const report = model.report?.report ?? model.report, rows = list(report?.policy_comparison);
      return panel("analytics", "Analytics, frozen policies and research methods", table(scalarRows(model.episode?.metrics), [["key", "Metric"], ["value", "Actual value"]]),
        table(Object.entries(obj(model.episode?.metrics?.costs)).map(([category, cost]) => ({category, cost})), [["category", "Eligible cost component"], ["cost", "Actual synthetic cost", number]]),
        node("div", {class: "lg-form"}, numeric("training-seed", model.trainingSeed, 0, 2147483647, 1, v => { model.trainingSeed = v; }), numeric("training-cases", model.cases, 10, 100, 1, v => { model.cases = v; }),
          button("Train frozen acquisition policy and compare policies", async () => { model.report = await post("/training", {seed: model.trainingSeed, cases: model.cases}); }, "logistics-train", true)),
        hint("Training can take several minutes; this explicit request waits up to ten minutes. After a timeout or lost connection, refresh retained experiment results before trying again. No training request is automatically replayed."),
        details("Actual retained frozen models", model.models),
        model.experiments.length ? node("div", {class: "lg-actions"}, model.experiments.map(item => button(`Inspect experiment ${item.experiment_id}`, async () => { model.report = await get(`/experiments/${encodeURIComponent(item.experiment_id)}`); }, "logistics-experiment"))) : null,
        rows.length ? table(rows, [["inventory_policy", "Inventory policy"], ["acquisition_policy", "Information policy"], ["total_cost", "Total cost", number], ["fill_rate", "Fill rate", number], ["cycle_service_level", "Cycle service level", number], ["forecast_mae", "Forecast MAE", number], ["acquisition_cost", "Acquisition cost", number], ["computation_cost", "Computation cost", number], ["paired_cost_vs_baseline", "Paired cost vs baseline"]]) : hint("No policy comparison has been selected. The service may report gains, ties or losses."),
        report ? details("Actual training, split, comparison and limitation report", report) : null,
        model.episode ? node("div", {class: "lg-form"}, select("analysis-method", METHODS, model.method, v => { model.method = v; }), button("Run bounded logistics analysis", async () => { model.analysis = await post(path("/analyses"), {method: model.method}); }, "logistics-analyze")) : null,
        details("Actual metrics, calibration and cutoff limitations", model.episode?.metrics), details("Retained hypothesis-labelled analyses", model.analysis ?? model.episode?.analyses), hint("Method comparison, bounded search and counterfactuals are local synthetic research calculations. They cannot execute arbitrary code or silently replace a forecasting method."));
    }
    function time() {
      const s = obj(model.episode?.snapshot);
      return panel("time", "Virtual time and eligible outcomes", hint(`Accepted day ${s.day ?? "not supplied"} · decision clock ${s.decision_clock ?? "not supplied"} · remaining days ${s.days_remaining ?? "not supplied"} · revision ${s.revision ?? "not supplied"}`),
        numeric("advance-days", model.advance, 1, 30, 1, v => { model.advance = v; }), button("Advance virtual logistics time", async () => { await post(path("/advance"), {days: model.advance, expected_revision: revision()}); }, "logistics-advance"),
        hint("Advancement explicitly executes the retained inventory and acquisition policy at each new review day. Fresh episodes start with order-up-to/no-acquisition; a learned plan keeps its original frozen model until an explicit new decision replaces it. No GET advances time."), details("Eligible retrospective evaluations", model.episode?.evaluations));
    }
    function draw() {
      if (!alive()) return;
      const opened = new Set([...host.querySelectorAll("details[open]")].map(x => x.querySelector("summary")?.textContent));
      host.replaceChildren(node("div", {class: "page-heading"}, node("div", {}, node("p", {class: "eyebrow"}, "GENESIS 6.2 · VIRTUAL OPERATIONS"), node("h1", {}, "Cognitive logistics"), hint("Observe inventory. Forecast demand. Pay for useful evidence. Evaluate replenishment after outcomes arrive.")), button("Refresh logistics public state", async () => {}, "logistics-refresh")));
      if (model.error) host.append(node("div", {class: "lg-error", role: "alert"}, model.error));
      if (model.busy) host.append(node("p", {role: "status"}, "Waiting for the requested virtual operation…"));
      host.append(details("Actual cognitive-logistics service status", model.status), create());
      if (model.episodes.length) host.append(select("episode", model.episodes.map(e => e.episode_id), selectedEpisode, value => { selectedEpisode = value; model.episode = null; model.analysis = null; command(async () => {}); }));
      if (model.episode) host.append(node("nav", {class: "lg-section-nav", "aria-label": "Logistics sections"}, ["inventory", "demand", "replenishment", "network", "relevance", "analytics", "time"].map(id => node("a", {href: `#logistics-${id}`, on: {click: event => { event.preventDefault(); document.getElementById(`logistics-${id}`)?.scrollIntoView({behavior: "smooth", block: "start"}); }}}, label(id)))), inventory(), demand(), replenishment(), network(), relevance(), analytics(), time());
      else host.append(hint("Create a virtual episode explicitly to open the seven logistics sections."), analytics());
      for (const item of host.querySelectorAll("details")) if (opened.has(item.querySelector("summary")?.textContent)) item.open = true;
    }
    try { await refresh(); draw(); } catch (error) { model.error = error.message; draw(); }
    return root;
  }
  window.DragonLogistics = Object.freeze({view, stop});
}());
