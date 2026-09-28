"use strict";
/* The engine on a bank that is not Tim's: matching, selection, the disputed hold, hidden roles, questions, the model. */
const test = require("node:test");
const assert = require("node:assert/strict");
const { R, postings, engine, draft } = require("../lib/riley.js");

test("the revenue-operations posting drafts from the Halcyon role and holds the disputed metric back", () => {
  const { E } = engine();
  const d = draft(E, postings["01"]);
  assert.ok(d.score > 0.5 && d.score < 0.95, `score ${d.score}`);
  const m = E.resumeModel(d);
  assert.equal(m.roles[0].key, "hal");
  assert.ok(m.roles[0].bullets.length >= 4);
  assert.ok(!m.roles.some(r => r.bullets.some(b => /pipeline to \$6\.[18]M/.test(b.text))), "the disputed pipeline metric must not print");
  assert.ok(!m.roles.some(r => r.key === "qui"), "the hidden early role stays off the draft unless it scores");
  assert.equal(m.generator.core, R.VERSION);
  assert.equal(m.generator.edition, "hub");
  assert.ok(Object.keys(m.trace).filter(k => k.startsWith("role:hal:")).length >= 4);
  for (const b of m.roles[0].bullets) assert.ok(b.claim_ids.length, "every printed bullet names its claim");
});

test("the retail media posting leans on the Kestrel role", () => {
  const { E } = engine();
  const m = E.resumeModel(draft(E, postings["02"]));
  const kes = m.roles.find(r => r.key === "kes");
  assert.ok(kes && kes.bullets.length >= 3);
  assert.ok(kes.bullets.some(b => /retail media|ROAS|CPM|grocery/.test(b.text)), "the retail-media bullets win the cap race");
});

test("template questions target gaps, at most five, with valid sections", () => {
  const { E } = engine();
  const d = draft(E, postings["05"]);
  const qs = E.templateQuestions(d);
  assert.ok(qs.length >= 3 && qs.length <= 5);
  for (const q of qs) assert.ok(["experience", "technology", "engagement"].includes(q.section), q.section);
  assert.ok(qs.filter(q => q.section === "technology").length <= 1);
  for (const q of qs.filter(q => q.section === "experience")) assert.ok(d.req[q.tag], `question tag ${q.tag} is a requirement`);
});

test("the neutral layout prints the model without tagline or core-competency sections", () => {
  const { lib, E } = engine();
  const m = E.resumeModel(draft(E, postings["01"]));
  const kinds = R.doc.docParagraphs(m, JSON.parse(require("node:fs").readFileSync(require("node:path").join(require("../lib/riley.js").ROOT, "core", "layouts", "neutral-1.json"), "utf8"))).map(p => p[0]);
  assert.deepEqual(kinds.slice(0, 3), ["name", "contact", "heading"]);
  assert.ok(!kinds.includes("tagline") && !kinds.includes("comp"));
  assert.ok(kinds.includes("expertise") && kinds.includes("tech_line") && kinds.includes("school") && kinds.includes("cert"));
  assert.ok(lib.competencies.length);
});

test("an answer bullet may only state numbers its answer states", () => {
  const { E } = engine();
  const Q = { section: "experience", role: "hal", answer: "We took forecast accuracy from 71% to 93% in two quarters.", question: "?" };
  const good = { text: "Took forecast accuracy from 71% to 93% in two quarters.", role: "hal", engagement: null };
  const bad = { text: "Took forecast accuracy from 71% to 99% in two quarters.", role: "hal", engagement: null };
  assert.deepEqual(E.bulletQa(Q, good), []);
  assert.deepEqual(E.bulletQa(Q, bad), ["numbers not in your answer or the evidence: 99"]);
});
