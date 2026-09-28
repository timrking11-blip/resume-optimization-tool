"""Build the Hub's neutral source document, hub/template/neutral_template.docx, deterministically.

The document is a sample resume in the neutral-1 layout (core/layouts/neutral-1.json): one column, Calibri, standard
headings, real Word bullets, no tables or text boxes. make_template.py reads it for its page setup, list definitions and
theme, and writes hub/template/docx_template.json:

    python hub/template/make_neutral.py
    python make_template.py --source hub/template/neutral_template.docx --layout core/layouts/neutral-1.json --out hub/template/docx_template.json

Running it twice gives byte-identical files (fixed timestamps). The sample text is placeholder copy, not a person.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.docx_writer import Doc, run  # noqa: E402

OUT = ROOT / "hub" / "template" / "neutral_template.docx"
LAYOUT = json.loads((ROOT / "core" / "layouts" / "neutral-1.json").read_text(encoding="utf-8"))
HEAD = {s["kind"]: s["heading"] for s in LAYOUT["sections"] if s.get("heading")}
ACCENT = LAYOUT["theme"]["accent"]


def main():
    d = Doc(title="Resume", author="Career Companion Hub", stamp="2026-01-01T00:00:00Z", page=(12240, 15840), margins=(1008, 1008, 1008, 1008))
    cw = d.content_width
    heading = lambda t: d.p([run(t, b=True, color=ACCENT, sz=20)], style="Heading1", keep_next=True, before=240, after=100)
    d.p([run("Full Name", b=True, color=ACCENT, sz=32)], jc="center", after=40)
    d.p([run("City, ST | (000) 000-0000 | name@example.com | linkedin.com/in/name", color="444444")], jc="center", after=200)
    heading("Summary")
    d.p("Two or three sentences a reader can verify against the lines below: the roles held, the scope carried and one or two results with numbers.", jc="both", after=100)
    heading("Skills")
    d.p("Skill One • Skill Two • Skill Three • Skill Four", after=100)
    d.p([run("Tools", b=True, u=True), run(":", b=True)], keep_next=True)
    d.p("Tool A, Tool B, Tool C")
    heading("Experience")
    d.p([run("Title | Employer |", b=True), "<w:r><w:tab/></w:r>", run("January 2024 – Present")], tab_right=cw, keep_next=True)
    d.p([run("City, ST", color="6B6B6B", sz=16)], keep_next=True, after=100)
    d.bullet("Verb-first line with the scope and a measurable result, in one sentence.", num=1, after=80)
    d.bullet("Second accomplishment for the same role, with a number the reader can check.", num=1, after=240)
    heading("Consulting & Advisory")
    d.p([run("Client, as it should print", b=True), run(" | City, ST |", b=True, i=True), run(" February 2023 – August 2023", b=True), run(" (Part Time)")], keep_next=True, after=80)
    d.p([run("One-line description of the engagement", i=True)], keep_next=True, after=80)
    d.bullet("A longer Section C style line: what was delivered, how, and what changed as a result, in up to two sentences.", num=5, after=160)
    heading("Education")
    d.p([run("University", b=True)], keep_next=True, after=20)
    d.p([run("Degree, Field | Year", i=True, color="444444")], after=100)
    heading("Certifications")
    d.bullet("Certification Name — Issuer", num=5, after=40)
    # a list the layout does not print but make_template expects a definition for (core competencies)
    d.p([run("Area: item, item", color="FFFFFF", sz=2)], style="ListParagraph", num=2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    d.write(OUT)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
