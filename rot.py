#!/usr/bin/env python3
"""Resume Optimization Tool (ROT) · CLI

  python rot.py ingest                 rebuild resume.db from sources/raw_extract.json + curation/*.json
                                        (fails if any raw bullet is not assigned to an achievement)
  python rot.py query --tags a,b [--family f] [--role r]
  python rot.py match JD.txt           requirement map + coverage + ranked bullets for a job description
  python rot.py build [--jd JD.txt] [--name out] [--version v1]
                                        resume JSON + Markdown + HTML + PDF (headless Chrome) under out/
  python rot.py export                 data/library.json for the web artifact (confidential names scrubbed)
                                        + data/dump.sql for readable git diffs
  python rot.py learn FILE.json        merge artifact learnings (JDs, follow-up answers, new bullets, feedback)
  python rot.py profile                data profile of the database -> reports/db_profile.md

Design: sources are never edited; curated bullets are append-only (edits supersede); learning
tables survive re-ingest; learned bullets live in curation/learned.json so the DB is reproducible.
"""
import argparse, datetime as dt, hashlib, html, json, re, sqlite3, subprocess, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DB = ROOT / "resume.db"
CUR = ROOT / "curation"
CHROME = [Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
          Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")]
CURATED_TABLES = ["achievement_evidence", "achievement_tags", "raw_bullets", "achievements", "tags",
                  "competencies", "technologies", "domain_fluency", "certifications", "education",
                  "summaries", "roles", "sources", "meta", "enums"]
BANNED_IN_OUTPUT = [r"liminal", r"therapy companion", r"\bkamal\b", r"co-up\b", r"sonnett"]
ROLE_ALIAS = {"liminal": "hc_ai_strategy"}          # internal role key -> exported key (confidential)
ROLE_UNALIAS = {v: k for k, v in ROLE_ALIAS.items()}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


# ---------------------------------------------------------------- helpers
def jload(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def jdump(obj, p):
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def norm(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def fmt_date(v):
    if not v:
        return "Present"
    if re.fullmatch(r"\d{4}-\d{2}", v):
        y, m = v.split("-")
        return f"{MONTHS[int(m) - 1]} {y}"
    return v


def load_curation():
    tax = jload(CUR / "taxonomy.json")
    ach = jload(CUR / "achievements.json")["achievements"]
    prof = jload(CUR / "profile.json")
    base = jload(CUR / "baseline.json")
    learned = jload(CUR / "learned.json", {"achievements": [], "bullets": [], "overrides": {},
                                            "profile_overrides": {}, "baseline_overrides": {}})
    # learned achievements join the curated set; overrides patch curated fields
    ach = ach + learned.get("achievements", [])
    for a in ach:
        o = learned.get("overrides", {}).get(a["id"])
        if o:
            for k, v in o.items():
                if k == "variants":
                    a.setdefault("variants", {}).update(v)
                elif k == "tags":
                    a.setdefault("tags", {}).update(v)
                elif k == "retire_variants":
                    a["retired_variants"] = list(v)
                elif k == "_gate":
                    a["override_why"] = v
                elif not k.startswith("_"):
                    a[k] = v
    for r in prof["roles"]:
        r.update(learned.get("profile_overrides", {}).get("roles", {}).get(r["key"], {}))
    for k, v in learned.get("profile_overrides", {}).items():
        if k != "roles":
            prof[k] = v
    for k, v in learned.get("baseline_overrides", {}).items():
        if not k.startswith("_"):
            base[k] = v
    for role, order in base.pop("priority_overrides", {}).items():
        base["priority"][role] = order
    # learned achievements join the priority list for their role (after curated ones)
    for a in learned.get("achievements", []):
        lst = base["priority"].setdefault(a["role"], [])
        if a["id"] not in lst:
            lst.append(a["id"])
    return tax, ach, prof, base, learned


# ---------------------------------------------------------------- ingest
def cmd_ingest(args):
    raw = jload(ROOT / "sources/raw_extract.json")
    if raw is None:
        sys.exit("run: python extract.py  first")
    tax, ach, prof, base, learned = load_curation()
    con = connect()
    con.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
    con.execute("PRAGMA foreign_keys = OFF")  # curated tables are rebuilt; integrity re-checked below
    cur = con.cursor()
    for t in CURATED_TABLES:
        cur.execute(f"DELETE FROM {t}")

    # enums
    for i, (code, label) in enumerate([("verified", "Consistent across sources"), ("asserted", "Single source"),
                                       ("conflict", "Sources disagree")]):
        cur.execute("INSERT INTO enums VALUES ('confidence',?,?,?)", (code, label, i))
    for i, code in enumerate(["canonical", "variant", "learned"]):
        cur.execute("INSERT INTO enums VALUES ('bullet_kind',?,?,?)", (code, code, i))
    for fam, label in tax["families"].items():
        cur.execute("INSERT INTO enums VALUES ('tag_family',?,?,0)", (fam, label))

    # sources, roles
    for s in raw:
        cur.execute("INSERT INTO sources (id,file,md5,target_role,kind,headline) VALUES (?,?,?,?,?,?)",
                    (s["id"], s["file"], s["md5"], s["target_role"], s["kind"], s.get("headline")))
    for r in prof["roles"]:
        cur.execute("""INSERT INTO roles (key,sort,employer,employer_private,confidential,title,title_variants,location,
                       start,end,engagement,hidden_by_default,date_note,context_line) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (r["key"], r["order"], r["employer"], r.get("employer_private"), int(r.get("confidential", False)),
                     r["title"], json.dumps(r.get("title_variants", [])), r.get("location"), r.get("start"), r.get("end"),
                     r.get("engagement"), int(r.get("hidden_by_default", False)), r.get("date_note"), r.get("context_line")))
    cur.execute("INSERT OR IGNORE INTO roles (key,sort,employer,title) VALUES ('education',99,'Education','Education')")

    # tags
    for tid, t in tax["tags"].items():
        cur.execute("INSERT INTO tags VALUES (?,?,?,?)", (tid, t["family"], t["label"], json.dumps(t["synonyms"])))

    # raw bullets
    raw_rows = []
    for s in raw:
        for b in s["bullets"]:
            cur.execute("INSERT INTO raw_bullets (source_id,role_key,section,text,chars,norm) VALUES (?,?,?,?,?,?)",
                        (s["id"], b["role"], b["section"], b["text"], len(b["text"]), norm(b["text"])))
            raw_rows.append((cur.lastrowid, b["role"], b["text"], s["id"]))

    # achievements + tags + evidence
    known_tags = set(tax["tags"])
    errors = []
    for a in ach:
        cur.execute("INSERT INTO achievements (id,role_key,confidence,notes,metrics) VALUES (?,?,?,?,?)",
                    (a["id"], a["role"], a.get("confidence", "asserted"), a.get("notes", ""), json.dumps(a.get("metrics", []))))
        for tag, w in a.get("tags", {}).items():
            if tag not in known_tags:
                errors.append(f"{a['id']}: unknown tag '{tag}'")
                continue
            cur.execute("INSERT INTO achievement_tags VALUES (?,?,?)", (a["id"], tag, w))
    by_role = {}
    for a in ach:
        by_role.setdefault(a["role"], []).append(a)
    unassigned = []
    for rid, role, text, sid in raw_rows:
        hits = [a["id"] for a in by_role.get(role, []) if any(re.search(p, text, re.I) for p in a.get("patterns", []))]
        for h in hits:
            cur.execute("INSERT OR IGNORE INTO achievement_evidence VALUES (?,?)", (h, rid))
        if not hits:
            unassigned.append((sid, role, text))

    # bullets (append-only merge by key = achievement:kind:angle)
    existing = {}
    for row in cur.execute("SELECT id, achievement_id, kind, angle, text FROM bullets WHERE superseded_by IS NULL"):
        existing[(row["achievement_id"], row["kind"], row["angle"] or "")] = (row["id"], row["text"])
    wanted = []
    for a in ach:
        st = "rejected" if a.get("retired") else "accepted"
        why = a.get("override_why")
        wanted.append((a["id"], "canonical", "", a["canonical"], a.get("origin", "curated"), st, why))
        for angle, text in a.get("variants", {}).items():
            vst = "rejected" if angle in a.get("retired_variants", []) else st
            wanted.append((a["id"], "variant", angle, text, a.get("origin", "curated"), vst, why))
    for b in learned.get("bullets", []):
        wanted.append((b["achievement_id"], "learned", b.get("angle", ""), b["text"], b.get("origin", "artifact"),
                       b.get("status", "accepted"), b.get("why")))
    added = superseded = 0
    ach_ids = {a["id"] for a in ach}
    for aid, kind, angle, text, origin, status, why in wanted:
        if aid not in ach_ids:
            errors.append(f"bullet for unknown achievement {aid}")
            continue
        key = (aid, kind, angle)
        if key in existing and existing[key][1] == text:
            cur.execute("UPDATE bullets SET status=? WHERE id=?", (status, existing[key][0]))
            continue
        cur.execute("INSERT INTO bullets (achievement_id,kind,angle,text,chars,status,origin) VALUES (?,?,?,?,?,?,?)",
                    (aid, kind, angle or None, text, len(text), status, origin))
        new_id = cur.lastrowid
        added += 1
        if key in existing:
            cur.execute("UPDATE bullets SET superseded_by=?, supersede_why=? WHERE id=?",
                        (new_id, why or ("curation edit" if origin == "curated" else f"{origin} update"), existing[key][0]))
            superseded += 1
    # retire bullets whose curated definition disappeared
    wanted_keys = {(w[0], w[1], w[2]) for w in wanted}
    for key, (bid, _) in existing.items():
        if key not in wanted_keys:
            cur.execute("UPDATE bullets SET status='rejected', supersede_why='removed from curation' WHERE id=?", (bid,))

    # profile facts
    for c in prof["competencies"]:
        cur.execute("INSERT INTO competencies (text,tags) VALUES (?,?)", (c["text"], json.dumps(c["tags"])))
    cur.execute("DELETE FROM expertise_areas")
    for ai, area in enumerate(prof.get("expertise_areas", [])):
        for ii, it in enumerate(area["items"]):
            cur.execute("INSERT INTO expertise_areas (area,area_sort,text,tags,sort) VALUES (?,?,?,?,?)",
                        (area["label"], ai, it["text"], json.dumps(it["tags"]), ii))
    for t in prof["technologies"]:
        cur.execute("INSERT INTO technologies (name,category,tags) VALUES (?,?,?)", (t["name"], t["category"], json.dumps(t["tags"])))
    for d in prof["domain_fluency"]:
        cur.execute("INSERT INTO domain_fluency (name,tags) VALUES (?,?)", (d["name"], json.dumps(d["tags"])))
    for c in prof["certifications"]:
        cur.execute("INSERT INTO certifications (name,issuer,date,credential_id,status,source,tags) VALUES (?,?,?,?,?,?,?)",
                    (c["name"], c["issuer"], c.get("date"), c.get("credential_id"), c.get("status"), c.get("source"), json.dumps(c.get("tags", []))))
    for e in prof["education"]:
        cur.execute("INSERT INTO education (school,degree,degree_variants,location,year,date_note,bullet_ids) VALUES (?,?,?,?,?,?,?)",
                    (e["school"], e["degree"], json.dumps(e.get("degree_variants", [])), e.get("location"), e["year"], e.get("date_note"), json.dumps(e.get("bullet_ids", []))))
    cur.execute("INSERT INTO summaries (source_id,tags,text,origin) VALUES (NULL,?,?, 'baseline')",
                (json.dumps(["gtm-strategy", "new-business", "full-cycle-sales"]), base["summary"]))
    for s in prof["summaries"]:
        cur.execute("INSERT INTO summaries (source_id,tags,text) VALUES (?,?,?)", (s["source"], json.dumps(s["tags"]), s["text"]))

    # length band from Resume 1 (the bullet standard)
    r1 = sorted(len(b["text"]) for b in raw[0]["bullets"])
    q = lambda p: r1[min(len(r1) - 1, int(round(p * (len(r1) - 1))))]
    band = {"source": raw[0]["id"], "n": len(r1), "min": r1[0], "p10": q(.1), "p25": q(.25), "median": q(.5),
            "p75": q(.75), "p90": q(.9), "max": r1[-1], "hard_ceiling": 170}
    cur.execute("INSERT INTO meta VALUES ('length_band', ?)", (json.dumps(band),))
    cur.execute("INSERT INTO meta VALUES ('ingested_at', ?)", (dt.datetime.now().isoformat(timespec="seconds"),))
    con.commit()
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    for r in fk:
        errors.append(f"foreign key: {tuple(r)}")

    # ---- report
    n_raw = len(raw_rows)
    n_unique = cur.execute("SELECT COUNT(DISTINCT role_key||norm) FROM raw_bullets").fetchone()[0]
    print(f"sources: {len(raw)}   raw bullets: {n_raw} ({n_unique} unique)   achievements: {len(ach)}   tags: {len(tax['tags'])}")
    print(f"bullets: +{added} new, {superseded} superseded   length band (R1): p10={band['p10']} median={band['median']} p90={band['p90']} ceiling={band['hard_ceiling']}")
    long_ = cur.execute("SELECT achievement_id, kind, angle, chars FROM current_bullets WHERE chars > ? OR chars < ?",
                        (band["hard_ceiling"], band["p10"] - 20)).fetchall()
    for r in long_:
        print(f"  LENGTH  {r['achievement_id']} {r['kind']} {r['angle'] or ''}: {r['chars']} chars")
    for e in errors:
        print("  ERROR  ", e)
    if unassigned:
        print(f"\nUNASSIGNED raw bullets: {len(unassigned)}")
        for sid, role, text in unassigned:
            print(f"  [{sid}] ({role}) {text[:140]}")
        sys.exit(1)
    if errors:
        sys.exit(1)
    print("coverage: every raw bullet is assigned to >= 1 achievement ✓")


# ---------------------------------------------------------------- matching
def tag_index(con):
    tags = {}
    for r in con.execute("SELECT * FROM tags"):
        tags[r["id"]] = {"family": r["family"], "label": r["label"], "synonyms": json.loads(r["synonyms"])}
    return tags


REQ_HINT = re.compile(r"(require|qualif|must|you have|you bring|what you.ll need|experience with|proven|track record|"
                      r"responsib|you will|what you.ll do|preferred|bonus|nice to have)", re.I)


def extract_requirements(jd_text, tags):
    """Map a JD to tag weights. Weight = min(hits,3) × section boost; niche phrases score > generic."""
    lines = [l.strip() for l in jd_text.splitlines() if l.strip()]
    boost_lines = set()
    in_req = False
    for i, l in enumerate(lines):
        if len(l) < 80 and REQ_HINT.search(l):
            in_req = True
        elif len(l) < 60 and l.endswith(":") and not REQ_HINT.search(l):
            in_req = False
        if in_req:
            boost_lines.add(i)
    req = {}
    for tid, t in tags.items():
        hits, phrases = 0.0, []
        for syn in t["synonyms"]:
            pat = r"(?<![a-z0-9-])" + re.escape(syn.lower()) + r"(?![a-z0-9])"
            for i, l in enumerate(lines):
                n = len(re.findall(pat, l.lower()))
                if n:
                    specificity = 1.0 if len(syn) > 4 else 0.6
                    hits += n * specificity * (1.4 if i in boost_lines else 1.0)
                    phrases.append(syn)
        if hits:
            req[tid] = {"weight": round(min(hits, 3.0), 2), "phrases": sorted(set(phrases))}
    return req


def load_bullets(con, include_hidden=True):
    rows = con.execute("""SELECT b.id, b.achievement_id, b.kind, b.angle, b.text, b.chars, b.score_adj, b.origin,
                                 a.role_key, a.confidence, r.sort AS role_sort, r.hidden_by_default
                          FROM current_bullets b JOIN achievements a ON a.id=b.achievement_id
                          JOIN roles r ON r.key=a.role_key""").fetchall()
    atags = {}
    for r in con.execute("SELECT * FROM achievement_tags"):
        atags.setdefault(r["achievement_id"], {})[r["tag_id"]] = r["weight"]
    metr = {r["id"]: bool(json.loads(r["metrics"] or "[]")) for r in con.execute("SELECT id, metrics FROM achievements")}
    ach = {}
    for r in rows:
        a = ach.setdefault(r["achievement_id"], {"id": r["achievement_id"], "role": r["role_key"], "confidence": r["confidence"],
                                                 "has_metrics": metr.get(r["achievement_id"], False),
                                                 "role_sort": r["role_sort"], "hidden": r["hidden_by_default"],
                                                 "tags": atags.get(r["achievement_id"], {}), "texts": []})
        a["texts"].append(dict(r))
    return ach


def score_achievement(a, req, tags):
    """Direct tag hits count fully; same-family hits count 25% (niche rolls up to family)."""
    if not req:
        return 0.0, []
    fam_w = {}
    for tid, r in req.items():
        fam_w[tags[tid]["family"]] = fam_w.get(tags[tid]["family"], 0) + r["weight"]
    s, why = 0.0, []
    for tid, w in a["tags"].items():
        if tid in req:
            s += w * req[tid]["weight"]
            why.append(tid)
        else:
            s += 0.25 * w * min(fam_w.get(tags[tid]["family"], 0), 2.0)  # family roll-up
    adj = max((t["score_adj"] or 0) for t in a["texts"])
    conf = {"verified": 1.0, "asserted": 0.95, "conflict": 0.9}.get(a["confidence"], 0.9)
    return round((s + adj) * conf, 3), why


def angle_score(m, req, tags):
    """Relevance of a variant's angle: max JD weight over its tag(s) or family (max, not sum)."""
    if "tag" in m:
        return req.get(m["tag"], {}).get("weight", 0.0)
    if "tags" in m:
        return max([req.get(t, {}).get("weight", 0.0) for t in m["tags"]] or [0.0])
    if "family" in m:
        return max([r["weight"] for tid, r in req.items() if tags[tid]["family"] == m["family"]] or [0.0])
    return 0.0


def pick_text(a, req, tags, base):
    """Canonical by default. A variant wins only when its angle is a strong JD requirement AND clearly
    beats the canonical's own best-matched requirement (so broad angles can't displace metric bullets)."""
    sc = base.get("scoring", {})
    canon = next((t for t in a["texts"] if t["kind"] == "canonical"), a["texts"][0])
    canon_rel = max([req[t]["weight"] for t in a["tags"] if t in req] or [0.0])
    best, best_s = canon, 0.0
    for t in a["texts"]:
        if t["kind"] not in ("variant", "learned"):
            continue
        m = base["angle_map"].get(t["angle"] or "", {})
        s = angle_score(m, req, tags) if m else (canon_rel + 0.1 + (t["score_adj"] or 0) if t["kind"] == "learned" else 0.0)
        if s > best_s:
            best, best_s = t, s
    if best is not canon and best_s >= sc.get("variant_min", 1.5) and best_s > sc.get("variant_margin", 1.25) * canon_rel:
        return best
    if best is not canon and best["kind"] == "learned" and best_s >= canon_rel:
        return best
    return canon


def select(con, req, base, tags, caps=None):
    ach = load_bullets(con)
    caps = caps or base["caps"]
    prio = base["priority"]
    by_role = {}
    for a in ach.values():
        if a["role"] == "education":
            continue
        s, why = score_achievement(a, req, tags)
        plist = prio.get(a["role"], [])
        rank = plist.index(a["id"]) if a["id"] in plist else 99
        if req:
            sc = base.get("scoring", {})
            s += sc.get("priority_bonus", 1.5) * max(0.0, 1 - rank / max(len(plist), 1))
            s += sc.get("metric_bonus", 0.5) if a.get("has_metrics") else 0.0
        by_role.setdefault(a["role"], []).append((round(s, 3), -rank, a, why))
    chosen = {}
    for role, items in by_role.items():
        items.sort(key=lambda x: (x[0], x[1]), reverse=True)
        hidden = items[0][2]["hidden"]
        top = items[0][0]
        if hidden and (not req or top < base.get("scoring", {}).get("hidden_role_min", 4.0)):
            continue
        cap = caps.get(role, 3)
        chosen[role] = [(s, a, why, pick_text(a, req, tags, base)) for s, _, a, why in items[:cap]]
    return chosen


def coverage(req, chosen):
    cov = {}
    for tid in req:
        best = 0.0
        for items in chosen.values():
            for s, a, why, t in items:
                if tid in a["tags"]:
                    best = max(best, a["tags"][tid])
        cov[tid] = best
    return cov


def cmd_match(args):
    con = connect()
    tags = tag_index(con)
    _, _, _, base, _ = load_curation()
    jd = Path(args.jd).read_text(encoding="utf-8")
    req = extract_requirements(jd, tags)
    chosen = select(con, req, base, tags)
    cov = coverage(req, chosen)
    print("REQUIREMENTS (tag · weight · coverage · JD phrases)")
    for tid, r in sorted(req.items(), key=lambda x: -x[1]["weight"]):
        c = cov[tid]
        mark = "✓" if c >= 0.8 else ("~" if c > 0 else "✗")
        print(f"  {mark} {tags[tid]['label']:<46} {r['weight']:>4}  cov={c:.1f}  {', '.join(r['phrases'][:4])}")
    total = sum(r["weight"] for r in req.values()) or 1
    score = sum(r["weight"] * min(cov[t], 1.0) for t, r in req.items()) / total
    print(f"\nMATCH SCORE: {score:.0%}   gaps (weight >= 1, coverage < 0.5):",
          ", ".join(tags[t]["label"] for t, r in req.items() if r["weight"] >= 1 and cov[t] < 0.5) or "none")
    print("\nSELECTED BULLETS")
    for role in sorted(chosen, key=lambda k: next(iter(chosen[k]))[1]["role_sort"]):
        print(f"  [{role}]")
        for s, a, why, t in chosen[role]:
            print(f"    {s:5.2f}  {t['text']}")


def cmd_query(args):
    con = connect()
    tags = tag_index(con)
    want = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    for t in want:
        if t not in tags:
            cand = [k for k, v in tags.items() if t.lower() in v["label"].lower() or t.lower() in k]
            if not cand:
                sys.exit(f"unknown tag '{t}'")
            want[want.index(t)] = cand[0]
    if args.family:
        want += [k for k, v in tags.items() if v["family"] == args.family]
    req = {t: {"weight": 1.0, "phrases": []} for t in want}
    ach = load_bullets(con)
    res = []
    for a in ach.values():
        if args.role and a["role"] != args.role:
            continue
        s = sum(a["tags"].get(t, 0) for t in req)
        if s > 0:
            res.append((s, a))
    res.sort(key=lambda x: -x[0])
    print(f"{len(res)} achievements match {', '.join(want)}")
    for s, a in res[: args.limit]:
        canon = next(t for t in a["texts"] if t["kind"] == "canonical")
        print(f"  {s:4.1f} [{a['role']}] {a['id']}\n        {canon['text']}")
        for t in a["texts"]:
            if t["kind"] != "canonical":
                print(f"        ↳ ({t['kind']}:{t['angle']}) {t['text']}")


# ---------------------------------------------------------------- build / render
def assemble(con, req, base, prof_roles, version, jd_meta=None):
    tags = tag_index(con)
    chosen = select(con, req, base, tags)
    roles = {r["key"]: dict(r) for r in con.execute("SELECT * FROM roles")}
    # competencies: JD-ranked or baseline order
    comps = [dict(r) for r in con.execute("SELECT * FROM competencies")]
    if req:
        for c in comps:
            c["s"] = sum(req.get(t, {}).get("weight", 0) for t in json.loads(c["tags"]))
        comps.sort(key=lambda c: -c["s"])
        comp_list = [c["text"] for c in comps if c["s"] > 0][: base["competency_count"]]
        for t in base["competency_order"]:
            if len(comp_list) >= base["competency_count"]:
                break
            if t not in comp_list:
                comp_list.append(t)
    else:
        comp_list = base["competency_order"][: base["competency_count"]]
    tech = [r["name"] for r in con.execute("SELECT * FROM technologies ORDER BY id")]
    if req:
        tech.sort(key=lambda n: -sum(req.get(t, {}).get("weight", 0) for t in
                                     json.loads(con.execute("SELECT tags FROM technologies WHERE name=?", (n,)).fetchone()[0])))
    certs = []
    for c in con.execute("SELECT * FROM certifications ORDER BY id"):
        when = "In progress" if c["status"] else (fmt_date(c["date"]) if c["date"] else "")
        certs.append(f"{c['name']} — {c['issuer']}" + (f" ({when})" if when else ""))
    edu = []
    ach_all = load_bullets(con)
    for e in con.execute("SELECT * FROM education"):
        bl = [next(t for t in ach_all[b]["texts"] if t["kind"] == "canonical")["text"] for b in json.loads(e["bullet_ids"]) if b in ach_all]
        edu.append({"degree": e["degree"], "school": e["school"], "year": e["year"], "bullets": bl})
    out_roles = []
    for key in sorted(chosen, key=lambda k: roles[k]["sort"]):
        r = roles[key]
        out_roles.append({
            "key": key, "title": r["title"], "employer": r["employer"], "location": r["location"],
            "dates": f"{fmt_date(r['start'])} – {fmt_date(r['end'])}",
            "context": r["engagement"] if key == "liminal" else (r["context_line"] or ""),
            "bullets": [t["text"] for s, a, why, t in chosen[key]],
            "bullet_ids": [t["id"] for s, a, why, t in chosen[key]],
            "achievement_ids": [a["id"] for s, a, why, t in chosen[key]],
        })
    ident = jload(CUR / "profile.json")["identity"]
    cov = coverage(req, chosen) if req else {}
    total = sum(r["weight"] for r in req.values()) or 1
    # areas of expertise (categorized block): JD-ranked within each area, capped per area
    areas = {}
    for r in con.execute("SELECT * FROM expertise_areas ORDER BY area_sort, sort"):
        s = sum(req.get(t, {}).get("weight", 0) for t in json.loads(r["tags"])) if req else 0
        areas.setdefault((r["area_sort"], r["area"]), []).append((-s, r["sort"], r["text"]))
    n_items = base.get("expertise_items_per_area", 7)
    expertise = [{"label": label, "items": [t for _, _, t in sorted(items)[:n_items]]}
                 for (_, label), items in sorted(areas.items())]
    layout = base.get("layout", {}).get("expertise_block", "none")
    return {
        "version": version, "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "jd": jd_meta, "identity": ident, "headline": base["headline"], "summary": base["summary"],
        "competencies": comp_list, "technologies": tech, "roles": out_roles, "certifications": certs, "education": edu,
        "expertise": expertise if layout != "none" else [], "layout": layout,
        "match": {"score": round(sum(r["weight"] * min(cov.get(t, 0), 1.0) for t, r in req.items()) / total, 3) if req else None,
                  "requirements": {t: {"label": tags[t]["label"], **r, "coverage": cov.get(t, 0)} for t, r in req.items()}},
    }


def render_html(res):
    e = html.escape
    i = res["identity"]
    parts = [f"<h1>{e(i['name'])}</h1>",
             f"<div class='headline'>{e(res['headline'])}</div>",
             f"<div class='contact'>{e(i['location'])} · {e(i['phone'])} · <a href='mailto:{e(i['email'])}'>{e(i['email'])}</a> · "
             f"<a href='https://{e(i['linkedin'])}'>{e(i['linkedin'])}</a></div>"]
    if res.get("summary"):
        parts.append("<h2>Professional Summary</h2>")
        parts.append(f"<p class='summary'>{e(res['summary'])}</p>")
    parts.append("<h2>Core Competencies</h2>")
    parts.append(f"<p class='comp'>{' · '.join(e(c) for c in res['competencies'])}</p>")
    parts.append(f"<p class='sys'><b>Systems:</b> {' · '.join(e(t) for t in res['technologies'])}</p>")
    parts.append("<h2>Professional Experience</h2>")
    for r in res["roles"]:
        parts.append("<div class='role'>")
        parts.append(f"<div class='role-head'><span class='role-title'>{e(r['title'])} <span class='emp'>| {e(r['employer'])}</span></span>"
                     f"<span class='role-dates'>{e(r['dates'])}</span></div>")
        meta = e(r["location"] or "") + (f" · {e(r['context'])}" if r.get("context") else "")
        parts.append(f"<div class='role-meta'>{meta}</div><ul>")
        parts += [f"<li>{e(b)}</li>" for b in r["bullets"]]
        parts.append("</ul></div>")
    parts.append("<h2>Certifications</h2><ul>")
    parts += [f"<li>{e(c)}</li>" for c in res["certifications"]]
    parts.append("</ul><h2>Education</h2>")
    for ed in res["education"]:
        parts.append(f"<div class='edu'><b>{e(ed['degree'])}</b> | {e(ed['school'])} | {e(ed['year'])}</div><ul>")
        parts += [f"<li>{e(b)}</li>" for b in ed["bullets"]]
        parts.append("</ul>")
    if res.get("expertise"):
        parts.append("<h2>Areas of Expertise</h2>")
        parts += [f"<p class='skill'><b>{e(a['label'])}:</b> {e(', '.join(a['items']))}</p>" for a in res["expertise"]]
    tpl = (ROOT / "templates/resume.html").read_text(encoding="utf-8")
    return tpl.replace("{{title}}", e(f"{i['name']} — Resume")).replace("{{body}}", "\n".join(parts))


def render_md(res):
    i = res["identity"]
    L = [f"# {i['name']}", f"**{res['headline']}**  ", f"{i['location']} · {i['phone']} · {i['email']} · {i['linkedin']}", ""]
    if res.get("summary"):
        L += ["## Professional Summary", res["summary"], ""]
    L += ["## Core Competencies", " · ".join(res["competencies"]), "", f"**Systems:** {' · '.join(res['technologies'])}", "",
          "## Professional Experience"]
    for r in res["roles"]:
        L += [f"**{r['title']}** | {r['employer']} — {r['location']} — {r['dates']}" + (f"  \n*{r['context']}*" if r.get("context") else "")]
        L += [f"- {b}" for b in r["bullets"]] + [""]
    L += ["## Certifications"] + [f"- {c}" for c in res["certifications"]] + ["", "## Education"]
    for ed in res["education"]:
        L += [f"**{ed['degree']}** | {ed['school']} | {ed['year']}"] + [f"- {b}" for b in ed["bullets"]]
    if res.get("expertise"):
        L += ["", "## Areas of Expertise"] + [f"**{a['label']}:** {', '.join(a['items'])}  " for a in res["expertise"]]
    return "\n".join(L) + "\n"


def to_pdf(html_path, pdf_path):
    exe = next((p for p in CHROME if p.exists()), None)
    if not exe:
        print("  (no Chrome/Edge found — skipped PDF)")
        return None
    subprocess.run([str(exe), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-sandbox",
                    f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
                   check=True, capture_output=True, timeout=120)
    try:
        from pypdf import PdfReader
        pages = len(PdfReader(str(pdf_path)).pages)
    except Exception:
        pages = "?"
    return pages


def scrub_check(text, where):
    bad = [p for p in BANNED_IN_OUTPUT if re.search(p, text, re.I)]
    if bad:
        sys.exit(f"SCRUB FAIL in {where}: {bad}")


def cmd_build(args):
    con = connect()
    tags = tag_index(con)
    _, _, prof, base, _ = load_curation()
    req, jd_meta = {}, None
    if args.jd:
        jd_text = Path(args.jd).read_text(encoding="utf-8")
        req = extract_requirements(jd_text, tags)
        jd_id = "jd_" + hashlib.md5(jd_text.encode()).hexdigest()[:10]
        jd_meta = {"id": jd_id, "file": str(args.jd)}
        con.execute("INSERT OR IGNORE INTO job_descriptions (id,title,text,origin) VALUES (?,?,?, 'cli')",
                    (jd_id, Path(args.jd).stem, jd_text))
        con.execute("DELETE FROM jd_requirements WHERE jd_id=?", (jd_id,))
        for tid, r in req.items():
            con.execute("INSERT INTO jd_requirements (jd_id,tag_id,phrase,weight) VALUES (?,?,?,?)",
                        (jd_id, tid, ", ".join(r["phrases"]), r["weight"]))
    res = assemble(con, req, base, prof["roles"], args.version, jd_meta)
    name = args.name or ("baseline_" + args.version if not args.jd else Path(args.jd).stem + "_" + args.version)
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    jdump(res, out / f"{name}.json")
    md = render_md(res)
    scrub_check(md, name)
    (out / f"{name}.md").write_text(md, encoding="utf-8")
    h = render_html(res)
    hp = out / f"{name}.html"
    hp.write_text(h, encoding="utf-8")
    pages = to_pdf(hp, out / f"{name}.pdf")
    con.execute("INSERT INTO generated_resumes (jd_id,version,json,html_path,pdf_path) VALUES (?,?,?,?,?)",
                (jd_meta["id"] if jd_meta else None, args.version, json.dumps(res), str(hp), str(out / f"{name}.pdf")))
    con.commit()
    n_b = sum(len(r["bullets"]) for r in res["roles"])
    print(f"built {name}: {len(res['roles'])} roles, {n_b} bullets, pdf pages={pages}"
          + (f", match={res['match']['score']:.0%}" if res["match"]["score"] is not None else ""))
    print(f"  {out / (name + '.pdf')}")


# ---------------------------------------------------------------- export for the artifact
def cmd_export(args):
    con = connect()
    tags = tag_index(con)
    _, ach_cur, prof, base, _ = load_curation()
    ach = load_bullets(con)
    band = json.loads(con.execute("SELECT value FROM meta WHERE key='length_band'").fetchone()[0])
    roles = []
    for r in con.execute("SELECT * FROM roles WHERE key != 'education' ORDER BY sort"):
        roles.append({"key": ROLE_ALIAS.get(r["key"], r["key"]), "sort": r["sort"], "employer": r["employer"], "title": r["title"],
                      "location": r["location"], "start": r["start"], "end": r["end"],
                      "dates": f"{fmt_date(r['start'])} – {fmt_date(r['end'])}",
                      "engagement": r["engagement"], "context": r["context_line"], "hidden": bool(r["hidden_by_default"])})
    metrics = {a["id"]: a.get("metrics", []) for a in ach_cur}
    out_ach = []
    for a in ach.values():
        out_ach.append({"id": a["id"], "role": ROLE_ALIAS.get(a["role"], a["role"]), "confidence": a["confidence"], "tags": a["tags"],
                        "metrics": metrics.get(a["id"], []),
                        "texts": [{"id": t["id"], "kind": t["kind"], "angle": t["angle"], "text": t["text"],
                                   "score_adj": t["score_adj"] or 0} for t in a["texts"]]})
    lib = {
        "schema": "rot-library/1", "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
        "identity": prof["identity"], "length_band": band, "families": jload(CUR / "taxonomy.json")["families"],
        "tags": tags, "roles": roles, "achievements": out_ach,
        "competencies": [{"text": r["text"], "tags": json.loads(r["tags"])} for r in con.execute("SELECT * FROM competencies")],
        "expertise_areas": [{"label": a["label"], "items": a["items"]} for a in prof.get("expertise_areas", [])],
        "technologies": [{"name": r["name"], "category": r["category"], "tags": json.loads(r["tags"])} for r in con.execute("SELECT * FROM technologies")],
        "domain_fluency": [r["name"] for r in con.execute("SELECT * FROM domain_fluency")],
        "certifications": [{"name": r["name"], "issuer": r["issuer"], "date": r["date"], "status": r["status"]} for r in con.execute("SELECT * FROM certifications")],
        "education": [{"school": r["school"], "degree": r["degree"], "year": r["year"], "bullet_ids": json.loads(r["bullet_ids"])} for r in con.execute("SELECT * FROM education")],
        "summaries": [{"source": r["source_id"] or "baseline", "tags": json.loads(r["tags"]), "text": r["text"]} for r in con.execute("SELECT * FROM summaries")],
        "baseline": {k: ({ROLE_ALIAS.get(rk, rk): rv for rk, rv in base.get(k).items()} if k in ("caps", "priority") else base.get(k)) for k in ("headline", "summary", "caps", "priority", "competency_count", "competency_order",
                                               "angle_map", "layout", "expertise_items_per_area", "scoring")},
    }
    s = json.dumps(lib, ensure_ascii=False, indent=1)
    scrub_check(s, "library.json")
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data/library.json").write_text(s, encoding="utf-8")
    with open(ROOT / "data/dump.sql", "w", encoding="utf-8") as f:
        for line in con.iterdump():
            f.write(line + "\n")
    print(f"exported data/library.json ({len(s)//1024} KB, {len(out_ach)} achievements, "
          f"{sum(len(a['texts']) for a in out_ach)} bullets) and data/dump.sql")


# ---------------------------------------------------------------- learning loop
def cmd_learn(args):
    """Merge a learnings file (artifact export or gate answers). Shape:
       {"runs":[{"id","company","title","jd_text","requirements":{tag:weight},"followups":[{"question","answer","tag","bullet":{...}}],
                 "feedback":[{"bullet_id","action","edited_text"}]}],
        "new_bullets":[{"achievement_id" | "new_achievement":{...}, "angle","text","tags":{},"origin"}]}"""
    data = jload(args.file) if isinstance(args.file, (str, Path)) else args.file
    con = connect()
    ensure_learning_keys(con)
    learned = jload(CUR / "learned.json", {"achievements": [], "bullets": [], "overrides": {}, "profile_overrides": {}, "baseline_overrides": {}})
    n_runs = n_fb = n_new = 0
    known = {r["id"] for r in con.execute("SELECT id FROM achievements")}
    for run in data.get("runs", []):
        jid = run.get("id") or "jd_" + hashlib.md5(run["jd_text"].encode()).hexdigest()[:10]
        # idempotent: re-syncing a run refreshes it instead of duplicating it
        con.execute("""INSERT INTO job_descriptions (id,company,title,text,origin) VALUES (?,?,?,?, 'artifact')
                       ON CONFLICT(id) DO UPDATE SET company=excluded.company, title=excluded.title, text=excluded.text""",
                    (jid, run.get("company"), run.get("title"), run.get("jd_text", "")))
        con.execute("DELETE FROM jd_requirements WHERE jd_id=?", (jid,))
        for tag, w in (run.get("requirements") or {}).items():
            con.execute("INSERT INTO jd_requirements (jd_id,tag_id,weight) SELECT ?,?,? WHERE EXISTS (SELECT 1 FROM tags WHERE id=?)",
                        (jid, tag, float(w if not isinstance(w, dict) else w.get("weight", 1)), tag))
        for f in run.get("followups", []):
            key = hashlib.md5(f"{jid}|{f['question']}|{f.get('answer') or ''}".encode()).hexdigest()
            con.execute("""INSERT OR IGNORE INTO followups (jd_id,gate,question,answer,tag_id,answered_at,ext_key)
                           VALUES (?,?,?,?,(SELECT id FROM tags WHERE id=?),datetime('now'),?)""",
                        (jid, f.get("gate", 2), f["question"], f.get("answer"), f.get("tag"), key))
        for fb in run.get("feedback", []):
            ext = fb.get("ext_id") or hashlib.md5(json.dumps(fb, sort_keys=True).encode()).hexdigest()
            cur = con.execute("INSERT OR IGNORE INTO feedback (jd_id,bullet_id,action,edited_text,ext_id) VALUES (?,?,?,?,?)",
                              (jid, fb.get("bullet_id"), fb["action"], fb.get("edited_text"), ext))
            if cur.rowcount != 1:
                continue  # already learned
            delta = {"keep": 0.3, "reject": -0.6, "drop": -0.6}.get(fb["action"], 0)
            if delta and fb.get("bullet_id"):
                con.execute("UPDATE bullets SET score_adj = COALESCE(score_adj,0) + ? WHERE id=?", (delta, fb["bullet_id"]))
            n_fb += 1
        n_runs += 1
    for nb in data.get("new_bullets", []):
        if nb.get("new_achievement"):
            a = nb["new_achievement"]
            a["role"] = ROLE_UNALIAS.get(a.get("role"), a.get("role"))
            a.setdefault("origin", nb.get("origin", "artifact"))
            a.setdefault("variants", {})
            a.setdefault("patterns", [])
            if a["id"] not in known and all(x["id"] != a["id"] for x in learned["achievements"]):
                learned["achievements"].append(a)
                n_new += 1
        elif nb.get("achievement_id") in known:
            if not any(b["text"] == nb["text"] for b in learned["bullets"]):
                learned["bullets"].append({"achievement_id": nb["achievement_id"], "angle": nb.get("angle", "learned"),
                                           "text": nb["text"], "origin": nb.get("origin", "artifact"),
                                           "status": nb.get("status", "accepted")})
                n_new += 1
    con.commit()
    jdump(learned, CUR / "learned.json")
    print(f"learned: {n_runs} runs, {n_fb} feedback events, {n_new} new bullets/achievements -> curation/learned.json")
    if not getattr(args, "quiet_next", False):
        print("next: python rot.py ingest && python rot.py export")
    return {"runs": n_runs, "feedback": n_fb, "new": n_new}


def ensure_learning_keys(con):
    """Add the dedupe keys learning needs (safe to run on any older resume.db)."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(followups)")}
    if "ext_key" not in cols:
        con.execute("ALTER TABLE followups ADD COLUMN ext_key TEXT")
    cols = {r[1] for r in con.execute("PRAGMA table_info(feedback)")}
    if "ext_id" not in cols:
        con.execute("ALTER TABLE feedback ADD COLUMN ext_id TEXT")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_followups_ext ON followups(ext_key)")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_feedback_ext ON feedback(ext_id)")
    con.commit()


# ---------------------------------------------------------------- Match Desk sync
FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'd|me|my|mine|we|our|us)\b")
SYNC_DIR = ROOT / "sync"


def _load_dump(dump, coll):
    out = []
    d = Path(dump) / coll
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc["_id"] = f.stem
        out.append(doc)
    return out


def _is_synced(doc):
    return doc.get("synced") is True or doc.get("sync_status") == "synced"


def bullet_checks(text, band):
    issues = []
    if FIRST_PERSON.search(text):
        issues.append("first person")
    if len(text) > band["hard_ceiling"]:
        issues.append(f"{len(text)} chars > {band['hard_ceiling']}")
    if len(text) < band["p10"] - 20:
        issues.append(f"{len(text)} chars, too short")
    if not re.match(r"^[A-Z]", text.strip()):
        issues.append("not capitalized")
    return issues


def cmd_sync_prepare(args):
    """Read an ArtifactData dump (jd_runs / bullet_inbox / feedback), decide what to learn, and write
    sync/pending.json. Bullets that break the Resume 1 standard are flagged needs_polish; the sync agent
    (Claude) rewrites them into sync/polished.json before sync-apply."""
    con = connect()
    band = json.loads(con.execute("SELECT value FROM meta WHERE key='length_band'").fetchone()[0])
    runs = [r for r in _load_dump(args.dump, "jd_runs") if not _is_synced(r)]
    inbox = [b for b in _load_dump(args.dump, "bullet_inbox") if not _is_synced(b)]
    feedback = [f for f in _load_dump(args.dump, "feedback") if not _is_synced(f)]
    pending_runs = [r for r in runs if r.get("sync_status") == "pending"]
    if not pending_runs and not args.all:
        print(json.dumps({"status": "nothing_pending", "unsynced_runs": len(runs)}))
        return
    known = {r["id"] for r in con.execute("SELECT id FROM achievements")}
    items, seen = {}, {}
    run_by_id = {r["_id"]: r for r in runs}
    # latest edit / drop per gate-2 achievement id
    edits, drops = {}, set()
    for f in sorted(feedback, key=lambda x: x.get("created", "")):
        aid = f.get("achievement_id") or ""
        if f.get("action") == "edit" and f.get("text"):
            edits[aid] = f["text"]
        if f.get("action") in ("drop", "reject"):
            drops.add(aid)
    def add_item(key, run_id, role, aid, text, tags, src, angle):
        role = ROLE_UNALIAS.get(role, role)
        n = norm(text)
        if n in seen:
            items[seen[n]]["source_ids"] += src
            return
        seen[n] = key
        items[key] = {"key": key, "run_id": run_id, "role": role, "achievement_id": aid if aid in known else None,
                      "text": text.strip(), "tags": [t for t in (tags or []) if t], "angle": angle,
                      "source_ids": list(src), "issues": bullet_checks(text, band)}
    # gate-2 bullets recorded on each run (index n -> page id gate2-<run>-<n>)
    for r in runs:
        # what the final resume actually showed wins; then the latest sheet edit; then the answer-derived text
        shown = {b.get("aid"): b.get("text") for role in ((r.get("final_resume") or {}).get("roles") or [])
                 for b in role.get("bullets", []) if isinstance(b, dict)}
        for n, nb in enumerate(r.get("new_bullets") or []):
            gid = f"gate2-{r['_id']}-{n}"
            if gid in drops:
                continue
            text = shown.get(gid) or edits.get(gid) or nb.get("text") or ""
            if len(text) < 15:
                continue
            src = [b["_id"] for b in inbox if b.get("run_id") == r["_id"] and norm(b.get("text", "")) == norm(nb.get("text", ""))]
            add_item(f"{r['_id']}-{n}", r["_id"], nb.get("role"), nb.get("achievement_id"), text, nb.get("tags"), src, "gate2")
    # anything else in the inbox (edits of library bullets, older runs)
    for b in inbox:
        if any(b["_id"] in it["source_ids"] for it in items.values()):
            continue
        if len(b.get("text", "")) < 15:
            continue
        add_item(f"inbox-{b['_id']}", b.get("run_id"), b.get("role"), b.get("achievement_id"), b["text"], b.get("tags"),
                 [b["_id"]], b.get("angle") or "learned")
    for it in items.values():
        it["needs_polish"] = bool(it["issues"])
    SYNC_DIR.mkdir(exist_ok=True)
    pending = {"band": band, "runs": [r["_id"] for r in runs], "pending_runs": [r["_id"] for r in pending_runs],
               "feedback": [f["_id"] for f in feedback], "inbox": [b["_id"] for b in inbox],
               "bullets": list(items.values())}
    jdump(pending, SYNC_DIR / "pending.json")
    need = [it for it in items.values() if it["needs_polish"]]
    print(json.dumps({"status": "ready", "runs": len(runs), "pending_runs": len(pending_runs), "bullets": len(items),
                      "needs_polish": len(need), "feedback": len(feedback), "file": "sync/pending.json"}, indent=1))
    for it in need:
        print(f"  POLISH {it['key']}: {', '.join(it['issues'])} :: {it['text'][:110]}")


def _model_from_run(con, r):
    """Full resume model for a run's PDF: the page's final_model when present, else rebuilt from final_resume."""
    m = r.get("final_model")
    if m:
        m = json.loads(json.dumps(m))
        for role in m.get("roles", []):
            role["bullets"] = [b["text"] if isinstance(b, dict) else b for b in role.get("bullets", [])]
        return m
    fr = r.get("final_resume")
    if not fr:
        return None
    _, _, prof, base, _ = load_curation()
    res = assemble(con, {}, base, prof["roles"], "run")
    roles = {x["key"]: x for x in res["roles"]}
    allroles = {row["key"]: dict(row) for row in con.execute("SELECT * FROM roles")}
    out_roles = []
    for rr in fr.get("roles", []):
        key = ROLE_UNALIAS.get(rr["key"], rr["key"])
        info = roles.get(key) or allroles.get(key)
        if not info:
            continue
        out_roles.append({"title": info["title"], "employer": info["employer"], "location": info.get("location"),
                          "dates": info.get("dates") or f"{fmt_date(info['start'])} – {fmt_date(info['end'])}",
                          "context": info.get("context") or info.get("engagement") or "",
                          "bullets": [b["text"] for b in rr.get("bullets", [])]})
    res.update({"headline": fr.get("headline") or res["headline"], "summary": fr.get("summary") or res["summary"],
                "competencies": fr.get("competencies") or res["competencies"], "roles": out_roles})
    return res


def cmd_sync_apply(args):
    """Apply sync/pending.json (+ sync/polished.json) -> learn -> ingest -> export -> run PDFs -> commit/push.
    Prints the artifact doc ids to mark synced."""
    pend = jload(SYNC_DIR / "pending.json")
    if not pend:
        sys.exit("run sync-prepare first")
    polished = jload(SYNC_DIR / "polished.json", {})
    runs = {r["_id"]: r for r in _load_dump(args.dump, "jd_runs")}
    feedback = {f["_id"]: f for f in _load_dump(args.dump, "feedback")}
    band = pend["band"]
    new_bullets, skipped = [], []
    known = {r["id"] for r in connect().execute("SELECT id FROM achievements")}
    for it in pend["bullets"]:
        p = polished.get(it["key"], it["text"])
        if p is None:
            skipped.append(it["key"]); continue
        if isinstance(p, dict):   # {"text", optional "achievement_id" to fold into an existing accomplishment, optional "tags"}
            if p.get("achievement_id") in known:
                it["achievement_id"] = p["achievement_id"]
            if p.get("tags"):
                it["tags"] = p["tags"]
            p = p.get("text") or ""
        text = p.strip()
        if not text:
            skipped.append(it["key"]); continue
        if bullet_checks(text, band) and it["needs_polish"] and it["key"] not in polished:
            skipped.append(it["key"]); continue   # never learn an unpolished first-person / overlong answer
        if it["achievement_id"]:
            new_bullets.append({"achievement_id": it["achievement_id"], "angle": it["angle"], "text": text, "origin": "artifact"})
        else:
            aid = "art-" + re.sub(r"[^a-z0-9-]", "", it["key"].lower())[:40]
            new_bullets.append({"new_achievement": {"id": aid, "role": it["role"], "canonical": text,
                                                    "tags": {t: 1.0 for t in it["tags"]} or {"gtm-strategy": 0.3},
                                                    "confidence": "asserted", "origin": "artifact",
                                                    "notes": f"Learned from Match Desk run {it['run_id']}", "metrics": [],
                                                    "patterns": [], "variants": {}}, "origin": "artifact"})
    learn_runs = []
    for rid in pend["runs"]:
        r = runs.get(rid)
        if not r:
            continue
        learn_runs.append({"id": rid, "company": r.get("company"), "title": r.get("title"), "jd_text": r.get("jd_text", ""),
                           "requirements": r.get("requirements") or {},
                           "followups": [{"gate": 2, "question": f["question"], "answer": f.get("answer"), "tag": f.get("tag")}
                                         for f in (r.get("followups") or []) if f.get("answer")],
                           "feedback": [{"ext_id": fid, "bullet_id": f.get("bullet_id"), "action": f.get("action"),
                                         "edited_text": f.get("text") if f.get("action") == "edit" else None}
                                        for fid, f in feedback.items() if f.get("run_id") == rid and fid in pend["feedback"]]})
    SYNC_DIR.mkdir(exist_ok=True)
    learnings = {"runs": learn_runs, "new_bullets": new_bullets}
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    jdump(learnings, SYNC_DIR / f"learnings-{stamp}.json")
    res = cmd_learn(argparse.Namespace(file=learnings, quiet_next=True))
    cmd_ingest(argparse.Namespace())
    cmd_export(argparse.Namespace())
    con = connect()
    # a PDF of every downloaded run, rendered with full typography
    pdfs = []
    (ROOT / "out" / "runs").mkdir(parents=True, exist_ok=True)
    for rid in pend["pending_runs"]:
        r = runs.get(rid)
        m = _model_from_run(con, r) if r else None
        if not m:
            continue
        slug = re.sub(r"[^A-Za-z0-9]+", "_", (r.get("company") or "posting")).strip("_")
        base = ROOT / "out" / "runs" / f"{(r.get('created') or stamp)[:10]}_{slug}_{rid}"
        jdump(m, base.with_suffix(".json"))
        hp = base.with_suffix(".html")
        hp.write_text(render_html(m), encoding="utf-8")
        to_pdf(hp, base.with_suffix(".pdf"))
        pdfs.append(str(base.with_suffix(".pdf").relative_to(ROOT)))
    cmd_profile_quiet()
    commit = None
    if not args.no_git:
        subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
        msg = (f"Sync Match Desk: {len(learn_runs)} run(s), {res['new']} new bullet(s), {res['feedback']} feedback event(s)\n\n"
               + "\n".join(f"- {b.get('text') or b['new_achievement']['canonical']}" for b in new_bullets)
               + "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n")
        c = subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=ROOT, input=msg, text=True, capture_output=True)
        if c.returncode == 0:
            commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
            gh = r"!'/c/Program Files/GitHub CLI/gh.exe' auth git-credential"
            p = subprocess.run(["git", "-c", "credential.helper=", "-c", f"credential.helper={gh}", "push"], cwd=ROOT,
                               capture_output=True, text=True)
            if p.returncode != 0:
                print("PUSH FAILED:", p.stderr.strip()[-400:])
    out = {"mark_synced": {"jd_runs": pend["runs"], "bullet_inbox": pend["inbox"], "feedback": pend["feedback"]},
           "learned": res, "skipped_unpolished": skipped, "pdfs": pdfs, "commit": commit,
           "synced_at": dt.datetime.now().astimezone().isoformat(timespec="seconds")}
    jdump(out, SYNC_DIR / "last_result.json")
    print(json.dumps(out, indent=1))


def cmd_profile_quiet():
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_profile(argparse.Namespace())


# ---------------------------------------------------------------- data profile
def cmd_profile(args):
    con = connect()
    band = json.loads(con.execute("SELECT value FROM meta WHERE key='length_band'").fetchone()[0])
    L = ["# Data Profile: resume.db", f"Generated {dt.date.today().isoformat()} by `rot.py profile`.", "", "## Overview", "",
         "| Table | Rows | Grain |", "|---|---|---|"]
    grains = {"sources": "one resume version / capture", "raw_bullets": "one bullet as written in one source",
              "achievements": "one real accomplishment", "bullets": "one bare-bone rendering of an achievement (all versions)",
              "tags": "one niche skill/keyword", "achievement_tags": "achievement × tag (one-to-many)",
              "achievement_evidence": "achievement × raw bullet", "competencies": "one competency phrase",
              "technologies": "one tool", "certifications": "one credential", "summaries": "one summary variant",
              "job_descriptions": "one JD processed", "followups": "one gate question", "feedback": "one keep/reject/edit"}
    for t, g in grains.items():
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        L.append(f"| `{t}` | {n} | {g} |")
    cur_b = con.execute("SELECT COUNT(*) FROM current_bullets").fetchone()[0]
    L += ["", f"Current (non-superseded, accepted) bullets: **{cur_b}**.", "",
          "## Bullet length vs. the Resume 1 standard", "",
          f"Resume 1 band: p10 **{band['p10']}**, median **{band['median']}**, p90 **{band['p90']}** characters (ceiling {band['hard_ceiling']}).", "",
          "| Layer | n | min | median | max | over ceiling |", "|---|---|---|---|---|---|"]
    def stats(q):
        v = sorted(r[0] for r in con.execute(q))
        if not v:
            return "0 | – | – | – | 0"
        return f"{len(v)} | {v[0]} | {v[len(v)//2]} | {v[-1]} | {sum(1 for x in v if x > band['hard_ceiling'])}"
    L.append("| Raw bullets (all sources) | " + stats("SELECT chars FROM raw_bullets") + " |")
    L.append("| Canonical bare-bone | " + stats("SELECT chars FROM current_bullets WHERE kind='canonical'") + " |")
    L.append("| Angle variants | " + stats("SELECT chars FROM current_bullets WHERE kind='variant'") + " |")
    L += ["", "## Achievements by role and confidence", "", "| Role | Achievements | verified | asserted | conflict | raw bullets evidencing |", "|---|---|---|---|---|---|"]
    for r in con.execute("""SELECT a.role_key, COUNT(*) n, SUM(a.confidence='verified') v, SUM(a.confidence='asserted') s, SUM(a.confidence='conflict') c,
                            (SELECT COUNT(DISTINCT e.raw_bullet_id) FROM achievement_evidence e JOIN achievements a2 ON a2.id=e.achievement_id WHERE a2.role_key=a.role_key) ev
                            FROM achievements a GROUP BY a.role_key ORDER BY (SELECT sort FROM roles WHERE key=a.role_key)"""):
        L.append(f"| {r['role_key']} | {r['n']} | {r['v']} | {r['s']} | {r['c']} | {r['ev']} |")
    L += ["", "## Tag coverage by family", "", "| Family | Tags | Tags used | Achievement links | Thin tags (0–1 achievements) |", "|---|---|---|---|---|"]
    for f in con.execute("SELECT code, label FROM enums WHERE domain='tag_family'"):
        tids = [r[0] for r in con.execute("SELECT id FROM tags WHERE family=?", (f["code"],))]
        cnt = {t: con.execute("SELECT COUNT(*) FROM achievement_tags WHERE tag_id=?", (t,)).fetchone()[0] for t in tids}
        thin = [t for t, n in cnt.items() if n <= 1]
        L.append(f"| {f['label']} | {len(tids)} | {sum(1 for n in cnt.values() if n)} | {sum(cnt.values())} | {', '.join(thin) or '—'} |")
    L += ["", "## Most-reused raw bullets (how often each achievement was rewritten)", "", "| Achievement | Sources | Distinct wordings |", "|---|---|---|"]
    for r in con.execute("""SELECT e.achievement_id, COUNT(DISTINCT rb.source_id) s, COUNT(DISTINCT rb.norm) w
                            FROM achievement_evidence e JOIN raw_bullets rb ON rb.id=e.raw_bullet_id
                            GROUP BY e.achievement_id ORDER BY s DESC, w DESC LIMIT 12"""):
        L.append(f"| {r['achievement_id']} | {r['s']} | {r['w']} |")
    L += ["", "## Data quality flags", ""]
    for r in con.execute("SELECT id, notes FROM achievements WHERE confidence='conflict'"):
        L.append(f"- **Conflict · {r['id']}**: {r['notes']}")
    for r in con.execute("SELECT key, date_note FROM roles WHERE date_note IS NOT NULL AND date_note != ''"):
        L.append(f"- **Dates · {r['key']}**: {r['date_note']}")
    un = con.execute("SELECT COUNT(*) FROM unassigned_raw").fetchone()[0]
    L.append(f"- Unassigned raw bullets: **{un}**.")
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/db_profile.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description="Resume Optimization Tool")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("ingest").set_defaults(fn=cmd_ingest)
    q = sp.add_parser("query"); q.add_argument("--tags"); q.add_argument("--family"); q.add_argument("--role"); q.add_argument("--limit", type=int, default=15); q.set_defaults(fn=cmd_query)
    m = sp.add_parser("match"); m.add_argument("jd"); m.set_defaults(fn=cmd_match)
    b = sp.add_parser("build"); b.add_argument("--jd"); b.add_argument("--name"); b.add_argument("--version", default="v1"); b.set_defaults(fn=cmd_build)
    sp.add_parser("export").set_defaults(fn=cmd_export)
    l = sp.add_parser("learn"); l.add_argument("file"); l.set_defaults(fn=cmd_learn)
    sp.add_parser("profile").set_defaults(fn=cmd_profile)
    s1 = sp.add_parser("sync-prepare"); s1.add_argument("--dump", default=str(ROOT / "sync" / "dump")); s1.add_argument("--all", action="store_true"); s1.set_defaults(fn=cmd_sync_prepare)
    s2 = sp.add_parser("sync-apply"); s2.add_argument("--dump", default=str(ROOT / "sync" / "dump")); s2.add_argument("--no-git", action="store_true"); s2.set_defaults(fn=cmd_sync_apply)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
