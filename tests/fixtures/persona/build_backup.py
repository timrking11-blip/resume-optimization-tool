"""Riley Mahoney as a cch-backup/1: the result an intake of the four persona documents should produce.

Every accomplishment wording from every document is an evidence row; the newest resume's wording is the canonical
text; the deliberate traps become the shapes the core must handle: the pipeline metric that differs between two
resumes is an unresolved contradiction (disputed, never printed), the Kestrel end date and the Pinecrest title are
disputed role facts (the stronger value prints with a warning), the three formats of one amount are plain support.
Tags are left empty: the Hub and the tests fill them with the engine's tagger, as the Hub does at entry time.

    python tests/fixtures/persona/build_backup.py      writes tests/fixtures/persona/riley_backup.json
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_persona as P  # noqa: E402

DOCS = {"v1": ("src:v1", "resume", "HISTORICAL_RESUME", "2026-03-02", "resume_v1_classic.docx"),
        "v2": ("src:v2", "resume", "HISTORICAL_RESUME", "2025-11-14", "resume_v2_media_partnerships.docx"),
        "v3": ("src:v3", "resume", "HISTORICAL_RESUME", "2026-08-20", "resume_v3_revops.docx"),
        "li": ("src:li", "linkedin", "PUBLIC_PROFILE", "2026-09-20", "linkedin_profile.pdf")}
STRENGTH_ORDER = ["v3", "v1", "v2", "li"]            # the wording that becomes canonical: strongest source, newest first
ROLE_DOCS = {"hal": ["v1", "v2", "v3", "li"], "kes": ["v1", "v2", "v3", "li"], "pin": ["v1", "v2", "v3", "li"], "qui": ["v1", "li"], "lark": ["v3", "li"]}
TITLES = P.PERSONA["roles"]
SKILLS = ["Retail media networks", "Agency partnerships", "ROAS and CPM business cases", "Discovery and multi-stakeholder selling",
          "Newsletter and lifecycle marketing", "Paid social", "Budget ownership", "Forecasting", "Territory design", "Lead routing",
          "Pricing and packaging", "CRM consolidation", "ICP definition", "Discovery interviews", "Pilot programs"]


def main():
    sources, evidence, subjects, achievements = [], [], [], []
    for d, (sid, kind, st, date, file) in DOCS.items():
        sources.append({"id": sid, "kind": kind, "label": file, "authored_at": date, "observed_at": "2026-09-28", "source_type": st})

    def ev(doc, key, quote, locator):
        eid = f"ev:{doc}:{key}"
        evidence.append({"id": eid, "source": DOCS[doc][0], "source_type": DOCS[doc][2], "channel": f"upload:{DOCS[doc][1]}", "quote": quote,
                         "observed_at": DOCS[doc][3], "locator": locator})
        return eid

    # roles: one header evidence row per document, facts cite it; the deliberate conflicts stay unresolved
    order = ["hal", "lark", "kes", "pin", "qui"]
    for i, key in enumerate(order):
        r = P.ROLES[key]
        facts = {p: {"value": None, "evidence": [], "contradicting": []} for p in ("title", "employer", "location", "start", "end")}
        for doc in ROLE_DOCS[key]:
            title = TITLES[key]["titles_by_source"].get(doc, r["title"])
            start, end = r["start"], r["end"]
            if key == "kes" and doc == "v1":
                start_txt, end_txt, sv, evv = "2021", "2024", "2021", "2024"
            else:
                start_txt, end_txt, sv, evv = P.fmt(start, short=(doc in ("v2", "li"))), P.fmt(end, short=(doc in ("v2", "li"))), start, end
            head = {"v1": f"{title} | {r['employer']} | {r['loc']}  {start_txt} – {end_txt}", "v2": f"{r['employer']} — {title} ({r['loc']}) · {start_txt} – {end_txt}",
                    "v3": f"{title}, {r['employer']}  {start_txt} – {end_txt}  {r['loc']}", "li": f"{r['employer']} / {title} / {start_txt} - {end_txt}"}[doc]
            eid = ev(doc, f"role:{key}", head, f"role header ({doc})")
            for p, v in (("title", title), ("employer", r["employer"]), ("location", r["loc"]), ("start", sv), ("end", evv)):
                f = facts[p]
                if f["value"] is None or v == f["value"] or (p in ("start", "end") and v and f["value"] and (v.startswith(f["value"]) or f["value"].startswith(v))):
                    if f["value"] is None or (p in ("start", "end") and v and len(v) > len(f["value"] or "")):
                        f["value"] = v
                    f["evidence"].append(eid)
                else:
                    c = next((c for c in f["contradicting"] if c["value"] == v), None)
                    if c:
                        c["evidence"].append(eid)
                    else:
                        f["contradicting"].append({"value": v, "evidence": [eid]})
        # the stronger reading wins the primary slot: a majority of sources, else the newest resume
        for p, f in facts.items():
            if f["contradicting"]:
                best = max([{"value": f["value"], "evidence": f["evidence"]}] + f["contradicting"], key=lambda c: (len(c["evidence"]), c["value"]))
                others = [c for c in [{"value": f["value"], "evidence": f["evidence"]}] + f["contradicting"] if c is not best]
                f["value"], f["evidence"], f["contradicting"] = best["value"], best["evidence"], others
        subjects.append({"id": f"role:{key}", "kind": "role", "key": key, "sort": i + 1, "hidden": key == "qui", "facts": facts})

    # accomplishments: every wording is evidence; the strongest source's wording is canonical; hal-pipeline stays contradicted
    for aid, words in P.A.items():
        role = aid.split("-")[0]
        eids = {doc: ev(doc, aid, text, f"bullet ({doc})") for doc, text in words.items()}
        canon_doc = next(d for d in STRENGTH_ORDER if d in words)
        entry = {"id": aid, "role": role, "canonical": words[canon_doc], "evidence": list(eids.values()), "tags": {}, "metrics": [],
                 "origin": "intake", "contradicting": []}
        if aid == "hal-pipeline":
            entry["evidence"] = [eids["v3"]]
            entry["contradicting"] = [{"value": words["v1"], "evidence": [eids["v1"]]}]
        achievements.append(entry)

    # education, credentials, tools, skills
    edu_ev = [ev(d, "edu", "Lakeside State University — B.A., Communication, 2016", "education") for d in DOCS]
    subjects.append({"id": "edu:lakeside", "kind": "education", "facts": {"school": {"value": "Lakeside State University", "evidence": edu_ev},
                                                                             "degree": {"value": "B.A., Communication", "evidence": edu_ev},
                                                                             "date": {"value": "2016", "evidence": edu_ev}}})
    for cid, name, issuer, date, docs in (("cred:hubspot-revops", "HubSpot Revenue Operations Certification", "HubSpot", "2023", ["v1", "v2", "v3", "li"]),
                                          ("cred:ga-iq", "Google Analytics Individual Qualification", "Google", "2020", ["v2"]),
                                          ("cred:sf-trailhead", "Salesforce Trailhead: Sales Cloud Basics", "Salesforce", None, ["li"])):
        ce = [ev(d, cid.split(":")[1], f"{name} ({date})" if date else name, "certification") for d in docs]
        facts = {"name": {"value": name, "evidence": ce}, "issuer": {"value": issuer, "evidence": ce}}
        if date:
            facts["date"] = {"value": date, "evidence": ce}
        subjects.append({"id": cid, "kind": "credential", "facts": facts})
    slug = lambda n: n.lower().replace(" ", "-").replace(".", "").replace(",", "")
    tools = {}
    for d, names in P.PERSONA["tools_by_source"].items():
        for n in names:
            tools.setdefault(n, []).append(ev(d, "tool:" + slug(n), n, "tools line"))
    for k, (n, ce) in enumerate(tools.items()):
        subjects.append({"id": "tool:" + slug(n), "kind": "tool", "sort": k, "facts": {"name": {"value": n, "evidence": ce}}})
    for k, sk in enumerate(SKILLS):
        e = ev("v3" if k >= 7 else "v2", "skill:" + sk.lower().replace(" ", "-"), sk, "skills")
        subjects.append({"id": "skill:" + sk.lower().replace(" ", "-").replace(",", ""), "kind": "expertise", "sort": k, "facts": {"text": {"value": sk, "evidence": [e]}}})

    backup = {"schema": "cch-backup/1", "core": "1.1.0", "exported_at": "2026-09-28T00:00:00Z", "edition": "hub", "fixture": "riley-mahoney/1",
              "identity": {"name": P.NAME, "location": "Denver, CO", "phone": "(555) 010-0199", "email": "riley.mahoney@example.com",
                           "links": [{"label": "LinkedIn", "url": "https://www.linkedin.com/in/rileymahoney-example"}]},
              "sources": sources, "evidence": evidence, "subjects": subjects, "achievements": achievements,
              "taxonomy": {"id": "gtm/1", "user_tags": {}}, "settings": {}, "sessions": [], "feedback": [], "outcomes": [], "review_log": []}
    out = HERE / "riley_backup.json"
    out.write_text(json.dumps(backup, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    disputed = [s["id"] + ":" + p for s in subjects for p, f in s.get("facts", {}).items() if f.get("contradicting")] + [a["id"] for a in achievements if a["contradicting"]]
    print(f"wrote {out.name}: {len(sources)} sources, {len(evidence)} evidence rows, {len(subjects)} subjects, {len(achievements)} achievements; unresolved: {disputed}")


if __name__ == "__main__":
    main()
