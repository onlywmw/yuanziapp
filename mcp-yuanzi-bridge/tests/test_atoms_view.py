"""atoms VIEW 完整性测试（CLEANUP_PLAN 步骤 5）——保护 VIEW 不被回退为 TABLE。"""

from __future__ import annotations

import json
import sqlite3

import pytest
from migrations import migrate
from registry import submit_atom


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def _atom(atom_id="com.example.view-test"):
    return {
        "atom_id": atom_id,
        "name": "ViewTest",
        "version": "1.0.0",
        "description": "",
        "purpose": {"functions": [{"name": "f1"}, {"name": "f2"}]},
        "architecture": {"type": "mcp-server", "runtime": "py3"},
        "ownership": {"author": "test", "license": "MIT"},
        "runtime": {"endpoint": "http://127.0.0.1:8080/mcp/com.example.view-test"},
        "lifecycle": {"status": "submitted"},
    }


def test_atoms_view_exists(conn):
    row = conn.execute("SELECT type FROM sqlite_master WHERE name = 'atoms'").fetchone()
    assert row is not None
    assert row[0] == "view", f"Expected VIEW, got {row[0]}"


def test_view_mirrors_registry(conn):
    submit_atom(conn, _atom())
    row = conn.execute(
        "SELECT * FROM atoms WHERE atom_id = 'com.example.view-test'"
    ).fetchone()
    assert row is not None
    assert row["label"] == "ViewTest"
    assert row["atom_type"] == "mcp-server"
    assert row["endpoint"] == "http://127.0.0.1:8080/mcp/com.example.view-test"
    assert json.loads(row["capabilities"]) == [
        "mcp/com.example.view-test/f1",
        "mcp/com.example.view-test/f2",
    ]


def test_view_is_read_only(conn):
    with pytest.raises(sqlite3.OperationalError):
        conn.execute(
            "INSERT INTO atoms (atom_id, label, atom_type, endpoint) "
            "VALUES ('x.y', 'x', 't', 'e')"
        )


def test_view_columns_match_legacy(conn):
    submit_atom(conn, _atom())
    row = conn.execute("SELECT * FROM atoms LIMIT 1").fetchone()
    for column in (
        "id",
        "atom_id",
        "label",
        "atom_type",
        "endpoint",
        "status",
        "capabilities",
        "updated_at",
        "created_at",
    ):
        assert column in row.keys(), column


def test_view_never_returns_null(conn):
    """加固3：缺 JSON 字段的原子，VIEW 列返回 'unknown'/'' 而不是 NULL。"""
    conn.execute(
        """
        INSERT INTO atom_registry
        (atom_id, name, version, purpose_json, architecture_json,
         ownership_json, lifecycle_json, signature_hash)
        VALUES ('com.example.sparse', '', '1.0.0', '{}', '{}', '{}', '{}', 'h1')
        """
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM atoms WHERE atom_id = 'com.example.sparse'"
    ).fetchone()
    assert row["label"] == ""  # name 列 NOT NULL，空串原样返回
    assert row["atom_type"] == "unknown"
    assert row["endpoint"] == ""
    assert row["status"] == "unknown"
    assert row["capabilities"] == "[]"
    assert row["updated_at"] == ""
    assert row["created_at"] == ""
    for column in row.keys():
        assert row[column] is not None, column
