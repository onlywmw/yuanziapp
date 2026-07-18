"""Review verification: dedup scenario, probe edge cases (file://, no_endpoint audit)."""
from __future__ import annotations

import sqlite3
import sys
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp-yuanzi-bridge"))
import registry  # noqa: E402


def fresh():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    registry.ensure_registry_schema(c)
    return c


def mk(atom_id, fn=("f1",)):
    return {
        "atom_id": atom_id, "name": "A", "description": "d",
        "purpose": {"functions": [{"name": f} for f in fn]},
        "architecture": {"type": "skill", "runtime": "python",
                         "interface": "i", "dependencies": []},
        "ownership": {},
    }


print("== 1. BUG-006 dedup scenario on new layered signatures ==")
c = fresh()
r1 = registry.submit_atom(c, mk("com.qa.alpha"))
r2 = registry.submit_atom(c, mk("com.qa.beta"))  # same capabilities, different id
print("alpha:", r1.get("success"), "| beta:", r2.get("success"), r2.get("error"))
a = registry.get_atom(c, "com.qa.alpha")
b = registry.get_atom(c, "com.qa.beta")
sa, sb = a["signature"], b["signature"]
print("content_hash equal:", sa["content_hash"] == sb["content_hash"])
print("full signature equal:", sa["hash"] == sb["hash"])
dup = c.execute(
    "SELECT content_grp, COUNT(*) FROM (SELECT json_extract(signature_json,'$.content_hash') AS content_grp FROM atom_registry) GROUP BY content_grp HAVING COUNT(*)>1"
).fetchall() if c.execute("SELECT name FROM pragma_table_info('atom_registry') WHERE name='signature_json'").fetchone() else "no signature_json column"
print("content-level duplicate detection query:", dup)

print()
print("== 2. probe_atom with file:// scheme ==")
c2 = fresh()
registry.submit_atom(c2, {**mk("com.qa.file"), "runtime": {"health_url": "file:///C:/Windows/win.ini"}})
registry.review_atom(c2, "com.qa.file", True)
try:
    r = registry.probe_atom(c2, "com.qa.file")
    print("result:", r)
except Exception as e:
    print(f"UNHANDLED EXCEPTION: {type(e).__name__}: {e}")

print()
print("== 3. probe_atom with ftp:// scheme ==")
try:
    r = registry.probe_atom(c2, "com.qa.file")  # same atom still file://
except Exception as e:
    pass
c3 = fresh()
registry.submit_atom(c3, {**mk("com.qa.ftp"), "runtime": {"health_url": "ftp://example.invalid/x"}})
registry.review_atom(c3, "com.qa.ftp", True)
try:
    r = registry.probe_atom(c3, "com.qa.ftp")
    print("result:", {k: r.get(k) for k in ("success", "probe_status", "new_status")})
except Exception as e:
    print(f"UNHANDLED EXCEPTION: {type(e).__name__}: {e}")

print()
print("== 4. no_endpoint audit gap ==")
c4 = fresh()
registry.submit_atom(c4, {**mk("com.qa.noep"), "runtime": {}})
registry.review_atom(c4, "com.qa.noep", True)
r = registry.probe_atom(c4, "com.qa.noep")
audits = registry.get_audit_log(c4, "com.qa.noep")
print("probe result:", r.get("error"), "| audit actions:", [a["action"] for a in audits])

print()
print("== 5. offline -> probe fail -> unreachable (state machine consistency) ==")
c5 = fresh()
registry.submit_atom(c5, {**mk("com.qa.off"), "runtime": {"health_url": "http://127.0.0.1:1/x"}})
registry.review_atom(c5, "com.qa.off", True)
registry.set_atom_status(c5, "com.qa.off", "offline")
r = registry.probe_atom(c5, "com.qa.off", timeout=0.5)
print("offline probe-fail ->", r["new_status"], "| allowed in set_atom_status table? offline->unreachable not listed")
