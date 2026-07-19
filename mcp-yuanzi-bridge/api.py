#!/usr/bin/env python3
"""Yuanzi Registry REST API（FastAPI）。

把注册中心的能力包成 HTTP 服务：提交、审核、状态流转、健康探测、
版本回溯、依赖解析、统计与审计。

启动：
    uvicorn api:app --host 127.0.0.1 --port 8000
    REGISTRY_DB=/path/agent.db uvicorn api:app
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from auth import (
    ROLE_ADMIN,
    ROLE_PROBE,
    ROLE_REGISTRY,
    ROLE_VIEWER,
    Auth,
    create_token,
    list_tokens,
    revoke_token,
)
from embeddings import search_functions
from engine import get_run, list_workflow_runs, run_workflow
from fastapi import Depends, FastAPI, HTTPException, Query
from federation import (
    add_peer,
    export_atoms,
    list_peers,
    remove_peer,
    sync_peer,
)
from marketplace import (
    add_review,
    composite_score,
    list_reviews,
    marketplace_board,
)
from migrations import migrate
from pydantic import BaseModel
from registry import (
    RESERVED_PREFIXES,
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
    verify_audit_chain,
)
from workflow import get_workflow, list_workflows, save_workflow, validate_workflow

DEFAULT_DB = Path(__file__).with_name("registry.db")


def _with_side_effect(atom: Dict[str, Any]) -> Dict[str, Any]:
    """原子视图暴露 side_effect 字段（P0-B）。

    注册原子取 meta（submit 时已归一化并镜像进 classification），
    基础原子（system.*）取 BASE_ATOM_SIDE_EFFECTS 常量表，缺省 impure。
    """
    from registry.core import resolve_side_effect  # 惰性导入，避免包循环

    atom["side_effect"] = resolve_side_effect(atom)
    return atom


class ReviewBody(BaseModel):
    approved: bool
    reviewer: str = "api"
    comments: str = ""
    score: Optional[float] = None


class NotarizeBody(BaseModel):
    # 手动公证动作（DESIGN_BLOCKCHAIN_NOTARY §二）：补登/转让/版本/下架
    action: str


class StatusBody(BaseModel):
    status: str
    detail: str = ""


class PeerBody(BaseModel):
    name: str
    base_url: str
    trust_level: str = "review"


class AtomReviewBody(BaseModel):
    author: str
    rating: int
    text: str = ""


class TokenBody(BaseModel):
    token: str
    role: str = "viewer"
    description: str = ""
    expires_at: Optional[str] = None


def create_app(db_path: str | Path = DEFAULT_DB) -> FastAPI:
    app = FastAPI(title="Yuanzi Registry API", version="0.1.0")
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    auth = Auth(conn)

    viewer = Depends(auth.require_role(ROLE_VIEWER))
    registry_role = Depends(auth.require_role(ROLE_REGISTRY))
    probe_role = Depends(auth.require_role(ROLE_PROBE))
    admin = Depends(auth.require_role(ROLE_ADMIN))

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/stats", dependencies=[viewer])
    def stats() -> Dict[str, Any]:
        return compute_registry_stats(conn)

    @app.get("/atoms", dependencies=[viewer])
    def atoms(
        status: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # P0-B：列表视图逐条带上 side_effect
        return [
            _with_side_effect(a)
            for a in list_atoms(conn, status=status, category=category, search=search)
        ]

    @app.post("/atoms", status_code=201, dependencies=[registry_role])
    def submit(atom: Dict[str, Any]) -> Dict[str, Any]:
        result = submit_atom(conn, atom, actor="api")
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("message"))
        return result

    @app.delete("/atoms/{atom_id}", dependencies=[admin])
    def delete_atom(atom_id: str) -> Dict[str, Any]:
        # 内置基础原子不可删除（加固4）
        for prefix in RESERVED_PREFIXES:
            if atom_id.startswith(prefix):
                raise HTTPException(
                    status_code=403,
                    detail=f"'{prefix}*' built-in atoms cannot be deleted",
                )
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        conn.execute("DELETE FROM atom_registry WHERE atom_id = ?", (atom_id,))
        conn.commit()
        return {"success": True, "atom_id": atom_id}

    @app.get("/atoms/{atom_id}", dependencies=[viewer])
    def get_one(atom_id: str) -> Dict[str, Any]:
        atom = get_atom(conn, atom_id)
        if not atom:
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        # P0-B：详情视图带上 side_effect
        return _with_side_effect(atom)

    @app.post("/atoms/{atom_id}/review", dependencies=[admin])
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

    # 区块链公证允许的手动 action（DESIGN_BLOCKCHAIN_NOTARY §二）
    NOTARIZE_ACTIONS = ("register", "transfer", "version", "deprecate")

    def _load_notarize():
        """惰性导入 notarize 模块（同 auth.py 里 from registry import _audit 的惰性导入模式）。

        模块未落盘时返回 None，由路由报 501，不影响其余接口。
        """
        try:
            import notarize

            return notarize
        except Exception:  # noqa: BLE001
            return None

    @app.get("/atoms/{atom_id}/verify", dependencies=[viewer])
    def verify_atom_notarization(atom_id: str) -> Dict[str, Any]:
        """链上公证验证（DESIGN_BLOCKCHAIN_NOTARY §六，viewer 可读）。"""
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        notarize = _load_notarize()
        if notarize is None:
            raise HTTPException(status_code=501, detail="notarize module unavailable")
        return notarize.verify_notarization(conn, atom_id)

    @app.post("/atoms/{atom_id}/notarize")
    def notarize_atom_manual(
        atom_id: str,
        body: NotarizeBody,
        principal: Dict[str, Any] = Depends(auth.require_role(ROLE_ADMIN)),
    ) -> Dict[str, Any]:
        """手动触发公证记录：补登/转让/版本/下架（admin 专用，actor 取 token 身份）。"""
        if body.action not in NOTARIZE_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"action must be one of {NOTARIZE_ACTIONS}",
            )
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        notarize = _load_notarize()
        if notarize is None:
            raise HTTPException(status_code=501, detail="notarize module unavailable")
        return notarize.notarize_atom(
            conn, atom_id, body.action, actor=principal.get("subject", "api")
        )

    @app.post("/atoms/{atom_id}/status", dependencies=[registry_role])
    def set_status(atom_id: str, body: StatusBody) -> Dict[str, Any]:
        result = set_atom_status(conn, atom_id, body.status, detail=body.detail)
        if not result.get("success"):
            code = 404 if result.get("error") == "not_found" else 409
            raise HTTPException(status_code=code, detail=result.get("message"))
        return result

    @app.post("/atoms/{atom_id}/probe", dependencies=[probe_role])
    def probe_one(atom_id: str, timeout: float = 2.0) -> Dict[str, Any]:
        result = probe_atom(conn, atom_id, timeout=timeout, actor="api")
        if not result.get("success"):
            code = 404 if result.get("error") == "not_found" else 409
            raise HTTPException(status_code=code, detail=result.get("message"))
        return result

    @app.post("/probe", dependencies=[probe_role])
    def probe_all(timeout: float = 2.0) -> Dict[str, Any]:
        results = probe_atoms(conn, timeout=timeout, actor="api")
        ok_count = sum(1 for r in results if r.get("ok"))
        return {
            "total": len(results),
            "reachable": ok_count,
            "results": results,
        }

    @app.get("/atoms/{atom_id}/versions", dependencies=[viewer])
    def versions(atom_id: str) -> List[Dict[str, Any]]:
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return list_atom_versions(conn, atom_id)

    @app.get("/atoms/{atom_id}/versions/{version}", dependencies=[viewer])
    def version_detail(atom_id: str, version: str) -> Dict[str, Any]:
        snapshot = get_atom_version(conn, atom_id, version)
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"Version '{version}' of atom '{atom_id}' not found",
            )
        return snapshot

    @app.post("/atoms/{atom_id}/rollback/{version}", dependencies=[admin])
    def rollback(atom_id: str, version: str) -> Dict[str, Any]:
        result = rollback_atom(conn, atom_id, version, actor="api")
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("message"))
        return result

    @app.get("/atoms/{atom_id}/dependencies", dependencies=[viewer])
    def dependencies(atom_id: str) -> Dict[str, Any]:
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return resolve_dependencies(conn, atom_id)

    @app.get("/atoms/{atom_id}/recommendations", dependencies=[viewer])
    def recommendations(atom_id: str, limit: int = 5) -> Dict[str, Any]:
        """原子搭配推荐（M5 任务 5.3）：依赖/被依赖/同类别加权。"""
        from recommend import recommend_for_atom

        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return {
            "atom_id": atom_id,
            "recommendations": recommend_for_atom(conn, atom_id, limit=limit),
        }

    @app.get("/atoms/{atom_id}/combination", dependencies=[viewer])
    def combination(atom_id: str) -> Dict[str, Any]:
        """原子的完整启动组合（依赖闭包，拓扑序）。"""
        from recommend import recommend_combination

        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return recommend_combination(conn, atom_id)

    @app.post("/search", dependencies=[viewer])
    def search_post(
        q: str,
        limit: int = 10,
        provider: str = "mock",
        model: Optional[str] = None,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:
        return _do_search(q, limit, provider, model, min_score)

    @app.get("/search", dependencies=[viewer])
    def search(
        q: str,
        limit: int = 10,
        provider: str = "mock",
        model: Optional[str] = None,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:
        return _do_search(q, limit, provider, model, min_score)

    def _do_search(
        q: str,
        limit: int,
        provider: str,
        model: Optional[str],
        min_score: float,
    ) -> Dict[str, Any]:
        """语义搜索原子功能（M5 任务 5.2）。

        provider=mock 离线可用；provider=openai 需要
        EMBEDDING_API_BASE / EMBEDDING_API_KEY / EMBEDDING_MODEL。
        """
        from embeddings import get_provider

        try:
            prov = get_provider(provider)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        results = search_functions(
            conn, q, prov, limit=limit, model=model, min_score=min_score
        )
        return {
            "query": q,
            "provider": prov.name,
            "model": model or prov.model,
            "count": len(results),
            "results": results,
        }

    @app.post("/tokens", status_code=201, dependencies=[admin])
    def create_api_token(body: TokenBody) -> Dict[str, Any]:
        try:
            return create_token(
                conn,
                token=body.token,
                role=body.role,
                description=body.description,
                expires_at=body.expires_at,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/tokens", dependencies=[admin])
    def list_api_tokens() -> List[Dict[str, Any]]:
        return list_tokens(conn)

    @app.delete("/tokens/{token_id}", dependencies=[admin])
    def revoke_api_token(token_id: int) -> Dict[str, Any]:
        if not revoke_token(conn, token_id):
            raise HTTPException(
                status_code=404, detail="Token not found or already revoked"
            )
        return {"success": True, "id": token_id}

    @app.post("/atoms/{atom_id}/reviews", status_code=201, dependencies=[registry_role])
    def create_review(atom_id: str, body: AtomReviewBody) -> Dict[str, Any]:
        result = add_review(conn, atom_id, body.author, body.rating, body.text)
        if not result.get("success"):
            code = 404 if result.get("error") == "not_found" else 400
            raise HTTPException(
                status_code=code, detail=result.get("message") or result.get("error")
            )
        return result

    @app.get("/atoms/{atom_id}/reviews", dependencies=[viewer])
    def reviews(atom_id: str) -> List[Dict[str, Any]]:
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return list_reviews(conn, atom_id)

    @app.get("/atoms/{atom_id}/rating", dependencies=[viewer])
    def rating(atom_id: str) -> Dict[str, Any]:
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return composite_score(conn, atom_id)

    @app.get("/marketplace", dependencies=[viewer])
    def marketplace(tab: str = "hot", limit: int = 20) -> List[Dict[str, Any]]:
        if tab not in ("hot", "top", "new"):
            raise HTTPException(status_code=400, detail="tab must be hot|top|new")
        return marketplace_board(conn, tab=tab, limit=limit)

    @app.post("/workflows", status_code=201, dependencies=[registry_role])
    def create_workflow(definition: Dict[str, Any]) -> Dict[str, Any]:
        result = save_workflow(conn, definition)
        if not result.get("success"):
            raise HTTPException(
                status_code=422,
                detail={"errors": result["errors"], "warnings": result["warnings"]},
            )
        return result

    @app.get("/workflows", dependencies=[viewer])
    def workflows() -> List[Dict[str, Any]]:
        return list_workflows(conn)

    @app.get("/workflows/{workflow_id}", dependencies=[viewer])
    def workflow_detail(workflow_id: str) -> Dict[str, Any]:
        wf = get_workflow(conn, workflow_id)
        if not wf:
            raise HTTPException(
                status_code=404, detail=f"Workflow '{workflow_id}' not found"
            )
        return wf

    @app.post("/workflows/{workflow_id}/validate", dependencies=[viewer])
    def workflow_validate(workflow_id: str) -> Dict[str, Any]:
        wf = get_workflow(conn, workflow_id)
        if not wf:
            raise HTTPException(
                status_code=404, detail=f"Workflow '{workflow_id}' not found"
            )
        return validate_workflow(wf["definition"])

    @app.post("/workflows/{workflow_id}/run", dependencies=[registry_role])
    def workflow_run(
        workflow_id: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        run = run_workflow(conn, workflow_id, params=params)
        if "not found" in (run.get("error") or ""):
            raise HTTPException(status_code=404, detail=run["error"])
        return run

    @app.get("/workflows/{workflow_id}/runs", dependencies=[viewer])
    def workflow_runs(workflow_id: str) -> List[Dict[str, Any]]:
        return list_workflow_runs(conn, workflow_id)

    @app.get("/runs/{run_id}", dependencies=[viewer])
    def run_detail(run_id: str) -> Dict[str, Any]:
        run = get_run(conn, run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        return run

    @app.get("/federation/export", dependencies=[viewer])
    def federation_export() -> Dict[str, Any]:
        """对外共享的原子元数据（不含 runtime/endpoint）。"""
        return {"atoms": export_atoms(conn)}

    @app.post("/federation/peers", status_code=201, dependencies=[admin])
    def create_peer(body: PeerBody) -> Dict[str, Any]:
        result = add_peer(conn, body.name, body.base_url, body.trust_level)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result

    @app.get("/federation/peers", dependencies=[viewer])
    def peers() -> List[Dict[str, Any]]:
        return list_peers(conn)

    @app.delete("/federation/peers/{peer_id}", dependencies=[admin])
    def delete_peer(peer_id: int) -> Dict[str, Any]:
        if not remove_peer(conn, peer_id):
            raise HTTPException(status_code=404, detail="Peer not found")
        return {"success": True, "id": peer_id}

    @app.post("/federation/sync/{peer_id}", dependencies=[admin])
    def federation_sync(peer_id: int) -> Dict[str, Any]:
        result = sync_peer(conn, peer_id)
        if not result.get("success"):
            code = 404 if result.get("error") == "peer_not_found" else 400
            raise HTTPException(
                status_code=code, detail=result.get("message") or result.get("error")
            )
        return result

    @app.get("/audit/verify", dependencies=[admin])
    def audit_verify() -> Dict[str, Any]:
        """审计哈希链完整性校验（M6.4）。"""
        return verify_audit_chain(conn)

    @app.get("/audit", dependencies=[viewer])
    def audit(atom_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
        return get_audit_log(conn, atom_id=atom_id)

    return app


app = create_app(os.environ.get("REGISTRY_DB", str(DEFAULT_DB)))


def start_server(files_dir: str, host: str = "127.0.0.1", port: int = 8081):
    """Chaquopy 入口：在守护线程里启动 uvicorn。

    Kotlin 侧调用：py.getModule("api").callAttr("start_server", filesDir)
    DB 落在 <files_dir>/agent.db（DESIGN_CHAQUOPY_MIGRATION §3.3）。
    """
    import threading

    import uvicorn

    db_path = str(Path(files_dir) / "agent.db")
    config = uvicorn.Config(
        create_app(db_path), host=host, port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread
