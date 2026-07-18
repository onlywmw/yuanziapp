"""Tests for API Key auth + RBAC (M6 tasks 6.1/6.2, BUG-025)."""

from __future__ import annotations

import sqlite3

import pytest
from api import create_app
from auth import create_token
from fastapi.testclient import TestClient
from migrations import migrate

ADMIN_TOKEN = "admin-secret"
VIEWER_TOKEN = "viewer-secret"
REGISTRY_TOKEN = "registry-secret"
PROBE_TOKEN = "probe-secret"


def _atom(atom_id="com.example.sum"):
    return {
        "atom_id": atom_id,
        "name": "Sum",
        "version": "1.0.0",
        "description": "",
        "purpose": {"functions": [{"name": "sum"}]},
        "architecture": {"type": "t", "runtime": "r", "dependencies": []},
        "ownership": {"author": "t", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("YUANZI_API_TOKEN", raising=False)
    db = tmp_path / "auth-test.db"
    conn = sqlite3.connect(str(db))
    migrate(conn)
    create_token(conn, ADMIN_TOKEN, role="admin", description="boss")
    create_token(conn, VIEWER_TOKEN, role="viewer")
    create_token(conn, REGISTRY_TOKEN, role="registry")
    create_token(conn, PROBE_TOKEN, role="probe")
    conn.close()
    with TestClient(create_app(db)) as c:
        yield c


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_missing_token_401(client):
    assert client.get("/atoms").status_code == 401
    assert client.post("/atoms", json=_atom()).status_code == 401


def test_invalid_token_401(client):
    assert client.get("/atoms", headers=_h("wrong")).status_code == 401


def test_viewer_can_read_not_write(client):
    assert client.get("/atoms", headers=_h(VIEWER_TOKEN)).status_code == 200
    assert client.get("/stats", headers=_h(VIEWER_TOKEN)).status_code == 200
    assert (
        client.get("/search", params={"q": "x"}, headers=_h(VIEWER_TOKEN)).status_code
        == 200
    )
    # viewer 写操作 → 403
    assert (
        client.post("/atoms", json=_atom(), headers=_h(VIEWER_TOKEN)).status_code == 403
    )


def test_registry_can_submit_and_status_not_review(client):
    r = client.post("/atoms", json=_atom(), headers=_h(REGISTRY_TOKEN))
    assert r.status_code == 201
    # review 需要 admin
    r = client.post(
        "/atoms/com.example.sum/review",
        json={"approved": True},
        headers=_h(REGISTRY_TOKEN),
    )
    assert r.status_code == 403
    # admin 可以
    r = client.post(
        "/atoms/com.example.sum/review",
        json={"approved": True},
        headers=_h(ADMIN_TOKEN),
    )
    assert r.status_code == 200


def test_probe_role_can_probe_not_review(client):
    client.post("/atoms", json=_atom(), headers=_h(ADMIN_TOKEN))
    # probe 角色不能审核
    r = client.post(
        "/atoms/com.example.sum/review",
        json={"approved": True},
        headers=_h(PROBE_TOKEN),
    )
    assert r.status_code == 403
    # probe 角色可以探测（无 endpoint → 409 no_endpoint，说明通过了认证）
    r = client.post("/atoms/com.example.sum/probe", headers=_h(PROBE_TOKEN))
    assert r.status_code in (200, 409)


def test_admin_full_access_and_token_crud(client):
    r = client.post(
        "/tokens",
        json={"token": "new-secret", "role": "viewer", "description": "ci"},
        headers=_h(ADMIN_TOKEN),
    )
    assert r.status_code == 201
    token_id = r.json()["id"]

    tokens = client.get("/tokens", headers=_h(ADMIN_TOKEN)).json()
    assert any(t["description"] == "ci" for t in tokens)
    # token 列表不泄露 hash
    assert "token_hash" not in tokens[0]

    # 新 token 可用
    assert client.get("/atoms", headers=_h("new-secret")).status_code == 200

    # 吊销后失效
    assert (
        client.delete(f"/tokens/{token_id}", headers=_h(ADMIN_TOKEN)).status_code == 200
    )
    assert client.get("/atoms", headers=_h("new-secret")).status_code == 401


def test_viewer_cannot_manage_tokens(client):
    assert client.get("/tokens", headers=_h(VIEWER_TOKEN)).status_code == 403
    assert (
        client.post(
            "/tokens", json={"token": "x"}, headers=_h(VIEWER_TOKEN)
        ).status_code
        == 403
    )


def test_env_token_grants_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("YUANZI_API_TOKEN", "env-secret")
    db = tmp_path / "env-token.db"
    conn = sqlite3.connect(str(db))
    migrate(conn)
    # 表里放一个 viewer token，确保不是 dev mode
    create_token(conn, "viewer-only", role="viewer")
    conn.close()
    with TestClient(create_app(db)) as c:
        r = c.post("/atoms", json=_atom(), headers=_h("env-secret"))
        assert r.status_code == 201
        assert c.get("/tokens", headers=_h("env-secret")).status_code == 200


def test_post_search_endpoint(client):
    r = client.post("/search", params={"q": "x"}, headers=_h(VIEWER_TOKEN))
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_revoke_nonexistent_token_404(client):
    assert client.delete("/tokens/999", headers=_h(ADMIN_TOKEN)).status_code == 404


def test_audit_verify_endpoint(client):
    client.post("/atoms", json=_atom(), headers=_h(ADMIN_TOKEN))
    # viewer 无权访问审计链校验
    assert client.get("/audit/verify", headers=_h(VIEWER_TOKEN)).status_code == 403
    r = client.get("/audit/verify", headers=_h(ADMIN_TOKEN))
    assert r.status_code == 200
    assert r.json()["valid"] is True
    assert r.json()["total_rows"] >= 1


def test_builtin_atom_cannot_be_deleted(client):
    """加固4：DELETE 内置原子 → 403。"""
    r = client.delete("/atoms/system.file-read", headers=_h(ADMIN_TOKEN))
    assert r.status_code == 403


def test_delete_atom_admin_only(client):
    client.post("/atoms", json=_atom(), headers=_h(ADMIN_TOKEN))
    # viewer 无权删除
    assert (
        client.delete("/atoms/com.example.sum", headers=_h(VIEWER_TOKEN)).status_code
        == 403
    )
    # admin 可删除
    assert (
        client.delete("/atoms/com.example.sum", headers=_h(ADMIN_TOKEN)).status_code
        == 200
    )
    assert (
        client.get("/atoms/com.example.sum", headers=_h(ADMIN_TOKEN)).status_code == 404
    )
