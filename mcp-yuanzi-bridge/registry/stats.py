"""统计、导出、审计查询与历史哈希回填。

由 registry.py 拆分而来（ISOLATION_HARDENING_PLAN 加固1），纯结构移动，逻辑零变化。
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from .core import get_atom, list_atoms
from .hashing import compute_content_hash, compute_identity_hash
from .schema import AUDIT_TABLE, REGISTRY_TABLE, now_iso


def get_audit_log(
    conn: sqlite3.Connection, atom_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    query = f"SELECT * FROM {AUDIT_TABLE}"
    params: List[Any] = []
    if atom_id:
        query += " WHERE atom_id = ?"
        params.append(atom_id)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def backfill_content_hashes(conn: sqlite3.Connection) -> int:
    """回填历史行的 content_hash / identity_hash（迁移 005 之后执行）。

    返回回填的行数。"""
    rows = conn.execute(
        f"SELECT atom_id FROM {REGISTRY_TABLE} "
        "WHERE content_hash IS NULL OR content_hash = ''"
    ).fetchall()
    for row in rows:
        atom = get_atom(conn, row[0])
        if not atom:
            continue
        conn.execute(
            f"UPDATE {REGISTRY_TABLE} SET content_hash = ?, identity_hash = ? WHERE atom_id = ?",
            (compute_content_hash(atom), compute_identity_hash(atom), row[0]),
        )
    conn.commit()
    return len(rows)


def compute_registry_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    total = conn.execute(f"SELECT COUNT(*) FROM {REGISTRY_TABLE}").fetchone()[0]
    status_counts = {}
    for row in conn.execute(
        f"SELECT json_extract(lifecycle_json, '$.status') AS s, COUNT(*) FROM {REGISTRY_TABLE} GROUP BY s"
    ).fetchall():
        status_counts[row[0] or "unknown"] = row[1]

    category_counts = {}
    for row in conn.execute(
        f"SELECT json_extract(classification_json, '$.category') AS c, COUNT(*) FROM {REGISTRY_TABLE} GROUP BY c"
    ).fetchall():
        category_counts[row[0] or "uncategorized"] = row[1]

    return {
        "total_atoms": total,
        "status_counts": status_counts,
        "category_counts": category_counts,
        "generated_at": now_iso(),
    }


def dump_registry(
    conn: sqlite3.Connection, include_audit: bool = False
) -> Dict[str, Any]:
    from migrations import current_version

    return {
        "schema_version": str(current_version(conn)),
        "generated_at": now_iso(),
        "stats": compute_registry_stats(conn),
        "atoms": list_atoms(conn),
        "audit_log": get_audit_log(conn) if include_audit else [],
    }
