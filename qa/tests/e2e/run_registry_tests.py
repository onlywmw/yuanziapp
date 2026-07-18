"""QA execution: TC-REG-001 .. TC-REG-015 against mcp-yuanzi-bridge/registry.py."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp-yuanzi-bridge"))

import registry  # noqa: E402

results = []


def rec(tc, ok, note=""):
    results.append((tc, "PASS" if ok else "FAIL", note.replace("\n", " ")[:300]))


def fresh_conn():
    db = Path(tempfile.mkdtemp(prefix="qa-reg-")) / "reg.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    registry.ensure_registry_schema(conn)
    return conn


def mk(atom_id, name="Atom", fn=("f1",), desc="d"):
    return {
        "atom_id": atom_id,
        "name": name,
        "description": desc,
        "purpose": {"functions": [{"name": f} for f in fn]},
        "architecture": {
            "type": "skill",
            "runtime": "python",
            "interface": "std-atom-http-v1",
            "dependencies": [],
        },
        "ownership": {"team": "qa"},
    }


# TC-REG-001 submit new atom
conn = fresh_conn()
r = registry.submit_atom(conn, mk("com.qa.alpha"), actor="qa")
rec(
    "TC-REG-001",
    r.get("success") and r["status"] == "submitted" and len(r["signature"]) == 32,
    str(r),
)

# TC-REG-002 duplicate signature, different atom_id
r2 = registry.submit_atom(
    conn, mk("com.qa.beta"), actor="qa"
)  # same functions/type/runtime
rec(
    "TC-REG-002",
    not r2.get("success") and r2.get("error") == "duplicate_signature",
    str(r2),
)

# TC-REG-003 resubmit same atom_id -> update
r3 = registry.submit_atom(conn, mk("com.qa.alpha", desc="updated"), actor="qa")
atom = registry.get_atom(conn, "com.qa.alpha")
logs = registry.get_audit_log(conn, "com.qa.alpha")
rec(
    "TC-REG-003",
    r3.get("success")
    and atom["description"] == "updated"
    and sum(1 for log in logs if log["action"] == "submit") == 2,
    f"desc={atom['description']} submits={sum(1 for log in logs if log['action'] == 'submit')}",
)

# TC-REG-004 approve -> registered
r = registry.review_atom(conn, "com.qa.alpha", True, reviewer="qa", score=9)
atom = registry.get_atom(conn, "com.qa.alpha")
rec(
    "TC-REG-004",
    r.get("success") and r["status"] == "registered" and atom["review_score"] == 9,
    str(r),
)

# TC-REG-005 reject -> rejected
registry.submit_atom(conn, mk("com.qa.gamma", fn=("f2",)), actor="qa")
r = registry.review_atom(conn, "com.qa.gamma", False, comments="bad")
rec("TC-REG-005", r.get("success") and r["status"] == "rejected", str(r))

# TC-REG-006 review non-existent
r = registry.review_atom(conn, "com.ghost.x", True)
rec("TC-REG-006", not r.get("success") and r.get("error") == "not_found", str(r))

# TC-REG-007 registered -> running
r = registry.set_atom_status(conn, "com.qa.alpha", "running")
rec("TC-REG-007", r.get("success") and r["new_status"] == "running", str(r))

# TC-REG-008 submitted -> running (invalid)
registry.submit_atom(conn, mk("com.qa.delta", fn=("f3",)), actor="qa")
r = registry.set_atom_status(conn, "com.qa.delta", "running")
rec(
    "TC-REG-008",
    not r.get("success") and r.get("error") == "invalid_transition",
    str(r),
)

# TC-REG-009 list_atoms filter by status
rows = registry.list_atoms(conn, status="running")
rec(
    "TC-REG-009",
    len(rows) == 1 and rows[0]["atom_id"] == "com.qa.alpha",
    f"running={len(rows)}",
)

# TC-REG-010 list_atoms search
rows = registry.list_atoms(conn, search="gamma")
rec(
    "TC-REG-010",
    len(rows) == 1 and rows[0]["atom_id"] == "com.qa.gamma",
    f"hits={[r['atom_id'] for r in rows]}",
)

# TC-REG-011 audit log completeness
logs = registry.get_audit_log(conn, "com.qa.alpha")
actions = [log["action"] for log in logs]
ok = actions.count("submit") >= 2 and "review" in actions and "status_change" in actions
rec("TC-REG-011", ok, f"actions={actions}")

# TC-REG-012 SQL injection attempt in search
rows = registry.list_atoms(conn, search="' OR '1'='1")
total = registry.compute_registry_stats(conn)["total_atoms"]
rec(
    "TC-REG-012",
    len(rows) == 0 and total >= 3,
    f"injection returned {len(rows)} rows (total={total}) -> parameterized",
)

# TC-REG-013 submit without atom_id
try:
    registry.submit_atom(conn, {"name": "x"})
    r13 = "no exception"
except ValueError as e:
    r13 = f"ValueError: {e}"
rec("TC-REG-013", "atom_id is required" in r13, r13)

# TC-REG-014 rejected -> resubmit -> submitted
r = registry.submit_atom(conn, mk("com.qa.gamma", fn=("f2",)), actor="qa")
atom = registry.get_atom(conn, "com.qa.gamma")
st = atom["lifecycle"]["status"]
rec(
    "TC-REG-014",
    r.get("success") and st == "submitted",
    f"documented: rejected -> resubmit -> {st}",
)

# TC-REG-015 deprecated -> registered rollback
registry.review_atom(conn, "com.qa.delta", True)
registry.set_atom_status(conn, "com.qa.delta", "deprecated")
r = registry.set_atom_status(conn, "com.qa.delta", "registered")
rec("TC-REG-015", r.get("success") and r["new_status"] == "registered", str(r))

print("=" * 70)
for tc, status, note in results:
    print(f"{tc} | {status} | {note}")
fails = [t for t, s, _ in results if s == "FAIL"]
print("=" * 70)
print(f"TOTAL {len(results)}  PASS {len(results) - len(fails)}  FAIL {len(fails)}")
if fails:
    print("FAILED:", ",".join(fails))
