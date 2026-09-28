#!/usr/bin/env python3
"""One-time migration (2026-09-27): everything the repo already knows becomes claims with evidence.

  python tools/migrate_claims.py --dump <folder with jd_runs/ bullet_inbox/ feedback/>   [--write]

Reads curation/profile.json, learned.json, achievements.json, data/gate1_answers.json, sources/raw_extract.json and a
one-time dump of the Match Desk database (the answers behind the learned bullets). Writes:
  curation/evidence/answers.jsonl      Gate 1 and Gate 2 answers, sheet edits (verbatim, append-only)
  curation/evidence/statements.jsonl   dated chat decisions
  curation/claims.json                 subjects with facts, each fact with evidence, contradictions and resolutions
and adds evidence ids to learned.json items and metric resolutions to achievements.json.
Idempotent: re-running produces the same files. Without --write it only prints the review list.
"""
import argparse, glob, json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import claims as C   # noqa: E402

CUR = ROOT / "curation"
STAMP = "2026-09-27"
SESSION = "claude-code session 2f507c70 (2026-09-25 to 2026-09-27)"
FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MONTHS = "|".join(FULL + [m[:3] for m in FULL] + ["Spring", "Fall"])
RANGE_RE = re.compile(rf"(?:({MONTHS})\s+)?(\d{{4}})\s*[–-]\s*(?:(?:({MONTHS})\s+)?(\d{{4}})|(Present))", re.I)
MONTH_NUM = {m: i + 1 for i, m in enumerate(FULL)}
MONTH_NUM.update({m[:3]: i + 1 for i, m in enumerate(FULL)})
ROLE_MATCH = {
    "liminal": r"Liminal|Healthcare (AI|FinTech|Tech)|Chief (Strategy|of Strategy)|Strategy Consultant|Strategic Market Insights|Business Consultant|Princip(le|al) Business Strateg|(July|August) 2026 [–-] Present",
    "psp": r"Professional Sports Publications|PSP Sports|Ad(vertising)? Sales Director|March 2026 [–-]",
    "nyl": r"New York Life|Financial Services Professional|December 2025 – March 2026",
    "tek_lead": r"Specialized Lead|TEKsystems \| New York|January 2024 – December 2025|2024 – November 2025",
    "tek_recruiter": r"(Enterprise|National) Recruiter|TEKsystems \| Boston|January 2021 – December 2023|2021 – 2024",
    "demanddrive": r"demand ?Drive|Amazon Business|Inside Sales Rep|Sales Development Representative|January 2018 – December 2020|2018 – 2021",
    "yri": r"YRI",
    "massdot": r"EZ Pass|Department of Transportation",
}
EMPLOYER_KEY = {"liminal": "Strategic Market Insights", "psp": "Professional Sports Publications", "nyl": "New York Life",
                "tek_lead": "TEKsystems", "tek_recruiter": "TEKsystems", "demanddrive": "demandDrive", "yri": "YRI", "massdot": "Transportation"}
# answers behind learned items (from the Match Desk dump), mapped by hand once and reviewed
LEARNED_EVIDENCE = {
    "art-run-muhbu38f-0": ["ev:ans:run-muhbu38f:0", "ev:edit:run-muhbu38f:gate2-run-muhbu38f-0"],
    "art-run-muhbu38f-1": ["ev:ans:run-muhbu38f:1"],
    "art-run-muhbu38f-2": ["ev:ans:run-muhbu38f:3"],
    "art-run-muhfveal-0": ["ev:ans:run-muhfveal:0"],
    "art-run-muhfveal-1": ["ev:ans:run-muhfveal:1"],
    "art-run-muhfveal-2": ["ev:ans:run-muhfveal:3"],
    "art-run-muhghrt2-2": ["ev:ans:run-muhghrt2:2"],
    "art-run-muhghrt2-3": ["ev:ans:run-muhghrt2:3"],
}
LEARNED_BULLET_EVIDENCE = {   # learned.json bullets by achievement_id -> answer ids
    "lim-entity-ip-structure": ["ev:ans:run-muhbu38f:4", "ev:edit:run-muhbu38f:gate2-run-muhbu38f-3"],
    "lim-operating-cadence": ["ev:ans:run-muhfveal:4"],
    "tekl-southern-gas-discovery": ["ev:ans:run-muhghrt2:0"],
    "tekl-universal-poc": ["ev:ans:run-muhghrt2:1"],
    "tekl-fortune500-discovery": ["ev:ans:run-muhghrt2:4"],
}
STATEMENTS = [
    ("2026-09-25T16:20:00-04:00", "replace the role of Chief Strategy Consultant to Founder, Business Consultant, and GTM Engineer | Strategic Market Insights (with the knowledge the most relevant work has come from my work with the Healthcare start-up)", ["role:liminal"]),
    ("2026-09-27T18:05:00-04:00", "make this the new default template for resumes that are altered by this tool. if further questions or data stores would benefit from storing tag lines or relevant info for sections 1-4 integrate that into the tool", ["template"]),
    ("2026-09-27T18:40:00-04:00", "Summary paragraph: no paragraph; Claude tailors the Section A tagline and orders the Section B expertise line", ["template"]),
    ("2026-09-27T18:40:00-04:00", "PDF font: download Carlito (OFL) and embed it in the page's PDFs", ["template"]),
    ("2026-09-27T18:40:00-04:00", "Repeats: like the template. Short version under the consulting role, long version in Section C, never the identical sentence twice", ["template"]),
    ("2026-09-27T18:40:00-04:00", "HVAC: create an HVAC Section C engagement record and ask me for its details", ["eng:hvac"]),
    ("2026-09-27T20:35:00-04:00", "Git JSON stays the truth; SQLite derives it", ["architecture"]),
    ("2026-09-27T20:35:00-04:00", "Yes go with option 1 (a light application-outcome log) with one note: I would not initially design the system around agents learning from every resume iteration. Instead, distinguish four things: 1. Evidence: what actually happened. 2. Derived knowledge: what the system reasonably infers from the evidence. 3. Generation: what the model writes from that knowledge. 4. Feedback: what happened after generation.", ["architecture"]),
    ("2026-09-27T20:35:00-04:00", "Summary paragraph: optional, off by default", ["architecture"]),
    ("2026-09-27T20:35:00-04:00", "Scope: Phase 1, claims + evidence + projection", ["architecture"]),
    ("2026-09-27T20:50:00-04:00", "Conflicts: print the stronger value and warn; a disputed number never prints until resolved", ["architecture"]),
    ("2026-09-27T20:50:00-04:00", "Answer log: verbatim, in the private repo, never exported to the page", ["architecture"]),
    ("2026-09-27T20:50:00-04:00", "Trust: answers, sheet edits and engagement details are first-hand evidence at once; model output never is", ["architecture"]),
    ("2026-09-27T20:50:00-04:00", "Migration review: only disputed and low-confidence claims", ["architecture"]),
]


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jd(obj, p):
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_dump(folder, coll):
    out = {}
    for f in sorted(glob.glob(os.path.join(folder, coll, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        out[os.path.basename(f)[:-5]] = d.get("data", d)
    return out


def ymd(v):
    return str(v)[:10] if v else None


# ---------------------------------------------------------------- evidence logs
def build_answers(dump):
    rows = []
    g1 = jl(ROOT / "data/gate1_answers.json")
    for n, f in enumerate(g1["runs"][0]["followups"]):
        rows.append({"id": f"ev:ans:gate1:{n}", "source_type": "USER_ENTERED", "channel": "gate1", "source_ref": "gate1_baseline_2026-09-25",
                     "locator": f"followup {n}", "question": f["question"], "quote": f["answer"], "observed_at": "2026-09-25T14:02:00-04:00",
                     "section": "experience", "tags": [f["tag"]] if f.get("tag") else [], "engagement_key": None})
    runs = load_dump(dump, "jd_runs")
    for rid, r in sorted(runs.items()):
        for n, f in enumerate(r.get("followups") or []):
            if not (f.get("answer") or "").strip():
                continue
            rows.append({"id": f"ev:ans:{rid}:{n}", "source_type": "USER_ENTERED", "channel": "match_desk", "source_ref": rid,
                         "locator": f"followup {n}", "question": f.get("question"), "quote": f["answer"].strip(),
                         "observed_at": r.get("finalized") or r.get("created"), "section": f.get("section") or "experience",
                         "tags": [f["tag"]] if f.get("tag") else [], "role": f.get("role"), "engagement_key": f.get("engagement_key"),
                         "posting": {"company": r.get("company"), "title": r.get("title")}})
    fb = load_dump(dump, "feedback")
    for fid, f in sorted(fb.items(), key=lambda x: x[1].get("created", "")):
        if f.get("action") == "edit" and f.get("text"):
            rows.append({"id": f"ev:edit:{f.get('run_id')}:{f.get('achievement_id')}", "source_type": "USER_ENTERED", "channel": "match_desk",
                         "source_ref": f.get("run_id"), "locator": f"sheet edit of {f.get('achievement_id')}", "question": None,
                         "quote": f["text"].strip(), "observed_at": f.get("created"), "section": "experience", "tags": [], "engagement_key": None})
    return rows


def build_statements():
    rows, seen = [], {}
    for at, quote, about in STATEMENTS:
        day = at[:10]
        seen[day] = seen.get(day, 0) + 1
        rows.append({"id": f"ev:stmt:{day}:{seen[day]}", "source_type": "USER_ENTERED", "channel": "chat", "source_ref": SESSION,
                     "locator": "user message", "question": None, "quote": quote, "observed_at": at, "about": about})
    return rows


# ---------------------------------------------------------------- claims
def header_evidence(raw):
    """(source id, evidence id, line text, source type, authored_at, label, kind) for every role header line, all sources."""
    out = []
    for s in raw:
        for n, h in enumerate(s.get("role_headers") or []):
            out.append((s["id"], f"ev:{s['id']}:h{n}", h["text"], C.source_type_for(s), s.get("authored_at"), h.get("role"), s.get("kind")))
    return out


def belongs(key, text, label, kind):
    """A header line belongs to a role when the role's own words match it, or (LinkedIn only, whose labels are reliable)
    when it is the tenure line under that position."""
    if re.search(ROLE_MATCH[key], text, re.I):
        return True
    return kind == "linkedin_md" and label == key and bool(RANGE_RE.search(text))


def line_evidence(raw, key, code):
    out = []
    for s in raw:
        for n, l in enumerate(s.get(key) or []):
            out.append((s["id"], f"ev:{s['id']}:{code}{n}", l, C.source_type_for(s)))
    return out


def fact(value, evidence=(), text=None, **kw):
    if value == "":
        value = None
    f = {"value": value, "evidence": sorted(set(evidence))}
    if text:
        f["text"] = text
    f.update({k: v for k, v in kw.items() if v not in (None, [], {})})
    return f


def role_subjects(prof, learned, raw):
    heads = header_evidence(raw)
    overrides = learned.get("profile_overrides", {}).get("roles", {})
    subjects = []
    for r in prof["roles"]:
        r = {**r, **{k: v for k, v in overrides.get(r["key"], {}).items() if k != "date_note"}}
        key, sid = r["key"], f"role:{r['key']}"
        mine = [h for h in heads if belongs(key, h[2], h[5], h[6])]
        title_ev, emp_ev, loc_ev, ctx_ev, title_ref, emp_ref = [], [], [], [], [], []
        start_ev, end_ev, start_alt, end_alt = [], [], {}, {}
        # context lines sit under the role header without naming the role: match them anywhere
        if r.get("context_line"):
            ctx_ev = [h[1] for h in heads if C.norm(r["context_line"])[:40] in C.norm(h[2])]
        per_source = {}
        for sid_, eid, text, st, authored, label, kind in mine:
            n = C.norm(text)
            if C.norm(r["title"]) in n:
                title_ev.append(eid)
            elif not RANGE_RE.search(text) and ("|" in text or key == "liminal" and re.search(r"Chief|Founder|Princip", text) or kind == "linkedin_md"):
                title_ref.append(eid)
            if C.norm(EMPLOYER_KEY[key]) in n or (key == "demanddrive" and "demanddrive" in n):
                emp_ev.append(eid)
            elif key == "liminal" and re.search(r"Liminal|Healthcare (AI|Tech)", text):
                emp_ref.append(eid)
            if r.get("location") and C.norm(r["location"])[:8] in n:
                loc_ev.append(eid)
            for m in RANGE_RE.finditer(text):
                sm, sy, em, ey, present = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
                s_val = f"{sy}-{MONTH_NUM[sm.capitalize()]:02d}" if sm and sm.capitalize() in MONTH_NUM else sy
                e_val = "Present" if present else (f"{ey}-{MONTH_NUM[em.capitalize()]:02d}" if em and em.capitalize() in MONTH_NUM else ey)
                per_source.setdefault(sid_, []).append((s_val, e_val, eid, authored))
        # one source may split a role into positions (LinkedIn): its earliest start and latest end are what it states
        for sid_, ranges in per_source.items():
            s_val, _, s_eid, _ = min(ranges, key=lambda x: x[0])
            (start_ev if not C.values_conflict(s_val, r.get("start")) else start_alt.setdefault(s_val, [])).append(s_eid)
            ends = [x for x in ranges if x[1] != "Present"]
            if any(x[1] == "Present" for x in ranges):
                e_eid, authored = next((x[2], x[3]) for x in ranges if x[1] == "Present")
                if not (r.get("end") is None or (authored and authored[:7] <= str(r["end"])[:7])):
                    end_alt.setdefault("Present", []).append(e_eid)   # "Present" written after the role ended is a disagreement
            elif ends:
                _, e_val, e_eid, _ = max(ends, key=lambda x: x[1])
                (end_ev if not C.values_conflict(e_val, r.get("end")) else end_alt.setdefault(e_val, [])).append(e_eid)
        # Tim's statements and Gate 1 answers
        if key == "psp":
            end_ev.append("ev:ans:gate1:0")
        if key == "liminal":
            title_ev.append("ev:stmt:2026-09-27:1"); emp_ev.append("ev:stmt:2026-09-27:1")
        contra = lambda alts: [{"value": v, "evidence": sorted(set(ids))} for v, ids in alts.items()]
        note = r.get("date_note") or overrides.get(key, {}).get("date_note")
        resolution = {"why": note, "at": STAMP, "by": "template + notes"} if note else None
        facts = {
            "title": fact(r["title"], title_ev, refining=title_ref, text=f"Title: {r['title']}"),
            "employer": fact(r["employer"], emp_ev, refining=emp_ref, text=f"Employer: {r['employer']}"),
            "location": fact(r.get("location"), loc_ev, text=f"Location: {r.get('location')}"),
            "start": fact(r.get("start"), start_ev, contradicting=contra(start_alt), text=f"Started {r.get('start')}",
                          resolution=resolution if start_alt else None),
            "end": fact(r.get("end"), end_ev, contradicting=contra(end_alt), text=f"Ended {r.get('end') or '(current)'}",
                        resolution=resolution if end_alt else None),
            "context": fact(r.get("context_line"), ctx_ev, text=f"Context: {r.get('context_line')}"),
        }
        subjects.append({"id": sid, "kind": "role", "key": key, "label": f"{r['title']} | {r['employer']}", "order": r["order"],
                         "confidential": bool(r.get("confidential")), "employer_private": r.get("employer_private"),
                         "title_variants": r.get("title_variants", []), "hidden_by_default": bool(r.get("hidden_by_default")),
                         "engagement": r.get("engagement"), "section": r.get("section", "experience"), "date_note": note,
                         "facts": facts})
    # the superseded Founder title keeps its history
    subjects.append({"id": "role:liminal@2026-09-25", "kind": "role", "key": "liminal", "label": "Founder title (superseded)", "order": 1,
                     "history_only": True, "hidden_by_default": True, "section": "experience",
                     "facts": {"title": fact("Founder, Business Consultant, and GTM Engineer", ["ev:stmt:2026-09-25:1"], status="retired",
                                             valid_from="2026-09-25", valid_to="2026-09-27",
                                             relations=[{"rel": "supersedes", "to": "role:liminal:title", "note": "replaced by the source template title on 2026-09-27", "reverse": True}]),
                               "employer": fact("Strategic Market Insights", ["ev:stmt:2026-09-25:1"], status="retired", valid_from="2026-09-25", valid_to="2026-09-27")}})
    return subjects


def simple_subjects(prof, raw):
    subjects = []
    heads = header_evidence(raw)
    # education
    e = prof["education"][0]
    school_ev = [eid for _, eid, t, _, _, _, _ in heads if "maine" in C.norm(t)]
    degree_ev = [eid for _, eid, t, _, _, _, _ in heads if "finance" in C.norm(t) and "marketing" in C.norm(t)]
    date_ev = [eid for _, eid, t, _, _, _, _ in heads if "2018" in t and ("maine" in C.norm(t) or "spring" in C.norm(t) or "finance" in C.norm(t))]
    subjects.append({"id": "edu:umaine", "kind": "education", "label": e["school"], "location": e.get("location"), "year": e["year"],
                     "degree_variants": e.get("degree_variants", []), "bullet_ids": e.get("bullet_ids", []), "hidden_bullet_ids": e.get("hidden_bullet_ids", []),
                     "date_note": e.get("date_note"),
                     "facts": {"school": fact(e["school"], school_ev, text=e["school"]),
                               "degree": fact(e["degree"], degree_ev, text=e["degree"], refining=[eid for _, eid, t, _, _, _, _ in heads if "bba" in C.norm(t) or "bachelorofscience" in C.norm(t)]),
                               "date": fact(e.get("date_display") or e["year"], date_ev, text=f"Graduated {e.get('date_display') or e['year']}")}})
    # credentials
    certs = line_evidence(raw, "cert_lines", "r")
    for c in prof["certifications"]:
        keyw = re.sub(r" Certification$", "", c["name"])
        nk = C.norm(keyw)
        ev = []
        for cut in (len(nk), 20, 15, 12):          # the longest name prefix any source states
            ev = [eid for _, eid, t, _ in certs if nk[:cut] in C.norm(t)]
            if ev:
                break
        sid = f"cred:{C.slug(keyw)}"
        subjects.append({"id": sid, "kind": "credential", "label": c["name"], "credential_id": c.get("credential_id"), "source": c.get("source"),
                         "tags": c.get("tags", []), "sort": c.get("sort"), "hidden_by_default": bool(c.get("hidden_by_default")), "hidden_note": c.get("hidden_note"),
                         "facts": {"name": fact(c["name"], ev, text=c["name"]), "issuer": fact(c["issuer"], ev),
                                   "date": fact(c.get("date") if any("issued" in t.lower() for _, eid, t, _ in certs if eid in ev) else None,
                                                [eid for _, eid, t, _ in certs if eid in ev and "issued" in t.lower()]),
                                   "status": fact(c.get("status"), [eid for _, eid, t, _ in certs if eid in ev and "progress" in t.lower()])}})
    # technologies
    lines = line_evidence(raw, "systems_lines", "s") + line_evidence(raw, "skills_lines", "k")
    for t in prof["technologies"]:
        base = re.split(r"[(&/]", t["name"])[0].strip()
        keys = [base] + (["Claude"] if "Claude" in t["name"] else []) + (["VS Code", "Visual Studio"] if "Visual Studio" in t["name"] else [])
        ev = sorted({eid for _, eid, l, _ in lines if any(C.norm(k) and C.norm(k) in C.norm(l) for k in keys)})
        subjects.append({"id": f"tool:{C.slug(base)}", "kind": "tool", "label": t["name"], "category": t.get("category"), "tags": t.get("tags", []),
                         "sort": t.get("sort"), "origin": t.get("origin", "curated"), "facts": {"name": fact(t["name"], ev, text=f"Uses {t['name']}")}})
    # tagline phrases (A): template line + LinkedIn headline
    tl = line_evidence(raw, "tagline_lines", "t") + [(s["id"], f"ev:{s['id']}:d0", s["headline"], C.source_type_for(s)) for s in raw if s.get("headline")]
    for p in prof.get("tagline_phrases", []):
        ev = [eid for _, eid, l, _ in tl if C.norm(p["text"])[:24] in C.norm(l)]
        subjects.append({"id": f"tagline:{C.slug(p['text'])}", "kind": "tagline", "label": p["text"], "tags": p.get("tags", []), "sort": p.get("sort"),
                         "origin": p.get("origin", "template"), "facts": {"text": fact(p["text"], ev, text=p["text"])}})
    # expertise items (B)
    comp = line_evidence(raw, "competency_lines", "c") + line_evidence(raw, "skills_lines", "k")
    for c in prof["competencies"]:
        ev = [eid for _, eid, l, _ in comp if C.norm(c["text"]) in C.norm(l)]
        subjects.append({"id": f"expertise:{C.slug(c['text'])}", "kind": "expertise", "label": c["text"], "tags": c.get("tags", []), "sort": c.get("sort"),
                         "origin": c.get("origin", "curated"), "facts": {"text": fact(c["text"], ev, text=c["text"])}})
    # core competency items (D)
    skills = line_evidence(raw, "skills_lines", "k")
    for ai, area in enumerate(prof.get("core_competencies", [])):
        for ii, it in enumerate(area["items"]):
            ev = [eid for _, eid, l, _ in skills if C.norm(it["text"]) in C.norm(l)]
            subjects.append({"id": f"core:{C.slug(area['label'])}:{C.slug(it['text'])}", "kind": "core_item", "label": it["text"], "area": area["label"],
                             "area_sort": ai, "sort": ii, "tags": it.get("tags", []), "facts": {"text": fact(it["text"], ev, text=it["text"])}})
    # engagements (C)
    for ei, e in enumerate(prof.get("engagements", [])):
        sid = f"eng:{e['key']}"
        if e["key"] == "healthcare":
            hev = [eid for _, eid, t, _, _, _, _ in heads if "healthcaretechnologystartup" in C.norm(t)]
            sub = [eid for _, eid, t, _, _, _, _ in heads if "principalbusinessstrategist" in C.norm(t)]
            facts = {"client": fact(e["client"], hev, text=e["client"]), "location": fact(e.get("location"), hev), "start": fact(e.get("start"), hev),
                     "end": fact(e.get("end"), hev), "commitment": fact(e.get("commitment"), hev), "subtitle": fact(e.get("subtitle"), sub)}
        else:
            facts = {"client": fact(e["client"], ["ev:ans:run-muhfveal:0", "ev:stmt:2026-09-27:6"], text=e["client"]), "location": fact(None), "start": fact(None),
                     "end": fact(None), "commitment": fact(None), "subtitle": fact(None)}
        subjects.append({"id": sid, "kind": "engagement", "key": e["key"], "label": e["client"], "role": e.get("role", "liminal"), "sort": ei,
                         "confidential": bool(e.get("confidential", True)), "needs_details": bool(e.get("needs_details")), "ask": e.get("ask"),
                         "notes": e.get("notes"), "achievements": e.get("achievements", []), "facts": facts})
    # identity links
    contact = line_evidence(raw, "contact_lines", "x")
    for ln in prof["identity"].get("links", []):
        ev = [eid for _, eid, l, _ in contact if ln["label"].split()[0].lower() in l.lower()]
        subjects.append({"id": f"contact:{C.slug(ln['label'])}", "kind": "contact", "label": ln["label"], "sort": len(subjects),
                         "facts": {"url": fact(ln["url"], ev, text=f"{ln['label']}: {ln['url']}")}})
    return subjects


def ground(subjects, achievements):
    """Tagline, expertise and core items point at the achievements that back them (tag overlap), so a phrase with no
    document line behind it is still traceable, and the tailor step can cite them."""
    for s in subjects:
        if s["kind"] not in ("tagline", "expertise", "core_item") or not s.get("tags"):
            continue
        scored = []
        for a in achievements:
            if a.get("retired") or a["role"] == "education":
                continue
            w = sum(a.get("tags", {}).get(t, 0) for t in s["tags"] if a.get("tags", {}).get(t, 0) >= 0.5)
            if w > 0:
                scored.append((w, a["id"]))
        scored.sort(reverse=True)
        s["relations"] = [{"rel": "grounded_in", "to": f"ach:{aid}", "confidence": 0.6, "note": "tag overlap"} for _, aid in scored[:5]]


def review(subjects, evidence_ids, cfg):
    """Provisional confidence per fact, plus the list Tim reviews: disputed, resolved conflicts, and < 0.7."""
    rows = []
    for s in subjects:
        for name, f in s["facts"].items():
            if f.get("value") is None:
                continue
            ev = [e for e in f["evidence"] if e in evidence_ids]
            missing = [e for e in f["evidence"] if e not in evidence_ids]
            sup = [{"source_type": evidence_ids[e]["source_type"], "strength": evidence_ids[e]["strength"]} for e in ev]
            contra = [c for c in f.get("contradicting") or []]
            conf, basis, status = C.confidence_for(sup, contra, bool(f.get("resolution")), cfg)
            rows.append((s["id"], name, f["value"], conf, status, basis, contra, f.get("resolution"), missing, len(ev)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    cfg = C.load_config()
    prof, learned, ach = jl(CUR / "profile.json"), jl(CUR / "learned.json"), jl(CUR / "achievements.json")
    raw = jl(ROOT / "sources/raw_extract.json")
    answers, statements = build_answers(a.dump), build_statements()
    logged = {r["id"]: {**r, "strength": cfg["strengths"]["USER_ENTERED"], "source_type": "USER_ENTERED"} for r in answers + statements}
    src_ev = {r["id"]: r for r in C.source_evidence(raw, cfg)}
    evidence_ids = {**src_ev, **logged}
    subjects = role_subjects(prof, learned, raw) + simple_subjects(prof, raw)
    ground(subjects, ach["achievements"] + learned.get("achievements", []))
    rows = review(subjects, evidence_ids, cfg)
    print(f"evidence: {len(src_ev)} document lines + {len(answers)} answers/edits + {len(statements)} statements")
    print(f"subjects: {len(subjects)}  facts with values: {len(rows)}")
    by_kind = {}
    for s in subjects:
        by_kind[s["kind"]] = by_kind.get(s["kind"], 0) + 1
    print("  by kind:", by_kind)
    print("\nREVIEW LIST (disputed, resolved conflicts, confidence < 0.7, missing evidence ids)")
    for sid, name, val, conf, status, basis, contra, res, missing, n_ev in rows:
        flag = "DISPUTED" if status == "disputed" else ("resolved" if contra else ("low" if conf < 0.7 else None))
        if not flag and not missing:
            continue
        print(f"  [{flag or 'ok'}] {sid}.{name} = {val!r}  conf={conf} ({basis})")
        for c in contra:
            print(f"        vs {c['value']!r} from {', '.join(c['evidence'][:6])}{' …' if len(c['evidence']) > 6 else ''}")
        if res:
            print(f"        resolution: {res.get('why')}")
        if missing:
            print(f"        MISSING evidence ids: {missing}")
    grounded = {s["id"] for s in subjects if s.get("relations")}
    no_ev = [(sid, name) for sid, name, val, conf, status, basis, contra, res, missing, n_ev in rows if n_ev == 0 and sid not in grounded]
    print(f"\nfacts with no evidence and no grounding: {len(no_ev)}")
    for sid, name in no_ev[:60]:
        print("   ", sid, name)
    if not a.write:
        print("\n(dry run; add --write to write curation/evidence/*.jsonl, curation/claims.json and update learned.json/achievements.json)")
        return
    # ---- write
    n1 = C.append_jsonl(C.EVID / "answers.jsonl", answers)
    n2 = C.append_jsonl(C.EVID / "statements.jsonl", statements)
    claims_json = {"_about": ("Tier 2 truth for every fact that is not an achievement: subjects (roles, education, credentials, tools, Section A tagline "
                              "phrases, Section B expertise items, Section D core items, Section C engagements, contact links) with facts. Each fact has a "
                              "value, evidence ids (tier 1), contradicting values with their evidence, and a resolution when Tim settled a conflict. "
                              "Achievements and metrics are implied by achievements.json. Ingest flattens this into resume.db claims and computes confidence "
                              "with curation/confidence.json. Edit values here; never edit evidence quotes."),
                   "schema": "rot-claims/1", "migrated": STAMP, "subjects": subjects}
    jd(claims_json, CUR / "claims.json")
    # learned items and metric resolutions gain their evidence
    po = learned.setdefault("profile_overrides", {})
    if po.get("roles"):
        po.setdefault("_history", []).append({"superseded": STAMP, "roles": po.pop("roles"), "why": "role facts now live in curation/claims.json with their evidence"})
    for la in learned.get("achievements", []):
        if la["id"] in LEARNED_EVIDENCE:
            la["evidence"] = LEARNED_EVIDENCE[la["id"]]
    for b in learned.get("bullets", []):
        if b["achievement_id"] in LEARNED_BULLET_EVIDENCE:
            b["evidence"] = LEARNED_BULLET_EVIDENCE[b["achievement_id"]]
    jd(learned, CUR / "learned.json")
    for x in ach["achievements"]:
        if x["id"] == "psp-closed-deals":
            x["resolutions"] = {"signed-deals": {"value": 5, "why": "Gate 1 answer 2026-09-25: ended Aug 2026 with 5 signed deals", "at": "2026-09-25", "evidence": ["ev:ans:gate1:0"]}}
            x["contradict_patterns"] = {"signed-deals": [r"^Closed (3|three) signed"]}
        if x["id"] == "psp-pipeline-discovery":
            for m in x.get("metrics", []):
                if m["label"] == "active pipeline":
                    m["evidence"] = ["ev:ans:gate1:2"]; m["as_of"] = "2026-08"
        if x["id"] == "tekl-coaching":
            if not any(m["label"] == "direct reports" for m in x.get("metrics", [])):
                x.setdefault("metrics", []).append({"label": "direct reports", "value": 5, "unit": "reports (3–5)", "evidence": ["ev:ans:gate1:1"]})
            x["evidence"] = ["ev:ans:gate1:1"]
        if x["id"] in ("lim-build-vs-buy", "lim-staffing-restructure", "lim-data-rights"):
            x["evidence"] = ["ev:ans:gate1:3"]
    from pathlib import Path as _P
    txt = json.dumps(ach, ensure_ascii=False)  # keep the compact one-entry-per-block style via fmt below
    (CUR / "achievements.json").write_text(_compact(ach), encoding="utf-8")
    print(f"\nwrote claims.json ({len(subjects)} subjects), answers.jsonl (+{n1}), statements.jsonl (+{n2}), learned.json, achievements.json")


def _compact(A):
    d = lambda v: json.dumps(v, ensure_ascii=False)
    items = []
    for a in A["achievements"]:
        parts = []
        for k, v in a.items():
            if k == "variants" and v:
                inner = ",\n".join(f"        {d(kk)}: {d(vv)}" for kk, vv in v.items())
                parts.append(f'      "variants": {{\n{inner}\n      }}')
            else:
                parts.append(f"      {d(k)}: {d(v)}")
        items.append("    {\n" + ",\n".join(parts) + "\n    }")
    return "{\n" + f'  "_about": {d(A["_about"])},\n  "achievements": [\n' + ",\n".join(items) + "\n  ]\n}\n"


if __name__ == "__main__":
    main()
