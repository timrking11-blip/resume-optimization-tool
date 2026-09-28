"use strict";
/* The document builders: paragraph kinds in the source template's order, well-formed Word XML, plain text. */
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const R = require(path.resolve(__dirname, "..", "..", "core", "rot_core.js"));

const MODEL = {
  identity: { name: "Test Person", location: "Denver, CO", phone: "(555) 010-0000", email: "t@example.com", links: [{ label: "LinkedIn", url: "https://example.com/in/t" }] },
  summary: null, tagline: ["Revenue Operations Leader", "Process Builder"], expertise: ["Forecasting", "Pricing & Packaging"], technologies: ["Salesforce", "Looker"],
  education: [{ school: "Lakeside State University", degree_line: "B.A., Communication | 2016", bullets: [] }],
  roles: [{ title: "Director of Revenue Operations", employer: "Halcyon Metrics", dates: "January 2024 – Present", context: "Denver, CO", bullets: ["Rebuilt the forecast.", { text: "Consolidated three CRMs." }] }],
  certifications: [{ name: "HubSpot Revenue Operations Certification", issuer: "HubSpot", note: null }],
  engagements: [], core_competencies: [{ label: "Systems", items: ["Salesforce", "Looker"] }],
};

test("docParagraphs follows the source template's section order", () => {
  const kinds = R.doc.docParagraphs(MODEL).map(p => p[0]);
  assert.deepEqual(kinds, ["name", "contact", "heading", "tagline", "expertise", "tech_label", "tech_line", "heading", "school", "degree",
    "heading", "role_header", "role_context", "bullet", "bullet_last", "heading", "cert", "heading", "comp"]);
  const withSummary = R.doc.docParagraphs({ ...MODEL, summary: "A paragraph." }).map(p => p[0]);
  assert.equal(withSummary[3], "summary");
});

test("documentXml wraps the body in the template's document and reports the hyperlinks", () => {
  const tpl = require(path.resolve(__dirname, "..", "..", "templates", "docx_template.json"));
  const { xml, links } = R.doc.documentXml(MODEL, tpl);
  assert.ok(xml.startsWith(tpl.doc_open) && xml.endsWith(tpl.doc_close));
  assert.equal(links.length, 1);
  assert.equal(links[0][1], "https://example.com/in/t");
  assert.ok(xml.includes("Consolidated three CRMs."));
  assert.ok(!xml.includes("undefined"));
});

test("plainText and xmlEsc", () => {
  const txt = R.doc.plainText(MODEL);
  assert.ok(txt.includes("PROFESSIONAL EXPERIENCE") && txt.includes("• Rebuilt the forecast."));
  assert.equal(R.doc.xmlEsc('a<b&"c"'), "a&lt;b&amp;&quot;c&quot;");
});
