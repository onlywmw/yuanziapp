"""基础层 v2：classification 分类扩展字段 + I/O Schema 注册验证测试
（docs/DESIGN_ATOM_FOUNDATION_V2.md §3「分类扩展字段」/§2「I/O Schema」）。

覆盖八组契约（全部 hermetic：内存库 + submit_atom 直调，不碰真实
registry.db、不触网）：

§3 分类扩展字段（classification 下六个可选新字段）：
1. style/audience/mood/quality/use_case/narrative 六字段合法值全部通过注册、
   无警告，并随 classification_json 持久化读回；
2. style/audience/use_case 超过 3 个 → 拒绝注册；含枚举外值 → 拒绝注册；
   恰 3 个 → 通过；
3. mood/quality 单选枚举外值（或单选字段给数组）→ 拒绝注册
   （use_case 数组枚举外值已在第 2 组覆盖）；
4. narrative 与 description 完全一致 → 警告但注册成功；narrative 含明显
   占位词（测试/todo/123）→ 警告；narrative 正常 → 无警告；
5. quality=handcrafted → 警告（Audit 审核）；quality=experimental 且
   use_case=[生产环境] → 冲突警告；experimental + 学习 → 无冲突警告；
6. 无警告时 result["warnings"] == []；警告同时写入审计链（atom_audit_log）；
7.（§2）I/O 类型 type=json/stream/file_ref 合法通过；type=JSON（大写）→
   拒绝；type=yaml → 拒绝；缺省不写 type → 通过；
8. 六个字段全不填 → 零影响通过（所有字段可选，不填不影响注册）。

实现口径（与 P0-B 注册验证同款）：字段定义落在 atom-registry-schema.json，
submit_atom 经 validate_atom_meta 拒绝非法值（error == "schema_validation"，
message 带字段路径）；警告不拦截注册，由 submit_atom 返回 result["warnings"]
列表并写入审计链。
"""

from __future__ import annotations

import sqlite3

import pytest
from migrations import migrate
from registry import get_atom, submit_atom


def _valid_atom(atom_id, fn="ping"):
    """完全符合 atom-registry-schema.json 的最小 meta（存量欠账字段一并补齐）。

    与 tests/test_registration_validation.py 的 _valid_atom 同款 fixture 惯例。
    """
    return {
        "atom_id": atom_id,
        "name": "Foundation V2",
        "version": "1.0.0",
        "description": "基础层 v2 演示原子",
        "purpose": {
            "summary": "演示分类扩展字段与 I/O 注册验证",
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


def _assert_rejected(result, field_path):
    """拒绝注册的统一形状：success=False + schema_validation + message 带字段路径。"""
    assert result["success"] is False, result
    assert result["error"] == "schema_validation", result
    assert field_path in result["message"], result


def _warnings_about(result, *keywords):
    """断言 warnings 为非空列表，且至少一条提及任一关键词（大小写不敏感）。"""
    warnings = result["warnings"]  # 契约：submit_atom 始终返回 warnings 列表
    assert isinstance(warnings, list), result
    assert warnings, result
    text = " | ".join(str(w) for w in warnings).lower()
    assert any(keyword.lower() in text for keyword in keywords), result


# ---------------------------------------------------------------------------
# 1. §3：六字段合法值全部通过注册且无警告
# ---------------------------------------------------------------------------


def test_all_six_fields_valid_register_without_warnings(conn):
    """§3：六字段合法值全部通过注册、零警告，并随 classification_json 持久化。"""
    atom = _valid_atom("com.example.fv2-six-fields")
    atom["classification"] = {
        "style": ["极简", "可靠"],
        "audience": ["后端开发", "极客"],
        "mood": "专注",
        "quality": "polished",
        "use_case": ["日常工作", "原型开发"],
        "narrative": "为夜班工程师写的最小待命面板，第一版成稿于长途火车上。",
    }
    expected_classification = dict(atom["classification"])
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    assert result["warnings"] == [], result

    stored = get_atom(conn, "com.example.fv2-six-fields")
    assert stored is not None
    for key, value in expected_classification.items():
        assert stored["classification"][key] == value


# ---------------------------------------------------------------------------
# 2. §3：style/audience/use_case 超 3 个拒绝 / 枚举外值拒绝 / 恰 3 个通过
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,values",
    [
        ("style", ["极简", "可靠", "专业", "优雅"]),
        ("audience", ["后端开发", "设计师", "学生", "所有人"]),
        ("use_case", ["日常工作", "生产环境", "学习", "原型开发"]),
    ],
    ids=["style", "audience", "use_case"],
)
def test_multi_select_over_limit_rejected(conn, field, values):
    """§3：style/audience/use_case 最多 3 个——4 个合法枚举值同样拒绝注册。"""
    atom = _valid_atom(f"com.example.fv2-{field}-overflow")
    atom["classification"] = {field: values}
    result = submit_atom(conn, atom, actor="tester")
    _assert_rejected(result, f"classification.{field}")


@pytest.mark.parametrize(
    "field,values",
    [
        ("style", ["极简", "花哨"]),
        ("audience", ["学生", "外星人"]),
        ("use_case", ["学习", "打游戏"]),
    ],
    ids=["style", "audience", "use_case"],
)
def test_multi_select_out_of_enum_rejected(conn, field, values):
    """§3：多选字段含枚举外值 → 拒绝注册（即使个数未超上限）。"""
    atom = _valid_atom(f"com.example.fv2-{field}-badvalue")
    atom["classification"] = {field: values}
    result = submit_atom(conn, atom, actor="tester")
    _assert_rejected(result, f"classification.{field}")


def test_multi_select_exactly_three_registers(conn):
    """§3：style/audience/use_case 恰 3 个（达上限）→ 通过且无警告。"""
    atom = _valid_atom("com.example.fv2-exactly-three")
    atom["classification"] = {
        "style": ["极简", "可靠", "专业"],
        "audience": ["后端开发", "设计师", "学生"],
        "use_case": ["日常工作", "学习", "原型开发"],
    }
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    assert result["warnings"] == [], result


# ---------------------------------------------------------------------------
# 3. §3：mood/quality 单选枚举外值（或单选字段给数组）→ 拒绝注册
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug,field,value",
    [
        ("mood-bad-enum", "mood", "狂喜"),
        ("quality-bad-enum", "quality", "传世之作"),
        ("mood-not-single", "mood", ["专注", "平静"]),
    ],
    ids=["mood-bad-enum", "quality-bad-enum", "mood-not-single"],
)
def test_single_select_invalid_rejected(conn, slug, field, value):
    """§3：mood/quality 为单选——枚举外值拒绝；单选字段给数组同样拒绝。"""
    atom = _valid_atom(f"com.example.fv2-{slug}")
    atom["classification"] = {field: value}
    result = submit_atom(conn, atom, actor="tester")
    _assert_rejected(result, f"classification.{field}")


# ---------------------------------------------------------------------------
# 4. §3：narrative 警告规则（不拦截注册）
# ---------------------------------------------------------------------------


def test_narrative_same_as_description_warns_but_registers(conn):
    """§3：narrative 与 description 完全一致 → 警告，但注册成功。"""
    text = "这段叙事与简介完全一致的演示文本。"
    atom = _valid_atom("com.example.fv2-narrative-echo")
    atom["description"] = text
    atom["classification"] = {"narrative": text}
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    _warnings_about(result, "narrative", "description")


@pytest.mark.parametrize(
    "narrative",
    [
        "这个原子还在测试阶段，内容以后再补。",
        "todo：等有空了再认真补完这段叙事。",
        "先随便写上 123 充数，之后再完善。",
    ],
    ids=["word-ceshi", "word-todo", "word-123"],
)
def test_narrative_placeholder_words_warn(conn, narrative):
    """§3：narrative 含明显占位词（测试/todo/123）→ 警告，但注册成功。"""
    atom = _valid_atom("com.example.fv2-narrative-placeholder")
    atom["classification"] = {"narrative": narrative}
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    _warnings_about(result, "narrative", "占位", "placeholder")


def test_narrative_normal_no_warning(conn):
    """§3：narrative 正常（10-200 字、非占位、不与 description 重复）→ 无警告。"""
    atom = _valid_atom("com.example.fv2-narrative-good")
    atom["classification"] = {
        "narrative": "作者在长途火车上写下第一版，为夜班工程师保留的最小待命面板。"
    }
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    assert result["warnings"] == [], result


# ---------------------------------------------------------------------------
# 5. §3：quality 警告规则（不拦截注册）
# ---------------------------------------------------------------------------


def test_quality_handcrafted_warns_but_registers(conn):
    """§3：quality=handcrafted → 警告（提示 Audit 审核），但注册成功。"""
    atom = _valid_atom("com.example.fv2-handcrafted")
    atom["classification"] = {"quality": "handcrafted"}
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    _warnings_about(result, "handcrafted", "审核", "audit")


def test_experimental_production_conflict_warns(conn):
    """§3：quality=experimental 且 use_case=[生产环境] → 冲突警告，但注册成功。"""
    atom = _valid_atom("com.example.fv2-exp-prod")
    atom["classification"] = {"quality": "experimental", "use_case": ["生产环境"]}
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    _warnings_about(result, "experimental", "冲突", "生产")


def test_experimental_learning_no_conflict_warning(conn):
    """§3：quality=experimental 且 use_case=[学习] → 无冲突警告（学习场景合理）。"""
    atom = _valid_atom("com.example.fv2-exp-learn")
    atom["classification"] = {"quality": "experimental", "use_case": ["学习"]}
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    assert result["warnings"] == [], result


# ---------------------------------------------------------------------------
# 6. §3：warnings 形状与审计链
# ---------------------------------------------------------------------------


def test_result_warnings_empty_list_when_no_warning(conn):
    """§3：无警告时 result["warnings"] 为空列表（键存在且 == []，不是缺失/None）。"""
    atom = _valid_atom("com.example.fv2-no-warning")
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    assert result["warnings"] == [], result


def test_warnings_written_to_audit_chain(conn):
    """§3：注册产生的警告同时写入审计链（atom_audit_log 行的 detail 含警告信息）。"""
    atom = _valid_atom("com.example.fv2-audit-warnings")
    atom["classification"] = {"quality": "handcrafted"}
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    assert result["warnings"], result

    rows = conn.execute(
        "SELECT action, detail FROM atom_audit_log WHERE atom_id = ? ORDER BY id",
        ("com.example.fv2-audit-warnings",),
    ).fetchall()
    assert rows, "submit 必须落审计行"
    assert rows[0][0] == "submit"
    details = " ".join(str(row[1] or "") for row in rows)
    assert "warning" in details.lower() or "handcrafted" in details, rows


# ---------------------------------------------------------------------------
# 7. §2：I/O Schema 注册验证（input_schema/output_schema 的 type 枚举）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["input_schema", "output_schema"])
@pytest.mark.parametrize("io_type", ["json", "stream", "file_ref"])
def test_io_type_valid_values_register(conn, field, io_type):
    """§2：I/O 类型严格小写三值 json/stream/file_ref，输入输出两侧均通过注册。"""
    side = "in" if field == "input_schema" else "out"
    atom = _valid_atom(f"com.example.fv2-io-{side}-{io_type.replace('_', '-')}")
    atom["purpose"]["functions"][0][field] = {"type": io_type}
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result


@pytest.mark.parametrize("field", ["input_schema", "output_schema"])
@pytest.mark.parametrize("bad_type", ["JSON", "yaml"])
def test_io_type_invalid_values_rejected(conn, field, bad_type):
    """§2：类型名称统一小写——大写 JSON 与非枚举 yaml 一律拒绝注册。"""
    side = "in" if field == "input_schema" else "out"
    atom = _valid_atom(f"com.example.fv2-io-{side}-bad-{bad_type.lower()}")
    atom["purpose"]["functions"][0][field] = {"type": bad_type}
    result = submit_atom(conn, atom, actor="tester")
    _assert_rejected(result, field)


@pytest.mark.parametrize("field", ["input_schema", "output_schema"])
def test_io_type_omitted_registers(conn, field):
    """§2：缺省不写 type 通过（默认 json，由注册侧归一化，schema 层不强制必填）。"""
    side = "in" if field == "input_schema" else "out"
    atom = _valid_atom(f"com.example.fv2-io-{side}-default")
    atom["purpose"]["functions"][0][field] = {"description": "只写说明不声明类型"}
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result


# ---------------------------------------------------------------------------
# 8. §3：六个字段全不填 → 零影响通过
# ---------------------------------------------------------------------------


def test_all_six_fields_omitted_zero_impact(conn):
    """§3：六个扩展字段全部不填 → 零影响，正常注册（所有字段可选）。"""
    atom = _valid_atom("com.example.fv2-plain")
    assert "classification" not in atom
    result = submit_atom(conn, atom, actor="tester")
    assert result["success"] is True, result
    stored = get_atom(conn, "com.example.fv2-plain")
    assert stored is not None
    assert stored["lifecycle"]["status"] == "submitted"
