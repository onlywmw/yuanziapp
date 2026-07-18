"""API Key 认证与 RBAC（M6 任务 6.1/6.2，DESIGN_M6 §3.1/§3.2）。

token 来源（优先级）：
1. 环境变量 YUANZI_API_TOKEN —— 静态管理员 token（role=admin）
2. agent.db 的 api_tokens 表 —— SHA-256(token) 落库，带角色/过期/吊销
3. 两者皆空 → 开发模式：允许所有请求并打印警告

角色：admin（全部）/ registry（读+submit+status）/ probe（读+probe）/ viewer（只读）
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ROLE_ADMIN = "admin"
ROLE_REGISTRY = "registry"
ROLE_PROBE = "probe"
ROLE_VIEWER = "viewer"

# 角色包含关系：高级别角色拥有低级别角色的权限
_ROLE_RANK = {ROLE_VIEWER: 1, ROLE_PROBE: 2, ROLE_REGISTRY: 3, ROLE_ADMIN: 4}

_security = HTTPBearer(auto_error=False)

ENV_TOKEN = "YUANZI_API_TOKEN"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _lookup_db_token(conn: sqlite3.Connection, token: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT id, role, expires_at, revoked_at FROM api_tokens WHERE token_hash = ?",
        (hash_token(token),),
    ).fetchone()
    if not row:
        return None
    token_id, role, expires_at, revoked_at = row
    if revoked_at:
        return None
    if expires_at and expires_at < _now_iso():
        return None
    return {"id": token_id, "role": role}


def _dev_mode(conn: sqlite3.Connection) -> bool:
    """没有配置任何 token 时进入开发模式（允许所有请求）。"""
    if os.environ.get(ENV_TOKEN):
        return False
    row = conn.execute(
        "SELECT 1 FROM api_tokens WHERE revoked_at IS NULL LIMIT 1"
    ).fetchone()
    return row is None


class Auth:
    """绑定到一个 sqlite 连接的认证/授权上下文。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        if _dev_mode(conn):
            print(
                "WARNING: no API token configured (env YUANZI_API_TOKEN or "
                "api_tokens table); running in DEV MODE - all requests allowed"
            )

    def verify_token(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ) -> Dict[str, Any]:
        """FastAPI 依赖：验证 Bearer token，返回 {role, subject}。"""
        if _dev_mode(self.conn):
            return {"role": ROLE_ADMIN, "subject": "dev-mode"}

        if not credentials:
            raise HTTPException(status_code=401, detail="Missing Bearer token")

        env_token = os.environ.get(ENV_TOKEN)
        if env_token and secrets.compare_digest(credentials.credentials, env_token):
            return {"role": ROLE_ADMIN, "subject": "env-token"}

        db_token = _lookup_db_token(self.conn, credentials.credentials)
        if db_token:
            return {"role": db_token["role"], "subject": f"token-{db_token['id']}"}

        raise HTTPException(status_code=401, detail="Invalid token")

    def require_role(self, *roles: str):
        """FastAPI 依赖工厂：要求最低角色（含更高级别）。"""

        async def dependency(
            credentials: Optional[HTTPAuthorizationCredentials] = Security(_security),
        ) -> Dict[str, Any]:
            principal = self.verify_token(credentials)
            allowed = any(
                _ROLE_RANK.get(principal["role"], 0) >= _ROLE_RANK.get(role, 99)
                for role in roles
            )
            if not allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"Requires role: {' or '.join(roles)}",
                )
            return principal

        return dependency


# ---------- token CRUD（api.py 的 /tokens 路由用） ----------


def create_token(
    conn: sqlite3.Connection,
    token: str,
    role: str = ROLE_VIEWER,
    description: str = "",
    created_by: str = "api",
    expires_at: Optional[str] = None,
) -> Dict[str, Any]:
    if role not in _ROLE_RANK:
        raise ValueError(f"unknown role: {role}")
    conn.execute(
        "INSERT INTO api_tokens (token_hash, description, role, created_by, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (hash_token(token), description, role, created_by, _now_iso(), expires_at),
    )
    conn.commit()
    token_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": token_id, "role": role, "description": description}


def list_tokens(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, description, role, created_by, created_at, expires_at, revoked_at "
        "FROM api_tokens ORDER BY id"
    ).fetchall()
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
    cursor = conn.execute(
        "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
        (_now_iso(), token_id),
    )
    conn.commit()
    return cursor.rowcount > 0
