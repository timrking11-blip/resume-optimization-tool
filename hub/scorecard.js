"use strict";
/* Career Companion Hub · scorecard: reads the match without changing it. Where the match can grow, what one requirement is worth,
   which tools an answer names that the Tools line lacks, and what each answered question did to the match. Pure; tested in Node. */
(function(root){
const R = root.RotCore || (typeof require==="function" ? require("../core/rot_core.js") : null);
const {norm, escRe, TOOL_LEXICON} = R.util;
const total = req => Object.values(req||{}).reduce((a,r)=>a+r.weight,0) || 1;
/* the requirements not yet proven, ranked by what proving each would add to the match */
function growth(req, cov, tags, limit){
  const tot=total(req);
  return Object.entries(req||{}).map(([t,r])=>{ const c=Math.min((cov||{})[t]||0,1);
      return {tag:t, label:(tags&&tags[t]&&tags[t].label)||t, weight:r.weight, coverage:c, words:(r.phrases||[]).slice(0,4), gain:r.weight*(1-c)/tot}; })
    .filter(g=>g.gain>0.0005).sort((a,b)=>b.gain-a.gain||a.tag.localeCompare(b.tag)).slice(0, limit||8);
}
/* what proving one requirement would add right now */
function potential(req, cov, tag){ if(!tag||!req||!req[tag]) return 0; return req[tag].weight*(1-Math.min((cov||{})[tag]||0,1))/total(req); }
const headroom = (req, cov) => Object.keys(req||{}).reduce((a,t)=>a+potential(req, cov, t), 0);
/* tools a text names (proper nouns from the lexicon) that the given Tools line lacks */
function toolsNamed(text, knownNames){
  const known=new Set((knownNames||[]).map(n=>norm(String(n).replace(/\.io$/,"")))), out=[];
  for(const t of TOOL_LEXICON){ if(new RegExp("(?<![A-Za-z0-9])"+escRe(t)+"(?![A-Za-z0-9])").test(text||"") && !known.has(norm(t.replace(/\.io$/,"")))) out.push(t); }
  return out.slice(0,6);
}
/* What each answered question did, in question order: the match with that question's entries added on top of the earlier
   ones, minus the match without them. Enrichments of existing entries add wording, not coverage, and show as such. */
function contributions(E, d){
  const fresh=d.newAch||[], byQ=new Map();
  for(const x of fresh){ const k=x.q_ix==null?-1:x.q_ix; if(!byQ.has(k)) byQ.set(k,[]); byQ.get(k).push(x); }
  const freshIds=new Set(fresh.map(x=>x.ach?x.ach.id:x.attach));
  const scoreWith=qs=>{ const keep=fresh.filter(x=>qs.has(x.q_ix==null?-1:x.q_ix)), keepIds=new Set(keep.map(x=>x.ach?x.ach.id:x.attach));
    const pinned=new Set([...d.pinned].filter(id=>!freshIds.has(id)||keepIds.has(id)));
    return E.compute({...d, newAch:keep, pinned, locked:null}, d.req).score||0; };
  const order=[...byQ.keys()].sort((a,b)=>a-b), seen=new Set(); let prev=scoreWith(seen); const out={before:prev, byQuestion:{}};
  for(const ix of order){ seen.add(ix); const now=scoreWith(seen); const xs=byQ.get(ix);
    out.byQuestion[ix]={delta:now-prev, entries:xs.filter(x=>x.ach).length, enriched:xs.filter(x=>x.attach).length}; prev=now; }
  out.after=prev; return out;
}
const pct = x => (Math.round(x*1000)/10).toFixed(1);
const EXPLAIN = "The posting is read for the skills it asks for; each gets a weight from how strongly the posting stresses it. The match is the share of that weight already proven by the entries printed under your roles. A skill counts once: the first entry that proves it earns the full weight, and a second entry for the same skill changes nothing. The Skills and Tools lines don't count. An answer moves the match only when it becomes a printed entry that proves a skill no entry proved yet.";
const Scorecard={growth, potential, headroom, toolsNamed, contributions, pct, EXPLAIN};
if(root.CCH) root.CCH.Scorecard=Scorecard; else root.CCH={Scorecard};
if(typeof module!=="undefined" && module.exports) module.exports=Scorecard;
})(typeof globalThis!=="undefined"?globalThis:this);
