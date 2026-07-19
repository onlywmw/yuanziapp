"""依赖图解析（architecture.dependencies 拓扑序）。

由 registry.py 拆分而来（ISOLATION_HARDENING_PLAN 加固1），纯结构移动，逻辑零变化。
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from .core import get_atom


def resolve_dependencies(conn: sqlite3.Connection, atom_id: str) -> Dict[str, Any]:
    """解析原子的依赖图（architecture.dependencies）。

    返回：
    - order：拓扑序（依赖在前，目标原子在最后），可直接按序启动/安装
    - missing：引用了但未注册的 atom_id
    - cycles：检测到的循环依赖（每条为构成环的 atom_id 序列）
    - ok：无缺失且无循环时为 True
    """
    states: Dict[str, str] = {}  # atom_id -> visiting / done
    order: List[str] = []
    missing: set = set()
    cycles: List[List[str]] = []

    def visit(aid: str, path: List[str]) -> None:
        state = states.get(aid)
        if state == "done":
            return
        if state == "visiting":
            start = path.index(aid)
            cycles.append(path[start:] + [aid])
            return
        atom = get_atom(conn, aid)
        if not atom:
            missing.add(aid)
            return
        states[aid] = "visiting"
        deps = atom.get("architecture", {}).get("dependencies", []) or []
        for dep in sorted(set(deps)):
            visit(dep, path + [aid])
        states[aid] = "done"
        order.append(aid)

    visit(atom_id, [])

    deps: List[Dict[str, Any]] = []
    root = get_atom(conn, atom_id)
    if root:
        for dep_id in sorted(
            set(root.get("architecture", {}).get("dependencies", []) or [])
        ):
            dep_atom = get_atom(conn, dep_id)
            deps.append(
                {
                    "atom_id": dep_id,
                    "name": dep_atom.get("name", "") if dep_atom else "",
                    "status": (
                        dep_atom.get("lifecycle", {}).get("status", "")
                        if dep_atom
                        else "missing"
                    ),
                }
            )
    return {
        "ok": not missing and not cycles,
        "atom_id": atom_id,
        "order": order,
        "missing": sorted(missing),
        "cycles": cycles,
        "deps": deps,
    }
