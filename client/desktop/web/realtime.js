/* Synthetic research workspace. The server owns replay, models and investigation. */
"use strict";
(function () {
  const PREFIX = "/realtime";
  const MODES = new Set(["DEMONSTRATION", "REPLAY"]);
  const UNIVERSES = ["constant", "card_sensitive", "tempo_signal", "noisy_signal", "clock_sensitive"];
  const HORIZONS = [["1", "1 min"], ["5", "5 min"], ["10", "10 min"], ["30", "30 min"], ["FULL_TIME", "Full time"]];
  const OUTCOMES = [["home", "Home", "rt-home"], ["draw", "Draw", "rt-draw"], ["away", "Away", "rt-away"]];
  let generation = 0;
  let timer = null;
  let selectedMatch = "";
  function stop() { generation += 1; clearTimeout(timer); timer = null; }
  function node(tag, attrs = {}, ...children) {
    const item = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "class") item.className = value;
      else if (key === "on") for (const [event, handler] of Object.entries(value)) item.addEventListener(event, handler);
      else if (key.startsWith("aria-") && value !== null && value !== undefined) item.setAttribute(key, String(value));
      else if (value !== null && value !== undefined && value !== false) item.setAttribute(key, value === true ? "" : String(value));
    }
    for (const child of children.flat(Infinity)) if (child !== null && child !== undefined && child !== false) item.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return item;
  }
  const obj = value => value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const list = value => Array.isArray(value) ? value : [];
  const label = value => String(value).replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  const number = value => typeof value === "number" && Number.isFinite(value);
  const probability = value => number(value) && value >= 0 && value <= 1 ? value : null;
  const percent = value => probability(value) === null ? "Not supplied" : `${(value * 100).toFixed(1)}%`;
  const points = value => number(value) && Math.abs(value) <= 1 ? `${value > 0 ? "+" : ""}${(value * 100).toFixed(2)} pp` : "Not supplied";
  const score = value => number(obj(value).home) && number(obj(value).away) ? `${value.home} – ${value.away}` : "Not supplied";
  function timestamp(value) {
    if (typeof value !== "string") return "Not supplied";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? value : date.toISOString().replace("T", " ");
  }
  function inspectValue(value, depth = 0) {
    if (depth > 8) return "[depth limit]";
    if (Array.isArray(value)) return value.slice(0, 200).map(v => inspectValue(v, depth + 1));
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).slice(0, 100).map(([key, item]) => [key, /secret|credential|authorization|api.?key|token/i.test(key) ? "[redacted]" : inspectValue(item, depth + 1)]));
    return value;
  }
  function details(title, value, open = false) {
    const text = JSON.stringify(inspectValue(value), null, 2) ?? "Not supplied";
    return node("details", {class: "rt-details", open}, node("summary", {}, title), node("pre", {}, text.slice(0, 24000) + (text.length > 24000 ? "\n[display limit]" : "")));
  }
  const panel = (title, ...children) => node("section", {class: "panel rt-panel"}, node("h2", {}, title), ...children);
  const hint = text => node("p", {class: "rt-hint"}, text);
  const fact = (title, value) => node("div", {class: "rt-fact"}, node("span", {}, title), node("strong", {}, value === true ? "Yes" : value === false ? "No" : value ?? "Not supplied"));
  function synthetic(snapshot) {
    if (snapshot?.synthetic !== true || !MODES.has(snapshot.source_mode ?? snapshot.state?.source_mode)) throw new Error("Research accepts only explicitly synthetic DEMONSTRATION or REPLAY snapshots.");
    return snapshot;
  }
  function distribution(title, values) {
    const entries = Array.isArray(values) ? values.map(v => [number(obj(v).home) && number(obj(v).away) ? `${v.home} – ${v.away}` : obj(v).score ?? obj(v).goals ?? obj(v).outcome ?? "Outcome", obj(v).probability]) : Object.entries(obj(values));
    const valid = entries.filter(([, value]) => probability(value) !== null).sort((a, b) => b[1] - a[1]);
    const section = node("div", {class: "rt-distribution"}, node("h3", {}, title));
    if (!valid.length) { section.append(hint("Distribution not supplied by this forecast.")); return section; }
    for (const [name, value] of valid.slice(0, 12)) {
      const meter = node("progress", {max: 1, value, "aria-label": `${label(Array.isArray(name) ? name.join("–") : name)}: ${percent(value)}`});
      section.append(node("div", {class: "rt-probability"}, node("span", {}, label(Array.isArray(name) ? name.join("–") : name)), meter, node("strong", {}, percent(value))));
    }
    if (valid.length > 12) section.append(hint(`Showing the 12 highest probabilities of ${valid.length} supplied outcomes.`));
    return section;
  }
  function fullTime(forecast) {
    const values = obj(forecast.full_time_result);
    const box = node("div", {class: "rt-result-grid"});
    for (const [key, title, cls] of OUTCOMES) box.append(node("div", {class: `rt-result ${cls}`}, node("span", {}, title), node("strong", {}, percent(values[key]))));
    return box;
  }
  function timelineChart(items, selected, choose) {
    const namespace = "http://www.w3.org/2000/svg";
    function svg(tag, attrs) { const n = document.createElementNS(namespace, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v)); return n; }
    const graph = svg("svg", {viewBox: "0 0 760 230", role: "img", "aria-label": "Full-time home, draw and away probability timeline by forecast revision", class: "rt-chart"});
    const title = svg("title", {}); title.textContent = "Fetched forecast revisions: full-time probabilities"; graph.append(title);
    const x = index => 45 + index * 680 / Math.max(1, items.length - 1);
    const y = value => 190 - value * 165;
    for (const value of [0, 0.5, 1]) {
      graph.append(svg("line", {x1: 45, x2: 725, y1: y(value), y2: y(value), class: "rt-gridline"}));
      const text = svg("text", {x: 35, y: y(value) + 4, "text-anchor": "end"}); text.textContent = `${value * 100}%`; graph.append(text);
    }
    const chosen = items.findIndex(item => item.revision === selected);
    if (chosen >= 0) graph.append(svg("line", {x1: x(chosen), x2: x(chosen), y1: 20, y2: 195, class: "rt-selected-line"}));
    for (const [key, titleText, cls] of OUTCOMES) {
      let path = "", previous = false;
      items.forEach((item, index) => {
        const value = probability(obj(item.forecast?.full_time_result)[key]);
        if (value === null) { previous = false; return; }
        path += `${previous ? "L" : "M"}${x(index).toFixed(2)},${y(value).toFixed(2)} `; previous = true;
      });
      graph.append(svg("path", {d: path, class: `rt-prob-line ${cls}`}));
      items.forEach((item, index) => {
        const value = probability(obj(item.forecast?.full_time_result)[key]); if (value === null) return;
        const mark = svg("circle", {cx: x(index), cy: y(value), r: item.revision === selected ? 5 : 3.5, class: `rt-prob-point ${cls}`, tabindex: 0, role: "button", "aria-label": `Revision ${item.revision}, ${titleText} ${percent(value)}`});
        mark.addEventListener("click", () => choose(item.revision));
        mark.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); choose(item.revision); } }); graph.append(mark);
      });
    }
    if (items.length) for (const index of [...new Set([0, items.length - 1])]) { const t = svg("text", {x: x(index), y: 215, "text-anchor": "middle"}); t.textContent = `Revision ${items[index].revision}`; graph.append(t); }
    return graph;
  }
  async function view({request}) {
    stop(); const own = generation;
    let refreshVersion = 0;
    const alive = () => own === generation && location.hash.split("/")[0] === "#research";
    const get = path => request(PREFIX + path);
    const post = (path, body) => request(PREFIX + path, {method: "POST", body: JSON.stringify(body)});
    const model = {status: {}, matches: [], snapshot: null, timeline: [], events: [], revision: null, follow: true, horizon: "FULL_TIME", inspection: "analysis", analysis: null, evaluation: null, relevance: null, universe: "constant", seed: 42, branchName: "", speed: null, steps: 1, busy: false, error: ""};
    const root = node("div", {class: "rt-root", "data-testid": "research-workspace"});
    root.append(node("div", {class: "rt-simulation", role: "note"}, node("strong", {}, "SIMULATION · SYNTHETIC DATA ONLY"), node("span", {}, "Fictional matches, events, odds and outcomes. Virtual credentials only. No external provider or OpenAI calls.")));
    const host = node("div", {}, hint("Loading the synthetic research API…")); root.append(host);
    function actionButton(text, handler, cls = "secondary", attrs = {}) { return node("button", {type: "button", class: cls, disabled: model.busy, on: {click: handler}, ...attrs}, text); }
    function running() { return String(model.snapshot?.replay?.status).toUpperCase() === "PLAYING"; }
    function queuePoll() {
      clearTimeout(timer); timer = null;
      if (alive() && running()) timer = setTimeout(async () => { try { await refresh(); } catch (error) { model.error = error.message; draw(); } }, 1000);
    }
    async function loadList() {
      const result = await get("/matches");
      model.matches = list(result.items).filter(item => item.synthetic === true && MODES.has(item.source_mode ?? item.state?.source_mode));
      if (!model.matches.some(item => item.match_id === selectedMatch)) selectedMatch = model.matches[0]?.match_id ?? "";
    }
    async function refresh() {
      if (!selectedMatch || !alive()) return;
      const id = selectedMatch;
      const version = ++refreshVersion;
      const [snapshot, timeline, events, status] = await Promise.all([get(`/matches/${encodeURIComponent(id)}`), get(`/matches/${encodeURIComponent(id)}/timeline?limit=200`), get(`/matches/${encodeURIComponent(id)}/events`), get("/status")]);
      if (!alive() || id !== selectedMatch || version !== refreshVersion) return;
      model.snapshot = synthetic(snapshot); model.timeline = list(timeline.items); model.events = list(events.items); model.status = status;
      if (model.follow || !model.timeline.some(item => item.revision === model.revision)) model.revision = snapshot.current_forecast?.revision ?? model.timeline.at(-1)?.revision ?? null;
      model.error = ""; draw(); queuePoll();
    }
    async function command(operation) {
      if (model.busy) return;
      model.busy = true; model.error = ""; refreshVersion += 1; clearTimeout(timer); draw();
      try { await operation(); if (alive()) { await loadList(); await refresh(); } }
      catch (error) { if (alive()) model.error = error.message; }
      finally { if (alive()) { model.busy = false; draw(); queuePoll(); } }
    }
    function chosen() { return model.timeline.find(item => item.revision === model.revision) ?? model.snapshot?.current_forecast ?? null; }
    function choose(revision) { model.revision = revision; model.follow = false; model.analysis = null; draw(); }
    function selectedSeed() {
      const value = Number(model.seed);
      if (!Number.isInteger(value) || value < 0 || value > 2147483647) throw new Error("Use an integer seed from 0–2147483647.");
      return value;
    }
    function scenarioControls() {
      const universe = node("select", {id: "research-universe", disabled: model.busy, "aria-label": "Synthetic universe for a new scenario or branch"}, UNIVERSES.map(value => node("option", {value}, label(value))));
      universe.value = model.universe; universe.addEventListener("change", () => { model.universe = universe.value; });
      const seed = node("input", {id: "research-seed", disabled: model.busy, type: "number", step: 1, min: 0, max: 2147483647, value: model.seed, "aria-label": "Synthetic universe seed"});
      seed.addEventListener("input", () => { model.seed = seed.value; });
      return node("div", {class: "rt-world-controls"}, node("label", {for: "research-universe"}, "Universe for new scenario / branch", universe), node("label", {for: "research-seed"}, "Seed", seed), hint("Virtual time and seeded worlds make fictional futures reproducible. Creating a branch keeps its parent audit trail."));
    }
    async function fork(record, rewind) {
      const result = await post(`/matches/${encodeURIComponent(selectedMatch)}/branches`, {at_revision: record.state_revision, branch_name: model.branchName.trim() || `${rewind ? "Rewind" : "Fork"} at state ${record.state_revision}`, seed: selectedSeed(), universe: model.universe});
      selectedMatch = result.match_id; model.follow = true; model.analysis = null; model.speed = null;
    }
    function componentStatus() {
      const cards = node("div", {class: "rt-components"});
      for (const [id, component] of Object.entries(obj(model.status.components))) {
        const raw = obj(component), colour = ["GREEN", "AMBER", "RED", "NEUTRAL"].includes(raw.state) ? raw.state.toLowerCase() : "neutral";
        cards.append(node("div", {class: `rt-component rt-${colour}`}, node("strong", {}, label(id)), node("span", {}, raw.state ?? "NEUTRAL"), node("p", {}, raw.reason ?? raw.reason_code ?? "No observation supplied")));
      }
      cards.append(node("div", {class: "rt-component rt-neutral"}, node("strong", {}, "External OpenAI"), node("span", {}, "UNCONFIGURED"), node("p", {}, "This workspace uses only the local virtual transport. No external key or model request is used.")));
      return cards;
    }
    function controls(snapshot) {
      const select = node("select", {id: "research-match", disabled: model.busy, "aria-label": "Synthetic match"});
      for (const item of model.matches) { const teams = obj(item.state?.teams ?? item.teams); select.append(node("option", {value: item.match_id}, teams.home && teams.away ? `${teams.home} · ${teams.away}` : item.label ?? item.match_id)); }
      select.value = selectedMatch;
      select.addEventListener("change", () => { selectedMatch = select.value; model.follow = true; model.analysis = null; model.snapshot = null; model.timeline = []; model.events = []; model.speed = null; command(async () => {}); });
      const speed = node("select", {id: "research-speed", disabled: model.busy, "aria-label": "Replay speed"}, [1, 2, 5, 10, 30, 100].map(value => node("option", {value}, `${value}×`)));
      speed.value = String(model.speed ?? snapshot.replay?.speed ?? 1);
      speed.addEventListener("change", () => { model.speed = Number(speed.value); });
      const steps = node("input", {id: "research-steps", disabled: model.busy, type: "number", min: 1, max: 100, step: 1, value: model.steps, "aria-label": "Events per step"});
      steps.addEventListener("input", () => { model.steps = steps.value; });
      function replay(action) {
        const count = Number(steps.value), rate = Number(speed.value);
        if (!Number.isInteger(count) || count < 1 || count > 100 || !Number.isFinite(rate) || rate < 1 || rate > 100) { model.error = "Use 1–100 steps and a replay speed from 1–100."; draw(); return; }
        command(async () => { await post(`/replay/${encodeURIComponent(selectedMatch)}`, {action, speed: rate, steps: count}); });
      }
      return node("section", {class: "rt-controls", "aria-label": "Synthetic replay controls"}, node("label", {for: "research-match"}, "Simulation", select), node("div", {class: "rt-replay-actions"}, actionButton("Step", () => replay("step"), "secondary", {"data-action": "research-step"}), actionButton("Play", () => replay("start"), "primary"), actionButton("Pause", () => replay("pause")), actionButton("Resume", () => replay("resume"))), node("label", {for: "research-speed"}, "Speed on next action", speed), node("label", {for: "research-steps"}, "Events / step", steps), node("span", {class: "rt-replay-state", role: "status"}, `${snapshot.replay?.status ?? "Not supplied"} · ${snapshot.replay?.position ?? "—"} / ${snapshot.replay?.total ?? "—"} events`));
    }
    function horizonView(record) {
      const forecast = obj(record?.forecast), horizons = obj(forecast.horizons), value = obj(horizons[model.horizon]);
      const tabs = node("div", {class: "rt-horizon-tabs", role: "tablist", "aria-label": "Forecast horizon"});
      for (const [key, text] of HORIZONS) tabs.append(actionButton(text, () => { model.horizon = key; draw(); }, model.horizon === key ? "primary" : "secondary", {role: "tab", "aria-selected": model.horizon === key}));
      const body = panel("Forecast distributions", tabs, hint("Observed score and forecast distributions are separate. Probabilities describe possible synthetic outcomes, not certain future scores."));
      if (!Object.keys(value).length) { body.append(hint("This forecast does not supply the selected horizon.")); return body; }
      body.append(node("div", {class: "rt-facts"}, fact("Availability", value.availability), fact("Effective minutes", value.effective_minutes), fact("Unallocated / tail mass", percent(value.tail_mass))));
      if (value.reason) body.append(hint(label(value.reason)));
      if (number(value.next_goal_occurrence)) body.append(fact("Next goal occurrence", percent(value.next_goal_occurrence)));
      else body.append(distribution("Next goal occurrence", value.next_goal_occurrence));
      const side = obj(value.next_goal_side), remaining = obj(value.remaining_goals);
      const remainingDistribution = Array.isArray(remaining.distribution) ? Object.fromEntries(remaining.distribution.map((p, goals) => [String(goals), p])) : remaining.distribution;
      body.append(distribution("Next goal side (unconditional)", {home: side.home, away: side.away, no_goal: side.no_goal}), node("div", {class: "rt-facts"}, fact("Home given a goal", percent(side.conditional_home)), fact("Away given a goal", percent(side.conditional_away))), node("div", {class: "rt-facts"}, fact("Expected remaining goals", number(remaining.mean) ? remaining.mean.toFixed(3) : null), fact("Home expectation", number(remaining.home_mean) ? remaining.home_mean.toFixed(3) : null), fact("Away expectation", number(remaining.away_mean) ? remaining.away_mean.toFixed(3) : null)), distribution("Remaining goal count", remainingDistribution), fact(`Remaining goal tail (from ${remaining.tail_bucket?.from_goals ?? "unsupplied"})`, percent(remaining.tail_bucket?.probability)), distribution("Future score distribution", value.score_distribution), details("Uncertainty and model context", {uncertainty: value.uncertainty ?? forecast.uncertainty, model_id: forecast.model_id, horizon: value}));
      return body;
    }
    function timelineView(record) {
      const section = panel("Probability timeline", hint("Select a fetched forecast revision to inspect its original clocks, distribution and investigation."));
      section.append(node("div", {class: "rt-legend"}, OUTCOMES.map(([, title, cls]) => node("span", {class: cls}, title))), timelineChart(model.timeline, model.revision, choose));
      const select = node("select", {"aria-label": "Forecast revision"});
      for (const item of model.timeline) select.append(node("option", {value: item.revision}, `Revision ${item.revision} · ${item.minute ?? "—"} min · ${score(item.score)} · ${item.event_type ?? "event"}`));
      select.value = String(model.revision ?? ""); select.addEventListener("change", () => choose(Number(select.value)));
      section.append(node("div", {class: "rt-revision-select"}, node("label", {}, "Inspect revision", select), actionButton("Follow latest", () => { model.follow = true; model.revision = model.snapshot?.current_forecast?.revision ?? null; model.analysis = null; draw(); })), node("div", {class: "rt-facts"}, fact("Forecast revision", record?.revision), fact("State revision", record?.state_revision), fact("Event time", timestamp(record?.event_time)), fact("Received at", timestamp(record?.received_at))));
      const delta = obj(record?.change?.delta);
      section.append(node("div", {class: "rt-deltas"}, OUTCOMES.map(([key, title]) => fact(`${title} change`, points(delta[key])))), hint(list(record?.change?.reason_codes).join(" · ") || "No change reason supplied."));
      const branchName = node("input", {id: "research-branch-name", disabled: model.busy, type: "text", maxlength: 64, value: model.branchName, placeholder: "Optional branch name", "aria-label": "New synthetic branch name"});
      branchName.addEventListener("input", () => { model.branchName = branchName.value; });
      const terminal = String(model.snapshot?.state?.status).toUpperCase() === "FINISHED" && record?.state_revision >= model.snapshot?.state?.revision;
      const unavailable = !Number.isInteger(record?.state_revision) || terminal;
      section.append(node("div", {class: "rt-branch-controls"}, branchName, actionButton("Fork future", () => command(() => fork(record, false)), "secondary", {disabled: model.busy || unavailable}), actionButton("Rewind into new branch", () => command(() => fork(record, true)), "secondary", {disabled: model.busy || unavailable})), hint(terminal ? "Select an earlier revision to branch from before full time." : "Fork and rewind create a new match from the selected event-state prefix. Neither erases or rewrites the original history."));
      return section;
    }
    function relevanceView() {
      const section = panel("Relevance and utility across virtual worlds", hint("Compare features and universes using proper held-out scoring. Synthetic improvements are research-only and do not establish real-world forecasting accuracy."));
      section.append(node("div", {class: "actions"}, actionButton("Inspect latest experiment", () => command(async () => { model.relevance = await get("/experiments"); })), actionButton("Run 400-case relevance experiment", () => command(async () => { model.relevance = await post("/experiments/relevance", {seed: selectedSeed(), cases: 400}); }), "primary")));
      if (!model.relevance) { section.append(hint("No relevance report has been inspected. Experiments run only on explicit request.")); return section; }
      const report = obj(model.relevance.report ?? model.relevance), rows = list(report.rows);
      if (!rows.length) section.append(hint("The API did not supply experiment rows."));
      else {
        const names = [...new Set(rows.flatMap(row => Object.keys(obj(row))))];
        const first = ["universe", "feature", "target", "horizon", "train_brier", "test_brier", "heldout_brier_delta", "observed_improvement"].filter(name => names.includes(name));
        const columns = [...first, ...names.filter(name => !first.includes(name))].slice(0, 20);
        const body = node("tbody");
        for (const row of rows.slice(0, 400)) body.append(node("tr", {}, columns.map(key => node("td", {}, key === "observed_improvement" && typeof row[key] === "boolean" ? row[key] ? "Observed (synthetic)" : "Not observed" : row[key] === null || row[key] === undefined ? "Not supplied" : typeof row[key] === "object" ? JSON.stringify(inspectValue(row[key])) : String(row[key])))));
        section.append(node("div", {class: "table-wrap rt-experiment"}, node("table", {}, node("thead", {}, node("tr", {}, columns.map(key => node("th", {scope: "col"}, label(key))))), body)));
        if (rows.length > 400 || names.length > 20) section.append(hint(`Table display is limited to 400 rows and 20 columns; the API supplied ${rows.length} rows and ${names.length} fields. Inspect the report for the remaining data.`));
      }
      section.append(details("Actual experiment report and limitations", model.relevance));
      return section;
    }
    function inspectionView(record) {
      const analyses = list(model.snapshot?.analyses);
      const analysis = (model.analysis && record && model.analysis.revision === record.revision ? model.analysis.value : null) ?? record?.analysis ?? analyses.find(item => record && item.event_revision === record.state_revision) ?? null;
      const section = panel("Investigation and evidence", node("div", {class: "rt-inspector-tabs", role: "tablist", "aria-label": "Research inspection"}, ["analysis", "tools", "evidence"].map(key => actionButton(label(key), () => { model.inspection = key; draw(); }, model.inspection === key ? "primary" : "secondary", {role: "tab", "aria-selected": model.inspection === key}))));
      section.append(hint("The virtual reasoner can inspect this synthetic forecast with bounded local tools. External OpenAI remains unconfigured."));
      if (Number.isInteger(record?.revision)) section.append(actionButton("Investigate this revision", () => command(async () => { model.analysis = {revision: record.revision, value: await post(`/matches/${encodeURIComponent(selectedMatch)}/investigations`, {forecast_revision: record.revision})}; }), "primary", {"data-action": "research-investigate"}));
      if (!analysis) section.append(hint("No investigation is available for this revision. Use the explicit investigation action."));
      else if (model.inspection === "analysis") section.append(node("p", {class: "rt-analysis-summary"}, analysis.summary ?? "No summary supplied."), details("Hypotheses and analysis", analysis, true));
      else if (model.inspection === "tools") section.append(details("Actual tool results", analysis.tool_results ?? analysis.tools ?? [], true));
      else section.append(details("Evidence identifiers and packet", {evidence_ids: analysis.evidence_ids, packet_id: analysis.packet_id, forecast_id: record?.forecast_id, event_id: record?.event_id, event: model.events.find(event => event.event_id === record?.event_id)}, true));
      return section;
    }
    function draw() {
      if (!alive()) return;
      const opened = new Set([...host.querySelectorAll("details[open]")].map(item => item.querySelector("summary")?.textContent));
      const focus = host.contains(document.activeElement) ? document.activeElement.id : null;
      const top = node("div", {class: "rt-heading"}, node("div", {}, node("p", {class: "eyebrow"}, "VIRTUAL RESEARCH LAB"), node("h1", {}, "Realtime research"), node("p", {}, "Replay fictional evidence. Inspect each probability revision.")), node("div", {class: "actions"}, actionButton("New standard simulation", () => command(async () => { const created = await post("/scenarios", {scenario_id: "standard", source_mode: "DEMONSTRATION", universe: model.universe, seed: selectedSeed()}); selectedMatch = created.match_id; model.follow = true; model.analysis = null; model.speed = null; })), actionButton("Refresh research", () => command(async () => {}))));
      host.replaceChildren(top, scenarioControls(), componentStatus());
      if (model.error) host.append(node("div", {class: "rt-error", role: "alert"}, model.error));
      if (!model.matches.length || !model.snapshot) { host.append(panel(model.busy ? "Loading selected simulation" : "Start a synthetic scenario", hint("Create a standard simulation explicitly; opening this page never creates a scenario or starts a replay.")), relevanceView()); return; }
      const snapshot = model.snapshot, current = obj(snapshot.state), teams = obj(current.teams), record = chosen(), forecast = obj(record?.forecast);
      host.append(controls(snapshot));
      const observed = panel("Observed simulation state", node("p", {class: "rt-teams"}, `${teams.home ?? "Home"} · ${teams.away ?? "Away"}`), node("div", {class: "rt-score", "data-testid": "observed-score"}, score(current.score)), node("div", {class: "rt-facts"}, fact("Minute", current.minute), fact("Period", current.period), fact("State", current.status), fact("Source mode", snapshot.source_mode ?? current.source_mode)), details("Virtual world and lineage", snapshot.descriptor), details("Quality, virtual odds and state", {quality: current.quality, odds: current.odds, state: current}));
      const ft = panel("Full-time result probabilities", node("p", {class: "rt-selected-caption"}, `Forecast revision ${record?.revision ?? "not supplied"}${model.follow ? " · following latest" : " · historical selection"}`), fullTime(forecast), hint("Home / draw / away values come directly from the selected API forecast."));
      host.append(node("div", {class: "rt-overview"}, observed, ft), timelineView(record), node("div", {class: "rt-research-grid"}, horizonView(record), inspectionView(record)));
      const eventRows = node("tbody");
      for (const event of model.events.slice(-200).reverse()) eventRows.append(node("tr", {}, node("td", {}, event.event_type ?? event.type ?? "Not supplied"), node("td", {}, event.attributes?.minute ?? "—"), node("td", {}, timestamp(event.event_time)), node("td", {}, timestamp(event.received_at))));
      host.append(panel("Synthetic event audit", hint("Event time is when the fictional event occurred; received at is when the local engine received it."), node("div", {class: "table-wrap rt-events"}, node("table", {}, node("thead", {}, node("tr", {}, ["Event", "Minute", "Event time (UTC)", "Received at (UTC)"].map(title => node("th", {scope: "col"}, title)))), eventRows)), details("Canonical events", model.events)));
      host.append(panel("Metrics and evaluation", details("Fetched engine metrics", {status: model.status.metrics, match: snapshot.metrics}), node("div", {class: "actions"}, actionButton("Inspect cached evaluation", () => command(async () => { model.evaluation = await get("/evaluation"); })), actionButton("Evaluate synthetic replay", () => command(async () => { model.evaluation = await post("/evaluation", {}); }))), hint("Evaluation is an explicit synthetic-only action. No evaluation is started by page navigation or refresh."), model.evaluation ? details("Evaluation report", model.evaluation, true) : hint("No evaluation report has been requested in this view.")));
      host.append(relevanceView());
      for (const item of host.querySelectorAll("details")) if (opened.has(item.querySelector("summary")?.textContent)) item.open = true;
      if (focus) document.getElementById(focus)?.focus({preventScroll: true});
    }
    try { model.status = await get("/status"); await loadList(); if (selectedMatch) await refresh(); else draw(); }
    catch (error) { model.error = error.message; draw(); }
    return root;
  }
  window.DragonRealtime = Object.freeze({view, stop});
}());
