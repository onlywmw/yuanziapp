"""Review verification round 2: persistence of content_hash, probe edge cases."""

from __future__ import annotations

import sqlite3
import sys
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
        "atom_id": atom_id,
        "name": "A",
        "description": "d",
        "purpose": {"functions": [{"name": f} for f in fn]},
        "architecture": {
            "type": "skill",
            "runtime": "python",
            "interface": "i",
            "dependencies": [],
        },
        "ownership": {},
    }


print("== 1. dedup + content_hash persistence ==")
c = fresh()
registry.submit_atom(c, mk("com.qa.alpha"))
registry.submit_atom(c, mk("com.qa.beta"))
cols = [r[1] for r in c.execute("PRAGMA table_info(atom_registry)").fetchall()]
print("table columns:", cols)
print("has content_hash column:", "content_hash" in cols)
# is content_hash persisted anywhere?
row = c.execute("SELECT * FROM atom_registry WHERE atom_id='com.qa.alpha'").fetchone()
dump = {k: row[k] for k in row.keys()}
stored = str(dump)
print("content_hash present in stored row:", "content_hash" in stored)
ch_alpha = registry.compute_content_hash(mk("com.qa.alpha"))
ch_beta = registry.compute_content_hash(mk("com.qa.beta"))
print("computed content_hash equal (clone detectable in theory):", ch_alpha == ch_beta)

print()
print("== 2. probe_atom file:// scheme ==")
c2 = fresh()
registry.submit_atom(
    c2, {**mk("com.qa.file"), "runtime": {"health_url": "file:///C:/Windows/win.ini"}}
)
registry.review_atom(c2, "com.qa.file", True)
try:
    r = registry.probe_atom(c2, "com.qa.file")
    print(
        "result:",
        {k: r.get(k) for k in ("success", "probe_status", "new_status", "ok")},
    )
except Exception as e:
    print(f"UNHANDLED EXCEPTION: {type(e).__name__}: {e}")

print()
print("== 3. probe_atom ftp:// scheme ==")
c3 = fresh()
registry.submit_atom(
    c3, {**mk("com.qa.ftp"), "runtime": {"health_url": "ftp://example.invalid/x"}}
)
registry.review_atom(c3, "com.qa.ftp", True)
try:
    r = registry.probe_atom(c3, "com.qa.ftp", timeout=2)
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
print(
    "probe result:", r.get("error"), "| audit actions:", [a["action"] for a in audits]
)

print()
print("== 5. offline probe-fail -> unreachable vs transition table ==")
c5 = fresh()
registry.submit_atom(
    c5, {**mk("com.qa.off"), "runtime": {"health_url": "http://127.0.0.1:1/x"}}
)
registry.review_atom(c5, "com.qa.off", True)
registry.set_atom_status(c5, "com.qa.off", "offline")
r = registry.probe_atom(c5, "com.qa.off", timeout=1)
print(
    "offline probe-fail ->",
    r["new_status"],
    "| note: offline->unreachable not in set_atom_status.allowed_transitions",
)

print()
print("== 6. rejected atom probe (only-记录 claim) ==")
c6 = fresh()
registry.submit_atom(
    c6, {**mk("com.qa.rej"), "runtime": {"health_url": "http://127.0.0.1:1/x"}}
)
registry.review_atom(c6, "com.qa.rej", False)
r = registry.probe_atom(c6, "com.qa.rej", timeout=1)
atom = registry.get_atom(c6, "com.qa.rej")
print(
    "rejected probe ->",
    r["new_status"],
    "| runtime recorded:",
    atom["runtime"].get("last_probe_status"),
    "| audit:",
    [a["action"] for a in registry.get_audit_log(c6, "com.qa.rej")],
)
