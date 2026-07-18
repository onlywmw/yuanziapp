"""Tests for registry layered signatures (content / identity / full)."""

from __future__ import annotations

import copy
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


# ---------- BUG-006/016 回归：能力去重闭环 ----------


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


def test_duplicate_content_blocked_across_atom_ids(conn):
    """BUG-006/016：能力相同、atom_id 不同的注册必须被拒绝。"""
    assert submit_atom(conn, _reg_atom("com.qa.alpha"))["success"]
    result = submit_atom(conn, _reg_atom("com.qa.beta"))
    assert not result["success"]
    assert result["error"] == "duplicate_content"
    assert "com.qa.alpha" in result["message"]


def test_same_atom_id_resubmit_allowed(conn):
    """同一 atom_id 重复提交（更新）不受能力去重影响。"""
    assert submit_atom(conn, _reg_atom("com.qa.alpha"))["success"]
    assert submit_atom(conn, _reg_atom("com.qa.alpha"))["success"]


def test_content_hash_persisted_in_column(conn):
    """BUG-016：content_hash / identity_hash 必须落库可查询。"""
    atom = _reg_atom("com.qa.alpha")
    submit_atom(conn, atom)
    row = conn.execute(
        "SELECT content_hash, identity_hash FROM atom_registry WHERE atom_id = ?",
        ("com.qa.alpha",),
    ).fetchone()
    assert row[0] == compute_content_hash(atom)
    assert len(row[0]) == 64
    assert len(row[1]) == 64


def test_backfill_content_hashes(conn):
    """迁移 005 后历史行可通过 backfill 补上 hash。"""
    conn.execute("UPDATE atom_registry SET content_hash = NULL, identity_hash = NULL")
    submit_atom(conn, _reg_atom("com.qa.alpha"))
    conn.execute("UPDATE atom_registry SET content_hash = NULL, identity_hash = NULL")
    assert backfill_content_hashes(conn) == 1
    row = conn.execute(
        "SELECT content_hash FROM atom_registry WHERE atom_id = 'com.qa.alpha'"
    ).fetchone()
    assert row[0] and len(row[0]) == 64
    assert backfill_content_hashes(conn) == 0  # 幂等
