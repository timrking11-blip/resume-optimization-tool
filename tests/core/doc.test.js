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

test("docxParts keeps rot.py's part order and stamps only core.xml", () => {
  const tpl = require(path.resolve(__dirname, "..", "..", "templates", "docx_template.json"));
  const parts = R.doc.docxParts(MODEL, tpl, "2026-01-01T00:00:00Z");
  const names = Object.keys(parts);
  assert.deepEqual(names.slice(0, 4), ["[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/_rels/document.xml.rels"]);
  assert.equal(names[names.length - 1], "docProps/core.xml");
  assert.ok(parts["docProps/core.xml"].includes("2026-01-01T00:00:00Z") && parts["docProps/core.xml"].includes("Test Person"));
  assert.ok(parts["word/_rels/document.xml.rels"].includes("https://example.com/in/t"));
  assert.equal(names.length, Object.keys(tpl.parts).length + 3);
});

test("plainText and xmlEsc", () => {
  const txt = R.doc.plainText(MODEL);
  assert.ok(txt.includes("PROFESSIONAL EXPERIENCE") && txt.includes("• Rebuilt the forecast."));
  assert.equal(R.doc.xmlEsc('a<b&"c"'), "a&lt;b&amp;&quot;c&quot;");
});
