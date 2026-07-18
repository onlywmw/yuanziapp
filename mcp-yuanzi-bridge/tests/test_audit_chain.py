"""Tests for the audit hash chain (M6.4)."""

from __future__ import annotations

import sqlite3

import pytest
from migrations import migrate
from registry import (
    backfill_audit_chain,
    get_audit_log,
    review_atom,
    set_atom_status,
    submit_atom,
    verify_audit_chain,
)


def _atom(atom_id="com.chain.sum", functions=("sum",)):
    return {
        "atom_id": atom_id,
        "name": "Sum",
        "version": "1.0.0",
        "description": "",
        "purpose": {"functions": [{"name": f} for f in functions]},
        "architecture": {"type": "t", "runtime": "r", "dependencies": []},
        "ownership": {"author": "t", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def test_audit_rows_carry_chain_hash(conn):
    submit_atom(conn, _atom())
    review_atom(conn, "com.chain.sum", approved=True)
    rows = conn.execute("SELECT chain_hash FROM atom_audit_log ORDER BY id").fetchall()
    assert len(rows) == 2
    assert all(r[0] and len(r[0]) == 64 for r in rows)
    assert rows[0][0] != rows[1][0]  # 链式递进


def test_verify_valid_chain(conn):
    submit_atom(conn, _atom())
    review_atom(conn, "com.chain.sum", approved=True)
    set_atom_status(conn, "com.chain.sum", "offline")
    result = verify_audit_chain(conn)
    assert result["valid"] is True
    assert result["total_rows"] == 3
    assert result["legacy_rows"] == 0
    assert result["broken_at_row"] is None


def test_verify_detects_tampering(conn):
    submit_atom(conn, _atom())
    review_atom(conn, "com.chain.sum", approved=True)
    # 篡改历史行：改动 detail 但不更新链
    conn.execute("UPDATE atom_audit_log SET detail = 'forged' WHERE action = 'submit'")
    conn.commit()
    result = verify_audit_chain(conn)
    assert result["valid"] is False
    assert result["broken_at_row"] is not None
    assert result["expected"] != result["actual"]


def test_verify_detects_row_deletion(conn):
    submit_atom(conn, _atom())
    review_atom(conn, "com.chain.sum", approved=True)
    set_atom_status(conn, "com.chain.sum", "offline")
    # 删除中间行 → 后续行的 prev 引用断裂
    conn.execute("DELETE FROM atom_audit_log WHERE action = 'review'")
    conn.commit()
    result = verify_audit_chain(conn)
    assert result["valid"] is False


def test_backfill_legacy_rows(conn):
    # 模拟迁移前的旧行（无 chain_hash）
    conn.execute(
        "INSERT INTO atom_audit_log (atom_id, action, actor, detail, created_at) "
        "VALUES ('com.chain.old', 'submit', 'legacy', '', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    assert backfill_audit_chain(conn) == 1
    assert backfill_audit_chain(conn) == 0  # 幂等

    result = verify_audit_chain(conn)
    assert result["valid"] is True
    assert result["legacy_rows"] == 0


def test_verify_skips_null_chain_rows(conn):
    conn.execute(
        "INSERT INTO atom_audit_log (atom_id, action, actor, detail, created_at) "
        "VALUES ('com.chain.old', 'submit', 'legacy', '', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    submit_atom(conn, _atom())
    result = verify_audit_chain(conn)
    assert result["valid"] is True
    assert result["legacy_rows"] == 1


def test_audit_log_includes_chain_hash(conn):
    submit_atom(conn, _atom())
    logs = get_audit_log(conn, "com.chain.sum")
    assert "chain_hash" in logs[0]
