"""P0-B 注册验证接线 + 副作用标签落地测试（DESIGN_ATOM_FOUNDATION_V2 §2/§6）。

覆盖：
- 合法 meta 注册通过（JSON Schema 校验已接入 submit_atom）
- 缺 side_effect 自动归一化为 impure（并镜像进 classification 持久化）
- 非法 schema（坏 atom_id / 坏枚举字段 / 坏 side_effect / 坏 I/O 类型）被拒，
  错误信息带具体字段路径
- 14 个基础原子的 side_effect 常量映射
- 原子详情/列表 API 视图暴露 side_effect
- 星级计算中 pure 原子 +0.5 权重（marketplace.composite_score）
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from api import create_app
from fastapi.testclient import TestClient
from marketplace import composite_score
from migrations import migrate
from registry import get_atom, submit_atom
from registry.core import (
    BASE_ATOM_SIDE_EFFECTS,
    DEFAULT_SIDE_EFFECT,
    _get_meta_validator,
    resolve_side_effect,
)

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "atom-registry-schema.json"


def _valid_atom(atom_id="com.example.p0b-valid", fn="ping"):
    """完全符合 atom-registry-schema.json 的 meta（存量欠账字段也补齐）。"""
    return {
        "atom_id": atom_id,
        "name": "P0B Valid",
        "version": "1.0.0",
        "description": "schema-valid atom",
        "purpose": {
            "summary": "solves nothing",
            "functions": [{"name": fn, "description": "demo fn"}],
        },
        "architecture": {
            "type": "function",
            "runtime": "python3.12",
            "interface": "std-atom-http-v1",
        },
        "ownership": {"author": "test", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "api-test.db")
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. 合法 meta 注册通过
# ---------------------------------------------------------------------------


def test_valid_meta_registers_successfully(conn):
    result = submit_atom(conn, _valid_atom())
    assert result["success"] is True
    assert result["atom_id"] == "com.example.p0b-valid"
    assert get_atom(conn, "com.example.p0b-valid") is not None


def test_meta_validator_is_cached_at_module_level():
    """校验器模块级缓存编译：两次获取是同一个对象。"""
    first = _get_meta_validator()
    second = _get_meta_validator()
    assert first is not None
    assert first is second


# ---------------------------------------------------------------------------
# 2. side_effect 归一化：缺省 impure，显式 pure 保留
# ---------------------------------------------------------------------------


def test_missing_side_effect_defaults_to_impure(conn):
    assert DEFAULT_SIDE_EFFECT == "impure"
    result = submit_atom(conn, _valid_atom())
    assert result["success"] is True
    atom = get_atom(conn, "com.example.p0b-valid")
    # 注册表无独立列，镜像进 classification 持久化
    assert atom["classification"]["side_effect"] == "impure"
    assert resolve_side_effect(atom) == "impure"


def test_explicit_pure_side_effect_is_preserved(conn):
    atom = _valid_atom("com.example.p0b-pure")
    atom["side_effect"] = "pure"
    result = submit_atom(conn, atom)
    assert result["success"] is True
    stored = get_atom(conn, "com.example.p0b-pure")
    assert stored["classification"]["side_effect"] == "pure"
    assert resolve_side_effect(stored) == "pure"


# ---------------------------------------------------------------------------
# 3. 非法 schema 被拒，错误信息带具体字段路径
# ---------------------------------------------------------------------------


def test_bad_atom_id_pattern_rejected_with_path(conn):
    atom = _valid_atom("not reverse domain!")
    result = submit_atom(conn, atom)
    assert result["success"] is False
    assert result["error"] == "schema_validation"
    assert "atom_id" in result["message"]
    assert get_atom(conn, "not reverse domain!") is None


def test_bad_enum_field_rejected_with_path(conn):
    atom = _valid_atom("com.example.p0b-badfield")
    atom["classification"] = {"maturity": "golden"}  # 不在枚举内
    result = submit_atom(conn, atom)
    assert result["success"] is False
    assert result["error"] == "schema_validation"
    assert "classification.maturity" in result["message"]


def test_bad_side_effect_rejected_with_path(conn):
    atom = _valid_atom("com.example.p0b-badse")
    atom["side_effect"] = "sometimes"  # 契约枚举只有 pure/impure
    result = submit_atom(conn, atom)
    assert result["success"] is False
    assert result["error"] == "schema_validation"
    assert "side_effect" in result["message"]


def _find_io_type_paths(node, meta_path=()):
    """在 schema 中递归定位 I/O 类型枚举（含 file_ref 的 enum），返回 meta 路径列表。

    P0-A 负责把 I/O 类型枚举 ["json", "stream", "file_ref"] 加入
    atom-registry-schema.json；本助手与其落点解耦，枚举出现在任何
    嵌套位置（含数组 items，路径段用整数下标表示）都能找到并据此构造非法 meta。
    """
    paths = []
    if isinstance(node, dict):
        enum = node.get("enum")
        if isinstance(enum, list) and "file_ref" in enum:
            paths.append(meta_path)
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                for prop, sub in value.items():
                    paths.extend(_find_io_type_paths(sub, meta_path + (prop,)))
            elif key == "items":
                # 数组节点：路径段用下标 0 代表任意元素
                paths.extend(_find_io_type_paths(value, meta_path + (0,)))
            elif isinstance(value, (dict, list)):
                paths.extend(_find_io_type_paths(value, meta_path))
    elif isinstance(node, list):
        for item in node:
            paths.extend(_find_io_type_paths(item, meta_path))
    return paths


def _set_meta_path(atom, meta_path, value):
    """按 meta 路径（可含整数下标）写入值，缺失的 dict/list 自动补建。"""
    target = atom
    for index, key in enumerate(meta_path[:-1]):
        next_is_index = isinstance(meta_path[index + 1], int)
        if isinstance(key, int):
            while len(target) <= key:
                target.append([] if next_is_index else {})
            target = target[key]
        else:
            if not isinstance(target.get(key), (dict, list)):
                target[key] = [] if next_is_index else {}
            target = target[key]
    last = meta_path[-1]
    if isinstance(last, int):
        while len(target) <= last:
            target.append(None)
        target[last] = value
    else:
        target[last] = value


def test_bad_io_type_rejected_with_path(conn):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    io_paths = _find_io_type_paths(schema)
    if not io_paths:
        pytest.skip("atom-registry-schema.json 尚未加入 I/O 类型枚举（P0-A 并行中）")
    for meta_path in io_paths:
        path_str = ".".join(str(p) for p in meta_path)
        atom = _valid_atom("com.example.p0b-badio-" + path_str.replace(".", "-"))
        _set_meta_path(atom, meta_path, "yaml-stream")  # 非法 I/O 类型
        result = submit_atom(conn, atom)
        assert result["success"] is False, meta_path
        assert result["error"] == "schema_validation"
        assert path_str in result["message"]


def test_reserved_namespace_still_rejected_before_validation(conn):
    atom = _valid_atom("system.math-calc")
    result = submit_atom(conn, atom)
    assert result["success"] is False
    assert result["error"] == "reserved_namespace"


# ---------------------------------------------------------------------------
# 4. 基础原子 side_effect 常量映射
# ---------------------------------------------------------------------------


def test_base_atom_side_effect_map_covers_14_atoms():
    assert len(BASE_ATOM_SIDE_EFFECTS) == 14
    # 文档点名 pure 的只有这三个（无副作用、无状态）
    pure = {k for k, v in BASE_ATOM_SIDE_EFFECTS.items() if v == "pure"}
    assert pure == {"system.math-calc", "system.string-split", "system.json-parse"}
    # 其余一律保守 impure（含 ai / string-match / hash-digest / date-time）
    impure = {k for k, v in BASE_ATOM_SIDE_EFFECTS.items() if v == "impure"}
    assert impure == {
        "system.file-read",
        "system.file-write",
        "system.file-dir",
        "system.http-get",
        "system.http-post",
        "system.encrypt-aes",
        "system.decrypt-aes",
        "system.string-match",
        "system.hash-digest",
        "system.date-time",
        "system.ai",
    }


def test_resolve_side_effect_uses_constant_map_for_base_atoms():
    assert resolve_side_effect({"atom_id": "system.math-calc"}) == "pure"
    assert resolve_side_effect({"atom_id": "system.ai"}) == "impure"
    # 常量表优先于 meta：即使 meta 乱标也以常量表为准
    assert (
        resolve_side_effect({"atom_id": "system.http-get", "side_effect": "pure"})
        == "impure"
    )


def test_resolve_side_effect_defaults_to_impure_for_unknown_atoms():
    assert resolve_side_effect({"atom_id": "com.example.unknown"}) == "impure"
    assert resolve_side_effect({}) == "impure"


# ---------------------------------------------------------------------------
# 5. 原子详情/列表 API 视图暴露 side_effect
# ---------------------------------------------------------------------------


def test_api_detail_view_exposes_side_effect(client):
    r = client.post("/atoms", json=_valid_atom())
    assert r.status_code == 201
    atom = client.get("/atoms/com.example.p0b-valid").json()
    assert atom["side_effect"] == "impure"


def test_api_detail_view_exposes_explicit_pure(client):
    atom = _valid_atom("com.example.p0b-api-pure", fn="pure_fn")
    atom["side_effect"] = "pure"
    assert client.post("/atoms", json=atom).status_code == 201
    stored = client.get("/atoms/com.example.p0b-api-pure").json()
    assert stored["side_effect"] == "pure"


def test_api_list_view_exposes_side_effect(client):
    atom = _valid_atom("com.example.p0b-api-list", fn="list_fn")
    atom["side_effect"] = "pure"
    client.post("/atoms", json=atom)
    client.post("/atoms", json=_valid_atom("com.example.p0b-api-list2", fn="list_fn2"))
    listed = client.get("/atoms").json()
    assert len(listed) == 2
    by_id = {a["atom_id"]: a for a in listed}
    assert by_id["com.example.p0b-api-list"]["side_effect"] == "pure"
    assert by_id["com.example.p0b-api-list2"]["side_effect"] == "impure"


def test_api_submit_invalid_meta_returns_error_with_path(client):
    atom = _valid_atom()
    atom["side_effect"] = "dirty"
    r = client.post("/atoms", json=atom)
    assert r.status_code == 409
    assert "side_effect" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 6. 星级权重：pure 原子 +0.5（marketplace.composite_score 已存在评分计算）
# ---------------------------------------------------------------------------


def test_pure_atom_gets_star_rating_bonus(conn):
    impure = _valid_atom("com.example.p0b-score-impure", fn="score_fn_a")
    pure = _valid_atom("com.example.p0b-score-pure", fn="score_fn_b")
    pure["side_effect"] = "pure"
    assert submit_atom(conn, impure)["success"] is True
    assert submit_atom(conn, pure)["success"] is True
    impure_score = composite_score(conn, "com.example.p0b-score-impure")
    pure_score = composite_score(conn, "com.example.p0b-score-pure")
    assert impure_score["purity_bonus"] == 0.0
    assert pure_score["purity_bonus"] == 0.5
    assert pure_score["score"] == pytest.approx(impure_score["score"] + 0.5)
