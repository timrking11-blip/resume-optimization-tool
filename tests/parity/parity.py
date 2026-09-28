"""Twin parity: rot.py and the page must build the same Word body from the same data, today.

    python tests/parity/parity.py

rot.py's assemble() + docx_bytes() run against resume.db and curation/ (opened read-only, nothing written), and the
page's resumeModel() + documentXml() run inside Node against data/library.json, the bank rot.py exported from that
same database. The two word/document.xml strings must be identical. This is a live equality rather than a golden
because the hourly sync moves both sides together; the page's own goldens (legacy_oracle.js) pin the bank instead.
"""
import io
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import rot  # noqa: E402


def python_xml():
    con = sqlite3.connect(f"file:{rot.DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    _, _, prof, base, _ = rot.load_curation()
    model = rot.assemble(con, {}, base, prof, "parity")
    with zipfile.ZipFile(io.BytesIO(rot.docx_bytes(model))) as z:
        return z.read("word/document.xml").decode("utf-8")


def page_xml():
    r = subprocess.run(["node", str(ROOT / "tests" / "parity" / "legacy_oracle.js"), "--emit", "baseline", "document.xml", "--lib", "data/library.json"],
                       cwd=ROOT, capture_output=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"page render failed:\n{r.stderr}")
    return r.stdout


def first_diff(a, b):
    al, bl = a.split("\n"), b.split("\n")
    for i in range(max(len(al), len(bl))):
        x = al[i] if i < len(al) else "<end>"
        y = bl[i] if i < len(bl) else "<end>"
        if x != y:
            return i + 1, x[:160], y[:160]
    return None


def main():
    py, page = python_xml(), page_xml()
    d = first_diff(page, py)
    if d:
        print(f"FAIL rot.py and the page disagree on the baseline document.xml at line {d[0]}\n  page:   {d[1]}\n  python: {d[2]}")
        sys.exit(1)
    print(f"twin parity OK: rot.py and the page build the same baseline document.xml ({len(py)} chars)")


if __name__ == "__main__":
    main()
