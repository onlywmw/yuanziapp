"""Tests for atom version archiving, listing and rollback."""

from __future__ import annotations

import json
import sqlite3

import pytest
from registry import (
    ensure_registry_schema,
    get_atom,
    get_atom_version,
    get_audit_log,
    list_atom_versions,
    review_atom,
    rollback_atom,
    submit_atom,
)


def _atom(version="1.0.0", functions=("sum",), description="adds numbers"):
    return {
        "atom_id": "com.example.sum",
        "name": "Sum",
        "version": version,
        "description": description,
        "purpose": {"functions": [{"name": f} for f in functions]},
        "architecture": {"type": "python_script", "runtime": "python3.12"},
        "ownership": {"author": "test", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_registry_schema(c)
    yield c
    c.close()


def test_submit_archives_version(conn):
    submit_atom(conn, _atom())
    versions = list_atom_versions(conn, "com.example.sum")
    assert len(versions) == 1
    v = versions[0]
    assert v["version"] == "1.0.0"
    assert v["purpose"]["functions"] == [{"name": "sum"}]
    assert len(v["signature_hash"]) == 64
    assert len(v["content_hash"]) == 64
    assert len(v["identity_hash"]) == 64


def test_resubmit_same_version_updates_snapshot(conn):
    submit_atom(conn, _atom(description="v1 first"))
    submit_atom(conn, _atom(description="v1 revised"))
    versions = list_atom_versions(conn, "com.example.sum")
    assert len(versions) == 1
    assert versions[0]["description"] == "v1 revised"


def test_multiple_versions_archived(conn):
    submit_atom(conn, _atom(version="1.0.0"))
    submit_atom(conn, _atom(version="1.1.0", functions=("sum", "sum_many")))
    versions = list_atom_versions(conn, "com.example.sum")
    assert [v["version"] for v in versions] == ["1.0.0", "1.1.0"]

    v11 = get_atom_version(conn, "com.example.sum", "1.1.0")
    assert [f["name"] for f in v11["purpose"]["functions"]] == ["sum", "sum_many"]
    assert get_atom_version(conn, "com.example.sum", "9.9.9") is None


def test_rollback_restores_old_content(conn):
    submit_atom(conn, _atom(version="1.0.0"))
    review_atom(conn, "com.example.sum", approved=True)
    submit_atom(conn, _atom(version="2.0.0", functions=("sum", "multiply")))
    review_atom(conn, "com.example.sum", approved=True)

    result = rollback_atom(conn, "com.example.sum", "1.0.0")
    assert result["success"]

    current = get_atom(conn, "com.example.sum")
    assert current["version"] == "1.0.0"
    assert [f["name"] for f in current["purpose"]["functions"]] == ["sum"]
    # lifecycle 状态保留，不被回滚改回 submitted
    assert current["lifecycle"]["status"] == "registered"

    # 两个版本的归档都还在
    assert len(list_atom_versions(conn, "com.example.sum")) == 2

    audits = get_audit_log(conn, "com.example.sum")
    rollback_entries = [a for a in audits if a["action"] == "rollback"]
    assert len(rollback_entries) == 1
    assert rollback_entries[0]["old_status"] == "2.0.0"
    assert rollback_entries[0]["new_status"] == "1.0.0"


def test_rollback_unknown_version(conn):
    submit_atom(conn, _atom())
    result = rollback_atom(conn, "com.example.sum", "9.9.9")
    assert not result["success"]
    assert result["error"] == "version_not_found"


def test_rollback_unknown_atom(conn):
    result = rollback_atom(conn, "com.example.ghost", "1.0.0")
    assert not result["success"]
    assert result["error"] == "version_not_found"


def test_migration_backfills_existing_atoms():
    """迁移 003/005 会把迁移前已注册的原子回填进对应新结构。"""
    from migrations import MIGRATIONS_DIR, applied_versions, migrate

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # 用 001 基线 SQL 模拟旧库（而不是 ensure_registry_schema 的最新结构）
    conn.executescript((MIGRATIONS_DIR / "001_init.sql").read_text(encoding="utf-8"))
    conn.execute(
        """
        INSERT INTO atom_registry
        (atom_id, name, version, purpose_json, architecture_json,
         ownership_json, lifecycle_json, signature_hash, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "com.example.legacy",
            "Legacy",
            "1.0.0",
            json.dumps({"functions": [{"name": "old"}]}),
            json.dumps({"type": "mcp-server"}),
            json.dumps({"author": "test"}),
            json.dumps({"status": "registered"}),
            "deadbeef",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()

    applied = migrate(conn)
    assert applied == [1, 2, 3, 4, 5, 6]

    versions = list_atom_versions(conn, "com.example.legacy")
    assert len(versions) == 1
    assert versions[0]["version"] == "1.0.0"
    assert versions[0]["signature_hash"] == "deadbeef"
    assert versions[0]["created_at"] == "2026-01-01T00:00:00+00:00"
    assert applied_versions(conn) == [1, 2, 3, 4, 5, 6]
