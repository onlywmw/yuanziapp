#!/usr/bin/env python3
"""工作流执行引擎（M7 任务 7.3）。

执行模型：拓扑排序 → 逐节点执行 → 通道转换 → 写运行记录。
- 基础原子（system.*）：本地加载 base-atoms/<name>/core.py 的 handler 执行
- 注册原子：POST 其 runtime.endpoint/run（http/https）
- 失败策略：重试 max_retries 次（间隔递增），最终失败则工作流 FAILED
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from workflow import get_workflow, validate_workflow


def _resolve_base_atoms_dir() -> Path:
    """base-atoms 目录：仓库布局（上级）或 Chaquopy 打包布局（同级）。"""
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "base-atoms", here / "base-atoms"):
        if candidate.exists():
            return candidate
    return here.parent / "base-atoms"


BASE_ATOMS_DIR = _resolve_base_atoms_dir()

STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_CANCELLED = "CANCELLED"

_http_post: Optional[Callable] = None  # 测试可注入


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _load_base_handler(atom_id: str) -> Callable:
    """加载基础原子 handler：system.<name> -> base-atoms/<name>/core.py。"""
    name = atom_id.split(".", 1)[1]
    path = BASE_ATOMS_DIR / name / "core.py"
    if not path.exists():
        raise ValueError(f"unknown base atom: {atom_id}")
    spec = importlib.util.spec_from_file_location(f"wf_core_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.handler


def _default_http_post(
    url: str, payload: Dict[str, Any], timeout: float = 10.0
) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _topo_order(
    nodes: List[Dict[str, Any]], channels: List[Dict[str, Any]]
) -> List[str]:
    order: List[str] = []
    states: Dict[str, str] = {}
    edges: Dict[str, List[str]] = {}
    for ch in channels:
        target = ch.get("target")
        sources = ch.get("source")
        sources = sources if isinstance(sources, list) else [sources]
        for sid in sources:
            if sid and target:
                edges.setdefault(sid, []).append(target)

    def visit(nid: str) -> None:
        if states.get(nid) == "done":
            return
        states[nid] = "visiting"
        for nxt in edges.get(nid, []):
            visit(nxt)
        states[nid] = "done"
        order.insert(0, nid)

    for node in nodes:
        visit(node["id"])
    return order


def _gather_payload(
    node_id: str,
    channels: List[Dict[str, Any]],
    outputs: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """按通道规则把上游输出组装成节点输入。"""
    payload: Dict[str, Any] = {}
    for ch in channels:
        if ch.get("target") != node_id:
            continue
        ctype = ch.get("type", "direct")
        sources = ch.get("source")
        sources = sources if isinstance(sources, list) else [sources]
        if ctype in ("map", "transform"):
            mapping = ch.get("mapping") or {}
            for sid in sources:
                src_out = outputs.get(sid, {})
                for src_field, dst_field in mapping.items():
                    if src_field in src_out:
                        payload[dst_field] = src_out[src_field]
            for field, mode in (ch.get("convert") or {}).items():
                if field in payload:
                    if mode == "str":
                        payload[field] = str(payload[field])
                    elif mode == "json":
                        payload[field] = json.dumps(payload[field], ensure_ascii=False)
        else:  # direct / merge / split：整体合并
            for sid in sources:
                payload.update(outputs.get(sid, {}))
    return payload


def _execute_node(
    atom_id: str, payload: Dict[str, Any], http_post: Callable
) -> Dict[str, Any]:
    if atom_id.startswith("system."):
        handler = _load_base_handler(atom_id)
        return handler(payload)
    raise ValueError(
        f"registered atom '{atom_id}' is not runnable in this engine "
        "(no live endpoint dispatch yet)"
    )


def run_workflow(
    conn: sqlite3.Connection,
    workflow_id: str,
    params: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    retry_delay: float = 0.0,
) -> Dict[str, Any]:
    """执行工作流并写运行记录。返回 run dict（含 node_runs）。"""
    http_post = _http_post or _default_http_post
    run_id = uuid.uuid4().hex[:12]
    started_at = _now_iso()

    def _finish(
        status: str, node_runs: List[Dict[str, Any]], error: str = ""
    ) -> Dict[str, Any]:
        finished_at = _now_iso()
        conn.execute(
            """
            INSERT INTO workflow_runs
            (run_id, workflow_id, status, node_runs_json, error, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                workflow_id,
                status,
                json.dumps(node_runs, ensure_ascii=False),
                error,
                started_at,
                finished_at,
            ),
        )
        conn.commit()
        return {
            "run_id": run_id,
            "workflow_id": workflow_id,
            "status": status,
            "error": error,
            "started_at": started_at,
            "finished_at": finished_at,
            "node_runs": node_runs,
        }

    workflow = get_workflow(conn, workflow_id)
    if not workflow:
        return _finish(STATUS_FAILED, [], f"workflow '{workflow_id}' not found")

    definition = workflow["definition"]
    validation = validate_workflow(definition)
    if not validation["valid"]:
        return _finish(STATUS_FAILED, [], "; ".join(validation["errors"]))

    nodes = definition.get("nodes", [])
    channels = definition.get("channels", [])
    overrides = params or {}

    outputs: Dict[str, Dict[str, Any]] = {}
    node_runs: List[Dict[str, Any]] = []

    for node_id in _topo_order(nodes, channels):
        node = next(n for n in nodes if n["id"] == node_id)
        started = time.monotonic()

        if node.get("type") == "param":
            key = node.get("key", "")
            value = overrides.get(key, node.get("value"))
            outputs[node_id] = {key: value}
            node_runs.append(
                {
                    "node": node_id,
                    "status": STATUS_SUCCESS,
                    "duration_ms": 0,
                    "param": key,
                }
            )
            continue

        atom_id = node.get("atom_id", "")
        payload = _gather_payload(node_id, channels, outputs)

        attempts = 0
        result: Optional[Dict[str, Any]] = None
        error = ""
        while attempts <= max_retries:
            attempts += 1
            try:
                result = _execute_node(atom_id, payload, http_post)
                if result.get("status") == "success":
                    break
                error = result.get("message", "handler returned error")
                result = None
            except Exception as exc:  # noqa: BLE001 - 节点异常进入重试策略
                error = str(exc)
                result = None
            if attempts <= max_retries and retry_delay > 0:
                time.sleep(retry_delay * attempts)

        duration_ms = round((time.monotonic() - started) * 1000, 1)
        if result is not None:
            data = result.get("data", {})
            outputs[node_id] = data if isinstance(data, dict) else {"value": data}
            node_runs.append(
                {
                    "node": node_id,
                    "atom_id": atom_id,
                    "status": STATUS_SUCCESS,
                    "duration_ms": duration_ms,
                    "attempts": attempts,
                }
            )
        else:
            node_runs.append(
                {
                    "node": node_id,
                    "atom_id": atom_id,
                    "status": STATUS_FAILED,
                    "duration_ms": duration_ms,
                    "attempts": attempts,
                    "error": error,
                }
            )
            return _finish(
                STATUS_FAILED, node_runs, f"node '{node_id}' failed: {error}"
            )

    return _finish(STATUS_SUCCESS, node_runs)


def list_workflow_runs(
    conn: sqlite3.Connection, workflow_id: str
) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT run_id, workflow_id, status, error, started_at, finished_at "
        "FROM workflow_runs WHERE workflow_id = ? ORDER BY id DESC",
        (workflow_id,),
    ).fetchall()
    return [
        {
            "run_id": r[0],
            "workflow_id": r[1],
            "status": r[2],
            "error": r[3],
            "started_at": r[4],
            "finished_at": r[5],
        }
        for r in rows
    ]


def get_run(conn: sqlite3.Connection, run_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT run_id, workflow_id, status, node_runs_json, error, started_at, finished_at "
        "FROM workflow_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "run_id": row[0],
        "workflow_id": row[1],
        "status": row[2],
        "node_runs": json.loads(row[3]),
        "error": row[4],
        "started_at": row[5],
        "finished_at": row[6],
    }
