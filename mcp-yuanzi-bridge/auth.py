#!/usr/bin/env python3
"""API 认证与授权（BUG-025 / M6.1a/1b/2a/2b）。

- Bearer token 认证：``Authorization: Bearer <token>``，静态 token 比较用
  ``secrets.compare_digest``（常量时间，防时序侧信道）。
- 静态（引导）token 来源优先级：环境变量 ``YUANZI_API_TOKEN`` >
  ``registry_meta`` 表 ``key='api_token'`` > 两者皆空进入开发模式
  （放行并打 warning 日志）。静态 token 视为 admin。
- ``api_tokens`` 表支持多 token：SHA-256 哈希查找，``role`` 列决定角色；
  ``revoked_at`` 非空或 ``expires_at`` 过期一律拒绝。
- 角色（设计 §3.2）：admin 全权 / registry 读+submit+status /
  viewer 只读 / probe 读+probe。
- 401/403 安全事件写入 ``security_audit_log``（AC-13）。
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENV_TOKEN_VAR = "YUANZI_API_TOKEN"
TOKENS_TABLE = "api_tokens"
META_TABLE = "registry_meta"
SECURITY_AUDIT_TABLE = "security_audit_log"

#: 四级角色（M6.2a）
ROLES = ("admin", "registry", "viewer", "probe")


@dataclass(frozen=True)
class Principal:
    """认证主体：标识 + 角色。"""

    subject: str
    role: str


def hash_token(token: str) -> str:
    """token 的 SHA-256 哈希；库中只存哈希，永不存明文（AC-08）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: str) -> datetime:
    """解析 ISO 时间戳；naive 一律按 UTC 处理。"""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ? AND type = 'table'", (name,)
    ).fetchone()
    return row is not None


def resolve_static_token(conn: sqlite3.Connection) -> Optional[str]:
    """静态引导 token：环境变量 > registry_meta，皆空返回 None（开发模式）。"""
    env_token = os.environ.get(ENV_TOKEN_VAR)
    if env_token:
        return env_token
    if _table_exists(conn, META_TABLE):
        row = conn.execute(
            f"SELECT value FROM {META_TABLE} WHERE key = 'api_token'"
        ).fetchone()
        if row and row[0]:
            return row[0]
    return None


def authenticate(conn: sqlite3.Connection, token: str) -> Optional[Principal]:
    """校验 token，成功返回 Principal，失败（错误/吊销/过期）返回 None。

    静态 token 走 ``secrets.compare_digest`` 常量时间比较（AC-02），视为
    admin（引导用途）；api_tokens 表 token 走哈希查找，role 列决定角色。
    """
    static = resolve_static_token(conn)
    if static is not None and secrets.compare_digest(token, static):
        return Principal(subject="static-token", role="admin")
    if not _table_exists(conn, TOKENS_TABLE):
        return None
    row = conn.execute(
        f"SELECT id, role, expires_at, revoked_at FROM {TOKENS_TABLE} "
        "WHERE token_hash = ?",
        (hash_token(token),),
    ).fetchone()
    if row is None:
        return None
    token_id, role, expires_at, revoked_at = row
    if revoked_at:
        return None
    if expires_at and _parse_ts(expires_at) <= datetime.now(timezone.utc):
        return None
    return Principal(subject=f"api_token:{token_id}", role=role)


# ============================================================
# token 管理（M6.1b，仅 admin 路由调用）
# ============================================================


def create_token(
    conn: sqlite3.Connection,
    description: str = "",
    role: str = "viewer",
    created_by: str = "api",
    expires_at: Optional[str] = None,
) -> Dict[str, Any]:
    """创建 token；明文仅在此处返回一次，库中只存 SHA-256 哈希（AC-08）。"""
    if role not in ROLES:
        raise ValueError(f"invalid role '{role}'; expected one of {ROLES}")
    if expires_at is not None:
        expires_at = _parse_ts(expires_at).isoformat()
    plaintext = secrets.token_urlsafe(32)
    cur = conn.execute(
        f"""
        INSERT INTO {TOKENS_TABLE}
        (token_hash, description, role, created_by, created_at,
         expires_at, revoked_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL)
        """,
        (hash_token(plaintext), description, role, created_by, _now_iso(), expires_at),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "token": plaintext,
        "description": description,
        "role": role,
        "created_by": created_by,
        "expires_at": expires_at,
    }


def list_tokens(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """列出 tokens（不含完整 token，也不含哈希）（AC-08）。"""
    rows = conn.execute(f"""
        SELECT id, description, role, created_by, created_at, expires_at,
               revoked_at
        FROM {TOKENS_TABLE} ORDER BY id
        """).fetchall()
    return [
        {
            "id": r[0],
            "description": r[1],
            "role": r[2],
            "created_by": r[3],
            "created_at": r[4],
            "expires_at": r[5],
            "revoked_at": r[6],
        }
        for r in rows
    ]


def revoke_token(conn: sqlite3.Connection, token_id: int) -> bool:
    """吊销 token（写 revoked_at），下一次请求即 401（AC-09）。"""
    cur = conn.execute(
        f"UPDATE {TOKENS_TABLE} SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
        (_now_iso(), token_id),
    )
    conn.commit()
    return cur.rowcount > 0


# ============================================================
# 安全审计（AC-13）
# ============================================================


def log_security_event(
    conn: sqlite3.Connection,
    subject: str,
    method: str,
    route: str,
    result: int,
    detail: str = "",
) -> None:
    """记录 401/403 安全事件：主体标识、路由、结果、时间戳。"""
    try:
        conn.execute(
            f"""
            INSERT INTO {SECURITY_AUDIT_TABLE}
            (subject, method, route, result, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (subject, method, route, result, detail, _now_iso()),
        )
        conn.commit()
    except sqlite3.Error:
        # 审计写入失败不应阻断请求主流程
        logger.exception("failed to write security audit event")
