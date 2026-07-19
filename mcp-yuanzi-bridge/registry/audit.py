"""审计日志写入与 M6.4 哈希链校验/回填。

由 registry.py 拆分而来（ISOLATION_HARDENING_PLAN 加固1），纯结构移动，逻辑零变化。
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any, Dict, Optional

from .hashing import _canonical_json
from .schema import AUDIT_TABLE, now_iso


def _compute_chain_hash(prev_chain_hash: str, row: Dict[str, Any]) -> str:
    """SHA-256(prev_chain_hash + 本行内容的规范化 JSON)（M6.4 审计哈希链）。"""
    payload = prev_chain_hash + _canonical_json(row)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _audit(
    conn: sqlite3.Connection,
    atom_id: str,
    action: str,
    old_status: Optional[str],
    new_status: Optional[str],
    actor: str,
    detail: str = "",
) -> None:
    created_at = now_iso()
    row = {
        "atom_id": atom_id,
        "action": action,
        "old_status": old_status,
        "new_status": new_status,
        "actor": actor,
        "detail": detail,
        "created_at": created_at,
    }
    prev = conn.execute(
        f"SELECT chain_hash FROM {AUDIT_TABLE} ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = prev[0] if prev and prev[0] else ""
    chain_hash = _compute_chain_hash(prev_hash, row)
    conn.execute(
        f"""
        INSERT INTO {AUDIT_TABLE}
        (atom_id, action, old_status, new_status, actor, detail, created_at, chain_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            atom_id,
            action,
            old_status,
            new_status,
            actor,
            detail,
            created_at,
            chain_hash,
        ),
    )
    conn.commit()


def verify_audit_chain(conn: sqlite3.Connection) -> Dict[str, Any]:
    """重算审计哈希链，检测篡改（M6.4）。

    返回 {"valid": bool, "total_rows": int, "legacy_rows": int,
          "broken_at_row": int|None, "verified_at": str}
    legacy_rows = 迁移前没有 chain_hash 的旧行，不参与校验。"""
    rows = conn.execute(
        f"SELECT id, atom_id, action, old_status, new_status, actor, detail, created_at, chain_hash "
        f"FROM {AUDIT_TABLE} ORDER BY id"
    ).fetchall()
    prev_hash = ""
    legacy = 0
    for row in rows:
        (
            row_id,
            atom_id,
            action,
            old_status,
            new_status,
            actor,
            detail,
            created_at,
            chain_hash,
        ) = row
        if not chain_hash:
            legacy += 1
            continue
        expected = _compute_chain_hash(
            prev_hash,
            {
                "atom_id": atom_id,
                "action": action,
                "old_status": old_status,
                "new_status": new_status,
                "actor": actor,
                "detail": detail,
                "created_at": created_at,
            },
        )
        if expected != chain_hash:
            return {
                "valid": False,
                "total_rows": len(rows),
                "legacy_rows": legacy,
                "broken_at_row": row_id,
                "expected": expected,
                "actual": chain_hash,
                "verified_at": now_iso(),
            }
        prev_hash = chain_hash
    return {
        "valid": True,
        "total_rows": len(rows),
        "legacy_rows": legacy,
        "broken_at_row": None,
        "verified_at": now_iso(),
    }


def backfill_audit_chain(conn: sqlite3.Connection) -> int:
    """为迁移前的旧审计行补算 chain_hash（按 id 顺序重链）。返回回填行数。"""
    rows = conn.execute(
        f"SELECT id, atom_id, action, old_status, new_status, actor, detail, created_at "
        f"FROM {AUDIT_TABLE} WHERE chain_hash IS NULL OR chain_hash = '' ORDER BY id"
    ).fetchall()
    prev = conn.execute(
        f"SELECT chain_hash FROM {AUDIT_TABLE} "
        "WHERE chain_hash IS NOT NULL AND chain_hash != '' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = prev[0] if prev else ""
    for row in rows:
        row_id, atom_id, action, old_status, new_status, actor, detail, created_at = row
        chain_hash = _compute_chain_hash(
            prev_hash,
            {
                "atom_id": atom_id,
                "action": action,
                "old_status": old_status,
                "new_status": new_status,
                "actor": actor,
                "detail": detail,
                "created_at": created_at,
            },
        )
        conn.execute(
            f"UPDATE {AUDIT_TABLE} SET chain_hash = ? WHERE id = ?",
            (chain_hash, row_id),
        )
        prev_hash = chain_hash
    conn.commit()
    return len(rows)
