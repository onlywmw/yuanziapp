"""Tests for workflow DAG validation and storage (M7 task 7.2)."""

from __future__ import annotations

import sqlite3

import pytest
from migrations import migrate
from workflow import (
    get_workflow,
    list_workflows,
    save_workflow,
    validate_workflow,
)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def _valid_workflow():
    return {
        "workflow_id": "wf_test",
        "name": "测试工作流",
        "author": "张三",
        "nodes": [
            {
                "id": "p1",
                "type": "param",
                "key": "url",
                "value": "https://api.example.com",
            },
            {"id": "n1", "atom_id": "system.http-get"},
            {"id": "n2", "atom_id": "system.json-parse"},
        ],
        "channels": [
            {"id": "c0", "type": "direct", "source": "p1", "target": "n1"},
            {
                "id": "c1",
                "type": "map",
                "source": "n1",
                "target": "n2",
                "mapping": {"body": "text"},
            },
        ],
    }


def test_valid_workflow_passes():
    result = validate_workflow(_valid_workflow())
    assert result["valid"], result["errors"]


def test_missing_meta_fields():
    result = validate_workflow({"nodes": [], "channels": []})
    assert not result["valid"]
    assert any("workflow_id" in e for e in result["errors"])
    assert any("author" in e for e in result["errors"])


def test_unknown_channel_type():
    wf = _valid_workflow()
    wf["channels"][1]["type"] = "quantum"
    result = validate_workflow(wf)
    assert not result["valid"]
    assert any("unknown type" in e for e in result["errors"])


def test_unknown_endpoint():
    wf = _valid_workflow()
    wf["channels"][1]["target"] = "ghost"
    result = validate_workflow(wf)
    assert not result["valid"]
    assert any("unknown target" in e for e in result["errors"])


def test_self_loop_rejected():
    wf = _valid_workflow()
    wf["channels"].append({"id": "c9", "source": "n1", "target": "n1"})
    result = validate_workflow(wf)
    assert not result["valid"]
    assert any("self loop" in e for e in result["errors"])


def test_cycle_rejected():
    wf = _valid_workflow()
    wf["channels"].append({"id": "c9", "source": "n2", "target": "n1"})
    result = validate_workflow(wf)
    assert not result["valid"]
    assert any("cycle" in e for e in result["errors"])


def test_isolated_node_rejected():
    wf = _valid_workflow()
    wf["nodes"].append({"id": "n9", "atom_id": "system.math-calc"})
    result = validate_workflow(wf)
    assert not result["valid"]
    assert any("isolated node: n9" in e for e in result["errors"])


def test_missing_required_input():
    # direct 通道默认覆盖（整体传递），所以这是合法的（保留 c0 避免 p1 孤立）
    wf = _valid_workflow()
    wf["channels"][1] = {"id": "c1", "type": "direct", "source": "n1", "target": "n2"}
    assert validate_workflow(wf)["valid"]

    # 但 map 通道只映射了别的字段 → text 无来源
    wf["channels"][1] = {
        "id": "c1",
        "type": "map",
        "source": "n1",
        "target": "n2",
        "mapping": {"body": "not_text"},
    }
    result = validate_workflow(wf)
    assert not result["valid"]
    assert any("required input 'text'" in e for e in result["errors"])


def test_merge_requires_list_source():
    wf = _valid_workflow()
    wf["channels"][1]["type"] = "merge"
    result = validate_workflow(wf)
    assert not result["valid"]
    assert any("merge requires a list" in e for e in result["errors"])


def test_danger_chain_warning():
    wf = {
        "workflow_id": "wf_danger",
        "name": "x",
        "author": "y",
        "nodes": [
            {"id": "p1", "type": "param", "key": "url", "value": "https://x.example"},
            {"id": "p2", "type": "param", "key": "path", "value": "/tmp/out.txt"},
            {"id": "n1", "atom_id": "system.http-get"},
            {"id": "n2", "atom_id": "system.file-write"},
        ],
        "channels": [
            {"id": "c0", "type": "direct", "source": "p1", "target": "n1"},
            {"id": "c2", "type": "direct", "source": "p2", "target": "n2"},
            {"id": "c1", "type": "direct", "source": "n1", "target": "n2"},
        ],
    }
    result = validate_workflow(wf)
    assert result["valid"]  # 警告不阻断
    assert any("危险链" in w for w in result["warnings"])


def test_save_and_get_workflow(conn):
    result = save_workflow(conn, _valid_workflow())
    assert result["success"]

    saved = get_workflow(conn, "wf_test")
    assert saved["name"] == "测试工作流"
    assert saved["author"] == "张三"
    assert len(saved["definition"]["nodes"]) == 3

    assert [w["workflow_id"] for w in list_workflows(conn)] == ["wf_test"]


def test_save_invalid_workflow_rejected(conn):
    result = save_workflow(conn, {"workflow_id": "wf_bad"})
    assert not result["success"]
    assert get_workflow(conn, "wf_bad") is None


def test_save_updates_existing(conn):
    save_workflow(conn, _valid_workflow())
    wf = _valid_workflow()
    wf["name"] = "改名了"
    save_workflow(conn, wf)
    assert get_workflow(conn, "wf_test")["name"] == "改名了"
    assert len(list_workflows(conn)) == 1
