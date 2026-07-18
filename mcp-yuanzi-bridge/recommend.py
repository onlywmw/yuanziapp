#!/usr/bin/env python3
"""原子组合推荐（M5 任务 5.3）。

推荐信号：
- 正向依赖：atom 声明的 dependencies（用它就 likely 也需要它们）
- 反向依赖：依赖 atom 的其他原子（生态位证明）
- 同类别：classification.category 相同的原子（功能相近）

recommend_for_atom：给"我已经在用 X"的场景推荐搭配。
recommend_combination：给出 X 的完整依赖闭包（拓扑序），作为一键启动组合。
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from registry import get_atom, list_atoms, resolve_dependencies

# 各信号的权重
W_DEPENDENCY = 1.0
W_DEPENDENT = 0.8
W_SAME_CATEGORY = 0.3


def find_dependents(conn: sqlite3.Connection, atom_id: str) -> List[str]:
    """找出所有把 atom_id 列为依赖的原子。"""
    dependents: List[str] = []
    for atom in list_atoms(conn):
        deps = atom.get("architecture", {}).get("dependencies", []) or []
        if atom_id in deps:
            dependents.append(atom["atom_id"])
    return dependents


def recommend_for_atom(
    conn: sqlite3.Connection, atom_id: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """为指定原子推荐搭配组合，按加权分数降序。"""
    atom = get_atom(conn, atom_id)
    if not atom:
        raise ValueError(f"Atom '{atom_id}' not found")

    scores: Dict[str, float] = {}
    reasons: Dict[str, List[str]] = {}

    def _add(target: str, weight: float, reason: str) -> None:
        if target == atom_id:
            return
        scores[target] = scores.get(target, 0.0) + weight
        reasons.setdefault(target, []).append(reason)

    for dep in atom.get("architecture", {}).get("dependencies", []) or []:
        if get_atom(conn, dep):
            _add(dep, W_DEPENDENCY, "dependency")

    for dependent in find_dependents(conn, atom_id):
        _add(dependent, W_DEPENDENT, "dependent")

    category = atom.get("classification", {}).get("category", "")
    if category:
        for other in list_atoms(conn, category=category):
            _add(other["atom_id"], W_SAME_CATEGORY, "same_category")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    results: List[Dict[str, Any]] = []
    for target, score in ranked:
        target_atom = get_atom(conn, target) or {}
        results.append(
            {
                "atom_id": target,
                "name": target_atom.get("name", ""),
                "category": target_atom.get("classification", {}).get("category", ""),
                "status": target_atom.get("lifecycle", {}).get("status", ""),
                "score": round(score, 3),
                "reasons": sorted(set(reasons[target])),
            }
        )
    return results


def recommend_combination(conn: sqlite3.Connection, atom_id: str) -> Dict[str, Any]:
    """给出原子的完整启动组合（依赖闭包，拓扑序）。

    ok=False 时 missing/cycles 说明组合不完整的原因。"""
    resolved = resolve_dependencies(conn, atom_id)
    combination: List[Dict[str, Any]] = []
    for aid in resolved["order"]:
        atom = get_atom(conn, aid) or {}
        combination.append(
            {
                "atom_id": aid,
                "name": atom.get("name", ""),
                "status": atom.get("lifecycle", {}).get("status", ""),
                "endpoint": atom.get("runtime", {}).get("endpoint", ""),
            }
        )
    return {
        "atom_id": atom_id,
        "ok": resolved["ok"],
        "missing": resolved["missing"],
        "cycles": resolved["cycles"],
        "combination": combination,
    }
