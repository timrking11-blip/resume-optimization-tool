"use strict";
/* The number check and the text helpers, exercised with the wordings the test person's documents use. */
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const R = require(path.resolve(__dirname, "..", "..", "core", "rot_core.js"));

const toks = s => [...R.qa.numberTokens(s)].sort();

test("numberTokens reads currency, suffixes, commas, words, ranges and percentages", () => {
  assert.deepEqual(toks("reached $1.2M ARR in its first year"), ["1200000"]);
  assert.deepEqual(toks("reached $1,200,000 in ARR in year one"), ["1", "1200000"]);
  assert.deepEqual(toks("passed $1M ARR"), ["1000000"]);
  assert.deepEqual(toks("Consolidated three CRMs into one instance"), ["1", "3"]);
  assert.deepEqual(toks("the top result on a team of nine"), ["9"]);
  assert.deepEqual(toks("from 71% to 93% within two quarters"), ["2", "71", "93"]);
  assert.deepEqual(toks("cut speed-to-lead from 26 hours to under 2 hours"), ["2", "26"]);
  assert.deepEqual(toks("produced $850K in first-year revenue"), ["850000"]);
  assert.deepEqual(toks("buying committees of 6 to 8 stakeholders"), ["6", "8"]);
  assert.deepEqual(toks("a 12–18 month payback"), ["12", "18"]);
  assert.deepEqual(toks("no figures in this sentence"), []);
});

test("qaLine judges numbers against the claims and the answer, flags first person and the ceiling", () => {
  const claims = { "ach:x": { id: "ach:x", status: "active", numbers: ["5"] }, "ach:y": { id: "ach:y", status: "disputed", numbers: ["9"] } };
  const lookup = id => claims[id];
  const band = { hard_ceiling: 170 };
  assert.deepEqual(R.qa.qaLine("Closed 5 signed partnerships.", ["ach:x"], [], band, lookup), []);
  assert.deepEqual(R.qa.qaLine("Closed 7 signed partnerships.", ["ach:x"], [], band, lookup), ["numbers not in your answer or the evidence: 7"]);
  assert.deepEqual(R.qa.qaLine("Closed 7 signed partnerships.", [], ["I closed seven partnerships last season"], band, lookup), []);
  assert.deepEqual(R.qa.qaLine("I closed 7 deals.", [], ["7 deals"], null, lookup), ["first person"]);
  assert.deepEqual(R.qa.qaLine("Handled I.T. tickets for the region.", [], ["tickets"], null, lookup), []);
  assert.deepEqual(R.qa.qaLine("Grew pipeline to 9 accounts.", ["ach:y"], [], null, lookup), ["disputed claim ach:y"]);
  const long = "x".repeat(171);
  assert.deepEqual(R.qa.qaLine(long, [], ["y"], band, lookup), ["171 chars > 170"]);
  assert.deepEqual(R.qa.blocking(["171 chars > 170", "first person"]), ["first person"]);
  assert.deepEqual(R.qa.qaLine("Closed 7 deals.", [], [], null, lookup), [], "with no basis at all, numbers are not judged");
});

test("text helpers: cleanBullet, splitAnswer, splitPhrases, uniq, fmtDate", () => {
  assert.equal(R.util.cleanBullet("• rebuilt the renewal pipeline"), "Rebuilt the renewal pipeline.");
  assert.deepEqual(R.util.splitAnswer("Built pricing scenarios for three territories\nPresented the go/no-go recommendation"),
    ["Built pricing scenarios for three territories.", "Presented the go/no-go recommendation."]);
  assert.deepEqual(R.util.splitPhrases("Looker (dashboards, basic), SQL (basic queries)", "technology"), ["Looker (dashboards, basic)", "SQL (basic queries)"]);
  assert.deepEqual(R.util.uniq(["Alpha", "alpha", "Beta"]), ["Alpha", "Beta"]);
  assert.equal(R.util.fmtDate("2024-01"), "January 2024");
  assert.equal(R.util.fmtDate(null), "Present");
  assert.equal(R.util.sectionOf({}), "experience");
  assert.equal(R.util.placeKey({ role: "r1", engagement: null }), "r:r1");
  assert.equal(R.util.placeKey({ role: "r1", engagement: "e1" }), "e:e1");
});
