"use strict";
/* Not a test: a probe of the demo's score headroom. For each fixture posting against the example record it prints the baseline
   match, how much of the score is still available, what each template question can move, and the effect of tagging answers
   with the taxonomy (as intake does) instead of the question's tag alone.   node tests/hub/score_probe.js */
const path = require("node:path");
const fs = require("node:fs");
const { R, ROOT, taxonomy, postings } = require("../lib/riley.js");

const EX = JSON.parse(fs.readFileSync(path.join(ROOT, "hub", "example", "backup.json"), "utf8"));
const T = R.createEngine({ bank: { tags: taxonomy.tags }, settings: {} });
const tagsFor = t => Object.fromEntries(Object.keys(T.extractRequirements(t)).map(x => [x, 1]));
for (const a of EX.achievements) if (!Object.keys(a.tags || {}).length) a.tags = tagsFor(a.canonical);
const lib = R.claims.projectLibrary(EX, taxonomy, { now: "2026-09-28T00:00:00Z" });
const E = R.createEngine({ bank: lib, settings: lib.baseline.settings });
const mk = jd => { const d = { req: E.extractRequirements(jd), jd, pinned: new Set(), excluded: new Set(), locked: null, textChoice: {}, edits: {}, tagline: null, compOrder: null, sectionEdits: {}, extra: { tagline: [], expertise: [], technology: [], competency: [] }, engDetails: {}, editsC: {}, excludedC: new Set(), newAch: [], inbox: [], adj: {}, summaryOn: false, summary: null, summaryClaims: [], runId: "probe", questions: [] }; Object.assign(d, E.compute(d, d.req)); return d; };
// a thoughtful answer per question tag: lines that name the requirement's own words and a number
const ANS = {
  "revenue-analytics": "Built the CRO's weekly pipeline review in Looker: coverage by segment, stage conversion and win rates, reported every Monday to 12 leaders.\nReplaced spreadsheet roll-ups with one revenue dashboard; the forecast call dropped from 90 minutes to 30.",
  "data-solutions": "Modelled Tableau dashboards for 6 enterprise accounts showing pipeline coverage and win rates by segment.",
  "product-marketing": "Partnered with product marketing on the launch of the mid-market tier: positioning, packaging and a 14-market launch calendar delivered on time.",
  "strategic-partnerships": "Stood up 3 agency partnerships that sourced 22 opportunities and $1.4M of pipeline in a year.",
  "team-leadership": "Hired and managed a team of 4 analysts and administrators; two were promoted within 18 months.",
  "pipeline-management": "Ran weekly pipeline reviews covering $6.8M of qualified pipeline; coverage held above 3x for four quarters." };
const dflt = t => `Led the ${(lib.tags[t] || { label: t }).label.toLowerCase()} work for the team: defined the process, ran it weekly, and improved the result by 20% in two quarters.`;
for (const [k, jd] of Object.entries(postings)) {
  const d = mk(jd), tot = Object.values(d.req).reduce((a, r) => a + r.weight, 0);
  const qs = E.templateQuestions(d);
  const gaps = Object.entries(d.req).map(([t, r]) => ({ t, w: r.weight, c: d.cov[t] || 0 })).sort((a, b) => b.w * (1 - Math.min(b.c, 1)) - a.w * (1 - Math.min(a.c, 1)));
  const uncovered = gaps.reduce((a, g) => a + g.w * (1 - Math.min(g.c, 1)), 0);
  const sim = rich => { const d2 = mk(jd); let n = 0; for (const q of qs) { if (q.section !== "experience") continue; const text = ANS[q.tag] || dflt(q.tag); for (const line of text.split("\n")) { const tags = rich ? { ...tagsFor(line), [q.tag]: 1 } : { [q.tag]: 1 }; const id = `gate2-probe-${n++}`; d2.newAch.push({ n, ach: { id, role: q.role, engagement: null, confidence: "asserted", fresh: true, has_metrics: /\d/.test(line), tags, metrics: [], texts: [{ id: "t" + n, kind: "learned", angle: "gate2", text: line, score_adj: 0, fresh: true }] }, role: q.role, tags: Object.keys(tags), engagement: null, q_ix: 0, b_ix: 0, text: { text: line } }); d2.pinned.add(id); } } Object.assign(d2, E.compute(d2, d2.req)); return d2.score; };
  console.log(`\n== posting ${k} · baseline ${(d.score * 100).toFixed(1)}% · ${Object.keys(d.req).length} requirement tags, total weight ${tot.toFixed(1)}, uncovered weight ${uncovered.toFixed(1)} (${(100 * uncovered / tot).toFixed(0)}% of the score still available)`);
  console.log("  top gaps:", gaps.slice(0, 8).map(g => `${g.t} w${g.w} cov${g.c}`).join(" | "));
  console.log("  questions:", qs.map(q => `${q.section}${q.tag ? ":" + q.tag : ""}${q.section === "experience" ? ` (+${(100 * d.req[q.tag].weight * (1 - Math.min(d.cov[q.tag] || 0, 1)) / tot).toFixed(1)}% max)` : " (+0%: tools line)"}`).join(" | "));
  console.log(`  after thoughtful answers: question-tag only ${(sim(false) * 100).toFixed(1)}% · answers tagged by the taxonomy ${(sim(true) * 100).toFixed(1)}%`);
}
