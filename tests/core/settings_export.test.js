"use strict";
/* The bank exported by rot.py carries the edition settings the engine reads, with role keys aliased, and those settings
   drive the engine exactly as the page's own fallback block does. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..", "..");
const R = require(path.join(ROOT, "core", "rot_core.js"));

test("data/library.json carries baseline.settings with aliased role keys and no notes", () => {
  const lib = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "library.json"), "utf8"));
  const s = lib.baseline.settings;
  assert.ok(s, "baseline.settings missing: run python rot.py export");
  assert.equal(s._about, undefined);
  assert.ok(lib.roles.some(r => r.key === s.fallback_role), "fallback_role must be a bank role key");
  assert.ok(lib.roles.some(r => r.key === s.default_engagement_role), "default_engagement_role must be a bank role key");
  assert.ok(lib.roles.some(r => "r:" + r.key === s.prompts.bullet_example.place), "bullet_example.place must name a bank role");
  assert.ok(lib.claims.some(c => c.id === s.education_claim_default));
  for (const [tag] of s.questions.consulting) assert.ok(lib.tags[tag], `unknown consulting tag ${tag}`);
  assert.ok(lib.tags[s.questions.engagement_tag]);
  assert.deepEqual(Object.keys(s.prompts.persona).sort(), ["first", "name", "possessive", "possessive_cap", "standard_label", "subject"]);
});

test("the engine reads settings from the bank the same way the page's fallback supplies them", () => {
  const lib = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "library.json"), "utf8"));
  const fromBank = R.createEngine({ bank: lib, settings: lib.baseline.settings });
  const fromPage = R.createEngine({ bank: lib, settings: { ...lib.baseline.settings, prompts: JSON.parse(JSON.stringify(lib.baseline.settings.prompts)) } });
  const texts = ["Closed 5 signed partnerships across two divisions in one season."];
  assert.equal(fromBank.prompts.tighten(texts), fromPage.prompts.tighten(texts));
  assert.equal(fromBank.consultingWanted({ req: { "board-advisory": { weight: 1 } }, jd: "" }), true);
  assert.equal(fromBank.consultingWanted({ req: {}, jd: "We value client engagements." }), true);
  assert.equal(fromBank.consultingWanted({ req: {}, jd: "Nothing here." }), false);
});
