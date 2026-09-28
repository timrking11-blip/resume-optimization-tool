"use strict";
/* The public folders (core/, hub/) must contain nothing about Tim: no names, role keys, contact details or
   confidential client words. The fixture person and the Desk shell are allowed to; the shared engine is not. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..", "..");
const PUBLIC_DIRS = ["core", "hub"];
// Person-specific strings. Keep the list literal so a match is easy to read; add to it when a new literal is spotted.
const PATTERNS = [
  /\bTim\b/, /\bKing\b/, /\bliminal\b/i, /\bhc_ai_strategy\b/, /\bpsp\b/, /\btek_lead\b/, /\btek_recruiter\b/, /\bdemanddrive\b/i,
  /\bnyl\b/, /\bmassdot\b/i, /\byri\b/, /umaine/i, /Professional Sports Publications/, /TEKsystems/, /New York Life/,
  /Strategic Market Insights/, /\b\d{3}-\d{3}-\d{4}\b/, /tim\.r\.king/i, /timrking/i, /Therapy Companion/i, /\bKamal\b/,
];
const TEXT = /\.(js|mjs|json|html|css|md|txt|py)$/;

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out); else if (TEXT.test(e.name)) out.push(p);
  }
  return out;
}

test("core/ and hub/ contain no personal strings", () => {
  const hits = [];
  for (const d of PUBLIC_DIRS) {
    const dir = path.join(ROOT, d);
    if (!fs.existsSync(dir)) continue;
    for (const f of walk(dir)) {
      const lines = fs.readFileSync(f, "utf8").split("\n");
      lines.forEach((line, i) => { for (const re of PATTERNS) if (re.test(line)) hits.push(`${path.relative(ROOT, f)}:${i + 1} ${re} :: ${line.trim().slice(0, 100)}`); });
    }
  }
  assert.deepEqual(hits, [], "personal strings found in public folders:\n" + hits.join("\n"));
});
