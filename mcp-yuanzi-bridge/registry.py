#!/usr/bin/env python3
"""Atom Registry v2

提供原子的提交、审核、注册、去重、状态流转、审计日志等功能。
注册信息必须满足 atom-registry-schema.json 定义的完整字段。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REGISTRY_TABLE = "atom_registry"
AUDIT_TABLE = "atom_audit_log"
VERSIONS_TABLE = "atom_versions"


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


def _function_fingerprints(purpose: Dict[str, Any]) -> List[Dict[str, Any]]:
    """功能的稳定指纹：名称 + 输入/输出 schema（如有）。"""
    fingerprints = []
    for f in purpose.get("functions", []):
        name = f.get("name")
        if not name:
            continue
        fingerprints.append(
            {
                "name": name,
                "input": f.get("input") or f.get("input_schema") or {},
                "output": f.get("output") or f.get("output_schema") or {},
            }
        )
    return sorted(fingerprints, key=lambda x: x["name"])


def compute_content_hash(atom: Dict[str, Any]) -> str:
    """能力指纹：功能（含 input/output schema）、架构、依赖、接口。

    不含任何身份字段，能力完全相同的原子会得到相同的 content_hash，
    可用于跨 atom_id 的重复能力检测。
    """
    arch = atom.get("architecture", {})
    payload = {
        "functions": _function_fingerprints(atom.get("purpose", {})),
        "type": arch.get("type", ""),
        "runtime": arch.get("runtime", ""),
        "interface": arch.get("interface", ""),
        "dependencies": sorted(set(arch.get("dependencies", []))),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def compute_identity_hash(atom: Dict[str, Any]) -> str:
    """身份指纹：atom_id、版本、归属。"""
    ownership = atom.get("ownership", {})
    payload = {
        "atom_id": atom.get("atom_id", ""),
        "version": atom.get("version", ""),
        "author": ownership.get("author", ""),
        "license": ownership.get("license", ""),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def compute_signature(atom: Dict[str, Any]) -> str:
    """完整签名（去重主键）：content_hash + identity_hash 的组合。

    返回完整的 sha256 hex（64 字符）；展示时截取前 16 位即可。
    能力指纹和身份指纹可分别通过 compute_content_hash /
    compute_identity_hash 获取。
    """
    content = compute_content_hash(atom)
    identity = compute_identity_hash(atom)
    raw = _canonical_json({"content": content, "identity": identity})
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_registry_schema(conn: sqlite3.Connection) -> None:
    conn.execute(f"""
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
            content_hash TEXT,
            identity_hash TEXT,
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
        """)
    conn.execute(f"""
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
        """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {VERSIONS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atom_id TEXT NOT NULL,
            version TEXT NOT NULL,
            name TEXT,
            description TEXT,
            purpose_json TEXT,
            architecture_json TEXT,
            ownership_json TEXT,
            classification_json TEXT,
            compliance_json TEXT,
            quality_json TEXT,
            runtime_json TEXT,
            signature_hash TEXT,
            content_hash TEXT,
            identity_hash TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (atom_id, version)
        )
        """)
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

    signature_info = atom.get("signature", {})
    conn.execute(
        f"""
        INSERT INTO {REGISTRY_TABLE}
        (atom_id, name, version, description, purpose_json, architecture_json,
         ownership_json, classification_json, compliance_json, quality_json,
         runtime_json, lifecycle_json, signature_hash, signature_algorithm,
         content_hash, identity_hash, alias,
         created_at, submitted_at, registered_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
         runtime_json, signature_hash, content_hash, identity_hash,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "error": "duplicate_content",
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


# 探测后允许变更生命周期的状态；deprecated / rejected 只记录探测结果，不改状态
_PROBEABLE_STATUSES = {"registered", "probing", "running", "unreachable", "offline"}

# 只允许探测 http/https（BUG-014/020）：注册数据不可信，其他 scheme
# （file:// 等）既不合法也会让 urllib 返回非 HTTP 响应导致崩溃。
_ALLOWED_PROBE_SCHEMES = {"http", "https"}


def probe_atom(
    conn: sqlite3.Connection,
    atom_id: str,
    timeout: float = 2.0,
    actor: str = "probe",
) -> Dict[str, Any]:
    """真实请求原子的 health_url（缺省用 endpoint），按结果更新状态。

    - 2xx            -> running
    - 其他 HTTP 码   -> unreachable（有进程监听但不健康）
    - 连接错误/超时  -> unreachable
    - 非 http/https  -> invalid_url（不发请求，不改生命周期）

    探测结果写入 runtime_json（last_probe_at / last_probe_status /
    last_probe_latency_ms / consecutive_failures）。
    审计节流（BUG-022）：只有生命周期变化或探测结果类别变化时才记审计。
    探测前先把状态置为 probing（两阶段写入，进程崩溃可识别，BUG-017）。
    """
    atom = get_atom(conn, atom_id)
    if not atom:
        # 原子不存在，没有可依附审计的对象，直接返回
        return {
            "success": False,
            "error": "not_found",
            "message": f"Atom '{atom_id}' not found",
        }

    runtime = atom.get("runtime") or {}
    lifecycle = atom.get("lifecycle", {})
    old_status = lifecycle.get("status")

    def _persist(
        probe_status: str,
        ok: Optional[bool],
        latency_ms: Optional[float] = None,
        detail: str = "",
    ) -> str:
        prev_probe_status = runtime.get("last_probe_status")
        runtime["last_probe_at"] = now_iso()
        runtime["last_probe_status"] = probe_status
        if latency_ms is not None:
            runtime["last_probe_latency_ms"] = latency_ms

        new_status = old_status
        if ok is not None:
            runtime["consecutive_failures"] = (
                0 if ok else int(runtime.get("consecutive_failures", 0)) + 1
            )
            if old_status in _PROBEABLE_STATUSES:
                target = "running" if ok else "unreachable"
                if target == old_status or _transition_allowed(old_status, target):
                    new_status = target
        # 始终写回计算结果：结果不变时把两阶段的 probing 标记还原（BUG-017）
        lifecycle["status"] = new_status
        lifecycle["updated_at"] = now_iso()

        conn.execute(
            f"UPDATE {REGISTRY_TABLE} SET runtime_json = ?, lifecycle_json = ?, updated_at = ? WHERE atom_id = ?",
            (
                json.dumps(runtime, ensure_ascii=False),
                json.dumps(lifecycle, ensure_ascii=False),
                now_iso(),
                atom_id,
            ),
        )
        conn.commit()

        if new_status != old_status or probe_status != prev_probe_status:
            parts = [probe_status]
            if latency_ms is not None:
                parts.append(f"{latency_ms}ms")
            if detail:
                parts.append(detail)
            _audit(
                conn, atom_id, "probe", old_status, new_status, actor, " ".join(parts)
            )
        return new_status

    url = runtime.get("health_url") or runtime.get("endpoint")
    if not url:
        # BUG-018：无端点也要留下探测痕迹与审计
        new_status = _persist("no_endpoint", ok=None)
        return {
            "success": False,
            "atom_id": atom_id,
            "error": "no_endpoint",
            "message": f"Atom '{atom_id}' has no health_url or endpoint",
            "old_status": old_status,
            "new_status": new_status,
        }

    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_PROBE_SCHEMES:
        new_status = _persist("invalid_url", ok=None)
        return {
            "success": False,
            "atom_id": atom_id,
            "error": "invalid_url",
            "message": f"Refusing to probe non-HTTP URL (scheme='{scheme or 'none'}')",
            "old_status": old_status,
            "new_status": new_status,
        }

    # BUG-017 两阶段：先把可探测原子标记为 probing（静默，不记审计）
    if old_status in _PROBEABLE_STATUSES and old_status != "probing":
        lifecycle["status"] = "probing"
        lifecycle["updated_at"] = now_iso()
        conn.execute(
            f"UPDATE {REGISTRY_TABLE} SET lifecycle_json = ? WHERE atom_id = ?",
            (json.dumps(lifecycle, ensure_ascii=False), atom_id),
        )
        conn.commit()

    started = time.monotonic()
    detail = ""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            code = resp.status
        ok = 200 <= code < 300
        probe_status = "ok" if ok else f"http_{code}"
    except urllib.error.HTTPError as exc:
        ok = False
        probe_status = f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        ok = False
        probe_status = "connection_error"
        reason = getattr(exc, "reason", exc)
        detail = str(reason)
    latency_ms = round((time.monotonic() - started) * 1000, 1)

    new_status = _persist(probe_status, ok, latency_ms, detail)
    return {
        "success": True,
        "atom_id": atom_id,
        "ok": ok,
        "probe_status": probe_status,
        "latency_ms": latency_ms,
        "old_status": old_status,
        "new_status": new_status,
    }


def probe_atoms(
    conn: sqlite3.Connection,
    atom_ids: Optional[List[str]] = None,
    timeout: float = 2.0,
    actor: str = "probe",
) -> List[Dict[str, Any]]:
    """批量探测。atom_ids 为 None 时探测注册表里的所有原子。

    单个原子探测异常不会中断整个批次（BUG-014）。"""
    if atom_ids is None:
        atom_ids = [a["atom_id"] for a in list_atoms(conn)]
    results: List[Dict[str, Any]] = []
    for aid in atom_ids:
        try:
            results.append(probe_atom(conn, aid, timeout=timeout, actor=actor))
        except Exception as exc:  # noqa: BLE001 - 批量探测必须隔离单点失败
            results.append(
                {
                    "success": False,
                    "atom_id": aid,
                    "error": "probe_exception",
                    "message": str(exc),
                }
            )
    return results


def get_atom(conn: sqlite3.Connection, atom_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        f"SELECT * FROM {REGISTRY_TABLE} WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_atom(row)


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
    """列出某原子的全部归档版本，按创建时间升序。"""
    rows = conn.execute(
        f"SELECT * FROM {VERSIONS_TABLE} WHERE atom_id = ? ORDER BY created_at, id",
        (atom_id,),
    ).fetchall()
    return [_row_to_version(row) for row in rows]


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
    return {
        "atom_id": atom_id,
        "order": order,
        "missing": sorted(missing),
        "cycles": cycles,
        "ok": not missing and not cycles,
    }


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
