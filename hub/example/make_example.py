"""The Hub's example person: the test persona (Riley Mahoney, fictional) with its clerical disagreements already settled and
exactly one discrepancy left open, chosen because it takes judgment rather than a lookup: the latest resume says Riley
*owned* pricing and packaging for the mid-market tier; the LinkedIn profile says Riley *partnered with product marketing and
finance* on it. Same tier, same $1.2M ARR, a different claim about the person's part in it.

    python hub/example/make_example.py        -> hub/example/backup.json (published beside the Hub as example/backup.json)

tests/fixtures/persona/riley_backup.json is left untouched; the tests keep their fixture."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tests" / "fixtures" / "persona" / "riley_backup.json"
OUT = Path(__file__).resolve().parent / "backup.json"
SETTLED = "2026-09-21"

b = json.loads(SRC.read_text(encoding="utf-8"))
subjects = {s["id"]: s for s in b["subjects"]}
achievements = {a["id"]: a for a in b["achievements"]}
evidence = {e["id"]: e for e in b["evidence"]}

# clerical disagreements the persona carries for the tests: settled here, kept as history
subjects["role:kes"]["facts"]["end"]["resolution"] = {"value": "2023-11", "why": "offer letter for the next role is dated December 2023", "at": SETTLED}
subjects["role:pin"]["facts"]["title"]["resolution"] = {"value": "Senior Marketing Manager", "why": "title on the 2020 promotion letter", "at": SETTLED}
achievements["hal-pipeline"]["resolution"] = {"value": achievements["hal-pipeline"]["canonical"], "why": "pipeline report at hand-off shows $6.8M", "at": SETTLED}

# the one open discrepancy: ownership of the pricing work
a = achievements["hal-pricing"]
li = evidence["ev:li:hal-pricing"]
li["quote"] = "Partnered with product marketing and finance on pricing and packaging for the new mid-market tier; the tier reached $1.2M ARR in its first year."
a["evidence"] = [i for i in a["evidence"] if i != "ev:li:hal-pricing"]
a["contradicting"] = [{"value": li["quote"], "evidence": ["ev:li:hal-pricing"]}]
a.pop("resolution", None)

b["fixture"] = "riley-mahoney/1 · hub example"
b["meta"] = {"created_at": SETTLED, "last_backup_at": None, "entries": len(b["achievements"]),
             "note": "Fictional record for the Career Companion Hub demo. One discrepancy is left open on purpose: the Halcyon pricing entry."}
OUT.write_text(json.dumps(b, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
open_conflicts = [s["id"] + ":" + p for s in b["subjects"] for p, f in s["facts"].items() if f.get("contradicting") and not f.get("resolution")]
open_conflicts += ["ach:" + x["id"] for x in b["achievements"] if x.get("contradicting") and not x.get("resolution")]
print("wrote", OUT.relative_to(ROOT), "· open discrepancies:", open_conflicts)
