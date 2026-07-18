"""Tests for the workflow execution engine (M7 task 7.3)."""

from __future__ import annotations

import sqlite3

import pytest
from engine import get_run, list_workflow_runs, run_workflow
from migrations import migrate
from workflow import save_workflow


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def _calc_hash_workflow():
    return {
        "workflow_id": "wf_calc_hash",
        "name": "计算并哈希",
        "author": "test",
        "nodes": [
            {"id": "p1", "type": "param", "key": "expression", "value": "2 + 3 * 4"},
            {"id": "n1", "atom_id": "system.math-calc"},
            {"id": "n2", "atom_id": "system.hash-digest"},
        ],
        "channels": [
            {"id": "c0", "type": "direct", "source": "p1", "target": "n1"},
            {
                "id": "c1",
                "type": "map",
                "source": "n1",
                "target": "n2",
                "mapping": {"result": "text"},
                "convert": {"text": "str"},
            },
        ],
    }


def test_run_success_end_to_end(conn):
    save_workflow(conn, _calc_hash_workflow())
    run = run_workflow(conn, "wf_calc_hash")
    assert run["status"] == "SUCCESS"
    assert [n["node"] for n in run["node_runs"]] == ["p1", "n1", "n2"]
    assert all(n["status"] == "SUCCESS" for n in run["node_runs"])
    assert run["run_id"]

    # 运行记录落库
    saved = get_run(conn, run["run_id"])
    assert saved["status"] == "SUCCESS"
    assert list_workflow_runs(conn, "wf_calc_hash")[0]["run_id"] == run["run_id"]


def test_run_param_override(conn):
    save_workflow(conn, _calc_hash_workflow())
    run1 = run_workflow(conn, "wf_calc_hash", params={"expression": "1 + 1"})
    run2 = run_workflow(conn, "wf_calc_hash", params={"expression": "2 + 2"})
    # 覆盖参数后两次运行的哈希不同
    assert run1["status"] == run2["status"] == "SUCCESS"


def test_run_node_failure_retries_and_stops(conn):
    wf = _calc_hash_workflow()
    wf["nodes"][0]["value"] = "__import__('os')"  # math-calc 拒绝
    save_workflow(conn, wf)

    run = run_workflow(conn, "wf_calc_hash", max_retries=2)
    assert run["status"] == "FAILED"
    failed_node = run["node_runs"][-1]
    assert failed_node["node"] == "n1"
    assert failed_node["status"] == "FAILED"
    assert failed_node["attempts"] == 3  # 1 + 2 retries
    assert "failed" in run["error"]
    # 后续节点未执行
    assert len(run["node_runs"]) == 2


def test_run_unknown_workflow(conn):
    run = run_workflow(conn, "wf_ghost")
    assert run["status"] == "FAILED"
    assert "not found" in run["error"]


def test_run_invalid_definition_fails_fast(conn):
    save = save_workflow(conn, _calc_hash_workflow())
    assert save["success"]
    # 直接往库里塞一个非法定义（绕过 save 校验）
    conn.execute(
        'UPDATE workflows SET definition_json = \'{"workflow_id": "wf_calc_hash"}\' '
        "WHERE workflow_id = 'wf_calc_hash'"
    )
    conn.commit()
    run = run_workflow(conn, "wf_calc_hash")
    assert run["status"] == "FAILED"
    assert "missing required field" in run["error"]


def test_run_merge_channel(conn, tmp_path, monkeypatch):
    target = tmp_path / "out.txt"
    monkeypatch.setenv("ATOM_FILE_ROOTS", str(tmp_path))
    wf = {
        "workflow_id": "wf_merge",
        "name": "合并写入",
        "author": "test",
        "nodes": [
            {"id": "p1", "type": "param", "key": "path", "value": str(target)},
            {"id": "p2", "type": "param", "key": "content", "value": "hello"},
            {"id": "n1", "atom_id": "system.file-write"},
        ],
        "channels": [
            {"id": "c1", "type": "merge", "source": ["p1", "p2"], "target": "n1"},
        ],
    }
    save_workflow(conn, wf)
    run = run_workflow(conn, "wf_merge")
    assert run["status"] == "SUCCESS", run
    assert target.read_text() == "hello"


def test_run_registered_atom_not_runnable(conn):
    wf = {
        "workflow_id": "wf_reg",
        "name": "注册原子",
        "author": "test",
        "nodes": [
            {"id": "p1", "type": "param", "key": "text", "value": "x"},
            {"id": "n1", "atom_id": "mcp.postgres"},
        ],
        "channels": [{"id": "c1", "type": "direct", "source": "p1", "target": "n1"}],
    }
    save_workflow(conn, wf)
    run = run_workflow(conn, "wf_reg")
    assert run["status"] == "FAILED"
    assert "not runnable" in run["error"]
