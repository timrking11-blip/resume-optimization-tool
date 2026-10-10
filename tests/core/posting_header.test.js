"use strict";
/* postingHeader: the company and role title a posting states near its top, for the Company and Role title fields. */
const test = require("node:test");
const assert = require("node:assert/strict");
const { R, postings } = require("../lib/riley.js");
const H = R.util.postingHeader;

test("the fixture postings: a title line over 'Company · Location · Full-time'", () => {
  assert.deepEqual(H(postings["01"]), { company: "Northgate Software", title: "Director, Revenue Operations" });
  assert.deepEqual(H(postings["02"]), { company: "Cobalt Commerce Media", title: "Senior Account Executive, Retail Media" });
  assert.deepEqual(H(postings["03"]), { company: "Fernwood", title: "Head of Growth Marketing" });
  assert.deepEqual(H(postings["04"]), { company: "Sable Signals", title: "Partnerships Manager, Agency & Channel" });
  assert.deepEqual(H(postings["05"]), { company: "Orbit Labs", title: "GTM Strategy Lead" });
});

test("common paste formats", () => {
  assert.deepEqual(H("Account Executive at Gong\nSan Francisco, CA · Remote\n\nAbout the role\nYou will sell."), { company: "Gong", title: "Account Executive" });
  assert.deepEqual(H("Ramp\nSenior Revenue Operations Manager\nNew York, NY · 2 weeks ago · 120 applicants\nEasy Apply"), { company: "Ramp", title: "Senior Revenue Operations Manager" });
  assert.deepEqual(H("Company: Acme Corp\nJob Title: Head of Partnerships\nLocation: Remote"), { company: "Acme Corp", title: "Head of Partnerships" });
  assert.deepEqual(H("Stripe is hiring a Partnerships Manager to grow our ecosystem.\nWhat you'll do"), { company: "Stripe", title: "Partnerships Manager" });
  assert.deepEqual(H("Senior Account Executive - Gong\nRemote (US)"), { company: "Gong", title: "Senior Account Executive" });
  assert.deepEqual(H("Growth Marketing Lead | Fernwood | Remote (US)\nFull-time"), { company: "Fernwood", title: "Growth Marketing Lead" });
  assert.deepEqual(H("Enterprise Account Executive — Brightline Labs\nChicago, IL"), { company: "Brightline Labs", title: "Enterprise Account Executive" });
  assert.deepEqual(H("About the role\nAt Lumen Health, we build clinic software. We are hiring a Sales Director to lead our team."), { company: "Lumen Health", title: "Sales Director" });
});

test("LinkedIn's job-page paste: logo line, company, title, then a long preamble", () => {
  assert.deepEqual(H("Company logo for, Northwind.\nNorthwind\n\n\nGrowth Lead, IT \n\nNew York, NY · 1 week ago · 19 people clicked apply\n\nPromoted by hirer\n\nOn-site\nFull-time\nApply\n\nSave\nAbout the job\nAbout Northwind"),
    { company: "Northwind", title: "Growth Lead, IT" });
  const pre = "Vice President, Sales Strategy - Platform and Data \n\nNew York, NY · Reposted 1 week ago · Over 100 people clicked apply\n\nHybrid\nFull-time\nApply\nSave\n"
    + Array.from({ length: 12 }, (_, i) => `Premium prompt ${i}`).join("\n") + "\nAbout the job\nJob Category\nOperations\nAbout Contoso\nContoso is a cloud company.";
  assert.deepEqual(H(pre), { company: "Contoso", title: "Vice President, Sales Strategy - Platform and Data" });
});

test("a dash that continues the title is not mistaken for the employer, and prose yields nothing", () => {
  assert.deepEqual(H("Director, Go-To-Market — Advertiser Partnerships\nNew York, NY (Hybrid)\n\nAbout the role\nWe are an AI-native ad-tech company."),
    { company: "", title: "Director, Go-To-Market — Advertiser Partnerships" });
  assert.deepEqual(H("We make great things for great people.\nJoin us."), { company: "", title: "" });
  assert.deepEqual(H(""), { company: "", title: "" });
});
