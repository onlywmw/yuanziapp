#!/usr/bin/env python3
"""工作流 DAG 数据模型与连线验证引擎（M7 任务 7.2a/7.2c）。

验证规则（DESIGN_M7 §3.3 + WORKFLOW_CONNECTION_RULES + ATOM_CONNECTION_RULES）：
1. 连线类型匹配（direct/map/transform/merge/split）
2. 无孤立节点
3. 无环（DAG）
4. 必填参数已覆盖（通道或 param 节点提供；key 类参数允许来自系统配置）
5. 危险链警告（入站→写文件、读文件→出站、解密→出站、外网输入→执行）
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

CHANNEL_TYPES = {"direct", "map", "transform", "merge", "split"}

# 基础原子 I/O（WORKFLOW_CONNECTION_RULES §一）：
# (必填输入集合, 输出字段集合)
BASE_ATOM_IO: Dict[str, tuple] = {
    "system.file-dir": ({"path"}, {"entries", "count"}),
    "system.file-read": ({"path"}, {"path", "size", "mode", "content"}),
    "system.file-write": ({"path", "content"}, {"path", "written"}),
    "system.http-get": ({"url"}, {"status_code", "headers", "body", "truncated"}),
    "system.http-post": ({"url"}, {"status_code", "headers", "body", "truncated"}),
    "system.math-calc": ({"expression"}, {"result"}),
    "system.string-split": ({"text"}, {"parts", "count"}),
    "system.string-match": ({"text", "pattern"}, {"matches", "count"}),
    "system.json-parse": ({"text"}, {"data"}),
    "system.date-time": (set(), {"result"}),
    "system.hash-digest": ({"text"}, {"digest", "algorithm"}),
    "system.encrypt-aes": ({"text"}, {"ciphertext", "iv", "mode"}),
    "system.decrypt-aes": ({"ciphertext", "iv"}, {"text"}),
    # AI 意图理解原子（DESIGN_AI_INTENT_ATOM）：输入 query（context 可选），
    # 输出 intent/params/matched_atoms/matched_workflows/confidence/source
    "system.ai": (
        {"query"},
        {"intent", "params", "matched_atoms", "matched_workflows", "confidence", "source"},
    ),
}

# 允许来自系统配置/环境变量的参数（规则 2 的例外，速查表示例 2）
SYSTEM_PROVIDED_INPUTS = {"key", "headers", "timeout", "encoding", "mode", "algorithm"}

# 危险链模式（ATOM_CONNECTION_RULES §三）→ 警告
_DANGER_PATTERNS = [
    (
        {"system.http-get", "system.http-post"},
        {"system.file-write"},
        "入站内容直接写文件",
    ),
    (
        {"system.file-read"},
        {"system.http-get", "system.http-post"},
        "本地文件内容可能外泄",
    ),
    (
        {"system.decrypt-aes"},
        {"system.http-post", "system.file-write"},
        "解密数据流向不受控位置",
    ),
    (
        {"system.http-get", "system.http-post"},
        {"system.math-calc", "system.string-match"},
        "外部输入作为代码/正则执行",
    ),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_workflow(definition: Dict[str, Any]) -> Dict[str, Any]:
    """校验工作流定义，返回 {"valid": bool, "errors": [...], "warnings": [...]}。"""
    errors: List[str] = []
    warnings: List[str] = []

    for field in ("workflow_id", "name", "author"):
        if not definition.get(field):
            errors.append(f"missing required field: {field}")

    nodes = definition.get("nodes") or []
    channels = definition.get("channels") or []
    node_ids: Set[str] = set()
    for node in nodes:
        nid = node.get("id")
        if not nid:
            errors.append("node missing id")
            continue
        if nid in node_ids:
            errors.append(f"duplicate node id: {nid}")
        node_ids.add(nid)

    def node_by_id(nid: str) -> Optional[Dict[str, Any]]:
        return next((n for n in nodes if n.get("id") == nid), None)

    # ---- 通道结构与端点 ----
    connected: Set[str] = set()
    for ch in channels:
        ctype = ch.get("type", "direct")
        if ctype not in CHANNEL_TYPES:
            errors.append(f"channel {ch.get('id')}: unknown type '{ctype}'")
        source = ch.get("source")
        target = ch.get("target")
        sources = source if isinstance(source, list) else [source]
        if ctype == "merge" and not isinstance(source, list):
            errors.append(f"channel {ch.get('id')}: merge requires a list of sources")
        if ctype != "merge" and isinstance(source, list):
            errors.append(
                f"channel {ch.get('id')}: only merge accepts a list of sources"
            )
        for sid in sources:
            if sid not in node_ids:
                errors.append(f"channel {ch.get('id')}: unknown source node '{sid}'")
        if target not in node_ids:
            errors.append(f"channel {ch.get('id')}: unknown target node '{target}'")
        if isinstance(source, str) and source == target:
            errors.append(f"channel {ch.get('id')}: self loop on node '{source}'")
        connected.update(s for s in sources if s)
        if target:
            connected.add(target)

    # ---- 无孤立节点（规则 2）----
    for node in nodes:
        nid = node.get("id")
        if nid and nid not in connected and len(nodes) > 1:
            errors.append(f"isolated node: {nid}")

    # ---- 无环（规则 3/5）----
    edges: Dict[str, List[str]] = {}
    for ch in channels:
        target = ch.get("target")
        for sid in (
            ch.get("source")
            if isinstance(ch.get("source"), list)
            else [ch.get("source")]
        ):
            if sid and target:
                edges.setdefault(sid, []).append(target)
    states: Dict[str, str] = {}
    cycle_path: List[str] = []

    def _dfs(nid: str, path: List[str]) -> bool:
        states[nid] = "visiting"
        for nxt in edges.get(nid, []):
            if states.get(nxt) == "visiting":
                cycle_path.extend(path + [nid, nxt])
                return True
            if states.get(nxt) is None and _dfs(nxt, path + [nid]):
                return True
        states[nid] = "done"
        return False

    for nid in node_ids:
        if states.get(nid) is None and _dfs(nid, []):
            errors.append(f"cycle detected: {' -> '.join(cycle_path)}")
            break

    # ---- 类型匹配 + 必填参数覆盖（规则 1/2/4）----
    incoming: Dict[str, List[Dict[str, Any]]] = {}
    for ch in channels:
        if ch.get("target"):
            incoming.setdefault(ch["target"], []).append(ch)

    param_nodes = {n["id"]: n for n in nodes if n.get("type") == "param"}

    for node in nodes:
        atom_id = node.get("atom_id", "")
        if node.get("type") == "param":
            continue
        io = BASE_ATOM_IO.get(atom_id)
        if io is None:
            if atom_id.startswith("system."):
                warnings.append(f"node {node.get('id')}: unknown base atom '{atom_id}'")
            continue  # 注册原子的 I/O 由 meta 决定，跳过静态检查
        required, _outputs = io
        provided: Set[str] = set()
        for ch in incoming.get(node["id"], []):
            ctype = ch.get("type", "direct")
            if ctype in ("map", "transform"):
                mapping = ch.get("mapping") or {}
                provided.update(mapping.values())
            else:  # direct / merge / split 整体传递
                provided.update(required)
        for pid, pnode in param_nodes.items():
            target_key = pnode.get("key")
            # param 节点经通道连到本节点时提供对应 key
            for ch in incoming.get(node["id"], []):
                srcs = ch.get("source")
                srcs = srcs if isinstance(srcs, list) else [srcs]
                if pid in srcs and target_key:
                    provided.add(target_key)
        missing = required - provided - SYSTEM_PROVIDED_INPUTS
        for field in sorted(missing):
            errors.append(
                f"node {node['id']} ({atom_id}): required input '{field}' has no source"
            )

        # direct 连线的输出字段必须被目标接受（通道模型 §二.1）
        for ch in incoming.get(node["id"], []):
            if ch.get("type", "direct") != "direct":
                continue
            srcs = ch.get("source")
            srcs = srcs if isinstance(srcs, list) else [srcs]
            for sid in srcs:
                snode = node_by_id(sid)
                if not snode or snode.get("type") == "param":
                    continue
                sio = BASE_ATOM_IO.get(snode.get("atom_id", ""))
                if sio and not (sio[1] & (required | SYSTEM_PROVIDED_INPUTS)):
                    warnings.append(
                        f"channel {ch.get('id')}: {snode.get('atom_id')} 的输出与 "
                        f"{atom_id} 的输入没有交集，可能是无意义连线"
                    )

    # ---- 危险链警告（规则 5）----
    for ch in channels:
        srcs = ch.get("source")
        srcs = srcs if isinstance(srcs, list) else [srcs]
        target_node = node_by_id(ch.get("target", ""))
        if not target_node:
            continue
        for sid in srcs:
            snode = node_by_id(sid)
            if not snode:
                continue
            for src_set, dst_set, label in _DANGER_PATTERNS:
                if (
                    snode.get("atom_id") in src_set
                    and target_node.get("atom_id") in dst_set
                ):
                    warnings.append(
                        f"channel {ch.get('id')}: 危险链 - {label} "
                        f"({snode.get('atom_id')} -> {target_node.get('atom_id')})"
                    )

    return {"valid": not errors, "errors": errors, "warnings": warnings}


# ---------- 存储 ----------


def save_workflow(
    conn: sqlite3.Connection, definition: Dict[str, Any]
) -> Dict[str, Any]:
    """验证并保存工作流定义。验证失败不写入。"""
    result = validate_workflow(definition)
    if not result["valid"]:
        return {
            "success": False,
            "errors": result["errors"],
            "warnings": result["warnings"],
        }

    now = _now_iso()
    workflow_id = definition["workflow_id"]
    existing = conn.execute(
        "SELECT created_at FROM workflows WHERE workflow_id = ?", (workflow_id,)
    ).fetchone()
    created_at = existing[0] if existing else now
    conn.execute(
        """
        INSERT INTO workflows (workflow_id, name, author, definition_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(workflow_id) DO UPDATE SET
            name=excluded.name,
            author=excluded.author,
            definition_json=excluded.definition_json,
            updated_at=excluded.updated_at
        """,
        (
            workflow_id,
            definition["name"],
            definition["author"],
            json.dumps(definition, ensure_ascii=False),
            created_at,
            now,
        ),
    )
    conn.commit()
    return {
        "success": True,
        "workflow_id": workflow_id,
        "warnings": result["warnings"],
    }


def get_workflow(
    conn: sqlite3.Connection, workflow_id: str
) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT workflow_id, name, author, definition_json, created_at, updated_at "
        "FROM workflows WHERE workflow_id = ?",
        (workflow_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "workflow_id": row[0],
        "name": row[1],
        "author": row[2],
        "definition": json.loads(row[3]),
        "created_at": row[4],
        "updated_at": row[5],
    }


def list_workflows(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT workflow_id, name, author, created_at, updated_at FROM workflows "
        "ORDER BY workflow_id"
    ).fetchall()
    return [
        {
            "workflow_id": r[0],
            "name": r[1],
            "author": r[2],
            "created_at": r[3],
            "updated_at": r[4],
        }
        for r in rows
    ]
