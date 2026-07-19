"""BUG-036（compare_digest）与 BUG-037（401/403 审计落库）回归测试。"""

from __future__ import annotations

import sqlite3

import pytest
from api import create_app
from auth import (
    ACTION_AUTH_FAILED,
    ACTION_AUTHZ_DENIED,
    SECURITY_ATOM_ID,
    create_token,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient
from migrations import migrate

ADMIN_TOKEN = "admin-secret"
VIEWER_TOKEN = "viewer-secret"


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


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("YUANZI_API_TOKEN", raising=False)
    db = tmp_path / "auth-security.db"
    conn = sqlite3.connect(str(db))
    migrate(conn)
    create_token(conn, ADMIN_TOKEN, role="admin")
    create_token(conn, VIEWER_TOKEN, role="viewer")
    conn.close()
    with TestClient(create_app(db)) as c:
        yield c


def _security_events(client):
    """通过 /audit 端点读取安全事件（沿用既有审计查询路径）。"""
    r = client.get("/audit", params={"atom_id": SECURITY_ATOM_ID}, headers=_h(ADMIN_TOKEN))
    assert r.status_code == 200
    return r.json()


# ---------- BUG-036：compare_digest 路径回归 ----------


def test_env_token_compare_digest_accepts_exact_match(tmp_path, monkeypatch):
    """env token 精确匹配仍授予 admin（行为兼容）。"""
    monkeypatch.setenv("YUANZI_API_TOKEN", "env-secret")
    db = tmp_path / "cmp.db"
    conn = sqlite3.connect(str(db))
    migrate(conn)
    create_token(conn, VIEWER_TOKEN, role="viewer")  # 避免 dev mode
    conn.close()
    with TestClient(create_app(db)) as c:
        assert c.get("/tokens", headers=_h("env-secret")).status_code == 200
        # 等长但内容不同的 token 必须被拒绝（比较函数不是恒真）
        assert c.get("/tokens", headers=_h("env-secreX")).status_code == 401
        # 前缀相同、长度不同也必须被拒绝
        assert c.get("/tokens", headers=_h("env-secret-longer")).status_code == 401


def test_env_token_compare_digest_non_ascii(tmp_path, monkeypatch):
    """非 ASCII token 走 bytes 比较，不抛 TypeError（compare_digest str 形式仅限 ASCII）。

    HTTP 头只能携带 ASCII，故直接在单元层调用 verify_token。
    """
    from fastapi.security import HTTPAuthorizationCredentials

    from auth import Auth

    monkeypatch.setenv("YUANZI_API_TOKEN", "sécret-秘钥")
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    create_token(conn, VIEWER_TOKEN, role="viewer")  # 避免 dev mode
    auth = Auth(conn)

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="sécret-秘钥")
    assert auth.verify_token(creds)["role"] == "admin"

    bad = HTTPAuthorizationCredentials(scheme="Bearer", credentials="sécret-秘")
    with pytest.raises(HTTPException) as exc_info:
        auth.verify_token(bad)
    assert exc_info.value.status_code == 401


def test_db_token_still_works_after_compare_digest_change(client):
    """DB token 校验路径不受 BUG-036 影响。"""
    assert client.get("/atoms", headers=_h(VIEWER_TOKEN)).status_code == 200
    assert client.get("/atoms", headers=_h(ADMIN_TOKEN)).status_code == 200


# ---------- BUG-037：401/403 写审计日志 ----------


def test_401_missing_token_writes_audit(client):
    assert client.get("/atoms").status_code == 401
    events = _security_events(client)
    assert len(events) == 1
    assert events[0]["action"] == ACTION_AUTH_FAILED
    assert events[0]["actor"] == "anonymous"
    assert "401" in events[0]["detail"]
    assert events[0]["atom_id"] == SECURITY_ATOM_ID


def test_401_invalid_token_writes_audit(client):
    assert client.get("/atoms", headers=_h("wrong-token")).status_code == 401
    events = _security_events(client)
    assert len(events) == 1
    assert events[0]["action"] == ACTION_AUTH_FAILED
    assert "invalid" in events[0]["detail"]
    # 审计不得记录 token 本体
    assert "wrong-token" not in events[0]["detail"]


def test_403_insufficient_role_writes_audit(client):
    r = client.post("/atoms", json=_atom(), headers=_h(VIEWER_TOKEN))
    assert r.status_code == 403
    events = _security_events(client)
    assert len(events) == 1
    assert events[0]["action"] == ACTION_AUTHZ_DENIED
    # actor 为已通过认证的主体（token-<id>），detail 含要求角色与实际角色
    assert events[0]["actor"].startswith("token-")
    assert "registry" in events[0]["detail"]
    assert "viewer" in events[0]["detail"]


def test_successful_requests_write_no_security_audit(client):
    assert client.get("/atoms", headers=_h(VIEWER_TOKEN)).status_code == 200
    r = client.post("/atoms", json=_atom(), headers=_h(ADMIN_TOKEN))
    assert r.status_code == 201
    # 只有业务审计（submit），无安全事件
    assert _security_events(client) == []


def test_security_events_keep_audit_chain_valid(client):
    """安全事件接入哈希链后，整链校验仍通过（M6.4）。"""
    client.get("/atoms")  # 401
    client.get("/atoms", headers=_h("bad"))  # 401
    client.post("/atoms", json=_atom(), headers=_h(VIEWER_TOKEN))  # 403
    client.post("/atoms", json=_atom(), headers=_h(ADMIN_TOKEN))  # 201 业务审计
    r = client.get("/audit/verify", headers=_h(ADMIN_TOKEN))
    assert r.status_code == 200
    assert r.json()["valid"] is True
    assert r.json()["total_rows"] >= 4
