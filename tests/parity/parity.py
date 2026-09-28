"""Python twin parity for the baseline resume.

    python tests/parity/parity.py --write    record rot.py's own golden (golden/baseline/python_document.xml)
    python tests/parity/parity.py            check rot.py against that golden (exit 1 on a difference) and report,
                                             for information only, whether it also equals the page's document.xml

rot.py's assemble() + docx_bytes() must keep producing the same Word body while the layout abstraction lands
(Phase 1 step 4). The database is opened read-only; nothing is written to resume.db or to out/.
"""
import io
import sqlite3
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import rot  # noqa: E402

GOLD = Path(__file__).parent / "golden" / "baseline"
PY_GOLD = GOLD / "python_document.xml"


def build_xml():
    con = sqlite3.connect(f"file:{rot.DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    _, _, prof, base, _ = rot.load_curation()
    model = rot.assemble(con, {}, base, prof, "parity")
    data = rot.docx_bytes(model)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return z.read("word/document.xml").decode("utf-8")


def first_diff(a, b):
    al, bl = a.split("\n"), b.split("\n")
    for i in range(max(len(al), len(bl))):
        x = al[i] if i < len(al) else "<end>"
        y = bl[i] if i < len(bl) else "<end>"
        if x != y:
            return i + 1, x[:160], y[:160]
    return None


def main():
    xml = build_xml()
    if "--write" in sys.argv:
        PY_GOLD.parent.mkdir(parents=True, exist_ok=True)
        PY_GOLD.write_text(xml, encoding="utf-8")
        print(f"wrote {PY_GOLD.relative_to(ROOT)} ({len(xml)} chars)")
    else:
        if not PY_GOLD.exists():
            print("MISSING python golden (run --write first)")
            sys.exit(1)
        want = PY_GOLD.read_text(encoding="utf-8")
        if want != xml:
            line, x, y = first_diff(want, xml)
            print(f"FAIL rot.py document.xml differs from its golden at line {line}\n  expected: {x}\n  actual:   {y}")
            sys.exit(1)
        print("python parity OK: rot.py document.xml identical to its golden")
    page = GOLD / "document.xml"
    if page.exists():
        d = first_diff(page.read_text(encoding="utf-8"), xml)
        print("page == python: identical" if not d else f"page != python (pre-existing, informational): first difference at line {d[0]}\n  page:   {d[1]}\n  python: {d[2]}")


if __name__ == "__main__":
    main()
