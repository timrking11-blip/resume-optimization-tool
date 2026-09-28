"""Twin parity: rot.py and the page must build the same Word body from the same data, today.

    python tests/parity/parity.py

rot.py's assemble() + docx_bytes() run against resume.db and curation/ (opened read-only, nothing written), and the
page's resumeModel() + documentXml() run inside Node against data/library.json, the bank rot.py exported from that
same database. The two word/document.xml strings must be identical. This is a live equality rather than a golden
because the hourly sync moves both sides together; the page's own goldens (legacy_oracle.js) pin the bank instead.
"""
import io
import json
import re
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import rot  # noqa: E402


STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def python_parts():
    """Every part of rot.py's .docx, in zip order, with the timestamp normalized."""
    con = sqlite3.connect(f"file:{rot.DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    _, _, prof, base, _ = rot.load_curation()
    model = rot.assemble(con, {}, base, prof, "parity")
    with zipfile.ZipFile(io.BytesIO(rot.docx_bytes(model))) as z:
        return {n: STAMP.sub("STAMP", z.read(n).decode("utf-8")) for n in z.namelist()}


def page_parts():
    r = subprocess.run(["node", str(ROOT / "tests" / "parity" / "legacy_oracle.js"), "--emit", "baseline", "parts.json", "--lib", "data/library.json"],
                       cwd=ROOT, capture_output=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"page render failed:\n{r.stderr}")
    return json.loads(r.stdout)


def first_diff(a, b):
    al, bl = a.split("\n"), b.split("\n")
    for i in range(max(len(al), len(bl))):
        x = al[i] if i < len(al) else "<end>"
        y = bl[i] if i < len(bl) else "<end>"
        if x != y:
            return i + 1, x[:160], y[:160]
    return None


def main():
    py, page = python_parts(), page_parts()
    if list(py) != list(page):
        print(f"FAIL part order differs\n  python: {list(py)}\n  page:   {list(page)}")
        sys.exit(1)
    for name in py:
        d = first_diff(page[name], py[name])
        if d:
            print(f"FAIL rot.py and the page disagree on {name} at line {d[0]}\n  page:   {d[1]}\n  python: {d[2]}")
            sys.exit(1)
    print(f"twin parity OK: rot.py and the page build the same baseline .docx, all {len(py)} parts ({len(py['word/document.xml'])} chars of document.xml)")


if __name__ == "__main__":
    main()
