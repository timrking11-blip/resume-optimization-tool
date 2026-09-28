"use strict";
/* projectLibrary: a cch-backup/1 becomes a rot-library/3 bank with claims, confidence and the deliberate disputes. */
const test = require("node:test");
const assert = require("node:assert/strict");
const { R, bank, tagged } = require("../lib/riley.js");

test("the Riley backup projects to a complete bank", () => {
  const lib = bank();
  assert.equal(lib.schema, "rot-library/3");
  assert.deepEqual(lib.roles.map(r => r.key), ["hal", "lark", "kes", "pin", "qui"]);
  assert.equal(lib.roles.find(r => r.key === "kes").dates, "March 2021 – November 2023");
  assert.equal(lib.roles.find(r => r.key === "qui").hidden, true);
  assert.equal(lib.achievements.length, 19);
  assert.equal(lib.education[0].degree_line, "B.A., Communication | 2016");
  assert.equal(lib.certifications.length, 3);
  assert.equal(lib.technologies.length, 12);
  assert.equal(lib.competencies.length, 15);
  assert.equal(lib.identity.name, "Riley Mahoney");
  assert.equal(lib.template.id, "neutral-1");
  assert.deepEqual(lib.baseline.caps, { hal: 6, lark: 5, kes: 4, pin: 4, qui: 3 });
  assert.equal(lib.baseline.settings.fallback_role, "hal");
  assert.equal(lib.baseline.settings.prompts.persona.first, "Riley");
  assert.equal(lib.baseline.settings.edition, "hub");
  assert.ok(lib.tags["lead-routing-sla"] && lib.families.revops);
});

test("claims carry confidence from their evidence and the planned conflicts are disputed", () => {
  const lib = bank(), by = Object.fromEntries(lib.claims.map(c => [c.id, c]));
  assert.equal(lib.claims.length, 81);
  assert.deepEqual(lib.claims.filter(c => c.status === "disputed").map(c => c.id).sort(), ["ach:hal-pipeline", "role:kes:end", "role:pin:title"]);
  assert.equal(by["role:kes:end"].confidence, 0.55);           // 0.8 + 0.05 for a second source type, minus 0.3 unresolved
  assert.equal(by["ach:hal-pipeline"].confidence, 0.5);
  assert.equal(by["ach:hal-forecast"].confidence, 0.85);
  assert.deepEqual(by["ach:hal-forecast"].evidence.source_types, ["HISTORICAL_RESUME", "PUBLIC_PROFILE"]);
  for (const n of ["2", "71", "93"]) assert.ok(by["ach:hal-forecast"].numbers.includes(n), n);
  for (const n of ["1000000", "1200000"]) assert.ok(by["ach:hal-pricing"].numbers.includes(n), n);   // $1.2M, $1,200,000 and "over $1M" support one fact
  assert.equal(by["role:hal:title"].value, "Director of Revenue Operations");
  assert.equal(by["edu:lakeside:degree"].confidence, 0.85);
  assert.equal(by["cred:ga-iq:name"].evidence.n, 1);
});

test("a first-hand statement verifies and a resolution closes a dispute", () => {
  const B = tagged();
  const pin = B.subjects.find(s => s.id === "role:pin");
  pin.facts.title.resolution = { value: "Senior Marketing Manager", why: "picked in review", at: "2026-09-28" };
  const lib = R.claims.projectLibrary(B, require("../lib/riley.js").taxonomy, { now: "2026-09-28T00:00:00Z" });
  const c = lib.claims.find(c => c.id === "role:pin:title");
  assert.equal(c.status, "active");
  assert.equal(c.confidence, 1);
  assert.equal(c.value, "Senior Marketing Manager");
  assert.equal(lib.roles.find(r => r.key === "pin").title, "Senior Marketing Manager");
});

test("projection is deterministic", () => {
  assert.deepEqual(bank(), bank());
});

test("valuesConflict follows claims.py", () => {
  const v = R.claims.valuesConflict;
  assert.equal(v("2024", "2024-11"), false);
  assert.equal(v("2020", "2021"), true);
  assert.equal(v("2023-11", "2023-12"), true);
  assert.equal(v("6,100,000", "6100000"), false);
  assert.equal(v("6100000", "6800000"), true);
  assert.equal(v("HubSpot", "hubspot"), false);
  assert.equal(v("Marketing Manager", "Senior Marketing Manager"), true);
  assert.equal(v("", "x"), false);
});
