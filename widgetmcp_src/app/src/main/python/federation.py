#!/usr/bin/env python3
"""联邦注册中心（M7 任务 7.4）。

共享模型（DESIGN_M7 §5.2）：
- 只共享原子元数据（atom_id/name/author/purpose/signature），不共享 runtime
- trust_level: trusted（自动注册+审核通过）/ review（注册为 submitted 待审）/
  unknown（拒绝同步）
"""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from registry import get_atom, list_atoms, now_iso, review_atom, submit_atom

TRUST_TRUSTED = "trusted"
TRUST_REVIEW = "review"
TRUST_UNKNOWN = "unknown"
TRUST_LEVELS = {TRUST_TRUSTED, TRUST_REVIEW, TRUST_UNKNOWN}


def add_peer(
    conn: sqlite3.Connection,
    name: str,
    base_url: str,
    trust_level: str = TRUST_REVIEW,
) -> Dict[str, Any]:
    if trust_level not in TRUST_LEVELS:
        return {"success": False, "error": "invalid_trust_level"}
    if not base_url.startswith(("http://", "https://")):
        return {"success": False, "error": "invalid_base_url"}
    conn.execute(
        "INSERT INTO federation_peers (name, base_url, trust_level, added_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(base_url) DO UPDATE SET name=excluded.name, trust_level=excluded.trust_level",
        (name, base_url.rstrip("/"), trust_level, now_iso()),
    )
    conn.commit()
    peer_id = conn.execute(
        "SELECT id FROM federation_peers WHERE base_url = ?", (base_url.rstrip("/"),)
    ).fetchone()[0]
    return {"success": True, "id": peer_id, "base_url": base_url.rstrip("/")}


def list_peers(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, base_url, trust_level, added_at, last_synced_at "
        "FROM federation_peers ORDER BY id"
    ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "base_url": r[2],
            "trust_level": r[3],
            "added_at": r[4],
            "last_synced_at": r[5],
        }
        for r in rows
    ]


def remove_peer(conn: sqlite3.Connection, peer_id: int) -> bool:
    cursor = conn.execute("DELETE FROM federation_peers WHERE id = ?", (peer_id,))
    conn.commit()
    return cursor.rowcount > 0


def export_atoms(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """可共享的原子元数据（不含 runtime/endpoint——那是本地概念）。"""
    shared: List[Dict[str, Any]] = []
    for atom in list_atoms(conn):
        shared.append(
            {
                "atom_id": atom["atom_id"],
                "name": atom.get("name", ""),
                "version": atom.get("version", "1.0.0"),
                "description": atom.get("description", ""),
                "purpose": atom.get("purpose", {}),
                "architecture": atom.get("architecture", {}),
                "ownership": atom.get("ownership", {}),
                "classification": atom.get("classification", {}),
                "signature_hash": atom.get("signature_hash", ""),
                "content_hash": atom.get("content_hash", ""),
            }
        )
    return shared


def _default_http_get(url: str, timeout: float = 10.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sync_peer(
    conn: sqlite3.Connection,
    peer_id: int,
    http_get: Optional[Callable] = None,
) -> Dict[str, Any]:
    """从对等节点拉取共享原子并注册到本地。

    trusted → 注册并直接审核通过；review → 注册为 submitted 待人工审核；
    unknown → 拒绝同步。"""
    row = conn.execute(
        "SELECT base_url, trust_level FROM federation_peers WHERE id = ?", (peer_id,)
    ).fetchone()
    if not row:
        return {"success": False, "error": "peer_not_found"}
    base_url, trust_level = row
    if trust_level == TRUST_UNKNOWN:
        return {"success": False, "error": "untrusted_peer"}

    fetch = http_get or _default_http_get
    try:
        payload = fetch(f"{base_url}/federation/export")
    except Exception as exc:  # noqa: BLE001 - 网络失败统一返回同步失败
        return {"success": False, "error": "fetch_failed", "message": str(exc)}

    remote_atoms = (
        payload.get("atoms", payload) if isinstance(payload, dict) else payload
    )
    imported = 0
    skipped = 0
    for remote in remote_atoms:
        atom_id = remote.get("atom_id", "")
        if not atom_id:
            continue
        if get_atom(conn, atom_id):
            skipped += 1
            continue
        atom = {
            "atom_id": atom_id,
            "name": remote.get("name", ""),
            "version": remote.get("version", "1.0.0"),
            "description": remote.get("description", ""),
            "purpose": remote.get("purpose", {}),
            "architecture": remote.get("architecture", {}),
            "ownership": remote.get("ownership", {}),
            "classification": remote.get("classification", {}),
            "lifecycle": {"status": "submitted"},
        }
        result = submit_atom(conn, atom, actor=f"federation:{base_url}")
        if not result.get("success"):
            skipped += 1  # 能力重复（duplicate_signature）等
            continue
        if trust_level == TRUST_TRUSTED:
            review_atom(
                conn,
                atom_id,
                approved=True,
                reviewer=f"federation:{base_url}",
                comments="auto-approved from trusted peer",
            )
        imported += 1

    conn.execute(
        "UPDATE federation_peers SET last_synced_at = ? WHERE id = ?",
        (now_iso(), peer_id),
    )
    conn.commit()
    return {
        "success": True,
        "peer_id": peer_id,
        "trust_level": trust_level,
        "imported": imported,
        "skipped": skipped,
    }
