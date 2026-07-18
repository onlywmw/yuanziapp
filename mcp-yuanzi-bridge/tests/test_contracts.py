"""契约测试（INTERFACE_CONTRACTS.md）——只验证返回值结构，不验证业务逻辑。

注意：probe_atom 的契约（1.9）与当前实现存在分歧——契约基于 Arch 的
功能桩版本编写（endpoint/status_code/error/checked_at），现行实现是
BUG-014..022 修复后的版本（probe_status/old_status/new_status）。
按流程已上报 Arch 更新契约文档，probe 契约测试待文档对齐后补充。
"""

from __future__ import annotations

import sqlite3

import pytest
from migrations import (
    applied_versions,
    current_version,
    discover_migrations,
    migrate,
    pending_migrations,
)
from registry import (
    compute_registry_stats,
    dump_registry,
    get_atom,
    get_audit_log,
    list_atom_versions,
    list_atoms,
    resolve_dependencies,
    review_atom,
    rollback_atom,
    set_atom_status,
    submit_atom,
)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def _atom(atom_id="com.contract.sum", version="1.0.0", functions=("sum",)):
    return {
        "atom_id": atom_id,
        "name": "Sum",
        "version": version,
        "description": "contract fixture",
        "purpose": {"functions": [{"name": f} for f in functions]},
        "architecture": {"type": "python_script", "runtime": "py3", "dependencies": []},
        "ownership": {"author": "t", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }


def test_submit_atom_contract(conn):
    """契约 1.1"""
    result = submit_atom(conn, _atom())
    assert result["success"] is True
    assert isinstance(result["atom_id"], str)
    assert isinstance(result["signature"], str)
    assert result["status"] == "submitted"

    # 重复签名（含能力级 duplicate_signature）
    other = _atom(atom_id="com.contract.clone")
    dup = submit_atom(conn, other)
    assert dup["success"] is False
    assert dup["error"] == "duplicate_signature"
    assert isinstance(dup["message"], str)


def test_review_atom_contract(conn):
    """契约 1.2"""
    submit_atom(conn, _atom())
    result = review_atom(conn, "com.contract.sum", approved=True)
    assert result["success"] is True
    assert result["status"] == "registered"

    missing = review_atom(conn, "com.contract.ghost", approved=True)
    assert missing["success"] is False
    assert missing["error"] == "not_found"


def test_set_atom_status_contract(conn):
    """契约 1.3"""
    submit_atom(conn, _atom())
    review_atom(conn, "com.contract.sum", approved=True)
    result = set_atom_status(conn, "com.contract.sum", "offline")
    assert result["success"] is True
    assert result["old_status"] == "registered"
    assert result["new_status"] == "offline"

    bad = set_atom_status(conn, "com.contract.sum", "flying")
    assert bad["success"] is False
    assert bad["error"] == "invalid_transition"


def test_get_atom_contract(conn):
    """契约 1.4：关键键齐全"""
    submit_atom(conn, _atom())
    atom = get_atom(conn, "com.contract.sum")
    for key in (
        "atom_id",
        "name",
        "version",
        "purpose",
        "architecture",
        "ownership",
        "lifecycle",
        "signature_hash",
        "content_hash",
        "identity_hash",
    ):
        assert key in atom, key
    assert get_atom(conn, "com.contract.ghost") is None


def test_list_atoms_contract(conn):
    """契约 1.5：列表 + 过滤"""
    submit_atom(conn, _atom())
    atoms = list_atoms(conn)
    assert isinstance(atoms, list) and len(atoms) == 1
    assert list_atoms(conn, status="running") == []
    assert list_atoms(conn, search="contract") != []


def test_list_atom_versions_contract(conn):
    """契约 1.6：形状 + DESC 排序"""
    submit_atom(conn, _atom(version="1.0.0"))
    submit_atom(conn, _atom(version="1.1.0", functions=("sum", "sum2")))
    versions = list_atom_versions(conn, "com.contract.sum")
    assert [v["version"] for v in versions] == ["1.1.0", "1.0.0"]
    for v in versions:
        assert set(v.keys()) == {
            "version",
            "signature",
            "content_hash",
            "changelog",
            "purpose",
            "created_at",
        }
        assert isinstance(v["purpose"], dict)


def test_rollback_atom_contract(conn):
    """契约 1.8"""
    submit_atom(conn, _atom())
    result = rollback_atom(conn, "com.contract.sum", "1.0.0")
    assert result["success"] is True
    missing = rollback_atom(conn, "com.contract.sum", "9.9.9")
    assert missing["success"] is False
    assert missing["error"] == "version_not_found"


def test_resolve_dependencies_contract(conn):
    """契约 1.11：ok/atom_id/order/missing/cycles/deps 键齐全"""
    submit_atom(conn, _atom(atom_id="com.contract.base", functions=("base_fn",)))
    child = _atom(atom_id="com.contract.child", functions=("child_fn",))
    child["architecture"]["dependencies"] = ["com.contract.base"]
    submit_atom(conn, child)

    result = resolve_dependencies(conn, "com.contract.child")
    for key in ("ok", "atom_id", "order", "missing", "cycles", "deps"):
        assert key in result, key
    assert result["ok"] is True
    assert result["order"] == ["com.contract.base", "com.contract.child"]
    assert result["missing"] == []
    assert result["cycles"] == []
    assert result["deps"] == [
        {
            "atom_id": "com.contract.base",
            "name": "Sum",
            "status": "submitted",
        }
    ]

    ghost = resolve_dependencies(conn, "com.contract.ghost")
    assert ghost["ok"] is False
    assert ghost["missing"] == ["com.contract.ghost"]


def test_stats_contract(conn):
    """契约 1.12"""
    stats = compute_registry_stats(conn)
    assert isinstance(stats["total_atoms"], int)
    assert isinstance(stats["status_counts"], dict)
    assert isinstance(stats["category_counts"], dict)
    assert isinstance(stats["generated_at"], str)


def test_dump_registry_contract(conn):
    """契约 1.13：schema_version 来自 schema_migrations"""
    dump = dump_registry(conn)
    assert isinstance(dump["schema_version"], str)
    assert dump["schema_version"] == str(current_version(conn))
    for key in ("generated_at", "stats", "atoms", "audit_log"):
        assert key in dump


def test_audit_log_contract(conn):
    """契约 1.14"""
    submit_atom(conn, _atom())
    logs = get_audit_log(conn, "com.contract.sum")
    assert logs
    entry = logs[0]
    for key in ("id", "atom_id", "action", "actor", "detail", "created_at"):
        assert key in entry, key


def test_migrations_contract(conn):
    """契约 2.1-2.5"""
    assert migrate(conn) == []  # fixture 已迁移
    assert current_version(conn) >= 1
    versions = applied_versions(conn)
    assert versions == sorted(versions)
    assert pending_migrations(conn) == []
    discovered = discover_migrations()
    assert all(isinstance(v, int) for v, _, _ in discovered)
    assert [v for v, _, _ in discovered] == versions


def test_reserved_namespace_rejected(conn):
    """加固4：system./yuanzi. 命名空间禁止注册。"""
    for atom_id in ("system.file-read", "yuanzi.core"):
        result = submit_atom(conn, _atom(atom_id=atom_id))
        assert not result["success"]
        assert result["error"] == "reserved_namespace"
