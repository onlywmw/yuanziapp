"""Tests for the schema migration runner and the atoms VIEW."""

from __future__ import annotations

import json
import sqlite3

import pytest
from migrations import (
    MIGRATIONS_DIR,
    applied_versions,
    current_version,
    discover_migrations,
    migrate,
    pending_migrations,
)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _object_type(conn, name):
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    return row[0] if row else None


def _insert_atom(conn):
    # 用 001 基线 SQL 模拟迁移系统引入前的旧库结构
    conn.executescript((MIGRATIONS_DIR / "001_init.sql").read_text(encoding="utf-8"))
    conn.execute(
        """
        INSERT INTO atom_registry
        (atom_id, name, version, purpose_json, architecture_json,
         ownership_json, lifecycle_json, runtime_json, signature_hash,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "com.example.sum",
            "Sum",
            "1.0.0",
            json.dumps({"functions": [{"name": "sum"}, {"name": "sum_many"}]}),
            json.dumps({"type": "mcp-server"}),
            json.dumps({"author": "test"}),
            json.dumps(
                {
                    "status": "running",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-02T00:00:00+00:00",
                }
            ),
            json.dumps({"endpoint": "http://127.0.0.1:8080/mcp/com.example.sum"}),
            "abc123",
            "2026-01-01T00:00:00+00:00",
            "2026-01-02T00:00:00+00:00",
        ),
    )
    conn.commit()


def _create_legacy_atoms_table(conn):
    conn.execute(
        """
        CREATE TABLE atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atom_id TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            atom_type TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unknown',
            capabilities TEXT DEFAULT '[]',
            updated_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def test_fresh_db_migrates_to_latest(conn):
    applied = migrate(conn)
    assert applied == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    assert current_version(conn) == 13
    assert _object_type(conn, "atom_registry") == "table"
    assert _object_type(conn, "atoms") == "view"


def test_migrate_is_idempotent(conn):
    migrate(conn)
    assert migrate(conn) == []
    assert applied_versions(conn) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    assert pending_migrations(conn) == []


def test_legacy_db_gets_baseline_and_view(conn):
    # 模拟迁移系统引入前的旧库：有业务表，无 schema_migrations
    _insert_atom(conn)
    _create_legacy_atoms_table(conn)

    applied = migrate(conn)
    assert applied == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]

    desc = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = 1"
    ).fetchone()[0]
    assert "baseline" in desc

    assert _object_type(conn, "atoms") == "view"


def test_atoms_view_mirrors_registry(conn):
    _insert_atom(conn)
    migrate(conn)

    row = conn.execute(
        "SELECT * FROM atoms WHERE atom_id = 'com.example.sum'"
    ).fetchone()
    assert row["label"] == "Sum"
    assert row["atom_type"] == "mcp-server"
    assert row["endpoint"] == "http://127.0.0.1:8080/mcp/com.example.sum"
    assert row["status"] == "running"
    assert json.loads(row["capabilities"]) == [
        "mcp/com.example.sum/sum",
        "mcp/com.example.sum/sum_many",
    ]
    assert row["created_at"] == "2026-01-01T00:00:00+00:00"
    assert row["updated_at"] == "2026-01-02T00:00:00+00:00"


def test_atoms_view_updates_live(conn):
    _insert_atom(conn)
    migrate(conn)
    conn.execute(
        "UPDATE atom_registry SET lifecycle_json = ? WHERE atom_id = 'com.example.sum'",
        (json.dumps({"status": "unreachable"}),),
    )
    conn.commit()
    row = conn.execute(
        "SELECT status FROM atoms WHERE atom_id = 'com.example.sum'"
    ).fetchone()
    assert row[0] == "unreachable"


def test_discover_migrations_sorted():
    versions = [v for v, _, _ in discover_migrations()]
    assert versions == sorted(versions)
    assert versions == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
