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

from embeddings import search_functions
from fastapi import FastAPI, HTTPException, Query
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

DEFAULT_DB = Path(__file__).with_name("registry.db")


class ReviewBody(BaseModel):
    approved: bool
    reviewer: str = "api"
    comments: str = ""
    score: Optional[float] = None


class StatusBody(BaseModel):
    status: str
    detail: str = ""


def create_app(db_path: str | Path = DEFAULT_DB) -> FastAPI:
    app = FastAPI(title="Yuanzi Registry API", version="0.1.0")
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    migrate(conn)

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/stats")
    def stats() -> Dict[str, Any]:
        return compute_registry_stats(conn)

    @app.get("/atoms")
    def atoms(
        status: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return list_atoms(conn, status=status, category=category, search=search)

    @app.post("/atoms", status_code=201)
    def submit(atom: Dict[str, Any]) -> Dict[str, Any]:
        result = submit_atom(conn, atom, actor="api")
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("message"))
        return result

    @app.get("/atoms/{atom_id}")
    def get_one(atom_id: str) -> Dict[str, Any]:
        atom = get_atom(conn, atom_id)
        if not atom:
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return atom

    @app.post("/atoms/{atom_id}/review")
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

    @app.post("/atoms/{atom_id}/status")
    def set_status(atom_id: str, body: StatusBody) -> Dict[str, Any]:
        result = set_atom_status(conn, atom_id, body.status, detail=body.detail)
        if not result.get("success"):
            code = 404 if result.get("error") == "not_found" else 409
            raise HTTPException(status_code=code, detail=result.get("message"))
        return result

    @app.post("/atoms/{atom_id}/probe")
    def probe_one(atom_id: str, timeout: float = 2.0) -> Dict[str, Any]:
        result = probe_atom(conn, atom_id, timeout=timeout, actor="api")
        if not result.get("success"):
            code = 404 if result.get("error") == "not_found" else 409
            raise HTTPException(status_code=code, detail=result.get("message"))
        return result

    @app.post("/probe")
    def probe_all(timeout: float = 2.0) -> Dict[str, Any]:
        results = probe_atoms(conn, timeout=timeout, actor="api")
        ok_count = sum(1 for r in results if r.get("ok"))
        return {
            "total": len(results),
            "reachable": ok_count,
            "results": results,
        }

    @app.get("/atoms/{atom_id}/versions")
    def versions(atom_id: str) -> List[Dict[str, Any]]:
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return list_atom_versions(conn, atom_id)

    @app.get("/atoms/{atom_id}/versions/{version}")
    def version_detail(atom_id: str, version: str) -> Dict[str, Any]:
        snapshot = get_atom_version(conn, atom_id, version)
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"Version '{version}' of atom '{atom_id}' not found",
            )
        return snapshot

    @app.post("/atoms/{atom_id}/rollback/{version}")
    def rollback(atom_id: str, version: str) -> Dict[str, Any]:
        result = rollback_atom(conn, atom_id, version, actor="api")
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("message"))
        return result

    @app.get("/atoms/{atom_id}/dependencies")
    def dependencies(atom_id: str) -> Dict[str, Any]:
        if not get_atom(conn, atom_id):
            raise HTTPException(status_code=404, detail=f"Atom '{atom_id}' not found")
        return resolve_dependencies(conn, atom_id)

    @app.get("/search")
    def search(
        q: str,
        limit: int = 10,
        provider: str = "mock",
        model: Optional[str] = None,
        min_score: float = 0.0,
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

    @app.get("/audit")
    def audit(atom_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
        return get_audit_log(conn, atom_id=atom_id)

    return app


app = create_app(os.environ.get("REGISTRY_DB", str(DEFAULT_DB)))
