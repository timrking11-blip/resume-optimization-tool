"use strict";
/* Career Companion Hub · storage and the feature registry.
   Everything a person enters stays in this browser (localStorage, one versioned envelope per key) until they download a backup.
   A backup is a cch-backup/1 document: the same shapes the core's projectLibrary() reads. Nothing here talks to a server. */
(function(root){
const PREFIX="cch.v1:", KEYS=["identity","sources","evidence","subjects","achievements","taxonomy","settings","sessions","feedback","outcomes","review_log","workspace","meta"];
const EMPTY={identity:{name:"",location:"",phone:"",email:"",links:[]}, sources:[], evidence:[], subjects:[], achievements:[], taxonomy:{id:"gtm/1", user_tags:{}}, settings:{},
  sessions:{}, feedback:[], outcomes:[], review_log:[], workspace:{current:null, saved_at:null}, meta:{created_at:null, last_backup_at:null, entries:0}};
const clone=o=>JSON.parse(JSON.stringify(o));

class BrowserStore{
  constructor(coreVersion){ this.core=coreVersion||"0"; this.mem=new Map(); this.available=true; this.listeners=[];
    try{ const k=PREFIX+"__probe"; localStorage.setItem(k,"1"); localStorage.removeItem(k); }catch{ this.available=false; } }
  _read(key){ if(!this.available) return this.mem.has(key)?clone(this.mem.get(key)):undefined;
    try{ const t=localStorage.getItem(PREFIX+key); if(t==null) return undefined; const env=JSON.parse(t); return env&&env.v===1?env.data:env; }catch{ return undefined; } }
  _write(key, data){ const env={v:1, at:new Date().toISOString(), core:this.core, data};
    if(!this.available){ this.mem.set(key, clone(data)); return true; }
    try{ localStorage.setItem(PREFIX+key, JSON.stringify(env)); return true; }
    catch(e){ this.lastError=e; return false; } }
  get(key){ const v=this._read(key); return v===undefined ? clone(EMPTY[key]) : v; }
  set(key, data, silent){ const ok=this._write(key, data); if(!silent) this.emit(key); return ok; }
  update(key, fn){ const v=this.get(key); const r=fn(v); return this.set(key, r===undefined?v:r); }
  del(key){ if(this.available){ try{ localStorage.removeItem(PREFIX+key); }catch{} } this.mem.delete(key); this.emit(key); }
  on(fn){ this.listeners.push(fn); return ()=>{ this.listeners=this.listeners.filter(f=>f!==fn); }; }
  emit(key){ for(const f of this.listeners){ try{ f(key); }catch(e){ console.warn("store listener", e); } } }
  /* bytes this store uses (UTF-16 as the browser counts it) */
  usage(){ let n=0; if(!this.available){ for(const v of this.mem.values()) n+=JSON.stringify(v).length*2; return n; }
    try{ for(let i=0;i<localStorage.length;i++){ const k=localStorage.key(i); if(k&&k.startsWith(PREFIX)) n+=(k.length+(localStorage.getItem(k)||"").length)*2; } }catch{} return n; }
  /* the whole record as one document */
  snapshot(){
    const s={}; for(const k of KEYS) s[k]=this.get(k);
    return {schema:"cch-backup/1", core:this.core, exported_at:new Date().toISOString(), edition:"hub",
      identity:s.identity, sources:s.sources, evidence:s.evidence, subjects:s.subjects, achievements:s.achievements, taxonomy:s.taxonomy, settings:s.settings,
      sessions:Object.values(s.sessions||{}), feedback:s.feedback, outcomes:s.outcomes, review_log:s.review_log, meta:s.meta};
  }
  /* load a backup made by this page (or by the fixture builder); replaces what is here */
  importBackup(b){
    if(!b || b.schema!=="cch-backup/1") throw new Error("Not a Career Companion Hub backup (expected schema cch-backup/1).");
    const sessions={}; for(const x of (Array.isArray(b.sessions)?b.sessions:Object.values(b.sessions||{}))) if(x&&x.runId) sessions[x.runId]=x;
    for(const [k,v] of Object.entries({identity:{...EMPTY.identity, ...(b.identity||{})}, sources:b.sources||[], evidence:b.evidence||[], subjects:b.subjects||[], achievements:b.achievements||[],
      taxonomy:{...EMPTY.taxonomy, ...(b.taxonomy||{})}, settings:b.settings||{}, sessions, feedback:b.feedback||[], outcomes:b.outcomes||[], review_log:b.review_log||[],
      workspace:{current:null, saved_at:null}, meta:{...EMPTY.meta, ...(b.meta||{}), imported_at:new Date().toISOString()}})) this.set(k, v, true);
    this.emit("*");
  }
  wipe(){ for(const k of KEYS) this.del(k); this.emit("*"); }
  isEmpty(){ return !this.get("subjects").length && !this.get("achievements").length && !(this.get("identity").name||"").trim(); }
}

/* Features register themselves; the shell builds the navigation and shows one at a time. A feature that needs a capability
   the viewer's page cannot run stays listed with the reason, never silently missing. */
const Hub={
  features:[], ctx:null, active:null, _on:{},
  register(def){ this.features.push(def); this.features.sort((a,b)=>(a.order??99)-(b.order??99)); },
  on(ev, fn){ (this._on[ev]=this._on[ev]||[]).push(fn); }, emit(ev, data){ for(const f of this._on[ev]||[]) { try{ f(data); }catch(e){ console.warn(ev, e); } } },
  mount(ctx){
    this.ctx=ctx; const nav=document.querySelector("#nav"), views=document.querySelector("#views");
    nav.innerHTML=this.features.map(f=>`<button class="tab" data-view="${f.id}" role="tab" aria-selected="false">${f.label}</button>`).join("");
    for(const f of this.features){ let el=views.querySelector(`[data-view="${f.id}"]`); if(!el){ el=document.createElement("section"); el.dataset.view=f.id; views.appendChild(el); } el.hidden=true; f.el=el; try{ f.mount(ctx, el); }catch(e){ console.error("mount "+f.id, e); el.innerHTML=`<p class="err">This part of the page failed to load (${String(e.message||e)}).</p>`; } }
    nav.addEventListener("click", e=>{ const b=e.target.closest("button[data-view]"); if(b) this.show(b.dataset.view); });
    const want=(location.hash||"").replace(/^#/,""); this.show(this.features.some(f=>f.id===want)?want:(ctx.store.isEmpty()?"evidence":"match"));
  },
  show(id){
    for(const f of this.features){ const on=f.id===id; f.el.hidden=!on; if(on && f.refresh) { try{ f.refresh(this.ctx); }catch(e){ console.error("refresh "+id, e); } } }
    document.querySelectorAll("#nav .tab").forEach(b=>{ const on=b.dataset.view===id; b.classList.toggle("on", on); b.setAttribute("aria-selected", on?"true":"false"); });
    this.active=id; try{ history.replaceState(null, "", "#"+id); }catch{}
    this.emit("view", id);
  },
  refresh(id){ const f=this.features.find(f=>f.id===(id||this.active)); if(f&&f.refresh) f.refresh(this.ctx); },
};
root.CCH={BrowserStore, Hub, EMPTY, KEYS, clone};
})(typeof globalThis!=="undefined"?globalThis:this);
