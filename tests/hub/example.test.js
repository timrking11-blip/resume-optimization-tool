"use strict";
/* The Hub's example person: one open discrepancy, chosen for judgment, and everything else settled; it loads, projects and drafts. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { R, ROOT, taxonomy, postings } = require("../lib/riley.js");

const EX = JSON.parse(fs.readFileSync(path.join(ROOT, "hub", "example", "backup.json"), "utf8"));

test("the example record leaves exactly one discrepancy open, and it is the pricing ownership question", () => {
  const T = R.createEngine({ bank: { tags: taxonomy.tags }, settings: {} }), B = JSON.parse(JSON.stringify(EX));   // tag a copy, the way the page does
  for (const a of B.achievements) if (!Object.keys(a.tags || {}).length) a.tags = Object.fromEntries(Object.keys(T.extractRequirements(a.canonical)).map(t => [t, 1]));
  const lib = R.claims.projectLibrary(B, taxonomy, { now: "2026-09-28T00:00:00Z" });
  assert.deepEqual(lib.claims.filter(c => c.status === "disputed").map(c => c.id), ["ach:hal-pricing"]);
  const c = lib.claims.find(c => c.id === "ach:hal-pricing");
  assert.match(c.value, /^Owned pricing and packaging/);
  const a = EX.achievements.find(a => a.id === "hal-pricing");
  assert.match(a.contradicting[0].value, /^Partnered with product marketing and finance/);
  assert.ok(a.contradicting[0].evidence.every(id => EX.evidence.some(e => e.id === id)), "the other statement cites a real evidence row");
  assert.equal(lib.roles.find(r => r.key === "kes").dates, "March 2021 – November 2023", "the clerical date conflict is settled");
  assert.equal(lib.roles.find(r => r.key === "pin").title, "Senior Marketing Manager");
  const E = R.createEngine({ bank: lib, settings: lib.baseline.settings });
  const d = { req: E.extractRequirements(postings["01"]), jd: postings["01"], pinned: new Set(), excluded: new Set(), locked: null, textChoice: {}, edits: {}, tagline: null, compOrder: null,
    sectionEdits: {}, extra: { tagline: [], expertise: [], technology: [], competency: [] }, engDetails: {}, editsC: {}, excludedC: new Set(), newAch: [], inbox: [], adj: {},
    summaryOn: false, summary: null, summaryClaims: [], runId: "t", questions: [] };
  Object.assign(d, E.compute(d, d.req));
  const m = E.resumeModel(d);
  assert.equal(m.roles[0].key, "hal");
  assert.ok(!m.roles.some(r => r.bullets.some(b => /pricing and packaging for the mid-market tier/.test(b.text))), "the disputed entry is held back until the person decides");
  assert.ok(m.roles.some(r => r.bullets.some(b => /\$6\.8M/.test(b.text))), "the settled pipeline figure prints");
});

test("the example is what make_example.py writes", () => {
  const r = require("node:child_process").spawnSync("python", [path.join(ROOT, "hub", "example", "make_example.py")], { cwd: ROOT, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /open discrepancies: \['ach:hal-pricing'\]/);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(ROOT, "hub", "example", "backup.json"), "utf8")), EX);
});
