"""Derive the Hub's GTM taxonomy v1 (core/taxonomy/gtm_v1.json) from the private taxonomy (curation/taxonomy.json).

The private file stays untouched. The derivation is declarative and printed, so a change is a review of this file:
- families and tags that only describe Tim's own history are dropped (fundraising, legal, healthcare regulatory, exit paths...);
- board-advisory becomes executive-advisory with general wording;
- person-specific synonyms are removed;
- gaps for revenue operations, marketing, partnerships, sales and customer roles are filled with new tags.
Every synonym is lowercase and belongs to exactly one tag; a new synonym that already exists elsewhere is skipped and reported.

    python tools/derive_taxonomy.py            write core/taxonomy/gtm_v1.json and print the summary
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "curation" / "taxonomy.json"
OUT = ROOT / "core" / "taxonomy" / "gtm_v1.json"

DROP_FAMILIES = {"fundraising", "legal"}
DROP_TAGS = {"healthcare-regulatory", "exit-path-modeling", "funding-source-diagnostics", "capital-strategy", "feasibility-roadmap", "buy-vs-build"}
RENAME = {"board-advisory": ("executive-advisory", "Executive & Board Advisory",
                             ["advisory", "advisor", "board", "board of directors", "executive advisor", "strategic advisor", "fractional", "advise founders", "board updates"])}
MOVE_FAMILY = {"crm-discipline": "revops", "forecasting": "revops", "pipeline-management": "revops", "territory-design": "revops", "capacity-planning": "revops"}
# synonyms that name Tim's own employers, clients or leagues rather than a skill
STRIP_SYNONYMS = re.compile(r"\b(nfl|mlb|nba|nhl|liminal|teksystems|psp|new york life|demanddrive|fortune 500)\b", re.I)
NEW_FAMILIES = {"revops": "Revenue Operations"}
NEW_TAGS = {
    # revenue operations
    "lead-routing-sla": ("revops", "Lead Routing & SLAs", ["lead routing", "routing rules", "speed-to-lead", "speed to lead", "sla", "slas", "service level agreement", "lead assignment", "lead response time"]),
    "sales-process-stages": ("revops", "Sales Process & Stage Definitions", ["sales process", "stage definitions", "pipeline stages", "deal stages", "sales methodology", "exit criteria", "opportunity stages"]),
    "revenue-analytics": ("revops", "Revenue Analytics & Dashboards", ["revenue analytics", "dashboards", "dashboard", "reporting", "kpi", "kpis", "pipeline coverage", "win rate", "win rates", "looker", "tableau", "power bi", "sales analytics"]),
    "sales-compensation": ("revops", "Sales Compensation", ["sales compensation", "comp plan", "comp plans", "commission", "commissions", "quota setting", "incentive plan", "spiffs"]),
    "deal-desk": ("revops", "Deal Desk & Quote-to-Cash", ["deal desk", "quote-to-cash", "quote to cash", "cpq", "approval workflow", "discount approval", "order forms", "contract desk"]),
    "tech-stack-consolidation": ("revops", "Systems & Tech Stack Consolidation", ["consolidation", "consolidate", "consolidating", "crm consolidation", "tech stack", "salesforce administration", "salesforce admin", "crm migration", "systems integration", "revenue tech stack"]),
    # marketing
    "lifecycle-email": ("marketing", "Lifecycle & Email Marketing", ["lifecycle", "lifecycle marketing", "email marketing", "newsletter", "newsletters", "esp", "klaviyo", "drip", "nurture", "win-back", "open rate", "click rate"]),
    "paid-media": ("marketing", "Paid Media", ["paid media", "paid social", "paid search", "ppc", "media buying", "google ads", "meta ads", "performance marketing", "ad spend"]),
    "seo-sem": ("marketing", "SEO & SEM", ["seo", "sem", "search engine optimization", "organic search", "keywords", "search marketing"]),
    "product-marketing": ("marketing", "Product Marketing", ["product marketing", "launch messaging", "competitive positioning", "sales enablement content", "product launches", "go-to-market messaging"]),
    "marketing-analytics-attribution": ("marketing", "Marketing Analytics & Attribution", ["attribution", "ga4", "google analytics", "cohort", "cohorts", "marketing analytics", "conversion rate optimization", "cro", "funnel analytics"]),
    "events-field": ("marketing", "Events & Field Marketing", ["events", "field marketing", "webinars", "webinar", "conferences", "trade shows", "event marketing"]),
    "audience-growth": ("marketing", "Audience & Subscriber Growth", ["subscriber", "subscribers", "audience growth", "subscriber base", "newsletter growth", "followers", "community growth", "audience"]),
    "budget-ownership": ("marketing", "Budget Ownership", ["budget", "media budget", "annual budget", "spend", "seven-figure budget", "p&l ownership", "budget ownership"]),
    # partnerships
    "partner-enablement": ("partnerships", "Partner Enablement", ["partner enablement", "certification program", "partner training", "partner portal", "certify partners", "partner certification"]),
    "co-marketing": ("partnerships", "Co-Marketing & Co-Selling", ["co-marketing", "joint marketing", "co-selling", "joint go-to-market", "partner campaigns", "joint campaigns"]),
    "partner-recruitment": ("partnerships", "Partner Recruitment", ["partner recruitment", "recruit partners", "agency partners", "holding company", "holding companies", "reseller", "resellers", "agency relationships"]),
    "alliances-ecosystem": ("partnerships", "Alliances & Ecosystem", ["alliances", "ecosystem", "technology partners", "isv", "isvs", "marketplace", "ecosystem partners"]),
    # sales
    "outbound-sequencing": ("sales", "Outbound & Sequencing", ["outbound", "sequences", "cadences", "cold outreach", "cold calling", "email sequences", "outreach.io", "salesloft"]),
    "enterprise-sales": ("sales", "Enterprise Sales", ["enterprise sales", "enterprise accounts", "complex sales", "strategic accounts", "named accounts", "enterprise brands", "enterprise deals", "enterprise buyers", "large enterprise", "global accounts", "enterprise segment"]),
    "sdr-management": ("sales", "SDR Team Management", ["sdr", "sdrs", "bdr", "bdrs", "sales development", "sdr team", "meetings booked", "qualified meetings"]),
    # customer
    "renewals-retention": ("customer", "Renewals & Retention", ["renewal", "renewals", "retention", "churn", "net revenue retention", "nrr", "expansion revenue", "annual commitment", "annual commitments"]),
    # onboarding and adoption already live under customer-success; no separate tag
    # media
    "retail-media": ("media", "Retail Media", ["retail media", "retail media network", "retail media networks", "sponsored products", "onsite display", "offsite audiences", "shopper marketing", "cpg"]),
}


def main():
    src = json.loads(SRC.read_text(encoding="utf-8"))
    families = {k: v for k, v in src["families"].items() if k not in DROP_FAMILIES}
    families.update(NEW_FAMILIES)
    tags, notes = {}, []
    for tid, t in src["tags"].items():
        if t["family"] in DROP_FAMILIES or tid in DROP_TAGS:
            notes.append(f"dropped {tid}")
            continue
        new_id, label, syns = tid, t["label"], list(t["synonyms"])
        if tid in RENAME:
            new_id, label, syns = RENAME[tid]
            notes.append(f"renamed {tid} -> {new_id}")
        kept = [s.lower() for s in syns if not STRIP_SYNONYMS.search(s)]
        if len(kept) != len(syns):
            notes.append(f"{new_id}: stripped {sorted(set(syns) - set(kept))}")
        tags[new_id] = {"family": MOVE_FAMILY.get(tid, t["family"]), "label": label, "synonyms": kept}
    # the private file lets a synonym sit in two tags; here each belongs to one: the tag whose id contains the word, else the first
    owner = {}
    for tid, t in tags.items():
        for s in list(t["synonyms"]):
            if s in owner and owner[s] != tid:
                loser, winner = (owner[s], tid) if (s.split()[0] in tid and s.split()[0] not in owner[s]) else (tid, owner[s])
                tags[loser]["synonyms"].remove(s)
                notes.append(f"'{s}' was in {owner[s]} and {tid}: kept in {winner}")
                if winner == tid:
                    owner[s] = tid
                continue
            owner[s] = tid
    for tid, (fam, label, syns) in NEW_TAGS.items():
        assert tid not in tags, tid
        keep = []
        for s in syns:
            s = s.lower()
            if s in owner and owner[s] != tid:
                notes.append(f"{tid}: '{s}' already belongs to {owner[s]}, skipped")
                continue
            owner[s] = tid
            keep.append(s)
        assert len(keep) >= 3, (tid, keep)
        tags[tid] = {"family": fam, "label": label, "synonyms": keep}
    # every synonym lowercase, unique, at least three per tag; every family used
    seen = {}
    for tid, t in tags.items():
        assert t["family"] in families, (tid, t["family"])
        assert len(t["synonyms"]) >= 3, tid
        for s in t["synonyms"]:
            assert s == s.lower(), (tid, s)
            assert s not in seen or seen[s] == tid, (s, seen.get(s), tid)
            seen[s] = tid
    families = {k: v for k, v in families.items() if any(t["family"] == k for t in tags.values())}
    out = {"version": "gtm/1", "_about": "Career Companion Hub skill taxonomy v1 for go-to-market, sales, marketing and revenue roles. Derived by tools/derive_taxonomy.py; edit that file, not this one. Shape: families {id: label}, tags {id: {family, label, synonyms}}; a posting is matched on whole-word synonyms.",
           "families": families, "tags": dict(sorted(tags.items(), key=lambda kv: (kv[1]["family"], kv[0])))}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    byfam = {}
    for tid, t in tags.items():
        byfam.setdefault(t["family"], []).append(tid)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(tags)} tags in {len(families)} families, {len(seen)} synonyms")
    for f in families:
        print(f"  {f} ({families[f]}): {len(byfam.get(f, []))}")
    for n in notes:
        print("  -", n)


if __name__ == "__main__":
    main()
