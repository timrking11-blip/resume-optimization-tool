"use strict";
/* The scorecard reads the match without changing it: growth list, potential per requirement, tools named in an answer,
   and what each answered question did. The tailor prompt carries the growth section when settings.prompts.growth_list is on. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { R, ROOT, taxonomy, postings, engine, draft } = require("../lib/riley.js");
const S = R.scorecard;

const EX = JSON.parse(fs.readFileSync(path.join(ROOT, "hub", "example", "backup.json"), "utf8"));
function exampleEngine() {
  const T = R.createEngine({ bank: { tags: taxonomy.tags }, settings: {} }), B = JSON.parse(JSON.stringify(EX));
  for (const a of B.achievements) if (!Object.keys(a.tags || {}).length) a.tags = Object.fromEntries(Object.keys(T.extractRequirements(a.canonical)).map(t => [t, 1]));
  const lib = R.claims.projectLibrary(B, taxonomy, { now: "2026-09-28T00:00:00Z" });
  return { lib, E: R.createEngine({ bank: lib, settings: lib.baseline.settings }) };
}

test("the core carries the scorecard and the Hub alias points at it", () => {
  assert.equal(R.VERSION, "1.2.0");
  assert.deepEqual(require(path.join(ROOT, "hub", "scorecard.js")), S);
  assert.equal(engine().E.prompts.VERSIONS.tailor, "tailor@7");
});

test("growth ranks the unproven requirements by what proving them would add, and the gains sum to the headroom", () => {
  const { lib, E } = exampleEngine();
  const d = draft(E, postings["01"]);
  const g = S.growth(d.req, d.cov, lib.tags, 8);
  assert.equal(g[0].tag, "revenue-analytics");
  assert.ok(Math.abs(g[0].gain - 0.0602) < 0.002, String(g[0].gain));
  assert.ok(g[0].words.includes("dashboards"));
  assert.ok(g.every((x, i) => i === 0 || x.gain <= g[i - 1].gain));
  const all = S.growth(d.req, d.cov, lib.tags, 100);
  assert.ok(Math.abs(all.reduce((a, x) => a + x.gain, 0) - S.headroom(d.req, d.cov)) < 1e-9);
  assert.ok(Math.abs(d.score + S.headroom(d.req, d.cov) - 1) < 1e-9, "score plus headroom is the whole posting");
  assert.equal(S.potential(d.req, d.cov, "crm-discipline"), 0, "a proven requirement has no potential left");
  assert.equal(S.potential(d.req, d.cov, "not-a-tag"), 0);
  const stretch = draft(E, postings["05"]);
  assert.ok(stretch.score < d.score - 0.1, "the stretch posting starts well below the close fit");
});

test("toolsNamed offers the tools an answer names that the Tools line lacks", () => {
  assert.deepEqual(S.toolsNamed("Built the review in Looker and wrote the SQL behind it; exported to Excel.", ["Excel", "Salesforce"]), ["Looker", "SQL"]);
  assert.deepEqual(S.toolsNamed("Nothing technical here", []), []);
  assert.deepEqual(S.toolsNamed("We ran Outreach.io sequences", ["Outreach"]), [], "Outreach.io is the Outreach already listed");
});

test("contributions attribute the change in the match to each answered question without changing the match", () => {
  const { E } = exampleEngine();
  const d = draft(E, postings["01"]);
  const before = d.score;
  const mk = (n, q, role, text, tags, attach) => attach
    ? { n, q_ix: q, b_ix: 0, attach, role, tags, engagement: null, longform: null, text: { id: `new:t:${n}`, kind: "learned", angle: "gate2", text, score_adj: 0, fresh: true } }
    : { n, q_ix: q, b_ix: 0, ach: { id: `gate2-t-${n}`, role, engagement: null, confidence: "asserted", fresh: true, has_metrics: /\d/.test(text), tags: Object.fromEntries(tags.map(t => [t, 1])), metrics: [], texts: [{ id: `new:t:${n}`, kind: "learned", angle: "gate2", text, score_adj: 0, fresh: true }] }, role, tags, engagement: null, longform: null, text: { text } };
  d.newAch = [
    mk(0, 1, "hal", "Built the CRO's weekly pipeline review in Looker with coverage by segment and win rates.", ["revenue-analytics"]),
    mk(1, 2, "hal", "Ran the forecast call every Monday for 12 leaders.", ["forecasting"]),
    mk(2, 3, "hal", "Added a stage-exit checklist to the forecast process.", ["forecasting"], "hal-forecast"),
  ];
  d.pinned.add("gate2-t-0"); d.pinned.add("gate2-t-1"); d.pinned.add("hal-forecast");
  Object.assign(d, E.compute(d, d.req));
  const c = S.contributions(E, d);
  assert.ok(Math.abs(c.before - before) < 1e-9);
  assert.ok(Math.abs(c.after - d.score) < 1e-9, "the attribution reproduces the actual match");
  assert.ok(Math.abs(c.byQuestion[1].delta - 0.0602) < 0.002, String(c.byQuestion[1].delta));
  assert.equal(c.byQuestion[1].entries, 1);
  assert.ok(Math.abs(c.byQuestion[2].delta) < 1e-9, "a second entry for a proven skill adds nothing");
  assert.deepEqual([c.byQuestion[3].delta, c.byQuestion[3].enriched], [0, 1]);
  assert.ok(d.score - before > 0.055, "the real match moved by the new entry, and only by it");
});

test("the tailor prompt carries the growth section when growth_list is on, and not otherwise", () => {
  const { E, lib } = exampleEngine();
  const d = draft(E, postings["01"]);
  const p = E.prompts.tailor(d);
  assert.ok(p.includes("WHERE THE MATCH CAN GROW"));
  assert.ok(p.includes("revenue-analytics: Revenue Analytics & Dashboards | +6.0 | dashboards, looker"));
  assert.ok(p.includes("At least four of the five followups target WHERE THE MATCH CAN GROW"));
  assert.ok(p.includes("never as a suggested answer"));
  const off = R.createEngine({ bank: lib, settings: { ...lib.baseline.settings, prompts: { ...lib.baseline.settings.prompts, growth_list: false } } });
  assert.ok(!off.prompts.tailor(draft(off, postings["01"])).includes("WHERE THE MATCH CAN GROW"));
});
