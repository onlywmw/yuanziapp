#!/usr/bin/env python3
"""原子市场：评分、评论与热度排行（M7 任务 7.1）。

综合分 = 0.3×可用性 + 0.2×文档 + 0.4×社区 + 0.1×测试（DESIGN_M7 §2.1）
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any, Dict, List

from registry import get_atom, list_atoms, now_iso
from registry.core import resolve_side_effect

W_AVAILABILITY = 0.3
W_DOC = 0.2
W_COMMUNITY = 0.4
W_TEST = 0.1

# 副作用标签权重（DESIGN_ATOM_FOUNDATION_V2 §6）：
# pure（无副作用、可安全并行/重试/缓存）原子星级 +0.5
PURE_SIDE_EFFECT_BONUS = 0.5


def add_review(
    conn: sqlite3.Connection,
    atom_id: str,
    author: str,
    rating: int,
    text: str = "",
) -> Dict[str, Any]:
    """写评论（同作者重复评论则更新评分与内容）。"""
    if not author:
        return {"success": False, "error": "author_required"}
    if not 1 <= int(rating) <= 5:
        return {
            "success": False,
            "error": "invalid_rating",
            "message": "rating must be 1-5",
        }
    if not get_atom(conn, atom_id):
        return {
            "success": False,
            "error": "not_found",
            "message": f"Atom '{atom_id}' not found",
        }

    now = now_iso()
    existing = conn.execute(
        "SELECT created_at FROM atom_reviews WHERE atom_id = ? AND author = ?",
        (atom_id, author),
    ).fetchone()
    created_at = existing[0] if existing else now
    conn.execute(
        """
        INSERT INTO atom_reviews (atom_id, author, rating, text, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(atom_id, author) DO UPDATE SET
            rating=excluded.rating,
            text=excluded.text,
            updated_at=excluded.updated_at
        """,
        (atom_id, author, int(rating), text, created_at, now),
    )
    conn.commit()
    return {
        "success": True,
        "atom_id": atom_id,
        "author": author,
        "rating": int(rating),
    }


def list_reviews(conn: sqlite3.Connection, atom_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT author, rating, text, created_at, updated_at FROM atom_reviews "
        "WHERE atom_id = ? ORDER BY created_at DESC",
        (atom_id,),
    ).fetchall()
    return [
        {
            "author": r[0],
            "rating": r[1],
            "text": r[2],
            "created_at": r[3],
            "updated_at": r[4],
        }
        for r in rows
    ]


def atom_rating(conn: sqlite3.Connection, atom_id: str) -> Dict[str, Any]:
    """社区评分汇总：average / count / distribution。"""
    rows = conn.execute(
        "SELECT rating, COUNT(*) FROM atom_reviews WHERE atom_id = ? GROUP BY rating",
        (atom_id,),
    ).fetchall()
    distribution = {str(r[0]): r[1] for r in rows}
    count = sum(distribution.values())
    average = (
        round(sum(int(k) * v for k, v in distribution.items()) / count, 2)
        if count
        else 0.0
    )
    return {"average": average, "count": count, "distribution": distribution}


def _availability_score(atom: Dict[str, Any]) -> float:
    runtime = atom.get("runtime", {}) or {}
    probe_status = runtime.get("last_probe_status")
    if probe_status == "ok":
        return 5.0
    if probe_status is None:
        return 2.5  # 未探测，中性
    failures = int(runtime.get("consecutive_failures", 0) or 0)
    return max(0.0, 5.0 - failures)


def _doc_score(atom: Dict[str, Any]) -> float:
    score = 0.0
    if atom.get("description"):
        score += 2.5
    if atom.get("purpose", {}).get("examples"):
        score += 2.5
    return score


def _test_score(atom: Dict[str, Any]) -> float:
    status = atom.get("quality", {}).get("test_status", "untested")
    return {"passed": 5.0, "testing": 2.5}.get(status, 0.0)


def composite_score(conn: sqlite3.Connection, atom_id: str) -> Dict[str, Any]:
    atom = get_atom(conn, atom_id)
    if not atom:
        raise ValueError(f"Atom '{atom_id}' not found")
    community = atom_rating(conn, atom_id)
    parts = {
        "availability": _availability_score(atom),
        "documentation": _doc_score(atom),
        "community": community["average"],
        "test": _test_score(atom),
    }
    total = (
        W_AVAILABILITY * parts["availability"]
        + W_DOC * parts["documentation"]
        + W_COMMUNITY * parts["community"]
        + W_TEST * parts["test"]
    )
    # 副作用标签权重（DESIGN_ATOM_FOUNDATION_V2 §6）：pure 原子 +0.5
    purity_bonus = (
        PURE_SIDE_EFFECT_BONUS if resolve_side_effect(atom) == "pure" else 0.0
    )
    total += purity_bonus
    return {
        "atom_id": atom_id,
        "score": round(total, 2),
        "parts": parts,
        "purity_bonus": purity_bonus,
        "ratings": community,
    }


def marketplace_board(
    conn: sqlite3.Connection, tab: str = "hot", limit: int = 20
) -> List[Dict[str, Any]]:
    """市场榜单：hot（热度）/ top（高分）/ new（最新）。"""
    entries: List[Dict[str, Any]] = []
    for atom in list_atoms(conn):
        atom_id = atom["atom_id"]
        composite = composite_score(conn, atom_id)
        count = composite["ratings"]["count"]
        entries.append(
            {
                "atom_id": atom_id,
                "name": atom.get("name", ""),
                "author": atom.get("ownership", {}).get("author", ""),
                "description": atom.get("description", ""),
                "category": atom.get("classification", {}).get("category", ""),
                "status": atom.get("lifecycle", {}).get("status", ""),
                "score": composite["score"],
                "reviews": count,
                "functions": len(atom.get("purpose", {}).get("functions", []) or []),
                "hotness": round(composite["score"] * (1 + math.log1p(count)), 2),
                "created_at": atom.get("created_at", ""),
            }
        )
    if tab == "top":
        entries.sort(key=lambda e: (e["score"], e["reviews"]), reverse=True)
    elif tab == "new":
        entries.sort(key=lambda e: e["created_at"] or "", reverse=True)
    else:  # hot
        entries.sort(key=lambda e: e["hotness"], reverse=True)
    return entries[:limit]
