"use strict";
/* The Hub's store and the shapes its manual-entry path writes: a backup round-trips, the page's fallback layout is the neutral
   layout, and a record typed by hand projects to a bank that drafts from the newest role with every line traced to the person's words. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { R, ROOT, taxonomy, postings, backup } = require("../lib/riley.js");

require(path.join(ROOT, "hub", "store.js"));   // defines globalThis.CCH; no localStorage here, so the store runs in memory
const { BrowserStore } = globalThis.CCH;
const HUB_JS = fs.readFileSync(path.join(ROOT, "hub", "hub.js"), "utf8");

test("a backup round-trips through the store", () => {
  const s = new BrowserStore(R.VERSION);
  assert.equal(s.available, false);
  const B = backup();
  s.importBackup(B);
  const out = s.snapshot();
  assert.equal(out.schema, "cch-backup/1");
  for (const k of ["identity", "sources", "evidence", "subjects", "achievements", "taxonomy", "settings", "feedback", "outcomes", "review_log"]) assert.deepEqual(out[k], B[k], k);
  assert.deepEqual(out.sessions, []);
  assert.equal(s.isEmpty(), false);
  s.wipe();
  assert.equal(s.isEmpty(), true);
  assert.throws(() => s.importBackup({ schema: "other" }), /cch-backup\/1/);
});

test("the page's fallback layout is the neutral layout", () => {
  const m = HUB_JS.match(/const NEUTRAL_LAYOUT = (\{.*\});\n/);
  assert.ok(m, "NEUTRAL_LAYOUT constant");
  const page = JSON.parse(m[1]), file = JSON.parse(fs.readFileSync(path.join(ROOT, "core", "layouts", "neutral-1.json"), "utf8"));
  assert.deepEqual(page.sections, file.sections);
  assert.deepEqual(page.labels, file.labels);
  assert.deepEqual(page.joins, file.joins);
  assert.equal(page.id, file.id);
});

/* the shapes hub.js writes for a person who types their record (addRole / addLines / addSubject / saveLists), without the DOM */
function typedRecord() {
  const T = R.createEngine({ bank: { tags: taxonomy.tags }, settings: {} });
  const tagsFor = t => Object.fromEntries(Object.keys(T.extractRequirements(t)).map(x => [x, 1]));
  const ev = [], subjects = [], achievements = [];
  const row = (id, quote, locator) => { ev.push({ id, source: "src:you", source_type: "USER_ENTERED", channel: "paste", quote, observed_at: "2026-09-28", locator }); return id; };
  const fact = (v, e) => ({ value: v, evidence: [e], contradicting: [] });
  const roles = [
    ["r1", "Director of Revenue Operations", "Halcyon Metrics", "Denver, CO", "2024-01", null, [
      "Redesigned forecasting cadence and stage definitions; forecast accuracy rose from 71% to 93% in two quarters.",
      "Cut speed-to-lead from 26 hours to under 2 with new routing rules and a weekly SLA review.",
      "Consolidated 14 GTM tools to 9, saving $210K a year in licences.",
      "Built the pricing and packaging model for two new tiers with finance." ]],
    ["r2", "Senior Account Executive", "Kestrel Media", "Denver, CO", "2021-03", "2023-11", [
      "Closed $2.4M in retail media and CTV deals, 118% of quota.",
      "Ran discovery and executive presentations with grocery and CPG brands.",
      "Modelled CPM and CPA scenarios that won three agency pitches." ]],
  ];
  for (const [key, title, employer, location, start, end, lines] of roles) {
    const e = row(`ev:you:${key}:role`, [title, employer, location, `${start} – ${end || "Present"}`].join(" | "), `role ${key}`);
    subjects.push({ id: `role:${key}`, kind: "role", key, sort: subjects.length, hidden: false, facts: { title: fact(title, e), employer: fact(employer, e), location: fact(location, e), start: fact(start, e), end: fact(end, e) } });
    lines.forEach((t, n) => { const id = `${key}-${n + 1}`; row(`ev:you:${id}`, t, `role ${key}, line ${n + 1}`);
      achievements.push({ id, role: key, engagement: null, canonical: R.util.cleanBullet(t), evidence: [`ev:you:${id}`], contradicting: [], tags: tagsFor(t), metrics: [], origin: "paste" }); });
  }
  const e = row("ev:you:edu:lakeside", "Lakeside State University | B.A., Communication | 2016", "education");
  subjects.push({ id: "edu:lakeside", kind: "education", facts: { school: fact("Lakeside State University", e), degree: fact("B.A., Communication", e), date: fact("2016", e) } });
  ["Forecasting", "Pricing and packaging", "Lead routing"].forEach((t, i) => { const id = `expertise:${t.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`; row(`ev:you:${id}`, t, "expertise");
    subjects.push({ id, kind: "expertise", sort: i, tags: Object.keys(T.extractRequirements(t)), facts: { text: fact(t, `ev:you:${id}`) } }); });
  ["Salesforce", "HubSpot", "Looker"].forEach((t, i) => { const id = `tool:${t.toLowerCase()}`; row(`ev:you:${id}`, t, "tool");
    subjects.push({ id, kind: "tool", sort: i, tags: [], facts: { name: fact(t, `ev:you:${id}`) } }); });
  return { schema: "cch-backup/1", core: R.VERSION, edition: "hub", identity: { name: "Sam Example", location: "Denver, CO", phone: "", email: "sam@example.com", links: [] },
    sources: [{ id: "src:you", kind: "paste", label: "Typed on this page", authored_at: "2026-09-28", observed_at: "2026-09-28", source_type: "USER_ENTERED" }],
    evidence: ev, subjects, achievements, taxonomy: { id: "gtm/1", user_tags: {} }, settings: {}, sessions: [], feedback: [], outcomes: [], review_log: [] };
}

test("a record typed by hand projects, drafts from the newest role, and traces every line to the person's words", () => {
  const lib = R.claims.projectLibrary(typedRecord(), taxonomy, { now: "2026-09-28T00:00:00Z" });
  assert.deepEqual(lib.roles.map(r => r.key), ["r1", "r2"]);
  assert.equal(lib.roles[0].dates, "January 2024 – Present");
  assert.equal(lib.achievements.length, 7);
  assert.ok(lib.claims.every(c => c.confidence === 1 && c.status === "active"), "every typed fact is first-hand and verified");
  assert.equal(lib.baseline.settings.fallback_role, "r1");
  assert.equal(lib.baseline.settings.prompts.persona.first, "Sam");
  const E = R.createEngine({ bank: lib, settings: lib.baseline.settings });
  const d = { req: E.extractRequirements(postings["01"]), jd: postings["01"], pinned: new Set(), excluded: new Set(), locked: null, textChoice: {}, edits: {}, tagline: null, compOrder: null,
    sectionEdits: {}, extra: { tagline: [], expertise: [], technology: [], competency: [] }, engDetails: {}, editsC: {}, excludedC: new Set(), newAch: [], inbox: [], adj: {},
    summaryOn: false, summary: null, summaryClaims: [], runId: "run-test", questions: [] };
  Object.assign(d, E.compute(d, d.req));
  assert.ok(d.score > 0.3, `score ${d.score}`);
  const m = E.resumeModel(d);
  assert.equal(m.roles[0].key, "r1");
  assert.equal(m.roles[0].bullets.length, 4);
  for (const r of m.roles) for (const b of r.bullets) assert.ok(b.claim_ids.length && E.claimById(b.claim_ids[0]).evidence.source_types.includes("USER_ENTERED"));
  assert.equal(m.generator.edition, "hub");
  const qs = E.templateQuestions(d);
  assert.ok(qs.length >= 3 && qs.length <= 5);
  // the neutral layout prints Skills and Tools, no tagline, and a contact line without an empty phone slot
  const P = R.doc.docParagraphs(m, JSON.parse(fs.readFileSync(path.join(ROOT, "core", "layouts", "neutral-1.json"), "utf8")));
  assert.equal(P[1][1][0][1], "Denver, CO | sam@example.com");
  assert.ok(P.some(p => p[0] === "tech_label") && !P.some(p => p[0] === "tagline"));
  assert.ok(R.doc.plainText(m, NEUTRAL()).includes("Denver, CO | sam@example.com\n"));
});
function NEUTRAL() { return JSON.parse(fs.readFileSync(path.join(ROOT, "core", "layouts", "neutral-1.json"), "utf8")); }
