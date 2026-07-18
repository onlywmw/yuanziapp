"""Integrity tests for the atoms VIEW (CLEANUP_PLAN step 5).

Protects the 002_atoms_view.sql contract: ``atoms`` must stay a read-only
VIEW mirroring ``atom_registry`` with the legacy column layout consumed by
Widget MCP /graph. If anyone reverts it to a TABLE or breaks the mirror,
these tests fail.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from migrations import migrate


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def _insert_atom(conn, atom_id="com.example.sum"):
    conn.execute(
        """
        INSERT INTO atom_registry
        (atom_id, name, version, purpose_json, architecture_json,
         ownership_json, lifecycle_json, runtime_json, signature_hash,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            atom_id,
            "Sum",
            "1.0.0",
            json.dumps({"functions": [{"name": "sum"}]}),
            json.dumps({"type": "mcp-server"}),
            json.dumps({}),
            json.dumps({"status": "registered"}),
            json.dumps({"endpoint": "http://127.0.0.1:9000/sum"}),
            "sig-" + atom_id,
            "2026-01-01T00:00:00",
            "2026-01-01T00:00:00",
        ),
    )
    conn.commit()


def test_atoms_view_exists(conn):
    row = conn.execute("SELECT type FROM sqlite_master WHERE name = 'atoms'").fetchone()
    assert row is not None, "atoms object missing from schema"
    assert row[0] == "view", f"atoms must stay a VIEW, got {row[0]}"


def test_view_mirrors_registry(conn):
    _insert_atom(conn)
    row = conn.execute(
        "SELECT atom_id, label, endpoint, status FROM atoms WHERE atom_id = ?",
        ("com.example.sum",),
    ).fetchone()
    assert row is not None, "atom inserted into atom_registry not visible in atoms VIEW"
    assert row["label"] == "Sum"
    assert row["endpoint"] == "http://127.0.0.1:9000/sum"
    assert row["status"] == "registered"


def test_view_is_read_only(conn):
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO atoms (atom_id, label) VALUES ('com.evil.x', 'Evil')")


def test_view_columns_match_legacy(conn):
    _insert_atom(conn)
    row = conn.execute("SELECT * FROM atoms LIMIT 1").fetchone()
    for column in ("label", "atom_type", "endpoint", "capabilities"):
        assert column in row.keys(), f"legacy column {column} missing from atoms VIEW"
    capabilities = json.loads(row["capabilities"])
    assert capabilities == ["mcp/com.example.sum/sum"]
