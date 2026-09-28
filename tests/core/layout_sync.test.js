"use strict";
/* The source layout exists in three places that must agree: core/layouts/source-2026-09.json (the truth), the copy the
   core embeds as RotCore.layouts.source, and the copy make_template.py writes into templates/docx_template.json. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..", "..");
const R = require(path.join(ROOT, "core", "rot_core.js"));

const strip = o => Object.fromEntries(Object.entries(o).filter(([k]) => !k.startsWith("_")));
const truth = strip(JSON.parse(fs.readFileSync(path.join(ROOT, "core", "layouts", "source-2026-09.json"), "utf8")));

test("the core embeds the source layout exactly", () => {
  assert.deepEqual(R.layouts.source, truth);
});

test("the built template carries the source layout", () => {
  const tpl = JSON.parse(fs.readFileSync(path.join(ROOT, "templates", "docx_template.json"), "utf8"));
  assert.deepEqual(tpl.layout, truth);
});
