"use strict";
/* Career Companion Hub · intake: a resume (or LinkedIn export) becomes verbatim evidence lines; Claude, or a layout heuristic, points
   at lines (never rewrites them); deterministic checks; a review the person edits; then a merge into the record with corroboration
   and conflicts. Pure functions live on CCH.Intake (tested in Node); the DOM part mounts when the page says it is ready. */
(function(root){
const R = root.RotCore || (typeof require==="function" ? require("../core/rot_core.js") : null);
const {norm, cleanBullet, TOOL_LEXICON} = R.util, {numberTokens} = R.qa, {valuesConflict} = R.claims;
const clone = o => JSON.parse(JSON.stringify(o));
const MONTHS={jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,sept:9,oct:10,nov:11,dec:12};
const MON="(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\\.?";
const DATE=`(?:${MON}\\s+(?:19|20)\\d{2}|(?:0?[1-9]|1[0-2])[\\/.](?:19|20)\\d{2}|(?:19|20)\\d{2}-(?:0[1-9]|1[0-2])|(?:19|20)\\d{2})`;
const PRESENT="(?:present|current|now|today|ongoing)";
const RANGE_RE=new RegExp(`(${DATE})\\s*(?:[-–—]|to|until|through)\\s*(${DATE}|${PRESENT})`, "i");
const BULLET_RE=/^[•·\-–—*▪●○◦■]\s*/;
const COMPANY_RE=/\b(inc|llc|ltd|co|corp|corporation|company|group|labs|media|metrics|software|health|partners|technologies|systems|solutions|studio|agency|network|adtech|bank|capital|holdings|publications|ventures)\b\.?/i;
const SECTION_RE={experience:/^(professional |work |relevant |career )?(experience|employment|history)\b/i, education:/^education\b/i, certs:/^(certifications?|licen[cs]es?|credentials?|certifications? & tools)\b/i,
  skills:/^(core |key |technical )?(skills|competencies|areas of expertise|expertise|tools|technologies|tools & technologies|technical proficiencies)\b/i, summary:/^(professional |executive )?(summary|profile|about|overview)\b/i};
const STOP=new Set(["with","from","that","this","into","over","across","through","while","their","were","have","than","them","then","also","within","under","after","before","during","which","where","when","what","about","first","year","years","team"]);

/* ------------------------------ dates ------------------------------ */
function normDate(s){
  if(s==null) return null; s=String(s).trim(); if(!s || new RegExp(`^${PRESENT}$`,"i").test(s)) return null;
  let m;
  if((m=/^((?:19|20)\d{2})-(\d{2})(?:-\d{2})?$/.exec(s))) return `${m[1]}-${m[2]}`;
  if((m=/^(\d{1,2})[\/.]((?:19|20)\d{2})$/.exec(s))) return `${m[2]}-${String(m[1]).padStart(2,"0")}`;
  if((m=new RegExp(`^(${MON})\\s+((?:19|20)\\d{2})$`,"i").exec(s))){ const k=m[1].toLowerCase().replace(/\.$/,""); const n=MONTHS[k.slice(0,4)]||MONTHS[k.slice(0,3)]; return n?`${m[2]}-${String(n).padStart(2,"0")}`:m[2]; }
  if((m=/^((?:19|20)\d{2})$/.exec(s))) return m[1];
  return null;
}
const ym=(v,end)=>v?(String(v).length===4?`${v}-${end?"12":"01"}`:String(v)):(end?"9999-12":null);
function overlap(aS,aE,bS,bE){ const as=ym(aS), bs=ym(bS); if(!as||!bs) return false; return as<=ym(bE,true) && bs<=ym(aE,true); }

/* ------------------------------ lines from a document ------------------------------ */
function linesFromText(text){ return String(text||"").split(/\r?\n/).map(t=>t.replace(/\s+/g," ").trim()).filter(Boolean).slice(0,400).map((t,i)=>({id:i+1, text:t, bullet:BULLET_RE.test(t)})); }
const W_NS="http://schemas.openxmlformats.org/wordprocessingml/2006/main";
async function linesFromDocx(buf, JSZip){
  const zip=await JSZip.loadAsync(buf); const docFile=zip.file("word/document.xml"); if(!docFile) throw new Error("Not a Word document (no word/document.xml).");
  const xml=new DOMParser().parseFromString(await docFile.async("string"), "application/xml"), out=[];
  for(const p of xml.getElementsByTagNameNS(W_NS, "p")){
    let t=""; for(const n of p.getElementsByTagNameNS(W_NS, "*")){ if(n.localName==="t") t+=n.textContent; else if(n.localName==="tab"||n.localName==="br") t+=" "; }
    t=t.replace(/\s+/g," ").trim(); if(t) out.push({text:t, bullet:p.getElementsByTagNameNS(W_NS,"numPr").length>0});
  }
  let authored_at=null; const cf=zip.file("docProps/core.xml");
  if(cf){ const core=await cf.async("string"); const m=/<dcterms:modified[^>]*>([^<]+)</.exec(core)||/<dcterms:created[^>]*>([^<]+)</.exec(core); if(m) authored_at=m[1].slice(0,10); }
  return {lines:out.slice(0,400).map((l,i)=>({id:i+1, text:l.text, bullet:l.bullet||BULLET_RE.test(l.text)})), authored_at};
}
async function linesFromPdf(buf, pdfjsLib, workerSrc){
  if(workerSrc && pdfjsLib.GlobalWorkerOptions) pdfjsLib.GlobalWorkerOptions.workerSrc=workerSrc;
  const pdf=await pdfjsLib.getDocument({data:buf}).promise, out=[];
  for(let p=1;p<=pdf.numPages;p++){
    const page=await pdf.getPage(p), tc=await page.getTextContent(), rows=new Map();
    for(const it of tc.items){ if(!it.str) continue; const y=Math.round(it.transform[5]/2)*2; if(!rows.has(y)) rows.set(y,[]); rows.get(y).push({x:it.transform[4], w:it.width||0, s:it.str}); }
    for(const y of [...rows.keys()].sort((a,b)=>b-a)){
      const items=rows.get(y).sort((a,b)=>a.x-b.x); let t=""; let end=null;
      for(const it of items){ if(end!=null && it.x-end>1.5 && !t.endsWith(" ") && !it.s.startsWith(" ")) t+=" "; t+=it.s; end=it.x+it.w; }
      t=t.replace(/\s+/g," ").trim(); if(t) out.push({text:t, bullet:BULLET_RE.test(t)});
    }
  }
  return {lines:out.slice(0,400).map((l,i)=>({id:i+1, text:l.text, bullet:l.bullet})), authored_at:null};
}

/* ------------------------------ the layout heuristic (no Claude) ------------------------------ */
function splitItems(s){ const out=[]; let depth=0, cur=""; for(const ch of String(s||"")){ if(ch==="(") depth++; if(ch===")") depth=Math.max(0,depth-1);
  if(depth===0 && (ch==="•"||ch==="|"||ch===";"||ch===","||ch==="·")){ if(cur.trim()) out.push(cur.trim()); cur=""; } else cur+=ch; } if(cur.trim()) out.push(cur.trim());
  return out.map(x=>x.replace(/^[\s\-–—]+|[\s.]+$/g,"")).filter(x=>x.length>1 && x.length<=60); }
const LEX=new Map(TOOL_LEXICON.map(t=>[norm(t.replace(/\.io$/,"")), t]));
const isTool=s=>LEX.has(norm(s));
function splitHeader(s){
  const pm=/\(([^)]+)\)\s*$/.exec(s); const base=s.replace(/\s*\([^)]*\)\s*$/,"");
  let parts=base.split(/\s+\|\s+|\s+[–—]\s+|\s+·\s+|\s+at\s+/).map(x=>x.trim()).filter(Boolean);
  if(parts.length<2) parts=base.split(/,\s+(?=[A-Z])/).map(x=>x.trim()).filter(Boolean);   // "Title, Employer" only when no stronger separator is present, so "Denver, CO" survives
  let title=parts[0]||"", employer=parts[1]||"", location=parts[2]||(pm?pm[1]:"");
  if(COMPANY_RE.test(title) && !COMPANY_RE.test(employer)) [title, employer]=[employer, title];
  return {title:title.replace(/\s*\([^)]*\)\s*$/,"").trim(), employer:employer.replace(/\s*\([^)]*\)\s*$/,"").trim(), location:location.replace(/[()]/g,"").trim()||null};
}
function parseEdu(t, id){
  if(!/\b(university|college|institute|school|academy|b\.?a\.?|b\.?s\.?|m\.?s\.?|mba|bachelor|master|associate|ph\.?d)\b/i.test(t)) return null;
  const year=(/\b(19|20)\d{2}\b/.exec(t)||[""])[0];
  const parts=t.split(/\s+[—–|]\s+|,\s+(?=[A-Z])|\s+\(/).map(x=>x.replace(/[()]/g,"").trim()).filter(Boolean);
  const school=parts.find(p=>/university|college|institute|school|academy/i.test(p))||parts[0]||t;
  const degree=t.replace(school,"").replace(year,"").replace(/[—–|()]/g," ").replace(/\s+/g," ").replace(/^[\s,]+|[\s,]+$/g,"").trim()||null;
  return {school, degree, date:year||null, lines:[id]};
}
function parseCert(t, id){
  const year=(/\b(19|20)\d{2}\b/.exec(t)||[""])[0]; const s=t.replace(/\(?\b(19|20)\d{2}\b\)?/,"").replace(/\s+/g," ").trim().replace(/[,;–—-]\s*$/,"");
  const parts=s.split(/\s+[—–|]\s+|,\s+/).map(x=>x.trim()).filter(Boolean); if(!parts.length) return null;
  return {name:parts[0], issuer:parts[1]||null, date:year||null, lines:[id]};
}
function heuristic(lines){
  const L=lines, P={identity:{lines:L.slice(0,3).map(l=>l.id)}, roles:[], education:[], certifications:[], skills:[], tools:[], notes:["Structure guessed from the layout, without Claude. Check titles, employers and dates before adding."]};
  const top=L.slice(0,6).map(l=>l.text).join(" | ");
  const em=/[\w.+-]+@[\w-]+\.[\w.-]+/.exec(top); if(em) P.identity.email=em[0];
  const ph=/(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/.exec(top); if(ph) P.identity.phone=ph[0].trim();
  const li=/(?:https?:\/\/)?(?:www\.)?linkedin\.com\/in\/[\w-]+/i.exec(top); if(li) P.identity.linkedin=/^https?:/i.test(li[0])?li[0]:"https://"+li[0];
  const loc=/\b([A-Z][a-zA-Z.]+(?: [A-Z][a-zA-Z.]+)*, [A-Z]{2})\b/.exec(top); if(loc) P.identity.location=loc[1];
  const first=L[0]&&L[0].text; if(first && first.split(/\s+/).length<=5 && !/\d|@|\|/.test(first)) P.identity.name=first;
  let sec="top", cur=null;
  const toolsPrefix=t=>/^(tools|technologies|software|systems|platforms|tech stack)\s*[:：]\s*(.+)$/i.exec(t);
  for(let i=0;i<L.length;i++){
    const l=L[i], t=l.text;
    const s=t.length<48 && Object.entries(SECTION_RE).find(([,re])=>re.test(t)); if(s){ sec=s[0]; cur=null; if(sec==="skills" && /^(tools|technologies)\b/i.test(t)) sec="tools"; continue; }
    const tp=toolsPrefix(t); if(tp && sec!=="experience"){ for(const x of splitItems(tp[2])) P.tools.push({name:x, line:l.id}); continue; }
    if(sec==="experience"||sec==="top"){
      const r=RANGE_RE.exec(t), isBullet=l.bullet||BULLET_RE.test(t);
      if(r && !isBullet){
        let rest=t.replace(r[0],"").replace(/^[\s|·•,–—-]+|[\s|·•,–—-]+$/g,"").trim(), header=[l.id];
        if(rest.replace(/[()]/g,"").trim().length<3 && i>0 && !P.roles.some(x=>x.header_lines.includes(L[i-1].id))){ rest=L[i-1].text; header.unshift(L[i-1].id); }
        const h=splitHeader(rest); if(!h.title && !h.employer) continue;
        cur={...h, start:normDate(r[1]), end:normDate(r[2]), header_lines:header, accomplishment_lines:[]}; P.roles.push(cur); sec="experience"; continue;
      }
      if(!r && !isBullet && i+1<L.length && !BULLET_RE.test(L[i+1].text) && RANGE_RE.test(L[i+1].text) && L[i+1].text.replace(RANGE_RE,"").replace(/[\s|·•,–—()-]+/g,"").length<3) continue;   // header text; the date line below picks it up
      if(cur && sec==="experience" && (isBullet || (t.length>40 && /[a-z]/.test(t)))) cur.accomplishment_lines.push(l.id);
    } else if(sec==="education"){ const e=parseEdu(t, l.id); if(e) P.education.push(e); else { const c=/certif|qualif/i.test(t)?parseCert(t,l.id):null; if(c) P.certifications.push(c); } }
    else if(sec==="certs"){ const e=/university|college|b\.?a\.?|b\.?s\.?|mba\b/i.test(t)?parseEdu(t,l.id):null; if(e) P.education.push(e); else { const c=parseCert(t, l.id); if(c) P.certifications.push(c); } }
    else if(sec==="skills"||sec==="tools"){ const lab=/^([A-Za-z][A-Za-z /&-]{1,30}):\s*(.+)$/.exec(t); for(const x of splitItems(lab?lab[2]:t)) (sec==="tools"||isTool(x)?P.tools:P.skills).push(sec==="tools"||isTool(x)?{name:x, line:l.id}:{text:x, line:l.id}); }
  }
  return P;
}

/* ------------------------------ Claude: the prompt and its reply ------------------------------ */
const PROMPT_VERSION="intake@1";
function prompt(lines, kind){
  return `A person uploaded a document about their own career (${kind==="linkedin"?"a LinkedIn profile export":"a resume"}). It is given as numbered lines, exactly as extracted. Your job is to point at lines, never to write.
Reply with ONLY one JSON object:
{"identity":{"name":string|null,"email":string|null,"phone":string|null,"location":string|null,"linkedin":string|null,"lines":[line numbers]},
 "roles":[{"title":string,"employer":string,"location":string|null,"start":"YYYY-MM"|"YYYY"|null,"end":"YYYY-MM"|"YYYY"|null,"header_lines":[line numbers],"accomplishment_lines":[line numbers]}],
 "education":[{"school":string,"degree":string|null,"date":"YYYY"|null,"lines":[line numbers]}],
 "certifications":[{"name":string,"issuer":string|null,"date":"YYYY"|null,"lines":[line numbers]}],
 "skills":[{"text":string,"line":line number}],
 "tools":[{"name":string,"line":line number}]}
Rules:
- An accomplishment is one whole line describing something the person did in a role. Cite its number under that role. Never merge, split or reword lines. A summary paragraph, a skills list or a header is not an accomplishment.
- Titles, employers, locations, schools, degrees and certification names are copied from the cited lines. Dates: month names become YYYY-MM; a current role has end null.
- Roles in the document's order. Every role needs a title and an employer.
- Skills are short phrases from a skills or competencies section. Tools are software, platforms or systems named anywhere, one entry each. Cite the line each came from.
- Skip anything you cannot tie to a line.

LINES
${lines.map(l=>`L${l.id}: ${l.text}`).join("\n")}`;
}
function parse(r, lines){
  const n=lines.length, ok=id=>Number.isInteger(id)&&id>=1&&id<=n, ids=a=>[...new Set((Array.isArray(a)?a:[]).map(x=>+String(x).replace(/^L/i,"")).filter(ok))];
  const str=v=>typeof v==="string"&&v.trim()?v.trim():null, one=v=>{ const x=+String(v??"").replace(/^L/i,""); return ok(x)?x:null; };
  const id0=r&&typeof r.identity==="object"&&r.identity||{};
  return {source:"claude", notes:[],
    identity:{name:str(id0.name), email:str(id0.email), phone:str(id0.phone), location:str(id0.location), linkedin:str(id0.linkedin), lines:ids(id0.lines)},
    roles:(Array.isArray(r?.roles)?r.roles:[]).map(x=>({title:str(x.title)||"", employer:str(x.employer)||"", location:str(x.location), start:normDate(x.start), end:normDate(x.end), header_lines:ids(x.header_lines), accomplishment_lines:ids(x.accomplishment_lines)})).filter(x=>x.title||x.employer),
    education:(Array.isArray(r?.education)?r.education:[]).map(x=>({school:str(x.school)||"", degree:str(x.degree), date:normDate(x.date), lines:ids(x.lines)})).filter(x=>x.school),
    certifications:(Array.isArray(r?.certifications)?r.certifications:[]).map(x=>({name:str(x.name)||"", issuer:str(x.issuer), date:normDate(x.date), lines:ids(x.lines)})).filter(x=>x.name),
    skills:(Array.isArray(r?.skills)?r.skills:[]).map(x=>({text:str(x.text)||"", line:one(x.line)})).filter(x=>x.text),
    tools:(Array.isArray(r?.tools)?r.tools:[]).map(x=>({name:str(x.name)||"", line:one(x.line)})).filter(x=>x.name)};
}
/* deterministic checks on either proposal: cited lines exist, entries are real lines, nothing appears twice */
function check(P, lines){
  const byId=Object.fromEntries(lines.map(l=>[l.id,l])), seen=new Set(), notes=[...(P.notes||[])];
  const wordy=id=>byId[id] && byId[id].text.split(/\s+/).length>=4;
  P.roles=P.roles.filter(r=>{ if(!r.title||!r.employer){ notes.push(`Skipped a role without a title or employer (${r.title||r.employer||"?"}).`); return false; } return true; });
  for(const r of P.roles){
    r.header_lines=r.header_lines.filter(id=>byId[id]);
    r.accomplishment_lines=r.accomplishment_lines.filter(id=>byId[id] && wordy(id) && !r.header_lines.includes(id) && !seen.has(id) && seen.add(id));
    const head=r.header_lines.map(id=>norm(byId[id].text)).join(" ");
    r.flags=[]; if(head && !head.includes(norm(r.title))) r.flags.push("title not in the cited lines"); if(head && !head.includes(norm(r.employer))) r.flags.push("employer not in the cited lines");
    if(r.start && r.end && ym(r.start)>ym(r.end,true)) r.flags.push("start is after end");
  }
  const dd=(arr,key)=>{ const s=new Set(); return arr.filter(x=>{ const k=norm(x[key]); if(!k||s.has(k)) return false; s.add(k); return true; }); };
  P.education=dd(P.education,"school"); P.certifications=dd(P.certifications,"name"); P.skills=dd(P.skills.filter(x=>x.text.length<=60),"text"); P.tools=dd(P.tools.filter(x=>x.name.length<=60),"name");
  P.notes=notes; return P;
}
async function propose(lines, kind, sample, opts={}){
  if(!sample) return check(heuristic(lines), lines);
  const text=prompt(lines, kind); if(text.length>60000) throw Object.assign(new Error("too long"),{code:"prompt_too_large"});
  const r=await sample.json(text, {signal:opts.signal, modelTier:"default", cache:false});
  const P=check(parse(r, lines), lines);
  if(!P.roles.length){ const H=check(heuristic(lines), lines); H.notes.unshift("Claude found no roles, so the structure below was guessed from the layout."); return H; }
  return P;
}

/* ------------------------------ the merge plan: what the record becomes ------------------------------ */
const words=t=>new Set(String(t).toLowerCase().replace(/[^a-z0-9$%]+/g," ").split(" ").filter(w=>w.length>=4&&!STOP.has(w)));
function jaccard(a,b){ const A=words(a), B=words(b); if(!A.size||!B.size) return 0; let n=0; for(const w of A) if(B.has(w)) n++; return n/(A.size+B.size-n); }
/* two lines about the same accomplishment: identical numbers with some shared wording, or one line's numbers inside the other's;
   the same wording with different numbers is a conflict (the classic "$6.1M in one resume, $6.8M in the next") */
function relation(a, b){
  const A=numberTokens(a), B=numberTokens(b), j=jaccard(a, b);
  const eq=A.size===B.size && [...A].every(n=>B.has(n)), sub=[...A].every(n=>B.has(n)) || [...B].every(n=>A.has(n));
  if(eq){ if(A.size>=2) return j>=0.15?"same":null; if(A.size===1) return j>=0.35?"same":null; return j>=0.6?"same":null; }
  if(sub && j>=0.3) return "same";
  return j>=0.5?"conflict":null;
}
const val = f => f ? (f.resolution ? f.resolution.value : f.value) : null;
const slug = s => String(s||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"").slice(0,40) || "x";
/* P: the reviewed proposal (unchecked items removed, edits applied); record: {identity, sources, evidence, subjects, achievements}; returns the new record slices and a summary */
function plan(P, lines, record, ctx){
  const day=ctx.today||new Date().toISOString().slice(0,10), kind=P.kind||ctx.kind||"resume";
  const n=record.sources.filter(s=>/^src:u\d+$/.test(s.id)).length+1, sk=`u${n}`, srcId=`src:${sk}`, source_type=kind==="linkedin"?"PUBLIC_PROFILE":"HISTORICAL_RESUME";
  const sources=[...record.sources, {id:srcId, kind, label:ctx.label||"uploaded document", authored_at:ctx.authored_at||day, observed_at:day, source_type}];
  const evidence=[...record.evidence]; const evId=id=>`ev:${sk}:l${id}`; const byId=Object.fromEntries(lines.map(l=>[l.id,l]));
  for(const l of lines) evidence.push({id:evId(l.id), source:srcId, source_type, channel:`upload:${kind}`, quote:l.text, observed_at:day, locator:`line ${l.id}`});   // the whole document, verbatim, first
  const youRow=(id, quote, locator)=>{ evidence.push({id, source:"src:you", source_type:"USER_ENTERED", channel:"paste", quote, observed_at:day, locator}); return id; };
  if(!sources.some(s=>s.id==="src:you")) sources.push({id:"src:you", kind:"paste", label:"Typed on this page", authored_at:day, observed_at:day, source_type:"USER_ENTERED"});
  const subjects=clone(record.subjects), achievements=clone(record.achievements), identity={...record.identity};
  const sum={roles_new:0, roles_merged:0, entries_new:0, entries_corroborated:0, conflicts:0, education:0, certifications:0, skills:0, tools:0, lines:lines.length};
  const addFact=(s, pred, value, ids)=>{
    if(value==null||value==="") return; const f=s.facts[pred]||(s.facts[pred]={value:null, evidence:[], contradicting:[]}); const cur=val(f);
    if(cur==null||cur===""){ f.value=value; for(const i of ids) if(!f.evidence.includes(i)) f.evidence.push(i); return; }
    if(!valuesConflict(cur, value)){ for(const i of ids) if(!f.evidence.includes(i)) f.evidence.push(i); if((pred==="start"||pred==="end"||pred==="date") && !f.resolution && String(value).length>String(f.value||"").length) f.value=value; return; }   // a finer date wins
    f.contradicting=f.contradicting||[]; const c=f.contradicting.find(x=>!valuesConflict(x.value, value));
    if(c){ for(const i of ids) if(!c.evidence.includes(i)) c.evidence.push(i); } else { f.contradicting.push({value, evidence:[...ids]}); if(!f.resolution) sum.conflicts++; }
  };
  const roleSubs=()=>subjects.filter(s=>s.kind==="role"), taken=new Set(roleSubs().map(s=>s.key)); let rn=1; const newKey=()=>{ while(taken.has("r"+rn)) rn++; const k="r"+rn; taken.add(k); return k; };
  const g=(s,p)=>val(s.facts&&s.facts[p]);
  for(const r of P.roles){
    const hid=r.header_lines.map(evId); const edited=r.edited?[youRow(`ev:you:${slug(r.employer)}-${slug(r.title)}:review`, [r.title, r.employer, r.location, r.start?`${r.start} – ${r.end||"Present"}`:null].filter(Boolean).join(" | "), "review edit")]:[];
    let s=roleSubs().find(x=>norm(g(x,"employer"))===norm(r.employer) && (norm(g(x,"title"))===norm(r.title) || overlap(g(x,"start"), g(x,"end"), r.start, r.end)));
    if(s) sum.roles_merged++; else { s={id:`role:${newKey()}`, kind:"role", key:null, sort:99, hidden:false, facts:{}}; s.key=s.id.slice(5); subjects.push(s); sum.roles_new++; }
    for(const [pred,v] of [["title",r.title],["employer",r.employer],["location",r.location],["start",r.start],["end",r.end]]) addFact(s, pred, v, hid.concat(edited));
    if(r.end===null && r.start && s.facts.end && s.facts.end.value && !s.facts.end.resolution){ /* a document that says Present for a role another document ended: keep both on file */ const f=s.facts.end; f.contradicting=f.contradicting||[]; if(!f.contradicting.some(c=>c.value===null)){ f.contradicting.push({value:null, evidence:hid}); sum.conflicts++; } }
    const mine=achievements.filter(a=>a.role===s.key && !a.engagement); let k=mine.length;
    for(const id of r.accomplishment_lines){
      const line=byId[id].text, ed=r.edits&&r.edits[id], text=ed||line, canonical=cleanBullet(text);
      let rel=null; const twin=mine.find(a=>(rel=relation(a.canonical, text)));
      if(twin && rel==="same"){ if(!twin.evidence.includes(evId(id))) twin.evidence.push(evId(id)); sum.entries_corroborated++; continue; }
      if(twin){ twin.contradicting=twin.contradicting||[]; if(!twin.contradicting.some(c=>norm(c.value)===norm(canonical))) { twin.contradicting.push({value:canonical, evidence:[evId(id)]}); if(!twin.resolution) sum.conflicts++; } continue; }
      let aid; do{ aid=`${s.key}-${++k}`; }while(achievements.some(a=>a.id===aid));
      const ev=[evId(id)]; if(ed && norm(ed)!==norm(line)) ev.push(youRow(`ev:you:${aid}`, ed, "review edit"));
      const rec={id:aid, role:s.key, engagement:null, canonical, evidence:ev, contradicting:[], tags:ctx.tagsFor?ctx.tagsFor(text):{}, metrics:[], origin:"intake"}; achievements.push(rec); mine.push(rec); sum.entries_new++;
    }
  }
  const findSub=(kind,pred,value)=>subjects.find(x=>x.kind===kind && norm(g(x,pred))===norm(value));
  for(const e of P.education){ const ids=e.lines.map(evId); let s=findSub("education","school",e.school); if(!s){ let id=`edu:${slug(e.school)}`; while(subjects.some(x=>x.id===id)) id+="-2"; s={id, kind:"education", facts:{}}; subjects.push(s); sum.education++; }
    addFact(s,"school",e.school,ids); addFact(s,"degree",e.degree,ids); addFact(s,"date",e.date,ids); }
  for(const c of P.certifications){ const ids=c.lines.map(evId); let s=findSub("credential","name",c.name); if(!s){ let id=`cred:${slug(c.name)}`; while(subjects.some(x=>x.id===id)) id+="-2"; s={id, kind:"credential", facts:{}}; subjects.push(s); sum.certifications++; }
    addFact(s,"name",c.name,ids); addFact(s,"issuer",c.issuer,ids); addFact(s,"date",c.date,ids); }
  const bare=t=>norm(String(t).replace(/\s*\([^)]*\)/g,""));   // "Salesforce (admin)" is the Salesforce already on file
  const addPhrase=(kind,pred,prefix,text,line,counter)=>{ let s=findSub(kind,pred,text)||subjects.find(x=>x.kind===kind && bare(g(x,pred))===bare(text)); const ids=line?[evId(line)]:[];
    if(s){ const f=s.facts[pred]; for(const i of ids) if(!f.evidence.includes(i)) f.evidence.push(i); return; }
    let id=`${prefix}:${slug(text)}`; while(subjects.some(x=>x.id===id)) id+="-2";
    subjects.push({id, kind, sort:subjects.filter(x=>x.kind===kind).length, tags:ctx.tagList?ctx.tagList(text):[], facts:{[pred]:{value:text, evidence:ids, contradicting:[]}}}); sum[counter]++; };
  for(const x of P.skills) addPhrase("expertise","text","expertise",x.text,x.line,"skills");
  for(const x of P.tools) addPhrase("tool","name","tool",x.name,x.line,"tools");
  const I=P.identity||{}; for(const k of ["name","location","phone","email"]) if(!(identity[k]||"").trim() && I[k]) identity[k]=I[k];
  if(I.linkedin && !(identity.links||[]).some(l=>/linkedin/i.test((l.label||"")+(l.url||"")))) identity.links=[{label:"LinkedIn", url:I.linkedin}, ...(identity.links||[])];
  return {sources, evidence, subjects, achievements, identity, summary:sum};
}

const Intake={normDate, overlap, linesFromText, linesFromDocx, linesFromPdf, heuristic, prompt, parse, check, propose, plan, jaccard, relation, PROMPT_VERSION};
if(root.CCH) root.CCH.Intake=Intake; else root.CCH={Intake};
if(typeof module!=="undefined" && module.exports) module.exports=Intake;

/* ------------------------------ the page: upload, review, add ------------------------------ */
if(typeof document!=="undefined" && root.CCH && root.CCH.Hub){
  const $=s=>document.querySelector(s); let ctx=null, cur=null;   // cur = {lines, P, meta}
  const esc=s=>R.util.esc(s);
  root.CCH.Hub.on("ready", c=>{ ctx=c;
    $("#intakeScan").onclick=scan; $("#intakeFile").addEventListener("change", ()=>{ const f=$("#intakeFile").files[0]; $("#intakeFileName").textContent=f?`${f.name} · ${Math.round(f.size/1024)} KB`:""; if(f) $("#intakeText").value=""; });
    $("#intakeReview").addEventListener("click", e=>{ const b=e.target.closest("button"); if(!b) return; if(b.id==="intakeApply") apply(); if(b.id==="intakeDiscard") discard(); });
  });
  function status(html, busy){ const el=$("#intakeStatus"); el.innerHTML=(busy?`<span class="spin" aria-hidden="true"></span> `:"")+html; el.hidden=false; }
  async function readInput(){
    const f=$("#intakeFile").files[0], pasted=$("#intakeText").value.trim();
    if(f){ const name=f.name.toLowerCase(), buf=await f.arrayBuffer(), authored=f.lastModified?new Date(f.lastModified).toISOString().slice(0,10):null;
      if(name.endsWith(".docx")){ if(!root.JSZip) throw new Error("The Word reader didn't load. Reload the page."); const r=await linesFromDocx(buf, root.JSZip); return {...r, authored_at:r.authored_at||authored, label:f.name}; }
      if(name.endsWith(".pdf")){ if(!root.pdfjsLib) throw new Error("The PDF reader didn't load. Paste the text instead."); const r=await linesFromPdf(buf, root.pdfjsLib, "vendor/pdf.worker.min.js"); return {...r, authored_at:authored, label:f.name}; }
      if(name.endsWith(".txt")||name.endsWith(".md")||f.type.startsWith("text/")) return {lines:linesFromText(new TextDecoder().decode(buf)), authored_at:authored, label:f.name};
      throw new Error("Use a .docx, .pdf or .txt file, or paste the text."); }
    if(pasted) return {lines:linesFromText(pasted), authored_at:null, label:"pasted text"};
    throw new Error("Choose a file or paste the text of your resume first.");
  }
  async function scan(){
    if(!ctx) return; const kind=$("#intakeKind").value; $("#intakeReview").hidden=true; $("#intakeScan").disabled=true;
    try{
      status("Reading the document…", true);
      const src=await readInput(); if(src.lines.length<5) throw new Error("That document has fewer than five lines of text. If it is a scanned PDF, paste the text instead.");
      const sample=ctx.D.sample; let P;
      if(sample){ status(`Claude is mapping ${src.lines.length} lines to roles, entries, education and tools… <button class="ghost" id="intakeStop">Stop</button>`, true); const ctl=new AbortController(); $("#intakeStop").onclick=()=>ctl.abort();
        try{ P=await propose(src.lines, kind, sample, {signal:ctl.signal}); }
        catch(e){ if(e?.code==="cancelled") { status("Stopped."); return; } P=check(heuristic(src.lines), src.lines); P.notes.unshift(e?.code==="not_granted"?"Claude isn't allowed on this page, so the structure was guessed from the layout.":`Claude couldn't map this document (${esc(e?.code||e?.message||"error")}), so the structure was guessed from the layout.`); } }
      else P=await propose(src.lines, kind, null);
      P.kind=kind; cur={lines:src.lines, P, meta:{label:src.label, authored_at:src.authored_at}};
      status(`${src.lines.length} lines read from <b>${esc(src.label)}</b>. Review below, untick anything that is wrong, edit what needs it, then add it to your record.`);
      renderReview();
    }catch(e){ console.warn("intake", e); status(`<span class="err">${esc(e?.message||String(e))}</span>`); }
    finally{ $("#intakeScan").disabled=false; }
  }
  function renderReview(){
    const {lines, P}=cur, byId=Object.fromEntries(lines.map(l=>[l.id,l])), H=[];
    const box=(name, checked=true)=>`<input type="checkbox" name="${name}" ${checked?"checked":""}>`;
    H.push(`<div class="rvhead"><b>Found:</b> ${P.roles.length} role${P.roles.length===1?"":"s"}, ${P.roles.reduce((a,r)=>a+r.accomplishment_lines.length,0)} accomplishment lines, ${P.education.length} education, ${P.certifications.length} certification${P.certifications.length===1?"":"s"}, ${P.skills.length} skills, ${P.tools.length} tools.${P.notes.length?` <span class="hint">${P.notes.map(esc).join(" ")}</span>`:""}</div>`);
    const I=P.identity||{}; if(I.name||I.email||I.phone||I.location||I.linkedin) H.push(`<div class="rvsec"><h3>Contact details <span class="hint">(fill only what your record lacks)</span></h3><div class="row2">${["name","location","phone","email","linkedin"].map(k=>`<label class="f">${k}<input type="text" data-id="${k}" value="${esc(I[k]||"")}"></label>`).join("")}</div></div>`);
    P.roles.forEach((r,ri)=>{
      H.push(`<div class="rvrole" data-ri="${ri}"><div class="rvtop"><label class="rvinc">${box("role")} <b>Role ${ri+1}</b></label>${r.flags&&r.flags.length?`<span class="pill warn">${esc(r.flags.join("; "))}</span>`:""}<span class="hint">lines ${r.header_lines.join(", ")}</span></div>
        <div class="head">${[["title","Title"],["employer","Employer"],["location","Location"],["start","Start (YYYY-MM)"],["end","End (blank = Present)"]].map(([k,l])=>`<label class="f">${l}<input type="text" data-f="${k}" value="${esc(r[k]||"")}"></label>`).join("")}</div>
        <ul class="lines">${r.accomplishment_lines.map(id=>`<li data-ln="${id}"><label class="rvline">${box("line")}<span class="ln-no">L${id}</span></label><input type="text" data-line value="${esc(byId[id].text.replace(BULLET_RE,""))}"></li>`).join("")||`<li class="hint">No accomplishment lines were found under this role.</li>`}</ul></div>`);
    });
    const list=(title, arr, name, fmt)=>{ if(!arr.length) return; H.push(`<div class="rvsec"><h3>${title}</h3><ul class="lines rvflat">${arr.map((x,i)=>`<li data-i="${i}"><label class="rvline">${box(name)}</label><span>${fmt(x)}</span>${x.line||x.lines?`<span class="ln-no">L${x.line||x.lines.join(",")}</span>`:""}</li>`).join("")}</ul></div>`); };
    list("Education", P.education, "edu", e=>`<b>${esc(e.school)}</b>${e.degree?` — ${esc(e.degree)}`:""}${e.date?` (${esc(e.date)})`:""}`);
    list("Certifications", P.certifications, "cert", c=>`<b>${esc(c.name)}</b>${c.issuer?` — ${esc(c.issuer)}`:""}${c.date?` (${esc(c.date)})`:""}`);
    list("Skills", P.skills, "skill", s=>esc(s.text));
    list("Tools", P.tools, "tool", t=>esc(t.name));
    H.push(`<div class="row"><button class="primary" id="intakeApply">Add to my record</button><button id="intakeDiscard">Discard</button><span class="hint">Every line you keep is stored verbatim as evidence; entries print in a tidied form.</span></div>`);
    const el=$("#intakeReview"); el.innerHTML=H.join(""); el.hidden=false;
  }
  function readReview(){
    const P=clone(cur.P), el=$("#intakeReview");
    const I=P.identity||{}; el.querySelectorAll("[data-id]").forEach(i=>{ I[i.dataset.id]=i.value.trim()||null; }); P.identity=I;
    P.roles=P.roles.filter((r,ri)=>{ const card=el.querySelector(`.rvrole[data-ri="${ri}"]`); if(!card||!card.querySelector('input[name="role"]').checked) return false;
      const before=JSON.stringify([r.title,r.employer,r.location,r.start,r.end]);
      card.querySelectorAll("[data-f]").forEach(i=>{ const v=i.value.trim(); r[i.dataset.f]= i.dataset.f==="start"||i.dataset.f==="end" ? normDate(v) : (v||null); });
      r.title=r.title||""; r.employer=r.employer||""; r.edited = JSON.stringify([r.title,r.employer,r.location,r.start,r.end])!==before;
      r.edits={}; r.accomplishment_lines=r.accomplishment_lines.filter(id=>{ const li=card.querySelector(`li[data-ln="${id}"]`); if(!li||!li.querySelector('input[name="line"]').checked) return false; const v=li.querySelector("[data-line]").value.trim(); if(v && norm(v)!==norm(cur.lines[id-1].text.replace(BULLET_RE,""))) r.edits[id]=v; return !!v; });
      return !!(r.title&&r.employer); });
    const keep=(arr,name)=>arr.filter((x,i)=>{ const li=el.querySelector(`li[data-i="${i}"] input[name="${name}"]`); return !li || li.checked; });
    P.education=keep(P.education,"edu"); P.certifications=keep(P.certifications,"cert"); P.skills=keep(P.skills,"skill"); P.tools=keep(P.tools,"tool");
    return P;
  }
  function apply(){
    if(!cur||!ctx) return; const P=readReview(), store=ctx.store;
    const record={identity:store.get("identity"), sources:store.get("sources"), evidence:store.get("evidence"), subjects:store.get("subjects"), achievements:store.get("achievements")};
    const out=plan(P, cur.lines, record, {today:ctx.today(), label:cur.meta.label, authored_at:cur.meta.authored_at, kind:P.kind, tagsFor:ctx.tagsFor, tagList:t=>Object.keys(ctx.tagsFor(t))});
    ctx.writeAll({identity:out.identity, sources:out.sources, evidence:out.evidence, subjects:out.subjects, achievements:out.achievements});
    const s=out.summary, parts=[];
    if(s.roles_new) parts.push(`${s.roles_new} new role${s.roles_new>1?"s":""}`); if(s.roles_merged) parts.push(`${s.roles_merged} role${s.roles_merged>1?"s":""} matched to ones you had`);
    if(s.entries_new) parts.push(`${s.entries_new} new entr${s.entries_new>1?"ies":"y"}`); if(s.entries_corroborated) parts.push(`${s.entries_corroborated} entr${s.entries_corroborated>1?"ies":"y"} confirmed by a second source`);
    if(s.education||s.certifications) parts.push(`${s.education+s.certifications} education or certification item${s.education+s.certifications>1?"s":""}`); if(s.skills||s.tools) parts.push(`${s.skills} skills, ${s.tools} tools`);
    if(s.conflicts) parts.push(`${s.conflicts} conflict${s.conflicts>1?"s":""} to settle (marked on the role cards)`);
    const label=cur.meta.label; ctx.refreshEvidence(); discard(); $("#intakeFile").value=""; $("#intakeFileName").textContent=""; $("#intakeText").value="";
    status(`<b>Added to your record</b> from ${esc(label)}: ${parts.join(", ")||"nothing new"}. ${s.lines} lines kept as evidence.`);
    ctx.toast("Added to your record. Download a backup when you are done.");
  }
  function discard(){ cur=null; $("#intakeReview").hidden=true; $("#intakeReview").innerHTML=""; }
}
})(typeof globalThis!=="undefined"?globalThis:this);
