"""system.ai（AI 意图理解原子）的 workflow/引擎集成测试（DESIGN_AI_INTENT_ATOM 落地）。

覆盖：
- BASE_ATOM_IO 条目与定稿 I/O 契约一致
- validate_workflow 对含 system.ai 节点的工作流不再报 unknown base atom
- 必填输入 query 覆盖检查与 I/O 交集检查对 system.ai 生效
- engine._load_base_handler('system.ai') 经目录约定加载 handler 并返回契约键
  （依赖 base-atoms/ai/core.py，由原子本体任务交付；未落盘时本模块相关用例 skip）
"""

from __future__ import annotations

import sqlite3

import pytest
from migrations import migrate

import engine
from engine import run_workflow
from workflow import BASE_ATOM_IO, save_workflow, validate_workflow

# 定稿 I/O 契约（设计文档 / 审计 / 代码三方一致）
AI_REQUIRED_INPUTS = {"query"}
AI_OUTPUTS = {"intent", "params", "matched_atoms", "matched_workflows", "confidence", "source"}


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def _ai_workflow():
    """param(query) -> system.ai 的最小合法工作流。"""
    return {
        "workflow_id": "wf_ai",
        "name": "AI 意图理解",
        "author": "test",
        "nodes": [
            {"id": "p1", "type": "param", "key": "query", "value": "播放一点轻音乐"},
            {"id": "n1", "atom_id": "system.ai"},
        ],
        "channels": [
            {"id": "c0", "type": "direct", "source": "p1", "target": "n1"},
        ],
    }


def _load_ai_handler_or_skip():
    """加载 system.ai 的 handler；原子文件未落盘时 skip 并注明原因。"""
    try:
        return engine._load_base_handler("system.ai")
    except ValueError as exc:
        pytest.skip(
            "system.ai 原子文件尚未落盘（base-atoms/ai/core.py 缺失），"
            f"待原子本体交付后本用例自动生效：{exc}"
        )


# ---------- BASE_ATOM_IO 条目 ----------


def test_base_atom_io_entry_matches_contract():
    assert "system.ai" in BASE_ATOM_IO
    required, outputs = BASE_ATOM_IO["system.ai"]
    assert required == AI_REQUIRED_INPUTS
    assert outputs == AI_OUTPUTS


# ---------- validate_workflow ----------


def test_ai_node_no_unknown_base_atom_warning():
    result = validate_workflow(_ai_workflow())
    assert result["valid"], result["errors"]
    assert not any("unknown base atom" in w for w in result["warnings"])


def test_ai_required_query_missing():
    """map 通道未提供 query 时必须报必填输入缺失。"""
    wf = {
        "workflow_id": "wf_ai_bad",
        "name": "x",
        "author": "y",
        "nodes": [
            {"id": "p1", "type": "param", "key": "expression", "value": "1+1"},
            {"id": "n1", "atom_id": "system.math-calc"},
            {"id": "n2", "atom_id": "system.ai"},
        ],
        "channels": [
            {"id": "c0", "type": "direct", "source": "p1", "target": "n1"},
            {
                "id": "c1",
                "type": "map",
                "source": "n1",
                "target": "n2",
                "mapping": {"result": "not_query"},
            },
        ],
    }
    result = validate_workflow(wf)
    assert not result["valid"]
    assert any("required input 'query'" in e for e in result["errors"])


def test_ai_io_intersection_check():
    """math-calc 输出 {result} 与 system.ai 输入 {query} 无交集 → 警告。"""
    wf = {
        "workflow_id": "wf_ai_intersect",
        "name": "x",
        "author": "y",
        "nodes": [
            {"id": "p1", "type": "param", "key": "expression", "value": "1+1"},
            {"id": "n1", "atom_id": "system.math-calc"},
            {"id": "n2", "atom_id": "system.ai"},
        ],
        "channels": [
            {"id": "c0", "type": "direct", "source": "p1", "target": "n1"},
            {"id": "c1", "type": "direct", "source": "n1", "target": "n2"},
        ],
    }
    result = validate_workflow(wf)
    # direct 通道整体传递，必填覆盖满足（valid），但 I/O 无交集要警告
    assert result["valid"], result["errors"]
    assert any("没有交集" in w for w in result["warnings"])


# ---------- engine 加载与执行 ----------


def test_load_base_handler_and_run_minimal_payload():
    handler = _load_ai_handler_or_skip()
    result = handler({"query": "明天出门要带伞吗"})
    assert result["status"] == "success", result
    data = result["data"]
    # 契约键齐全
    assert AI_OUTPUTS <= set(data.keys())
    assert isinstance(data["intent"], str)
    assert isinstance(data["params"], dict)
    assert isinstance(data["matched_atoms"], list)
    assert isinstance(data["matched_workflows"], list)
    assert 0.0 <= data["confidence"] <= 1.0
    assert data["source"] in ("rules", "onnx")


def test_run_workflow_with_ai_node(conn):
    _load_ai_handler_or_skip()
    assert save_workflow(conn, _ai_workflow())["success"]
    run = run_workflow(conn, "wf_ai")
    assert run["status"] == "SUCCESS", run["error"]
    ai_node = next(n for n in run["node_runs"] if n.get("atom_id") == "system.ai")
    assert ai_node["status"] == "SUCCESS"
