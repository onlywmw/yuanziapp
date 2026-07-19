"""Tests for v2.1 I/O 类型枚举与副作用标签（side_effect）的 schema 校验。

规格来源：docs/DESIGN_ATOM_FOUNDATION_V2.md §2（I/O Schema）与 §6（副作用标签）。
跨代理契约：
- I/O 类型枚举 = 严格小写三值 ["json", "stream", "file_ref"]，默认 "json"；
- 副作用标签字段名 = "side_effect"，枚举 ["pure", "impure"]，默认 "impure"；
- 缺省值由注册侧归一化，schema 层不强制必填。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from register_mcp_atoms import build_registry_atom, validate_atom

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "atom-registry-schema.json").read_text(
        encoding="utf-8"
    )
)


def _valid_atom():
    return build_registry_atom(
        {
            "atom_id": "mcp.demo",
            "label": "Demo",
            "description": "demo atom",
            "capabilities": ["mcp/demo/ping"],
        }
    )


def _set_io_type(atom, io_kind, field, value):
    """把第一个 function 的 input/output schema 的 type 改成指定值。"""
    atom["purpose"]["functions"][0][field]["type"] = value


# ---------------------------------------------------------------------------
# I/O 类型枚举（§2）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["input_schema", "output_schema"])
@pytest.mark.parametrize("io_type", ["json", "stream", "file_ref"])
def test_io_type_valid_values_pass(field, io_type):
    """合法三值 json/stream/file_ref 在 input/output 两侧都必须通过。"""
    atom = _valid_atom()
    _set_io_type(atom, io_type, field, io_type)
    assert validate_atom(atom, SCHEMA) == []


@pytest.mark.parametrize("field", ["input_schema", "output_schema"])
@pytest.mark.parametrize(
    "bad_type",
    ["JSON", "Stream", "FILE_REF", "Json", "object", "binary", ""],
)
def test_io_type_invalid_values_rejected(field, bad_type):
    """大写变体与非枚举值一律拒绝（类型名称统一小写）。"""
    atom = _valid_atom()
    _set_io_type(atom, bad_type, field, bad_type)
    errors = validate_atom(atom, SCHEMA)
    assert any(field in e for e in errors)


@pytest.mark.parametrize("field", ["input_schema", "output_schema"])
def test_io_type_omitted_passes(field):
    """缺省 type 合法：默认 json 由注册侧归一化，schema 层不强制必填。"""
    atom = _valid_atom()
    del atom["purpose"]["functions"][0][field]["type"]
    assert validate_atom(atom, SCHEMA) == []


def test_io_type_schema_default_is_json():
    """schema 声明的 I/O 类型默认值必须是 json。"""
    funcs = SCHEMA["properties"]["purpose"]["properties"]["functions"]["items"]
    for field in ("input_schema", "output_schema"):
        type_def = funcs["properties"][field]["properties"]["type"]
        assert type_def["default"] == "json"
        assert type_def["enum"] == ["json", "stream", "file_ref"]


# ---------------------------------------------------------------------------
# 副作用标签（§6）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side_effect", ["pure", "impure"])
def test_side_effect_valid_values_pass(side_effect):
    """pure/impure 两值通过（顶层字段，与注册侧/CLI 模板口径一致）。"""
    atom = _valid_atom()
    atom["side_effect"] = side_effect
    assert validate_atom(atom, SCHEMA) == []


@pytest.mark.parametrize("bad_value", ["PURE", "Impure", "none", "stateful", ""])
def test_side_effect_invalid_values_rejected(bad_value):
    """大写变体与非枚举值一律拒绝。"""
    atom = _valid_atom()
    atom["side_effect"] = bad_value
    errors = validate_atom(atom, SCHEMA)
    assert any("side_effect" in e for e in errors)


def test_side_effect_omitted_passes():
    """省略 side_effect 合法：默认 impure 由注册侧归一化。"""
    atom = _valid_atom()
    assert "side_effect" not in atom
    assert validate_atom(atom, SCHEMA) == []


def test_side_effect_schema_default_is_impure():
    """schema 声明的 side_effect 默认值必须是 impure。"""
    side_effect = SCHEMA["properties"]["side_effect"]
    assert side_effect["default"] == "impure"
    assert side_effect["enum"] == ["pure", "impure"]
