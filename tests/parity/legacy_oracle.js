#!/usr/bin/env node
"use strict";
/* Golden oracle for the Resume Match Desk page (artifact/index.html).

   node tests/parity/legacy_oracle.js --write [--source <git ref>]   record goldens from that ref's page (default: HEAD)
   node tests/parity/legacy_oracle.js --check [--source <git ref>]   run the page (working tree by default) and compare
   node tests/parity/legacy_oracle.js --list                          show the cases

   The page runs inside Node's vm with tests/lib/dom_stub.js: no fetch and no window.claude, so start() returns early;
   the oracle then sets the bank and template and drives the page's own functions. Every case records the resume model,
   the Word document XML, the plain text and (for sample_jd) the questions and the Claude prompts. Cases:
     baseline    the bank with no posting
     sample_jd   the built-in sample posting, keyword-matched, template questions, tailor and bullets prompts
     run-<id>    every finalized run under sync/dump/jd_runs (Tim's data: goldens stay local, see .gitignore)
   Local <script src> files named by the page (the shared core, from Phase 1 on) are evaluated first, in order. */
const fs = require("fs"), path = require("path"), vm = require("vm"), cp = require("child_process");
const { makeWindow } = require("../lib/dom_stub.js");

const ROOT = path.resolve(__dirname, "..", "..");
const GOLD = path.join(__dirname, "golden");
const args = process.argv.slice(2);
const flag = k => args.includes(k);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] && !args[i + 1].startsWith("--") ? args[i + 1] : d; };
const REF = opt("--source", null), ONLY = opt("--only", null);
const ANSWER = "Rebuilt the renewal pipeline for the division and closed four new partnerships in one season.";

function gitShow(ref, file) { return cp.execFileSync("git", ["show", `${ref}:${file}`], { cwd: ROOT, encoding: "utf8", maxBuffer: 64 << 20 }); }
function readRepo(ref, file) { return ref ? gitShow(ref, file) : fs.readFileSync(path.join(ROOT, file), "utf8"); }
function pageScripts(ref) {
  const html = readRepo(ref, "artifact/index.html");
  const scripts = [];
  for (const m of html.matchAll(/<script\s+src="([^"]+)"[^>]*><\/script>/g)) {
    const src = m[1];
    if (/^https?:/.test(src)) continue;   // CDN libraries (JSZip, jsPDF) are not needed for the model or document.xml
    let code = null;
    for (const cand of [`artifact/${src}`, src]) { try { code = readRepo(ref, cand); break; } catch { /* try the next location */ } }
    if (code == null) throw new Error(`local script not found: ${src}`);
    scripts.push({ name: src, code });
  }
  const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].pop();
  if (!inline) throw new Error("no inline script in artifact/index.html");
  scripts.push({ name: "index.html", code: inline[1] });
  return scripts;
}

function boot(scripts, libText, tplText) {
  const win = makeWindow();
  const ctx = vm.createContext(win);
  for (const s of scripts) vm.runInContext(s.code, ctx, { filename: s.name });
  const P = name => vm.runInContext(name, ctx);          // top-level const/function bindings of the page script
  const parse = P("JSON.parse");                          // objects created in the page's realm
  const S = P("S");
  S.lib = parse(libText); S.tpl = parse(tplText);
  return { ctx, P, S, parse };
}

function outputs(P, S, extra = {}) {
  const model = P("resumeModel")();
  const out = { "model.json": JSON.stringify(model, null, 1) + "\n", "document.xml": P("documentXml")(model, S.tpl).xml, "text.txt": P("plainText")(model) + "\n" };
  for (const [k, v] of Object.entries(extra)) if (v != null) out[k] = typeof v === "string" ? v : JSON.stringify(v, null, 1) + "\n";
  return out;
}

const cases = {
  async baseline({ P, S }) { P("recompute")(); return outputs(P, S); },
  async sample_jd({ P, S }) {
    const SAMPLE = P("SAMPLE_JD");
    S.jd = SAMPLE; S.req = P("extractRequirements")(SAMPLE); S.phase = "draft"; P("recompute")();
    S.questions = P("templateQuestions")();
    const cap = {};
    S.sample = { json: async prompt => { cap.last = prompt; const e = new Error("cancelled"); e.code = "cancelled"; throw e; } };
    await P("claudeTailor")();
    const tailor = cap.last; cap.last = null;
    const items = S.questions.map((q, ix) => ({ ...q, ix })).filter(q => (q.section || "experience") === "experience").slice(0, 2).map(q => ({ ...q, answer: ANSWER }));
    try { await P("claudeBullets")(items, new AbortController()); } catch { /* the stub throws after recording the prompt */ }
    return outputs(P, S, { "questions.json": S.questions, "prompt_tailor.txt": tailor, "prompt_bullets.txt": cap.last });
  },
};
function runCases() {
  const dir = path.join(ROOT, "sync", "dump", "jd_runs");
  if (!fs.existsSync(dir)) return {};
  const inbox = readDump("bullet_inbox"), feedback = readDump("feedback");
  const out = {};
  for (const f of fs.readdirSync(dir).filter(f => f.endsWith(".json")).sort()) {
    const id = f.replace(/\.json$/, ""), runText = fs.readFileSync(path.join(dir, f), "utf8");
    if (!/"final_resume"/.test(runText)) continue;
    const name = `run-${id.replace(/^run-/, "")}`;
    const replay = fresh => async ({ P, S, parse }) => {
      const run = parse(runText);
      if (fresh) { delete run.synced_map; }   // as the page saw it before the sync: answer bullets are still fresh, placed per bullet
      S.inbox = parse(JSON.stringify(fresh ? inbox.map(b => ({ ...b, synced: false })) : inbox)); S.adj = {};
      for (const fb of feedback) { const k = fb.bullet_id; if (k == null || fb.synced) continue; S.adj[k] = (S.adj[k] || 0) + (fb.action === "keep" ? 0.3 : (fb.action === "drop" || fb.action === "reject") ? -0.6 : 0); }
      const st = P("sessionFromRun")({ _id: id, ...run });
      P("restoreState")(st);
      return outputs(P, S);
    };
    out[name] = replay(false);
    if (/"new_bullets":\s*\[\s*\{/.test(runText)) out[`${name}-fresh`] = replay(true);
  }
  return out;
}
function readDump(coll) {
  const dir = path.join(ROOT, "sync", "dump", coll);
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f => f.endsWith(".json")).sort().map(f => ({ _id: f.replace(/\.json$/, ""), ...JSON.parse(fs.readFileSync(path.join(dir, f), "utf8")) }));
}

function firstDiff(a, b) {
  const A = a.split("\n"), B = b.split("\n");
  for (let i = 0; i < Math.max(A.length, B.length); i++) if (A[i] !== B[i]) return { line: i + 1, expected: A[i] ?? "<end>", actual: B[i] ?? "<end>" };
  return null;
}

async function main() {
  const all = { ...cases, ...runCases() };
  if (flag("--list")) { console.log(Object.keys(all).join("\n")); return; }
  const mode = flag("--write") ? "write" : "check";
  const scripts = pageScripts(REF);
  const libText = fs.readFileSync(path.join(ROOT, "data", "library.json"), "utf8");
  const tplText = fs.readFileSync(path.join(ROOT, "templates", "docx_template.json"), "utf8");
  let failures = 0, files = 0;
  for (const [name, fn] of Object.entries(all)) {
    if (ONLY && name !== ONLY) continue;
    const env = boot(scripts, libText, tplText);
    const out = await fn(env);
    const dir = path.join(GOLD, name);
    if (mode === "write") {
      fs.mkdirSync(dir, { recursive: true });
      for (const [f, text] of Object.entries(out)) { fs.writeFileSync(path.join(dir, f), text, "utf8"); files++; }
      console.log(`wrote ${name}: ${Object.keys(out).join(", ")}`);
    } else {
      for (const [f, text] of Object.entries(out)) {
        const gp = path.join(dir, f); files++;
        if (!fs.existsSync(gp)) { failures++; console.log(`MISSING ${name}/${f} (run --write first)`); continue; }
        const want = fs.readFileSync(gp, "utf8");
        if (want === text) continue;
        failures++; const d = firstDiff(want, text);
        console.log(`FAIL ${name}/${f} at line ${d.line}\n  expected: ${d.expected.slice(0, 160)}\n  actual:   ${d.actual.slice(0, 160)}`);
      }
    }
  }
  if (mode === "check") { console.log(failures ? `${failures} of ${files} golden files differ` : `parity OK: ${files} golden files identical`); process.exitCode = failures ? 1 : 0; }
}
main().catch(e => { console.error(e); process.exitCode = 2; });
