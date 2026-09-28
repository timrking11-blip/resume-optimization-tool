"""Run every check: node unit tests, the page parity oracle, and the Python parity scripts. Exit 1 on any failure.

    python tests/run.py            everything
    python tests/run.py --fast     unit tests only
"""
import glob
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fast = "--fast" in sys.argv
steps = []
unit = sorted(glob.glob(str(ROOT / "tests" / "**" / "*.test.js"), recursive=True))
if unit:
    steps.append(("node unit tests", ["node", "--test", *unit]))
if not fast:
    steps.append(("page parity (goldens)", ["node", str(ROOT / "tests" / "parity" / "legacy_oracle.js"), "--check"]))
    for py in sorted((ROOT / "tests" / "parity").glob("*.py")):
        steps.append((f"python parity: {py.name}", [sys.executable, str(py)]))
if not steps:
    print("nothing to run yet")
    sys.exit(0)
fails = []
for label, cmd in steps:
    print(f"\n== {label}")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode:
        fails.append(label)
print("\nALL GREEN" if not fails else "\nFAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
