/* RotCore 1.0.0: the shared engine behind the Resume Match Desk and Career Companion Hub.
   Pure JavaScript: no DOM, no storage, no capabilities and no person. A shell (artifact/index.html, hub/) passes a bank
   (rot-library/3), a template (rot-docx-template/1) and its own state. Loads as a classic script (window.RotCore) and as a
   Node module (module.exports) for the tests. Keep model_paragraphs() and docx_bytes() in rot.py in step with doc.*. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.RotCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
"use strict";
const VERSION = "1.0.0";
const SCHEMAS = { bank: "rot-library/3", model: "rot-resume/2", template: "rot-docx-template/1", backup: "cch-backup/1", taxonomy: "rot-taxonomy/1" };

/* ------------------------------ util ------------------------------ */
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const escRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const fmtDate = v => !v ? "Present" : (/^\d{4}-\d{2}$/.test(v) ? `${MONTHS[+v.slice(5)-1]} ${v.slice(0,4)}` : v);
const REQ_HINT = /(require|qualif|must|you have|you bring|what you.ll need|experience with|proven|track record|responsib|you will|what you.ll do|preferred|bonus|nice to have)/i;
const uniq = a => { const seen=new Set(), out=[]; for(const x of a){ const k=norm(x); if(x && !seen.has(k)){ seen.add(k); out.push(x); } } return out; };
function norm(t){ return String(t||"").toLowerCase().replace(/[^a-z0-9]/g,""); }
/* split a line on its separator, but never inside parentheses: "Salesforce (Classic, Lightning), Canva" -> 2 items */
function splitList(s, seps){
  const out=[]; let depth=0, cur="";
  for(const ch of String(s||"")){ if(ch==="(") depth++; if(ch===")") depth=Math.max(0,depth-1);
    if(depth===0 && seps.includes(ch)){ if(cur.trim()) out.push(cur.trim()); cur=""; } else cur+=ch; }
  if(cur.trim()) out.push(cur.trim());
  return out;
}
/* Template sections (TIM KING SOURCE RESUME.docx): A = tagline, B = areas-of-expertise line, C = consulting
   engagements (long-form bullets), D = core competencies. A question's "section" says which store its answer feeds. */
const PHRASE_SECTIONS = {
  tagline:{label:"Tagline · Section A", max:60, sep:"|", hint:"A short identity phrase, e.g. Revenue Operations Builder. Several are fine, one per line."},
  expertise:{label:"Expertise line · Section B", max:70, sep:"•", hint:"A skill as it should appear on the expertise line, e.g. Partner Ecosystem Development."},
  technology:{label:"Technologies", max:90, sep:",", hint:"The tools you've used, as a resume lists them, e.g. Salesforce Apex (basic). Write no if you haven't used them."},
  competency:{label:"Core competencies · Section D", max:80, sep:",", hint:"A short lowercase phrase for a Section D category, e.g. partner enablement."}
};
/* Tools a posting may name; used to ask whether you've used ones your template doesn't list yet (proper nouns, matched case-sensitively) */
const TOOL_LEXICON = ["Salesforce","HubSpot","Marketo","Pardot","Outreach.io","Salesloft","Gong","Clari","Apollo","ZoomInfo","6sense","Demandbase","Sales Navigator","Tableau","Looker","Power BI","SQL","Python","Snowflake","dbt","BigQuery","Amplitude","Mixpanel","Google Analytics","GA4","Google Ads","Meta Ads","LinkedIn Ads","The Trade Desk","DV360","Jira","Asana","Notion","Airtable","Zapier","n8n","Clay","Apex","Gainsight","Zendesk","Intercom","Braze","Iterable","Klaviyo","Figma","Canva","Miro","Excel","PowerPoint","ClickUp","Workday","NetSuite","SAP","Oracle","AWS","Azure","GCP","Databricks","ChatGPT","Claude","Copilot","Gemini","Perplexity","Cursor","GitHub","Seismic","Highspot","DocuSign","PandaDoc","Chili Piper","Lusha","Crunchbase","PitchBook","Nielsen","Comscore","LiveRamp","AppsFlyer","Adobe Analytics","Optimizely","Segment.io","Looker Studio","Trello","Slack","Webflow","WordPress","Squarespace","Google Tag Manager"];
function isSkip(a){ return !a || /^(no|n\/a|none|nothing|skip|-|—|not really|haven'?t)\.?$/i.test(a.trim()); }
function cleanBullet(t){ t=String(t).replace(/^[\s•·\-*–—\d.)]+/,"").replace(/\s+/g," ").trim(); if(!t) return ""; t=t.charAt(0).toUpperCase()+t.slice(1); if(!/[.!?]$/.test(t)) t+="."; return t; }
function cleanPhrase(t, sec){ t=String(t).replace(/^[\s•·\-*–—\d.)]+/,"").replace(/\s+/g," ").trim().replace(/[.;,]+$/,""); if(sec==="tagline"||sec==="expertise") t=t.charAt(0).toUpperCase()+t.slice(1); return t.slice(0,(PHRASE_SECTIONS[sec]||{max:90}).max); }
function splitAnswer(a){ let parts=String(a).split(/\r?\n+/); if(parts.length===1) parts=String(a).split(/\s+[•·]\s+|;\s+/); return parts.map(cleanBullet).filter(s=>s.length>12); }
function splitPhrases(a, sec){ if(isSkip(a)) return []; return String(a).split(/\r?\n+|;|,(?![^(]*\))/).map(x=>cleanPhrase(x,sec)).filter(x=>x.length>1 && !isSkip(x)); }
function shortRole(r){
  const emp = r.employer.replace(/ \(self-employed\)$/,"").replace(/ \(.*\)$/,"").split(" / ").pop().replace(/ Insurance Company$/,"");
  const title = r.title.split(/ [-–] |,|\//)[0].trim();
  return `${emp} · ${title}`;
}
function sectionOf(q){ return q.section || "experience"; }
/* Where an answer bullet prints: under a role (Professional Experience) or a consulting engagement (Section C).
   Every bullet keeps its own place, because one answer can draw on several jobs. Places read "r:<role>" or "e:<engagement>". */
const placeKey = p => p.engagement ? "e:"+p.engagement : "r:"+p.role;

/* ------------------------------ qa: numbers, first person, bands (mirrors claims.py number_tokens / check_line) ------------------------------ */
const NUMBER_WORDS={one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,eleven:11,twelve:12,fifteen:15,twenty:20,thirty:30,forty:40,fifty:50,hundred:100,half:50,dozen:12};
function numberTokens(text){
  const out=new Set(), t=String(text||"");
  for(const m of t.matchAll(/\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|hundred|half|dozen)\b/gi)) out.add(String(NUMBER_WORDS[m[1].toLowerCase()]));
  for(const m of t.matchAll(/(?<![A-Za-z])~?\$?(\d[\d,]*(?:\.\d+)?)\s*(K\b|M\b|MM\b|B\b|thousand|million|billion)?(?![A-Za-z])/gi)){
    let v=parseFloat(m[1].replace(/,/g,"")); if(isNaN(v)) continue;
    v*=({K:1e3,M:1e6,MM:1e6,B:1e9,THOUSAND:1e3,MILLION:1e6,BILLION:1e9})[(m[2]||"").toUpperCase()]||1;
    out.add(Math.abs(v-Math.round(v))<1e-9?String(Math.round(v)):Number(v.toPrecision(4)).toString());
  }
  return out;
}
const FIRST_PERSON=/\b(I(?!\.[A-Z])|I'm|I've|I'd|me|my|mine|we|our|us)\b/;
/* A line may only state numbers that its claims' evidence or your own answer states. */
function qaLine(text, claimIds, quotes, band, lookup){
  const issues=[], allowed=new Set(); let anyBasis=false;
  for(const id of claimIds||[]){ const c=lookup?lookup(id):null; if(!c) continue; anyBasis=true; if(c.status==="disputed") issues.push(`disputed claim ${id}`); for(const n of c.numbers||[]) allowed.add(n); }
  for(const q of quotes||[]){ if(q){ anyBasis=true; for(const n of numberTokens(q)) allowed.add(n); } }
  const missing=[...numberTokens(text)].filter(n=>!allowed.has(n)).sort((a,b)=>+a-+b);
  if(missing.length && anyBasis) issues.push("numbers not in your answer or the evidence: "+missing.join(", "));
  if(FIRST_PERSON.test(text||"")) issues.push("first person");
  if(band && (text||"").length>band.hard_ceiling) issues.push(`${text.length} chars > ${band.hard_ceiling}`);
  return issues;
}
const blocking = qa => (qa||[]).filter(x=>!/chars >/.test(x));
function answerQuotes(Q){ return Q ? [Q.answer||""].concat(Q.fields?[Object.values(Q.fields).filter(Boolean).join("; ")]:[]) : []; }

/* ------------------------------ scoring helpers (mirror rot.py coverage / rank_items) ------------------------------ */
function coverage(req, chosen){
  const cov={};
  for(const tid of Object.keys(req)){ let best=0; for(const items of Object.values(chosen)) for(const i of items) if(i.a.tags[tid]) best=Math.max(best,i.a.tags[tid]); cov[tid]=best; }
  return cov;
}
function matchScore(req,cov){ const tot=Object.values(req).reduce((a,r)=>a+r.weight,0)||1; return Object.entries(req).reduce((a,[t,r])=>a+r.weight*Math.min(cov[t]||0,1),0)/tot; }
const tagWeight = (tags, req) => (tags||[]).reduce((a,t)=>a+(req[t]?.weight||0),0);
function rankByTags(items, req){ if(!Object.keys(req).length) return [...items]; return items.map((it,i)=>({it,i,s:tagWeight(it.tags,req)})).sort((a,b)=>(b.s-a.s)||(a.i-b.i)).map(x=>x.it); }

/* ------------------------------ documents: paragraphs, Word XML, PDF metrics, plain text (mirror rot.py model_paragraphs / docx_bytes) ------------------------------ */
const btext = b => typeof b==="string" ? b : b.text;
/* The resume as [kind, runs] paragraphs. Mirrors model_paragraphs() in rot.py, so the page and the CLI build the same document.
   A run is [style, text], ["tab"], or ["link", label, url]. */
function docParagraphs(m){
  const i=m.identity, P=[];
  P.push(["name",[["name",i.name]]]);
  const contact=[["contact",`${i.location} | ${i.phone} | ${i.email}`+((i.links||[]).length?" | ":"")]];
  (i.links||[]).forEach((ln,k)=>{ if(k) contact.push(["contact"," | "]); contact.push(["link",ln.label,ln.url]); });
  P.push(["contact",contact]);
  P.push(["heading",[["heading","Professional Summary & Areas of Expertise"]]]);
  if(m.summary) P.push(["summary",[["plain",m.summary]]]);
  if(m.tagline.length) P.push(["tagline",[["plain",m.tagline.join(" | ")]]]);
  if(m.expertise.length) P.push(["expertise",[["plain",m.expertise.join(" • ")]]]);
  if(m.technologies.length){ P.push(["tech_label",[["bold_u","Technologies"],["bold",":"]]]); P.push(["tech_line",[["plain",m.technologies.join(", ")]]]); }
  if(m.education.length){ P.push(["heading",[["heading","Education"]]]); for(const e of m.education){ P.push(["school",[["bold",e.school]]]); P.push(["degree",[["degree",e.degree_line]]]); for(const b of e.bullets||[]) P.push(["bullet",[["plain",btext(b)]]]); } }
  P.push(["heading",[["heading","Professional Experience"]]]);
  for(const r of m.roles){
    P.push(["role_header",[["bold",`${r.title} | ${r.employer} |`],["tab"],["plain",r.dates]]]);
    if(r.context) P.push(["role_context",[["context",r.context]]]);
    r.bullets.forEach((b,k)=>P.push([k===r.bullets.length-1?"bullet_last":"bullet",[["plain",btext(b)]]]));
  }
  if(m.certifications.length){ P.push(["heading",[["heading","Credentialing & Certifications"]]]);
    for(const c of m.certifications){ const runs=[["bold",c.name],["plain",` — ${c.issuer}`]]; if(c.note) runs.push(["cert_note",` (${c.note})`]); P.push(["cert",runs]); } }
  if(m.engagements.length){ P.push(["heading",[["heading","Business Consulting Engagements"]]]);
    for(const e of m.engagements){
      const runs=[["bold",e.client]];
      if(e.location) runs.push(["bold_italic",` | ${e.location} |`]);
      if(e.dates) runs.push(["bold",(e.location?" ":" | ")+e.dates]);
      if(e.commitment) runs.push(["plain",` (${e.commitment})`]);
      P.push(["eng_header",runs]);
      if(e.subtitle) P.push(["eng_subtitle",[["italic",e.subtitle]]]);
      e.bullets.forEach((b,k)=>P.push([k===e.bullets.length-1?"eng_bullet_last":"eng_bullet",[["plain",btext(b)]]]));
    } }
  if(m.core_competencies.length){ P.push(["heading",[["heading","Core Competencies"]]]);
    for(const a of m.core_competencies) P.push(["comp",[["bold",a.label+": "],["plain",a.items.join(", ")]]]); }
  return P;
}
function xmlEsc(s){ return String(s??"").replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g,"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }
function rprXml(style, tpl){ const f=tpl.styles[style]||{}; let x=f.link?'<w:rStyle w:val="Hyperlink"/>':'';
  x+='<w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi" w:cstheme="majorHAnsi"/>';
  if(f.b) x+='<w:b/><w:bCs/>'; if(f.i) x+='<w:i/><w:iCs/>'; if(f.color) x+=`<w:color w:val="${f.color}"/>`;
  if(f.sz) x+=`<w:sz w:val="${f.sz}"/><w:szCs w:val="${f.sz}"/>`; if(f.u) x+='<w:u w:val="single"/>';
  return `<w:rPr>${x}</w:rPr>`; }
function documentXml(m, tpl){
  const links=[], body=[];
  for(const [kind,runs] of docParagraphs(m)){
    let out="";
    for(const r of runs){
      if(r[0]==="tab") out+=`<w:r>${rprXml("plain",tpl)}<w:tab/></w:r>`;
      else if(r[0]==="link"){ const rid=`rId${100+links.length}`; links.push([rid,r[2]]); out+=`<w:hyperlink r:id="${rid}" w:history="1"><w:r>${rprXml("link",tpl)}<w:t xml:space="preserve">${xmlEsc(r[1])}</w:t></w:r></w:hyperlink>`; }
      else out+=`<w:r>${rprXml(r[0],tpl)}<w:t xml:space="preserve">${xmlEsc(r[1])}</w:t></w:r>`;
    }
    body.push(`<w:p>${tpl.ppr[kind]}${out}</w:p>`);
  }
  return {xml:tpl.doc_open+body.join("")+tpl.doc_close, links};
}
/* Helvetica (fallback when the fonts can't load) only draws Latin-1; map typographic punctuation so nothing is silently dropped */
function pdfSafe(s){ return String(s)
  .replace(/[–—−]/g,"-").replace(/[‘’′]/g,"'").replace(/[“”″]/g,'"')
  .replace(/…/g,"...").replace(/•/g,"-").replace(/≥/g,">=").replace(/≤/g,"<=").replace(/→/g,"->")
  .replace(/[   ]/g," ").replace(/[^\x00-\xFF]/g,""); }
function abToB64(buf){ let s=""; const b=new Uint8Array(buf); for(let i=0;i<b.length;i+=0x8000) s+=String.fromCharCode.apply(null,b.subarray(i,i+0x8000)); return btoa(s); }
const PDF_METRICS={font:"Calibri", size:10, single:1.2207, ascent:0.9521, hyperlink:"#0000FF", page:{width:612,height:792,top:36,bottom:36,left:45,right:45},
  space:{name:2,contact:10,heading_before:12,heading_after:5,rule_gap:2,rule_width:0.75,tagline:5,school:1,degree:5,context:5,bullet_last:12,cert:2,eng_header:4,eng_subtitle:4,eng_bullet:2,eng_bullet_last:8},
  line:{context:1.15,list:250/240}, indent:{experience:{left:18,hanging:18,glyph:"•"},certs:{left:15.1,hanging:10.75,glyph:"•"},engagements:{left:15.1,hanging:10.75,glyph:"•"},competencies:{left:18,hanging:18,glyph:"•"}},
  colors:{rule:"#999999"}};
function plainText(m){
  const i=m.identity; const L=[i.name, `${i.location} | ${i.phone} | ${i.email}`+((i.links||[]).length?" | "+(i.links||[]).map(l=>`${l.label}: ${l.url}`).join(" | "):""), "",
    "PROFESSIONAL SUMMARY & AREAS OF EXPERTISE"].concat(m.summary?[m.summary,""]:[]).concat([m.tagline.join(" | "), "", m.expertise.join(" • "), "", "Technologies: "+m.technologies.join(", "), "", "EDUCATION"]);
  m.education.forEach(e=>L.push(e.school, e.degree_line));
  L.push("", "PROFESSIONAL EXPERIENCE");
  for(const r of m.roles){ L.push(`${r.title} | ${r.employer} | ${r.dates}`, r.context||""); r.bullets.forEach(b=>L.push("• "+btext(b))); L.push(""); }
  L.push("CREDENTIALING & CERTIFICATIONS", ...m.certifications.map(c=>`• ${c.name} — ${c.issuer}${c.note?` (${c.note})`:""}`));
  if(m.engagements.length){ L.push("", "BUSINESS CONSULTING ENGAGEMENTS"); for(const e of m.engagements){ L.push(`${e.client}${e.location?` | ${e.location} |`:""}${e.dates?` ${e.dates}`:""}${e.commitment?` (${e.commitment})`:""}`); if(e.subtitle) L.push(e.subtitle); e.bullets.forEach(b=>L.push("• "+btext(b))); L.push(""); } }
  L.push("CORE COMPETENCIES", ...m.core_competencies.map(a=>`• ${a.label}: ${a.items.join(", ")}`));
  return L.join("\n");
}

return {
  VERSION, SCHEMAS,
  util: { esc, escRe, MONTHS, fmtDate, REQ_HINT, uniq, norm, splitList, PHRASE_SECTIONS, TOOL_LEXICON, isSkip, cleanBullet, cleanPhrase, splitAnswer, splitPhrases, shortRole, sectionOf, placeKey },
  qa: { NUMBER_WORDS, numberTokens, FIRST_PERSON, qaLine, blocking, answerQuotes },
  score: { coverage, matchScore, tagWeight, rankByTags },
  doc: { btext, docParagraphs, xmlEsc, rprXml, documentXml, plainText, pdfSafe, abToB64, PDF_METRICS },
};
});
