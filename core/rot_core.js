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
const VERSION = "1.1.0";
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
/* Section order and headings of a template (rot-layout/1). The source template's layout is the default; a template JSON may carry
   its own under tpl.layout. rot.py's model_paragraphs() and render_md() read the same shape (core/layouts/*.json). */
const SOURCE_LAYOUT = {"schema":"rot-layout/1","id":"source-2026-09","sections":[{"kind":"header"},{"kind":"lines","heading":"Professional Summary & Areas of Expertise","blocks":["summary","tagline","expertise","technologies"],"always":true},{"kind":"education","heading":"Education"},{"kind":"experience","heading":"Professional Experience"},{"kind":"certifications","heading":"Credentialing & Certifications"},{"kind":"engagements","heading":"Business Consulting Engagements"},{"kind":"core_competencies","heading":"Core Competencies"}],"labels":{"technologies":"Technologies"},"joins":{"tagline":" | ","expertise":" • ","technologies":", ","core":", "}};
function layoutOf(layout){ const Ly=layout||SOURCE_LAYOUT; return {sections:Ly.sections||SOURCE_LAYOUT.sections, J:{...SOURCE_LAYOUT.joins, ...(Ly.joins||{})}, LB:{...SOURCE_LAYOUT.labels, ...(Ly.labels||{})}}; }
function lineBlocks(m){ return {summary:!!m.summary, tagline:(m.tagline||[]).length>0, expertise:(m.expertise||[]).length>0, technologies:(m.technologies||[]).length>0}; }
/* The resume as [kind, runs] paragraphs. Mirrors model_paragraphs() in rot.py, so the page and the CLI build the same document.
   A run is [style, text], ["tab"], or ["link", label, url]. */
function docParagraphs(m, layout){
  const {sections, J, LB}=layoutOf(layout), i=m.identity, P=[];
  const heading=t=>P.push(["heading",[["heading",t]]]);
  for(const sec of sections){
    if(sec.kind==="header"){
      P.push(["name",[["name",i.name]]]);
      const contact=[["contact",`${i.location} | ${i.phone} | ${i.email}`+((i.links||[]).length?" | ":"")]];
      (i.links||[]).forEach((ln,k)=>{ if(k) contact.push(["contact"," | "]); contact.push(["link",ln.label,ln.url]); });
      P.push(["contact",contact]);
    } else if(sec.kind==="lines"){
      const has=lineBlocks(m), blocks=sec.blocks||[];
      if(!sec.always && !blocks.some(b=>has[b])) continue;
      heading(sec.heading);
      for(const b of blocks){
        if(b==="summary" && has.summary) P.push(["summary",[["plain",m.summary]]]);
        else if(b==="tagline" && has.tagline) P.push(["tagline",[["plain",m.tagline.join(J.tagline)]]]);
        else if(b==="expertise" && has.expertise) P.push(["expertise",[["plain",m.expertise.join(J.expertise)]]]);
        else if(b==="technologies" && has.technologies){ P.push(["tech_label",[["bold_u",LB.technologies],["bold",":"]]]); P.push(["tech_line",[["plain",m.technologies.join(J.technologies)]]]); }
      }
    } else if(sec.kind==="education"){
      if(!(m.education||[]).length) continue;
      heading(sec.heading);
      for(const e of m.education){ P.push(["school",[["bold",e.school]]]); P.push(["degree",[["degree",e.degree_line]]]); for(const b of e.bullets||[]) P.push(["bullet",[["plain",btext(b)]]]); }
    } else if(sec.kind==="experience"){
      heading(sec.heading);
      for(const r of m.roles){
        P.push(["role_header",[["bold",`${r.title} | ${r.employer} |`],["tab"],["plain",r.dates]]]);
        if(r.context) P.push(["role_context",[["context",r.context]]]);
        r.bullets.forEach((b,k)=>P.push([k===r.bullets.length-1?"bullet_last":"bullet",[["plain",btext(b)]]]));
      }
    } else if(sec.kind==="certifications"){
      if(!(m.certifications||[]).length) continue;
      heading(sec.heading);
      for(const c of m.certifications){ const runs=[["bold",c.name],["plain",` — ${c.issuer}`]]; if(c.note) runs.push(["cert_note",` (${c.note})`]); P.push(["cert",runs]); }
    } else if(sec.kind==="engagements"){
      if(!(m.engagements||[]).length) continue;
      heading(sec.heading);
      for(const e of m.engagements){
        const runs=[["bold",e.client]];
        if(e.location) runs.push(["bold_italic",` | ${e.location} |`]);
        if(e.dates) runs.push(["bold",(e.location?" ":" | ")+e.dates]);
        if(e.commitment) runs.push(["plain",` (${e.commitment})`]);
        P.push(["eng_header",runs]);
        if(e.subtitle) P.push(["eng_subtitle",[["italic",e.subtitle]]]);
        e.bullets.forEach((b,k)=>P.push([k===e.bullets.length-1?"eng_bullet_last":"eng_bullet",[["plain",btext(b)]]]));
      }
    } else if(sec.kind==="core_competencies"){
      if(!(m.core_competencies||[]).length) continue;
      heading(sec.heading);
      for(const a of m.core_competencies) P.push(["comp",[["bold",a.label+": "],["plain",a.items.join(J.core)]]]);
    }
  }
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
  for(const [kind,runs] of docParagraphs(m, tpl.layout)){
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
function plainText(m, layout){
  const {sections, J, LB}=layoutOf(layout), i=m.identity, L=[];
  for(const sec of sections){
    if(sec.kind==="header") L.push(i.name, `${i.location} | ${i.phone} | ${i.email}`+((i.links||[]).length?" | "+(i.links||[]).map(l=>`${l.label}: ${l.url}`).join(" | "):""), "");
    else if(sec.kind==="lines"){
      const has=lineBlocks(m), blocks=sec.blocks||[];
      if(!sec.always && !blocks.some(b=>has[b])) continue;
      L.push(sec.heading.toUpperCase());
      for(const b of blocks){
        if(b==="summary"){ if(has.summary) L.push(m.summary, ""); }
        else if(b==="tagline") L.push((m.tagline||[]).join(J.tagline), "");
        else if(b==="expertise") L.push((m.expertise||[]).join(J.expertise), "");
        else if(b==="technologies") L.push(LB.technologies+": "+(m.technologies||[]).join(J.technologies), "");
      }
    }
    else if(sec.kind==="education"){ L.push(sec.heading.toUpperCase()); (m.education||[]).forEach(e=>L.push(e.school, e.degree_line)); }
    else if(sec.kind==="experience"){ L.push("", sec.heading.toUpperCase()); for(const r of m.roles){ L.push(`${r.title} | ${r.employer} | ${r.dates}`, r.context||""); r.bullets.forEach(b=>L.push("• "+btext(b))); L.push(""); } }
    else if(sec.kind==="certifications") L.push(sec.heading.toUpperCase(), ...(m.certifications||[]).map(c=>`• ${c.name} — ${c.issuer}${c.note?` (${c.note})`:""}`));
    else if(sec.kind==="engagements"){ if(!(m.engagements||[]).length) continue; L.push("", sec.heading.toUpperCase()); for(const e of m.engagements){ L.push(`${e.client}${e.location?` | ${e.location} |`:""}${e.dates?` ${e.dates}`:""}${e.commitment?` (${e.commitment})`:""}`); if(e.subtitle) L.push(e.subtitle); e.bullets.forEach(b=>L.push("• "+btext(b))); L.push(""); } }
    else if(sec.kind==="core_competencies") L.push(sec.heading.toUpperCase(), ...(m.core_competencies||[]).map(a=>`• ${a.label}: ${a.items.join(J.core)}`));
  }
  return L.join("\n");
}


/* ------------------------------ the engine: matching, selection, Section C, the resume model, placement, question drafts ------------------------------
   createEngine(ctx) reads ctx.bank (rot-library/3) and ctx.settings on every call, so a shell may swap the bank underneath it.
   Functions that need the working draft take it as their first argument `d`: {req, jd, cov, chosen, pinned, excluded, locked,
   textChoice, edits, editsC, excludedC, tagline, compOrder, sectionEdits, extra, engDetails, newAch, inbox, adj, summaryOn, summary,
   summaryClaims, runId, questions}. Settings the engine reads: default_engagement_role, education_claim_default, template_id,
   questions.{consulting:[[tag, weight]], consulting_regex, engagement_tag}. Mirrors rot.py select / assemble. */
function createEngine(ctx){
function extractRequirements(text){
  const lines = text.split(/\r?\n/).map(l=>l.trim()).filter(Boolean);
  const boost = new Set(); let inReq=false;
  lines.forEach((l,i)=>{ if(l.length<80 && REQ_HINT.test(l)) inReq=true; else if(l.length<60 && l.endsWith(":") && !REQ_HINT.test(l)) inReq=false; if(inReq) boost.add(i); });
  const low = lines.map(l=>l.toLowerCase()); const req={};
  for (const [tid,t] of Object.entries(ctx.bank.tags)){
    let hits=0; const phrases=new Set();
    for (const syn of t.synonyms){
      const re = new RegExp("(?<![a-z0-9-])"+escRe(syn.toLowerCase())+"(?![a-z0-9])","g");
      low.forEach((l,i)=>{ const m=l.match(re); if(m){ hits += m.length*(syn.length>4?1:0.6)*(boost.has(i)?1.4:1); phrases.add(syn);} });
    }
    if(hits) req[tid]={weight:Math.round(Math.min(hits,3)*100)/100, phrases:[...phrases].sort()};
  }
  return req;
}
function textAdj(d, t){ return (t.score_adj||0) + (d.adj[t.id]||0); }
const unsyncedInbox = (d) => d.inbox.filter(b=>!b.synced);
/* ------------------------------ tier 2 lookups and tier-3 QA (mirrors claims.py) ------------------------------ */
function claimById(id){ if(!ctx.bank._claims){ ctx.bank._claims=Object.fromEntries((ctx.bank.claims||[]).map(c=>[c.id,c])); } return ctx.bank._claims[id]; }
function disputedAchievements(){ const out=new Set(); for(const c of ctx.bank.claims||[]) if(c.status==="disputed" && (c.kind==="metric"||c.kind==="achievement")) out.add((c.kind==="metric"?c.subject:c.id).split(":").slice(1).join(":")); return out; }
function allAchievements(d){
  const held=disputedAchievements();   // a disputed number never prints
  const base = ctx.bank.achievements.filter(a=>!held.has(a.id)).map(a=>({...a, texts:[...a.texts], has_metrics:(a.metrics||[]).length>0}));
  const byId = Object.fromEntries(base.map(a=>[a.id,a]));
  for (const b of unsyncedInbox(d)){
    if(d.runId && b.run_id===d.runId && b.angle==="gate2") continue;   // this posting's answer bullets are already on the draft (d.newAch)
    const sec=b.section||"experience";
    if(sec!=="experience" && sec!=="engagement") continue;          // phrases and engagement details are not bullets
    const texts=[{id:"inbox:"+b._id, kind:"learned", angle:b.angle||"learned", text:b.text, score_adj:0}];
    if(b.longform) texts.push({id:"inbox-lf:"+b._id, kind:"learned", angle:"longform", text:b.longform, score_adj:0});
    if (b.achievement_id && byId[b.achievement_id]) byId[b.achievement_id].texts.push(...texts);
    else if (b.role) base.push({id:"inbox-"+b._id, role:b.role, engagement:b.engagement_key||null, confidence:"asserted", tags:Object.fromEntries((b.tags||[]).filter(t=>ctx.bank.tags[t]).map(t=>[t,1])), metrics:[], has_metrics:/\d/.test(b.text), texts});
  }
  for (const a of d.newAch){
    if (a.attach && byId[a.attach]) { byId[a.attach].texts.push(a.text); if(a.longText) byId[a.attach].texts.push(a.longText); }
    else if (a.ach) base.push(a.ach);
  }
  return base;
}
function scoreAch(d, a, req){
  const tags=ctx.bank.tags, keys=Object.keys(req);
  if(!keys.length) return [0,[]];
  const famW={}; for(const tid of keys){ const f=tags[tid].family; famW[f]=(famW[f]||0)+req[tid].weight; }
  let s=0; const why=[];
  const roll=(ctx.bank.baseline&&ctx.bank.baseline.scoring&&ctx.bank.baseline.scoring.family_rollup)??0.25;   // a partial credit for tags in a required family
  for(const [tid,w] of Object.entries(a.tags)){ if(req[tid]){ s+=w*req[tid].weight; why.push(tid);} else if(tags[tid]) s+=roll*w*Math.min(famW[tags[tid].family]||0,2); }
  const adj=Math.max(...a.texts.map(t=>textAdj(d,t)));
  const conf={verified:1,asserted:0.95,conflict:0.9}[a.confidence] ?? 0.9;
  return [(s+adj)*conf, why];
}
function angleScore(m, req){
  if(m.tag) return req[m.tag]?.weight||0;
  if(m.tags) return Math.max(0,...m.tags.map(t=>req[t]?.weight||0));
  if(m.family) return Math.max(0,...Object.entries(req).filter(([t])=>ctx.bank.tags[t].family===m.family).map(([,r])=>r.weight));
  return 0;
}
function pickText(d, a, req){
  const canon=a.texts.find(t=>t.kind==="canonical")||a.texts.find(t=>t.angle!=="longform")||a.texts[0];
  if(d.textChoice[a.id]){ const t=a.texts.find(x=>x.id===d.textChoice[a.id]); if(t) return t; }
  const newest=a.texts.find(t=>t.fresh && t.angle!=="longform"); if(newest) return newest;
  const sc=ctx.bank.baseline.scoring||{};
  const canonRel=Math.max(0,...Object.keys(a.tags).filter(t=>req[t]).map(t=>req[t].weight));
  let best=canon, bestS=0;
  for(const t of a.texts){ if(t.kind!=="variant"&&t.kind!=="learned") continue;
    if(t.angle==="longform") continue;                             // Section C wording never prints under a role
    const m=ctx.bank.baseline.angle_map[t.angle||""];
    const s = m ? angleScore(m,req) : (t.kind==="learned" ? canonRel+0.1+textAdj(d, t) : 0);
    if(s>bestS){best=t;bestS=s;} }
  if(best!==canon && bestS>=(sc.variant_min??1.5) && bestS>(sc.variant_margin??1.25)*canonRel) return best;
  if(best!==canon && best.kind==="learned" && bestS>=canonRel) return best;
  return canon;
}

/* ------------------------------ Section C: consulting engagements ------------------------------ */
function inboxEngDetails(d, key){
  const docs=unsyncedInbox(d).filter(b=>b.section==="engagement_details" && b.engagement_key===key).sort((a,b)=>String(a.created||"").localeCompare(String(b.created||"")));
  return docs.length ? docs[docs.length-1].details : null;
}
function engState(d, e){ const det=d.engDetails[e.key] || inboxEngDetails(d, e.key); return det ? {...e, ...Object.fromEntries(Object.entries(det).filter(([,v])=>v)), needs_details:false} : e; }
function visibleEngagements(d){ return (ctx.bank.engagements||[]).map(e=>engState(d,e)).filter(e=>!e.needs_details); }
function longText(a){ return a.texts.find(t=>t.kind==="learned"&&t.angle==="longform") || a.texts.find(t=>t.kind==="variant"&&t.angle==="longform") || null; }
function engMembers(d, e, all){
  const ids=[...(e.achievements||[])];
  for(const a of all) if(a.engagement===e.key && !ids.includes(a.id)) ids.push(a.id);
  for(const x of d.newAch) if(x.engagement===e.key){ const id=x.ach?x.ach.id:x.attach; if(id && !ids.includes(id)) ids.push(id); }
  return ids;
}
/* a bullet with no long form prints once, in Section C; fresh engagement answers print only in Section C */
function engExclude(d, all){
  const byId=new Map(all.map(a=>[a.id,a])), ex=new Set();
  for(const e of visibleEngagements(d)) for(const id of engMembers(d, e, all)){ const a=byId.get(id); if(a && !longText(a)) ex.add(id); }
  for(const x of d.newAch) if(x.engagement) ex.add(x.ach?x.ach.id:x.attach);
  return ex;
}
function engagementsModel(d, req){
  const L=ctx.bank, sc=L.baseline.scoring||{}, caps=L.baseline.engagement_caps||{}, hasReq=Object.keys(req).length>0;
  const all=allAchievements(d), byId=new Map(all.map(a=>[a.id,a]));
  const printed=new Set(); for(const items of Object.values(d.chosen)) for(const i of items) printed.add(norm(d.edits[i.a.id]??i.t.text));
  const out=[];
  for(const e of visibleEngagements(d)){
    const ids=engMembers(d, e, all).filter(id=>byId.has(id) && !d.excludedC.has(id));
    const items=ids.map((id,rank)=>{ const a=byId.get(id); let s=0;
      if(hasReq) s=scoreAch(d, a,req)[0]+(sc.priority_bonus??1.5)*Math.max(0,1-rank/Math.max(ids.length,1))+(a.has_metrics?(sc.metric_bonus??0.5):0);
      if(a.fresh) s+=1000;
      return {s, rank, a}; });
    items.sort((x,y)=>(y.s-x.s)||(x.rank-y.rank));
    const cap=(caps[e.key]??5)+items.filter(i=>i.a.fresh).length, picks=[];
    for(const i of items){
      const t=longText(i.a)||(i.a.texts.find(t=>t.kind==="canonical")||i.a.texts[0]);
      const text=d.editsC[i.a.id]??t.text;
      if(printed.has(norm(text))) continue;
      printed.add(norm(text)); picks.push({aid:i.a.id, tid:t.id, text, fresh:!!i.a.fresh});
      if(picks.length>=cap) break;
    }
    if(picks.length) out.push({key:e.key, client:e.client, location:e.location||null, dates:e.start?`${fmtDate(e.start)} – ${fmtDate(e.end)}`:null,
      commitment:e.commitment||null, subtitle:e.subtitle||null, bullets:picks});
  }
  return out;
}

function select(d, req){
  const L=ctx.bank, prio=L.baseline.priority, caps=L.baseline.caps, sc=L.baseline.scoring||{};
  const hasReq=Object.keys(req).length>0, byRole={};
  const all=allAchievements(d), ex=engExclude(d, all);
  for(const a of all){
    if(a.role==="education" || d.excluded.has(a.id) || ex.has(a.id)) continue;
    let [s,why]=scoreAch(d, a,req);
    const plist=prio[a.role]||[]; const ix=plist.indexOf(a.id); const rank= ix>=0?ix:99;
    if(hasReq){ s+=(sc.priority_bonus??1.5)*Math.max(0,1-rank/Math.max(plist.length,1)); s+= a.has_metrics?(sc.metric_bonus??0.5):0; }
    if(d.pinned.has(a.id)) s+=1000;
    (byRole[a.role] ||= []).push({s:Math.round(s*1000)/1000, rank, a, why});
  }
  const chosen={};
  for(const [role,items] of Object.entries(byRole)){
    items.sort((x,y)=>(y.s-x.s)||(x.rank-y.rank));
    const info=L.roles.find(r=>r.key===role); if(!info) continue;
    const pinnedHere=items.some(i=>d.pinned.has(i.a.id));
    const lock=d.locked?.[role];
    if(info.hidden && !pinnedHere && !(lock&&lock.length) && (!hasReq || items[0].s < (sc.hidden_role_min??4))) continue;
    const cap=(caps[role]??3) + items.filter(i=>i.a.fresh).length;
    let pick;
    if(lock){
      // a curated or restored draft stays exactly as it was; new pinned bullets go on top, open slots fill with the next best
      const byId=new Map(items.map(i=>[i.a.id,i]));
      const locked=lock.map(id=>byId.get(id)).filter(Boolean);
      const newPins=items.filter(i=>d.pinned.has(i.a.id) && !locked.includes(i));
      pick=[...newPins, ...locked];
      for(const i of items){ if(pick.length>=cap) break; if(!pick.includes(i)) pick.push(i); }
    } else pick=items.slice(0,cap);
    chosen[role]=pick.map(i=>({...i, t:pickText(d, i.a,req)}));
  }
  return chosen;
}
/* phrases answered on an earlier posting count before the hourly sync folds them into the bank */
function inboxPhrases(d, section){ return unsyncedInbox(d).filter(b=>b.section===section && b.text).map(b=>({text:b.text, name:b.text, tags:b.tags||[], area:b.area||null})); }
/* Section A */
function rankTagline(d, req){
  if(d.sectionEdits.tagline) return d.sectionEdits.tagline;
  const n=ctx.bank.baseline.tagline_count||7;
  const store=[...(ctx.bank.tagline_phrases||[]), ...inboxPhrases(d, "tagline")];
  const base=d.tagline ? d.tagline : rankByTags(store, req).map(p=>p.text);
  return uniq([...d.extra.tagline, ...base]).slice(0, Math.max(n, d.extra.tagline.length));
}
/* Section B: template order, JD-relevant items first when there is a posting */
function rankCompetencies(d, req){
  if(d.sectionEdits.expertise) return d.sectionEdits.expertise;
  const b=ctx.bank.baseline, n=b.competency_count||16, order=b.competency_order||[];
  let base;
  if(d.compOrder) base=d.compOrder;
  else if(!Object.keys(req).length) base=order;
  else {
    const pos=new Map(order.map((t,i)=>[t,i]));
    const comps=[...ctx.bank.competencies, ...inboxPhrases(d, "expertise")].map((c,i)=>({...c, p:pos.has(c.text)?pos.get(c.text):1000+i})).sort((x,y)=>x.p-y.p);
    base=rankByTags(comps,req).filter(c=>tagWeight(c.tags,req)>0).slice(0,n).map(c=>c.text);
    for(const t of order){ if(base.length>=n) break; if(!base.includes(t)) base.push(t); }
  }
  return uniq([...d.extra.expertise, ...base]).slice(0, Math.max(n, d.extra.expertise.length));
}
function rankTech(d, req){
  if(d.sectionEdits.technologies) return d.sectionEdits.technologies;
  const all=[...ctx.bank.technologies, ...inboxPhrases(d, "technology")];
  return uniq([...d.extra.technology, ...rankByTags(all, req).map(t=>t.name)]);
}
/* Section D: area order fixed, items JD-ranked within an area */
function rankCore(d, req){
  if(d.sectionEdits.core) return d.sectionEdits.core;
  const areas=(ctx.bank.core_competencies||[]).map(a=>({label:a.label, items:[...a.items]}));
  for(const it of [...inboxPhrases(d, "competency"), ...d.extra.competency.map(t=>typeof t==="string"?{text:t,tags:[]}:t)]){
    let target=areas.find(x=>x.label===it.area);
    if(!target){ let best=-1; for(const x of areas){ const have=new Set(x.items.flatMap(i=>i.tags)); const s=(it.tags||[]).filter(t=>have.has(t)).length; if(s>best){ best=s; target=x; } } }
    if(target && !target.items.some(i=>norm(i.text)===norm(it.text))) target.items.unshift({text:it.text, tags:it.tags||[]});
  }
  return areas.map(a=>({label:a.label, items:rankByTags(a.items, req).map(i=>i.text)}));
}

/* ------------------------------ resume model (schema rot-resume/2, same as rot.py assemble) ------------------------------ */
function resumeModel(d){
  const L=ctx.bank, req=d.req, id=L.identity, trace={};
  const roles=[...Object.keys(d.chosen)].map(k=>L.roles.find(r=>r.key===k)).filter(Boolean).sort((a,b)=>a.sort-b.sort);
  const byText=(list,key)=>Object.fromEntries((list||[]).map(x=>[x[key], x.claim_id]).filter(x=>x[1]));
  const tagline=rankTagline(d, req), expertise=rankCompetencies(d, req), technologies=rankTech(d, req);
  const tl=byText(L.tagline_phrases,"text"), ex=byText(L.competencies,"text"), tc=byText(L.technologies,"name");
  trace.tagline=tagline.map(t=>tl[t]).filter(Boolean); trace.expertise=expertise.map(t=>ex[t]).filter(Boolean); trace.technologies=technologies.map(t=>tc[t]).filter(Boolean);
  const education=L.education.map((e,n)=>{ const sid=(e.claim_id||ctx.settings.education_claim_default).split(":").slice(0,-1).join(":"); trace[`education:${n}`]=[`${sid}:school`,`${sid}:degree`,`${sid}:date`];
    return {school:e.school, degree_line:e.degree_line||`${e.degree} | ${e.date_display||e.year}`, bullets:[]}; });
  const achClaims=a=>a.claim_ids||[];
  const outRoles=roles.map(r=>{ trace[`role:${r.key}`]=r.claim_ids||[`role:${r.key}:title`,`role:${r.key}:employer`,`role:${r.key}:start`,`role:${r.key}:end`,`role:${r.key}:context`];
    return {key:r.key, title:r.title, employer:r.employer, location:r.location, dates:r.dates, context:[r.location, r.context].filter(Boolean).join(" · "),
      bullets:d.chosen[r.key].map((i,n)=>{ const ids=achClaims(i.a); trace[`role:${r.key}:${n}`]=ids; return {aid:i.a.id, tid:i.t.id, text:d.edits[i.a.id]??i.t.text, fresh:!!i.a.fresh||!!i.t.fresh, claim_ids:ids}; })}; });
  const certs=L.certifications.filter(c=>!c.hidden).map((c,n)=>{ if(c.claim_id){ const sid=c.claim_id.split(":").slice(0,-1).join(":"); trace[`cert:${n}`]=[`${sid}:name`,`${sid}:issuer`].concat(c.status?[`${sid}:status`]:[]); }
    return {name:c.name, issuer:c.issuer, note:c.note||(c.status?"In Progress":null)}; });
  const engagements=engagementsModel(d, req).map(e=>{ const lib=(L.engagements||[]).find(x=>x.key===e.key); trace[`eng:${e.key}`]=(lib&&lib.claim_ids)||[];
    e.bullets=e.bullets.map((b,n)=>{ const a=allAchievements(d).find(x=>x.id===b.aid); const ids=a?achClaims(a):[]; trace[`eng:${e.key}:${n}`]=ids; return {...b, claim_ids:ids}; }); return e; });
  const core=rankCore(d, req).map(a=>{ const items=(L.core_competencies||[]).find(x=>x.label===a.label)?.items||[]; const m=Object.fromEntries(items.map(i=>[i.text,i.claim_id])); trace[`core:${a.label}`]=a.items.map(t=>m[t]).filter(Boolean); return a; });
  if(d.summaryOn && d.summary) trace.summary=d.summaryClaims||[];
  return {
    schema:"rot-resume/2", template:(L.template&&L.template.id)||ctx.settings.template_id,
    generator:{core:VERSION, edition:ctx.settings.edition||"desk", prompt_versions:prompts.VERSIONS},   // tier 3 provenance: what wrote this model
    identity:{name:id.name, location:id.location, phone:id.phone, email:id.email, links:id.links||[{label:"LinkedIn Profile", url:"https://"+id.linkedin}]},
    summary:(d.summaryOn && d.summary)||null,
    tagline, expertise, technologies, education, roles:outRoles, certifications:certs, engagements, core_competencies:core, trace
  };
}

const engByKey = k => (ctx.bank.engagements||[]).find(e=>e.key===k);
function parsePlace(v){ v=String(v||""); const key=v.slice(2);
  if(v.startsWith("e:")){ const e=engByKey(key); return e ? {role:e.role||ctx.settings.default_engagement_role, engagement:key} : null; }
  return v.startsWith("r:") && ctx.bank.roles.some(r=>r.key===key) ? {role:key, engagement:null} : null; }
function defaultPlace(q){ const e=sectionOf(q)==="engagement" && q.engagement ? engByKey(q.engagement) : null;
  return e ? {role:e.role||ctx.settings.default_engagement_role, engagement:e.key} : {role:q.role, engagement:null}; }
function bulletPlace(q, b){ return b && (b.role || b.engagement) ? {role:b.role || defaultPlace(q).role, engagement:b.engagement || null} : defaultPlace(q); }
function placeName(d, p){
  if(p.engagement){ const e=engByKey(p.engagement); return e ? engState(d, e).client.replace(/ \(Confidential\)$/,"") : p.engagement; }
  const r=ctx.bank.roles.find(r=>r.key===p.role); return r ? shortRole(r) : p.role; }
/* the resume's roles, then consulting engagements that print, then earlier roles (picking one adds that role to the resume) */
function placeGroups(d){
  const onDraft=ctx.bank.roles.filter(r=>!r.hidden || d.chosen[r.key]), earlier=ctx.bank.roles.filter(r=>r.hidden && !d.chosen[r.key]);
  const engs=(ctx.bank.engagements||[]).map(e=>engState(d,e)).filter(e=>!e.needs_details || d.questions.some(q=>q.engagement===e.key));
  return [["Professional Experience", onDraft.map(r=>["r:"+r.key, shortRole(r)])],
          ["Consulting engagements (Section C)", engs.map(e=>["e:"+e.key, e.client.replace(/ \(Confidential\)$/,"")])],
          ["Earlier roles (adds the role to this resume)", earlier.map(r=>["r:"+r.key, shortRole(r)])]].filter(g=>g[1].length);
}
/* an answer bullet can enrich a bank bullet only from the same role (or engagement) */
function attachOk(aid, p){ const a=ctx.bank.achievements.find(x=>x.id===aid); if(!a) return false;
  if(p.engagement){ const e=engByKey(p.engagement); return !!e && ((e.achievements||[]).includes(aid) || a.engagement===p.engagement); }
  return a.role===p.role; }
/* the number check for an answer bullet in its current place: its answer, plus the bank bullet it enriches (same place only) */
function bulletQa(Q, B){
  const p=bulletPlace(Q,B), ids=(B.achievement_id&&attachOk(B.achievement_id,p))?((ctx.bank.achievements.find(a=>a.id===B.achievement_id)||{}).claim_ids||[]):[];
  let qa=qaLine(B.text, ids, answerQuotes(Q), ctx.bank.length_band, claimById);
  if(B.longform && p.engagement) qa=qa.concat(qaLine(B.longform, ids, answerQuotes(Q), ctx.bank.longform_band||{hard_ceiling:340}, claimById).map(x=>"long form: "+x));
  return qa;
}
/* tools the posting names that neither the Technologies list nor Section D mentions yet */
function unknownTools(d, jd){
  const known=[...ctx.bank.technologies.map(t=>t.name), ...(ctx.bank.core_competencies||[]).flatMap(a=>a.items.map(i=>i.text)), ...inboxPhrases(d, "technology").map(t=>t.text), ...d.extra.technology].join(" | ").toLowerCase();
  const found=[];
  for(const t of TOOL_LEXICON){ const re=new RegExp("(?<![A-Za-z0-9])"+escRe(t)+"(?![A-Za-z0-9])"); if(re.test(jd) && !known.includes(t.toLowerCase().replace(/\.io$/,""))) found.push(t); }
  return found.slice(0,6);
}
function consultingWanted(d){
  const r=d.req, w=t=>r[t]?.weight||0, cfg=ctx.settings.questions||{};
  const score=(cfg.consulting||[]).reduce((a,[t,k])=>a+w(t)*k, 0);
  return score >= 1 || (cfg.consulting_regex ? new RegExp(cfg.consulting_regex, "i").test(d.jd) : false);
}
function templateQuestions(d){
  const tags=ctx.bank.tags;
  const gaps=Object.entries(d.req).map(([t,r])=>({t,w:r.weight,c:d.cov[t]||0,ph:r.phrases})).sort((a,b)=>(b.w*(1-Math.min(b.c,1)))-(a.w*(1-Math.min(a.c,1))));
  const roleFor=t=>{ let best=null,bs=-1; for(const a of ctx.bank.achievements){ const w=a.tags[t]||0; const r=ctx.bank.roles.find(x=>x.key===a.role); if(r&&!r.hidden&&w>bs){bs=w;best=a.role;} } return best||ctx.bank.roles[0].key; };
  const qs=[];
  const waiting=(ctx.bank.engagements||[]).map(e=>engState(d,e)).find(e=>e.needs_details);
  if(waiting && consultingWanted(d)) qs.push({section:"engagement", engagement:waiting.key, tag:ctx.settings.questions.engagement_tag, role:waiting.role||ctx.settings.default_engagement_role,
    question:`This posting values consulting work. Your ${waiting.client.replace(/ \(Confidential\)$/,"")} engagement has a bullet but no details yet. When did it run, how should the client read on a resume, and what else did you deliver?`,
    why:"Section C can only show an engagement once it has dates and a one-line description.", fields:{}});
  const tools=unknownTools(d, d.jd);
  if(tools.length) qs.push({section:"technology", tag:null, role:null, question:`The posting names ${tools.join(", ")}. Which of these have you used, and at what level?`,
    why:"Your Technologies line doesn't list them yet. Anything you name here joins it.", hint:"e.g. Salesforce Apex (basic), Looker (dashboards). Write no to skip."});
  for(const g of gaps){ if(qs.length>=5) break;
    qs.push({section:"experience", tag:g.t, role:roleFor(g.t), question:`The posting leans on ${tags[g.t].label.toLowerCase()} (“${g.ph.slice(0,2).join("”, “")}”). What's your strongest concrete example? Say what you did, the scope, and the measurable result.`, why: g.c>0?"Your draft touches this only lightly.":"Nothing in your draft proves this yet.", hint:"e.g. who, how many, how much, what changed"}); }
  return qs.slice(0,5);
}

function libraryDigest(){
  return ctx.bank.achievements.filter(a=>a.role!=="education").map(a=>`${a.id} | ${a.role} | ${(a.texts.find(t=>t.kind==="canonical")||a.texts[0]).text}`).join("\n");
}
function draftDigest(d){
  return Object.entries(d.chosen).map(([r,items])=>`[${r}]\n`+items.map(i=>`- (${i.a.id}) ${i.t.text}`).join("\n")).join("\n");
}
function currentBulletDigest(d){ return Object.entries(d.chosen).flatMap(([r,items])=>items.map(i=>`${i.a.id} | ${r} | ${d.edits[i.a.id]??i.t.text}`)).join("\n"); }
function findChosen(d, aid){ for(const items of Object.values(d.chosen)) for(const i of items) if(i.a.id===aid) return i; return null; }
/* ------------------------------ prompts: pure builders and parsers (the shell talks to Claude) ------------------------------
   Wording comes from ctx.settings.prompts: persona {name, first, subject, possessive, possessive_cap, standard_label},
   bullet_example {place, text, tags}, entry_example {text, tags}. Bump VERSIONS whenever a prompt's text changes. */
const prompts = {
  VERSIONS: {tailor:"tailor@6", bullets:"bullets@6", tighten:"tighten@2", summary:"summary@1"},
  persona(){ const p=(ctx.settings.prompts||{}).persona||{};
    return {name:p.name||"the candidate", first:p.first||"the candidate", subject:p.subject||"they", possessive:p.possessive||"their", possessive_cap:p.possessive_cap||"Their", standard_label:p.standard_label||"Resume 1"}; },
  /* one call weighs the posting, orders Sections A and B, and drafts the five questions */
  tailor(d){
    const L=ctx.bank, P=prompts.persona(), taxo=Object.entries(L.tags).map(([id,t])=>`${id}: ${t.label}`).join("\n");
    const roleList=L.roles.map(r=>`${r.key}: ${r.title} | ${r.employer} | ${r.dates}`).join("\n");
    const engList=(L.engagements||[]).map(e=>engState(d,e)).map(e=>`${e.key}: ${e.client} | ${e.needs_details?"NEEDS DETAILS (not shown until dates and a description are given)":`${e.dates||""} | ${e.subtitle||""}`}`).join("\n");
    const tools=unknownTools(d, d.jd);
    return `You are tailoring ${P.name}'s resume to one job description. ${P.possessive_cap} template has no summary paragraph: a tagline line (Section A) and an areas-of-expertise line (Section B) carry the positioning. Use ONLY facts present in the candidate library and draft below. Never invent employers, titles, numbers, tools, or outcomes.

JOB DESCRIPTION:
<<<
${d.jd.slice(0,12000)}
>>>

TAG TAXONOMY (id: label):
${taxo}

DETERMINISTIC REQUIREMENT MAP (tag id: weight 0-3):
${Object.entries(d.req).map(([t,r])=>`${t}: ${r.weight}`).join("\n")||"(none)"}

ROLES (key: title | employer | dates):
${roleList}

CONSULTING ENGAGEMENTS (Section C; key: client | status):
${engList||"(none)"}

CURRENT DRAFT BULLETS:
${draftDigest(d)}

FULL LIBRARY (achievement id | role | canonical bullet):
${libraryDigest()}

TAGLINE OPTIONS (Section A, exact text):
${(L.tagline_phrases||[]).map(p=>p.text).join(" | ")}

EXPERTISE OPTIONS (Section B, choose only from these, exact text):
${L.competencies.map(c=>c.text).join(" | ")}

TECHNOLOGIES ALREADY LISTED: ${L.technologies.map(t=>t.name).join(", ")}
TOOLS THE POSTING NAMES THAT ARE NOT LISTED: ${tools.join(", ")||"(none detected)"}

Reply with ONLY one JSON object:
{"company": string|null, "title": string|null,
 "requirements": [{"tag": "<tag id from taxonomy>", "weight": <0.5 to 3, 3 = must-have>, "why": "<short evidence from the posting>"}],
 "uncatalogued": [{"phrase": "<requirement no tag covers>", "weight": <1-3>}],
 "tagline": ["<4 to 7 phrases in print order, most relevant to this posting first: exact TAGLINE OPTIONS, plus at most 2 new phrases of 60 characters or fewer that the library clearly supports>"],
 "expertise_order": ["<up to 16 exact EXPERTISE OPTIONS, most relevant first>"],
 "followups": [{"question": "...", "why": "<which requirement this proves and why it matters>", "tag": "<tag id>", "section": "experience"|"engagement"|"technology"|"tagline"|"expertise", "role": "<role key, for experience>", "engagement": "<engagement key, for engagement>", "hint": "<what a strong answer includes>"}]}
Requirements: return up to 20 tags with your corrected importance. Followups: exactly 5, one concrete question each, no compound questions.
- Most should be "experience": target the highest-weight requirements the draft proves weakly or not at all, or implied experience ${P.first} likely has but hasn't stated (quota %, team size, deal size, cycle length).
- If the posting values consulting or advisory work and an engagement NEEDS DETAILS, make one "engagement" question for it (it asks for dates, how to name the client, a one-line description, and what else ${P.subject} delivered).
- If the posting names tools that are not listed, make one "technology" question naming them.
- Use "tagline" or "expertise" only when the posting stresses an identity or a strength no option covers.
Address ${P.first} directly in second person ("you", "your"), never "${P.first}" or "${P.subject}". Don't ask about anything already well evidenced.`;
  },
  /* the tailor reply as plain data: merged requirement weights, uncatalogued phrases, tagline/expertise orders (null = keep), questions */
  parseTailor(d, r){
    const L=ctx.bank, req={...d.req};
    for(const q of (Array.isArray(r.requirements)?r.requirements:[])){
      const t=String(q.tag||""), w=Math.max(0.5,Math.min(3,+q.weight||0));
      if(!L.tags[t]||!w) continue;
      req[t] = req[t] ? {...req[t], weight:Math.round(Math.max(req[t].weight,w)*100)/100} : {weight:w, phrases:[String(q.why||"").slice(0,40)].filter(Boolean)};
    }
    const uncatalogued=(Array.isArray(r.uncatalogued)?r.uncatalogued:[]).filter(u=>u&&u.phrase).slice(0,8).map(u=>({phrase:String(u.phrase).slice(0,80), weight:+u.weight||1}));
    const opts=new Set((L.tagline_phrases||[]).map(p=>p.text)); let fresh=0;
    const tl=(Array.isArray(r.tagline)?r.tagline:[]).map(x=>String(x||"").trim()).filter(x=>x && (opts.has(x) || (x.length<=60 && !/\b(I|my|we)\b/.test(x) && fresh++<2)));
    const eopts=new Set(L.competencies.map(c=>c.text)); const co=(r.expertise_order||r.competency_order||[]).filter(c=>eopts.has(c));
    const SECS=new Set(["experience","engagement","technology","tagline","expertise"]);
    const questions=(Array.isArray(r.followups)?r.followups:[]).filter(q=>q&&q.question).slice(0,5).map(q=>{
      let section=SECS.has(q.section)?q.section:"experience";
      const eng=engByKey(q.engagement)||(section==="engagement"?(L.engagements||[]).map(e=>engState(d,e)).find(e=>e.needs_details):null);
      if(section==="engagement" && !eng) section="experience";
      return {question:String(q.question), why:String(q.why||""), tag:L.tags[q.tag]?q.tag:null, section,
        engagement:section==="engagement"?eng.key:null, role:L.roles.some(x=>x.key===q.role)?q.role:(section==="engagement"?(eng.role||ctx.settings.default_engagement_role):ctx.settings.fallback_role),
        hint:String(q.hint||""), fields:{}}; });
    return {company:r.company?String(r.company).slice(0,80):null, title:r.title?String(r.title).slice(0,120):null, req, uncatalogued,
      tagline:tl.length>=4?uniq(tl).slice(0,7):null, compOrder:co.length>=6?co:null, questions};
  },
  /* where a bullet may go: the resume's roles, consulting engagements that print, earlier roles, and each answer's own default */
  offers(d, items){
    const L=ctx.bank, offer=new Map();
    for(const r of L.roles.filter(r=>!r.hidden||d.chosen[r.key])) offer.set("r:"+r.key, `${r.title} | ${r.employer} | ${r.dates}`);
    for(const e of (L.engagements||[]).map(e=>engState(d,e)).filter(e=>!e.needs_details||d.questions.some(q=>q.engagement===e.key))) offer.set("e:"+e.key, `consulting client "${e.client}" (Business Consulting Engagements section)`);
    for(const r of L.roles.filter(r=>r.hidden&&!d.chosen[r.key])) offer.set("r:"+r.key, `${r.title} | ${r.employer} | ${r.dates} (earlier role, not on this resume: only when the answer clearly describes work there)`);
    for(const q of items){ if(PHRASE_SECTIONS[sectionOf(q)]) continue; const p=defaultPlace(q), k=placeKey(p); if(!offer.has(k)) offer.set(k, placeName(d, p)); }
    return offer;
  },
  /* one call converts any number of answers into bullets (short and Section C long form) and short entries */
  bullets(d, items, offer, posting){
    const L=ctx.bank, P=prompts.persona(), band=L.length_band, lband=L.longform_band||{min:170,hard_ceiling:340};
    const kindOf=q=>{ const s=sectionOf(q); return PHRASE_SECTIONS[s]?s:(s==="engagement"?"engagement":"bullet"); };
    const ex=(ctx.settings.prompts||{}).bullet_example||{place:"r:current", text:"Built the weekly pipeline review that the sales team adopted within one quarter.", tags:["pipeline-management"]};
    const ex2=(ctx.settings.prompts||{}).entry_example||{text:"Salesforce (admin)", tags:["crm-discipline"]};
    return `Turn ${P.name}'s interview answers into content for ${P.possessive} resume template.
BULLET answers (kind "bullet"): resume bullets in ${P.possessive} "${P.standard_label}" bare-bone style.
- Verb-first, outcome- and impact-driven, ${band.p10}-${band.hard_ceiling} characters each (aim for about ${band.median}).
- Implied first person: never "I", "my", "we", or "${P.first}". Past tense for past roles; present tense only for the current role.
- An answer written as bullet points or several sentences may become 1 to 3 bullets, one per distinct accomplishment. Merge fragments that describe the same thing.
- If an answer strengthens an existing bullet listed below, rewrite that bullet and put its id in "achievement_id"; otherwise use null.
ENGAGEMENT answers (kind "engagement"): bullets for a consulting engagement in the Business Consulting Engagements section. For each distinct accomplishment return "text" (the short version, ${band.p10}-${band.hard_ceiling} characters) and "longform" (${lband.min||170}-${lband.hard_ceiling} characters: the same facts with scope, method, and result, in the style of the examples below).
PLACEMENT (bullet and engagement answers): each bullet goes under the job or consulting client where that work happened. Return "place": one id from PLACES. An answer that draws on several jobs becomes separate bullets, each with its own place. When the answer doesn't say where the work happened, use the place shown with the answer. A bullet placed at a consulting client (an "e:" id) also gets "longform" as described above. Use "achievement_id" only for an existing bullet from the same place.
ENTRY answers (kind "tagline", "expertise", "technology", or "competency"): return "entries", never bullets.
- tagline: identity phrases of 60 characters or fewer, e.g. "Process Engineer", "GTM and Sales/Marketing Execution Specialist".
- expertise: Title Case skills of 70 characters or fewer, e.g. "Lead Generation & Prospecting".
- technology: tool names exactly as a resume lists them, with the level in parentheses only if the answer states it, e.g. "Salesforce Apex (basic)". Only tools the answer says were used.
- competency: short lowercase phrases, e.g. "partner enablement".
Every kind: use ONLY facts stated in the answer. Never invent results, metrics, or tools. If an answer adds nothing usable (empty, "no", "none"), return nothing for it.

POSTING: ${(posting&&posting.title)||"(title unknown)"} at ${(posting&&posting.company)||"(company unknown)"}

PLACES (id: where the bullet prints)
${[...offer].map(([k,v])=>`${k}: ${v}`).join("\n")}

ANSWERS
${items.map((q,n)=>`${n+1}. [kind: ${kindOf(q)} | proves: ${q.tag||"general"}${PHRASE_SECTIONS[sectionOf(q)]?"":` | place: ${placeKey(defaultPlace(q))}`}]\nQ: ${q.question}\nA: ${String(q.answer).slice(0,2000)}`).join("\n\n")}

EXISTING BULLETS (achievement id | role | text)
${currentBulletDigest(d)}

SECTION C STYLE EXAMPLES
${(L.achievements.flatMap(a=>a.texts.filter(t=>t.angle==="longform").map(t=>t.text))).slice(0,3).map(t=>"- "+t).join("\n")}

TAG IDS YOU MAY USE: ${Object.keys(L.tags).join(", ")}

Reply with ONLY one JSON object, for example:
{"bullets":[{"q":1,"place":"${ex.place}","text":"${ex.text}","longform":null,"tags":${JSON.stringify(ex.tags)},"achievement_id":null}],
 "entries":[{"q":2,"text":"${ex2.text}","tags":${JSON.stringify(ex2.tags)}}]}`;
  },
  /* the bullets reply as clean bullets with a place each, and clean entries; the shell runs the tighten passes, then qaBullets */
  parseBullets(d, items, offer, r){
    const L=ctx.bank;
    const src=b=>items[(+b.q||1)-1]||items[0];
    const bullets=(Array.isArray(r?.bullets)?r.bullets:[]).filter(b=>b&&typeof b.text==="string"&&b.text.trim().length>20&&!PHRASE_SECTIONS[sectionOf(src(b))])
      .map(b=>{ const s=src(b), pid=[b.place, "r:"+b.place, "e:"+b.place].find(v=>offer.has(v)), p=(pid&&parsePlace(pid))||defaultPlace(s);
        return {q:(+b.q||1), ix:s.ix, role:p.role, engagement:p.engagement, text:cleanBullet(b.text), longform:(p.engagement&&typeof b.longform==="string"&&b.longform.trim().length>40)?cleanBullet(b.longform):null,
        tags:(Array.isArray(b.tags)?b.tags:[]).filter(t=>L.tags[t]).concat(s.tag&&!(b.tags||[]).includes(s.tag)?[s.tag]:[]), achievement_id:(b.achievement_id&&attachOk(b.achievement_id,p))?b.achievement_id:null}; });
    const entries=(Array.isArray(r?.entries)?r.entries:[]).filter(e=>e&&typeof e.text==="string"&&e.text.trim()).map(e=>{ const s=src(e); const sec=sectionOf(s);
      return {q:(+e.q||1), ix:s.ix, text:cleanPhrase(e.text, PHRASE_SECTIONS[sec]?sec:"technology"), tags:(Array.isArray(e.tags)?e.tags:[]).filter(t=>L.tags[t])}; }).filter(e=>e.text && PHRASE_SECTIONS[sectionOf(items.find(q=>q.ix===e.ix)||{})]);
    return {bullets, entries};
  },
  /* tier-3 QA: a converted bullet may only state what the answer (or the bank bullet it enriches) states */
  qaBullets(bullets, items){
    const L=ctx.bank, band=L.length_band, lband=L.longform_band||{min:170,hard_ceiling:340};
    const quotesOf=q=>[String(q.answer||"")].concat(q.fields?[Object.values(q.fields).filter(Boolean).join("; ")]:[]);
    const claimsOf=aid=>aid?((L.achievements.find(a=>a.id===aid)||{}).claim_ids||[]):[];
    for(const b of bullets){ const q=items.find(x=>x.ix===b.ix)||{}; const ids=claimsOf(b.achievement_id), quotes=quotesOf(q);
      b.qa=qaLine(b.text, ids, quotes, band, claimById); if(b.longform) b.qa=b.qa.concat(qaLine(b.longform, ids, quotes, lband, claimById).map(x=>"long form: "+x)); }
    return bullets;
  },
  tighten(texts, mode){
    const L=ctx.bank, P=prompts.persona(), band=L.length_band, lband=L.longform_band||{min:170,hard_ceiling:340};
    const std = mode==="longform" ? `the Business Consulting Engagements standard: verb-first, outcome-driven, ${lband.min||170}-${lband.hard_ceiling} characters with scope, method, and result`
                                 : `${P.name}'s "${P.standard_label}" standard: verb-first, outcome-driven, ${band.p10}-${band.hard_ceiling} characters`;
    return `Tighten each resume bullet to ${std}, implied first person (no "I", "my", "we"), the same facts and numbers, nothing invented.
BULLETS
${texts.map((t,i)=>`${i+1}. ${t}`).join("\n")}
Reply with ONLY a JSON array of ${texts.length} strings in the same order.`;
  },
  /* the optional summary paragraph is written only from the claims on the draft; the shell checks the answer with qaLine */
  summary(d, m, posting){
    const L=ctx.bank, P=prompts.persona();
    const ids=[...new Set([...(m.roles.flatMap(r=>r.bullets.flatMap(b=>b.claim_ids||[]))), ...(m.trace.tagline||[])])].slice(0,24);
    const facts=ids.map(claimById).filter(Boolean).map(c=>`- [${c.id}] ${c.text}${c.numbers&&c.numbers.length?` (numbers you may use: ${c.numbers.join(", ")})`:""}`).join("\n");
    const words=(L.confidence&&L.confidence.bands&&L.confidence.bands.summary_max_words)||55;
    const prompt=`Write the Professional Summary paragraph for ${P.name}'s resume for this posting, using ONLY the facts below.
RULES: at most ${words} words, one paragraph, implied first person (never "I", "my", "we", or "${P.first}"), open with a role noun such as "Revenue and go-to-market operator", no adjectives without a fact behind them, and use a number only if it appears in the facts' allowed numbers. Never invent employers, clients, tools or outcomes.
POSTING: ${(posting&&posting.title)||"(title unknown)"} at ${(posting&&posting.company)||"(company unknown)"}
${d.jd.slice(0,3000)}

FACTS (claim id, statement):
${facts}

Reply with ONLY one JSON object: {"summary": "<the paragraph>", "claims_used": ["<claim ids the paragraph relies on>"]}`;
    return {prompt, ids, words};
  },
  summaryRetry(text, blocked, words){ return `Rewrite this resume summary so it contains none of these numbers: ${blocked.join("; ")}. Keep it under ${words} words, implied first person, same facts otherwise. Reply with ONLY {"summary": "..."}\n\n${text}`; },
};

function compute(d, req){ const chosen=select(d, req); const cov=coverage(req, chosen); return {chosen, cov, score:Object.keys(req).length?matchScore(req, cov):null}; }
return { extractRequirements, claimById, disputedAchievements, angleScore, longText, parsePlace, defaultPlace, bulletPlace, attachOk, bulletQa, libraryDigest, textAdj, allAchievements, scoreAch, pickText, inboxEngDetails, engState, visibleEngagements, engMembers, engExclude, engagementsModel, select, inboxPhrases, rankTagline, rankCompetencies, rankTech, rankCore, resumeModel, placeName, placeGroups, unknownTools, consultingWanted, templateQuestions, draftDigest, currentBulletDigest, findChosen, unsyncedInbox, engByKey, compute, prompts };
}

/* ------------------------------ Word and PDF files (the shell passes JSZip, jsPDF and a font loader) ------------------------------ */
/* The document's parts in the order rot.py's docx_bytes writes them: the template's own parts plus a document.xml built from docParagraphs. */
function docxParts(m, tpl, stamp){
  const {xml, links}=documentXml(m, tpl), parts={};
  parts["[Content_Types].xml"]=tpl.parts["[Content_Types].xml"];
  parts["_rels/.rels"]=tpl.parts["_rels/.rels"];
  parts["word/document.xml"]=xml;
  parts["word/_rels/document.xml.rels"]=tpl.rels_open+tpl.rels_base.join("")+links.map(([id,url])=>tpl.rel_hyperlink.replace("{id}",()=>id).replace("{url}",()=>xmlEsc(url))).join("")+tpl.rels_close;
  for(const [name,x] of Object.entries(tpl.parts)) if(name!=="[Content_Types].xml" && name!=="_rels/.rels") parts[name]=x;
  parts["docProps/core.xml"]=tpl.core_xml.replace("{title}",()=>xmlEsc(m.identity.name+" — Resume")).replace(/\{author\}/g,()=>xmlEsc(m.identity.name)).replace(/\{stamp\}/g,()=>stamp);
  return parts;
}
async function buildDocx(m, tpl, JSZip, opts={}){
  if(!JSZip) throw new Error("jszip");
  const zip=new JSZip(), stamp=opts.stamp||new Date().toISOString().replace(/\.\d{3}Z$/,"Z");
  for(const [name,data] of Object.entries(docxParts(m, tpl, stamp))) zip.file(name, data, {createFolders:false});   // no folder entries, as rot.py writes it
  return zip.generateAsync({type:opts.type||"blob", mimeType:"application/vnd.openxmlformats-officedocument.wordprocessingml.document", compression:"DEFLATE"});
}
/* jsPDF: the template's layout in Carlito, the metric-compatible twin of Calibri. loadFonts(doc) registers Carlito and returns true, or false for Helvetica. */
async function buildPdf(m, tpl, jspdf, loadFonts){
  const { jsPDF } = jspdf;
  const doc=new jsPDF({unit:"pt", format:"letter", compress:true});
  const M=(tpl&&tpl.metrics)||PDF_METRICS, STY=(tpl&&tpl.styles)||{};
  const carlito=await loadFonts(doc);
  const FONT=carlito?"Carlito":"helvetica", T=carlito?(s=>String(s)):pdfSafe;
  const P=M.page, X0=P.left, X1=P.width-P.right, CW=X1-X0, TOP=P.top, BOT=P.height-P.bottom, SP=M.space;
  const SGL=M.single, ASC=M.ascent;
  // Word's paragraph rules from the template: alignment, spacing (the larger of after/before wins), line multiple,
  // list indent, keep-with-next, and "contextual" spacing (no space between two list paragraphs of the same style)
  const K={name:{align:"center",after:SP.name}, contact:{align:"center",after:SP.contact},
    heading:{before:SP.heading_before,after:SP.heading_after,rule:true,keep:true}, summary:{after:SP.tagline}, tagline:{align:"center",after:SP.tagline}, expertise:{align:"center",after:SP.tagline},
    tech_label:{align:"center",keep:true}, tech_line:{align:"center"}, school:{after:SP.school,keep:true}, degree:{after:SP.degree},
    role_header:{keep:true,tab:true}, role_context:{after:SP.context,line:M.line.context,keep:true},
    bullet:{list:"experience",after:4,group:"list"}, bullet_last:{list:"experience",after:SP.bullet_last,group:"list"},
    cert:{list:"certs",after:SP.cert,line:M.line.list}, eng_header:{after:SP.eng_header,keep:true}, eng_subtitle:{after:SP.eng_subtitle,keep:true},
    eng_bullet:{list:"engagements",after:SP.eng_bullet,line:M.line.list}, eng_bullet_last:{list:"engagements",after:SP.eng_bullet_last,line:M.line.list},
    comp:{list:"competencies",after:3.5,line:M.line.list,group:"list"}};
  const style=st=>{ const f=STY[st]||{}; return {b:!!f.b, i:!!f.i, u:!!f.u||!!f.link, color:f.link?M.hyperlink:(f.color?"#"+f.color:"#000000"), size:f.sz?f.sz/2:M.size, link:!!f.link}; };
  const setF=sy=>{ doc.setFont(FONT, sy.b&&sy.i?"bolditalic":sy.b?"bold":sy.i?"italic":"normal"); doc.setFontSize(sy.size); };
  const width=(t,sy)=>{ setF(sy); return doc.getTextWidth(t); };
  function tokens(runs){ const out=[]; for(const r of runs){ if(r[0]==="tab") continue; const sy=style(r[0]==="link"?"link":r[0]); const txt=T(r[1]);
      for(const part of txt.split(/(\s+)/)) if(part){ const sp=/^\s+$/.test(part), t=sp?" ":part; out.push({t, sy, sp, url:r[0]==="link"?r[2]:null, w:width(t,sy)}); } } return out; }
  /* draw same-style stretches as one string, so the PDF keeps real spaces: copy/paste and applicant-tracking parsers read words, not glyph runs */
  function segments(toks){ const segs=[]; for(const tk of toks){ const last=segs[segs.length-1]; if(last && last.sy===tk.sy && last.url===tk.url){ last.t+=tk.t; last.w+=tk.w; } else segs.push({t:tk.t, sy:tk.sy, url:tk.url, w:tk.w}); } return segs; }
  function drawSegs(segs, x, base){ for(const sg of segs){ setF(sg.sy); doc.setTextColor(sg.sy.color); doc.text(sg.t, x, base);
      if(sg.sy.u){ doc.setDrawColor(sg.sy.color); doc.setLineWidth(0.5); doc.line(x, base+1.3, x+sg.w, base+1.3); }
      if(sg.url) doc.link(x, base-sg.sy.size*ASC, sg.w, sg.sy.size*SGL, {url:sg.url});
      x+=sg.w; } }
  function wrap(toks, w){ const lines=[]; let cur=[], lw=0;
    for(const tk of toks){ if(!cur.length && tk.sp) continue;
      if(!tk.sp && lw+tk.w>w && cur.length){ while(cur.length && cur[cur.length-1].sp){ lw-=cur.pop().w; } lines.push({toks:cur,w:lw}); cur=[]; lw=0; }
      cur.push(tk); lw+=tk.w; }
    while(cur.length && cur[cur.length-1].sp){ lw-=cur.pop().w; }
    if(cur.length) lines.push({toks:cur,w:lw}); return lines.length?lines:[{toks:[],w:0}]; }
  const paras=docParagraphs(m, tpl&&tpl.layout).map(([kind,runs])=>{ const k=K[kind]||{}, ind=k.list?M.indent[k.list]:null;
    const x=X0+(ind?ind.left:0), w=CW-(ind?ind.left:0);
    let lines, right=null;
    if(k.tab){ const ti=runs.findIndex(r=>r[0]==="tab"); const rt=tokens(runs.slice(ti+1)); right={toks:rt, w:rt.reduce((a,t)=>a+t.w,0)}; lines=wrap(tokens(runs.slice(0,ti)), w-right.w-12); }
    else lines=wrap(tokens(runs), w);
    const size=Math.max(...runs.filter(r=>r[0]!=="tab").map(r=>style(r[0]==="link"?"link":r[0]).size));
    return {kind, k, ind, x, w, lines, right, size, lh:size*SGL*(k.line||1)}; });
  let y=TOP, prev=null;
  const newPage=()=>{ doc.addPage(); y=TOP; };
  paras.forEach((p,ix)=>{
    const k=p.k; let gap = prev ? ((prev.k.group && prev.k.group===k.group) ? 0 : Math.max(prev.k.after||0, k.before||0)) : 0;
    let need=gap+p.lh*Math.min(p.lines.length,2);
    if(k.keep && paras[ix+1]) need=gap+p.lh*p.lines.length+(k.after||0)+paras[ix+1].lh*Math.min(paras[ix+1].lines.length,2)+(k.rule?3:0);
    if(y+need>BOT && y>TOP+1){ newPage(); gap=0; }
    y+=gap;
    p.lines.forEach((ln,li)=>{
      if(y+p.lh>BOT+0.5){ newPage(); }
      const base=y+p.size*ASC;
      let cx = k.align==="center" ? X0+(CW-ln.w)/2 : p.x;
      if(li===0 && p.ind){ const sy=style("plain"); setF(sy); doc.setTextColor("#000000"); doc.text(T(p.ind.glyph||"•"), X0+p.ind.left-p.ind.hanging, base); }
      drawSegs(segments(ln.toks), cx, base);
      if(p.right && li===p.lines.length-1) drawSegs(segments(p.right.toks), X1-p.right.w, base);
      y+=p.lh;
    });
    if(k.rule){ y+=SP.rule_gap; doc.setDrawColor(M.colors?.rule||"#999999"); doc.setLineWidth(SP.rule_width); doc.line(X0, y, X1, y); y+=SP.rule_width; }
    prev=p;
  });
  doc.setProperties({title:`${m.identity.name} — Resume`, author:m.identity.name, creator:"Resume Match Desk"});
  return {doc, font:FONT};
}

/* ------------------------------ claims: confidence, conflicts, and the projection of a backup into a bank (mirrors claims.py; export shape as rot.py cmd_export) ------------------------------
   A backup (cch-backup/1) holds the four tiers in the repo's curation shapes:
     sources[]     {id, kind: resume|linkedin|paste|answer, label, authored_at, observed_at, source_type}
     evidence[]    {id, source, source_type, channel, quote, observed_at, locator}                                    (tier 1, verbatim)
     subjects[]    {id, kind: role|engagement|education|credential|tool|expertise, key?, sort?, hidden?, tags?,
                    facts:{pred:{value, evidence:[ids], contradicting:[{value, evidence:[ids]}], resolution:{value, why, at}}}}   (tier 2)
     achievements[] {id, role, engagement?, canonical, evidence:[ids], contradicting?, resolution?, tags:{tid:w}, metrics?, variants?, confidence?, origin, retired?}
     taxonomy      {id, user_tags:{}}   settings {confidence?, length_band?, longform_band?, scoring?, caps?, persona?, engine?}
     sessions[], feedback[], outcomes[], review_log[]                                                                   (tiers 3 and 4)
   projectLibrary() turns that into the bank the engine reads; every printed line therefore traces to evidence rows. */
const CONFIDENCE_DEFAULTS = {formula_version:"1.0",
  strengths:{USER_ENTERED:1.0, INTERVIEW_RESPONSE:0.95, MASTER_RESUME:0.9, HISTORICAL_RESUME:0.8, PUBLIC_PROFILE:0.7, EXTERNAL_RESEARCH:0.6, MODEL_INFERENCE:0.5},
  corroboration_bonus:0.05, cap:0.98, verified_confidence:1.0, contradiction_penalty:0.3,
  print:{fact_min:0.6, number_min:0.7, disputed:"never", on_conflict:"print_stronger_and_warn"},
  bands:{summary_max_words:55, tagline_phrase_max_chars:60, expertise_item_max_chars:70, technology_max_chars:90, core_item_max_chars:80}};
const HUB_DEFAULTS = {
  length_band:{source:"cch-default", n:0, min:60, p10:97, p25:120, median:143, p75:160, p90:168, max:170, hard_ceiling:170},
  longform_band:{source:"cch-default", n:0, min:170, median:250, max:340, hard_ceiling:340},
  scoring:{variant_min:1.5, variant_margin:1.25, priority_bonus:1.5, metric_bonus:0.5, family_rollup:0.25, hidden_role_min:4.0},
  caps:[6,5,4,4,3,2,2,2], competency_count:16,
};
/* Deterministic: the strongest supporting source, +bonus per extra independent source type, capped; a first-hand statement verifies;
   an unresolved contradiction disputes. supports/contradicts are evidence rows; a row may carry its own `strength`. */
function confidenceFor(supports, contradicts, resolved, cfg){
  cfg=cfg||CONFIDENCE_DEFAULTS;
  if(!supports||!supports.length) return {confidence:0, basis:"no evidence", status:"active"};
  const types=new Set(supports.map(e=>e.source_type));
  let conf=Math.min(cfg.cap, Math.max(...supports.map(e=>e.strength??cfg.strengths[e.source_type]??0.5)) + cfg.corroboration_bonus*(types.size-1));
  let basis=`${supports.length} evidence, ${types.size} source type${types.size>1?"s":""}`;
  if(types.has("USER_ENTERED")){ conf=cfg.verified_confidence; basis+=", verified by you"; }
  let status="active";
  const nCon=(contradicts||[]).length;
  if(nCon && !resolved){ conf=Math.round(Math.max(0, conf-cfg.contradiction_penalty)*1000)/1000; status="disputed"; basis+=`, ${nCon} contradicting, unresolved`; }
  else if(nCon) basis+=`, ${nCon} contradicting, resolved`;
  return {confidence:Math.round(conf*1000)/1000, basis, status};
}
const DATE_RE=/^(\d{4})(?:-(\d{2}))?$/, NUMERIC_RE=/^\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*$/;
function dateParts(v){ const m=DATE_RE.exec(String(v??"").trim()); return m?[+m[1], m[2]?+m[2]:null]:null; }
/* Two values for the same fact disagree. 2024 and 2024-11 are compatible (one is coarser); 2020 and 2021 are not. */
function valuesConflict(a, b){
  if(a==null||a===""||b==null||b==="") return false;
  const da=dateParts(a), db=dateParts(b);
  if(da&&db) return da[0]!==db[0] || (da[1]!=null&&db[1]!=null&&da[1]!==db[1]);
  const sa=String(a).replace(/,/g,""), sb=String(b).replace(/,/g,"");
  if(NUMERIC_RE.test(sa)&&NUMERIC_RE.test(sb)) return Math.abs(parseFloat(sa)-parseFloat(sb))>1e-9;
  return norm(a)!==norm(b);
}
const isYear = n => /^(19|20)\d\d$/.test(n);
/* one claim from a fact: its winning value, confidence from its evidence, and the numbers those quotes state */
function claimOf(id, kind, subjectId, predicate, fact, text, ev, cfg){
  const rows=ids=>(ids||[]).map(i=>ev[i]).filter(Boolean);
  const value=fact.resolution?fact.resolution.value:fact.value;
  const sup=rows(fact.evidence).concat(fact.resolution?[{id:id+":resolution", source_type:"USER_ENTERED", quote:String(fact.resolution.value), observed_at:fact.resolution.at||null}]:[]);
  const con=(fact.contradicting||[]).flatMap(c=>rows(c.evidence));
  const {confidence, status, basis}=confidenceFor(sup.map(e=>({...e, strength:e.strength??cfg.strengths[e.source_type]??0.5})), con, !!fact.resolution, cfg);
  const numbers=new Set(numberTokens(value)); for(const e of sup) for(const n of numberTokens(e.quote)) numbers.add(n);
  const types=[...new Set(sup.map(e=>e.source_type))].sort();
  const latest=sup.map(e=>e.observed_at||e.authored_at||"").filter(Boolean).sort().pop()||null;
  return {id, kind, subject:subjectId, predicate, value, unit:null, text:text||`${predicate}: ${value}`, confidence, confidence_basis:basis, status,
    valid_from:null, valid_to:null, as_of:null, evidence:{n:sup.length, source_types:types, latest}, numbers:[...numbers].sort((a,b)=>+a-+b)};
}
/* The bank (rot-library/3) a shell hands to createEngine. taxonomy = {families, tags}; opts = {now, templateId, templateDocx}. */
function projectLibrary(backup, taxonomy, opts={}){
  const S0=backup.settings||{}, cfg={...CONFIDENCE_DEFAULTS, ...(S0.confidence||{})};
  const ev=Object.fromEntries((backup.evidence||[]).map(e=>[e.id,e]));
  const subjects=backup.subjects||[], claims=[];
  const val=f=>f?(f.resolution?f.resolution.value:f.value):null;
  const has=f=>f && val(f)!=null && val(f)!=="";
  const factClaim=(s, kind, pred, label)=>{ const f=s.facts&&s.facts[pred]; if(!has(f)) return null; const id=`${s.id}:${pred}`; claims.push(claimOf(id, kind, s.id, pred, f, `${label}: ${pred} ${val(f)}`, ev, cfg)); return id; };
  const roleSubjects=subjects.filter(s=>s.kind==="role").slice().sort((a,b)=>(a.sort??99)-(b.sort??99));
  const roles=roleSubjects.map(s=>{ const g=p=>val(s.facts&&s.facts[p]); const who=`${g("title")||s.key} at ${g("employer")||"?"}`;
    const ids=["title","employer","location","start","end"].map(p=>factClaim(s,"role_fact",p,who)).filter(Boolean);
    const start=g("start"), end=g("end"), dates=start?`${fmtDate(start)} – ${fmtDate(end)}`:(end?fmtDate(end):"");
    return {key:s.key, sort:s.sort??99, title:g("title")||"", employer:g("employer")||"", location:g("location")||null, start:start||null, end:end||null, dates,
      engagement:null, context:g("location")||null, hidden:!!s.hidden, claim_ids:ids}; });
  const engagements=subjects.filter(s=>s.kind==="engagement").map(s=>{ const g=p=>val(s.facts&&s.facts[p]); const who=g("client")||s.key;
    const ids=["client","location","start","end","commitment","subtitle"].map(p=>factClaim(s,"engagement_fact",p,who)).filter(Boolean);
    const start=g("start");
    return {key:s.key, role:s.role||(roleSubjects[0]&&roleSubjects[0].key)||null, client:g("client")||"", location:g("location")||null, start:start||null, end:g("end")||null,
      dates:start?`${fmtDate(start)} – ${fmtDate(g("end"))}`:null, commitment:g("commitment")||null, subtitle:g("subtitle")||null, needs_details:!start, ask:null, achievements:[], claim_ids:ids}; });
  const achievements=(backup.achievements||[]).filter(a=>!a.retired).map(a=>{
    const f={value:a.canonical, evidence:a.evidence||[], contradicting:a.contradicting||[], resolution:a.resolution||null};
    const c=claimOf(`ach:${a.id}`, "achievement", `ach:${a.id}`, "text", f, a.canonical, ev, cfg); claims.push(c);
    const tags=Object.fromEntries(Object.entries(a.tags||{}).filter(([t])=>taxonomy.tags[t]));
    const texts=[{id:`${a.id}:c`, kind:"canonical", angle:null, text:a.canonical, score_adj:0}]
      .concat((a.variants||[]).map((v,i)=>({id:`${a.id}:v${i}`, kind:v.kind||"learned", angle:v.angle||null, text:v.text, score_adj:v.score_adj||0})));
    const metrics=(a.metrics&&a.metrics.length)?a.metrics:[...numberTokens(a.canonical)].filter(n=>!isYear(n)).map(n=>({value:+n}));
    const eng=a.engagement||null; if(eng){ const e=engagements.find(x=>x.key===eng); if(e && !e.achievements.includes(a.id)) e.achievements.push(a.id); }
    return {id:a.id, role:a.role, engagement:eng, confidence:a.confidence||(c.evidence.source_types.includes("USER_ENTERED")?"verified":"asserted"), tags, metrics, claim_ids:[`ach:${a.id}`], texts};
  });
  const education=subjects.filter(s=>s.kind==="education").map(s=>{ const g=p=>val(s.facts&&s.facts[p]); const ids=["school","degree","date"].map(p=>factClaim(s,"education",p,g("school")||s.id)).filter(Boolean);
    return {school:g("school")||"", degree:g("degree")||"", year:g("date")||null, date_display:g("date")||null, degree_line:[g("degree"), g("date")].filter(Boolean).join(" | "), bullet_ids:[], claim_id:ids.find(i=>i.endsWith(":degree"))||ids[0]||null}; });
  const certifications=subjects.filter(s=>s.kind==="credential").map(s=>{ const g=p=>val(s.facts&&s.facts[p]); const ids=["name","issuer","date"].map(p=>factClaim(s,"credential",p,g("name")||s.id)).filter(Boolean);
    return {name:g("name")||"", issuer:g("issuer")||"", date:g("date")||null, status:null, note:g("note")||null, hidden:!!s.hidden, claim_id:ids[0]||null}; });
  const technologies=subjects.filter(s=>s.kind==="tool").map(s=>({name:val(s.facts&&s.facts.name)||"", category:"Tools", tags:s.tags||[], sort:s.sort??null, claim_id:factClaim(s,"tool","name","Tool")}));
  const competencies=subjects.filter(s=>s.kind==="expertise").map(s=>({text:val(s.facts&&s.facts.text)||"", tags:s.tags||[], sort:s.sort??null, origin:"user", claim_id:factClaim(s,"expertise","text","Skill")}));
  const identity={name:"", location:"", phone:"", email:"", links:[], ...(backup.identity||{})};
  const caps={}, priority={};
  roleSubjects.forEach((s,i)=>{ caps[s.key]=(S0.caps&&S0.caps[s.key])??HUB_DEFAULTS.caps[Math.min(i, HUB_DEFAULTS.caps.length-1)]; priority[s.key]=achievements.filter(a=>a.role===s.key&&!a.engagement).map(a=>a.id); });
  const newest=roleSubjects.length?roleSubjects[0].key:null;
  const first=(identity.name||"").trim().split(/\s+/)[0]||"the candidate";
  const settings={fallback_role:newest, default_engagement_role:newest, education_claim_default:(education[0]&&education[0].claim_id)||"edu:none:degree",
    template_id:opts.templateId||"neutral-1", edition:"hub",
    questions:{consulting:[], consulting_regex:"", engagement_tag:null},
    prompts:{persona:{name:identity.name||"the candidate", first, subject:"they", possessive:"their", possessive_cap:"Their", standard_label:"one-line accomplishment", ...(S0.persona||{})},
      bullet_example:{place:newest?"r:"+newest:"r:current", text:"Cut speed-to-lead from 26 hours to under 2 with new routing rules and a weekly SLA review.", tags:["lead-routing-sla"]},
      entry_example:{text:"Salesforce (administrator)", tags:["crm-discipline"]}},
    ...(S0.engine||{})};
  return {schema:"rot-library/3", exported_at:opts.now||new Date().toISOString(),
    tiers:{"1":"Evidence","2":"Derived knowledge","3":"Generation","4":"Feedback"},
    confidence:{formula_version:cfg.formula_version, print:cfg.print, bands:cfg.bands},
    claims, template:{id:settings.template_id, docx:opts.templateDocx||"template/docx_template.json", section_order:[]},
    identity, length_band:S0.length_band||HUB_DEFAULTS.length_band, longform_band:S0.longform_band||HUB_DEFAULTS.longform_band,
    families:taxonomy.families||{}, tags:taxonomy.tags||{}, roles, achievements, tagline_phrases:[], competencies, core_competencies:[], engagements,
    expertise_areas:[], technologies, domain_fluency:[], certifications, education, summaries:[],
    baseline:{template:settings.template_id, summary_enabled:false, section_order:[], caps, priority, engagement_caps:Object.fromEntries(engagements.map(e=>[e.key,5])),
      competency_count:S0.competency_count||HUB_DEFAULTS.competency_count, competency_order:competencies.map(c=>c.text), tagline_count:0, angle_map:{},
      scoring:{...HUB_DEFAULTS.scoring, ...(S0.scoring||{})}, settings}};
}

return {
  VERSION, SCHEMAS, createEngine,
  util: { esc, escRe, MONTHS, fmtDate, REQ_HINT, uniq, norm, splitList, PHRASE_SECTIONS, TOOL_LEXICON, isSkip, cleanBullet, cleanPhrase, splitAnswer, splitPhrases, shortRole, sectionOf, placeKey },
  qa: { NUMBER_WORDS, numberTokens, FIRST_PERSON, qaLine, blocking, answerQuotes },
  score: { coverage, matchScore, tagWeight, rankByTags },
  doc: { btext, docParagraphs, xmlEsc, rprXml, documentXml, plainText, pdfSafe, abToB64, PDF_METRICS, docxParts, buildDocx, buildPdf },
  layouts: { source: SOURCE_LAYOUT },
  claims: { CONFIDENCE_DEFAULTS, HUB_DEFAULTS, confidenceFor, valuesConflict, dateParts, claimOf, projectLibrary },
};
});
