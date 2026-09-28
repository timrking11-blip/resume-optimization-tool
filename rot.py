#!/usr/bin/env python3
"""Resume Optimization Tool (ROT) · CLI

  python rot.py ingest                 rebuild resume.db from sources/raw_extract.json + curation/*.json
                                        (fails if any raw bullet is not assigned to an achievement)
  python rot.py query --tags a,b [--family f] [--role r]
  python rot.py match JD.txt           requirement map + coverage + ranked bullets for a job description
  python rot.py build [--jd JD.txt] [--name out] [--version v1]
                                        resume in the source template: Word (.docx) + PDF (Word, or headless
                                        Chrome as fallback) + HTML + Markdown + JSON under out/
  python rot.py export                 data/library.json for the web artifact (confidential names scrubbed)
                                        + data/dump.sql for readable git diffs
  python rot.py learn FILE.json        merge artifact learnings (JDs, follow-up answers, new bullets, feedback)
  python rot.py profile                data profile of the database -> reports/db_profile.md

Design: sources are never edited; curated bullets are append-only (edits supersede); learning
tables survive re-ingest; learned bullets live in curation/learned.json so the DB is reproducible.
Every resume renders in the source template (templates/docx_template.json, built by make_template.py):
tagline (Section A) and expertise line (Section B) instead of a summary paragraph, then Education,
Experience, Certifications, Business Consulting Engagements (Section C) and Core Competencies (Section D).
"""
import argparse, datetime as dt, hashlib, html, io, json, re, sqlite3, subprocess, sys, zipfile
from pathlib import Path

import claims as CL   # the evidence layer: tiers 1 and 2

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DB = ROOT / "resume.db"
CUR = ROOT / "curation"
CHROME = [Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
          Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")]
TEMPLATE = ROOT / "templates" / "docx_template.json"
WORD_PDF = ROOT / "tools" / "docx2pdf.ps1"
CURATED_TABLES = ["claim_evidence", "claim_relations", "engagement_achievements", "achievement_evidence", "achievement_tags",
                  "raw_bullets", "achievements", "tags", "competencies", "technologies", "domain_fluency", "certifications", "education",
                  "summaries", "tagline_phrases", "core_competencies", "engagements", "roles", "sources", "meta", "enums"]
# persistent across ingests (never deleted): evidence, claims, claim_history, claim_confidence_history, bullets, learning tables
LONGFORM_CEILING = 340                              # Section C bullets (template max); the R1 band governs everything else
SCHEMA_ADDS = {                                     # columns added after the first release (ALTER on older resume.db files)
    "competencies": [("sort", "INTEGER"), ("origin", "TEXT"), ("claim_id", "TEXT")],
    "technologies": [("sort", "INTEGER"), ("origin", "TEXT"), ("claim_id", "TEXT")],
    "certifications": [("sort", "INTEGER"), ("hidden_by_default", "INTEGER DEFAULT 0"), ("claim_id", "TEXT")],
    "education": [("date_display", "TEXT"), ("claim_id", "TEXT")],
    "followups": [("section", "TEXT"), ("engagement_key", "TEXT"), ("evidence_id", "TEXT")],
    "roles": [("claim_id", "TEXT")],
    "tagline_phrases": [("claim_id", "TEXT")],
    "core_competencies": [("claim_id", "TEXT")],
    "engagements": [("claim_id", "TEXT")],
    "sources": [("authored_at", "TEXT"), ("source_type", "TEXT")],
    "feedback": [("event", "TEXT")],
    "generated_resumes": [("trace", "TEXT")],
    "bullets": [("claim_ids", "TEXT")],
}
TIERS = {"evidence": 1, "sources": 1, "raw_bullets": 1,
         "claims": 2, "claim_evidence": 2, "claim_relations": 2, "claim_confidence_history": 2, "achievements": 2, "achievement_tags": 2,
         "achievement_evidence": 2, "bullets": 2, "tags": 2, "competencies": 2, "technologies": 2, "certifications": 2, "education": 2,
         "tagline_phrases": 2, "core_competencies": 2, "engagements": 2, "engagement_achievements": 2, "roles": 2, "summaries": 2,
         "job_descriptions": 2, "jd_requirements": 2,
         "generation_events": 3, "prompt_versions": 3, "generated_resumes": 3,
         "feedback": 4, "outcomes": 4, "followups": 1}
TIER_LABELS = {1: "Evidence: what actually happened", 2: "Derived knowledge: what the system infers",
               3: "Generation: what was written", 4: "Feedback: what happened afterwards"}
BANNED_IN_OUTPUT = [r"liminal", r"therapy companion", r"\bkamal\b", r"co-up\b", r"sonnett"]
ROLE_ALIAS = {"liminal": "hc_ai_strategy"}          # internal role key -> exported key (confidential)
ROLE_UNALIAS = {v: k for k, v in ROLE_ALIAS.items()}
def alias_claim(cid):        # claim ids that name the confidential role key never leave the repo
    return str(cid).replace("role:liminal", "role:" + ROLE_ALIAS["liminal"])
def unalias_claim(cid):
    return str(cid).replace("role:" + ROLE_ALIAS["liminal"], "role:liminal")
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
    cj = CL.load_claims_json()
    if cj.get("subjects"):
        prof.update(CL.projection_from_claims(cj))   # roles, education, certifications, technologies, A/B/D items, engagements
    prof["_claims"] = cj
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
        if k != "roles" and not k.startswith("_"):
            prof[k] = v
    # template-section items learned from Match Desk answers (Sections A, B, C and Technologies)
    def merge(dst, items, key, sort_from):
        seen = {norm(x[key]) for x in dst}
        for n, it in enumerate(items):
            if it.get("status", "accepted") == "accepted" and norm(it[key]) not in seen:
                dst.append({"sort": sort_from + n, **it})
                seen.add(norm(it[key]))
    merge(prof.setdefault("tagline_phrases", []), learned.get("tagline_phrases", []), "text", 100)
    merge(prof["technologies"], learned.get("technologies", []), "name", 100)
    merge(prof["competencies"], learned.get("competencies", []), "text", 100)
    engs = {e["key"]: e for e in prof.setdefault("engagements", [])}
    for key, upd in learned.get("engagement_updates", {}).items():
        if key not in engs:
            engs[key] = {"key": key, "role": "liminal", "client": upd.get("client") or key, "achievements": [], "confidential": True}
            prof["engagements"].append(engs[key])
        engs[key].update({k: v for k, v in upd.items() if not k.startswith("_")})
    for a in learned.get("achievements", []):
        e = engs.get(a.get("engagement"))
        if e and a["id"] not in e["achievements"]:
            e["achievements"].append(a["id"])
    areas = {a["label"]: a for a in prof.setdefault("core_competencies", [])}
    for it in learned.get("core_competencies", []):
        if it.get("status", "accepted") != "accepted":
            continue
        area = areas.get(it.get("area")) or next(iter(areas.values()), None)
        if area is not None and norm(it["text"]) not in {norm(x["text"]) for x in area["items"]}:
            area["items"].append({"text": it["text"], "tags": it.get("tags", [])})
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


def migrate(con):
    """Bring an older resume.db up to the current schema: new tables come from schema.sql, new columns from here."""
    con.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
    for table, cols in SCHEMA_ADDS.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for name, typ in cols:
            if have and name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    con.commit()


# ---------------------------------------------------------------- ingest
def cmd_ingest(args):
    raw = jload(ROOT / "sources/raw_extract.json")
    if raw is None:
        sys.exit("run: python extract.py  first")
    tax, ach, prof, base, learned = load_curation()
    con = connect()
    migrate(con)
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
    for i, (t, label) in enumerate(CL.TIER_LABELS.items()):
        cur.execute("INSERT INTO enums VALUES ('tier',?,?,?)", (str(t), label, i))
    for domain, codes in (("source_type", CL.SOURCE_TYPES), ("relation", CL.RELATIONS), ("feedback_event", CL.FEEDBACK_EVENTS), ("response", CL.RESPONSES)):
        for i, code in enumerate(codes):
            cur.execute("INSERT INTO enums VALUES (?,?,?,?)", (domain, code, code, i))

    # sources, roles
    for s in raw:
        cur.execute("INSERT INTO sources (id,file,md5,target_role,kind,headline,authored_at,source_type) VALUES (?,?,?,?,?,?,?,?)",
                    (s["id"], s["file"], s["md5"], s["target_role"], s["kind"], s.get("headline"), s.get("authored_at"), CL.source_type_for(s)))
    for r in prof["roles"]:
        cur.execute("""INSERT INTO roles (key,sort,employer,employer_private,confidential,title,title_variants,location,
                       start,end,engagement,hidden_by_default,date_note,context_line,claim_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (r["key"], r["order"], r["employer"], r.get("employer_private"), int(r.get("confidential", False)),
                     r["title"], json.dumps(r.get("title_variants", [])), r.get("location"), r.get("start"), r.get("end"),
                     r.get("engagement"), int(r.get("hidden_by_default", False)), r.get("date_note"), r.get("context_line"), r.get("claim_id")))
    cur.execute("INSERT OR IGNORE INTO roles (key,sort,employer,title) VALUES ('education',99,'Education','Education')")

    # tags
    for tid, t in tax["tags"].items():
        cur.execute("INSERT INTO tags VALUES (?,?,?,?)", (tid, t["family"], t["label"], json.dumps(t["synonyms"])))

    # raw bullets
    raw_rows, bullet_ev = [], {}
    for s in raw:
        for n, b in enumerate(s["bullets"]):
            cur.execute("INSERT INTO raw_bullets (source_id,role_key,section,text,chars,norm) VALUES (?,?,?,?,?,?)",
                        (s["id"], b["role"], b["section"], b["text"], len(b["text"]), norm(b["text"])))
            raw_rows.append((cur.lastrowid, b["role"], b["text"], s["id"]))
            bullet_ev[cur.lastrowid] = f"ev:{s['id']}:b{n}"      # the raw bullet's evidence row

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
    for i, c in enumerate(prof["competencies"]):
        cur.execute("INSERT OR IGNORE INTO competencies (text,tags,sort,origin,claim_id) VALUES (?,?,?,?,?)",
                    (c["text"], json.dumps(c["tags"]), c.get("sort", i + 1), c.get("origin", "curated"), c.get("claim_id")))
    cur.execute("DELETE FROM expertise_areas")
    for ai, area in enumerate(prof.get("expertise_areas", [])):
        for ii, it in enumerate(area["items"]):
            cur.execute("INSERT INTO expertise_areas (area,area_sort,text,tags,sort) VALUES (?,?,?,?,?)",
                        (area["label"], ai, it["text"], json.dumps(it["tags"]), ii))
    for i, t in enumerate(prof["technologies"]):
        cur.execute("INSERT OR IGNORE INTO technologies (name,category,tags,sort,origin,claim_id) VALUES (?,?,?,?,?,?)",
                    (t["name"], t.get("category"), json.dumps(t.get("tags", [])), t.get("sort", i + 1), t.get("origin", "curated"), t.get("claim_id")))
    for d in prof["domain_fluency"]:
        cur.execute("INSERT INTO domain_fluency (name,tags) VALUES (?,?)", (d["name"], json.dumps(d["tags"])))
    for i, c in enumerate(prof["certifications"]):
        cur.execute("""INSERT INTO certifications (name,issuer,date,credential_id,status,source,tags,sort,hidden_by_default,claim_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (c["name"], c["issuer"], c.get("date"), c.get("credential_id"), c.get("status"), c.get("source"),
                     json.dumps(c.get("tags", [])), c.get("sort", i + 1), int(c.get("hidden_by_default", False)), c.get("claim_id")))
    for e in prof["education"]:
        cur.execute("""INSERT INTO education (school,degree,degree_variants,location,year,date_note,bullet_ids,date_display,claim_id)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (e["school"], e["degree"], json.dumps(e.get("degree_variants", [])), e.get("location"), e["year"], e.get("date_note"),
                     json.dumps(e.get("bullet_ids", [])), e.get("date_display") or e["year"], e.get("claim_id")))
    if base.get("summary"):
        cur.execute("INSERT INTO summaries (source_id,tags,text,origin) VALUES (NULL,?,?, 'baseline')",
                    (json.dumps(["gtm-strategy", "new-business", "full-cycle-sales"]), base["summary"]))
    for s in prof.get("summaries", []):
        cur.execute("INSERT INTO summaries (source_id,tags,text) VALUES (?,?,?)", (s["source"], json.dumps(s["tags"]), s["text"]))

    # template sections: A = tagline phrases, C = consulting engagements, D = core competency areas
    for i, t in enumerate(prof.get("tagline_phrases", [])):
        cur.execute("INSERT OR IGNORE INTO tagline_phrases (text,tags,sort,status,origin,claim_id) VALUES (?,?,?,?,?,?)",
                    (t["text"], json.dumps(t.get("tags", [])), t.get("sort", i + 1), t.get("status", "accepted"), t.get("origin", "template"), t.get("claim_id")))
    for ai, area in enumerate(prof.get("core_competencies", [])):
        for ii, it in enumerate(area["items"]):
            cur.execute("INSERT INTO core_competencies (area,area_sort,text,tags,sort,claim_id) VALUES (?,?,?,?,?,?)",
                        (area["label"], ai, it["text"], json.dumps(it.get("tags", [])), ii, it.get("claim_id")))
    for ei, e in enumerate(prof.get("engagements", [])):
        cur.execute("""INSERT INTO engagements (key,role_key,client,location,start,end,commitment,subtitle,sort,confidential,needs_details,notes,claim_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (e["key"], e.get("role", "liminal"), e["client"], e.get("location"), e.get("start"), e.get("end"), e.get("commitment"),
                     e.get("subtitle"), ei, int(e.get("confidential", True)), int(e.get("needs_details", False)), e.get("notes"), e.get("claim_id")))
        for si, aid in enumerate(e.get("achievements", [])):
            if aid not in ach_ids:
                errors.append(f"engagement {e['key']}: unknown achievement {aid}")
                continue
            cur.execute("INSERT OR IGNORE INTO engagement_achievements VALUES (?,?,?)", (e["key"], aid, si))

    # evidence layer: tiers 1 and 2 (append-only evidence, claims with confidence, relations)
    atags = [(a["id"], t, w) for a in ach for t, w in a.get("tags", {}).items() if t in known_tags]
    layer = CL.ingest_layer(con, cur, raw, ach, learned, prof.get("_claims") or {"subjects": []}, CL.load_config(), bullet_ev, prof, atags)
    errors += layer["errors"]

    # length band from Resume 1 (the bullet standard); Section C long-form bullets get their own band
    r1 = sorted(len(b["text"]) for b in raw[0]["bullets"])
    q = lambda p: r1[min(len(r1) - 1, int(round(p * (len(r1) - 1))))]
    band = {"source": raw[0]["id"], "n": len(r1), "min": r1[0], "p10": q(.1), "p25": q(.25), "median": q(.5),
            "p75": q(.75), "p90": q(.9), "max": r1[-1], "hard_ceiling": 170}
    cur.execute("INSERT INTO meta VALUES ('length_band', ?)", (json.dumps(band),))
    lf = sorted(len(b["text"]) for s in raw for b in s["bullets"] if b.get("section") == "consulting")
    lband = {"source": "Section C of the source template", "n": len(lf), "min": lf[0] if lf else 170,
             "median": lf[len(lf) // 2] if lf else 230, "max": lf[-1] if lf else LONGFORM_CEILING,
             "hard_ceiling": max([LONGFORM_CEILING] + lf)}
    cur.execute("INSERT INTO meta VALUES ('longform_band', ?)", (json.dumps(lband),))
    cur.execute("INSERT INTO meta VALUES ('ingested_at', ?)", (dt.datetime.now().isoformat(timespec="seconds"),))
    con.commit()
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    for r in fk:
        errors.append(f"foreign key: {tuple(r)}")

    # ---- report
    n_raw = len(raw_rows)
    n_unique = cur.execute("SELECT COUNT(DISTINCT role_key||norm) FROM raw_bullets").fetchone()[0]
    print(f"sources: {len(raw)}   raw bullets: {n_raw} ({n_unique} unique)   achievements: {len(ach)}   tags: {len(tax['tags'])}")
    print(f"bullets: +{added} new, {superseded} superseded   length band (R1): p10={band['p10']} median={band['median']} p90={band['p90']} ceiling={band['hard_ceiling']}"
          f"   Section C band: {lband['min']}–{lband['max']} (ceiling {lband['hard_ceiling']})")
    long_ = cur.execute("""SELECT achievement_id, kind, angle, chars FROM current_bullets
                           WHERE (COALESCE(angle,'') != 'longform' AND (chars > ? OR chars < ?)) OR (angle = 'longform' AND chars > ?)""",
                        (band["hard_ceiling"], band["p10"] - 20, lband["hard_ceiling"])).fetchall()
    for r in long_:
        print(f"  LENGTH  {r['achievement_id']} {r['kind']} {r['angle'] or ''}: {r['chars']} chars")
    print(f"evidence layer: {layer['n_evidence']} evidence rows (+{layer['n_new_evidence']} new) · {layer['n_claims']} claims · "
          f"{layer['n_relations']} relations · {layer['changed']} claims changed · {layer['n_disputed']} disputed · {layer['n_low']} below print threshold")
    for cid, val, basis in layer["disputed"]:
        print(f"  DISPUTED {cid} = {val!r}: {basis}  (prints the stronger value with this warning; numbers held back)")
    for cid, val, conf in layer["low"]:
        print(f"  LOW      {cid} = {val!r}: confidence {conf}")
    n_eng = cur.execute("SELECT COUNT(*) FROM engagements").fetchone()[0]
    print(f"template sections: {cur.execute('SELECT COUNT(*) FROM tagline_phrases').fetchone()[0]} tagline phrases · "
          f"{cur.execute('SELECT COUNT(*) FROM competencies').fetchone()[0]} expertise items · "
          f"{cur.execute('SELECT COUNT(*) FROM technologies').fetchone()[0]} technologies · {n_eng} engagements "
          f"({cur.execute('SELECT COUNT(*) FROM engagements WHERE needs_details=1').fetchone()[0]} awaiting details) · "
          f"{cur.execute('SELECT COUNT(DISTINCT area) FROM core_competencies').fetchone()[0]} core competency areas")
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


def select(con, req, base, tags, caps=None, exclude=()):
    ach = load_bullets(con)
    caps = caps or base["caps"]
    prio = base["priority"]
    by_role = {}
    for a in ach.values():
        if a["role"] == "education" or a["id"] in exclude:
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
    _, _, prof, base, _ = load_curation()
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
    m = assemble(con, req, base, prof, "match")
    print("\nSECTION A · TAGLINE\n  " + " | ".join(m["tagline"]))
    print("SECTION B · EXPERTISE\n  " + " • ".join(m["expertise"]))
    print("\nSELECTED BULLETS")
    for role in sorted(chosen, key=lambda k: next(iter(chosen[k]))[1]["role_sort"]):
        print(f"  [{role}]")
        for s, a, why, t in chosen[role]:
            print(f"    {s:5.2f}  {t['text']}")
    for e in m["engagements"]:
        print(f"  [Section C · {e['client']}]")
        for b in e["bullets"]:
            print(f"           {b}")


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


# ---------------------------------------------------------------- build / render (source template)
def rank_items(items, req, key="tags"):
    """JD-ranked and stable: requirement weight over each item's tags; the stored order breaks ties."""
    if not req:
        return list(items)
    tags_of = lambda it: json.loads(it[key]) if isinstance(it[key], str) else (it[key] or [])
    sc = lambda it: sum(req.get(t, {}).get("weight", 0) for t in tags_of(it))
    return [it for _, _, it in sorted(((-sc(it), i, it) for i, it in enumerate(items)), key=lambda x: (x[0], x[1]))]


def text_for(a, angle=None):
    """An achievement's current text for an angle ('longform' = Section C wording), else its canonical."""
    if angle:
        t = next((t for t in a["texts"] if t["kind"] == "learned" and (t["angle"] or "") == angle), None) or \
            next((t for t in a["texts"] if t["kind"] == "variant" and (t["angle"] or "") == angle), None)
        if t:
            return t
    return next((t for t in a["texts"] if t["kind"] == "canonical"), a["texts"][0])


def assemble(con, req, base, prof, version, jd_meta=None):
    """Resume model v2 (schema rot-resume/2): every section of the source template, JD-ranked when req is given."""
    tags = tag_index(con)
    ach_all = load_bullets(con)
    sc = base.get("scoring", {})
    engs = [dict(r) for r in con.execute("SELECT * FROM engagements WHERE needs_details = 0 ORDER BY sort")]
    members = {e["key"]: [r[0] for r in con.execute("SELECT achievement_id FROM engagement_achievements WHERE engagement_key=? "
                                                     "ORDER BY sort", (e["key"],)) if r[0] in ach_all] for e in engs}
    # a disputed number never prints: the achievement waits until the conflict is resolved
    held = {}
    for r in con.execute("SELECT id, subject, kind FROM claims WHERE status='disputed' AND kind IN ('metric','achievement')"):
        aid = (r["subject"] if r["kind"] == "metric" else r["id"]).split(":", 1)[1]
        held.setdefault(aid, []).append(r["id"])
    for aid, ids in held.items():
        print(f"  HELD BACK {aid}: disputed {', '.join(ids)} (resolve it in curation/claims.json or the achievement's resolutions)")
    members = {k: [aid for aid in v if aid not in held] for k, v in members.items()}
    # short under the role, long in Section C; a bullet with no long form prints once, in Section C
    exclude = set(held) | {aid for ids in members.values() for aid in ids if (text_for(ach_all[aid], "longform")["angle"] or "") != "longform"}
    chosen = select(con, req, base, tags, exclude=exclude)
    roles = {r["key"]: dict(r) for r in con.execute("SELECT * FROM roles")}

    metric_ids = {}
    for r in con.execute("SELECT id, subject FROM claims WHERE kind='metric' AND status != 'retired'"):
        metric_ids.setdefault(r["subject"], []).append(r["id"])
    trace = {}
    def ach_claims(aid):
        return [f"ach:{aid}"] + metric_ids.get(f"ach:{aid}", [])
    # Section A: tagline phrases
    phrases = [dict(r) for r in con.execute("SELECT * FROM tagline_phrases WHERE status='accepted' ORDER BY sort, id")]
    ranked_phrases = rank_items(phrases, req)[: base.get("tagline_count", 7)]
    tagline = [p["text"] for p in ranked_phrases]
    trace["tagline"] = [p["claim_id"] for p in ranked_phrases if p.get("claim_id")]
    # Section B: areas-of-expertise line (template order, JD-relevant items first when there is a JD)
    order, n = base["competency_order"], base["competency_count"]
    pos = {t: i for i, t in enumerate(order)}
    comps = sorted((dict(r) for r in con.execute("SELECT * FROM competencies")), key=lambda c: (pos.get(c["text"], 1000), c["sort"] or 0))
    if req:
        weight = lambda c: sum(req.get(t, {}).get("weight", 0) for t in json.loads(c["tags"]))
        expertise = [c["text"] for c in rank_items(comps, req) if weight(c) > 0][:n]
        expertise += [t for t in order if t not in expertise][: max(0, n - len(expertise))]
    else:
        expertise = order[:n]
    comp_claim = {c["text"]: c.get("claim_id") for c in comps}
    trace["expertise"] = [comp_claim[t] for t in expertise if comp_claim.get(t)]
    tech_rows = rank_items([dict(r) for r in con.execute("SELECT * FROM technologies ORDER BY sort, id")], req)
    technologies = [t["name"] for t in tech_rows]
    trace["technologies"] = [t["claim_id"] for t in tech_rows if t.get("claim_id")]
    education = []
    for n_e, e in enumerate(con.execute("SELECT * FROM education ORDER BY id")):
        bl = [text_for(ach_all[b])["text"] for b in json.loads(e["bullet_ids"] or "[]") if b in ach_all]
        education.append({"school": e["school"], "degree_line": f"{e['degree']} | {e['date_display'] or e['year']}", "bullets": bl})
        sid = (e["claim_id"] or "edu:umaine:degree").rsplit(":", 1)[0]
        trace[f"education:{n_e}"] = [f"{sid}:school", f"{sid}:degree", f"{sid}:date"]

    out_roles, printed = [], set()
    for key in sorted(chosen, key=lambda k: roles[k]["sort"]):
        r, items = roles[key], chosen[key]
        akey = ROLE_ALIAS.get(key, key)
        out_roles.append({
            "key": akey, "title": r["title"], "employer": r["employer"], "location": r["location"],
            "dates": f"{fmt_date(r['start'])} – {fmt_date(r['end'])}",
            "context": " · ".join(x for x in (r["location"], r["context_line"]) if x),
            "bullets": [t["text"] for s, a, why, t in items],
            "bullet_ids": [t["id"] for s, a, why, t in items],
            "achievement_ids": [a["id"] for s, a, why, t in items],
            "claim_ids": [ach_claims(a["id"]) for s, a, why, t in items],
        })
        trace[f"role:{akey}"] = [f"role:{akey}:{f}" for f in ("title", "employer", "start", "end", "context")]
        for n_b, (s_, a, why, t) in enumerate(items):
            trace[f"role:{akey}:{n_b}"] = ach_claims(a["id"])
        printed |= {norm(t["text"]) for s, a, why, t in items}
    certs = []
    for n_c, c in enumerate(con.execute("SELECT * FROM certifications WHERE COALESCE(hidden_by_default,0)=0 ORDER BY sort, id")):
        certs.append({"name": c["name"], "issuer": c["issuer"], "note": "In Progress" if c["status"] else None})
        sid = (c["claim_id"] or "").rsplit(":", 1)[0]
        trace[f"cert:{n_c}"] = [f"{sid}:name", f"{sid}:issuer"] + ([f"{sid}:status"] if c["status"] else []) if sid else []

    # Section C: consulting engagements, long-form bullets, never an identical sentence twice
    engagements = []
    for e in engs:
        ids = members[e["key"]]
        scored = []
        for rank, aid in enumerate(ids):
            a = ach_all[aid]
            s = 0.0
            if req:
                s = score_achievement(a, req, tags)[0] + sc.get("priority_bonus", 1.5) * max(0.0, 1 - rank / max(len(ids), 1)) \
                    + (sc.get("metric_bonus", 0.5) if a.get("has_metrics") else 0.0)
            scored.append((s, -rank, a))
        if req:
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        cap = base.get("engagement_caps", {}).get(e["key"], 5)
        picks = []
        for s, _, a in scored:
            t = text_for(a, "longform")
            if norm(t["text"]) in printed:
                continue
            picks.append((a, t))
            printed.add(norm(t["text"]))
            if len(picks) >= cap:
                break
        if picks:
            engagements.append({
                "key": e["key"], "client": e["client"], "location": e["location"],
                "dates": f"{fmt_date(e['start'])} – {fmt_date(e['end'])}" if e["start"] else None,
                "commitment": e["commitment"], "subtitle": e["subtitle"],
                "bullets": [t["text"] for a, t in picks], "bullet_ids": [t["id"] for a, t in picks],
                "achievement_ids": [a["id"] for a, t in picks], "claim_ids": [ach_claims(a["id"]) for a, t in picks]})
            trace[f"eng:{e['key']}"] = [f"eng:{e['key']}:{f}" for f in ("client", "location", "start", "end", "commitment", "subtitle")]
            for n_b, (a, t) in enumerate(picks):
                trace[f"eng:{e['key']}:{n_b}"] = ach_claims(a["id"])
    # Section D: categorized core competencies (area order fixed)
    rows = [dict(r) for r in con.execute("SELECT * FROM core_competencies ORDER BY area_sort, sort")]
    core = []
    for area in dict.fromkeys(r["area"] for r in rows):
        ranked = rank_items([x for x in rows if x["area"] == area], req)
        core.append({"label": area, "items": [r["text"] for r in ranked]})
        trace[f"core:{area}"] = [r["claim_id"] for r in ranked if r.get("claim_id")]

    ident = prof["identity"]
    cov = coverage(req, chosen) if req else {}
    total = sum(r["weight"] for r in req.values()) or 1
    return {
        "schema": "rot-resume/2", "template": base.get("template", "source-2026-09"), "version": version,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"), "jd": jd_meta,
        "identity": {"name": ident["name"], "location": ident["location"], "phone": ident["phone"], "email": ident["email"],
                     "links": ident.get("links") or [{"label": "LinkedIn Profile", "url": "https://" + ident["linkedin"]}]},
        "tagline": tagline, "expertise": expertise, "technologies": technologies, "education": education,
        "roles": out_roles, "certifications": certs, "engagements": engagements, "core_competencies": core,
        "summary": None, "trace": trace,
        "match": {"score": round(sum(r["weight"] * min(cov.get(t, 0), 1.0) for t, r in req.items()) / total, 3) if req else None,
                  "requirements": {t: {"label": tags[t]["label"], **r, "coverage": cov.get(t, 0)} for t, r in req.items()}},
    }


def _alias_settings(s):
    """Edition settings for the bank: role keys aliased like everything else exported, notes dropped."""
    s = json.loads(json.dumps(s))
    s.pop("_about", None)
    for k in ("fallback_role", "default_engagement_role"):
        if s.get(k):
            s[k] = ROLE_ALIAS.get(s[k], s[k])
    ex = (s.get("prompts") or {}).get("bullet_example") or {}
    if isinstance(ex.get("place"), str) and ex["place"].startswith("r:"):
        ex["place"] = "r:" + ROLE_ALIAS.get(ex["place"][2:], ex["place"][2:])
    return s


def load_template():
    t = jload(TEMPLATE)
    if not t:
        sys.exit("templates/docx_template.json is missing: run  python make_template.py")
    return t


def btext(b):
    return b["text"] if isinstance(b, dict) else b


LAYOUTS = ROOT / "core" / "layouts"
_SOURCE_LAYOUT = None


def load_layout(name="source-2026-09"):
    """A layout (rot-layout/1): section order, headings, joins and labels; see core/layouts/."""
    return jload(LAYOUTS / f"{name}.json")


def template_layout(tpl=None):
    """The layout a template JSON carries, else the source template's."""
    return (tpl or load_template()).get("layout") or load_layout()


def _layout_parts(layout):
    global _SOURCE_LAYOUT
    if _SOURCE_LAYOUT is None:
        _SOURCE_LAYOUT = load_layout()
    ly = layout or _SOURCE_LAYOUT
    return (ly.get("sections") or _SOURCE_LAYOUT["sections"], {**_SOURCE_LAYOUT["joins"], **(ly.get("joins") or {})},
            {**_SOURCE_LAYOUT["labels"], **(ly.get("labels") or {})})


def _line_blocks(m):
    return {"summary": bool(m.get("summary")), "tagline": bool(m.get("tagline")), "expertise": bool(m.get("expertise")),
            "technologies": bool(m.get("technologies"))}


def model_paragraphs(m, layout=None):
    """The resume as (paragraph kind, runs) in the layout's order; a run is (style, text), ("tab",) or ("link", label, url).
    The Match Desk's docParagraphs() mirrors this exactly, so the page and the CLI build the same document."""
    sections, J, LB = _layout_parts(layout)
    i, P = m["identity"], []
    heading = lambda t: P.append(("heading", [("heading", t)]))
    for sec in sections:
        kind = sec["kind"]
        if kind == "header":
            P.append(("name", [("name", i["name"])]))
            cparts = " | ".join(x for x in (i.get("location"), i.get("phone"), i.get("email")) if x)   # a blank field prints nothing, not an empty slot
            contact = [("contact", cparts + (" | " if i.get("links") else ""))]
            for k, ln in enumerate(i.get("links") or []):
                if k:
                    contact.append(("contact", " | "))
                contact.append(("link", ln["label"], ln["url"]))
            P.append(("contact", contact))
        elif kind == "lines":
            has, blocks = _line_blocks(m), sec.get("blocks") or []
            if not sec.get("always") and not any(has[b] for b in blocks):
                continue
            heading(sec["heading"])
            for b in blocks:
                if b == "summary" and has["summary"]:
                    P.append(("summary", [("plain", m["summary"])]))
                elif b == "tagline" and has["tagline"]:
                    P.append(("tagline", [("plain", J["tagline"].join(m["tagline"]))]))
                elif b == "expertise" and has["expertise"]:
                    P.append(("expertise", [("plain", J["expertise"].join(m["expertise"]))]))
                elif b == "technologies" and has["technologies"]:
                    P.append(("tech_label", [("bold_u", LB["technologies"]), ("bold", ":")]))
                    P.append(("tech_line", [("plain", J["technologies"].join(m["technologies"]))]))
        elif kind == "education":
            if not m.get("education"):
                continue
            heading(sec["heading"])
            for e in m["education"]:
                P.append(("school", [("bold", e["school"])]))
                P.append(("degree", [("degree", e["degree_line"])]))
                for b in e.get("bullets") or []:
                    P.append(("bullet", [("plain", btext(b))]))
        elif kind == "experience":
            heading(sec["heading"])
            for r in m["roles"]:
                P.append(("role_header", [("bold", f"{r['title']} | {r['employer']} |"), ("tab",), ("plain", r["dates"])]))
                if r.get("context"):
                    P.append(("role_context", [("context", r["context"])]))
                n = len(r["bullets"])
                for k, b in enumerate(r["bullets"]):
                    P.append(("bullet_last" if k == n - 1 else "bullet", [("plain", btext(b))]))
        elif kind == "certifications":
            if not m.get("certifications"):
                continue
            heading(sec["heading"])
            for c in m["certifications"]:
                runs = [("bold", c["name"]), ("plain", f" — {c['issuer']}")]
                if c.get("note"):
                    runs.append(("cert_note", f" ({c['note']})"))
                P.append(("cert", runs))
        elif kind == "engagements":
            if not m.get("engagements"):
                continue
            heading(sec["heading"])
            for e in m["engagements"]:
                runs = [("bold", e["client"])]
                if e.get("location"):
                    runs.append(("bold_italic", f" | {e['location']} |"))
                if e.get("dates"):
                    runs.append(("bold", (" " if e.get("location") else " | ") + e["dates"]))
                if e.get("commitment"):
                    runs.append(("plain", f" ({e['commitment']})"))
                P.append(("eng_header", runs))
                if e.get("subtitle"):
                    P.append(("eng_subtitle", [("italic", e["subtitle"])]))
                n = len(e["bullets"])
                for k, b in enumerate(e["bullets"]):
                    P.append(("eng_bullet_last" if k == n - 1 else "eng_bullet", [("plain", btext(b))]))
        elif kind == "core_competencies":
            if not m.get("core_competencies"):
                continue
            heading(sec["heading"])
            for a in m["core_competencies"]:
                P.append(("comp", [("bold", a["label"] + ": "), ("plain", J["core"].join(a["items"]))]))
    return P


def xml_esc(s):
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(s))
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def rpr_xml(style, tpl):
    f = tpl["styles"][style]
    x = ['<w:rStyle w:val="Hyperlink"/>'] if f.get("link") else []
    x.append('<w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi" w:cstheme="majorHAnsi"/>')
    if f.get("b"):
        x.append("<w:b/><w:bCs/>")
    if f.get("i"):
        x.append("<w:i/><w:iCs/>")
    if f.get("color"):
        x.append(f'<w:color w:val="{f["color"]}"/>')
    if f.get("sz"):
        x.append(f'<w:sz w:val="{f["sz"]}"/><w:szCs w:val="{f["sz"]}"/>')
    if f.get("u"):
        x.append('<w:u w:val="single"/>')
    return "<w:rPr>" + "".join(x) + "</w:rPr>"


def docx_bytes(m, tpl=None):
    """A Word document built from the source template's own styles, numbering and theme."""
    tpl = tpl or load_template()
    links, body = [], []
    for kind, runs in model_paragraphs(m, tpl.get("layout")):
        out = []
        for r in runs:
            if r[0] == "tab":
                out.append(f"<w:r>{rpr_xml('plain', tpl)}<w:tab/></w:r>")
            elif r[0] == "link":
                rid = f"rId{100 + len(links)}"
                links.append((rid, r[2]))
                out.append(f'<w:hyperlink r:id="{rid}" w:history="1"><w:r>{rpr_xml("link", tpl)}'
                           f'<w:t xml:space="preserve">{xml_esc(r[1])}</w:t></w:r></w:hyperlink>')
            else:
                out.append(f'<w:r>{rpr_xml(r[0], tpl)}<w:t xml:space="preserve">{xml_esc(r[1])}</w:t></w:r>')
        body.append(f"<w:p>{tpl['ppr'][kind]}{''.join(out)}</w:p>")
    document = tpl["doc_open"] + "".join(body) + tpl["doc_close"]
    rels = (tpl["rels_open"] + "".join(tpl["rels_base"])
            + "".join(tpl["rel_hyperlink"].replace("{id}", rid).replace("{url}", xml_esc(url)) for rid, url in links)
            + tpl["rels_close"])
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    name = m["identity"]["name"]
    core = tpl["core_xml"].replace("{title}", xml_esc(f"{name} — Resume")).replace("{author}", xml_esc(name)).replace("{stamp}", stamp)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tpl["parts"]["[Content_Types].xml"])
        z.writestr("_rels/.rels", tpl["parts"]["_rels/.rels"])
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", rels)
        for part, xml in tpl["parts"].items():
            if part not in ("[Content_Types].xml", "_rels/.rels"):
                z.writestr(part, xml)
        z.writestr("docProps/core.xml", core)
    return buf.getvalue()


HTML_STYLE = {"bold": "font-weight:700", "italic": "font-style:italic", "bold_italic": "font-weight:700;font-style:italic",
              "bold_u": "font-weight:700;text-decoration:underline", "name": "font-weight:700;color:#1F3864",
              "contact": "color:#444444", "heading": "font-weight:700;color:#1F3864", "degree": "font-style:italic;color:#444444",
              "context": "color:#808080;font-size:8pt", "cert_note": "font-style:italic;color:#404040", "plain": ""}


def render_html(m, layout=None):
    """HTML in the template's layout (preview, and the PDF fallback when Word is unavailable)."""
    e = html.escape
    out = []
    for kind, runs in model_paragraphs(m, layout):
        spans, right = [], []
        tgt = spans
        for r in runs:
            if r[0] == "tab":
                tgt = right
            elif r[0] == "link":
                tgt.append(f'<a href="{e(r[2])}">{e(r[1])}</a>')
            else:
                st = HTML_STYLE.get(r[0], "")
                tgt.append(f'<span style="{st}">{e(r[1])}</span>' if st else e(r[1]))
        inner = "".join(spans) + (f'<span class="dt">{"".join(right)}</span>' if right else "")
        out.append(f'<p class="k-{kind}">{inner}</p>')
    tpl = (ROOT / "templates/resume.html").read_text(encoding="utf-8")
    return tpl.replace("{{title}}", e(f"{m['identity']['name']} — Resume")).replace("{{body}}", "\n".join(out))


def render_md(m, layout=None):
    sections, J, LB = _layout_parts(layout)
    i, L = m["identity"], []
    for sec in sections:
        kind = sec["kind"]
        if kind == "header":
            links = " · ".join(f"[{ln['label']}]({ln['url']})" for ln in i.get("links") or [])
            L += [f"# {i['name']}", " | ".join(x for x in (i.get("location"), i.get("phone"), i.get("email")) if x) + (f" | {links}" if links else ""), ""]
        elif kind == "lines":
            has, blocks = _line_blocks(m), sec.get("blocks") or []
            if not sec.get("always") and not any(has[b] for b in blocks):
                continue
            L += [f"## {sec['heading']}"]
            for b in blocks:
                if b == "summary":
                    if has["summary"]:
                        L += [m["summary"], ""]
                elif b == "tagline":
                    L += [J["tagline"].join(m.get("tagline") or []), ""]
                elif b == "expertise":
                    L += [J["expertise"].join(m.get("expertise") or []), ""]
                elif b == "technologies":
                    L += [f"**{LB['technologies']}:** {J['technologies'].join(m.get('technologies') or [])}", ""]
        elif kind == "education":
            L += [f"## {sec['heading']}"]
            for ed in m.get("education") or []:
                L += [f"**{ed['school']}**  ", f"*{ed['degree_line']}*"] + [f"- {btext(b)}" for b in ed.get("bullets") or []]
        elif kind == "experience":
            L += ["", f"## {sec['heading']}"]
            for r in m["roles"]:
                L += [f"**{r['title']} | {r['employer']}** | {r['dates']}  ", f"{r.get('context') or ''}"]
                L += [f"- {btext(b)}" for b in r["bullets"]] + [""]
        elif kind == "certifications":
            if not m.get("certifications"):
                continue
            L += [f"## {sec['heading']}"] + [f"- **{c['name']}** — {c['issuer']}" + (f" *({c['note']})*" if c.get("note") else "")
                                             for c in m["certifications"]] + [""]
        elif kind == "engagements":
            if not m.get("engagements"):
                continue
            L += [f"## {sec['heading']}"]
            for g in m["engagements"]:
                L += [f"**{g['client']}** | {g.get('location') or ''} | {g.get('dates') or ''}" + (f" ({g['commitment']})" if g.get("commitment") else "") + "  "]
                if g.get("subtitle"):
                    L += [f"*{g['subtitle']}*"]
                L += [f"- {btext(b)}" for b in g["bullets"]] + [""]
        elif kind == "core_competencies":
            if not m.get("core_competencies"):
                continue
            L += [f"## {sec['heading']}"] + [f"- **{a['label']}:** {J['core'].join(a['items'])}" for a in m["core_competencies"]]
    return "\n".join(L) + "\n"


def pdf_pages(pdf_path):
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        return "?"


def docx_to_pdf(docx_path, pdf_path):
    """Microsoft Word exports the PDF from the .docx itself, so the PDF matches the Word download exactly."""
    if not WORD_PDF.exists():
        return False
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(WORD_PDF),
                            str(docx_path), str(pdf_path)], capture_output=True, text=True, timeout=240)
        return p.returncode == 0 and Path(pdf_path).exists()
    except Exception:
        return False


def to_pdf(html_path, pdf_path):
    """Fallback PDF renderer: headless Chrome/Edge printing the template HTML."""
    exe = next((p for p in CHROME if p.exists()), None)
    if not exe:
        print("  (no Word, Chrome or Edge found — skipped PDF)")
        return None
    subprocess.run([str(exe), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-sandbox",
                    f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
                   check=True, capture_output=True, timeout=120)
    return pdf_pages(pdf_path)


def scrub_check(text, where):
    bad = [p for p in BANNED_IN_OUTPUT if re.search(p, text, re.I)]
    if bad:
        sys.exit(f"SCRUB FAIL in {where}: {bad}")


PRESENT_VERBS = {"own", "owns", "advise", "advises", "run", "runs", "lead", "leads", "manage", "manages", "build", "builds",
                 "sell", "sells", "carry", "carries", "serve", "serves", "drive", "drives"}


def check_model(con, m, cfg=None):
    """Tier-3 QA: every printed line traces to claims; no number without evidence; no disputed or retired claim; no first
    person; bands. Returns (errors, warnings) as lists of 'line_key: issue'."""
    cfg = cfg or CL.load_config()
    band = json.loads(con.execute("SELECT value FROM meta WHERE key='length_band'").fetchone()[0])
    lband = json.loads((con.execute("SELECT value FROM meta WHERE key='longform_band'").fetchone() or ['{"hard_ceiling": 340, "p10": 170}'])[0])
    lband.setdefault("p10", 170)
    trace = m.get("trace") or {}
    lines = []
    if m.get("summary"):
        lines.append(("summary", m["summary"], trace.get("summary") or trace.get("tagline") or [], None, "phrase"))
    lines.append(("tagline", " | ".join(m.get("tagline") or []), trace.get("tagline", []), None, "phrase"))
    lines.append(("expertise", " • ".join(m.get("expertise") or []), trace.get("expertise", []), None, "phrase"))
    lines.append(("technologies", ", ".join(m.get("technologies") or []), trace.get("technologies", []), None, "phrase"))
    for n_e, e in enumerate(m.get("education") or []):
        lines.append((f"education:{n_e}", f"{e['school']} | {e['degree_line']}", trace.get(f"education:{n_e}", []), None, "phrase"))
    for r in m.get("roles") or []:
        lines.append((f"role:{r['key']}", f"{r['title']} | {r['employer']} | {r['dates']} | {r.get('context') or ''}", trace.get(f"role:{r['key']}", []), None, "phrase"))
        ended = not (r.get("dates") or "").endswith("Present")
        for n_b, b in enumerate(r.get("bullets") or []):
            text = btext(b)
            lines.append((f"role:{r['key']}:{n_b}", text, trace.get(f"role:{r['key']}:{n_b}", []), band, "bullet"))
            if ended and text.split(" ")[0].lower() in PRESENT_VERBS:
                lines.append((f"role:{r['key']}:{n_b}", text, None, None, "tense"))
    for n_c, c in enumerate(m.get("certifications") or []):
        lines.append((f"cert:{n_c}", f"{c['name']} — {c['issuer']}", trace.get(f"cert:{n_c}", []), None, "phrase"))
    for e in m.get("engagements") or []:
        lines.append((f"eng:{e['key']}", f"{e['client']} | {e.get('location') or ''} | {e.get('dates') or ''} | {e.get('subtitle') or ''}", trace.get(f"eng:{e['key']}", []), None, "phrase"))
        for n_b, b in enumerate(e.get("bullets") or []):
            lines.append((f"eng:{e['key']}:{n_b}", btext(b), trace.get(f"eng:{e['key']}:{n_b}", []), lband, "bullet"))
    for a in m.get("core_competencies") or []:
        lines.append((f"core:{a['label']}", ", ".join(a["items"]), trace.get(f"core:{a['label']}", []), None, "phrase"))
    errors, warnings = [], []
    for key, text, ids, band_, kind in lines:
        if kind == "tense":
            warnings.append(f"{key}: present-tense verb under an ended role")
            continue
        rows, quotes = CL.claim_context(con, [unalias_claim(i) for i in (ids or [])])
        kinds = {r["id"]: r["kind"] for r in rows}
        for issue in CL.check_line(text, rows, quotes, cfg, band_, kind):
            soft = "chars" in issue or (issue == "no claim trace" and kind == "phrase") or \
                   (issue.startswith("disputed claim") and kinds.get(issue.split()[-1]) not in ("metric", "achievement"))
            (warnings if soft else errors).append(f"{key}: {issue}")
    return errors, warnings


def cmd_check(args):
    con = connect()
    m = jload(args.model)
    if not m:
        sys.exit(f"no model at {args.model}")
    errors, warnings = check_model(con, m)
    for w in warnings:
        print("  WARN ", w)
    for e in errors:
        print("  ERROR", e)
    print(f"check: {len(errors)} error(s), {len(warnings)} warning(s), {sum(1 for k in (m.get('trace') or {}) )} traced lines")
    if errors:
        sys.exit(1)


def write_outputs(m, base_path, con=None, strict=True):
    """One resume model -> .json, .md, .html, .docx and .pdf beside base_path, after tier-3 QA. Returns (pdf path, pages, engine)."""
    base_path = Path(base_path)
    if con is not None:
        errors, warnings = check_model(con, m)
        for w in warnings:
            print("  WARN ", w)
        for e in errors:
            print("  ERROR", e)
        jdump({"trace": m.get("trace") or {}, "errors": errors, "warnings": warnings, "checked_at": dt.datetime.now().isoformat(timespec="seconds")},
              base_path.with_suffix(".trace.json"))
        if errors and strict:
            sys.exit(f"QA FAIL: {len(errors)} error(s) in {base_path.name}; fix the claim or the wording (or pass --force to write anyway)")
    tpl = load_template()
    ly = template_layout(tpl)
    md, h = render_md(m, ly), render_html(m, ly)
    blob = docx_bytes(m, tpl)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        doc_xml = z.read("word/document.xml").decode("utf-8")
    for text, where in ((md, "markdown"), (h, "html"), (doc_xml, "docx"), (json.dumps(m, ensure_ascii=False), "json")):
        scrub_check(text, f"{base_path.name} ({where})")
    jdump(m, base_path.with_suffix(".json"))
    base_path.with_suffix(".md").write_text(md, encoding="utf-8")
    hp = base_path.with_suffix(".html")
    hp.write_text(h, encoding="utf-8")
    dp, pp = base_path.with_suffix(".docx"), base_path.with_suffix(".pdf")
    dp.write_bytes(blob)
    if docx_to_pdf(dp, pp):
        return pp, pdf_pages(pp), "Word"
    return pp, to_pdf(hp, pp), "Chrome"


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
    res = assemble(con, req, base, prof, args.version, jd_meta)
    name = args.name or ("baseline_" + args.version if not args.jd else Path(args.jd).stem + "_" + args.version)
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    pdf, pages, engine = write_outputs(res, out / name, con, strict=not args.force)
    con.execute("INSERT INTO generated_resumes (jd_id,version,json,html_path,pdf_path) VALUES (?,?,?,?,?)",
                (jd_meta["id"] if jd_meta else None, args.version, json.dumps(res), str(out / f"{name}.docx"), str(pdf)))
    con.commit()
    n_b = sum(len(r["bullets"]) for r in res["roles"])
    n_c = sum(len(e["bullets"]) for e in res["engagements"])
    print(f"built {name}: {len(res['roles'])} roles, {n_b} bullets, {len(res['engagements'])} engagement(s) with {n_c} long-form bullets, "
          f"pdf pages={pages} ({engine})" + (f", match={res['match']['score']:.0%}" if res["match"]["score"] is not None else ""))
    print(f"  {out / (name + '.docx')}\n  {pdf}")


# ---------------------------------------------------------------- export for the artifact
def cmd_export(args):
    con = connect()
    tags = tag_index(con)
    _, ach_cur, prof, base, _ = load_curation()
    ach = load_bullets(con)
    band = json.loads(con.execute("SELECT value FROM meta WHERE key='length_band'").fetchone()[0])
    cfg = CL.load_config()
    alias = lambda cid: str(cid).replace("role:liminal", "role:" + ROLE_ALIAS["liminal"])   # confidential role key never leaves the repo
    claims_out, metric_ids = [], {}
    ev_by_claim = {}
    for r in con.execute("""SELECT ce.claim_id, e.source_type, e.authored_at, e.observed_at, e.quote FROM claim_evidence ce
                            JOIN evidence e ON e.id = ce.evidence_id WHERE ce.stance IN ('supports','refines')"""):
        ev_by_claim.setdefault(r["claim_id"], []).append(r)
    for c in con.execute("SELECT * FROM claims WHERE status != 'retired' ORDER BY id"):
        evs = ev_by_claim.get(c["id"], [])
        nums = set(CL.number_tokens(c["value"]))
        for e in evs:
            nums |= CL.number_tokens(e["quote"])
        if c["kind"] == "metric":
            metric_ids.setdefault(c["subject"], []).append(c["id"])
        claims_out.append({"id": alias(c["id"]), "kind": c["kind"], "subject": alias(c["subject"]), "predicate": c["predicate"],
                           "value": c["value"], "unit": c["unit"], "text": c["text"], "confidence": c["confidence"], "status": c["status"],
                           "valid_from": c["valid_from"], "valid_to": c["valid_to"], "as_of": c["as_of"],
                           "evidence": {"n": len(evs), "source_types": sorted({e["source_type"] for e in evs}),
                                        "latest": max([e["observed_at"] or e["authored_at"] or "" for e in evs] or [""]) or None},
                           "numbers": sorted(nums, key=lambda x: float(x))})
    roles = []
    for r in con.execute("SELECT * FROM roles WHERE key != 'education' ORDER BY sort"):
        rk = ROLE_ALIAS.get(r["key"], r["key"])
        roles.append({"key": rk, "sort": r["sort"], "employer": r["employer"], "title": r["title"],
                      "location": r["location"], "start": r["start"], "end": r["end"],
                      "dates": f"{fmt_date(r['start'])} – {fmt_date(r['end'])}",
                      "engagement": r["engagement"], "context": r["context_line"], "hidden": bool(r["hidden_by_default"]),
                      "claim_ids": [f"role:{rk}:{f}" for f in ("title", "employer", "start", "end", "context")]})
    metrics = {a["id"]: a.get("metrics", []) for a in ach_cur}
    out_ach = []
    for a in ach.values():
        out_ach.append({"id": a["id"], "role": ROLE_ALIAS.get(a["role"], a["role"]), "confidence": a["confidence"], "tags": a["tags"],
                        "metrics": metrics.get(a["id"], []),
                        "claim_ids": [f"ach:{a['id']}"] + metric_ids.get(f"ach:{a['id']}", []),
                        "texts": [{"id": t["id"], "kind": t["kind"], "angle": t["angle"], "text": t["text"],
                                   "score_adj": t["score_adj"] or 0} for t in a["texts"]]})
    lband = json.loads((con.execute("SELECT value FROM meta WHERE key='longform_band'").fetchone() or ['{}'])[0])
    prof_eng = {e["key"]: e for e in prof.get("engagements", [])}
    engagements = []
    for e in con.execute("SELECT * FROM engagements ORDER BY sort"):
        engagements.append({"key": e["key"], "role": ROLE_ALIAS.get(e["role_key"], e["role_key"]), "client": e["client"],
                            "claim_ids": [f"eng:{e['key']}:{f}" for f in ("client", "location", "start", "end", "commitment", "subtitle")],
                            "location": e["location"], "start": e["start"], "end": e["end"],
                            "dates": f"{fmt_date(e['start'])} – {fmt_date(e['end'])}" if e["start"] else None,
                            "commitment": e["commitment"], "subtitle": e["subtitle"], "needs_details": bool(e["needs_details"]),
                            "ask": prof_eng.get(e["key"], {}).get("ask"),
                            "achievements": [r[0] for r in con.execute("SELECT achievement_id FROM engagement_achievements "
                                                                      "WHERE engagement_key=? ORDER BY sort", (e["key"],))]})
    core = {}
    for r in con.execute("SELECT * FROM core_competencies ORDER BY area_sort, sort"):
        core.setdefault(r["area"], []).append({"text": r["text"], "tags": json.loads(r["tags"]), "claim_id": r["claim_id"]})
    lib = {
        "schema": "rot-library/3", "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
        "tiers": {str(k): v for k, v in CL.TIER_LABELS.items()},
        "confidence": {"formula_version": cfg["formula_version"], "print": cfg["print"], "bands": cfg["bands"]},
        "claims": claims_out,
        "template": {"id": base.get("template", "source-2026-09"), "docx": "template/docx_template.json",
                     "section_order": base.get("section_order")},
        "identity": prof["identity"], "length_band": band, "longform_band": lband,
        "families": jload(CUR / "taxonomy.json")["families"],
        "tags": tags, "roles": roles, "achievements": out_ach,
        "tagline_phrases": [{"text": r["text"], "tags": json.loads(r["tags"]), "sort": r["sort"], "origin": r["origin"], "claim_id": r["claim_id"]}
                            for r in con.execute("SELECT * FROM tagline_phrases WHERE status='accepted' ORDER BY sort, id")],
        "competencies": [{"text": r["text"], "tags": json.loads(r["tags"]), "sort": r["sort"], "origin": r["origin"], "claim_id": r["claim_id"]}
                         for r in con.execute("SELECT * FROM competencies ORDER BY sort, id")],
        "core_competencies": [{"label": k, "items": v} for k, v in core.items()],
        "engagements": engagements,
        "expertise_areas": [{"label": a["label"], "items": a["items"]} for a in prof.get("expertise_areas", [])],
        "technologies": [{"name": r["name"], "category": r["category"], "tags": json.loads(r["tags"]), "sort": r["sort"], "claim_id": r["claim_id"]}
                         for r in con.execute("SELECT * FROM technologies ORDER BY sort, id")],
        "domain_fluency": [r["name"] for r in con.execute("SELECT * FROM domain_fluency")],
        "certifications": [{"name": r["name"], "issuer": r["issuer"], "date": r["date"], "status": r["status"],
                            "note": "In Progress" if r["status"] else None, "hidden": bool(r["hidden_by_default"]), "claim_id": r["claim_id"]}
                           for r in con.execute("SELECT * FROM certifications ORDER BY sort, id")],
        "education": [{"school": r["school"], "degree": r["degree"], "year": r["year"], "date_display": r["date_display"] or r["year"],
                       "degree_line": f"{r['degree']} | {r['date_display'] or r['year']}", "bullet_ids": json.loads(r["bullet_ids"]), "claim_id": r["claim_id"]}
                      for r in con.execute("SELECT * FROM education")],
        "summaries": [{"source": r["source_id"] or "baseline", "tags": json.loads(r["tags"]), "text": r["text"]} for r in con.execute("SELECT * FROM summaries")],
        "baseline": {**{k: ({ROLE_ALIAS.get(rk, rk): rv for rk, rv in base.get(k).items()} if k in ("caps", "priority") else base.get(k))
                        for k in ("template", "summary_enabled", "section_order", "caps", "priority", "engagement_caps", "competency_count",
                                  "competency_order", "tagline_count", "angle_map", "scoring")},
                     "settings": _alias_settings(base.get("settings") or {})},
    }
    s = json.dumps(lib, ensure_ascii=False, indent=1)
    scrub_check(s, "library.json")
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data/library.json").write_text(s, encoding="utf-8")
    with open(ROOT / "data/dump.sql", "w", encoding="utf-8") as f:
        for line in con.iterdump():
            f.write(line + "\n")
    print(f"exported data/library.json ({len(s)//1024} KB, {len(out_ach)} achievements, "
          f"{sum(len(a['texts']) for a in out_ach)} bullets, {len(claims_out)} claims, {len(lib['tagline_phrases'])} tagline phrases, "
          f"{len(engagements)} engagements) and data/dump.sql")


# ---------------------------------------------------------------- learning loop
def cmd_learn(args):
    """Merge a learnings file (artifact export or gate answers). Shape:
       {"runs":[{"id","company","title","jd_text","requirements":{tag:weight},
                 "followups":[{"question","answer","tag","section","engagement_key"}],
                 "feedback":[{"bullet_id","action","edited_text"}]}],
        "new_bullets":[{"achievement_id" | "new_achievement":{...}, "angle","text","longform","engagement","tags":{},"origin"}],
        "tagline_phrases":[{"text","tags"}], "technologies":[{"name","category","tags"}],
        "competencies":[{"text","tags"}] (Section B), "core_competencies":[{"area","text","tags"}] (Section D),
        "engagement_updates":{key:{"client","location","start","end","commitment","subtitle"}} (Section C)}"""
    data = jload(args.file) if isinstance(args.file, (str, Path)) else args.file
    con = connect()
    ensure_learning_keys(con)
    learned = jload(CUR / "learned.json", {"achievements": [], "bullets": [], "overrides": {}, "profile_overrides": {}, "baseline_overrides": {}})
    n_runs = n_fb = n_new = n_ev = n_out = n_gen = 0
    known = {r["id"] for r in con.execute("SELECT id FROM achievements")}
    ev_rows, run_answer_ids = [], {}
    for run in data.get("runs", []):
        jid = run.get("id") or "jd_" + hashlib.md5(run["jd_text"].encode()).hexdigest()[:10]
        # idempotent: re-syncing a run refreshes it instead of duplicating it
        con.execute("""INSERT INTO job_descriptions (id,company,title,text,origin) VALUES (?,?,?,?, 'artifact')
                       ON CONFLICT(id) DO UPDATE SET company=excluded.company, title=excluded.title, text=excluded.text""",
                    (jid, run.get("company"), run.get("title"), run.get("jd_text", "")))
        # tier 1: every answered question is Tim's own words, logged verbatim before anything is derived from it
        for n, f in enumerate(run.get("followups", [])):
            ans = (f.get("answer") or "").strip()
            if not ans:
                continue
            eid = f"ev:ans:{jid}:{f.get('q_ix', n)}"
            ev_rows.append({"id": eid, "source_type": "USER_ENTERED", "channel": "match_desk", "source_ref": jid, "locator": f"followup {f.get('q_ix', n)}",
                            "question": f.get("question"), "quote": ans, "observed_at": run.get("finalized") or run.get("created") or dt.datetime.now().isoformat(timespec="seconds"),
                            "section": f.get("section") or "experience", "tags": [f["tag"]] if f.get("tag") else [], "role": f.get("role"),
                            "engagement_key": f.get("engagement_key"), "posting": {"company": run.get("company"), "title": run.get("title")}})
            f["evidence_id"] = eid
            run_answer_ids.setdefault(jid, []).append((f.get("q_ix", n), f.get("tag"), eid))
            if f.get("fields") and f.get("engagement_key"):
                det = "; ".join(f"{k}: {v}" for k, v in f["fields"].items() if v)
                if det:
                    ev_rows.append({"id": f"ev:eng:{jid}:{f['engagement_key']}", "source_type": "USER_ENTERED", "channel": "match_desk", "source_ref": jid,
                                    "locator": f"engagement details {f['engagement_key']}", "question": f.get("question"), "quote": det,
                                    "observed_at": run.get("finalized") or run.get("created"), "section": "engagement_details", "engagement_key": f["engagement_key"]})
        for fb in run.get("feedback", []):
            if fb.get("action") == "edit" and fb.get("edited_text"):
                ev_rows.append({"id": f"ev:edit:{jid}:{fb.get('achievement_id') or fb.get('bullet_id')}", "source_type": "USER_ENTERED", "channel": "match_desk",
                                "source_ref": jid, "locator": "sheet edit", "question": None, "quote": fb["edited_text"], "observed_at": fb.get("created") or run.get("finalized"),
                                "section": "experience"})
        # tier 4: application outcome, stored against the resume version, never used to re-weight anything
        oc = run.get("outcome")
        if oc and (oc.get("applied_at") or oc.get("response")):
            ext = f"{jid}:{oc.get('recorded_at') or oc.get('applied_at') or ''}"
            row = {"run_id": jid, "jd_id": jid, "resume_version": run.get("finalized") or run.get("downloaded_at"), "applied_at": oc.get("applied_at"),
                   "response": oc.get("response") or "pending", "note": oc.get("note"), "recorded_at": oc.get("recorded_at") or dt.datetime.now().isoformat(timespec="seconds"), "ext_id": ext}
            cur = con.execute("INSERT OR IGNORE INTO outcomes (run_id,jd_id,resume_version,applied_at,response,note,recorded_at,ext_id) VALUES (?,?,?,?,?,?,?,?)",
                              (row["run_id"], row["jd_id"], row["resume_version"], row["applied_at"], row["response"], row["note"], row["recorded_at"], row["ext_id"]))
            if cur.rowcount == 1:
                n_out += 1
                CL.append_jsonl(ROOT / "data/feedback/outcomes.jsonl", [{"id": ext, **row}])
        # tier 3: what was printed, traced to its claims and the prompt versions that produced it
        fm = run.get("final_model") or {}
        pvs = {k: (str(v) if str(v).startswith(f"{k}@") else f"{k}@{v}") for k, v in (run.get("prompt_versions") or {}).items()}
        pv = ",".join(v for _, v in sorted(pvs.items())) or None
        for k, v in pvs.items():
            con.execute("INSERT OR IGNORE INTO prompt_versions (id,name,hash) VALUES (?,?,?)", (v, k, v.split("@", 1)[1]))
        for line_key, ids in (fm.get("trace") or {}).items():
            text = _trace_text(fm, line_key)
            if text is None:
                continue
            ext = f"{jid}:{line_key}:{hashlib.md5(text.encode()).hexdigest()[:10]}"
            cur = con.execute("INSERT OR IGNORE INTO generation_events (run_id,jd_id,section,line_key,text,claim_ids,prompt_version,model,status,ext_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
                              (jid, jid, line_key.split(":")[0], line_key, text, json.dumps([unalias_claim(i) for i in ids]), pv, fm.get("model") or "match-desk", "shown", ext))
            n_gen += cur.rowcount
        con.execute("DELETE FROM jd_requirements WHERE jd_id=?", (jid,))
        for tag, w in (run.get("requirements") or {}).items():
            con.execute("INSERT INTO jd_requirements (jd_id,tag_id,weight) SELECT ?,?,? WHERE EXISTS (SELECT 1 FROM tags WHERE id=?)",
                        (jid, tag, float(w if not isinstance(w, dict) else w.get("weight", 1)), tag))
        for f in run.get("followups", []):
            key = hashlib.md5(f"{jid}|{f['question']}|{f.get('answer') or ''}".encode()).hexdigest()
            con.execute("""INSERT OR IGNORE INTO followups (jd_id,gate,question,answer,tag_id,answered_at,ext_key,section,engagement_key,evidence_id)
                           VALUES (?,?,?,?,(SELECT id FROM tags WHERE id=?),datetime('now'),?,?,?,?)""",
                        (jid, f.get("gate", 2), f["question"], f.get("answer"), f.get("tag"), key,
                         f.get("section") or "experience", f.get("engagement_key"), f.get("evidence_id")))
        for fb in run.get("feedback", []):
            ext = fb.get("ext_id") or hashlib.md5(json.dumps(fb, sort_keys=True).encode()).hexdigest()
            cur = con.execute("INSERT OR IGNORE INTO feedback (jd_id,bullet_id,action,edited_text,ext_id,event) VALUES (?,?,?,?,?,?)",
                              (jid, fb.get("bullet_id"), fb["action"], fb.get("edited_text"), ext, CL.ACTION_EVENT.get(fb["action"], fb["action"])))
            if cur.rowcount != 1:
                continue  # already learned
            delta = {"keep": 0.3, "reject": -0.6, "drop": -0.6}.get(fb["action"], 0)
            if delta and fb.get("bullet_id"):
                con.execute("UPDATE bullets SET score_adj = COALESCE(score_adj,0) + ? WHERE id=?", (delta, fb["bullet_id"]))
            n_fb += 1
        n_runs += 1
    def answer_evidence(nb):
        """The answer(s) a learned bullet came from: an exact question index when the page recorded one, else the run's
        answered questions that share its tag, else all of the run's answers."""
        if nb.get("evidence"):
            return list(nb["evidence"])
        ids = run_answer_ids.get(nb.get("run_id") or "", [])
        if nb.get("q_ix") is not None:
            hit = [e for q, t, e in ids if q == nb["q_ix"]]
            if hit:
                return hit
        tags = set((nb.get("tags") or {}).keys() if isinstance(nb.get("tags"), dict) else (nb.get("tags") or []))
        hit = [e for q, t, e in ids if t and t in tags]
        return hit or [e for q, t, e in ids]
    for nb in data.get("new_bullets", []):
        if nb.get("new_achievement"):
            a = nb["new_achievement"]
            a["role"] = ROLE_UNALIAS.get(a.get("role"), a.get("role"))
            a.setdefault("origin", nb.get("origin", "artifact"))
            a.setdefault("variants", {})
            a.setdefault("patterns", [])
            a["evidence"] = answer_evidence({**nb, "tags": a.get("tags")})
            if nb.get("engagement"):
                a["engagement"] = nb["engagement"]
            if nb.get("longform") and norm(nb["longform"]) != norm(a["canonical"]):
                a["variants"]["longform"] = nb["longform"]
            if a["id"] not in known and all(x["id"] != a["id"] for x in learned["achievements"]):
                learned["achievements"].append(a)
                n_new += 1
        elif nb.get("achievement_id") in known:
            adds = [(nb.get("angle", "learned"), nb["text"])] + ([("longform", nb["longform"])] if nb.get("longform") else [])
            for angle, text in adds:
                if not any(b["text"] == text for b in learned["bullets"]):
                    learned["bullets"].append({"achievement_id": nb["achievement_id"], "angle": angle, "text": text,
                                               "origin": nb.get("origin", "artifact"), "status": nb.get("status", "accepted"),
                                               "evidence": answer_evidence(nb)})
                    n_new += 1
    # template-section stores: A tagline phrases, B expertise items, D core competencies, Technologies, C engagement details
    have = {"tagline_phrases": {norm(r[0]) for r in con.execute("SELECT text FROM tagline_phrases")},
            "technologies": {norm(r[0]) for r in con.execute("SELECT name FROM technologies")},
            "competencies": {norm(r[0]) for r in con.execute("SELECT text FROM competencies")},
            "core_competencies": {norm(r[0]) for r in con.execute("SELECT text FROM core_competencies")}}
    n_sec = 0
    for store, field in (("tagline_phrases", "text"), ("technologies", "name"), ("competencies", "text"), ("core_competencies", "text")):
        dst = learned.setdefault(store, [])
        seen = have[store] | {norm(x[field]) for x in dst}
        for it in data.get(store) or []:
            if it.get(field) and norm(it[field]) not in seen:
                ev_id = it.get("evidence") or [f"ev:phrase:{it.get('run_id') or 'manual'}:{CL.slug(it[field])}"]
                if not it.get("evidence"):     # the entry itself is Tim's typed statement
                    ev_rows.append({"id": ev_id[0], "source_type": "USER_ENTERED", "channel": "match_desk", "source_ref": it.get("run_id"),
                                    "locator": f"{store} entry", "question": None, "quote": it[field],
                                    "observed_at": it.get("created") or dt.datetime.now().isoformat(timespec="seconds"), "section": store})
                dst.append({**{k: v for k, v in it.items() if k != "run_id"}, "origin": it.get("origin", "artifact"), "status": it.get("status", "accepted"), "evidence": ev_id})
                seen.add(norm(it[field]))
                n_sec += 1
    for k, upd in (data.get("engagement_updates") or {}).items():
        upd = dict(upd)
        run_id = upd.pop("run_id", None)
        upd = {f: v for f, v in upd.items() if v not in (None, "")}
        cur_upd = learned.setdefault("engagement_updates", {}).setdefault(k, {})
        if any(cur_upd.get(f) != v for f, v in upd.items()) or cur_upd.get("needs_details", True):
            cur_upd.update(upd)
            cur_upd["needs_details"] = False
            eid = f"ev:eng:{run_id or 'manual'}:{k}"
            if not any(r["id"] == eid for r in ev_rows):
                ev_rows.append({"id": eid, "source_type": "USER_ENTERED", "channel": "match_desk", "source_ref": run_id, "locator": f"engagement details {k}",
                                "question": None, "quote": "; ".join(f"{f}: {v}" for f, v in upd.items() if f != "evidence"),
                                "observed_at": dt.datetime.now().isoformat(timespec="seconds"), "section": "engagement_details", "engagement_key": k})
            cur_upd["evidence"] = sorted(set(cur_upd.get("evidence", []) + [eid]))
            n_sec += 1
    n_ev = CL.append_jsonl(CL.EVID / "answers.jsonl", ev_rows)
    con.commit()
    jdump(learned, CUR / "learned.json")
    print(f"learned: {n_runs} runs, {n_fb} feedback events, {n_new} new bullets/achievements, {n_sec} template-section items, "
          f"{n_ev} evidence rows, {n_out} outcomes, {n_gen} generation events -> curation/learned.json, curation/evidence/answers.jsonl")
    if not getattr(args, "quiet_next", False):
        print("next: python rot.py ingest && python rot.py export")
    return {"runs": n_runs, "feedback": n_fb, "new": n_new, "sections": n_sec, "evidence": n_ev, "outcomes": n_out, "generation": n_gen}


def _trace_text(fm, line_key):
    """The printed text behind a trace key of a page model (v2)."""
    parts = line_key.split(":")
    try:
        if parts[0] == "tagline":
            return " | ".join(fm.get("tagline") or [])
        if parts[0] == "expertise":
            return " • ".join(fm.get("expertise") or [])
        if parts[0] == "technologies":
            return ", ".join(fm.get("technologies") or [])
        if parts[0] == "summary":
            return fm.get("summary")
        if parts[0] == "education":
            e = fm["education"][int(parts[1])]
            return f"{e['school']} | {e['degree_line']}"
        if parts[0] == "cert":
            c = fm["certifications"][int(parts[1])]
            return f"{c['name']} — {c['issuer']}"
        if parts[0] == "core":
            a = next(x for x in fm["core_competencies"] if x["label"] == ":".join(parts[1:]))
            return ", ".join(a["items"])
        if parts[0] in ("role", "eng"):
            coll = fm["roles"] if parts[0] == "role" else fm["engagements"]
            item = next(x for x in coll if x["key"] == parts[1])
            if len(parts) == 2:
                return f"{item.get('title') or item.get('client')} | {item.get('employer') or item.get('location') or ''} | {item.get('dates') or ''}"
            return btext(item["bullets"][int(parts[2])])
    except (KeyError, IndexError, StopIteration, ValueError):
        return None
    return None


def ensure_learning_keys(con):
    """Add the dedupe keys learning needs (safe to run on any older resume.db)."""
    migrate(con)
    (ROOT / "data" / "feedback").mkdir(parents=True, exist_ok=True)
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
FIRST_PERSON = re.compile(r"\b(I(?!\.[A-Z])|I'm|I've|I'd|me|my|mine|we|our|us)\b")   # "I.T." is not first person
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


# Section answers that are phrases, not bullets: page section -> (learned.json store, field, max characters)
PHRASE_SECTIONS = {"tagline": ("tagline_phrases", "text", 60), "expertise": ("competencies", "text", 70),
                   "technology": ("technologies", "name", 90), "competency": ("core_competencies", "text", 80)}
ENG_FIELDS = ("client", "location", "start", "end", "commitment", "subtitle")


def phrase_checks(text, section):
    issues = []
    limit = PHRASE_SECTIONS[section][2]
    if FIRST_PERSON.search(text):
        issues.append("first person")
    if len(text) > limit:
        issues.append(f"{len(text)} chars > {limit}")
    if len(text) < 2:
        issues.append("empty")
    if text.rstrip().endswith("."):
        issues.append("ends with a period")
    return issues


def _answer_quotes(run, nb, edits=None):
    """The answers a page bullet came from: the exact question when the page recorded it, else the answers with the same
    tag, else every answer in the run. Sheet edits of that bullet count too (they are Tim's own words)."""
    fs = [(n, f) for n, f in enumerate(run.get("followups") or []) if (f.get("answer") or "").strip()]
    if nb.get("q_ix") is not None:
        hit = [f["answer"] for n, f in fs if n == nb["q_ix"]]
        if hit:
            return hit + list(edits or [])
    tags = set(nb.get("tags") or [])
    hit = [f["answer"] for n, f in fs if f.get("tag") in tags]
    fields = [" ; ".join(f"{k}: {v}" for k, v in (f.get("fields") or {}).items() if v) for n, f in fs if f.get("fields")]
    return (hit or [f["answer"] for n, f in fs]) + fields + list(edits or [])


def cmd_sync_prepare(args):
    """Read an ArtifactData dump (jd_runs / bullet_inbox / feedback), decide what to learn, and write
    sync/pending.json. Bullets that break the Resume 1 standard (or, for Section C, the long-form band) and phrases
    that break their section's rules are flagged needs_polish; the sync agent (Claude) rewrites them into
    sync/polished.json before sync-apply."""
    con = connect()
    band = json.loads(con.execute("SELECT value FROM meta WHERE key='length_band'").fetchone()[0])
    lband = json.loads((con.execute("SELECT value FROM meta WHERE key='longform_band'").fetchone() or ['{"hard_ceiling": 340}'])[0])
    runs = [r for r in _load_dump(args.dump, "jd_runs") if not _is_synced(r)]
    inbox = [b for b in _load_dump(args.dump, "bullet_inbox") if not _is_synced(b)]
    feedback = [f for f in _load_dump(args.dump, "feedback") if not _is_synced(f)]
    pending_runs = [r for r in runs if r.get("sync_status") == "pending"]
    if not pending_runs and not args.all:
        print(json.dumps({"status": "nothing_pending", "unsynced_runs": len(runs)}))
        return
    known = {r["id"] for r in con.execute("SELECT id FROM achievements")}
    engagements = {r[0] for r in con.execute("SELECT key FROM engagements")}
    items, seen = {}, {}
    # latest edit / drop per gate-2 achievement id
    edits, drops = {}, set()
    for f in sorted(feedback, key=lambda x: x.get("created", "")):
        aid = f.get("achievement_id") or ""
        if f.get("action") == "edit" and f.get("text"):
            edits[aid] = f["text"]
        if f.get("action") in ("drop", "reject"):
            drops.add(aid)

    def add_item(key, run_id, role, aid, text, tags, src, angle, engagement=None, longform=None, q_ix=None, quotes=None):
        role = ROLE_UNALIAS.get(role, role)
        n = norm(text)
        if n in seen:
            items[seen[n]]["source_ids"] += src
            return
        seen[n] = key
        allowed = set()
        for q in quotes or []:
            allowed |= CL.number_tokens(q)
        if aid in known:                                   # enriching a bank bullet: its evidence counts too
            _, q2 = CL.claim_context(con, [f"ach:{aid}"] + [r[0] for r in con.execute("SELECT id FROM claims WHERE subject=? AND kind='metric'", (f"ach:{aid}",))])
            for q in q2:
                allowed |= CL.number_tokens(q)
        if angle == "longform":    # a Section C edit is judged against the long-form band, not the Resume 1 ceiling
            issues = [i for i in bullet_checks(text, {**band, "hard_ceiling": lband["hard_ceiling"]}) if "short" not in i]
        else:
            issues = bullet_checks(text, band)
        eng = engagement if engagement in engagements else None
        if longform:
            issues += [f"long form {i}" for i in bullet_checks(longform, {**band, "hard_ceiling": lband["hard_ceiling"]}) if "short" not in i]
        if quotes is not None:
            missing = sorted(CL.number_tokens(text) - allowed, key=float)
            if missing:
                issues.append("numbers not in the answer: " + ", ".join(missing))
            if longform:
                lm = sorted(CL.number_tokens(longform) - allowed, key=float)
                if lm:
                    issues.append("long form numbers not in the answer: " + ", ".join(lm))
        items[key] = {"key": key, "run_id": run_id, "role": role, "achievement_id": aid if aid in known else None,
                      "text": text.strip(), "tags": [t for t in (tags or []) if t], "angle": angle, "q_ix": q_ix,
                      "engagement": eng, "longform": (longform or "").strip() or None, "allowed_numbers": sorted(allowed, key=float) if quotes is not None else None,
                      "source_ids": list(src), "issues": issues}

    # gate-2 bullets recorded on each run (index n -> page id gate2-<run>-<n>)
    for r in runs:
        # what the final resume actually showed wins; then the latest sheet edit; then the answer-derived text
        shown = {b.get("aid"): b.get("text") for role in ((r.get("final_resume") or {}).get("roles") or [])
                 for b in role.get("bullets", []) if isinstance(b, dict)}
        for n, nb in enumerate(r.get("new_bullets") or []):
            gid = f"gate2-{r['_id']}-{n}"
            if gid in drops or nb.get("section") in PHRASE_SECTIONS:
                continue
            text = shown.get(gid) or edits.get(gid) or nb.get("text") or ""
            if len(text) < 15:
                continue
            src = [b["_id"] for b in inbox if b.get("run_id") == r["_id"] and norm(b.get("text", "")) == norm(nb.get("text", ""))]
            add_item(f"{r['_id']}-{n}", r["_id"], nb.get("role"), nb.get("achievement_id"), text, nb.get("tags"), src, "gate2",
                     nb.get("engagement_key"), nb.get("longform"), nb.get("q_ix"), _answer_quotes(r, nb, [edits[gid]] if gid in edits else None))
    # template-section answers: phrases (tagline, expertise, technology, core competency) and engagement details
    phrases, eng_updates, pseen = {}, {}, set()
    stores = {"tagline": {norm(r[0]) for r in con.execute("SELECT text FROM tagline_phrases")},
              "expertise": {norm(r[0]) for r in con.execute("SELECT text FROM competencies")},
              "technology": {norm(r[0]) for r in con.execute("SELECT name FROM technologies")},
              "competency": {norm(r[0]) for r in con.execute("SELECT text FROM core_competencies")}}

    def add_phrase(key, section, text, tags, run_id, src, origin="artifact", area=None):
        text = re.sub(r"\s+", " ", str(text or "")).strip().strip("•·|,;").strip()
        if not text or norm(text) in stores[section] or (section, norm(text)) in pseen:
            return
        pseen.add((section, norm(text)))
        issues = phrase_checks(text, section)
        phrases[key] = {"key": key, "section": section, "text": text, "tags": [t for t in (tags or []) if t], "area": area,
                        "run_id": run_id, "origin": origin, "source_ids": list(src), "issues": issues, "needs_polish": bool(issues)}

    for b in sorted(inbox, key=lambda x: x.get("created", "")):
        sec = b.get("section")
        if sec == "engagement_details" and b.get("engagement_key") in engagements:
            d = {k: (str(v).strip() or None) if v is not None else None for k, v in (b.get("details") or {}).items() if k in ENG_FIELDS}
            eng_updates.setdefault(b["engagement_key"], {}).update({k: v for k, v in d.items() if v})
        elif sec in PHRASE_SECTIONS:
            add_phrase(f"inbox-{b['_id']}", sec, b.get("text"), b.get("tags"), b.get("run_id"), [b["_id"]], area=b.get("area"))
            if b.get("run_id") in [x for x in eng_updates] or True:
                pass
    # tagline phrases Claude proposed that made it onto a downloaded resume
    for r in pending_runs:
        for n, t in enumerate(((r.get("final_model") or {}).get("tagline")) or []):
            add_phrase(f"{r['_id']}-tag{n}", "tagline", t, [], r["_id"], [], origin="claude-proposed")
    # anything else in the inbox (edits of library bullets, engagement bullets, older runs)
    for b in inbox:
        if b.get("section") in PHRASE_SECTIONS or b.get("section") == "engagement_details":
            continue
        if any(b["_id"] in it["source_ids"] for it in items.values()):
            continue
        if len(b.get("text", "")) < 15:
            continue
        add_item(f"inbox-{b['_id']}", b.get("run_id"), b.get("role"), b.get("achievement_id"), b["text"], b.get("tags"),
                 [b["_id"]], b.get("angle") or "learned", b.get("engagement_key"), b.get("longform"))
    for it in items.values():
        it["needs_polish"] = bool(it["issues"])
    SYNC_DIR.mkdir(exist_ok=True)
    pending = {"band": band, "longform_band": lband, "runs": [r["_id"] for r in runs], "pending_runs": [r["_id"] for r in pending_runs],
               "feedback": [f["_id"] for f in feedback], "inbox": [b["_id"] for b in inbox],
               "bullets": list(items.values()), "phrases": list(phrases.values()), "engagement_updates": eng_updates}
    jdump(pending, SYNC_DIR / "pending.json")
    need = [it for it in items.values() if it["needs_polish"]] + [p for p in phrases.values() if p["needs_polish"]]
    print(json.dumps({"status": "ready", "runs": len(runs), "pending_runs": len(pending_runs), "bullets": len(items),
                      "phrases": len(phrases), "engagement_updates": sorted(eng_updates), "needs_polish": len(need),
                      "feedback": len(feedback), "file": "sync/pending.json"}, indent=1))
    for it in need:
        print(f"  POLISH {it['key']} [{it.get('section') or 'bullet'}]: {', '.join(it['issues'])} :: {it['text'][:110]}")


def _model_from_run(con, r):
    """Full resume model for a run's PDF: the page's final_model (v2) when present, else rebuilt in the template."""
    m = r.get("final_model")
    if m and m.get("schema") == "rot-resume/2":
        m = json.loads(json.dumps(m))
        for sec in ("roles", "engagements"):
            for x in m.get(sec) or []:
                x["bullets"] = [btext(b) for b in x.get("bullets", [])]
        for e in m.get("education") or []:
            e.setdefault("bullets", [])
        return m
    fr = r.get("final_resume") or ({"roles": [{"key": x.get("key"), "bullets": x.get("bullets", [])} for x in (m or {}).get("roles", [])]} if m else None)
    if not fr:
        return None
    _, _, prof, base, _ = load_curation()
    tags = tag_index(con)
    req = {t: {"weight": float(w if not isinstance(w, dict) else w.get("weight", 1)), "phrases": []}
           for t, w in (r.get("requirements") or {}).items() if t in tags}
    res = assemble(con, req, base, prof, "run")
    roles = {x["key"]: x for x in res["roles"]}
    allroles = {ROLE_ALIAS.get(row["key"], row["key"]): dict(row) for row in con.execute("SELECT * FROM roles")}
    out_roles = []
    for rr in fr.get("roles", []):
        key = ROLE_ALIAS.get(rr.get("key"), rr.get("key"))
        info = roles.get(key) or allroles.get(key)
        if not info:
            continue
        bl = [btext(b) for b in rr.get("bullets", [])]
        out_roles.append({"key": key, "title": info["title"], "employer": info["employer"], "location": info.get("location"),
                          "dates": info.get("dates") or f"{fmt_date(info['start'])} – {fmt_date(info['end'])}",
                          "context": info.get("context") if "context" in info else " · ".join(x for x in (info.get("location"), info.get("context_line")) if x),
                          "bullets": bl})
    res["roles"] = out_roles
    printed = {norm(b) for x in out_roles for b in x["bullets"]}
    for e in res["engagements"]:
        e["bullets"] = [b for b in e["bullets"] if norm(b) not in printed]
    res["engagements"] = [e for e in res["engagements"] if e["bullets"]]
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
    lceil = (pend.get("longform_band") or {}).get("hard_ceiling", LONGFORM_CEILING)
    new_bullets, skipped = [], []
    gate2_map = {}   # run_id -> {page gate-2 id -> bank achievement id (or None when skipped)}
    known = {r["id"] for r in connect().execute("SELECT id FROM achievements")}
    for it in pend["bullets"]:
        p = polished.get(it["key"], it["text"])
        is_g2 = it.get("angle") == "gate2" and it.get("run_id") and it["key"].startswith(it["run_id"] + "-")
        gid = "gate2-" + it["key"] if is_g2 else None
        if p is None:
            skipped.append(it["key"])
            if gid: gate2_map.setdefault(it["run_id"], {})[gid] = None
            continue
        longform = it.get("longform")
        if isinstance(p, dict):   # {"text", optional "longform", "achievement_id" to fold into an existing accomplishment, "tags"}
            if p.get("achievement_id") in known:
                it["achievement_id"] = p["achievement_id"]
            if p.get("tags"):
                it["tags"] = p["tags"]
            if "longform" in p:
                longform = p.get("longform")
            p = p.get("text") or ""
        text = p.strip()
        if not text:
            skipped.append(it["key"]); continue
        limits = {**band, "hard_ceiling": lceil} if it.get("angle") == "longform" else band
        if bullet_checks(text, limits) and it["needs_polish"] and it["key"] not in polished:
            skipped.append(it["key"]); continue   # never learn an unpolished first-person / overlong answer
        if it.get("allowed_numbers") is not None:  # a number Tim never stated cannot be learned, polished or not
            allowed = set(it["allowed_numbers"])
            bad = sorted(CL.number_tokens(text) - allowed, key=float) + sorted(CL.number_tokens(longform or "") - allowed, key=float)
            if bad:
                skipped.append(f"{it['key']} (numbers not in the answer: {', '.join(bad)})")
                if gid: gate2_map.setdefault(it["run_id"], {})[gid] = None
                continue
        if longform and (FIRST_PERSON.search(longform) or len(longform) > lceil):
            longform = None                        # an unpolished long form is dropped; the short bullet still prints
        extra = {"engagement": it.get("engagement"), "longform": longform}
        extra["run_id"] = it.get("run_id")
        extra["q_ix"] = it.get("q_ix")
        if it["achievement_id"]:
            new_bullets.append({"achievement_id": it["achievement_id"], "angle": it["angle"], "text": text, "origin": "artifact", **extra})
            if gid: gate2_map.setdefault(it["run_id"], {})[gid] = it["achievement_id"]
        else:
            aid = "art-" + re.sub(r"[^a-z0-9-]", "", it["key"].lower())[:40]
            if gid: gate2_map.setdefault(it["run_id"], {})[gid] = aid
            new_bullets.append({"new_achievement": {"id": aid, "role": it["role"], "canonical": text,
                                                    "tags": {t: 1.0 for t in it["tags"]} or {"gtm-strategy": 0.3},
                                                    "confidence": "asserted", "origin": "artifact",
                                                    "notes": f"Learned from Match Desk run {it['run_id']}", "metrics": [],
                                                    "patterns": [], "variants": {}}, "origin": "artifact", **extra})
    # template-section phrases -> learned.json stores
    sections = {store: [] for store, _, _ in PHRASE_SECTIONS.values()}
    for ph in pend.get("phrases", []):
        v = polished.get(ph["key"], ph["text"])
        tags, area = ph.get("tags") or [], ph.get("area")
        if isinstance(v, dict):
            tags, area, v = v.get("tags") or tags, v.get("area") or area, v.get("text") or ""
        if v is None or not str(v).strip():
            skipped.append(ph["key"]); continue
        text = re.sub(r"\s+", " ", str(v)).strip()
        if phrase_checks(text, ph["section"]) and ph["needs_polish"] and ph["key"] not in polished:
            skipped.append(ph["key"]); continue
        store, field, _ = PHRASE_SECTIONS[ph["section"]]
        item = {field: text, "tags": tags, "origin": ph.get("origin", "artifact"), "run_id": ph.get("run_id"), "created": dt.datetime.now().isoformat(timespec="seconds")}
        if ph["section"] == "technology":
            item["category"] = "Learned"
        if ph["section"] == "competency":
            item["area"] = area
        sections[store].append(item)
    learn_runs = []
    for rid in pend["runs"]:
        r = runs.get(rid)
        if not r:
            continue
        learn_runs.append({"id": rid, "company": r.get("company"), "title": r.get("title"), "jd_text": r.get("jd_text", ""),
                           "requirements": r.get("requirements") or {}, "created": r.get("created"), "finalized": r.get("finalized"),
                           "downloaded_at": r.get("downloaded_at"), "outcome": r.get("outcome"), "prompt_versions": r.get("prompt_versions"),
                           "final_model": {"trace": (r.get("final_model") or {}).get("trace"), **{k: v for k, v in (r.get("final_model") or {}).items() if k != "trace"}} if r.get("final_model") else None,
                           "followups": [{"gate": 2, "question": f["question"], "answer": f.get("answer"), "tag": f.get("tag"), "q_ix": n,
                                          "section": f.get("section"), "engagement_key": f.get("engagement_key"), "role": f.get("role"), "fields": f.get("fields")}
                                         for n, f in enumerate(r.get("followups") or []) if f.get("answer")],
                           "feedback": [{"ext_id": fid, "bullet_id": f.get("bullet_id"), "action": f.get("action"),
                                         "edited_text": f.get("text") if f.get("action") == "edit" else None}
                                        for fid, f in feedback.items() if f.get("run_id") == rid and fid in pend["feedback"]]})
    SYNC_DIR.mkdir(exist_ok=True)
    eng_upd = {k: {**v, "run_id": next((rid for rid in pend["pending_runs"]), None)} for k, v in (pend.get("engagement_updates") or {}).items()}
    learnings = {"runs": learn_runs, "new_bullets": new_bullets, **sections, "engagement_updates": eng_upd}
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    jdump(learnings, SYNC_DIR / f"learnings-{stamp}.json")
    res = cmd_learn(argparse.Namespace(file=learnings, quiet_next=True))
    cmd_ingest(argparse.Namespace())
    cmd_export(argparse.Namespace())
    con = connect()
    # every downloaded run, rendered in the source template: Word document + PDF
    pdfs = []
    (ROOT / "out" / "runs").mkdir(parents=True, exist_ok=True)
    for rid in pend["pending_runs"]:
        r = runs.get(rid)
        m = _model_from_run(con, r) if r else None
        if not m:
            continue
        slug = re.sub(r"[^A-Za-z0-9]+", "_", (r.get("company") or "posting")).strip("_")
        base = ROOT / "out" / "runs" / f"{(r.get('created') or stamp)[:10]}_{slug}_{rid}"
        pdf, _, _ = write_outputs(m, base, con, strict=False)     # QA warnings are reported, never block a sync
        pdfs.append(str(Path(pdf).relative_to(ROOT)))
    cmd_profile_quiet()
    commit = None
    if not args.no_git:
        subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
        sec_lines = [f"- [{s}] {x.get('text') or x.get('name')}" for s, xs in sections.items() for x in xs]
        eng_lines = [f"- [engagement {k}] details: {', '.join(sorted(v))}" for k, v in (pend.get("engagement_updates") or {}).items()]
        msg = (f"Sync Match Desk: {len(learn_runs)} run(s), {res['new']} new bullet(s), {res.get('sections', 0)} template item(s), "
               f"{res.get('evidence', 0)} evidence row(s), {res.get('outcomes', 0)} outcome(s), {res['feedback']} feedback event(s)\n\n"
               + "\n".join([f"- {b.get('text') or b['new_achievement']['canonical']}" for b in new_bullets] + sec_lines + eng_lines)
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
           "synced_map": gate2_map,
           "learned": res, "skipped_unpolished": skipped, "pdfs": pdfs, "commit": commit,
           "synced_at": dt.datetime.now().astimezone().isoformat(timespec="seconds")}
    jdump(out, SYNC_DIR / "last_result.json")
    print(json.dumps(out, indent=1))


def cmd_claims(args):
    """rot.py claims <prefix>: claims whose id or subject starts with the prefix, with evidence and relations."""
    con = connect()
    like = args.prefix + "%"
    rows = con.execute("SELECT * FROM claims WHERE id LIKE ? OR subject LIKE ? ORDER BY subject, id", (like, like)).fetchall()
    if not rows:
        sys.exit(f"no claims match {args.prefix!r}")
    for c in rows:
        print(f"{c['id']}  [{c['kind']}] {c['status']} conf={c['confidence']}  value={c['value']!r}")
        print(f"    {c['text']}   ({c['confidence_basis']})" + (f"  valid {c['valid_from'] or '…'} → {c['valid_to'] or 'present'}" if c["valid_from"] or c["valid_to"] else ""))
        for e in con.execute("""SELECT ce.stance, e.id, e.source_type, e.authored_at, e.observed_at, e.quote FROM claim_evidence ce JOIN evidence e ON e.id=ce.evidence_id
                                WHERE ce.claim_id=? ORDER BY ce.stance DESC, e.authored_at""", (c["id"],)):
            print(f"      {e['stance']:11} {e['source_type']:17} {(e['authored_at'] or e['observed_at'] or '')[:10]:10} {e['id']:38} {e['quote'][:80]!r}")
        for r in con.execute("SELECT rel, to_claim, confidence, note FROM claim_relations WHERE from_claim=?", (c["id"],)):
            print(f"      → {r['rel']} {r['to_claim']}" + (f" ({r['note']})" if r["note"] else ""))
    print(f"{len(rows)} claim(s)")


def cmd_profile_quiet():
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_profile(argparse.Namespace())


# ---------------------------------------------------------------- data profile
def cmd_profile(args):
    con = connect()
    band = json.loads(con.execute("SELECT value FROM meta WHERE key='length_band'").fetchone()[0])
    L = ["# Data Profile: resume.db", f"Generated {dt.date.today().isoformat()} by `rot.py profile`.", "",
         "## The four tiers", "", "| Tier | Tables | Rows |", "|---|---|---|"]
    for t, label in CL.TIER_LABELS.items():
        tabs = [tb for tb, tier in TIERS.items() if tier == t]
        n = sum(con.execute(f"SELECT COUNT(*) FROM {tb}").fetchone()[0] for tb in tabs if con.execute("SELECT name FROM sqlite_master WHERE name=?", (tb,)).fetchone())
        L.append(f"| {t}. {label} | {', '.join(f'`{tb}`' for tb in tabs)} | {n} |")
    L += ["", "## Claims", "", "| Kind | Active | Disputed | Retired | Mean confidence |", "|---|---|---|---|---|"]
    for r in con.execute("""SELECT kind, SUM(status='active') a, SUM(status='disputed') d, SUM(status='retired') r, ROUND(AVG(CASE WHEN status='active' THEN confidence END),3) c
                            FROM claims GROUP BY kind ORDER BY kind"""):
        L.append(f"| {r['kind']} | {r['a']} | {r['d']} | {r['r']} | {r['c']} |")
    L += ["", "| Evidence source type | Rows |", "|---|---|"]
    for r in con.execute("SELECT source_type, COUNT(*) n FROM evidence GROUP BY source_type ORDER BY n DESC"):
        L.append(f"| {r['source_type']} | {r['n']} |")
    disp = con.execute("SELECT id, value, confidence_basis FROM claims WHERE status='disputed'").fetchall()
    L += ["", f"Disputed claims: **{len(disp)}**" + ("" if not disp else " · " + "; ".join(f"`{d['id']}` = {d['value']!r}" for d in disp)), "",
          "## Overview", "", "| Table | Rows | Grain |", "|---|---|---|"]
    grains = {"sources": "one resume version / capture", "raw_bullets": "one bullet as written in one source",
              "achievements": "one real accomplishment", "bullets": "one bare-bone rendering of an achievement (all versions)",
              "tags": "one niche skill/keyword", "achievement_tags": "achievement × tag (one-to-many)",
              "achievement_evidence": "achievement × raw bullet", "competencies": "one competency phrase",
              "technologies": "one tool", "certifications": "one credential", "summaries": "one summary variant",
              "tagline_phrases": "one Section A tagline phrase", "engagements": "one Section C consulting engagement",
              "engagement_achievements": "engagement × achievement (long-form bullet)", "core_competencies": "one Section D item",
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
    b = sp.add_parser("build"); b.add_argument("--jd"); b.add_argument("--name"); b.add_argument("--version", default="v1"); b.add_argument("--force", action="store_true", help="write even when QA finds errors"); b.set_defaults(fn=cmd_build)
    c = sp.add_parser("check", help="tier-3 QA of a resume model JSON: claim trace, numbers vs evidence, disputed claims, bands"); c.add_argument("model"); c.set_defaults(fn=cmd_check)
    sp.add_parser("export").set_defaults(fn=cmd_export)
    l = sp.add_parser("learn"); l.add_argument("file"); l.set_defaults(fn=cmd_learn)
    cl = sp.add_parser("claims", help="show claims with their evidence and relations"); cl.add_argument("prefix"); cl.set_defaults(fn=cmd_claims)
    sp.add_parser("profile").set_defaults(fn=cmd_profile)
    s1 = sp.add_parser("sync-prepare"); s1.add_argument("--dump", default=str(ROOT / "sync" / "dump")); s1.add_argument("--all", action="store_true"); s1.set_defaults(fn=cmd_sync_prepare)
    s2 = sp.add_parser("sync-apply"); s2.add_argument("--dump", default=str(ROOT / "sync" / "dump")); s2.add_argument("--no-git", action="store_true"); s2.set_defaults(fn=cmd_sync_apply)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
