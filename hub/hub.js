"use strict";
/* Career Companion Hub · the page. A shell around core/rot_core.js: the engine matches, selects and models; this file keeps the
   person's record in the browser (store.js), talks to Claude only through the viewer's own `sample` capability, and renders.
   Everything that touches the record writes cch-backup/1 shapes, so a backup is exactly what the core's projectLibrary reads. */
const $ = s => document.querySelector(s);
const {esc, escRe, uniq, norm, splitList, PHRASE_SECTIONS, isSkip, cleanBullet, cleanPhrase, splitAnswer, splitPhrases, shortRole, sectionOf, placeKey} = RotCore.util;
const {numberTokens, blocking, answerQuotes} = RotCore.qa;
const {plainText, abToB64} = RotCore.doc;
const {Hub, BrowserStore, clone} = CCH;
const LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname) || location.protocol==="file:";
const GUIDE_URL = "https://claude.ai/artifact/786dD7KPL85z3Fp9v4xTz8";   // hub/guide.html as published
/* Fallback until the template loads. Must equal core/layouts/neutral-1.json (tests/hub/hub.test.js checks). */
const NEUTRAL_LAYOUT = {"schema":"rot-layout/1","id":"neutral-1","sections":[{"kind":"header"},{"kind":"lines","heading":"Summary","blocks":["summary"]},{"kind":"lines","heading":"Skills","blocks":["expertise","technologies"]},{"kind":"experience","heading":"Experience"},{"kind":"engagements","heading":"Consulting & Advisory"},{"kind":"education","heading":"Education"},{"kind":"certifications","heading":"Certifications"}],"labels":{"technologies":"Tools"},"joins":{"tagline":" | ","expertise":" • ","technologies":", ","core":", "}};
const ENG_INPUTS = [["client","Client, as it prints","e.g. Regional Logistics Company (Confidential)"],["location","Location","e.g. Denver, CO"],
  ["start","Start (YYYY-MM)","e.g. 2026-05"],["end","End (YYYY-MM, blank = Present)","blank = Present"],
  ["commitment","Commitment","e.g. Part Time"],["subtitle","One-line description","e.g. Pricing and packaging review"]];
const SECTION_LABELS = {experience:"Experience entry", technology:"Tools line", expertise:"Skills line", tagline:"Tagline", competency:"Skills"};
const SAMPLE_ERR = {not_granted:"Claude isn't allowed on this page. Allow it when the page asks, or reload and try again.", sampling_disabled:"Claude isn't available for this account.", rate_limited:"Claude is busy right now. Wait a minute and try again.", invalid_json:"Claude's reply came back malformed. Try again.", prompt_too_large:"That answer is too long for one pass. Shorten it and try again.", refused:"Claude declined this one. Rephrase the answer and try again.", empty_completion:"Claude returned nothing. Add a specific and try again.", session_expired:"Your Claude session expired. Sign in again, then retry."};
const sampleErr = e => SAMPLE_ERR[e?.code] || `Claude couldn't finish (${esc(e?.code||"error")}). Try again.`;
const LINE_EDIT = {tagline:{sep:["|"], join:" | "}, expertise:{sep:["•","·"], join:" • "}, technologies:{sep:[","], join:", "}};
/* a fictional posting, so the questions can be seen without finding one first */
const SAMPLE_JD = `Director, Revenue Operations
Northgate Software · Denver, CO (hybrid) · Full-time

About Northgate
Northgate makes planning software for mid-market manufacturers. We are a Series C company with 400 employees and a 90-person go-to-market team.

What you'll do
- Own the revenue forecast: stage definitions, weekly cadence, and the accuracy the executive team and board rely on.
- Run our Salesforce instance and the systems around it (HubSpot, Outreach, Gong, Looker), including the roadmap for consolidating tools acquired through two acquisitions.
- Design territories, lead routing and SLAs for SDR and AE teams; measure speed-to-lead and conversion at every stage.
- Partner with product marketing and finance on pricing and packaging changes, including the launch of a mid-market tier.
- Build the dashboards and pipeline reviews the CRO uses every week; report on pipeline coverage and win rates.
- Lead and grow a team of analysts and administrators.

What you bring
- 6+ years in revenue operations, sales operations or a related role at a B2B SaaS company.
- Proven forecasting accuracy improvements and CRM consolidation experience.
- Salesforce administration depth; Looker or Tableau fluency; comfortable with SQL basics.
- Experience presenting to C-suite stakeholders and aligning sales, customer success and marketing.
- Bonus: pricing and packaging work, or a quota-carrying background.`;

/* The working draft (the engine's `d`) plus this page's own state */
const D = {
  jd:"", req:{}, uncatalogued:[], chosen:{}, cov:{}, score:null, runId:null, phase:"idle",
  excluded:new Set(), pinned:new Set(), textChoice:{}, edits:{}, tagline:null, compOrder:null,
  summaryOn:false, summary:null, summaryClaims:[], outcome:null,
  sectionEdits:{}, engDetails:{}, editsC:{}, excludedC:new Set(), extra:{tagline:[],expertise:[],technology:[],competency:[]},
  questions:[], newAch:[], adj:{}, inbox:[], locked:null, finalModel:null,
  sample:null, downloads:null, tpl:null, fontData:undefined, ctl1:null, ctlQ:null
};
let store=null, taxonomy=null, T=null, E=null, bankCache=null;

/* ------------------------------ small helpers ------------------------------ */
const today = () => new Date().toISOString().slice(0,10);
const slug = s => String(s||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"").slice(0,40) || "x";
const fmtBytes = n => n<1048576 ? `${Math.max(1,Math.round(n/1024))} KB` : `${(n/1048576).toFixed(1)} MB`;
const fmtWhen = s => { const d=s?new Date(s):null; return d&&!isNaN(d) ? d.toLocaleString([], {month:"short", day:"numeric", hour:"numeric", minute:"2-digit"}) : ""; };
const fmtDay = s => { const d=s?new Date(s):null; return d&&!isNaN(d) ? d.toLocaleDateString([], {month:"short", day:"numeric"}) : ""; };
const isYear = n => /^(19|20)\d\d$/.test(n);
function toast(msg){ const t=$("#toast"); t.textContent=msg; t.hidden=false; clearTimeout(toast._t); toast._t=setTimeout(()=>t.hidden=true, 3600); }
function debounce(fn, ms){ let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; }
const val = f => f ? (f.resolution ? f.resolution.value : f.value) : null;

/* ------------------------------ the record: cch-backup/1 shapes in the browser store ------------------------------ */
function writeAll(obj, quiet){ for(const [k,v] of Object.entries(obj)) store.set(k, v, true); bankCache=null; if(quiet){ renderSideSoon(); renderStats(); } else store.emit("*"); }
function ensureSource(srcs){ if(!srcs.some(s=>s.id==="src:you")) srcs.push({id:"src:you", kind:"paste", label:"Typed on this page", authored_at:today(), observed_at:today(), source_type:"USER_ENTERED"}); return srcs; }
function evRow(id, quote, locator){ return {id, source:"src:you", source_type:"USER_ENTERED", channel:"paste", quote:String(quote||""), observed_at:today(), locator}; }
/* entries are tagged the way the engine reads a posting: the taxonomy's synonyms over the text */
function tagsFor(text){ return Object.fromEntries(Object.keys(T.extractRequirements(String(text||""))).map(t=>[t,1])); }
/* the bank the engine reads, rebuilt from the record whenever it changes */
function bank(){
  if(bankCache) return bankCache;
  const B=store.snapshot();
  for(const a of B.achievements) if(!a.tags || !Object.keys(a.tags).length) a.tags=tagsFor(a.canonical);   // a loaded backup may carry untagged entries
  for(const s of B.subjects) if((s.kind==="expertise"||s.kind==="tool") && !(s.tags&&s.tags.length)){ const t=val(s.facts&&s.facts[s.kind==="tool"?"name":"text"]); if(t) s.tags=Object.keys(T.extractRequirements(t)); }   // so the Skills and Tools lines rank by the posting
  bankCache=RotCore.claims.projectLibrary(B, taxonomy, {templateDocx:"template/docx_template.json"});
  return bankCache;
}
const SET = () => bank().baseline.settings;
function adjFromFeedback(){ const adj={}; for(const f of store.get("feedback")){ const k=f.bullet_id; if(k==null) continue; adj[k]=(adj[k]||0)+(f.action==="keep"?0.3:(f.action==="drop"||f.action==="reject")?-0.6:0); } return adj; }

/* roles: one subject each, five facts sharing the typed header as their evidence row */
const roleSubjects = subs => (subs||store.get("subjects")).filter(s=>s.kind==="role").sort((a,b)=>(a.sort??99)-(b.sort??99));
function sortRoles(subs){ const g=(s,p)=>String(val(s.facts&&s.facts[p])||""); const rs=subs.filter(s=>s.kind==="role");
  rs.sort((a,b)=>{ const ea=g(a,"end")||"9999", eb=g(b,"end")||"9999"; return eb.localeCompare(ea) || g(b,"start").localeCompare(g(a,"start")); }); rs.forEach((s,i)=>{ s.sort=i; }); }
function roleQuote(f){ const g=p=>val(f[p]); return [g("title"), g("employer"), g("location"), g("start")?`${g("start")} – ${g("end")||"Present"}`:null].filter(Boolean).join(" | "); }
function addRole(){
  const subs=store.get("subjects"), ev=store.get("evidence"), srcs=ensureSource(store.get("sources"));
  const taken=new Set(subs.filter(s=>s.kind==="role").map(s=>s.key)); let n=1; while(taken.has("r"+n)) n++;
  const key="r"+n, evId=`ev:you:${key}:role`;
  ev.push(evRow(evId, "", `role ${key}`));
  const fact=v=>({value:v, evidence:[evId], contradicting:[]});
  subs.push({id:`role:${key}`, kind:"role", key, sort:-1, hidden:false, facts:{title:fact(""), employer:fact(""), location:fact(""), start:fact(null), end:fact(null)}});
  sortRoles(subs); writeAll({subjects:subs, evidence:ev, sources:srcs});
  renderRoles(); const el=$(`#roles [data-role="${key}"] input`); if(el) el.focus();
}
function setRoleFact(key, pred, value){
  const subs=store.get("subjects"), ev=store.get("evidence"); const s=subs.find(x=>x.kind==="role"&&x.key===key); if(!s) return;
  const evId=`ev:you:${key}:role`, v=value===""?null:value; s.facts=s.facts||{};
  const f=s.facts[pred]||(s.facts[pred]={value:null, evidence:[], contradicting:[]});
  const row=ev.find(e=>e.id===evId);
  if(row){ f.value=v; if(!f.evidence.includes(evId)) f.evidence.push(evId); row.quote=roleQuote(s.facts); row.observed_at=today(); }
  else if(v!==val(f)) f.resolution={value:v, why:"typed on this page", at:today()};   // a role from a loaded backup keeps its document evidence; your statement settles the value
  const structural=pred==="start"||pred==="end"; if(structural) sortRoles(subs);
  writeAll({subjects:subs, evidence:ev}, !structural); if(structural) renderRoles();
}
function setRoleHidden(key, hidden){ const subs=store.get("subjects"); const s=subs.find(x=>x.kind==="role"&&x.key===key); if(!s) return; s.hidden=!!hidden; writeAll({subjects:subs}); renderRoles(); }
function delRole(key){
  const subs=store.get("subjects").filter(s=>!(s.kind==="role"&&s.key===key)), ach=store.get("achievements"), gone=new Set(ach.filter(a=>a.role===key).map(a=>a.id));
  const ev=store.get("evidence").filter(e=>e.id!==`ev:you:${key}:role` && !gone.has(e.id.replace(/^ev:you:/,"")));
  sortRoles(subs); writeAll({subjects:subs, achievements:ach.filter(a=>a.role!==key), evidence:ev}); renderRoles(); toast("Role removed.");
}
/* accomplishment lines: the typed line is the evidence, its cleaned form is the entry */
function addLines(key, text){
  const lines=String(text||"").split(/\r?\n/).map(t=>t.replace(/^[\s•·\-*–—]+/,"").trim()).filter(t=>t.length>3);
  if(!lines.length){ toast("Paste one accomplishment per line."); return; }
  const ach=store.get("achievements"), ev=store.get("evidence"), srcs=ensureSource(store.get("sources"));
  const ids=new Set(ach.map(a=>a.id)); let n=ach.filter(a=>a.role===key).length;
  for(const t of lines){ let id; do{ id=`${key}-${++n}`; }while(ids.has(id)); ids.add(id);
    ev.push(evRow(`ev:you:${id}`, t, `role ${key}, line ${n}`));
    ach.push({id, role:key, engagement:null, canonical:cleanBullet(t), evidence:[`ev:you:${id}`], contradicting:[], tags:tagsFor(t), metrics:[], origin:"paste"}); }
  writeAll({achievements:ach, evidence:ev, sources:srcs}); renderRoles(); toast(`Added ${lines.length} entr${lines.length>1?"ies":"y"} to your record.`);
}
function setLine(id, text, clean){
  const ach=store.get("achievements"), ev=store.get("evidence"); const a=ach.find(x=>x.id===id); if(!a) return;
  const raw=String(text||"").replace(/\s+/g," ").trim(); if(!raw) return;
  const evId=`ev:you:${id}`, cleaned=clean?cleanBullet(raw):raw; let row=ev.find(e=>e.id===evId);
  if(row){ row.quote=raw; row.observed_at=today(); a.canonical=cleaned; }
  else { row=evRow(evId, raw, "edited on this page"); ev.push(row); if(!a.evidence.includes(evId)) a.evidence.push(evId); a.canonical=cleaned; a.resolution={value:cleaned, why:"typed on this page", at:today()}; }   // an entry from a loaded backup: your wording settles it
  a.tags=tagsFor(raw);
  writeAll({achievements:ach, evidence:ev}, true);
  const li=$(`#roles li[data-line-id="${CSS.escape(id)}"]`); if(li) li.querySelector(".tags").innerHTML=tagChips(a);
}
function delLine(id){ writeAll({achievements:store.get("achievements").filter(a=>a.id!==id), evidence:store.get("evidence").filter(e=>e.id!==`ev:you:${id}`)}); renderRoles(); }
function tagChips(a){
  const L=bank(), nums=[...numberTokens(a.canonical)].filter(n=>!isYear(n));
  const tags=Object.keys(a.tags||{}).map(t=>`<span class="t">${esc((L.tags[t]||{label:t}).label)}</span>`).join("");
  return (nums.length?`<span class="t n" title="Numbers this entry states">${nums.map(esc).join(" · ")}</span>`:`<span class="t" title="A number makes an entry provable and stronger in a match">no number yet</span>`)+(tags||`<span class="t">no skill tag yet</span>`);
}
/* a fact two documents disagree on: both values with their sources, and the person's pick settles it */
const monthYear = s => { const d=s?new Date(s):null; return d&&!isNaN(d) ? d.toLocaleDateString([], {month:"short", year:"numeric"}) : ""; };
function sourceLabel(evIds){ const ev=store.get("evidence"), srcs=store.get("sources"); const labels=new Set(); for(const id of evIds||[]){ const row=ev.find(e=>e.id===id); const s=row&&srcs.find(x=>x.id===row.source); const when=monthYear((s&&s.authored_at)||(row&&row.observed_at)); labels.add((s?s.label:(row?row.source:"?"))+(when?` · ${when}`:"")); } return [...labels].join(", "); }
/* what the choice implies, so the person decides on the stakes and not on which line came first */
function stakes(kind, id, pred, f){
  if(kind==="ach") return "Two documents describe the same work differently. An interviewer will ask what you personally did and decided; pick the statement you could defend in detail, because the stronger claim is worth more only if a reference would say the same. If they are two separate pieces of work, keep both.";
  if(pred==="title") return "Titles are checked against references and HR records. Use the one your employer would confirm; scope belongs in the entries beneath it.";
  if(pred==="employer") return "Two names for one employer usually mean a rename or an acquisition. Use the name a reference call would recognize.";
  if(pred==="start"||pred==="end") return dateStakes(id, pred, f);
  if(pred==="school"||pred==="degree"||pred==="date") return "Education details are verified in background checks. Use what the registrar would confirm.";
  return "Pick the value you can back with a record.";
}
function dateStakes(id, pred, f){
  const s=store.get("subjects").find(x=>x.id===id); if(!s) return "";
  const others=roleSubjects().filter(r=>r.key!==s.key), ym=(v,end)=>v?(String(v).length===4?`${v}-${end?"12":"01"}`:String(v)):null;
  const months=(a,b)=>{ const [ay,am]=a.split("-").map(Number), [by,bm]=b.split("-").map(Number); return (by-ay)*12+(bm-am); };
  const notes=[];
  for(const v of [f.value, ...f.contradicting.map(c=>c.value)]){
    if(pred==="end"){ const e=ym(v,true)||"9999-12", mine=ym(val(s.facts.start))||"0000-01";
      const next=others.map(r=>({r, s:ym(val(r.facts&&r.facts.start))})).filter(x=>x.s && x.s>mine).sort((a,b)=>a.s.localeCompare(b.s))[0]; if(!next) continue;
      const m=months(e, next.s), who=val(next.r.facts.employer)||next.r.key;
      notes.push(`${v==null?"Present":v} ${m<0?`overlaps ${who} by ${-m} month${-m===1?"":"s"}`:(m>1?`leaves a ${m}-month gap before ${who}`:`runs straight into ${who}`)}`); }
    else { const st=ym(v); if(!st) continue; const prev=others.map(r=>({r, e:ym(val(r.facts&&r.facts.end),true)||"9999-12", s:ym(val(r.facts&&r.facts.start))})).filter(x=>x.s && x.s<st).sort((a,b)=>b.s.localeCompare(a.s))[0]; if(!prev) continue;
      const m=months(prev.e, st), who=val(prev.r.facts.employer)||prev.r.key;
      notes.push(`${v} ${m<0?`overlaps ${who} by ${-m} month${-m===1?"":"s"}`:(m>1?`leaves a ${m}-month gap after ${who}`:`follows ${who} directly`)}`); }
  }
  return (notes.length?`What each choice implies: ${notes.join("; ")}. `:"")+"Dates set the order of your roles and any gap a reader will ask about; use the dates on the offer letter or in the HR system.";
}
function conflictHtml(kind, id, pred, f){
  if(!f || !(f.contradicting||[]).length || f.resolution) return "";
  const cur=f.value, show=v=>v==null||v===""?"Present":String(v);
  return `<div class="conflict" role="group"><span>Two sources disagree${pred?` on <b>${esc(pred)}</b>`:""}. Which is right?</span><span class="hint">${esc(stakes(kind, id, pred, f))}</span>
    <div class="cv"><b>${esc(show(cur))}</b><span class="src">${esc(sourceLabel(f.evidence))}</span><button data-resolve="${kind}|${esc(id)}|${esc(pred||"")}|0">Use this</button></div>
    ${f.contradicting.map((c,i)=>`<div class="cv"><b>${esc(show(c.value))}</b><span class="src">${esc(sourceLabel(c.evidence))}</span><button data-resolve="${kind}|${esc(id)}|${esc(pred||"")}|${i+1}">Use this</button>${kind==="ach"?`<button class="ghost" data-split="${esc(id)}|${i}" title="Keep both as separate entries">They are different things</button>`:""}</div>`).join("")}</div>`;
}
function resolveFact(kind, id, pred, pick){
  const subs=store.get("subjects"), ach=store.get("achievements"), at=today();
  if(kind==="role"||kind==="sub"){ const s=subs.find(x=>x.id===id); const f=s&&s.facts&&s.facts[pred]; if(!f) return; const v=pick===0?f.value:f.contradicting[pick-1].value; f.resolution={value:v, why:"picked in review", at}; writeAll({subjects:subs}); }
  else { const a=ach.find(x=>x.id===id); if(!a) return; const v=pick===0?a.canonical:a.contradicting[pick-1].value; a.resolution={value:v, why:"picked in review", at}; a.canonical=v; a.tags=tagsFor(v); writeAll({achievements:ach}); }
  renderRoles(); toast("Settled. The fact prints again.");
}
function splitAch(id, i){
  const ach=store.get("achievements"), a=ach.find(x=>x.id===id); if(!a||!a.contradicting||!a.contradicting[i]) return;
  const c=a.contradicting.splice(i,1)[0]; let n=ach.filter(x=>x.role===a.role).length, nid; do{ nid=`${a.role}-${++n}`; }while(ach.some(x=>x.id===nid));
  ach.push({id:nid, role:a.role, engagement:a.engagement||null, canonical:c.value, evidence:[...c.evidence], contradicting:[], tags:tagsFor(c.value), metrics:[], origin:"intake"});
  writeAll({achievements:ach}); renderRoles(); toast("Kept as two entries.");
}
function renderRoles(){
  const subs=store.get("subjects"), ach=store.get("achievements"), roles=roleSubjects(subs);
  $("#roles").innerHTML = roles.length ? roles.map(s=>{ const g=p=>val(s.facts&&s.facts[p])||""; const lines=ach.filter(a=>a.role===s.key&&!a.engagement).sort((a,b)=>a.id.localeCompare(b.id, undefined, {numeric:true}));
    const conflicts=["title","employer","location","start","end"].map(p=>conflictHtml("role", s.id, p, s.facts&&s.facts[p])).join("");
    return `<div class="role" data-role="${esc(s.key)}">
      <div class="head">
        <label class="f">Title<input type="text" data-fact="title" value="${esc(g("title"))}" placeholder="Director of Revenue Operations"></label>
        <label class="f">Employer<input type="text" data-fact="employer" value="${esc(g("employer"))}" placeholder="Company"></label>
        <label class="f">Location<input type="text" data-fact="location" value="${esc(g("location"))}" placeholder="City, ST"></label>
        <label class="f">Start<input type="month" data-fact="start" value="${esc(g("start"))}"></label>
        <label class="f">End (blank = Present)<input type="month" data-fact="end" value="${esc(g("end"))}"></label>
      </div>
      ${conflicts}
      <ul class="lines">${lines.map(a=>`<li data-line-id="${esc(a.id)}"><input type="text" data-line value="${esc(a.canonical)}" aria-label="Accomplishment"><button class="ghost" data-del-line="${esc(a.id)}" title="Remove this entry">Remove</button><div class="tags">${tagChips(a)}</div>${a.contradicting&&a.contradicting.length&&!a.resolution?`<div style="grid-column:1 / 3">${conflictHtml("ach", a.id, "", {value:a.canonical, evidence:a.evidence, contradicting:a.contradicting, resolution:a.resolution})}</div>`:""}</li>`).join("")}</ul>
      <label class="f">Add accomplishments the document missed, one per line<textarea data-paste rows="2" placeholder="Cut speed-to-lead from 26 hours to under 2 with new routing rules.&#10;Grew partner-sourced pipeline 40% year over year."></textarea></label>
      <div class="row"><button data-addlines>Add these lines</button><label class="hint"><input type="checkbox" data-hidden ${s.hidden?"checked":""}> Earlier role: print only when a posting calls for it</label><button class="ghost danger" data-del-role>Remove role</button></div>
    </div>`; }).join("") : `<p class="hint">No roles yet. Scan a resume above and they appear here, or add one by hand.</p>`;
}
/* after a scan lands: bring the roles panel into view and say what just arrived */
function revealRoles(html){ const p=$("#pRoles"), n=$("#rolesNote"); if(html){ n.innerHTML=html; n.hidden=false; } p.classList.remove("flash"); void p.offsetWidth; p.classList.add("flash"); p.scrollIntoView({behavior:"smooth", block:"start"}); }
/* education, certifications, skills, tools: one subject each */
function addSubject(kind, prefix, facts, quote, locator){
  const subs=store.get("subjects"), ev=store.get("evidence"), srcs=ensureSource(store.get("sources"));
  let id=`${prefix}:${slug(Object.values(facts)[0])}`; while(subs.some(s=>s.id===id)) id+="-2";
  const evId=`ev:you:${id}`; ev.push(evRow(evId, quote, locator));
  const F={}; for(const [k,v] of Object.entries(facts)) F[k]= v ? {value:v, evidence:[evId], contradicting:[]} : {value:null, evidence:[], contradicting:[]};
  subs.push({id, kind, facts:F}); writeAll({subjects:subs, evidence:ev, sources:srcs}); return id;
}
function delSubject(id){ writeAll({subjects:store.get("subjects").filter(s=>s.id!==id), evidence:store.get("evidence").filter(e=>e.id!==`ev:you:${id}`)}); renderLists(); }
function addEdu(){ const school=$("#eduSchool").value.trim(), degree=$("#eduDegree").value.trim(), year=$("#eduYear").value.trim(); if(!school){ toast("Enter the school."); return; }
  addSubject("education", "edu", {school, degree, date:year}, [school, degree, year].filter(Boolean).join(" | "), "education"); $("#eduSchool").value=$("#eduDegree").value=$("#eduYear").value=""; renderLists(); }
function addCert(){ const name=$("#certName").value.trim(), issuer=$("#certIssuer").value.trim(), year=$("#certYear").value.trim(); if(!name){ toast("Enter the certification."); return; }
  addSubject("credential", "cred", {name, issuer, date:year}, [name, issuer, year].filter(Boolean).join(" | "), "certification"); $("#certName").value=$("#certIssuer").value=$("#certYear").value=""; renderLists(); }
function saveLists(){
  const subs=store.get("subjects"), ev=store.get("evidence"), srcs=ensureSource(store.get("sources"));
  const apply=(kind, pred, text, prefix)=>{ const want=uniq(splitList(text, [",","\n","•"]).map(x=>x.trim()).filter(Boolean)), have=subs.filter(s=>s.kind===kind), keep=new Set();
    want.forEach((t,i)=>{ let s=have.find(x=>norm(val(x.facts&&x.facts[pred]))===norm(t));
      if(!s){ let id=`${prefix}:${slug(t)}`; while(subs.some(x=>x.id===id)) id+="-2"; const evId=`ev:you:${id}`; ev.push(evRow(evId, t, kind));
        s={id, kind, sort:i, tags:Object.keys(T.extractRequirements(t)), facts:{[pred]:{value:t, evidence:[evId], contradicting:[]}}}; subs.push(s); }
      s.sort=i; keep.add(s.id); });
    for(let i=subs.length-1;i>=0;i--) if(subs[i].kind===kind && !keep.has(subs[i].id)) subs.splice(i,1); };
  apply("expertise","text",$("#skills").value,"expertise"); apply("tool","name",$("#tools").value,"tool");
  writeAll({subjects:subs, evidence:ev, sources:srcs}); renderLists(); $("#listsNote").textContent="Saved."; toast("Skills and tools saved.");
}
function renderLists(){
  const subs=store.get("subjects"), g=(s,p)=>val(s.facts&&s.facts[p])||"";
  $("#eduList").innerHTML=subs.filter(s=>s.kind==="education").map(s=>`<li><span>${esc([g(s,"school"), [g(s,"degree"), g(s,"date")].filter(Boolean).join(" | ")].filter(Boolean).join(" — "))}</span><button class="ghost" data-del-subject="${esc(s.id)}">Remove</button></li>`).join("");
  $("#certList").innerHTML=subs.filter(s=>s.kind==="credential").map(s=>`<li><span>${esc([g(s,"name"), g(s,"issuer"), g(s,"date")].filter(Boolean).join(" — "))}</span><button class="ghost" data-del-subject="${esc(s.id)}">Remove</button></li>`).join("");
  const bySort=(a,b)=>(a.sort??99)-(b.sort??99);
  if(document.activeElement!==$("#skills")) $("#skills").value=subs.filter(s=>s.kind==="expertise").sort(bySort).map(s=>g(s,"text")).filter(Boolean).join(", ");
  if(document.activeElement!==$("#tools")) $("#tools").value=subs.filter(s=>s.kind==="tool").sort(bySort).map(s=>g(s,"name")).filter(Boolean).join(", ");
}
function renderIdentity(){ const i=store.get("identity"); if(document.activeElement&&document.activeElement.closest("#pIdentity")) return;
  $("#idName").value=i.name||""; $("#idLoc").value=i.location||""; $("#idPhone").value=i.phone||""; $("#idEmail").value=i.email||"";
  $("#idLinkedin").value=((i.links||[]).find(l=>/linkedin/i.test((l.label||"")+(l.url||"")))||{}).url||""; }
function saveIdentityNow(){ const url=$("#idLinkedin").value.trim(); const i={...store.get("identity"), name:$("#idName").value.trim(), location:$("#idLoc").value.trim(), phone:$("#idPhone").value.trim(), email:$("#idEmail").value.trim()};
  i.links=(i.links||[]).filter(l=>!/linkedin/i.test((l.label||"")+(l.url||""))); if(url) i.links.unshift({label:"LinkedIn", url}); store.set("identity", i, true); bankCache=null; renderSideSoon(); renderStats(); }
const saveIdentity=debounce(saveIdentityNow, 400);

/* readiness: what the record needs before a match is worth reading */
function readiness(){
  const L=bank(), i=L.identity, ach=L.achievements.filter(a=>a.role!=="education"), y=new Date().getFullYear();
  const roles=L.roles, recent=roles.filter(r=>!r.hidden && (!r.end || +String(r.end).slice(0,4)>=y-6));
  const withNum=ach.filter(a=>[...numberTokens(a.texts[0].text)].some(n=>!isYear(n))).length, disputed=L.claims.filter(c=>c.status==="disputed").length;
  return [
    {ok:!!(i.name&&i.email), text:"Your name and email are entered"},
    {ok:roles.length>0 && roles.every(r=>r.title&&r.employer&&r.start), text:roles.length?"Every role has a title, employer and start date":"At least one role"},
    {ok:recent.length>0 && recent.every(r=>ach.filter(a=>a.role===r.key).length>=3), text:"Each recent role has at least three accomplishments"},
    {ok:ach.length>0 && withNum/ach.length>=0.5, text:`At least half of your accomplishments state a number (${ach.length?Math.round(100*withNum/ach.length):0}%)`},
    {ok:L.competencies.length>=3 && L.technologies.length>=3, text:"Three or more skills and three or more tools listed"},
    {ok:disputed===0, text:disputed?`${disputed} fact${disputed>1?"s":""} in conflict, held back from printing until settled`:"No facts in conflict"},
  ];
}
function renderReady(){ const R=readiness(), n=R.filter(x=>x.ok).length; $("#readyMeter").style.width=Math.round(100*n/R.length)+"%";
  $("#readyList").innerHTML=R.map(x=>`<li class="${x.ok?"ok":"no"}"><span class="k">${x.ok?"✓":"○"}</span><span>${esc(x.text)}</span></li>`).join("");
  $("#readyHint").textContent = n===R.length ? "Ready. Paste a posting under Match a posting." : (n>=3 ? "Good enough to try a posting; the rest sharpens the match." : "Add your roles and a few lines each, then match a posting."); }
function tiersHtml(){
  const L=bank(), cl=L.claims, disputed=cl.filter(c=>c.status==="disputed").length, avg=cl.length?(cl.reduce((a,c)=>a+(c.confidence||0),0)/cl.length):0;
  const ev=store.get("evidence"), srcs=store.get("sources"), fb=store.get("feedback"), oc=store.get("outcomes");
  const m=L.roles.length?E.resumeModel(D):null, traced=m?Object.values(m.trace).filter(v=>v.length).length:0, total=m?Object.keys(m.trace).length:0;
  const k=fb.filter(f=>f.action==="keep").length, d=fb.filter(f=>f.action==="drop"||f.action==="reject").length, e=fb.filter(f=>f.action==="edit").length;
  return [["1 · Evidence", `${ev.length}`, `verbatim lines from ${srcs.length} source${srcs.length===1?"":"s"}: what you typed, pasted or answered`],
    ["2 · Derived", `${cl.length}`, `claims · ${disputed} disputed · average confidence ${avg.toFixed(2)}`],
    ["3 · Generation", `${traced}/${total}`, `lines on the current draft traced to claims · prompts ${Object.values(E.prompts.VERSIONS).join(", ")}`],
    ["4 · Feedback", `${k+d+e}`, `${k} kept · ${d} dropped · ${e} edited · ${oc.length} outcome${oc.length===1?"":"s"} recorded`]]
    .map(([t,b,s])=>`<div class="tier"><span class="tn">${esc(t)}</span><b>${esc(b)}</b><span class="hint">${esc(s)}</span></div>`).join("");
}
const renderSideSoon=debounce(()=>{ if(Hub.active==="evidence"){ renderReady(); $("#tiers").innerHTML=tiersHtml(); } }, 500);
function renderStats(){
  const L=bank(), sess=Object.keys(store.get("sessions")).length, meta=store.get("meta"), used=store.usage(), disputed=L.claims.filter(c=>c.status==="disputed").length;
  $("#stats").innerHTML=[
    `<span class="chip"><b>${L.roles.length}</b> role${L.roles.length===1?"":"s"}</span>`, `<span class="chip"><b>${L.achievements.length}</b> entries</span>`,
    `<span class="chip"><b>${L.claims.length}</b> claims${disputed?` · <b>${disputed}</b> disputed`:""}</span>`, `<span class="chip"><b>${sess}</b> posting${sess===1?"":"s"}</span>`,
    `<span class="chip ${used>3.5e6?"warn":""}"><b>${fmtBytes(used)}</b> in this browser</span>`,
    `<span class="chip ${D.sample?"ok":"warn"}" title="${D.sample?"Questions, conversions and polish use Claude on your own account.":"Without Claude the page still matches, asks template questions and builds files; open it in Claude and allow it for the rest."}">${D.sample?"Claude on":"Claude off"}</span>`,
    (L.achievements.length&&!meta.last_backup_at)?`<span class="chip warn">no backup yet</span>`:(meta.last_backup_at?`<span class="chip">backup ${esc(fmtDay(meta.last_backup_at))}</span>`:"")
  ].join("");
}

/* ------------------------------ the draft: match, sheet, questions ------------------------------ */
function evidenceChip(claimIds, fresh){
  if(fresh) return `<span class="ev you" title="From your answer on this posting. It joins your record when you download the resume.">your answer</span>`;
  const c=(claimIds||[]).map(id=>E.claimById(id)).find(Boolean); if(!c||!c.evidence) return "";
  const kinds=(c.evidence.source_types||[]).map(t=>({USER_ENTERED:"you",MASTER_RESUME:"resume",HISTORICAL_RESUME:"resumes",PUBLIC_PROFILE:"LinkedIn",INTERVIEW_RESPONSE:"answers",MODEL_INFERENCE:"inferred"})[t]||t.toLowerCase()).join(", ");
  return `<span class="ev" title="${esc(`${c.evidence.n} evidence line${c.evidence.n===1?"":"s"} (${kinds}) · confidence ${c.confidence} · ${c.status}`)}">${c.evidence.n} src · ${c.confidence}</span>`;
}
function renderMatch(){
  const req=D.req, cov=D.cov, tags=bank().tags, pct=D.score==null?"–":Math.round(D.score*100);
  $("#score").innerHTML=`${pct}<small>%</small>`; $("#meter").style.width=(D.score==null?0:Math.round(D.score*100))+"%";
  const rows=Object.entries(req).sort((a,b)=>b[1].weight-a[1].weight).map(([t,r])=>{ const c=cov[t]||0, st=c>=0.8?["ok","proven"]:(c>0?["warn","partial"]:["gap","gap"]);
    return `<div class="req" role="listitem"><span class="pill ${st[0]}">${st[1]}</span><span class="lbl" title="${esc(r.phrases.join(", "))}">${esc((tags[t]||{label:t}).label)} <em>· ${esc(r.phrases.slice(0,3).join(", "))}</em></span><span class="w">${r.weight.toFixed(1)}</span></div>`; });
  for(const u of D.uncatalogued) rows.push(`<div class="req" role="listitem"><span class="pill gap">new</span><span class="lbl" title="Not in the skill taxonomy yet">${esc(u.phrase)} <em>· not in taxonomy</em></span><span class="w">${(+u.weight||1).toFixed(1)}</span></div>`);
  $("#reqs").innerHTML=rows.join("") || `<p class="hint">No requirements detected yet.</p>`;
  const held=E.disputedAchievements().size, hn=$("#heldNote"); hn.hidden=!held;
  if(held) hn.innerHTML=`<b>${held} entr${held===1?"y is":"ies are"} held back</b> until you settle the disagreement under Your evidence. A statement two documents make differently never prints on its own. <button class="ghost" data-goto="evidence">Go and decide</button>`;
  const phrases=[...new Set(Object.values(req).flatMap(r=>r.phrases))].sort((a,b)=>b.length-a.length); let h=esc(D.jd);
  if(phrases.length){ const re=new RegExp("(?<![A-Za-z0-9-])("+phrases.map(p=>escRe(esc(p))).join("|")+")(?![A-Za-z0-9])","gi"); h=h.replace(re,"<mark>$1</mark>"); }
  $("#jdview").innerHTML=h;
}
const layout = () => (D.tpl&&D.tpl.layout)||NEUTRAL_LAYOUT;
function renderSheet(){
  const L=bank(), Ly=layout(), J={...RotCore.layouts.source.joins, ...(Ly.joins||{})}, LB={...RotCore.layouts.source.labels, ...(Ly.labels||{})};
  const band=L.length_band, lband=L.longform_band||{hard_ceiling:340}, final=D.phase==="final", badge=$("#phaseBadge");
  if(!L.roles.length){ $("#sheet").innerHTML=`<p class="empty">Your draft appears here. Add a role and a few accomplishments under <b>Your evidence</b>, or load the example person, then paste a posting.</p>`; badge.textContent="EMPTY"; badge.classList.remove("final"); return; }
  const m=E.resumeModel(D);
  const ctl=(acts,aid,extra="")=>`<span class="ctl">${acts.map(([a,l,t])=>`<button data-act="${a}" data-aid="${esc(aid)}" title="${esc(t)}">${l}</button>`).join("")}${extra}</span>`;
  const ROLE_ACTS=[["keep","Keep","Keep: pin it and raise its future score"],["swap","Swap","Swap for the next-best entry in this role"],["drop","Drop","Drop: remove it and lower its future score"],["polish","Polish","Polish: Claude tightens it with the same facts"]];
  const C_ACTS=[["dropc","Drop","Leave it out of this section for this posting"],["polishc","Polish","Polish: Claude tightens it with the same facts"]];
  const bullet=(b,kind,sec)=>{ const n=b.text.length, ceil=sec==="c"?lband.hard_ceiling:band.hard_ceiling;
    const fi=b.fresh ? D.newAch.findIndex(x=>(x.ach&&x.ach.id===b.aid)||(x.attach===b.aid&&x.text&&x.text.id===b.tid)) : -1;
    const mv=fi>=0 ? `<select data-mv="${fi}" aria-label="Move this entry under another role" title="Move this answer under another role">${placeOptions(placeKey(D.newAch[fi]), "Move to…")}</select>` : "";
    return `<p class="k-${kind} ${b.fresh?"new":""}"><span class="bt" contenteditable="true" spellcheck="true" data-sec="${sec}" data-aid="${esc(b.aid)}">${esc(b.text)}</span><span class="cc ${n>ceil?"over":""}" title="characters (ceiling ${ceil})">${n}</span>${evidenceChip(b.claim_ids,b.fresh)}${ctl(sec==="c"?C_ACTS:ROLE_ACTS,b.aid,mv)}</p>`; };
  const ln=(line, text, title, extra="")=>`<span class="ln" contenteditable="true" spellcheck="true" data-line="${line}"${extra} title="${esc(title)}">${esc(text)}</span>`;
  const i=m.identity, H=[], has={summary:!!m.summary, tagline:(m.tagline||[]).length>0, expertise:(m.expertise||[]).length>0, technologies:(m.technologies||[]).length>0};
  for(const sec of Ly.sections){
    if(sec.kind==="header"){
      H.push(`<p class="k-name">${esc(i.name||"Your name")}</p>`);
      H.push(`<p class="k-contact">${esc([i.location,i.phone,i.email].filter(Boolean).join(" | "))}${(i.links||[]).map(l=>` | <a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join("")}</p>`);
    } else if(sec.kind==="lines"){
      const blocks=sec.blocks||[]; if(!sec.always && !blocks.some(b=>has[b])) continue;
      H.push(`<p class="k-heading">${esc(sec.heading)}</p>`);
      for(const b of blocks){
        if(b==="summary"&&has.summary) H.push(`<p class="k-summary">${ln("summary", m.summary, "Summary paragraph, written from the claims on this draft")}${evidenceChip(D.summaryClaims,false)}</p>`);
        else if(b==="tagline"&&has.tagline) H.push(`<p class="k-tagline">${ln("tagline", m.tagline.join(J.tagline), "Edit freely; separate phrases with |")}</p>`);
        else if(b==="expertise"&&has.expertise) H.push(`<p class="k-expertise">${ln("expertise", m.expertise.join(J.expertise), "Your skills line. Edit freely; separate items with •")}</p>`);
        else if(b==="technologies"&&has.technologies) H.push(`<p class="k-tech_line"><span class="k-tech_label">${esc(LB.technologies)}:</span> ${ln("technologies", m.technologies.join(J.technologies), "Separate tools with commas")}</p>`);
      }
    } else if(sec.kind==="experience"){
      H.push(`<p class="k-heading">${esc(sec.heading)}</p>`);
      for(const r of m.roles){
        H.push(`<p class="k-role_header"><span>${esc(`${r.title} | ${r.employer} |`)}</span><span class="dt">${esc(r.dates)}</span></p>`);
        if(r.context) H.push(`<p class="k-role_context">${esc(r.context)}</p>`);
        r.bullets.forEach((b,k)=>H.push(bullet(b, k===r.bullets.length-1?"bullet_last":"bullet", "r")));
      }
    } else if(sec.kind==="engagements"){
      if(!m.engagements.length) continue;
      H.push(`<p class="k-heading">${esc(sec.heading)}</p>`);
      for(const e of m.engagements){
        H.push(`<p class="k-eng_header"><b>${esc(e.client)}</b>${e.location?` <b><i>| ${esc(e.location)} |</i></b>`:""}${e.dates?` <b>${e.location?"":"| "}${esc(e.dates)}</b>`:""}${e.commitment?` (${esc(e.commitment)})`:""}</p>`);
        if(e.subtitle) H.push(`<p class="k-eng_subtitle">${esc(e.subtitle)}</p>`);
        e.bullets.forEach((b,k)=>H.push(bullet(b, k===e.bullets.length-1?"eng_bullet_last":"eng_bullet", "c")));
      }
    } else if(sec.kind==="education"){
      if(!m.education.length) continue;
      H.push(`<p class="k-heading">${esc(sec.heading)}</p>`);
      for(const e of m.education) H.push(`<p class="k-school">${esc(e.school)}</p><p class="k-degree">${esc(e.degree_line)}</p>`);
    } else if(sec.kind==="certifications"){
      if(!m.certifications.length) continue;
      H.push(`<p class="k-heading">${esc(sec.heading)}</p>`);
      for(const c of m.certifications) H.push(`<p class="k-cert"><b>${esc(c.name)}</b>${c.issuer?` — ${esc(c.issuer)}`:""}${c.note?` <i style="color:#404040">(${esc(c.note)})</i>`:""}</p>`);
    } else if(sec.kind==="core_competencies"){
      if(!m.core_competencies.length) continue;
      H.push(`<p class="k-heading">${esc(sec.heading)}</p>`);
      for(const a of m.core_competencies) H.push(`<p class="k-comp"><b>${esc(a.label)}:</b> ${ln("core", a.items.join(J.core), "Separate items with commas", ` data-area="${esc(a.label)}"`)}</p>`);
    }
  }
  $("#sheet").innerHTML=H.join("");
  badge.textContent = final ? "FINAL" : (D.phase==="idle"?"BASELINE":"DRAFT"); badge.classList.toggle("final", final);
}
function placeOptions(cur, lead){
  const groups=E.placeGroups(D);
  if(cur && !groups.some(([,l])=>l.some(([v])=>v===cur))){ const p=E.parsePlace(cur); if(p) groups.unshift(["Current", [[cur, E.placeName(D, p)]]]); }
  const opt=([v,l])=>`<option value="${esc(v)}"${v===cur?(lead?" disabled":" selected"):""}>${esc(l)}</option>`;
  return (lead?`<option value="" selected>${esc(lead)}</option>`:"") + groups.map(([g,l])=>`<optgroup label="${esc(g)}">${l.map(opt).join("")}</optgroup>`).join("");
}
function sectionLabel(q){ const s=sectionOf(q); if(s==="engagement"){ const e=E.engByKey(q.engagement); return "Consulting engagement"+(e?` · ${e.client}`:""); } return SECTION_LABELS[s]||"Experience entry"; }
function renderQuestions(){
  const L=bank(), roles=L.roles.filter(r=>!r.hidden||D.chosen[r.key]);
  $("#questions").innerHTML = D.questions.map((q,ix)=>{
    const sec=sectionOf(q), ph=PHRASE_SECTIONS[sec];
    const convLabel = !D.sample ? (ph?"Split into items":"Split into entries") : (q.bullets?.length ? "Re-polish with Claude" : (ph ? "Turn into entries with Claude" : "Turn into resume entries with Claude"));
    let form="";
    if(sec==="engagement"){ const e=E.engState(D, E.engByKey(q.engagement)||{}), f={...e, ...(q.fields||{})};
      form=`<div class="row2">${ENG_INPUTS.map(([k,label,phd])=>`<label class="f" for="ef${ix}-${k}">${label}<input type="text" id="ef${ix}-${k}" data-ef="${ix}:${k}" value="${esc(f[k]||"")}" placeholder="${esc(phd)}"></label>`).join("")}</div>`; }
    const lim = ph ? ph.max : (sec==="engagement" ? (L.longform_band?.hard_ceiling||340) : L.length_band.hard_ceiling);
    const dflt=placeKey(E.defaultPlace(q));
    const items = q.bullets?.length ? `<ul class="qb">${q.bullets.map((b,bi)=>{ const blk=blocking(b.qa), pl=ph?null:E.bulletPlace(q,b), pk=pl?placeKey(pl):"";
      const where = pl ? `<label class="bpl" for="bpl${ix}-${bi}"><span class="lb">Goes under</span><select id="bpl${ix}-${bi}" data-bplace="${ix}:${bi}" class="${pk!==dflt?"alt":""}" title="The role this entry describes">${placeOptions(pk)}</select></label>` : "";
      return `<li><input type="checkbox" id="bon${ix}-${bi}" data-bon="${ix}:${bi}" ${b.on&&!blk.length?"checked":""} ${blk.length?"disabled":""} aria-label="Use this entry"><textarea id="btx${ix}-${bi}" data-btxt="${ix}:${bi}" rows="${ph?1:2}" class="${blk.length?"blocked":""}" aria-label="Entry text">${esc(b.text)}</textarea><span class="cc ${b.text.length>(ph?ph.max:L.length_band.hard_ceiling)?"over":""}" id="bcc${ix}-${bi}">${b.text.length}</span>${where}${b.longform&&(!pl||pl.engagement)?`<span class="lf">Long form (${b.longform.length} chars): ${esc(b.longform)}</span>`:""}${blk.length?`<span class="lf err" id="bqa${ix}-${bi}">Not printable yet: ${esc(blk.join("; "))}. Edit the text, or add that fact to your answer and re-polish.</span>`:""}</li>`; }).join("")}</ul>` : "";
    return `
    <div class="q"><div class="qh"><span class="qn">${ix+1}</span><p>${esc(q.question)}</p></div>
      <div class="meta"><span class="sec">${esc(sectionLabel(q))}</span>${q.why?`<span class="why">${esc(q.why)}</span>`:""}</div>
      ${form}
      <textarea id="ans${ix}" data-ix="${ix}" placeholder="${esc(q.hint||(ph?ph.hint:(sec==="engagement"?"What you did for this client: bullet points are fine (scope, method, measurable result). Leave blank to skip.":"Bullet points are fine: what you did, the scope, the measurable result. Leave blank to skip.")))}">${esc(q.answer||"")}</textarea>
      <div class="meta">${L.tags[q.tag]?`<span>Proves: <b>${esc(L.tags[q.tag].label)}</b></span>`:""}
        ${sec==="experience"?`<label for="role${ix}"><span class="lb">${q.bullets?.length?"Default role":"Goes under"}</span><select id="role${ix}" data-ix="${ix}" title="The role this answer is mostly about. Each entry it becomes can go under its own role.">${roles.map(r=>`<option value="${esc(r.key)}" ${r.key===q.role?"selected":""}>${esc(shortRole(r))}</option>`).join("")}</select></label>`:`<span>Limit: ${lim} characters per entry</span>`}</div>
      <div class="qa-row"><button class="ghost" data-conv="${ix}" ${q.busy?"disabled":""}>${convLabel}</button>${q.busy?`<span class="spin" aria-hidden="true"></span><span class="hint">Claude is writing…</span>`:""}${q.note?`<span class="hint">${esc(q.note)}</span>`:""}</div>
      ${items}
    </div>`; }).join("");
  $("#finalBtn").disabled = !D.questions.length || D.phase==="finalizing";
  $("#polishAllBtn").hidden = !D.questions.length || !D.sample;
}
function renderAll(){ renderMatch(); renderSheet(); renderQuestions(); renderStats(); }

/* ------------------------------ flow ------------------------------ */
function lockCurrent(){ D.locked=Object.fromEntries(Object.entries(D.chosen).map(([r,items])=>[r, items.map(i=>i.a.id)])); }
function recompute(){ Object.assign(D, E.compute(D, D.req)); renderMatch(); renderSheet(); }
function resetPosting(){ Object.assign(D,{excluded:new Set(), pinned:new Set(), textChoice:{}, edits:{}, tagline:null, compOrder:null, summaryOn:false, summary:null, summaryClaims:[], outcome:null, finalModel:null,
  sectionEdits:{}, engDetails:{}, editsC:{}, excludedC:new Set(), extra:{tagline:[],expertise:[],technology:[],competency:[]}, questions:[], newAch:[]}); $("#sumToggle").checked=false; }
function logFeedback(action, aid, t){
  const rec={run_id:D.runId||null, achievement_id:aid, bullet_id:t?.tid??null, action, text:t?.text||null, created:new Date().toISOString()};
  if(t?.tid!=null){ if(action==="keep") D.adj[t.tid]=(D.adj[t.tid]||0)+0.3; if(action==="drop") D.adj[t.tid]=(D.adj[t.tid]||0)-0.6; }
  const fb=store.get("feedback"); fb.push(rec); store.set("feedback", fb, true);
}
async function doMatch(){
  const jd=$("#jd").value.trim();
  if(!bank().roles.length){ toast("Add at least one role with a few accomplishments first."); Hub.show("evidence"); return; }
  if(jd.length<80){ $("#jdHint").textContent="Paste the full posting (at least a few lines) to match against."; return; }
  $("#jdHint").textContent=""; D.ctl1?.abort(); D.ctlQ?.abort();
  resetPosting();
  Object.assign(D,{locked:null, jd, req:E.extractRequirements(jd), uncatalogued:[], phase:"draft", runId:"run-"+Date.now().toString(36)});
  $("#restoreNote").hidden=true; $("#syncNote").textContent="";
  recompute(); persist(true);
  if(D.sample) claudeTailor(); else useQuickQuestions("Claude isn't available in this view, so these questions come from the gap analysis.");
}
function useQuickQuestions(note){
  D.ctl1?.abort(); D.questions=E.templateQuestions(D); $("#qStatus").textContent=note||""; $("#quickQBtn").hidden=true; $("#claude1Status").hidden=true; renderQuestions(); persist(true);
}
/* the layout has no tagline or core-competency line, so questions for those sections give way to gap questions */
function printableQuestions(qs){ const keep=qs.filter(q=>!["tagline","competency"].includes(sectionOf(q))); if(keep.length>=3) return keep.slice(0,5);
  const add=E.templateQuestions(D).filter(t=>!keep.some(q=>q.tag&&q.tag===t.tag)); return keep.concat(add).slice(0,5); }
async function claudeTailor(){
  const st=$("#claude1Status"); st.hidden=false;
  st.innerHTML=`<span class="spin" aria-hidden="true"></span><span>Claude is weighing the posting, ordering your skills line and drafting five questions…</span><button class="ghost" id="stop1">Stop</button>`;
  $("#qStatus").innerHTML=`<span class="spin" aria-hidden="true"></span> Drafting questions…`; $("#quickQBtn").hidden=false;
  $("#stop1").onclick=()=>D.ctl1?.abort();
  const ctl=D.ctl1=new AbortController();
  try{
    const r=await D.sample.json(E.prompts.tailor(D), {signal:ctl.signal, modelTier:"default"});
    if(ctl.signal.aborted) return;
    if(r && typeof r==="object"){
      const t=E.prompts.parseTailor(D, r);
      if(t.company && !$("#company").value) $("#company").value=t.company;
      if(t.title && !$("#role").value) $("#role").value=t.title;
      D.req=t.req; D.uncatalogued=t.uncatalogued; if(t.compOrder) D.compOrder=t.compOrder;
      const qs=printableQuestions(t.questions);
      recompute();
      if(!D.questions.length || !D.questions.some(q=>q.answer)) D.questions = qs.length>=3 ? qs : E.templateQuestions(D);
      $("#qStatus").textContent = qs.length>=3 ? "" : "Claude returned fewer than three questions, so these come from the gap analysis.";
      renderQuestions();
      st.innerHTML=`<span class="pill ok">tailored</span><span>Claude adjusted requirement weights, ordered your skills line and drafted your questions.</span>`;
      persist(true);
    }
  }catch(e){
    if(e?.code==="cancelled"){ st.innerHTML=`<span>Stopped. The draft uses keyword matching only.</span>`; if(!D.questions.length) useQuickQuestions(); return; }
    const msg={not_granted:"Claude isn't allowed on this page, so the draft uses keyword matching only.", rate_limited:"Claude is busy. The draft uses keyword matching; try Match again in a minute.", invalid_json:"Claude's answer came back malformed. The draft uses keyword matching only."}[e?.code] || "Claude couldn't finish, so the draft uses keyword matching only.";
    st.innerHTML=`<span class="err">${esc(msg)}</span>`;
    if(e?.code==="not_granted"||e?.code==="sampling_disabled"){ D.sample=null; renderStats(); }
    useQuickQuestions();
  }finally{ $("#quickQBtn").hidden=true; }
}
async function claudeBullets(items, ctl){
  const L=bank(), band=L.length_band, lband=L.longform_band||{min:170,hard_ceiling:340};
  const offer=E.prompts.offers(D, items);
  const r=await D.sample.json(E.prompts.bullets(D, items, offer, {title:$("#role").value, company:$("#company").value}),{signal:ctl.signal, modelTier:"default", cache:false});
  const {bullets:out, entries}=E.prompts.parseBullets(D, items, offer, r);
  const over=out.filter(b=>b.text.length>band.hard_ceiling);
  if(over.length && !ctl.signal.aborted){ try{ const fixed=await claudeTighten(over.map(b=>b.text), ctl); over.forEach((b,i)=>{ if(fixed[i]) b.text=cleanBullet(fixed[i]); }); }catch(e){} }
  const lover=out.filter(b=>b.longform && b.longform.length>lband.hard_ceiling);
  if(lover.length && !ctl.signal.aborted){ try{ const fixed=await claudeTighten(lover.map(b=>b.longform), ctl, "longform"); lover.forEach((b,i)=>{ if(fixed[i]) b.longform=cleanBullet(fixed[i]); }); }catch(e){} }
  E.prompts.qaBullets(out, items);   // a converted entry may only state what the answer (or the entry it enriches) states
  return {bullets:out, entries};
}
async function claudeTighten(texts, ctl, mode){
  const r=await D.sample.json(E.prompts.tighten(texts, mode),{signal:ctl?.signal, modelTier:"default", cache:false});
  return Array.isArray(r)? r.map(x=>typeof x==="string"?x.trim():"") : [];
}
function readAnswers(){ D.questions.forEach((q,ix)=>{ const a=$("#ans"+ix); if(a) q.answer=a.value.trim(); const s=$("#role"+ix); if(s) q.role=s.value||q.role;
  if(sectionOf(q)==="engagement"){ q.fields=q.fields||{}; for(const [k] of ENG_INPUTS){ const el=$(`#ef${ix}-${k}`); if(el) q.fields[k]=el.value.trim(); } } }); }
async function convertQuestions(ixs, label){
  readAnswers();
  const items=ixs.map(ix=>({...D.questions[ix], ix})).filter(q=>!isSkip(q.answer));
  if(!items.length){ toast("Write an answer first."); return; }
  if(!D.sample){ for(const q of items){ const sec=sectionOf(q);
      D.questions[q.ix].bullets = PHRASE_SECTIONS[sec] ? splitPhrases(q.answer, sec).map(t=>({text:t,on:true,tags:q.tag?[q.tag]:[]})) : splitAnswer(q.answer).map(t=>({text:t,on:true,tags:q.tag?[q.tag]:[], ...E.defaultPlace(q)}));
      D.questions[q.ix].note="Claude isn't available here, so each line of your answer became an entry. Edit below."; } renderQuestions(); persist(true); return; }
  const ctl=D.ctlQ=new AbortController();
  for(const q of items){ D.questions[q.ix].busy=true; D.questions[q.ix].note=""; }
  renderQuestions(); $("#finalStatus").innerHTML=`<span class="spin" aria-hidden="true"></span> ${esc(label)} <button class="ghost" id="stopQ">Stop</button>`; $("#stopQ").onclick=()=>ctl.abort();
  try{
    const {bullets, entries}=await claudeBullets(items, ctl);
    for(const q of items){
      const mine = PHRASE_SECTIONS[sectionOf(q)] ? entries.filter(e=>e.ix===q.ix).map(e=>({text:e.text,on:true,tags:e.tags}))
                                                 : bullets.filter(b=>b.ix===q.ix).map(b=>({text:b.text,longform:b.longform,on:!blocking(b.qa).length,qa:b.qa||[],tags:b.tags,achievement_id:b.achievement_id,role:b.role,engagement:b.engagement}));
      D.questions[q.ix].bullets=mine;
      const nPlaces=new Set(mine.filter(b=>b.role||b.engagement).map(placeKey)).size;
      D.questions[q.ix].note=mine.length?(nPlaces>1?`This answer covers ${nPlaces} roles, so each entry goes under its own. Change any below.`:""):"Claude found nothing usable in this answer. Add a specific (scope, number, outcome, tool) and try again.";
    }
    $("#finalStatus").textContent="";
  }catch(e){
    $("#finalStatus").innerHTML = e?.code==="cancelled" ? "" : `<span class="err">${sampleErr(e)}</span>`;
    if(e?.code==="not_granted"||e?.code==="sampling_disabled"){ D.sample=null; renderStats(); }
  }finally{ for(const q of items) D.questions[q.ix].busy=false; renderQuestions(); persist(true); }
}
async function doFinal(){
  readAnswers();
  const answered=D.questions.map((q,ix)=>({...q,ix})).filter(q=>!isSkip(q.answer));
  const todo=answered.filter(q=>!(q.bullets&&q.bullets.length));
  if(todo.length && D.sample) await convertQuestions(todo.map(q=>q.ix), `Claude is turning ${todo.length} answer${todo.length>1?"s":""} into resume entries…`);
  D.phase="finalizing"; renderQuestions();
  const L=bank(), S_=SET(), fs=$("#finalStatus"), bullets=[], phrases=[], details=[]; let skippedQa=0;
  for(const q of D.questions.map((q,ix)=>({...q,ix}))){
    const sec=sectionOf(q);
    if(sec==="engagement" && q.engagement){ const f=Object.fromEntries(Object.entries(q.fields||{}).filter(([,v])=>v)); if(f.start||f.subtitle||f.client) details.push({key:q.engagement, fields:f}); }
    if(isSkip(q.answer)) continue;
    const list = q.bullets&&q.bullets.length ? q.bullets.map((b,bi)=>({...b, bi})).filter(b=>b.on&&b.text.trim())
               : (!D.sample ? (PHRASE_SECTIONS[sec] ? splitPhrases(q.answer,sec).map(t=>({text:t,tags:[]})) : splitAnswer(q.answer).map(t=>({text:t,tags:[]}))) : []);
    if(PHRASE_SECTIONS[sec]){ for(const b of list) phrases.push({section:sec, text:cleanPhrase(b.text,sec), tags:(b.tags&&b.tags.length?b.tags:(q.tag?[q.tag]:[]))}); continue; }
    for(const b of list){ if(blocking(b.qa).length){ skippedQa++; continue; }   // a number you never stated cannot print
      const p=E.bulletPlace(q,b);
      bullets.push({role:p.role, engagement:p.engagement, q_ix:q.ix, b_ix:b.bi??null, text:cleanBullet(b.text), longform:(p.engagement&&b.longform)?cleanBullet(b.longform):null, tags:(b.tags&&b.tags.length?b.tags:(q.tag?[q.tag]:[])), achievement_id:(b.achievement_id&&E.attachOk(b.achievement_id,p))?b.achievement_id:null}); }
  }
  if(!D.sample && (bullets.length||phrases.length)) fs.innerHTML=`<span class="hint">Claude isn't available here, so each line of your answers became an entry. Use Polish on the sheet once Claude is allowed.</span>`;
  for(const d of details) D.engDetails[d.key]={...(D.engDetails[d.key]||{}), ...d.fields};
  D.extra={tagline:[],expertise:[],technology:[],competency:[]};
  for(const p of phrases) if(!D.extra[p.section].some(x=>norm(typeof x==="string"?x:x.text)===norm(p.text))) D.extra[p.section].push(p.section==="competency"?{text:p.text,tags:p.tags}:p.text);
  D.newAch=[];
  const known=new Set(L.achievements.map(a=>a.id));
  bullets.forEach((b,n)=>{
    const role=L.roles.some(r=>r.key===b.role)?b.role:(b.engagement?S_.default_engagement_role:S_.fallback_role);
    const tagList=(b.tags||[]).filter(t=>L.tags[t]), tid="new:"+D.runId+":"+n;
    const lt=b.longform?{id:tid+":lf", kind:"learned", angle:"longform", text:b.longform, score_adj:0, fresh:true}:null;
    if(b.achievement_id && known.has(b.achievement_id)){
      D.newAch.push({n, attach:b.achievement_id, role, tags:tagList, engagement:b.engagement, longform:b.longform, q_ix:b.q_ix, b_ix:b.b_ix, text:{id:tid, kind:"learned", angle:"gate2", text:b.text, score_adj:0, fresh:true}, longText:lt});
      if(!b.engagement) D.pinned.add(b.achievement_id);
    }else{
      const id="gate2-"+D.runId+"-"+n, texts=[{id:tid, kind:"learned", angle:"gate2", text:b.text, score_adj:0, fresh:true}]; if(lt) texts.push(lt);
      D.newAch.push({n, ach:{id, role, engagement:b.engagement, confidence:"asserted", fresh:true, has_metrics:/\d/.test(b.text), tags:Object.fromEntries(tagList.map(t=>[t,1])), metrics:[], texts}, role, tags:tagList, engagement:b.engagement, longform:b.longform, q_ix:b.q_ix, b_ix:b.b_ix, text:{text:b.text}});
      if(!b.engagement) D.pinned.add(id);
    }
  });
  lockCurrent(); D.phase="final"; recompute(); renderQuestions(); D.finalModel=E.resumeModel(D); persist(true);
  const nAdded=bullets.length+phrases.length+details.length;
  toast((nAdded?`Added ${nAdded} new entr${nAdded>1?"ies":"y"}. `:"")+(skippedQa?`${skippedQa} left out: numbers not in your answers. `:"")+"Final draft ready. Download Word or PDF to add your answers to your record.");
}
const freshN = x => x.n ?? +(x.ach ? String(x.ach.id).split("-").pop() : String(x.text.id).split(":").pop());
function saveEdit(aid, i, txt){
  lockCurrent(); D.edits[aid]=txt; D.pinned.add(aid); persist(true);
  logFeedback("edit", aid, {tid:i.t.id, text:txt});
  const x=D.newAch.find(x=>(x.ach&&x.ach.id===aid)||(x.attach===aid&&x.text.id===i.t.id)); if(x && x.attach) x.edited=txt;
}
function saveEditC(aid, txt){ D.editsC[aid]=txt; persist(true); const x=D.newAch.find(x=>(x.ach&&x.ach.id===aid)); if(x) x.longform=txt; }
/* Move an answer entry under another role (from its question card or the sheet); the rest of the draft keeps its layout. */
function applyMove(n, p){
  const x=D.newAch[n]; if(!x || !p || placeKey(x)===placeKey(p)) return false;
  const k=freshN(x), Q=D.questions[x.q_ix], B=Q?.bullets?.[x.b_ix], L=bank();
  if(x.attach){   // it no longer enriches that entry: it becomes an entry of its own in the new place
    const blk=blocking(RotCore.qa.qaLine(x.edited||x.text.text, [], answerQuotes(Q), null, id=>E.claimById(id)));
    if(blk.length){ if(B){ B.role=x.role; B.engagement=x.engagement||null; } return blk; }
    const X=x.attach, id=`gate2-${D.runId}-${k}`;
    if(!D.newAch.some(y=>y!==x && y.attach===X)) D.pinned.delete(X);
    if(x.edited){ D.edits[id]=x.edited; if(D.edits[X]===x.edited) delete D.edits[X]; }
    x.ach={id, role:p.role, engagement:p.engagement, confidence:"asserted", fresh:true, has_metrics:/\d/.test(x.text.text), tags:Object.fromEntries((x.tags||[]).filter(t=>L.tags[t]).map(t=>[t,1])), metrics:[], texts:[x.text]};
    x.text={text:x.text.text}; delete x.attach; delete x.longText; delete x.edited;
    if(B) B.achievement_id=null;
  }
  const id=x.ach.id;
  x.role=x.ach.role=p.role; x.engagement=x.ach.engagement=p.engagement;
  if(p.engagement && !x.longform && B && B.longform) x.longform=cleanBullet(B.longform);
  const short=x.ach.texts.filter(t=>t.angle!=="longform");
  x.ach.texts = p.engagement && x.longform ? short.concat([{id:short[0].id+":lf", kind:"learned", angle:"longform", text:x.longform, score_adj:0, fresh:true}]) : short;
  if(p.engagement) D.pinned.delete(id); else D.pinned.add(id);
  if(B){ B.role=p.role; B.engagement=p.engagement; }
  return true;
}
function moveFresh(moves, focusId){
  lockCurrent(); let last=null, refused=null;
  for(const [n,p] of moves){ const r=applyMove(n,p); if(r===true) last=p; else if(Array.isArray(r)) refused=r; }
  recompute(); renderQuestions(); persist(true);
  if(focusId) $("#"+focusId)?.focus();
  if(refused) toast(`Not moved: ${refused.join("; ")}. That number comes from the entry it enriches. Edit it out first.`);
  else if(last) toast(`Moved under ${E.placeName(D, last)}.`);
}
function placeChanged(q, bis, focusId){
  const Q=D.questions[q], moves=[];
  for(const bi of bis){ const n=D.newAch.findIndex(x=>x.q_ix===q && x.b_ix===bi); if(n>=0) moves.push([n, E.bulletPlace(Q, Q.bullets[bi])]); }
  if(moves.length) moveFresh(moves);
  for(const bi of bis){ const B=Q.bullets[bi], was=blocking(B.qa).length; B.qa=E.bulletQa(Q,B); if(blocking(B.qa).length) B.on=false; else if(was) B.on=true; }
  renderQuestions(); if(focusId) $("#"+focusId)?.focus();
}
async function polishBullet(aid, sec){
  if(!D.sample){ toast("Claude isn't available in this view. Edit the text directly."); return; }
  if(sec==="c"){
    const b=E.resumeModel(D).engagements.flatMap(e=>e.bullets).find(b=>b.aid===aid); if(!b) return;
    toast("Claude is polishing that entry…");
    try{ const [t]=await claudeTighten([b.text], new AbortController(), "longform"); const c=t?cleanBullet(t):"";
      if(c && c!==b.text){ saveEditC(aid,c); renderSheet(); toast(`Polished (${c.length} characters).`); } else toast("That entry already meets the standard.");
    }catch(e){ toast(e?.code==="not_granted"?"Allow Claude on this page to use Polish.":"Claude couldn't polish it. Try again or edit it directly."); }
    return;
  }
  const i=E.findChosen(D, aid); if(!i) return;
  const cur=D.edits[aid]??i.t.text;
  toast("Claude is polishing that entry…");
  try{ const [t]=await claudeTighten([cur], new AbortController()); const c=t?cleanBullet(t):"";
    if(c && c!==cur){ saveEdit(aid,i,c); renderSheet(); toast(`Polished (${c.length} characters).`); } else toast("That entry already meets the standard.");
  }catch(e){ toast(e?.code==="not_granted"?"Allow Claude on this page to use Polish.":"Claude couldn't polish it. Try again or edit it directly."); }
}
/* The optional summary: Claude writes it only from the claims on this draft, and it is checked against their evidence. */
async function claudeSummary(){
  const m=E.resumeModel(D), qa=(text, ids)=>RotCore.qa.qaLine(text, ids, [], null, id=>E.claimById(id));
  const {prompt, ids, words}=E.prompts.summary(D, m, {title:$("#role").value, company:$("#company").value});
  const r=await D.sample.json(prompt,{modelTier:"default", cache:false});
  let text=String(r?.summary||"").replace(/\s+/g," ").trim(); if(!text) throw Object.assign(new Error("empty"),{code:"empty_completion"});
  const used=(Array.isArray(r?.claims_used)?r.claims_used:[]).filter(id=>E.claimById(id)); const basis=used.length?used:ids;
  let issues=qa(text, basis);
  if(blocking(issues).length){ const r2=await D.sample.json(E.prompts.summaryRetry(text, blocking(issues), words),{modelTier:"default", cache:false}); text=String(r2?.summary||"").replace(/\s+/g," ").trim(); issues=qa(text, basis); }
  if(blocking(issues).length) throw Object.assign(new Error(issues.join("; ")),{code:"qa"});
  if(text.split(/\s+/).length>words+10) throw Object.assign(new Error("too long"),{code:"qa"});
  return {text, claims:basis};
}
/* An edited skills or tools line keeps its order; items the record doesn't hold yet are added to it in your words */
function saveLineEdit(line, area, text){
  const m=E.resumeModel(D), L=bank();
  if(line==="summary"){ const issues=blocking(RotCore.qa.qaLine(text, D.summaryClaims||[], [], null, id=>E.claimById(id))); if(issues.length){ toast(`That edit doesn't pass the evidence check: ${issues.join("; ")}`); renderSheet(); return; } D.summary=text; persist(true); return; }
  if(line==="core"){ const items=splitList(text, [","]).map(x=>x.replace(/[.;]+$/,"").trim()).filter(Boolean); D.sectionEdits.core=m.core_competencies.map(a=>({label:a.label, items:a.label===area?items:a.items})); persist(true); return; }
  const cfg=LINE_EDIT[line]; const items=uniq(splitList(text, cfg.sep).map(x=>x.replace(/[.;]+$/,"").trim()).filter(Boolean));
  D.sectionEdits[line]=items;
  const have=new Set((line==="expertise" ? L.competencies.map(c=>c.text) : line==="technologies" ? L.technologies.map(t=>t.name) : (L.tagline_phrases||[]).map(p=>p.text)).map(norm));
  const fresh=items.filter(t=>!have.has(norm(t)));
  if(fresh.length && (line==="expertise"||line==="technologies")){
    const subs=store.get("subjects"), ev=store.get("evidence"), srcs=ensureSource(store.get("sources")), kind=line==="expertise"?"expertise":"tool", pred=line==="expertise"?"text":"name";
    for(const t of fresh){ let id=`${kind}:${slug(t)}`; while(subs.some(s=>s.id===id)) id+="-2"; const evId=`ev:you:${id}`; ev.push(evRow(evId, t, `${line} line, typed on the sheet`));
      subs.push({id, kind, sort:subs.filter(s=>s.kind===kind).length, tags:Object.keys(T.extractRequirements(t)), facts:{[pred]:{value:t, evidence:[evId], contradicting:[]}}}); }
    writeAll({subjects:subs, evidence:ev, sources:srcs}, true);
  }
  persist(true);
}

/* ------------------------------ answers become record: on download ------------------------------ */
/* Each answer entry on the final draft becomes an achievement with the answer as first-hand evidence; an entry that enriched an
   existing one adds a learned wording and the evidence to it; tools and skills from answers become subjects. Deterministic ids. */
function foldAnswers(){
  if(!D.runId || (!D.newAch.length && !D.extra.technology.length && !D.extra.expertise.length)) return false;
  const now=new Date().toISOString(), day=now.slice(0,10), map={};
  const srcs=store.get("sources"), ev=store.get("evidence"), ach=store.get("achievements"), subs=store.get("subjects");
  if(!srcs.some(s=>s.id==="src:answers")) srcs.push({id:"src:answers", kind:"answer", label:"Your answers on this page", authored_at:day, observed_at:day, source_type:"USER_ENTERED"});
  const upsertEv=(id, quote, locator)=>{ const row={id, source:"src:answers", source_type:"USER_ENTERED", channel:"answer", quote, observed_at:day, locator}; const i=ev.findIndex(e=>e.id===id); if(i>=0) ev[i]={...ev[i], ...row}; else ev.push(row); return id; };
  const answerEv=(qix, fallback)=>{ const Q=D.questions[qix]; const quote=Q?answerQuotes(Q).filter(Boolean).join("\n"):""; return quote ? upsertEv(`ev:${D.runId}:q${qix}`, quote, `${D.runId}: question ${qix+1}`) : upsertEv(`ev:${D.runId}:${slug(fallback).slice(0,24)}`, fallback, `${D.runId}: entry as printed`); };
  for(const x of D.newAch){
    const n=freshN(x);
    if(x.ach){
      const id=`${D.runId}-g${n}`, text=D.edits[x.ach.id]||x.text.text, evId=answerEv(x.q_ix, text);
      const tags=Object.fromEntries((x.tags||[]).map(t=>[t,1])), lf=x.engagement&&(D.editsC[x.ach.id]||x.longform);
      const rec={id, role:x.role, engagement:x.engagement||null, canonical:text, evidence:[evId], contradicting:[], tags:Object.keys(tags).length?tags:tagsFor(text), metrics:[], origin:"answer", variants:lf?[{kind:"learned", angle:"longform", text:lf}]:[]};
      const i=ach.findIndex(a=>a.id===id); if(i>=0) ach[i]={...ach[i], ...rec}; else ach.push(rec);
      map[x.ach.id]=id;
    } else if(x.attach){
      const a=ach.find(a=>a.id===x.attach); if(!a) continue;
      const text=x.edited||x.text.text, evId=answerEv(x.q_ix, text);
      a.variants=(a.variants||[]).filter(v=>norm(v.text)!==norm(text)); a.variants.push({kind:"learned", angle:"gate2", text});
      if(!a.evidence.includes(evId)) a.evidence.push(evId);
    }
  }
  const addPhrase=(kind, pred, text, sec)=>{
    if(subs.some(s=>s.kind===kind && norm(val(s.facts&&s.facts[pred]))===norm(text))) return;
    let qi=D.questions.findIndex(q=>sectionOf(q)===sec && norm(q.answer||"").includes(norm(text).slice(0,10))); if(qi<0) qi=D.questions.findIndex(q=>sectionOf(q)===sec);
    const evId=answerEv(qi>=0?qi:-1, text); let id=`${kind}:${slug(text)}`; while(subs.some(s=>s.id===id)) id+="-2";
    subs.push({id, kind, sort:subs.filter(s=>s.kind===kind).length, tags:Object.keys(T.extractRequirements(text)), facts:{[pred]:{value:text, evidence:[evId], contradicting:[]}}}); };
  for(const t of D.extra.technology) addPhrase("tool","name",t,"technology");
  for(const t of D.extra.expertise) addPhrase("expertise","text",t,"expertise");
  writeAll({sources:srcs, evidence:ev, achievements:ach, subjects:subs}, true);
  remapSynced(map); recompute(); renderQuestions(); persist(true);
  return true;
}
/* Entries the record now holds are shown from the record instead of the draft's answer copies (the Desk's routine, ids from `map`). */
function remapSynced(map){
  map=map||{}; const L=bank(), ids=new Set(L.achievements.map(a=>a.id)), libTexts=new Set(L.achievements.flatMap(a=>a.texts.map(t=>norm(t.text))));
  const move=(from,to)=>{
    if(D.pinned.delete(from) && to) D.pinned.add(to);
    if(D.excluded.delete(from) && to) D.excluded.add(to);
    if(D.excludedC.delete(from) && to) D.excludedC.add(to);
    delete D.edits[from]; delete D.editsC[from];
    if(D.locked) for(const r of Object.keys(D.locked)){ const out=[]; for(const x of D.locked[r]){ const y=(x===from)?to:x; if(y && !out.includes(y)) out.push(y); } D.locked[r]=out; }
  };
  D.newAch=D.newAch.filter(x=>{
    if(x.ach){ const gid=x.ach.id; if(Object.prototype.hasOwnProperty.call(map,gid)){ const to=map[gid]; move(gid, to && ids.has(to) ? to : null); return false; } return true; }
    return !libTexts.has(norm(x.edited||x.text.text));
  });
  for(const k of Object.keys(D.engDetails)){ const e=E.engByKey(k); if(e && !e.needs_details) delete D.engDetails[k]; }
}

/* ------------------------------ files ------------------------------ */
async function loadTemplate(){ if(D.tpl) return D.tpl; const r=await fetch("template/docx_template.json"); if(!r.ok) throw new Error("template "+r.status); D.tpl=await r.json(); return D.tpl; }
async function buildDocx(m){ if(!window.JSZip) throw new Error("jszip"); return RotCore.doc.buildDocx(m, await loadTemplate(), window.JSZip); }
async function loadFonts(doc){
  if(D.fontData===undefined){
    try{ const files={normal:"Carlito-Regular.ttf", bold:"Carlito-Bold.ttf", italic:"Carlito-Italic.ttf", bolditalic:"Carlito-BoldItalic.ttf"}, out={};
      await Promise.all(Object.entries(files).map(async([st,f])=>{ const r=await fetch("fonts/"+f); if(!r.ok) throw new Error(f); out[st]=[f, abToB64(await r.arrayBuffer())]; }));
      D.fontData=out;
    }catch(e){ console.warn("fonts", e); D.fontData=null; setTimeout(()=>{ D.fontData=undefined; }, 30000); }
  }
  if(!D.fontData) return false;
  try{ for(const [st,[f,b64]] of Object.entries(D.fontData)){ doc.addFileToVFS(f,b64); doc.addFont(f,"Carlito",st); } return true; }catch(e){ console.warn("addFont", e); return false; }
}
async function buildPdf(m){ let tpl=null; try{ tpl=await loadTemplate(); }catch{} return RotCore.doc.buildPdf(m, tpl, window.jspdf, loadFonts); }
function fileSlug(){ const nm=String(bank().identity.name||"Resume").replace(/[^A-Za-z0-9]+/g,"_").replace(/^_|_$/g,"")||"Resume"; const c=($("#company").value||"").replace(/[^A-Za-z0-9]+/g,"_").replace(/^_|_$/g,""); return `${nm}_Resume`+(c?"_"+c:"")+(D.phase==="final"?"":"_draft"); }
/* the viewer's downloads capability, or a plain link in the local preview; anything else has nowhere to put a file */
async function deliver(name, blob){
  if(D.downloads){ try{ await D.downloads.save({filename:name, data:blob}); return true; }catch(e){ if(e?.code!=="declined") toast(e?.code==="rate_limited"?"A save prompt is already open.":"The file couldn't be saved here."); return false; } }
  if(LOCAL){ const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download=name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(a.href), 5000); return true; }
  toast("Downloads aren't available in this view. Open the page in Claude to save files."); return false;
}
async function saveFile(kind){
  if(!bank().roles.length){ toast("Nothing to download yet. Add a role first."); return; }
  const model=E.resumeModel(D); let blob, name;
  try{
    if(kind==="pdf"){ if(!window.jspdf){ toast("The PDF library didn't load. Reload the page and try again."); return; }
      const {doc, font}=await buildPdf(model); blob=doc.output("blob"); name=fileSlug()+".pdf";
      if(font!=="Carlito") toast("The resume font didn't load, so this PDF uses Helvetica. The Word download keeps the template font."); }
    else { blob=await buildDocx(model); name=fileSlug()+".docx"; }
  }catch(e){ console.warn(kind, e); toast(kind==="pdf"?"The PDF couldn't be built. Try again, or use Download Word.":"The Word file couldn't be built. Reload the page and try again."); return; }
  if(!await deliver(name, blob)) return;
  const folded=foldAnswers(); D.finalModel=model; persist(true); renderStats();
  $("#syncNote").innerHTML = folded ? `<b>Added to your record.</b> The answers on this posting are now entries with your own words as evidence. Download a backup to keep them.` : `<b>Saved.</b> Download a backup under Backup &amp; privacy to keep your record.`;
  toast(`${kind==="pdf"?"PDF":"Word file"} saved.`);
}
async function downloadBackup(){
  const data=JSON.stringify(store.snapshot(), null, 1), name=`career-companion-backup-${today()}.json`;
  if(!await deliver(name, new Blob([data],{type:"application/json"}))) return;
  const m=store.get("meta"); m.last_backup_at=new Date().toISOString(); store.set("meta", m, true); renderStorage(); renderStats(); toast("Backup saved. Keep it somewhere safe.");
}
function loadBackup(b, msg){ D.ctl1?.abort(); D.ctlQ?.abort(); store.importBackup(b); resetDraft(); D.adj=adjFromFeedback(); renderAll(); Hub.show("evidence"); toast(msg); }

/* ------------------------------ saved work ------------------------------ */
function serializeState(){
  return {v:1, edition:"hub", core:RotCore.VERSION, runId:D.runId, saved_at:new Date().toISOString(),
    jd:D.jd, jdDraft:$("#jd").value, company:$("#company").value, title:$("#role").value,
    req:D.req, uncatalogued:D.uncatalogued, phase:D.phase, score:D.score,
    excluded:[...D.excluded], pinned:[...D.pinned], locked:D.locked, textChoice:D.textChoice, edits:D.edits,
    tagline:D.tagline, compOrder:D.compOrder, sectionEdits:D.sectionEdits, engDetails:D.engDetails, editsC:D.editsC, excludedC:[...D.excludedC], extra:D.extra,
    summaryOn:D.summaryOn, summary:D.summary, summaryClaims:D.summaryClaims, outcome:D.outcome,
    questions:D.questions.map(q=>({question:q.question, why:q.why||"", tag:q.tag||null, role:q.role, hint:q.hint||"", section:sectionOf(q), engagement:q.engagement||null, fields:q.fields||null, answer:q.answer||"", bullets:q.bullets||null, note:q.note||""})),
    newAch:D.newAch, qStatus:$("#qStatus").textContent, final_model:D.phase==="final"?(D.finalModel||E.resumeModel(D)):null};
}
let saveTimer=null;
function persist(soon){ clearTimeout(saveTimer); saveTimer=setTimeout(saveNow, soon?150:1200); }
function saveNow(){
  if(!store||!E) return; const st=serializeState();
  if(D.runId){ const s=store.get("sessions"); const isNew=!s[D.runId]; s[D.runId]=st; store.set("sessions", s, true); store.set("workspace", {current:D.runId, saved_at:st.saved_at, idle:null}, true); if(isNew) renderStats(); }
  else store.set("workspace", {current:null, saved_at:st.saved_at, idle:st}, true);
}
function restoreState(st){
  if(!st || st.v!==1) return false;
  D.ctl1?.abort(); D.ctlQ?.abort();
  D.runId=st.runId||null; D.jd=st.jd||"";
  $("#jd").value=st.jdDraft ?? st.jd ?? ""; $("#company").value=st.company||""; $("#role").value=st.title||"";
  D.req=st.req||{}; D.uncatalogued=st.uncatalogued||[]; D.phase=st.phase||(Object.keys(D.req).length?"draft":"idle");
  D.excluded=new Set(st.excluded||[]); D.pinned=new Set(st.pinned||[]); D.locked=st.locked?clone(st.locked):null;
  D.textChoice=st.textChoice||{}; D.edits=st.edits?{...st.edits}:{};
  D.tagline=Array.isArray(st.tagline)?st.tagline:null; D.compOrder=st.compOrder||null;
  D.sectionEdits=st.sectionEdits?clone(st.sectionEdits):{}; D.engDetails=st.engDetails?clone(st.engDetails):{}; D.editsC=st.editsC?{...st.editsC}:{};
  D.excludedC=new Set(st.excludedC||[]); D.extra={tagline:[],expertise:[],technology:[],competency:[], ...(st.extra?clone(st.extra):{})};
  D.questions=(st.questions||[]).map(q=>({...q, section:q.section||"experience", busy:false}));
  D.newAch=st.newAch?clone(st.newAch):[]; D.finalModel=st.final_model||null;
  D.summaryOn=!!st.summaryOn && !!st.summary; D.summary=st.summary||null; D.summaryClaims=st.summaryClaims||[]; D.outcome=st.outcome||null;
  $("#sumToggle").checked=D.summaryOn;
  $("#claude1Status").hidden=true; $("#quickQBtn").hidden=true; $("#finalStatus").textContent=""; $("#syncNote").textContent="";
  remapSynced({}); recompute(); renderQuestions(); $("#qStatus").textContent=st.qStatus||"";
  return true;
}
function showRestoreNote(st, how){
  if(!st.jd && !st.company && !st.title) return;
  const w=fmtWhen(st.saved_at), what=[st.company, st.title].filter(Boolean).join(" · ") || (st.jd? "your last posting" : "your last draft");
  const n=$("#restoreNote"); n.hidden=false; n.innerHTML=`<b>${how||"Picked up where you left off"}:</b> ${esc(what)}${w?` (saved ${esc(w)})`:""}. <b>New posting</b> starts fresh; this one stays under Saved postings.`;
}
function loadRecent(){
  const sess=Object.values(store.get("sessions")).sort((a,b)=>String(b.saved_at||"").localeCompare(String(a.saved_at||""))).slice(0,30), sel=$("#recent");
  sel.innerHTML=`<option value="">Open a saved posting…</option>`+sess.map(x=>`<option value="${esc(x.runId)}">${esc([x.company||"Untitled", x.title||"posting"].join(" — "))}${x.saved_at?` · ${esc(fmtDay(x.saved_at))}`:""}${x.runId===D.runId?" (open now)":""}</option>`).join("");
  $("#recentWrap").hidden=!sess.length;
}
function openSaved(id){
  if(id===D.runId) return; saveNow();
  const st=store.get("sessions")[id]; if(!st){ toast("That posting couldn't be opened."); return; }
  restoreState(st); showRestoreNote(st, "Opened"); saveNow(); loadRecent();
}
function resetDraft(){ resetPosting(); Object.assign(D,{runId:null, jd:"", req:{}, uncatalogued:[], locked:null, phase:"idle"});
  $("#jd").value=""; $("#company").value=""; $("#role").value=""; $("#restoreNote").hidden=true; $("#claude1Status").hidden=true; $("#qStatus").textContent="Paste a posting and press Match. Your five questions appear here."; $("#finalStatus").textContent=""; $("#syncNote").textContent=""; }
function newPosting(){ saveNow(); D.ctl1?.abort(); D.ctlQ?.abort(); resetDraft(); recompute(); renderQuestions(); persist(true); loadRecent(); $("#jd").focus(); }

/* ------------------------------ postings and outcomes ------------------------------ */
function renderPostings(){
  const sess=Object.values(store.get("sessions")).sort((a,b)=>String(b.saved_at||"").localeCompare(String(a.saved_at||""))), oc=store.get("outcomes");
  const latest=id=>oc.filter(o=>o.run_id===id).sort((a,b)=>String(b.recorded_at||"").localeCompare(String(a.recorded_at||"")))[0]||null;
  $("#postings").innerHTML = sess.length ? sess.map(s=>{ const o=latest(s.runId)||s.outcome||{}, pct=s.score==null?"–":Math.round(s.score*100)+"%";
    return `<div class="card" data-run="${esc(s.runId)}"><div class="top"><b>${esc([s.company||"Untitled", s.title||"posting"].join(" — "))}</b><span class="hint">${esc(fmtWhen(s.saved_at))} · match ${pct} · ${s.phase==="final"?"final":"draft"}${s.runId===D.runId?" · open now":""}</span></div>
      <div class="ocform"><label class="f">Applied on<input type="date" data-oc="applied_at" value="${esc(o.applied_at||"")}"></label><label class="f">Response<select data-oc="response">${["pending","no_response","screen","interview","offer","rejected"].map(v=>`<option value="${v}" ${(o.response||"pending")===v?"selected":""}>${v.replace("_"," ")}</option>`).join("")}</select></label><label class="f full">Note<input type="text" data-oc="note" value="${esc(o.note||"")}" placeholder="who, what stage, anything worth remembering"></label>
      <div class="row full"><button data-open="${esc(s.runId)}">Open this posting</button><button data-saveoc="${esc(s.runId)}">Save outcome</button><span class="hint">${o.recorded_at?`Saved ${esc(fmtDay(o.recorded_at))}.`:""}</span></div></div></div>`; }).join("")
    : `<p class="hint">Postings you match appear here with their drafts. Match one first.</p>`;
}
function saveOutcome(id, card){
  const g=k=>card.querySelector(`[data-oc="${k}"]`).value;
  const rec={run_id:id, applied_at:g("applied_at")||null, response:g("response")||"pending", note:g("note").trim()||null, recorded_at:new Date().toISOString()};
  const oc=store.get("outcomes"); oc.push(rec); store.set("outcomes", oc, true);
  const s=store.get("sessions"); if(s[id]){ s[id].outcome=rec; store.set("sessions", s, true); }
  if(id===D.runId) D.outcome=rec;
  renderPostings(); toast("Outcome saved with this posting.");
}
function renderStorage(){ const used=store.usage(), meta=store.get("meta");
  $("#storage").innerHTML=`<span class="chip ${used>3.5e6?"warn":""}"><b>${fmtBytes(used)}</b> used of about 5 MB</span><span class="chip">${meta.last_backup_at?`last backup ${esc(fmtWhen(meta.last_backup_at))}`:"no backup yet"}</span><span class="chip ${store.available?"":"warn"}">${store.available?"browser storage on":"browser storage blocked: this visit only"}</span>`; }

/* ------------------------------ features ------------------------------ */
Hub.register({id:"evidence", label:"Your evidence", order:1,
  mount(){
    const timers={};
    $("#pIdentity").addEventListener("input", saveIdentity); $("#pIdentity").addEventListener("change", saveIdentityNow);
    $("#addRole").onclick=addRole;
    $("#roles").addEventListener("input", e=>{ const card=e.target.closest("[data-role]"); if(!card) return; const key=card.dataset.role;
      if(e.target.dataset.fact!==undefined && e.target.type==="text"){ const k=key+":"+e.target.dataset.fact; clearTimeout(timers[k]); timers[k]=setTimeout(()=>setRoleFact(key, e.target.dataset.fact, e.target.value.trim()), 400); }
      if(e.target.dataset.line!==undefined){ const id=e.target.closest("li").dataset.lineId; clearTimeout(timers[id]); timers[id]=setTimeout(()=>setLine(id, e.target.value, false), 400); } });
    $("#roles").addEventListener("change", e=>{ const card=e.target.closest("[data-role]"); if(!card) return; const key=card.dataset.role;
      if(e.target.dataset.fact!==undefined){ const k=key+":"+e.target.dataset.fact; clearTimeout(timers[k]); setRoleFact(key, e.target.dataset.fact, e.target.value.trim()); }
      if(e.target.dataset.hidden!==undefined) setRoleHidden(key, e.target.checked);
      if(e.target.dataset.line!==undefined){ const id=e.target.closest("li").dataset.lineId; clearTimeout(timers[id]); setLine(id, e.target.value, true); const a=store.get("achievements").find(x=>x.id===id); if(a) e.target.value=a.canonical; } });
    $("#roles").addEventListener("click", e=>{ const b=e.target.closest("button"); if(!b) return; const card=b.closest("[data-role]"); if(!card) return; const key=card.dataset.role;
      if(b.dataset.addlines!==undefined){ const ta=card.querySelector("[data-paste]"); addLines(key, ta.value); return; }
      if(b.dataset.delLine) { delLine(b.dataset.delLine); return; }
      if(b.dataset.resolve){ const [kind, id, pred, pick]=b.dataset.resolve.split("|"); resolveFact(kind, id, pred, +pick); return; }   // ids carry colons, so the fields are pipe-separated
      if(b.dataset.split){ const [id, i]=b.dataset.split.split("|"); splitAch(id, +i); return; }
      if(b.dataset.delRole!==undefined){ if(b.dataset.armed){ delRole(key); return; } b.dataset.armed="1"; b.textContent="Click again to remove this role and its entries"; setTimeout(()=>{ delete b.dataset.armed; b.textContent="Remove role"; }, 4000); } });
    $("#addEdu").onclick=addEdu; $("#addCert").onclick=addCert; $("#saveLists").onclick=saveLists;
    ["#eduList","#certList"].forEach(s=>$(s).addEventListener("click", e=>{ const b=e.target.closest("[data-del-subject]"); if(b) delSubject(b.dataset.delSubject); }));
    ["#skills","#tools"].forEach(s=>$(s).addEventListener("input", ()=>{ $("#listsNote").textContent="Unsaved changes."; }));
    $("#goMatch").onclick=()=>Hub.show("match");
    $("#loadExample").onclick=async()=>{ if(!store.isEmpty()){ toast("The example replaces what is here: download a backup and delete everything first."); return; }
      try{ const r=await fetch("example/backup.json"); if(!r.ok) throw new Error(String(r.status)); loadBackup(await r.json(), "Loaded the example person (fictional).");
        const n=bank().claims.filter(c=>c.status==="disputed").length;
        revealRoles(`<b>Example loaded:</b> a fictional record built from four documents (three resumes and a LinkedIn profile). ${n?`They disagree in ${n===1?"one place":n+" places"}, marked below: read both statements and decide which the person could defend. Until then that entry is held back.`:"Nothing is in dispute."} Then open <b>Match a posting</b> and load the sample posting.`); }
      catch(e){ toast("The example couldn't load."); } };
  },
  refresh(){ renderIdentity(); renderRoles(); renderLists(); renderReady(); $("#tiers").innerHTML=tiersHtml(); }});

Hub.register({id:"match", label:"Match a posting", order:2,
  mount(){
    $("#matchBtn").onclick=doMatch; $("#newBtn").onclick=newPosting; $("#finalBtn").onclick=doFinal;
    $("#sampleJdBtn").onclick=()=>{ if($("#jd").value.trim() && $("#jd").value.trim()!==SAMPLE_JD.trim() && D.phase!=="idle") newPosting();
      $("#jd").value=SAMPLE_JD; $("#company").value="Northgate Software"; $("#role").value="Director, Revenue Operations"; $("#jdHint").textContent="Sample posting loaded (fictional). Press Match against my record."; persist(); $("#matchBtn").focus(); };
    $("#heldNote").addEventListener("click", e=>{ if(e.target.closest("[data-goto]")){ Hub.show("evidence"); revealRoles(); } });
    $("#quickQBtn").onclick=()=>useQuickQuestions("Quick questions from the gap analysis. Claude's version was skipped.");
    $("#polishAllBtn").onclick=()=>{ readAnswers(); const ixs=D.questions.map((q,ix)=>ix).filter(ix=>!isSkip(D.questions[ix].answer)); convertQuestions(ixs, `Claude is polishing ${ixs.length} answer${ixs.length>1?"s":""}…`); };
    $("#recent").addEventListener("change", e=>{ const id=e.target.value; e.target.value=""; if(id) openSaved(id); });
    ["#jd","#company","#role"].forEach(sel=>$(sel).addEventListener("input", ()=>persist()));
    $("#questions").addEventListener("input", e=>{
      persist(); const L=bank();
      const ix=e.target.dataset.ix; if(ix!=null && D.questions[ix] && e.target.tagName==="TEXTAREA") D.questions[ix].answer=e.target.value;
      const ef=e.target.dataset.ef; if(ef){ const [q,k]=ef.split(":"); const Q=D.questions[+q]; if(Q){ Q.fields=Q.fields||{}; Q.fields[k]=e.target.value; } }
      const bt=e.target.dataset.btxt; if(bt){ const [q,b]=bt.split(":").map(Number); const Q=D.questions[q], B=Q?.bullets?.[b]; if(B){ B.text=e.target.value; const ph=PHRASE_SECTIONS[sectionOf(Q)]; const lim=ph?ph.max:L.length_band.hard_ceiling; const cc=$(`#bcc${q}-${b}`); if(cc){ cc.textContent=B.text.length; cc.classList.toggle("over", B.text.length>lim); }
        if(!ph){ B.qa=E.bulletQa(Q,B); const blk=blocking(B.qa); const cb=$(`#bon${q}-${b}`), msg=$(`#bqa${q}-${b}`); if(cb){ cb.disabled=!!blk.length; if(!blk.length && !cb.checked){ cb.checked=true; B.on=true; } } e.target.classList.toggle("blocked", !!blk.length); if(msg) msg.textContent = blk.length ? `Not printable yet: ${blk.join("; ")}. Edit the text, or add that fact to your answer and re-polish.` : "Passes: every number is in your answer."; } } }
    });
    $("#questions").addEventListener("change", e=>{
      persist();
      const ix=e.target.dataset.ix;
      if(ix!=null && D.questions[ix] && e.target.tagName==="SELECT"){ const Q=D.questions[ix], old=Q.role; Q.role=e.target.value;
        const follow=(Q.bullets||[]).map((B,bi)=>bi).filter(bi=>{ const B=Q.bullets[bi]; return !B.engagement && (!B.role || B.role===old); });
        follow.forEach(bi=>{ Q.bullets[bi].role=Q.role; });
        if((Q.bullets||[]).length) placeChanged(+ix, follow, e.target.id); }
      const bp=e.target.dataset.bplace;
      if(bp){ const [q,b]=bp.split(":").map(Number); const B=D.questions[q]?.bullets?.[b], p=E.parsePlace(e.target.value); if(B && p){ B.role=p.role; B.engagement=p.engagement; placeChanged(q, [b], e.target.id); } }
      const bo=e.target.dataset.bon; if(bo){ const [q,b]=bo.split(":").map(Number); const B=D.questions[q]?.bullets?.[b]; if(B) B.on=e.target.checked; }
    });
    $("#questions").addEventListener("click", e=>{ const b=e.target.closest("button[data-conv]"); if(!b) return; convertQuestions([+b.dataset.conv], "Claude is turning that answer into resume entries…"); });
    $("#sheet").addEventListener("click", e=>{
      const b=e.target.closest("button[data-act]"); if(!b) return; const aid=b.dataset.aid, act=b.dataset.act;
      if(act==="dropc"){ D.excludedC.add(aid); logFeedback("drop", aid, {tid:null, text:null}); toast("Left out of this section for this posting."); renderSheet(); persist(true); return; }
      if(act==="polishc"){ polishBullet(aid, "c"); return; }
      const i=E.findChosen(D, aid); if(!i) return;
      if(act!=="polish") lockCurrent();
      if(act==="keep"){ D.pinned.add(aid); logFeedback("keep", aid, {tid:i.t.id, text:i.t.text}); toast("Kept. It ranks higher in future matches."); }
      if(act==="swap"){ D.excluded.add(aid); D.pinned.delete(aid); logFeedback("swap", aid, {tid:i.t.id, text:i.t.text}); }
      if(act==="drop"){ D.excluded.add(aid); D.pinned.delete(aid); logFeedback("drop", aid, {tid:i.t.id, text:i.t.text}); toast("Dropped. It ranks lower in future matches."); }
      if(act==="polish"){ polishBullet(aid, "r"); return; }
      recompute(); persist(true);
    });
    $("#sheet").addEventListener("focusout", e=>{
      const ln=e.target.closest(".ln[contenteditable]");
      if(ln){ const txt=ln.textContent.replace(/\s+/g," ").trim(); if(!txt){ renderSheet(); return; }
        const m=E.resumeModel(D); const cur = ln.dataset.line==="core" ? (m.core_competencies.find(a=>a.label===ln.dataset.area)||{items:[]}).items.join(", ") : (ln.dataset.line==="summary" ? (m.summary||"") : m[ln.dataset.line].join(LINE_EDIT[ln.dataset.line].join));
        if(txt!==cur){ saveLineEdit(ln.dataset.line, ln.dataset.area, txt); renderSheet(); } return; }
      const el=e.target.closest(".bt[contenteditable]"); if(!el) return;
      const aid=el.dataset.aid, txt=el.textContent.replace(/\s+/g," ").trim();
      if(el.dataset.sec==="c"){ const b=E.resumeModel(D).engagements.flatMap(x=>x.bullets).find(b=>b.aid===aid); if(!b || !txt || txt===b.text) return; saveEditC(aid, txt); renderSheet(); return; }
      const i=E.findChosen(D, aid); if(!i) return; const cur=D.edits[aid]??i.t.text; if(!txt || txt===cur) return;
      saveEdit(aid, i, txt); renderSheet();
    });
    $("#sheet").addEventListener("change", e=>{ const s=e.target.closest("select[data-mv]"); if(!s) return; const p=E.parsePlace(s.value); if(!p){ s.value=""; return; } moveFresh([[+s.dataset.mv, p]]); });
    $("#sheet").addEventListener("keydown", e=>{ if(e.key==="Enter" && e.target.closest(".bt,.ln")){ e.preventDefault(); e.target.blur(); } });
    $("#sumToggle").onchange=async e=>{
      if(!e.target.checked){ D.summaryOn=false; renderSheet(); persist(true); return; }
      if(!D.sample){ e.target.checked=false; toast("Claude isn't available in this view, so the summary can't be written here."); return; }
      if(D.phase==="idle"||!Object.keys(D.req).length){ e.target.checked=false; toast("Match a posting first; the summary is written for that posting."); return; }
      toast("Claude is writing the summary from this draft's claims…");
      try{ const {text, claims}=await claudeSummary(); D.summary=text; D.summaryClaims=claims; D.summaryOn=true; renderSheet(); persist(true); toast(`Summary added (${text.split(/\s+/).length} words).`); }
      catch(err){ e.target.checked=false; D.summaryOn=false; toast(err?.code==="qa"?`The summary didn't pass the evidence check (${err.message}). Try again.`:(err?.code==="not_granted"?"Allow Claude on this page to write the summary.":"Claude couldn't write the summary. Try again.")); }
    };
    $("#pdfBtn").onclick=()=>saveFile("pdf"); $("#docxBtn").onclick=()=>saveFile("docx");
    $("#copyBtn").onclick=async()=>{ const txt=plainText(E.resumeModel(D), layout());
      try{ await navigator.clipboard.writeText(txt); toast("Resume text copied."); }
      catch{ const r=document.createRange(); r.selectNodeContents($("#sheet")); const s=getSelection(); s.removeAllRanges(); s.addRange(r); toast("Copy was blocked. The resume is selected, so press Ctrl+C."); } };
  },
  refresh(){ recompute(); renderQuestions(); loadRecent(); }});

Hub.register({id:"postings", label:"Postings & outcomes", order:3,
  mount(){ $("#postings").addEventListener("click", e=>{ const b=e.target.closest("button"); if(!b) return;
    if(b.dataset.open){ openSaved(b.dataset.open); Hub.show("match"); }
    if(b.dataset.saveoc) saveOutcome(b.dataset.saveoc, b.closest(".card")); }); },
  refresh(){ renderPostings(); }});

Hub.register({id:"backup", label:"Backup & privacy", order:4,
  mount(){
    $("#backupBtn").onclick=downloadBackup;
    $("#restoreFile").addEventListener("change", async e=>{ const f=e.target.files[0]; e.target.value=""; if(!f) return;
      try{ loadBackup(JSON.parse(await f.text()), `Loaded ${f.name}.`); }catch(err){ toast(err?.message||"That file isn't a Career Companion Hub backup."); } });
    $("#wipeConfirm").addEventListener("input", e=>{ $("#wipeBtn").disabled = e.target.value.trim().toLowerCase()!=="delete"; });
    $("#wipeBtn").onclick=()=>{ D.ctl1?.abort(); D.ctlQ?.abort(); store.wipe(); resetDraft(); D.adj={}; $("#wipeConfirm").value=""; $("#wipeBtn").disabled=true; renderAll(); renderStorage(); Hub.show("evidence"); toast("Everything on this page was deleted."); };
    $("#backupNote").textContent="A backup is a JSON file with your whole record: evidence, entries, postings, answers and outcomes. Load it here on any device to continue.";
  },
  refresh(){ renderStorage(); }});

Hub.register({id:"how", label:"How it works", order:5,
  mount(){ if(GUIDE_URL) $("#guideNote").innerHTML=`Read the guide: <a href="${esc(GUIDE_URL)}" target="_blank" rel="noopener">what to bring, what the checks mean, and where your data goes</a>.`; },
  refresh(){ $("#tiers2").innerHTML=tiersHtml(); }});

/* ------------------------------ boot ------------------------------ */
async function boot(hot){
  store=new BrowserStore(RotCore.VERSION);
  try{ const r=await fetch("taxonomy/gtm_v1.json"); if(!r.ok) throw new Error(String(r.status)); taxonomy=await r.json(); }
  catch(e){ $("#stats").innerHTML=`<span class="chip warn">The skill taxonomy couldn't load. Reload the page.</span>`; return; }
  T=RotCore.createEngine({bank:{tags:taxonomy.tags}, settings:{}});
  E=RotCore.createEngine({ get bank(){ return bank(); }, get settings(){ return SET(); } });
  try{ await loadTemplate(); }catch(e){ console.warn("template", e); }
  store.on(()=>{ bankCache=null; renderStats(); renderSideSoon(); });
  D.adj=adjFromFeedback();
  Hub.mount({store, D});
  const ws=store.get("workspace"), st=(hot&&hot.state)||(ws.current&&store.get("sessions")[ws.current])||ws.idle||null;
  if(st && restoreState(st)) showRestoreNote(st);
  renderStats();
  const C=window.claude, useCap=n=>(C&&C.use) ? C.use(n).catch(()=>null) : Promise.resolve(null);
  useCap("downloads").then(d=>{ D.downloads=d; });
  useCap("sample").then(s=>{ D.sample=s; renderStats(); if(D.questions.length) renderQuestions(); });
  /* other page modules (intake.js) get the page's record helpers once everything is mounted */
  Hub.emit("ready", {store, D, get E(){ return E; }, get T(){ return T; }, bank, writeAll, toast, tagsFor, val, today, slug, revealRoles, refreshEvidence(){ renderIdentity(); renderRoles(); renderLists(); renderReady(); $("#tiers").innerHTML=tiersHtml(); renderStats(); }});
}
(function(){
  let booted=false; const once=d=>{ if(booted) return; booted=true; boot(d||{}); };
  let hot=null; try{ hot=window.claude&&window.claude.hot; }catch{}
  try{ if(hot && typeof hot.snapshot==="function") hot.snapshot(()=>({state:(store&&E)?serializeState():null})); }catch{}
  if(hot && typeof hot.ready==="function"){ try{ hot.ready(once); }catch{ once({}); } setTimeout(()=>once({}),3000); }
  else once((hot&&hot.data)||{});
})();
window.addEventListener("pagehide", ()=>{ try{ saveNow(); }catch{} });
