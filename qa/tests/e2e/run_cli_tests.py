"""QA execution: TC-CLI-001 .. TC-CLI-019 (TC-CLI-020 runs separately from repo root).

Prints one line per test: TC-ID | PASS/FAIL | note
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # yuanziapp/
sys.path.insert(0, str(REPO / "yuanzi-cli"))

from typer.testing import CliRunner  # noqa: E402
from yuanzi_cli.main import app  # noqa: E402
from yuanzi_cli.meta import validate_meta  # noqa: E402

runner = CliRunner()
results: list[tuple[str, str, str]] = []


def rec(tc: str, ok: bool, note: str = ""):
    results.append((tc, "PASS" if ok else "FAIL", note.replace("\n", " ")[:300]))


def base_meta(**kw):
    m = {
        "id": "com.qa.x",
        "version": "0.1.0",
        "name": "X",
        "description": "x",
        "type": "skill",
        "kernel_type": "python_script",
        "author": "qa",
        "license": "MIT",
        "runtime": {"port": 18777},
    }
    m.update(kw)
    return m


EXAMPLE = REPO / "yuanzi-atom-templates" / "examples" / "com.example.sum"

# TC-CLI-001 --version
r = runner.invoke(app, ["--version"])
rec("TC-CLI-001", r.exit_code == 0 and "yuanzi-cli 0.1.0" in r.output, r.output.strip())

# TC-CLI-002 init with default template resolution
tmp = Path(tempfile.mkdtemp(prefix="qa-cli-"))
r = runner.invoke(app, ["init", "com.qa.demo", "--output-dir", str(tmp)])
created = tmp / "com.qa.demo"
need = ["meta.yaml", "server.py", "atom/core.py", "atom/__init__.py",
        "tests/test_kernel.py", "tests/test_health.py"]
missing = [f for f in need if not (created / f).exists()]
rec("TC-CLI-002", r.exit_code == 0 and created.exists() and not missing,
    f"exit={r.exit_code} missing={missing} out={r.output.strip()}")

# TC-CLI-003 validate the generated atom
r2 = runner.invoke(app, ["validate", str(created)])
rec("TC-CLI-003", r2.exit_code == 0 and "com.qa.demo@0.1.0" in r2.output,
    f"exit={r2.exit_code} out={(r2.output + r2.stderr).strip()}")

# TC-CLI-004 init rejects invalid atom id
bad_dir = tmp / "BAD ID!!"
r = runner.invoke(app, ["init", "BAD ID!!", "--output-dir", str(tmp)])
rejected = r.exit_code != 0 and not bad_dir.exists()
rec("TC-CLI-004", rejected,
    f"exit={r.exit_code} dir_created={bad_dir.exists()} (expected: non-zero exit, no dir)")

# TC-CLI-005 init into existing directory
r1 = runner.invoke(app, ["init", "com.qa.dup", "--output-dir", str(tmp)])
r2 = runner.invoke(app, ["init", "com.qa.dup", "--output-dir", str(tmp)])
graceful = r2.exit_code != 0 and "traceback" not in (r2.output + (r2.stderr or "")).lower()
exc = getattr(r2, "exception", None)
rec("TC-CLI-005", r2.exit_code != 0 and exc is None,
    f"first={r1.exit_code} second={r2.exit_code} exception={type(exc).__name__ if exc else None}")

# TC-CLI-006 validate official example
r = runner.invoke(app, ["validate", str(EXAMPLE)])
rec("TC-CLI-006", r.exit_code == 0 and "com.example.sum@0.1.0" in r.output, r.output.strip())

# TC-CLI-007 validate missing meta.yaml
empty = tmp / "empty"
empty.mkdir(exist_ok=True)
r = runner.invoke(app, ["validate", str(empty)])
rec("TC-CLI-007", r.exit_code == 1 and "meta.yaml not found" in (r.output + r.stderr),
    f"exit={r.exit_code}")

# TC-CLI-008 validate missing required file
broken = tmp / "broken"
shutil.copytree(EXAMPLE, broken)
(broken / "tests" / "test_health.py").unlink()
r = runner.invoke(app, ["validate", str(broken)])
out = r.output + r.stderr
rec("TC-CLI-008", r.exit_code == 1 and "missing required files" in out
    and "test_health.py" in out, f"exit={r.exit_code} out={out.strip()}")

# TC-CLI-009 validate invalid meta (bad id)
badmeta = tmp / "badmeta"
badmeta.mkdir(exist_ok=True)
(badmeta / "meta.yaml").write_text("id: bad-id\nversion: 0.1\n", encoding="utf-8")
r = runner.invoke(app, ["validate", str(badmeta)])
rec("TC-CLI-009", r.exit_code == 1 and "validation failed" in (r.output + r.stderr),
    f"exit={r.exit_code}")

# TC-CLI-010 markdown_rules missing rules.md
md = tmp / "mdatom"
md.mkdir(exist_ok=True)
import yaml  # noqa: E402
(md / "meta.yaml").write_text(yaml.safe_dump(base_meta(kernel_type="markdown_rules")),
                               encoding="utf-8")
r = runner.invoke(app, ["validate", str(md)])
rec("TC-CLI-010", r.exit_code == 1 and "rules.md" in (r.output + r.stderr),
    f"exit={r.exit_code} out={(r.output + r.stderr).strip()}")

# TC-CLI-011 meta.yaml is a list
lst = tmp / "lstmeta"
lst.mkdir(exist_ok=True)
(lst / "meta.yaml").write_text("- a\n- b\n", encoding="utf-8")
r = runner.invoke(app, ["validate", str(lst)])
out = (r.output + (r.stderr or ""))
exc = getattr(r, "exception", None)
rec("TC-CLI-011", r.exit_code == 1,
    f"exit={r.exit_code} exception={type(exc).__name__ if exc else None} out={out.strip()}")

# TC-CLI-012 yuanzi test full flow
r = runner.invoke(app, ["test", str(EXAMPLE)])
rec("TC-CLI-012", r.exit_code == 0 and "8 passed" in r.output,
    f"exit={r.exit_code} tail={r.output.strip()[-120:]}")

# TC-CLI-013 yuanzi test --fast
r = runner.invoke(app, ["test", "--fast", str(EXAMPLE)])
rec("TC-CLI-013", r.exit_code == 0 and "fast mode" in r.output and "5 passed" in r.output,
    f"exit={r.exit_code} tail={r.output.strip()[-120:]}")

# TC-CLI-014 yuanzi test --no-validate
r = runner.invoke(app, ["test", "--no-validate", str(EXAMPLE)])
rec("TC-CLI-014", r.exit_code == 0 and "is a valid Yuanzi atom" not in r.output
    and "8 passed" in r.output, f"exit={r.exit_code}")

# TC-CLI-015 yuanzi test failing suite -> non-zero
failatom = tmp / "failatom"
shutil.copytree(EXAMPLE, failatom)
core = failatom / "atom" / "core.py"
core.write_text(core.read_text(encoding="utf-8").replace("return a + b", "return a + b + 1"),
                encoding="utf-8")
r = runner.invoke(app, ["test", "--no-validate", str(failatom)])
rec("TC-CLI-015", r.exit_code != 0, f"exit={r.exit_code}")

# TC-CLI-016 meta id boundary cases
cases = {"COM.EXAMPLE.X": None, "com.中文.x": None, "com.exa mple.x": None}
for cid in cases:
    try:
        validate_meta(base_meta(id=cid))
        cases[cid] = "accepted"
    except Exception as e:
        cases[cid] = f"rejected"
note = json.dumps(cases, ensure_ascii=False)
# hard requirement: id containing spaces must be rejected; uppercase/CJK recorded
rec("TC-CLI-016", cases["com.exa mple.x"] == "rejected", note)

# TC-CLI-017 port boundary
p0 = p65536 = None
try:
    validate_meta(base_meta(runtime={"port": 0}))
    p0 = "accepted"
except Exception:
    p0 = "rejected"
try:
    validate_meta(base_meta(runtime={"port": 65536}))
    p65536 = "accepted"
except Exception:
    p65536 = "rejected"
try:
    validate_meta(base_meta(runtime={"port": 18777}))
    pok = "accepted"
except Exception:
    pok = "rejected"
rec("TC-CLI-017", p0 == "rejected" and p65536 == "rejected" and pok == "accepted",
    f"port0={p0} port65536={p65536} port18777={pok}")

# TC-CLI-018 init with explicit template dir
r = runner.invoke(app, ["init", "com.qa.custom", "-t",
                        str(REPO / "yuanzi-atom-templates"), "-o", str(tmp)])
rec("TC-CLI-018", r.exit_code == 0 and (tmp / "com.qa.custom" / "meta.yaml").exists(),
    f"exit={r.exit_code}")

# TC-CLI-019 no args shows help
r = runner.invoke(app, [])
rec("TC-CLI-019", "Usage" in r.output or "usage" in r.output.lower(),
    f"exit={r.exit_code}")

print("=" * 70)
for tc, status, note in results:
    print(f"{tc} | {status} | {note}")
fails = [t for t, s, _ in results if s == "FAIL"]
print("=" * 70)
print(f"TOTAL {len(results)}  PASS {len(results)-len(fails)}  FAIL {len(fails)}")
if fails:
    print("FAILED:", ",".join(fails))
