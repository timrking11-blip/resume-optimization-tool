"use strict";
/* Intake without Claude: the layout heuristic reads the fixture resumes, and the merge plan turns three resumes into one record
   with corroboration and the persona's deliberate conflicts (Kestrel's end date, Pinecrest's title, the pipeline figure). */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { R, ROOT, taxonomy } = require("../lib/riley.js");
const Intake = require(path.join(ROOT, "hub", "intake.js"));

const T = R.createEngine({ bank: { tags: taxonomy.tags }, settings: {} });
const tagsFor = t => Object.fromEntries(Object.keys(T.extractRequirements(t)).map(x => [x, 1]));
const fixture = f => fs.readFileSync(path.join(ROOT, "tests", "fixtures", "persona", f), "utf8");
const propose = f => Intake.check(Intake.heuristic(Intake.linesFromText(fixture(f))), Intake.linesFromText(fixture(f)));
const val = f => f ? (f.resolution ? f.resolution.value : f.value) : null;

test("dates normalise and ranges overlap the way the merge expects", () => {
  assert.equal(Intake.normDate("January 2024"), "2024-01");
  assert.equal(Intake.normDate("Sept 2021"), "2021-09");
  assert.equal(Intake.normDate("03/2021"), "2021-03");
  assert.equal(Intake.normDate("2021"), "2021");
  assert.equal(Intake.normDate("Present"), null);
  assert.equal(Intake.overlap("2021-03", "2023-11", "2021", "2024"), true);
  assert.equal(Intake.overlap("2016-08", "2018-05", "2018-06", "2021-02"), false);
});

test("the layout heuristic reads the classic resume", () => {
  const P = propose("resume_v1_classic.txt");
  assert.equal(P.roles.length, 4);
  const [hal, kes, pin, qui] = P.roles;
  assert.deepEqual([hal.title, hal.employer, hal.location, hal.start, hal.end], ["Director of Revenue Operations", "Halcyon Metrics", "Denver, CO", "2024-01", null]);
  assert.equal(hal.accomplishment_lines.length, 5);
  assert.deepEqual([kes.title, kes.employer, kes.start, kes.end], ["Senior Account Executive", "Kestrel Adtech", "2021", "2024"]);
  assert.deepEqual([pin.title, pin.employer], ["Marketing Manager", "Pinecrest Sports Media"]);
  assert.deepEqual([qui.title, qui.employer, qui.accomplishment_lines.length], ["Sales Development Representative", "Quillstone Software", 2]);
  assert.equal(P.identity.name, "Riley Mahoney");
  assert.equal(P.identity.email, "riley.mahoney@example.com");
  assert.equal(P.education[0].school, "Lakeside State University");
  assert.equal(P.education[0].degree, "B.A., Communication");
  assert.equal(P.education[0].date, "2016");
  assert.ok(P.certifications.some(c => /HubSpot Revenue Operations/.test(c.name)));
  assert.ok(P.tools.map(t => t.name).includes("Salesforce") && P.tools.length >= 8);
  assert.deepEqual(P.roles.flatMap(r => r.flags), []);
});

test("the layout heuristic reads the one-line headers of the media resume", () => {
  const P = propose("resume_v2_media_partnerships.txt");
  assert.equal(P.roles.length, 3);
  assert.deepEqual([P.roles[0].title, P.roles[0].employer, P.roles[0].location, P.roles[0].start], ["Director of Revenue Operations", "Halcyon Metrics", "Denver, CO", "2024-01"]);
  assert.deepEqual([P.roles[1].employer, P.roles[1].start, P.roles[1].end], ["Kestrel Adtech", "2021-03", "2023-11"]);
  assert.equal(P.roles[2].title, "Senior Marketing Manager");
  assert.ok(P.skills.length >= 5 && P.tools.some(t => t.name === "Salesforce"), "skills line splits into skills and tools");
});

test("three resumes merge into one record with corroboration and the planned conflicts", () => {
  let record = { identity: { name: "", location: "", phone: "", email: "", links: [] }, sources: [], evidence: [], subjects: [], achievements: [] };
  const ctx = { today: "2026-09-28", tagsFor, tagList: t => Object.keys(tagsFor(t)) };
  const sums = [];
  for (const [f, kind] of [["resume_v1_classic.txt", "resume"], ["resume_v3_revops.txt", "resume"], ["resume_v2_media_partnerships.txt", "resume"]]) {
    const lines = Intake.linesFromText(fixture(f));
    const P = Intake.check(Intake.heuristic(lines), lines); P.kind = kind;
    const out = Intake.plan(P, lines, record, { ...ctx, label: f });
    sums.push(out.summary);
    record = { identity: out.identity, sources: out.sources, evidence: out.evidence, subjects: out.subjects, achievements: out.achievements };
  }
  const roles = record.subjects.filter(s => s.kind === "role");
  assert.equal(roles.length, 5, "the persona's five roles once, not eleven");
  assert.deepEqual(sums.map(s => [s.roles_new, s.roles_merged]), [[4, 0], [1, 3], [0, 3]], "the third resume adds only the fractional advisory role");
  assert.ok(sums[1].entries_corroborated + sums[2].entries_corroborated >= 4, "the same accomplishments worded differently corroborate");
  const kes = roles.find(s => val(s.facts.employer) === "Kestrel Adtech"), pin = roles.find(s => /Pinecrest/.test(val(s.facts.employer))), hal = roles.find(s => /Halcyon/.test(val(s.facts.employer)));
  assert.equal(val(kes.facts.start), "2021-03", "a finer start date wins over a year");
  assert.ok(kes.facts.end.contradicting.length >= 1, "Kestrel's end date is in conflict (2024 vs 2023-11)");
  assert.ok(pin.facts.title.contradicting.some(c => /Senior Marketing Manager|Marketing Manager/.test(c.value)), "Pinecrest's title is in conflict");
  const pipeline = record.achievements.filter(a => a.role === hal.key && /qualified pipeline/.test(a.canonical));
  assert.equal(pipeline.length, 1, "one pipeline entry");
  assert.ok(pipeline[0].contradicting.length === 1 && /6\.8M/.test(pipeline[0].contradicting[0].value), "the pipeline figure is disputed, not duplicated");
  assert.ok(record.evidence.filter(e => e.channel === "upload:resume").length === 31 + 28 + 24, "every document line is evidence");
  assert.equal(record.identity.name, "Riley Mahoney");
  assert.ok(record.identity.links.some(l => /linkedin\.com\/in\/rileymahoney-example/.test(l.url)));
  // the merged record projects to a bank; disputed facts are held back the way the Desk holds them
  const lib = R.claims.projectLibrary({ schema: "cch-backup/1", ...record, taxonomy: { id: "gtm/1" }, settings: {}, sessions: [], feedback: [], outcomes: [], review_log: [] }, taxonomy, { now: "2026-09-28T00:00:00Z" });
  assert.equal(lib.roles.length, 5);
  assert.ok(!record.subjects.some(s => s.kind === "tool" && /\(admin\)/.test(val(s.facts.name))), "Salesforce (admin) corroborates Salesforce instead of duplicating it");
  assert.ok(lib.claims.some(c => c.id === `ach:${pipeline[0].id}` && c.status === "disputed"));
  const E = R.createEngine({ bank: lib, settings: lib.baseline.settings });
  const d = { req: {}, jd: "", pinned: new Set(), excluded: new Set(), locked: null, textChoice: {}, edits: {}, tagline: null, compOrder: null, sectionEdits: {}, extra: { tagline: [], expertise: [], technology: [], competency: [] }, engDetails: {}, editsC: {}, excludedC: new Set(), newAch: [], inbox: [], adj: {}, summaryOn: false, summary: null, summaryClaims: [], runId: "t", questions: [] };
  Object.assign(d, E.compute(d, d.req));
  assert.ok(!E.resumeModel(d).roles.some(r => r.bullets.some(b => /qualified pipeline/.test(b.text))), "the disputed pipeline figure does not print");
});

test("Claude's reply is validated line by line", () => {
  const lines = Intake.linesFromText("Sam Example\nEXPERIENCE\nHead of Growth | Northwind Labs | 2022 – Present\n- Grew qualified pipeline 38% in two quarters.\n- Short line\nEDUCATION\nState University — B.S., Marketing, 2015");
  const P = Intake.check(Intake.parse({ roles: [{ title: "Head of Growth", employer: "Northwind Labs", start: "2022", end: null, header_lines: [3], accomplishment_lines: [4, 5, 99, "L4"] }, { title: "", employer: "Nowhere" }],
    education: [{ school: "State University", degree: "B.S., Marketing", date: "2015", lines: [7] }], skills: [{ text: "Growth marketing", line: 1 }], tools: [{ name: "HubSpot", line: 4 }, { name: "HubSpot", line: 4 }] }, lines), lines);
  assert.equal(P.roles.length, 1);
  assert.deepEqual(P.roles[0].accomplishment_lines, [4], "a header, a short line, a missing line and a repeat are all dropped");
  assert.deepEqual(P.roles[0].flags, []);
  assert.equal(P.tools.length, 1);
  assert.equal(P.education[0].date, "2015");
  assert.ok(Intake.prompt(lines, "resume").includes("L3: Head of Growth"));
});
