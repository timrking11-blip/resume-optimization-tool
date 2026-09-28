"use strict";
/* The fictional person as a bank: the Riley backup projected through the core with the GTM taxonomy. Tags are filled the way
   the Hub fills them at entry time (the engine's own tagger over each accomplishment). */
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..", "..");
const R = require(path.join(ROOT, "core", "rot_core.js"));

const NOW = "2026-09-28T00:00:00Z";
const taxonomy = JSON.parse(fs.readFileSync(path.join(ROOT, "core", "taxonomy", "gtm_v1.json"), "utf8"));
const postings = Object.fromEntries(fs.readdirSync(path.join(ROOT, "tests", "fixtures", "persona", "postings")).sort()
  .map(f => [f.slice(0, 2), fs.readFileSync(path.join(ROOT, "tests", "fixtures", "persona", "postings", f), "utf8")]));

function backup() { return JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "fixtures", "persona", "riley_backup.json"), "utf8")); }
function tagged() {
  const B = backup(), T = R.createEngine({ bank: { tags: taxonomy.tags }, settings: {} });
  for (const a of B.achievements) if (!Object.keys(a.tags || {}).length) a.tags = Object.fromEntries(Object.keys(T.extractRequirements(a.canonical)).map(t => [t, 1]));
  return B;
}
function bank(B) { return R.claims.projectLibrary(B || tagged(), taxonomy, { now: NOW }); }
function engine(lib) { lib = lib || bank(); return { lib, E: R.createEngine({ bank: lib, settings: lib.baseline.settings }) }; }
function draft(E, jd) {
  const d = { req: E.extractRequirements(jd), jd, pinned: new Set(), excluded: new Set(), locked: null, textChoice: {}, edits: {}, tagline: null, compOrder: null,
    sectionEdits: {}, extra: { tagline: [], expertise: [], technology: [], competency: [] }, engDetails: {}, editsC: {}, excludedC: new Set(), newAch: [], inbox: [], adj: {},
    summaryOn: false, summary: null, summaryClaims: [], runId: "run-test", questions: [] };
  const c = E.compute(d, d.req);
  Object.assign(d, c);
  return d;
}
module.exports = { R, ROOT, NOW, taxonomy, postings, backup, tagged, bank, engine, draft };
