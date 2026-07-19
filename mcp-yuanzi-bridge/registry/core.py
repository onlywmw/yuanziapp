"""注册中心核心：提交、审核、状态流转、查询与行转换。

由 registry.py 拆分而来（ISOLATION_HARDENING_PLAN 加固1），纯结构移动，逻辑零变化。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from .audit import _audit
from .hashing import compute_content_hash, compute_identity_hash, compute_signature
from .schema import REGISTRY_TABLE, RESERVED_PREFIXES, VERSIONS_TABLE, now_iso


def _insert_or_update(
    conn: sqlite3.Connection, atom: Dict[str, Any], signature: str, actor: str
) -> Dict[str, Any]:
    now = now_iso()
    lifecycle = atom.get("lifecycle", {})
    if "submitted_at" not in lifecycle:
        lifecycle["submitted_at"] = now
    if "created_at" not in lifecycle:
        lifecycle["created_at"] = now
    if "updated_at" not in lifecycle:
        lifecycle["updated_at"] = now

    ownership = atom.get("ownership", {})
    classification = atom.get("classification", {})
    compliance = atom.get("compliance", {})
    quality = atom.get("quality", {})
    runtime = atom.get("runtime", {})
    alias = atom.get("alias", [])

    signature_info = atom.get("signature", {})
    conn.execute(
        f"""
        INSERT INTO {REGISTRY_TABLE}
        (atom_id, name, version, description, purpose_json, architecture_json,
         ownership_json, classification_json, compliance_json, quality_json,
         runtime_json, lifecycle_json, signature_hash, signature_algorithm,
         content_hash, identity_hash, alias,
         created_at, submitted_at, registered_at, updated_at, version_counter)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(atom_id) DO UPDATE SET
            name=excluded.name,
            version=excluded.version,
            description=excluded.description,
            purpose_json=excluded.purpose_json,
            architecture_json=excluded.architecture_json,
            ownership_json=excluded.ownership_json,
            classification_json=excluded.classification_json,
            compliance_json=excluded.compliance_json,
            quality_json=excluded.quality_json,
            runtime_json=excluded.runtime_json,
            lifecycle_json=excluded.lifecycle_json,
            signature_hash=excluded.signature_hash,
            content_hash=excluded.content_hash,
            identity_hash=excluded.identity_hash,
            alias=excluded.alias,
            updated_at=excluded.updated_at,
            version_counter=atom_registry.version_counter + 1
        """,
        (
            atom["atom_id"],
            atom.get("name", ""),
            atom.get("version", "1.0.0"),
            atom.get("description", ""),
            json.dumps(atom.get("purpose", {}), ensure_ascii=False),
            json.dumps(atom.get("architecture", {}), ensure_ascii=False),
            json.dumps(ownership, ensure_ascii=False),
            json.dumps(classification, ensure_ascii=False),
            json.dumps(compliance, ensure_ascii=False),
            json.dumps(quality, ensure_ascii=False),
            json.dumps(runtime, ensure_ascii=False),
            json.dumps(lifecycle, ensure_ascii=False),
            signature,
            "sha256",
            signature_info.get("content_hash", ""),
            signature_info.get("identity_hash", ""),
            json.dumps(alias, ensure_ascii=False),
            lifecycle.get("created_at"),
            lifecycle.get("submitted_at"),
            lifecycle.get("registered_at"),
            lifecycle.get("updated_at"),
        ),
    )
    conn.commit()
    return {
        "atom_id": atom["atom_id"],
        "signature": signature,
        "status": lifecycle.get("status", "submitted"),
    }


def _archive_version(
    conn: sqlite3.Connection, atom: Dict[str, Any], signature: str
) -> None:
    """把本次提交的内容快照归档到 atom_versions（同版本重复提交则更新）。"""
    now = now_iso()
    signature_info = atom.get("signature", {})
    existing = conn.execute(
        f"SELECT created_at FROM {VERSIONS_TABLE} WHERE atom_id = ? AND version = ?",
        (atom["atom_id"], atom.get("version", "1.0.0")),
    ).fetchone()
    created_at = existing[0] if existing else now
    conn.execute(
        f"""
        INSERT INTO {VERSIONS_TABLE}
        (atom_id, version, name, description, purpose_json, architecture_json,
         ownership_json, classification_json, compliance_json, quality_json,
         runtime_json, signature_hash, content_hash, identity_hash, changelog,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(atom_id, version) DO UPDATE SET
            name=excluded.name,
            description=excluded.description,
            purpose_json=excluded.purpose_json,
            architecture_json=excluded.architecture_json,
            ownership_json=excluded.ownership_json,
            classification_json=excluded.classification_json,
            compliance_json=excluded.compliance_json,
            quality_json=excluded.quality_json,
            runtime_json=excluded.runtime_json,
            signature_hash=excluded.signature_hash,
            content_hash=excluded.content_hash,
            identity_hash=excluded.identity_hash,
            changelog=excluded.changelog,
            updated_at=excluded.updated_at
        """,
        (
            atom["atom_id"],
            atom.get("version", "1.0.0"),
            atom.get("name", ""),
            atom.get("description", ""),
            json.dumps(atom.get("purpose", {}), ensure_ascii=False),
            json.dumps(atom.get("architecture", {}), ensure_ascii=False),
            json.dumps(atom.get("ownership", {}), ensure_ascii=False),
            json.dumps(atom.get("classification", {}), ensure_ascii=False),
            json.dumps(atom.get("compliance", {}), ensure_ascii=False),
            json.dumps(atom.get("quality", {}), ensure_ascii=False),
            json.dumps(atom.get("runtime", {}), ensure_ascii=False),
            signature,
            signature_info.get("content_hash", ""),
            signature_info.get("identity_hash", ""),
            atom.get("changelog", ""),
            created_at,
            now,
        ),
    )
    conn.commit()


def submit_atom(
    conn: sqlite3.Connection, atom: Dict[str, Any], actor: str = "system"
) -> Dict[str, Any]:
    """提交一个新原子进入审核队列。"""
    atom_id = atom.get("atom_id", "")
    if not atom_id:
        raise ValueError("atom_id is required")

    # 保护内置命名空间（ISOLATION_HARDENING_PLAN 加固4）
    for prefix in RESERVED_PREFIXES:
        if atom_id.startswith(prefix):
            return {
                "success": False,
                "error": "reserved_namespace",
                "message": f"'{prefix}*' is reserved for built-in atoms",
            }

    signature = atom.get("signature", {}).get("hash") or compute_signature(atom)
    content_hash = compute_content_hash(atom)
    identity_hash = compute_identity_hash(atom)

    # 检查同 signature 是否被其他 atom_id 占用
    row = conn.execute(
        f"SELECT atom_id FROM {REGISTRY_TABLE} WHERE signature_hash = ?", (signature,)
    ).fetchone()
    if row and row[0] != atom_id:
        return {
            "success": False,
            "error": "duplicate_signature",
            "message": f"Signature already registered by atom '{row[0]}'; cannot register '{atom_id}'",
        }

    # BUG-006/016：能力级去重——content_hash 相同但 atom_id 不同，
    # 说明是换皮重复注册，拒绝。
    row = conn.execute(
        f"SELECT atom_id FROM {REGISTRY_TABLE} WHERE content_hash = ?",
        (content_hash,),
    ).fetchone()
    if row and row[0] != atom_id:
        return {
            "success": False,
            "error": "duplicate_signature",
            "message": (
                f"Identical capabilities already registered by atom "
                f"'{row[0]}'; cannot register '{atom_id}'"
            ),
        }

    lifecycle = atom.get("lifecycle", {})
    old_status = None
    existing = conn.execute(
        f"SELECT lifecycle_json FROM {REGISTRY_TABLE} WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if existing:
        old_status = json.loads(existing[0]).get("status")

    lifecycle["status"] = "submitted"
    atom["lifecycle"] = lifecycle
    if "signature" not in atom:
        atom["signature"] = {}
    atom["signature"]["hash"] = signature
    atom["signature"]["algorithm"] = "sha256"
    atom["signature"]["source"] = "auto-computed"
    atom["signature"]["content_hash"] = content_hash
    atom["signature"]["identity_hash"] = identity_hash

    result = _insert_or_update(conn, atom, signature, actor)
    _archive_version(conn, atom, signature)
    _audit(
        conn,
        atom_id,
        "submit",
        old_status,
        "submitted",
        actor,
        f"signature={signature}",
    )
    result["success"] = True
    return result


def review_atom(
    conn: sqlite3.Connection,
    atom_id: str,
    approved: bool,
    reviewer: str = "system",
    comments: str = "",
    score: Optional[float] = None,
) -> Dict[str, Any]:
    """审核原子，通过后进入 registered 状态，拒绝进入 rejected 状态。"""
    row = conn.execute(
        f"SELECT lifecycle_json FROM {REGISTRY_TABLE} WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if not row:
        return {
            "success": False,
            "error": "not_found",
            "message": f"Atom '{atom_id}' not found",
        }

    lifecycle = json.loads(row[0])
    old_status = lifecycle.get("status")

    if approved:
        lifecycle["status"] = "registered"
        lifecycle["registered_at"] = now_iso()
        lifecycle["review_result"] = {
            "reviewer": reviewer,
            "reviewed_at": now_iso(),
            "comments": comments,
            "score": score,
        }
    else:
        lifecycle["status"] = "rejected"
        lifecycle["review_result"] = {
            "reviewer": reviewer,
            "reviewed_at": now_iso(),
            "comments": comments,
            "score": score,
        }

    lifecycle["updated_at"] = now_iso()
    conn.execute(
        f"UPDATE {REGISTRY_TABLE} SET lifecycle_json = ?, reviewed_at = ?, reviewed_by = ?, review_comments = ?, review_score = ? WHERE atom_id = ?",
        (
            json.dumps(lifecycle, ensure_ascii=False),
            lifecycle["review_result"]["reviewed_at"],
            reviewer,
            comments,
            score,
            atom_id,
        ),
    )
    conn.commit()
    _audit(conn, atom_id, "review", old_status, lifecycle["status"], reviewer, comments)
    return {"success": True, "atom_id": atom_id, "status": lifecycle["status"]}


# 统一的状态流转表：set_atom_status 与 probe_atom 的唯一事实来源（BUG-019）
ALLOWED_TRANSITIONS = {
    "registered": ["probing", "running", "unreachable", "offline", "deprecated"],
    "probing": ["running", "unreachable", "offline", "deprecated"],
    "running": ["probing", "unreachable", "offline", "deprecated", "registered"],
    "unreachable": ["probing", "running", "offline", "deprecated"],
    "offline": ["probing", "running", "unreachable", "deprecated", "registered"],
    "deprecated": ["registered"],
}


def _transition_allowed(old_status: Optional[str], new_status: str) -> bool:
    return new_status in ALLOWED_TRANSITIONS.get(old_status or "", [])


def set_atom_status(
    conn: sqlite3.Connection,
    atom_id: str,
    status: str,
    actor: str = "system",
    detail: str = "",
) -> Dict[str, Any]:
    """在注册后变更原子运行状态：running / offline / deprecated。"""
    row = conn.execute(
        f"SELECT lifecycle_json FROM {REGISTRY_TABLE} WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if not row:
        return {
            "success": False,
            "error": "not_found",
            "message": f"Atom '{atom_id}' not found",
        }

    lifecycle = json.loads(row[0])
    old_status = lifecycle.get("status")
    if not _transition_allowed(old_status, status):
        return {
            "success": False,
            "error": "invalid_transition",
            "message": f"Cannot transition from '{old_status}' to '{status}'",
        }

    lifecycle["status"] = status
    lifecycle["updated_at"] = now_iso()
    conn.execute(
        f"UPDATE {REGISTRY_TABLE} SET lifecycle_json = ?, "
        "version_counter = version_counter + 1 WHERE atom_id = ?",
        (json.dumps(lifecycle, ensure_ascii=False), atom_id),
    )
    conn.commit()
    _audit(conn, atom_id, "status_change", old_status, status, actor, detail)
    return {
        "success": True,
        "atom_id": atom_id,
        "old_status": old_status,
        "new_status": status,
    }


def get_atom(conn: sqlite3.Connection, atom_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        f"SELECT * FROM {REGISTRY_TABLE} WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_atom(row)


def list_atoms(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    query = f"SELECT * FROM {REGISTRY_TABLE} WHERE 1=1"
    params: List[Any] = []
    if status:
        query += " AND json_extract(lifecycle_json, '$.status') = ?"
        params.append(status)
    if category:
        query += " AND json_extract(classification_json, '$.category') = ?"
        params.append(category)
    if search:
        query += " AND (atom_id LIKE ? OR name LIKE ? OR alias LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    query += " ORDER BY atom_id"
    rows = conn.execute(query, params).fetchall()
    return [_row_to_atom(row) for row in rows]


def _row_to_atom(row: sqlite3.Row) -> Dict[str, Any]:
    keys = [k for k in row.keys()]
    atom: Dict[str, Any] = {}
    for k in keys:
        v = row[k]
        if k.endswith("_json") and v is not None:
            atom[k[:-5]] = json.loads(v)
        elif k == "alias" and v is not None:
            atom[k] = json.loads(v)
        else:
            atom[k] = v
    return atom
