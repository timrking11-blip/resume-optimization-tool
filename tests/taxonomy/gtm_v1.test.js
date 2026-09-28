"use strict";
/* GTM taxonomy v1: well-formed, no synonym in two tags, and each persona posting surfaces the tags a reader would expect. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { R, ROOT, taxonomy, postings } = require("../lib/riley.js");

test("the taxonomy is well formed", () => {
  assert.equal(taxonomy.version, "gtm/1");
  const owner = {};
  for (const [tid, t] of Object.entries(taxonomy.tags)) {
    assert.ok(taxonomy.families[t.family], `${tid}: unknown family ${t.family}`);
    assert.ok(t.synonyms.length >= 3, `${tid}: fewer than 3 synonyms`);
    for (const s of t.synonyms) {
      assert.equal(s, s.toLowerCase(), `${tid}: ${s}`);
      assert.ok(!owner[s], `'${s}' is in ${owner[s]} and ${tid}`);
      owner[s] = tid;
    }
  }
  assert.ok(Object.keys(taxonomy.tags).length >= 90);
  const priv = JSON.parse(fs.readFileSync(path.join(ROOT, "curation", "taxonomy.json"), "utf8"));
  assert.equal(Object.keys(priv.tags).length, 84, "the private taxonomy is untouched by the derivation");
});

test("each persona posting surfaces its expected tags", () => {
  const T = R.createEngine({ bank: { tags: taxonomy.tags }, settings: {} });
  const expect = {
    "01": ["crm-discipline", "lead-routing-sla", "revenue-analytics", "tech-stack-consolidation", "pricing-packaging", "forecasting"],
    "02": ["media-ad-sales", "retail-media", "adtech-fluency", "discovery", "executive-selling", "cpm-cpa-modeling"],
    "03": ["audience-growth", "budget-ownership", "lifecycle-email", "paid-media", "audience-measurement"],
    "04": ["channel-strategy", "strategic-partnerships", "retail-media", "media-ad-sales"],
    "05": ["gtm-strategy", "market-segmentation", "pricing-packaging", "stakeholder-alignment", "positioning-messaging", "discovery", "executive-advisory"],
  };
  const present = { "04": ["partner-enablement", "partner-recruitment"] };
  for (const [k, ids] of Object.entries(expect)) {
    const req = T.extractRequirements(postings[k]);
    const top = Object.entries(req).sort((a, b) => b[1].weight - a[1].weight).slice(0, 10).map(([t]) => t);
    for (const id of ids) assert.ok(top.includes(id), `posting ${k}: ${id} not in top 10 (${top.join(", ")})`);
    for (const id of present[k] || []) assert.ok(req[id], `posting ${k}: ${id} not detected`);
  }
});
