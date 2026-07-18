#!/usr/bin/env python3
"""Yuanzi Registry REST API（FastAPI）。

把注册中心的能力包成 HTTP 服务：提交、审核、状态流转、健康探测、
版本回溯、依赖解析、统计与审计。

认证与授权（BUG-025 / M6.1a/1b/2a/2b）：
    所有业务路由要求 ``Authorization: Bearer <token>``。
    静态 token（env ``YUANZI_API_TOKEN`` 或 registry_meta ``api_token``）
    视为 admin；两者皆空进入开发模式（放行 + warning 日志）。
    api_tokens 表 token 的 role 列决定角色；RBAC 映射见设计
    ``docs/DESIGN_M6_SECURITY.md`` §3.2。

启动：
    uvicorn api:app --host 127.0.0.1 --port 8000
    REGISTRY_DB=/path/agent.db uvicorn api:app
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from auth import (
    ENV_TOKEN_VAR,
    Principal,
    authenticate,
    create_token,
    hash_token,
    list_tokens,
    log_security_event,
    resolve_static_token,
    revoke_token,
)
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from migrations import migrate
from pydantic import BaseModel
from registry import (
    compute_registry_stats,
    get_atom,
    get_atom_version,
    get_audit_log,
    list_atom_versions,
    list_atoms,
    probe_atom,
    probe_atoms,
    resolve_dependencies,
    review_atom,
    rollback_atom,
    set_atom_status,
    submit_atom,
)

logger = logging.getLogger(__name__)

DEFAULT_DB = Path(__file__).with_name("registry.db")

# RBAC 角色集合（设计 §3.2 / M6.2b）
READ_ROLES = ("admin", "registry", "viewer", "probe")  # viewer+：所有角色可读
SUBMIT_ROLES = ("admin", "registry")  # registry+：读 + submit + status
ADMIN_ROLES = ("admin",)  # admin 限定：review / rollback / token 管理
PROBE_ROLES = ("admin", "probe")  # probe+：健康探测

security = HTTPBearer(auto_error=False)


class ReviewBody(BaseModel):
    approved: bool
    reviewer: str = "api"
    comments: str = ""
    score: Optional[float] = None


class StatusBody(BaseModel):
    status: str
    detail: str = ""


class TokenCreateBody(BaseModel):
    description: str = ""
    role: str = "viewer"
    expires_at: Optional[str] = None


def create_app(db_path: str | Path = DEFAULT_DB) -> FastAPI:
    app = FastAPI(title="Yuanzi Registry API", version="0.1.0")
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    migrate(conn)

    if resolve_static_token(conn) is None:
        logger.warning(
            "%s 未设置且 registry_meta 无 api_token：API 处于开发模式，"
            "未认证请求将被放行；生产部署必须配置 token",
            ENV_TOKEN_VAR,
        )

    # ---------------- 认证 / 授权依赖（M6.1a / M6.2a） ----------------

    def verify_token(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    ) -> Principal:
        """解析认证主体；失败抛 401 并写安全审计（AC-01/02/13）。"""
        if credentials is None:
            if resolve_static_token(conn) is None:
                # 开发模式（AC-04）：放行但打 warning
                logger.warning(
                    "开发模式（未配置 %s / registry_meta api_token）："
                    "放行未认证请求 %s %s",
                    ENV_TOKEN_VAR,
                    request.method,
                    request.url.path,
                )
                return Principal(subject="anonymous", role="admin")
            log_security_event(
                conn,
                "anonymous",
                request.method,
                request.url.path,
                401,
                "missing bearer token",
            )
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        principal = authenticate(conn, credentials.credentials)
        if principal is None:
            log_security_event(
                conn,
                f"token_sha256:{hash_token(credentials.credentials)[:12]}",
                request.method,
                request.url.path,
                401,
                "invalid token",
            )
            raise HTTPException(status_code=401, detail="Invalid token")
        return principal

    def require_role(*roles: str):
        """RBAC 依赖（M6.2a）：角色不在白名单 → 403 并写安全审计（AC-11/13）。"""

        def checker(
            request: Request,
            principal: Principal = Depends(verify_token),
        ) -> Principal:
            if principal.role not in roles:
                log_security_event(
                    conn,
                    principal.subject,
                    request.method,
                    request.url.path,
                    403,
                    f"role '{principal.role}' not in {roles}",
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"Requires {' or '.join(roles)} role",
                )
            return principal

        return checker

    # ---------------- 业务路由（14 条全部绑定 require_role，M6.2b） ----------------

    @app.get("/health", dependencies=[Depends(require_role(*READ_ROLES))])
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/stats", dependencies=[Depends(require_role(*READ_ROLES))])
    def stats() -> Dict[str, Any]:
        return compute_registry_stats(conn)

    @app.get("/atoms", dependencies=[Depends(require_role(*READ_ROLES))])
    def atoms(
        status: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return list_atoms(conn, status=status, category=category, search=search)

    @app.post(
        "/atoms",
        status_code=201,
        dependencies=[Depends(require_role(*SUBMIT_ROLES))],
    )
    def submit(atom: Dict[str, Any]) -> Dict[str, Any]:
        result = submit_atom(conn, atom, actor="api")
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("message"))
        return result

    @app.get("/atoms/{atom_id}", dependencies=[Depends(require_role(*READ_ROLES))])
    def get_one(atom_id: str) -> Dict[str, Any]:
        atom = get_atom(conn, atom_id)
        if not atom:
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return atom

    @app.post(
        "/atoms/{atom_id}/review",
        dependencies=[Depends(require_role(*ADMIN_ROLES))],
    )
    def review(atom_id: str, body: ReviewBody) -> Dict[str, Any]:
        result = review_atom(
            conn,
            atom_id,
            approved=body.approved,
            reviewer=body.reviewer,
            comments=body.comments,
            score=body.score,
        )
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("message"))
        return result

    @app.post(
        "/atoms/{atom_id}/status",
        dependencies=[Depends(require_role(*SUBMIT_ROLES))],
    )
    def set_status(atom_id: str, body: StatusBody) -> Dict[str, Any]:
        result = set_atom_status(conn, atom_id, body.status, detail=body.detail)
        if not result.get("success"):
            code = 404 if result.get("error") == "not_found" else 409
            raise HTTPException(status_code=code, detail=result.get("message"))
        return result

    @app.post(
        "/atoms/{atom_id}/probe",
        dependencies=[Depends(require_role(*PROBE_ROLES))],
    )
    def probe_one(atom_id: str, timeout: float = 2.0) -> Dict[str, Any]:
        result = probe_atom(conn, atom_id, timeout=timeout, actor="api")
        if not result.get("success"):
            code = 404 if result.get("error") == "not_found" else 409
            raise HTTPException(status_code=code, detail=result.get("message"))
        return result

    @app.post("/probe", dependencies=[Depends(require_role(*PROBE_ROLES))])
    def probe_all(timeout: float = 2.0) -> Dict[str, Any]:
        results = probe_atoms(conn, timeout=timeout, actor="api")
        ok_count = sum(1 for r in results if r.get("ok"))
        return {
            "total": len(results),
            "reachable": ok_count,
            "results": results,
        }

    @app.get(
        "/atoms/{atom_id}/versions",
        dependencies=[Depends(require_role(*READ_ROLES))],
    )
    def versions(atom_id: str) -> List[Dict[str, Any]]:
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return list_atom_versions(conn, atom_id)

    @app.get(
        "/atoms/{atom_id}/versions/{version}",
        dependencies=[Depends(require_role(*READ_ROLES))],
    )
    def version_detail(atom_id: str, version: str) -> Dict[str, Any]:
        snapshot = get_atom_version(conn, atom_id, version)
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"Version '{version}' of atom '{atom_id}' not found",
            )
        return snapshot

    @app.post(
        "/atoms/{atom_id}/rollback/{version}",
        dependencies=[Depends(require_role(*ADMIN_ROLES))],
    )
    def rollback(atom_id: str, version: str) -> Dict[str, Any]:
        result = rollback_atom(conn, atom_id, version, actor="api")
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("message"))
        return result

    @app.get(
        "/atoms/{atom_id}/dependencies",
        dependencies=[Depends(require_role(*READ_ROLES))],
    )
    def dependencies(atom_id: str) -> Dict[str, Any]:
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return resolve_dependencies(conn, atom_id)

    @app.get("/audit", dependencies=[Depends(require_role(*READ_ROLES))])
    def audit(atom_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
        return get_audit_log(conn, atom_id=atom_id)

    # ---------------- token 管理（M6.1b，仅 admin） ----------------

    @app.post(
        "/api/v1/tokens",
        status_code=201,
        dependencies=[Depends(require_role(*ADMIN_ROLES))],
    )
    def create_token_route(
        body: TokenCreateBody,
        principal: Principal = Depends(verify_token),
    ) -> Dict[str, Any]:
        try:
            return create_token(
                conn,
                description=body.description,
                role=body.role,
                created_by=principal.subject,
                expires_at=body.expires_at,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get(
        "/api/v1/tokens",
        dependencies=[Depends(require_role(*ADMIN_ROLES))],
    )
    def list_tokens_route() -> List[Dict[str, Any]]:
        return list_tokens(conn)

    @app.delete(
        "/api/v1/tokens/{token_id}",
        dependencies=[Depends(require_role(*ADMIN_ROLES))],
    )
    def revoke_token_route(token_id: int) -> Dict[str, Any]:
        if not revoke_token(conn, token_id):
            raise HTTPException(status_code=404, detail=f"Token '{token_id}' not found")
        return {"revoked": True, "id": token_id}

    return app


app = create_app(os.environ.get("REGISTRY_DB", str(DEFAULT_DB)))
