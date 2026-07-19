"""版本归档、列举与回滚。

由 registry.py 拆分而来（ISOLATION_HARDENING_PLAN 加固1），纯结构移动，逻辑零变化。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from .audit import _audit
from .core import _insert_or_update, get_atom
from .hashing import compute_signature
from .schema import VERSIONS_TABLE, now_iso


def _row_to_version(row: sqlite3.Row) -> Dict[str, Any]:
    version: Dict[str, Any] = {}
    for k in row.keys():
        v = row[k]
        if k.endswith("_json") and v is not None:
            version[k[:-5]] = json.loads(v)
        else:
            version[k] = v
    return version


def list_atom_versions(conn: sqlite3.Connection, atom_id: str) -> List[Dict[str, Any]]:
    """列出某原子的全部归档版本（接口契约 1.6，按创建时间 DESC）。"""
    rows = conn.execute(
        f"""SELECT version, signature_hash, content_hash, changelog,
                   purpose_json, created_at
            FROM {VERSIONS_TABLE}
            WHERE atom_id = ?
            ORDER BY created_at DESC, id DESC""",
        (atom_id,),
    ).fetchall()
    return [
        {
            "version": row[0],
            "signature": row[1],
            "content_hash": row[2],
            "changelog": row[3],
            "purpose": json.loads(row[4]) if row[4] else {},
            "created_at": row[5],
        }
        for row in rows
    ]


def get_atom_version(
    conn: sqlite3.Connection, atom_id: str, version: str
) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        f"SELECT * FROM {VERSIONS_TABLE} WHERE atom_id = ? AND version = ?",
        (atom_id, version),
    ).fetchone()
    if not row:
        return None
    return _row_to_version(row)


def rollback_atom(
    conn: sqlite3.Connection, atom_id: str, version: str, actor: str = "system"
) -> Dict[str, Any]:
    """把注册表中的原子回滚到某个归档版本的内容。

    当前 lifecycle 状态保留（registered/running 等不变），只替换内容与
    version 字段；回滚本身记一条审计日志。归档版本记录不受影响。
    """
    snapshot = get_atom_version(conn, atom_id, version)
    if not snapshot:
        return {
            "success": False,
            "error": "version_not_found",
            "message": f"Version '{version}' of atom '{atom_id}' not found",
        }
    current = get_atom(conn, atom_id)
    if not current:
        return {
            "success": False,
            "error": "not_found",
            "message": f"Atom '{atom_id}' not found",
        }

    old_version = current.get("version")
    lifecycle = current.get("lifecycle", {})
    lifecycle["updated_at"] = now_iso()

    atom = {
        "atom_id": atom_id,
        "name": snapshot.get("name", ""),
        "version": snapshot.get("version", version),
        "description": snapshot.get("description", ""),
        "purpose": snapshot.get("purpose", {}),
        "architecture": snapshot.get("architecture", {}),
        "ownership": snapshot.get("ownership", {}),
        "classification": snapshot.get("classification", {}),
        "compliance": snapshot.get("compliance", {}),
        "quality": snapshot.get("quality", {}),
        "runtime": snapshot.get("runtime", {}),
        "lifecycle": lifecycle,
        "alias": current.get("alias", []),
    }
    signature = snapshot.get("signature_hash") or compute_signature(atom)
    _insert_or_update(conn, atom, signature, actor)
    _audit(
        conn,
        atom_id,
        "rollback",
        old_version,
        version,
        actor,
        f"rolled back from {old_version} to {version}",
    )
    return {"success": True, "atom_id": atom_id, "version": version}
