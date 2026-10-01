#!/usr/bin/env python3
"""Evidence layer for the Resume Optimization Tool: tiers 1 and 2.

Tier 1, evidence: what actually happened. Verbatim lines from Tim's documents (derived from sources/raw_extract.json)
and his own words (curation/evidence/answers.jsonl, statements.jsonl). Immutable and append-only.
Tier 2, derived knowledge: claims (one fact each) with evidence, confidence, validity dates and relations, kept in
curation/claims.json as subjects with facts, plus the achievements and metrics implied by curation/achievements.json.

Everything here is deterministic. The model never assigns confidence; it can only propose a claim, which enters as
MODEL_INFERENCE evidence and stays below the print threshold until Tim confirms it.
"""
import datetime as dt, hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CUR = ROOT / "curation"
EVID = CUR / "evidence"

SOURCE_TYPES = ["USER_ENTERED", "INTERVIEW_RESPONSE", "MASTER_RESUME", "HISTORICAL_RESUME", "PUBLIC_PROFILE",
                "EXTERNAL_RESEARCH", "MODEL_INFERENCE"]
RELATIONS = ["supports", "contradicts", "refines", "part_of", "same_as", "supersedes", "grounded_in", "used_in",
             "tagged", "derived_from", "about", "maps_to"]
FEEDBACK_EVENTS = ["bullet_accepted", "bullet_rejected", "bullet_swapped", "bullet_edited", "evidence_added",
                   "phrase_added", "terminology_corrected"]
RESPONSES = ["pending", "no_response", "screen", "interview", "offer", "rejected"]
ACTION_EVENT = {"keep": "bullet_accepted", "drop": "bullet_rejected", "reject": "bullet_rejected",
                "swap": "bullet_swapped", "edit": "bullet_edited"}
TIER_LABELS = {1: "Evidence: what actually happened", 2: "Derived knowledge: what the system infers",
               3: "Generation: what was written", 4: "Feedback: what happened afterwards"}
# subject kind -> the facts it carries (in print order); the first fact is the one a list shows
FACTS = {
    "role": ["title", "employer", "location", "start", "end", "context"],
    "education": ["school", "degree", "date"],
    "credential": ["name", "issuer", "date", "status"],
    "tool": ["name"],
    "tagline": ["text"],
    "expertise": ["text"],
    "core_item": ["text"],
    "engagement": ["client", "location", "start", "end", "commitment", "subtitle"],
    "contact": ["url"],
}
KIND_OF = {"role": "role_fact", "education": "education", "credential": "credential", "tool": "tool", "tagline": "tagline",
           "expertise": "expertise", "core_item": "core_item", "engagement": "engagement_fact", "contact": "contact"}
# kinds whose subjects legitimately hold several values per predicate (no sibling-conflict check)
MULTI_VALUE_KINDS = {"achievement", "metric", "tool", "tagline", "expertise", "core_item", "contact"}
# line kinds captured per source by extract.py -> evidence id code
LINE_KINDS = [("bullets", "b"), ("role_headers", "h"), ("competency_lines", "c"), ("systems_lines", "s"),
              ("skills_lines", "k"), ("cert_lines", "r"), ("tagline_lines", "t"), ("summary", "p"),
              ("contact_lines", "x"), ("headline", "d")]
FIRST_PERSON = re.compile(r"\b(I(?!\.[A-Z])|I'm|I've|I'd|me|my|mine|we|our|us)\b")   # "I.T." is not first person


def sha1(t):
    return hashlib.sha1(str(t).encode("utf-8")).hexdigest()


def norm(t):
    return re.sub(r"[^a-z0-9]", "", str(t or "").lower())


def slug(t):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(t or "").lower())).strip("-")[:48]


def now_iso():
    return dt.datetime.now().isoformat(timespec="seconds")


def load_config():
    return json.loads((CUR / "confidence.json").read_text(encoding="utf-8"))


def load_claims_json():
    p = CUR / "claims.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"subjects": []}


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_jsonl(path, rows):
    """Append rows whose id is new. Never rewrites existing lines (the log is append-only)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = read_jsonl(path)
    have = {r["id"] for r in old}
    # the same words from the same place are one row, even if the id scheme for them changed
    said = {(r.get("source_ref"), r.get("locator"), sha1(r["quote"])) for r in old if r.get("quote")}
    new = []
    for r in rows:
        k = (r.get("source_ref"), r.get("locator"), sha1(r["quote"])) if r.get("quote") else None
        if r["id"] in have or (k and k in said):
            continue
        have.add(r["id"])
        if k:
            said.add(k)
        new.append(r)
    if new:
        with open(path, "a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(new)


# ---------------------------------------------------------------- tier 1: evidence
def source_type_for(source):
    kind = source.get("kind")
    if kind == "docx_template":
        return "MASTER_RESUME"
    if kind == "linkedin_md":
        return "PUBLIC_PROFILE"
    return "HISTORICAL_RESUME"


def source_evidence(raw, cfg):
    """One evidence row per verbatim line extract.py captured from each source."""
    rows = []
    for s in raw:
        st = source_type_for(s)
        strength = cfg["strengths"][st]
        authored = s.get("authored_at")
        observed = s.get("captured_at") or authored
        for key, code in LINE_KINDS:
            items = [s["headline"]] if key == "headline" and s.get("headline") else (s.get(key) or [])
            for n, it in enumerate(items):
                text = it["text"] if isinstance(it, dict) else it
                if not text:
                    continue
                role = it.get("role") if isinstance(it, dict) else None
                rows.append({"id": f"ev:{s['id']}:{code}{n}", "source_type": st,
                             "channel": "linkedin" if st == "PUBLIC_PROFILE" else "resume", "source_ref": s["id"],
                             "locator": f"{key}[{n}]" + (f" role={role}" if role else ""), "question": None, "quote": text,
                             "authored_at": authored, "observed_at": observed, "strength": strength, "hash": sha1(text)})
    return rows


def logged_evidence(cfg):
    """Tim's own words: Gate answers, sheet edits, engagement details, chat statements (append-only logs)."""
    rows, seen = [], {}
    for name in ("answers.jsonl", "statements.jsonl"):
        for r in read_jsonl(EVID / name):
            r = dict(r)
            r.setdefault("source_type", "USER_ENTERED")
            r["strength"] = cfg["strengths"].get(r["source_type"], 0.5)
            r["hash"] = sha1(r["quote"])
            # the logs stay verbatim; a legacy id reused for a different quote (sheet edits of an unbanked bullet) is told apart on read
            if r["id"] in seen and seen[r["id"]] != r["hash"]:
                r["id"] = f"{r['id']}:h{r['hash'][:10]}"
            elif r["id"] in seen:
                continue
            seen[r["id"]] = r["hash"]
            rows.append(r)
    return rows


# ---------------------------------------------------------------- tier 2: claims
def _fact_claim(subj, fact, f):
    """A subject's fact -> one claim dict. f may be a bare value or {"value", "text", "evidence", "contradicting", ...}."""
    if not isinstance(f, dict):
        f = {"value": f}
    val = f.get("value")
    num = None
    if val not in (None, "") and re.fullmatch(r"-?[\d,]+(\.\d+)?", str(val)):
        try:
            num = float(str(val).replace(",", ""))
        except ValueError:
            num = None
    primary = fact == FACTS[subj["kind"]][0]
    rels = list(f.get("relations") or []) + (list(subj.get("relations") or []) if primary else [])
    return {"id": f"{subj['id']}:{fact}", "kind": KIND_OF[subj["kind"]], "subject": subj["id"], "predicate": fact,
            "value": None if val is None else str(val), "value_num": num, "unit": f.get("unit"),
            "text": f.get("text") or (f"{subj.get('label') or subj['id']}: {fact} = {val}" if val is not None else None),
            "valid_from": f.get("valid_from", subj.get("valid_from")), "valid_to": f.get("valid_to", subj.get("valid_to")),
            "as_of": f.get("as_of"), "status": f.get("status", "active"), "origin": f.get("origin", subj.get("origin", "curated")),
            "area": subj.get("area"), "sort": subj.get("sort"),
            "evidence": list(f.get("evidence") or []), "contradicting": list(f.get("contradicting") or []),
            "refining": list(f.get("refining") or []), "resolution": f.get("resolution"),
            "relations": rels, "confidence_override": f.get("confidence_override")}


def subject_claims(claims_json):
    """Flatten curation/claims.json (subjects with facts) into claim dicts."""
    out = []
    for subj in claims_json.get("subjects", []):
        for fact, f in (subj.get("facts") or {}).items():
            c = _fact_claim(subj, fact, f)
            if c["value"] is None:
                continue
            out.append(c)
    return out


def implied_claims(achievements, roles_by_key):
    """Achievements and their metrics are claims too, implied by achievements.json (never duplicated in claims.json)."""
    out = []
    for a in achievements:
        role = a["role"]
        r = roles_by_key.get(role, {})
        aid = f"ach:{a['id']}"
        out.append({"id": aid, "kind": "achievement", "subject": f"role:{role}", "predicate": "accomplished",
                    "value": None, "value_num": None, "unit": None, "text": a["canonical"],
                    "valid_from": a.get("valid_from", r.get("start")), "valid_to": a.get("valid_to", r.get("end")), "as_of": None,
                    "status": "retired" if a.get("retired") else "active", "origin": a.get("origin", "curated"), "area": None, "sort": None,
                    "evidence": list(a.get("evidence") or []), "contradicting": [], "refining": [], "resolution": None,
                    "relations": [{"rel": "part_of", "to": f"role:{role}"}] + ([{"rel": "part_of", "to": f"eng:{a['engagement']}"}] if a.get("engagement") else []),
                    "confidence_override": None, "legacy_confidence": a.get("confidence"), "achievement": a["id"]})
        for m in a.get("metrics", []):
            key = slug(m["label"])
            res = (a.get("resolutions") or {}).get(key)
            out.append({"id": f"metric:{a['id']}:{key}", "kind": "metric", "subject": aid, "predicate": key,
                        "value": str(m["value"]), "value_num": float(m["value"]) if isinstance(m["value"], (int, float)) else None,
                        "unit": m.get("unit"), "text": f"{m['label']}: {m['value']}" + (f" {m['unit']}" if m.get("unit") else ""),
                        "valid_from": None, "valid_to": None, "as_of": m.get("as_of"), "status": "active",
                        "origin": a.get("origin", "curated"), "area": None, "sort": None,
                        "evidence": list(m.get("evidence") or []) + (list(res.get("evidence") or []) if res else []),
                        "contradicting": [], "refining": [], "resolution": res,
                        # a derived figure (computed from stated ones) is grounded in its achievement, never treated as stated
                        "relations": [{"rel": "part_of", "to": aid}] + ([{"rel": "grounded_in", "to": aid, "confidence": 0.8,
                                                                          "note": m.get("derived_from") or "derived from stated figures"}] if m.get("derived") else []),
                        "confidence_override": None,
                        "contradict_patterns": (a.get("contradict_patterns") or {}).get(key) or [], "achievement": a["id"]})
    return out


def learned_section_claims(learned):
    """Section items the Match Desk taught (tagline phrases, expertise items, tools, core items, engagement details)."""
    out = []
    spec = [("tagline_phrases", "tagline", "text"), ("competencies", "expertise", "text"), ("technologies", "tool", "name"),
            ("core_competencies", "core_item", "text")]
    for store, kind, field in spec:
        for n, it in enumerate(learned.get(store) or []):
            if it.get("status", "accepted") != "accepted":
                continue
            subj = {"id": f"{kind}:{slug(it[field])}", "kind": kind, "label": it[field], "origin": it.get("origin", "learned"),
                    "area": it.get("area"), "sort": 100 + n, "relations": []}
            c = _fact_claim(subj, FACTS[kind][0], {"value": it[field], "text": it[field], "evidence": it.get("evidence") or [],
                                                   "origin": it.get("origin", "learned")})
            c["tags"] = it.get("tags", [])
            out.append(c)
    for key, upd in (learned.get("engagement_updates") or {}).items():
        subj = {"id": f"eng:{key}", "kind": "engagement", "label": upd.get("client") or key, "origin": "learned"}
        for fact in FACTS["engagement"]:
            if upd.get(fact):
                out.append(_fact_claim(subj, fact, {"value": upd[fact], "evidence": upd.get("evidence") or [], "origin": "learned"}))
    return out


# ---------------------------------------------------------------- confidence, conflicts
def confidence_for(supports, contradicts, resolved, cfg, override=None):
    """Deterministic: strongest supporting source, +bonus per extra independent source type, capped; a Tim statement
    verifies; an unresolved contradiction disputes. Returns (confidence, basis, status)."""
    if override is not None:
        return float(override["value"]), f"override: {override.get('why', '')}", "active"
    if not supports:
        return 0.0, "no evidence", "active"
    types = {e["source_type"] for e in supports}
    conf = min(cfg["cap"], max(e["strength"] for e in supports) + cfg["corroboration_bonus"] * (len(types) - 1))
    basis = f"{len(supports)} evidence, {len(types)} source type{'s' if len(types) > 1 else ''}"
    if "USER_ENTERED" in types:
        conf, basis = cfg["verified_confidence"], basis + ", verified by Tim"
    status = "active"
    if contradicts and not resolved:
        conf, status, basis = round(max(0.0, conf - cfg["contradiction_penalty"]), 3), "disputed", basis + f", {len(contradicts)} contradicting, unresolved"
    elif contradicts:
        basis += f", {len(contradicts)} contradicting, resolved"
    return round(conf, 3), basis, status


DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?$")


def date_parts(v):
    m = DATE_RE.match(str(v or "").strip())
    return (int(m.group(1)), int(m.group(2)) if m.group(2) else None) if m else None


def values_conflict(a, b):
    """Two values for the same fact disagree. 2024 and 2024-11 are compatible (one is coarser); 2020 and 2021 are not."""
    if a in (None, "") or b in (None, ""):
        return False
    da, db = date_parts(a), date_parts(b)
    if da and db:
        return da[0] != db[0] or (da[1] is not None and db[1] is not None and da[1] != db[1])
    try:
        return abs(float(str(a).replace(",", "")) - float(str(b).replace(",", ""))) > 1e-9
    except ValueError:
        return norm(a) != norm(b)


# ---------------------------------------------------------------- number check (QA)
NUM_RE = re.compile(r"(?<![A-Za-z])~?\$?(\d[\d,]*(?:\.\d+)?)\s*(K\b|M\b|MM\b|B\b|thousand|million|billion)?(?![A-Za-z])", re.I)
SCALE = {"K": 1e3, "M": 1e6, "MM": 1e6, "B": 1e9, "THOUSAND": 1e3, "MILLION": 1e6, "BILLION": 1e9}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100,
                "half": 50, "dozen": 12}
WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.I)


def number_tokens(text):
    """Every number a line states, normalized so '$115K', '115,000' and '115000' match; number words count too
    ('nine budget owners', 'over half' -> 50)."""
    out = set()
    for m in WORD_RE.finditer(str(text or "")):
        out.add(str(NUMBER_WORDS[m.group(1).lower()]))
    for m in NUM_RE.finditer(str(text or "")):
        raw, suf = m.group(1).replace(",", ""), (m.group(2) or "").upper()
        try:
            v = float(raw)
        except ValueError:
            continue
        v *= SCALE.get(suf, 1)
        out.add(str(int(round(v))) if abs(v - round(v)) < 1e-9 else f"{v:.4g}")
    return out


def check_line(text, claim_rows, evidence_quotes, cfg, band=None, kind="bullet"):
    """QA for one printed line. claim_rows: the claims it is derived from; evidence_quotes: their evidence quotes."""
    issues = []
    if not claim_rows:
        issues.append("no claim trace")
    for c in claim_rows:
        if c.get("status") == "disputed":
            issues.append(f"disputed claim {c['id']}")
        if c.get("status") == "retired":
            issues.append(f"retired claim {c['id']}")
    allowed = set()
    for c in claim_rows:
        if c.get("value") is not None:
            allowed |= number_tokens(c["value"])
    for q in evidence_quotes:
        allowed |= number_tokens(q)
    missing = sorted(number_tokens(text) - allowed, key=lambda x: float(x))
    if missing and claim_rows:
        issues.append("numbers not in evidence: " + ", ".join(missing))
    if FIRST_PERSON.search(text or ""):
        issues.append("first person")
    if band:
        n = len(text or "")
        if n > band["hard_ceiling"]:
            issues.append(f"{n} chars > {band['hard_ceiling']}")
        if kind == "bullet" and n < band.get("p10", 97) - 20:
            issues.append(f"{n} chars, too short")
    return issues


# ---------------------------------------------------------------- projection: claims.json -> the profile shapes rot.py renders
def _val(subj, fact):
    f = (subj.get("facts") or {}).get(fact)
    if f is None:
        return None
    return f.get("value") if isinstance(f, dict) else f


def projection_from_claims(cj):
    """The winning value of every fact, in the shapes the rest of the tool already consumes (roles, education, ...)."""
    out = {"roles": [], "education": [], "certifications": [], "technologies": [], "tagline_phrases": [], "competencies": [],
           "core_competencies": [], "engagements": []}
    areas = {}
    for s in cj.get("subjects", []):
        k = s["kind"]
        if k == "role":
            if s.get("history_only"):
                continue
            out["roles"].append({"key": s["key"], "order": s.get("order", 50), "employer": _val(s, "employer"), "employer_private": s.get("employer_private"),
                                 "confidential": s.get("confidential", False), "title": _val(s, "title"), "title_variants": s.get("title_variants", []),
                                 "location": _val(s, "location"), "start": _val(s, "start"), "end": _val(s, "end"), "engagement": s.get("engagement"),
                                 "section": s.get("section", "experience"), "hidden_by_default": s.get("hidden_by_default", False),
                                 "date_note": s.get("date_note"), "context_line": _val(s, "context") or "", "claim_id": f"{s['id']}:title"})
        elif k == "education":
            out["education"].append({"school": _val(s, "school"), "degree": _val(s, "degree"), "degree_variants": s.get("degree_variants", []),
                                     "location": s.get("location"), "year": s.get("year") or str(_val(s, "date"))[-4:], "date_display": _val(s, "date"),
                                     "date_note": s.get("date_note"), "bullet_ids": s.get("bullet_ids", []), "hidden_bullet_ids": s.get("hidden_bullet_ids", []),
                                     "claim_id": f"{s['id']}:degree"})
        elif k == "credential":
            out["certifications"].append({"name": _val(s, "name"), "issuer": _val(s, "issuer"), "date": _val(s, "date"), "credential_id": s.get("credential_id"),
                                          "status": _val(s, "status"), "source": s.get("source"), "tags": s.get("tags", []), "sort": s.get("sort"),
                                          "hidden_by_default": s.get("hidden_by_default", False), "claim_id": f"{s['id']}:name"})
        elif k == "tool":
            out["technologies"].append({"name": _val(s, "name"), "category": s.get("category"), "tags": s.get("tags", []), "sort": s.get("sort"),
                                        "origin": s.get("origin", "curated"), "claim_id": f"{s['id']}:name"})
        elif k == "tagline":
            out["tagline_phrases"].append({"text": _val(s, "text"), "tags": s.get("tags", []), "sort": s.get("sort"), "origin": s.get("origin", "template"),
                                           "claim_id": f"{s['id']}:text"})
        elif k == "expertise":
            out["competencies"].append({"text": _val(s, "text"), "tags": s.get("tags", []), "sort": s.get("sort"), "origin": s.get("origin", "curated"),
                                        "claim_id": f"{s['id']}:text"})
        elif k == "core_item":
            areas.setdefault((s.get("area_sort", 99), s["area"]), []).append({"text": _val(s, "text"), "tags": s.get("tags", []), "sort": s.get("sort", 0),
                                                                              "claim_id": f"{s['id']}:text"})
        elif k == "engagement":
            out["engagements"].append({"key": s["key"], "role": s.get("role", "liminal"), "client": _val(s, "client"), "location": _val(s, "location"),
                                       "start": _val(s, "start"), "end": _val(s, "end"), "commitment": _val(s, "commitment"), "subtitle": _val(s, "subtitle"),
                                       "confidential": s.get("confidential", True), "needs_details": s.get("needs_details", False), "ask": s.get("ask"),
                                       "notes": s.get("notes"), "achievements": list(s.get("achievements", [])), "claim_id": f"{s['id']}:client"})
    out["roles"].sort(key=lambda r: r["order"])
    out["core_competencies"] = [{"label": label, "items": sorted(items, key=lambda i: i["sort"])} for (_, label), items in sorted(areas.items())]
    for key in ("technologies", "tagline_phrases", "competencies", "certifications"):
        out[key].sort(key=lambda x: (x.get("sort") is None, x.get("sort") or 0))
    return out


# ---------------------------------------------------------------- ingest (tiers 1 and 2 into resume.db)
def ingest_layer(con, cur, raw, achievements, learned, cj, cfg, bullet_ev, prof, achievement_tags):
    """Upsert evidence (append-only), rebuild claims, relations and confidence. Returns a report dict."""
    rep = {"errors": [], "warnings": [], "disputed": [], "low": [], "n_evidence": 0, "n_new_evidence": 0, "n_claims": 0,
           "n_relations": 0, "changed": 0}
    # ---- tier 1
    rows = source_evidence(raw, cfg) + logged_evidence(cfg)
    known = {r["id"]: r["hash"] for r in cur.execute("SELECT id, hash FROM evidence")}
    for r in rows:
        if r["id"] in known:
            if known[r["id"]] != r["hash"]:
                rep["errors"].append(f"evidence {r['id']} changed since it was recorded; evidence is append-only (retract it with a new row instead)")
            continue
        cur.execute("""INSERT INTO evidence (id,source_type,channel,source_ref,locator,question,quote,authored_at,observed_at,strength,hash)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (r["id"], r["source_type"], r.get("channel"), r.get("source_ref"), r.get("locator"), r.get("question"), r["quote"],
                     r.get("authored_at"), r.get("observed_at"), r["strength"], r["hash"]))
        rep["n_new_evidence"] += 1
    ev = {r["id"]: r for r in rows}
    for r in cur.execute("SELECT id, source_type, strength, quote FROM evidence"):
        ev.setdefault(r["id"], {"id": r["id"], "source_type": r["source_type"], "strength": r["strength"], "quote": r["quote"]})
    rep["n_evidence"] = len(ev)

    # ---- tier 2: claims
    roles_by_key = {r["key"]: r for r in prof.get("roles", [])}
    claims = subject_claims(cj) + implied_claims(achievements, roles_by_key) + learned_section_claims(learned)
    by_id = {}
    for c in claims:
        if c["id"] in by_id:                       # a learned item that duplicates a curated one adds its evidence
            by_id[c["id"]]["evidence"] += c["evidence"]
            continue
        by_id[c["id"]] = c
    claims = list(by_id.values())
    for b in learned.get("bullets", []):          # a learned wording's answer backs its achievement
        c = by_id.get(f"ach:{b['achievement_id']}")
        if c:
            c["evidence"] += b.get("evidence") or []
    # raw-bullet evidence for achievements (patterns already matched) and their metrics (value present in the line)
    ach_bullets = {}
    for r in cur.execute("SELECT achievement_id, raw_bullet_id FROM achievement_evidence"):
        eid = bullet_ev.get(r["raw_bullet_id"])
        if eid:
            ach_bullets.setdefault(r["achievement_id"], []).append(eid)
    for c in claims:
        if c["kind"] == "achievement":
            c["evidence"] += ach_bullets.get(c["achievement"], [])
        elif c["kind"] == "metric":
            toks = number_tokens(c["value"])
            for eid in ach_bullets.get(c["achievement"], []):
                q = ev[eid]["quote"]
                if toks & number_tokens(q):
                    c["evidence"].append(eid)
                if any(re.search(p, q, re.I) for p in c.get("contradict_patterns") or []):
                    c["contradicting"].append({"value": "(other figure)", "evidence": [eid]})
    # attach, validate ids
    for c in claims:
        c["evidence"] = sorted(set(c["evidence"]))
        for e in c["evidence"]:
            if e not in ev:
                rep["errors"].append(f"{c['id']}: unknown evidence id {e}")
        c["_sup"] = [ev[e] for e in c["evidence"] if e in ev]
        c["_contra"] = [(x["value"], e) for x in c["contradicting"] for e in x["evidence"] if e in ev]
        c["_ref"] = [e for e in c.get("refining") or [] if e in ev]
    # sibling conflicts: two active claims, same subject and predicate, different values, no resolution
    groups = {}
    for c in claims:
        if c["kind"] in MULTI_VALUE_KINDS or c["status"] != "active":
            continue
        groups.setdefault((c["subject"], c["predicate"]), []).append(c)
    for (_, _), grp in groups.items():
        for i, a in enumerate(grp):
            for b in grp[i + 1:]:
                if values_conflict(a["value"], b["value"]):
                    for x, y in ((a, b), (b, a)):
                        if not x.get("resolution"):
                            x["_contra"] += [(y["value"], e) for e in y["evidence"]]
                            x["_sibling"] = y["id"]
    # confidence: achievements/metrics/facts first, grounded phrases second
    conf_of = {}
    grounded = [c for c in claims if not c["_sup"] and any(r.get("rel") == "grounded_in" for r in c.get("relations") or [])]
    for c in claims:
        if c in grounded:
            continue
        conf, basis, status = confidence_for(c["_sup"], c["_contra"], bool(c.get("resolution")), cfg, c.get("confidence_override"))
        if c["status"] == "retired":
            status = "retired"
        c.update({"confidence": conf, "confidence_basis": basis, "status": status})
        conf_of[c["id"]] = conf
    for c in grounded:
        g = [conf_of.get(r["to"], 0.0) for r in c["relations"] if r.get("rel") == "grounded_in"]
        conf = round(0.9 * max(g), 3) if g else 0.0
        notes = {r.get("note") for r in c["relations"] if r.get("rel") == "grounded_in" and r.get("note")}
        why = next(iter(notes)) if len(notes) == 1 else "tag overlap"
        c.update({"confidence": conf, "confidence_basis": f"grounded in {len(g)} achievement{'s' if len(g) != 1 else ''} ({why})",
                  "status": c["status"] if c["status"] == "retired" else "active"})
        conf_of[c["id"]] = conf
    # ---- write claims (stable ids; earlier states go to claim_history), evidence links, relations
    old = {r["id"]: dict(r) for r in cur.execute("SELECT * FROM claims")}
    now = now_iso()
    for c in claims:
        o = old.get(c["id"])
        row = (c["kind"], c["subject"], c["predicate"], c["value"], c["value_num"], c["unit"], c["text"], c["valid_from"], c["valid_to"],
               c["as_of"], c["status"], c["confidence"], c["confidence_basis"], cfg["formula_version"], c["origin"], c.get("area"), c.get("sort"))
        if o:
            changed = any(str(o.get(k)) != str(v) for k, v in zip(("value", "text", "status"), (c["value"], c["text"], c["status"])))
            if changed:
                cur.execute("INSERT INTO claim_history (claim_id,changed_at,value,text,status,confidence,why) VALUES (?,?,?,?,?,?,?)",
                            (c["id"], now, o["value"], o["text"], o["status"], o["confidence"], "ingest: curation changed"))
                rep["changed"] += 1
            if changed or o.get("confidence") != c["confidence"]:
                cur.execute("INSERT INTO claim_confidence_history (claim_id,computed_at,confidence,status,n_evidence,formula_version) VALUES (?,?,?,?,?,?)",
                            (c["id"], now, c["confidence"], c["status"], len(c["_sup"]), cfg["formula_version"]))
            cur.execute("""UPDATE claims SET kind=?,subject=?,predicate=?,value=?,value_num=?,unit=?,text=?,valid_from=?,valid_to=?,as_of=?,
                           status=?,confidence=?,confidence_basis=?,formula_version=?,origin=?,area=?,sort=? WHERE id=?""", row + (c["id"],))
        else:
            cur.execute("""INSERT INTO claims (kind,subject,predicate,value,value_num,unit,text,valid_from,valid_to,as_of,status,confidence,
                           confidence_basis,formula_version,origin,area,sort,id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row + (c["id"], now))
            cur.execute("INSERT INTO claim_confidence_history (claim_id,computed_at,confidence,status,n_evidence,formula_version) VALUES (?,?,?,?,?,?)",
                        (c["id"], now, c["confidence"], c["status"], len(c["_sup"]), cfg["formula_version"]))
        for e in c["evidence"]:
            if e in ev:
                cur.execute("INSERT OR IGNORE INTO claim_evidence VALUES (?,?,?)", (c["id"], e, "supports"))
        for _, e in c["_contra"]:
            cur.execute("INSERT OR REPLACE INTO claim_evidence VALUES (?,?,?)", (c["id"], e, "contradicts"))
        for e in c["_ref"]:
            cur.execute("INSERT OR IGNORE INTO claim_evidence VALUES (?,?,?)", (c["id"], e, "refines"))
        for r in c.get("relations") or []:
            frm, to = (r["to"], c["id"]) if r.get("reverse") else (c["id"], r["to"])
            cur.execute("INSERT OR IGNORE INTO claim_relations (from_claim,to_claim,rel,confidence,note) VALUES (?,?,?,?,?)",
                        (frm, to, r["rel"], r.get("confidence", 1.0), r.get("note")))
        if c.get("_sibling"):
            cur.execute("INSERT OR IGNORE INTO claim_relations (from_claim,to_claim,rel,confidence,note) VALUES (?,?,?,?,?)",
                        (c["id"], c["_sibling"], "contradicts", 1.0, "same fact, different value"))
    # derived relations: tagged, achievement part_of engagement, tool used_in achievement
    for aid, tag, w in achievement_tags:
        cur.execute("INSERT OR IGNORE INTO claim_relations (from_claim,to_claim,rel,confidence,note) VALUES (?,?,?,?,?)", (f"ach:{aid}", tag, "tagged", w, None))
    for e in prof.get("engagements", []):
        for aid in e.get("achievements", []):
            cur.execute("INSERT OR IGNORE INTO claim_relations (from_claim,to_claim,rel,confidence,note) VALUES (?,?,?,?,?)",
                        (f"ach:{aid}", f"eng:{e['key']}", "part_of", 1.0, "engagement membership"))
    canon = {a["id"]: a["canonical"] for a in achievements}
    for t in prof.get("technologies", []):
        base = norm(re.split(r"[(&/]", t["name"])[0])
        if len(base) < 4:
            continue
        for aid, text in canon.items():
            if base in norm(text):
                cur.execute("INSERT OR IGNORE INTO claim_relations (from_claim,to_claim,rel,confidence,note) VALUES (?,?,?,?,?)",
                            (f"tool:{slug(re.split(r'[(&/]', t['name'])[0])}", f"ach:{aid}", "used_in", 0.8, "named in the bullet"))
    # retire claims that left curation
    live = {c["id"] for c in claims}
    for cid, o in old.items():
        if cid not in live and o["status"] != "retired":
            cur.execute("INSERT INTO claim_history (claim_id,changed_at,value,text,status,confidence,why) VALUES (?,?,?,?,?,?,?)",
                        (cid, now, o["value"], o["text"], o["status"], o["confidence"], "removed from curation"))
            cur.execute("UPDATE claims SET status='retired' WHERE id=?", (cid,))
    # ---- checks and report
    for c in claims:
        if c["status"] == "disputed":
            rep["disputed"].append((c["id"], c["value"], c["confidence_basis"]))
        elif c["status"] == "active" and c["confidence"] < cfg["print"]["fact_min"]:
            rep["low"].append((c["id"], c["value"] or (c["text"] or "")[:60], c["confidence"]))
        if not c["_sup"] and c not in grounded and c["status"] != "retired":
            rep["errors"].append(f"{c['id']}: no evidence and no grounding")
    rep["n_claims"] = len(claims)
    rep["n_relations"] = cur.execute("SELECT COUNT(*) FROM claim_relations").fetchone()[0]
    rep["n_disputed"], rep["n_low"] = len(rep["disputed"]), len(rep["low"])
    return rep


def claim_context(con, claim_ids):
    """Claim rows and their supporting evidence quotes, for QA checks and the library export."""
    rows, quotes = [], []
    for cid in claim_ids:
        r = con.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
        if r:
            rows.append(dict(r))
            quotes += [q[0] for q in con.execute("SELECT e.quote FROM claim_evidence ce JOIN evidence e ON e.id=ce.evidence_id "
                                                  "WHERE ce.claim_id=? AND ce.stance IN ('supports','refines')", (cid,))]
    return rows, quotes
