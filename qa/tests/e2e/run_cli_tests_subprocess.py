"""QA execution: TC-CLI-012/013/014/015 (real subprocess) + TC-CLI-020.

Run from repo root. Uses the installed `yuanzi` console script.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
YUANZI = REPO / ".venv" / "Scripts" / "yuanzi.exe"
PYTEST = REPO / ".venv" / "Scripts" / "python.exe"
EXAMPLE = REPO / "yuanzi-atom-templates" / "examples" / "com.example.sum"

results = []


def rec(tc, ok, note=""):
    results.append((tc, "PASS" if ok else "FAIL", note.replace("\n", " ")[:300]))


def run(args, cwd=REPO):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=300)


# TC-CLI-012 full flow
r = run([str(YUANZI), "test", str(EXAMPLE)])
out = r.stdout + r.stderr
rec(
    "TC-CLI-012",
    r.returncode == 0 and "8 passed" in out and "is a valid Yuanzi atom" in out,
    f"rc={r.returncode} valid_line={'is a valid Yuanzi atom' in out} 8passed={'8 passed' in out}",
)

# TC-CLI-013 --fast
r = run([str(YUANZI), "test", "--fast", str(EXAMPLE)])
out = r.stdout + r.stderr
rec(
    "TC-CLI-013",
    r.returncode == 0 and "fast mode" in out and "5 passed" in out,
    f"rc={r.returncode} 5passed={'5 passed' in out}",
)

# TC-CLI-014 --no-validate
r = run([str(YUANZI), "test", "--no-validate", str(EXAMPLE)])
out = r.stdout + r.stderr
rec(
    "TC-CLI-014",
    r.returncode == 0 and "8 passed" in out and "is a valid Yuanzi atom" not in out,
    f"rc={r.returncode}",
)

# TC-CLI-015 failing suite -> non-zero exit
tmp = Path(tempfile.mkdtemp(prefix="qa-cli15-"))
failatom = tmp / "failatom"
shutil.copytree(EXAMPLE, failatom)
core = failatom / "atom" / "core.py"
src = core.read_text(encoding="utf-8")
assert 'return {"result": a + b}' in src
core.write_text(
    src.replace('return {"result": a + b}', 'return {"result": a + b + 1}'),
    encoding="utf-8",
)
r = run([str(YUANZI), "test", "--no-validate", str(failatom)])
out = r.stdout + r.stderr
rec(
    "TC-CLI-015",
    r.returncode != 0 and "failed" in out,
    f"rc={r.returncode} failed_in_out={'failed' in out}",
)

# TC-CLI-020 pytest from repo root (CWD robustness of relative-path tests)
r = run(
    [str(PYTEST), "-m", "pytest", "yuanzi-cli/tests", "-v", "--no-header"], cwd=REPO
)
out = r.stdout + r.stderr
rec("TC-CLI-020", r.returncode == 0, f"rc={r.returncode} tail={out.strip()[-200:]}")

print("=" * 70)
for tc, status, note in results:
    print(f"{tc} | {status} | {note}")
fails = [t for t, s, _ in results if s == "FAIL"]
print("=" * 70)
print(f"TOTAL {len(results)}  PASS {len(results)-len(fails)}  FAIL {len(fails)}")
if fails:
    print("FAILED:", ",".join(fails))
