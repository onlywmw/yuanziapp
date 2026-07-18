#!/usr/bin/env python3
"""Atom Registry v2

提供原子的提交、审核、注册、去重、状态流转、审计日志等功能。
注册信息必须满足 atom-registry-schema.json 定义的完整字段。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REGISTRY_TABLE = "atom_registry"
AUDIT_TABLE = "atom_audit_log"


@dataclass
class AtomRegistration:
    atom_id: str
    name: str
    version: str
    description: str
    purpose: Dict[str, Any]
    architecture: Dict[str, Any]
    ownership: Dict[str, Any]
    signature: Dict[str, str]
    lifecycle: Dict[str, Any] = field(default_factory=dict)
    classification: Dict[str, Any] = field(default_factory=dict)
    compliance: Dict[str, Any] = field(default_factory=dict)
    quality: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    alias: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_signature(atom: Dict[str, Any]) -> str:
    """基于核心身份与能力计算去重指纹。

    指纹包含：
    - atom_id
    - 提供的功能名称集合
    - 原子架构类型与运行时
    - 依赖的原子集合
    - 接口规范
    """
    purpose = atom.get("purpose", {})
    functions = sorted(
        {f.get("name", "") for f in purpose.get("functions", []) if f.get("name")}
    )
    arch = atom.get("architecture", {})
    deps = sorted(set(arch.get("dependencies", [])))

    sig_payload = {
        "atom_id": atom.get("atom_id", ""),
        "functions": functions,
        "type": arch.get("type", ""),
        "runtime": arch.get("runtime", ""),
        "interface": arch.get("interface", ""),
        "dependencies": deps,
    }
    raw = _canonical_json(sig_payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def ensure_registry_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {REGISTRY_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atom_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '1.0.0',
            description TEXT,
            purpose_json TEXT NOT NULL,
            architecture_json TEXT NOT NULL,
            ownership_json TEXT NOT NULL,
            classification_json TEXT,
            compliance_json TEXT,
            quality_json TEXT,
            runtime_json TEXT,
            lifecycle_json TEXT NOT NULL,
            signature_hash TEXT UNIQUE NOT NULL,
            signature_algorithm TEXT NOT NULL DEFAULT 'sha256',
            alias TEXT,
            created_at TEXT,
            submitted_at TEXT,
            registered_at TEXT,
            updated_at TEXT,
            reviewed_at TEXT,
            reviewed_by TEXT,
            review_comments TEXT,
            review_score REAL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atom_id TEXT NOT NULL,
            action TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT,
            actor TEXT,
            detail TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()


def _audit(
    conn: sqlite3.Connection,
    atom_id: str,
    action: str,
    old_status: Optional[str],
    new_status: Optional[str],
    actor: str,
    detail: str = "",
) -> None:
    conn.execute(
        f"""
        INSERT INTO {AUDIT_TABLE}
        (atom_id, action, old_status, new_status, actor, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (atom_id, action, old_status, new_status, actor, detail, now_iso()),
    )
    conn.commit()


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

    conn.execute(
        f"""
        INSERT INTO {REGISTRY_TABLE}
        (atom_id, name, version, description, purpose_json, architecture_json,
         ownership_json, classification_json, compliance_json, quality_json,
         runtime_json, lifecycle_json, signature_hash, signature_algorithm, alias,
         created_at, submitted_at, registered_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            alias=excluded.alias,
            updated_at=excluded.updated_at
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


def submit_atom(
    conn: sqlite3.Connection, atom: Dict[str, Any], actor: str = "system"
) -> Dict[str, Any]:
    """提交一个新原子进入审核队列。"""
    atom_id = atom.get("atom_id", "")
    if not atom_id:
        raise ValueError("atom_id is required")

    signature = atom.get("signature", {}).get("hash") or compute_signature(atom)

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

    result = _insert_or_update(conn, atom, signature, actor)
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


def set_atom_status(
    conn: sqlite3.Connection,
    atom_id: str,
    status: str,
    actor: str = "system",
    detail: str = "",
) -> Dict[str, Any]:
    """在注册后变更原子运行状态：running / offline / deprecated。"""
    allowed_transitions = {
        "registered": ["running", "offline", "deprecated"],
        "running": ["offline", "deprecated", "registered"],
        "offline": ["running", "deprecated", "registered"],
        "deprecated": ["registered"],
    }
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
    if status not in allowed_transitions.get(old_status, []):
        return {
            "success": False,
            "error": "invalid_transition",
            "message": f"Cannot transition from '{old_status}' to '{status}'",
        }

    lifecycle["status"] = status
    lifecycle["updated_at"] = now_iso()
    conn.execute(
        f"UPDATE {REGISTRY_TABLE} SET lifecycle_json = ? WHERE atom_id = ?",
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
    return {
        "schema_version": "2.0",
        "generated_at": now_iso(),
        "stats": compute_registry_stats(conn),
        "atoms": list_atoms(conn),
        "audit_log": get_audit_log(conn) if include_audit else [],
    }


if __name__ == "__main__":
    db_path = Path(__file__).with_name("registry.db")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_registry_schema(conn)
    print(f"Registry initialized at {db_path}")
    print("Stats:", compute_registry_stats(conn))
