/* Execute actual dashboard functions in an isolated DOM-semantics fixture.
 * This is a Node unit fixture, not browser/installed UI acceptance. */
"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const source = fs.readFileSync(process.argv[2], "utf8");
class DomNode {
  constructor(tag, text = "") { this.tagName = tag; this.children = []; this.text = text; this.style = {}; this.attrs = {}; }
  append(...children) { this.children.push(...children.map(c => c instanceof DomNode ? c : new DomNode("#text", String(c)))); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  addEventListener() {}
  focus() { document.activeElement = this; }
  get textContent() { return this.tagName === "#text" ? this.text : this.children.map(c => c.textContent).join(""); }
  set textContent(value) { this.children = [new DomNode("#text", String(value))]; }
  set innerHTML(_value) { throw new Error("Markup parsing must not be used by the child renderer"); }
  toString() { return this.tagName === "p" ? "[object HTMLParagraphElement]" : "[object HTMLElement]"; }
}
const main = new DomNode("main");
const document = {createElement: tag => new DomNode(tag), createTextNode: text => new DomNode("#text", text)};
const state = {render: 0, scrolls: new Map(), match: null};
const fixture = {competition: "Synthetic standings fixture", season: null, label: "Reconstructed fixture", official: false,
  items: [{team: "Synthetic team", team_id: "fixture-team", played: 0, won: 0, drawn: 0, lost: 0, goals_for: 0, goals_against: 0, points: 0}],
  source_id: "synthetic-only", as_of: null, limitations: ["First retained limitation", "Second retained limitation"]};
const context = vm.createContext({Node: DomNode, URL, document, main, state, location: {hash: "#standings/fixture",origin:"http://127.0.0.1:18999"},
  window: {scrollTo() {}}, sessionStorage: {setItem() {}}, updateNav() {}, go() {}, time: value => value || "Not supplied",
  request: async () => fixture, loading: () => new DomNode("p", "Loading"), errorView: error => { throw error; }});
function include(name) {
  const line = source.split(/\r?\n/).find(text => new RegExp(`^(?:async )?function ${name}\\(`).test(text));
  if (!line) return false;
  vm.runInContext(line, context); return true;
}
for (const name of ["contentNodes", "skipToMain", "el", "button", "badge", "heading", "note", "empty", "safeUrl", "link", "table", "standingsView", "render"]) include(name);
const checks = [];
function check(name, action) { action(); checks.push(name); }
async function run() {
  check("null_undefined_false_omitted_but_zero_and_empty_preserved", () => {
    const node = context.el("div", {}, null, undefined, false, 0, "");
    assert.equal(node.textContent, "0"); assert.equal(node.children.length, 2);
  });
  check("nested_nodes_and_strings_keep_order_and_identity", () => {
    const p = context.el("p", {}, "Paragraph");
    const node = context.el("div", {}, ["before", [p, [null, 0, "after"]]]);
    assert.equal(node.textContent, "beforeParagraph0after"); assert.equal(node.children[1], p);
  });
  check("html_like_values_are_text_not_markup", () => {
    const node = context.el("div", {}, '<img src=x onerror="synthetic()">', ["<script>fixture()</script>"]);
    assert.equal(node.children.length, 2); assert.ok(node.children.every(c => c.tagName === "#text"));
    assert.equal(node.textContent, '<img src=x onerror="synthetic()"><script>fixture()</script>');
  });
  await context.render();
  check("standings_top_level_has_no_coerced_null_or_node_array", () => {
    assert.ok(!main.textContent.includes("null"), main.textContent);
    assert.ok(!main.textContent.includes("[object HTML"), main.textContent);
    assert.ok(main.textContent.includes("First retained limitation"));
    assert.ok(main.textContent.includes("Second retained limitation"));
  });
  check("standings_zero_points_and_statistics_remain_zero", () => {
    function all(node) { return [node, ...node.children.flatMap(all)]; }
    const cells = all(main).filter(n => n.tagName === "td");
    assert.equal(cells.length, 8); assert.deepEqual(cells.slice(1).map(n => n.textContent), Array(7).fill("0"));
  });
  check("skip_focus_preserves_route_rendered_rows_and_does_not_render", () => {
    const hash=context.location.hash, children=[...main.children], render=state.render;
    let prevented=false;context.skipToMain({preventDefault(){prevented=true;}});
    assert.ok(prevented);assert.equal(document.activeElement,main);
    assert.equal(context.location.hash,hash);assert.equal(state.render,render);
    assert.deepEqual(main.children,children);
  });
  check("external_http_https_links_still_use_new_context_and_unsafe_schemes_are_text", () => {
    for(const address of ["https://example.invalid/register","http://example.invalid/docs"]){
      const anchor=context.link("Synthetic provider",address);
      assert.equal(anchor.tagName,"a");assert.equal(anchor.attrs.href,address);
      assert.equal(anchor.attrs.target,"_blank");assert.equal(anchor.attrs.rel,"noopener noreferrer");
    }
    assert.equal(context.link("Unsupported","javascript:synthetic()").tagName,"span");
  });
  fixture.available = false; fixture.items = []; fixture.label = "Regulation-only standings unavailable for retained score scope";
  fixture.limitations = ["Extra-time and penalty scope is not regulation-only evidence."];
  await context.render();
  check("unavailable_score_scope_is_not_mislabeled_as_tournament_groups_or_fresh_data", () => {
    assert.ok(main.textContent.includes(fixture.label));
    assert.ok(main.textContent.includes(fixture.limitations[0]));
    assert.ok(!main.textContent.includes("Group tables and qualification rules"));
    assert.ok(main.textContent.includes("does not refresh retained source timestamps"));
    assert.ok(!main.textContent.includes("[object HTML"));
  });
  return {passed: true, fixture_scope: "Node DOM semantics; no browser/backend execution", checks};
}
run().then(report => process.stdout.write(JSON.stringify(report))).catch(error => {
  process.stdout.write(JSON.stringify({passed: false, failure_class: error.name, checks,
    literal_null_visible: main.textContent.includes("null"), node_array_visible: main.textContent.includes("[object HTMLParagraphElement]")}));
  process.exitCode = 1;
});
