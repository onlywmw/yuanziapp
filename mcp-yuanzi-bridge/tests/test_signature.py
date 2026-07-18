"""Tests for registry layered signatures (content / identity / full)."""

from __future__ import annotations

import copy
import json
import sqlite3

import pytest
from registry import (
    backfill_content_hashes,
    compute_content_hash,
    compute_identity_hash,
    compute_signature,
    ensure_registry_schema,
    submit_atom,
)

BASE_ATOM = {
    "atom_id": "com.example.sum",
    "name": "Sum",
    "version": "1.0.0",
    "description": "adds numbers",
    "purpose": {"functions": [{"name": "sum"}, {"name": "sum_many"}]},
    "architecture": {
        "type": "python_script",
        "runtime": "python3.12",
        "interface": "std-atom-http-v1",
        "dependencies": ["com.example.base"],
    },
    "ownership": {"author": "yuanziapp", "license": "MIT"},
}


def test_hashes_are_full_sha256():
    for value in (
        compute_signature(BASE_ATOM),
        compute_content_hash(BASE_ATOM),
        compute_identity_hash(BASE_ATOM),
    ):
        assert len(value) == 64
        int(value, 16)  # valid hex


def test_full_signature_includes_identity():
    other = copy.deepcopy(BASE_ATOM)
    other["atom_id"] = "com.example.clone"
    assert compute_signature(other) != compute_signature(BASE_ATOM)


def test_full_signature_includes_version():
    other = copy.deepcopy(BASE_ATOM)
    other["version"] = "2.0.0"
    assert compute_signature(other) != compute_signature(BASE_ATOM)


def test_full_signature_includes_ownership():
    other = copy.deepcopy(BASE_ATOM)
    other["ownership"]["license"] = "Apache-2.0"
    assert compute_signature(other) != compute_signature(BASE_ATOM)


def test_content_hash_detects_capability_clones():
    # identity 不同但能力相同的原子，content_hash 必须一致（用于查重）
    clone = copy.deepcopy(BASE_ATOM)
    clone["atom_id"] = "org.copy.sum"
    clone["version"] = "9.9.9"
    assert compute_content_hash(clone) == compute_content_hash(BASE_ATOM)
    assert compute_identity_hash(clone) != compute_identity_hash(BASE_ATOM)


def test_content_hash_changes_with_functions():
    other = copy.deepcopy(BASE_ATOM)
    other["purpose"]["functions"].append({"name": "multiply"})
    assert compute_content_hash(other) != compute_content_hash(BASE_ATOM)


def test_content_hash_changes_with_function_schema():
    other = copy.deepcopy(BASE_ATOM)
    other["purpose"]["functions"][0]["input"] = {"a": "number", "b": "number"}
    assert compute_content_hash(other) != compute_content_hash(BASE_ATOM)


def test_content_hash_stable_to_function_order():
    other = copy.deepcopy(BASE_ATOM)
    other["purpose"]["functions"] = list(reversed(other["purpose"]["functions"]))
    assert compute_content_hash(other) == compute_content_hash(BASE_ATOM)


def test_content_hash_changes_with_dependencies():
    other = copy.deepcopy(BASE_ATOM)
    other["architecture"]["dependencies"].append("com.example.extra")
    assert compute_content_hash(other) != compute_content_hash(BASE_ATOM)


# ------------------------------------------------------------------
# BUG-016: capability dedup + content_hash persistence
# ------------------------------------------------------------------


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_registry_schema(c)
    yield c
    c.close()


def _reg_atom(atom_id):
    atom = copy.deepcopy(BASE_ATOM)
    atom["atom_id"] = atom_id
    atom["lifecycle"] = {"status": "submitted"}
    return atom


def test_duplicate_content_blocked_across_atom_ids_bug016(conn):
    """BUG-016: same capability under a different atom_id must be rejected."""
    assert submit_atom(conn, _reg_atom("com.example.a"))["success"]

    result = submit_atom(conn, _reg_atom("org.copy.b"))
    assert not result["success"]
    assert result["error"] == "duplicate_content"


def test_same_atom_resubmit_is_update_not_duplicate_bug016(conn):
    """BUG-016: resubmitting the SAME atom_id stays an update path."""
    assert submit_atom(conn, _reg_atom("com.example.a"))["success"]
    assert submit_atom(conn, _reg_atom("com.example.a"))["success"]


def test_content_hash_persisted_to_database_bug016(conn):
    """BUG-016: content_hash/identity_hash are real columns, queryable."""
    submit_atom(conn, _reg_atom("com.example.a"))

    columns = {r[1] for r in conn.execute("PRAGMA table_info(atom_registry)")}
    assert {"content_hash", "identity_hash"} <= columns

    row = conn.execute(
        "SELECT content_hash, identity_hash FROM atom_registry WHERE atom_id = ?",
        ("com.example.a",),
    ).fetchone()
    expected = _reg_atom("com.example.a")
    assert row[0] == compute_content_hash(expected)
    assert row[1] == compute_identity_hash(expected)


def test_backfill_content_hashes_bug016(conn):
    """BUG-016: rows predating the columns are backfilled (idempotent)."""
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
            "deadbeef" * 8,
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()

    assert backfill_content_hashes(conn) == 1
    row = conn.execute(
        "SELECT content_hash, identity_hash FROM atom_registry "
        "WHERE atom_id = 'com.example.legacy'"
    ).fetchone()
    assert row[0] and len(row[0]) == 64
    assert row[1] and len(row[1]) == 64
    # 幂等：再次调用不再更新任何行
    assert backfill_content_hashes(conn) == 0
