"""BUG-025 验收测试：Bearer 认证 + RBAC + token 管理 + 安全审计。

逐条对应 qa/tests/docs/BUG-025-ACCEPTANCE-CRITERIA.md 的 AC-01 ~ AC-13。
测试间通过 tmp_path（独立 SQLite 文件）与 monkeypatch（env 变量）隔离。
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import auth
import pytest
from api import create_app
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ADMIN_TOKEN = "test-admin-secret"
ENV_TOKEN = "env-secret"
META_TOKEN = "meta-secret"

#: 14 条业务路由（AC-01 / AC-12 共用清单，路径为具体实例）
PROTECTED_ROUTES = [
    ("GET", "/health"),
    ("GET", "/stats"),
    ("GET", "/atoms"),
    ("POST", "/atoms"),
    ("GET", "/atoms/com.example.sum"),
    ("POST", "/atoms/com.example.sum/review"),
    ("POST", "/atoms/com.example.sum/status"),
    ("POST", "/atoms/com.example.sum/probe"),
    ("POST", "/probe"),
    ("GET", "/atoms/com.example.sum/versions"),
    ("GET", "/atoms/com.example.sum/versions/1.0.0"),
    ("POST", "/atoms/com.example.sum/rollback/1.0.0"),
    ("GET", "/atoms/com.example.sum/dependencies"),
    ("GET", "/audit"),
]


def _atom(atom_id="com.example.sum", version="1.0.0", functions=("sum",)):
    return {
        "atom_id": atom_id,
        "name": "Sum",
        "version": version,
        "description": "adds numbers",
        "purpose": {"functions": [{"name": f} for f in functions]},
        "architecture": {
            "type": "python_script",
            "runtime": "python3.12",
            "dependencies": [],
        },
        "ownership": {"author": "test", "license": "MIT"},
        "runtime": {"health_url": "http://127.0.0.1:9000/health"},
        "lifecycle": {"status": "submitted"},
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """每个用例从干净的 env 开始，避免 token 泄漏跨用例。"""
    monkeypatch.delenv(auth.ENV_TOKEN_VAR, raising=False)


def _make_client(db, monkeypatch, token=ADMIN_TOKEN) -> TestClient:
    """创建 app；默认配置静态 admin token（env 来源）。"""
    if token is not None:
        monkeypatch.setenv(auth.ENV_TOKEN_VAR, token)
    return TestClient(create_app(db))


def _insert_db_token(db, plaintext, role, *, expires_at=None, revoked_at=None) -> int:
    """直接向 api_tokens 表插入一个指定角色的 token（AC-07/09/10/11 用）。"""
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.execute(
            "INSERT INTO api_tokens (token_hash, description, role, created_by,"
            " created_at, expires_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                auth.hash_token(plaintext),
                f"{role} test token",
                role,
                "test",
                datetime.now(timezone.utc).isoformat(),
                expires_at,
                revoked_at,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _seed_registry(client: TestClient) -> None:
    """用 admin 提交两个版本并审核通过，供写路由矩阵调用。"""
    h = _auth(ADMIN_TOKEN)
    assert (
        client.post("/atoms", json=_atom(version="1.0.0"), headers=h).status_code == 201
    )
    assert (
        client.post(
            "/atoms",
            json=_atom(version="1.1.0", functions=("sum", "sum_many")),
            headers=h,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/atoms/com.example.sum/review", json={"approved": True}, headers=h
        ).status_code
        == 200
    )


def _stub_probe_ok(monkeypatch) -> None:
    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=None: _Resp())


# ============================================================
# AC-01 无 token → 401（P0，14 条路由逐一）
# ============================================================


@pytest.mark.parametrize(
    "method,path", PROTECTED_ROUTES, ids=[f"{m} {p}" for m, p in PROTECTED_ROUTES]
)
def test_ac01_missing_token_401(tmp_path, monkeypatch, method, path):
    client = _make_client(tmp_path / "t.db", monkeypatch)
    r = client.request(method, path)
    assert r.status_code == 401
    assert "Missing Bearer token" in r.json()["detail"]


# ============================================================
# AC-02 错误 token → 401 + 常量时间比较（P0）
# ============================================================


def test_ac02_wrong_token_401(tmp_path, monkeypatch):
    client = _make_client(tmp_path / "t.db", monkeypatch)
    r = client.get("/atoms", headers=_auth("wrong-token"))
    assert r.status_code == 401


def test_ac02_constant_time_compare():
    """代码审查断言：token 比较使用 secrets.compare_digest（防时序侧信道）。"""
    src = inspect.getsource(auth)
    assert "secrets.compare_digest" in src


# ============================================================
# AC-03 有效 token 放行（P0）
# ============================================================


def test_ac03_valid_token_200(tmp_path, monkeypatch):
    client = _make_client(tmp_path / "t.db", monkeypatch)
    r = client.get("/atoms", headers=_auth(ADMIN_TOKEN))
    assert r.status_code == 200
    assert r.json() == []


# ============================================================
# AC-04 开发模式退化（P1）
# ============================================================


def test_ac04_dev_mode_allows_with_warning(tmp_path, monkeypatch, caplog):
    client = _make_client(tmp_path / "t.db", monkeypatch, token=None)
    with caplog.at_level(logging.WARNING):
        r = client.get("/atoms")
    assert r.status_code == 200
    assert any("开发模式" in rec.getMessage() for rec in caplog.records)


# ============================================================
# AC-05 token 来源优先级 env > registry_meta（P1）
# ============================================================


def test_ac05_env_overrides_registry_meta(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch, token=ENV_TOKEN)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO registry_meta (key, value) VALUES ('api_token', ?)",
        (META_TOKEN,),
    )
    conn.commit()
    conn.close()

    # env 存在时：仅 env token 通过
    assert client.get("/atoms", headers=_auth(ENV_TOKEN)).status_code == 200
    assert client.get("/atoms", headers=_auth(META_TOKEN)).status_code == 401

    # 移除 env → registry_meta token 生效
    monkeypatch.delenv(auth.ENV_TOKEN_VAR)
    assert client.get("/atoms", headers=_auth(META_TOKEN)).status_code == 200
    assert client.get("/atoms", headers=_auth(ENV_TOKEN)).status_code == 401


# ============================================================
# AC-06 api_tokens 表结构（P0）
# ============================================================


def test_ac06_api_tokens_schema(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    _make_client(db, monkeypatch)  # create_app 内执行迁移
    conn = sqlite3.connect(str(db))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_tokens)")}
        assert {
            "id",
            "token_hash",
            "description",
            "role",
            "created_by",
            "created_at",
            "expires_at",
            "revoked_at",
        } <= cols

        # token_hash 有唯一索引
        unique_cols = []
        for idx in conn.execute("PRAGMA index_list(api_tokens)").fetchall():
            if idx[2]:
                unique_cols += [
                    c[2]
                    for c in conn.execute(f"PRAGMA index_info({idx[1]})").fetchall()
                ]
        assert "token_hash" in unique_cols

        # 重复 hash 触发唯一约束错误
        h = auth.hash_token("dup")
        conn.execute(
            "INSERT INTO api_tokens (token_hash, role, created_at)"
            " VALUES (?, 'viewer', '2026-01-01T00:00:00+00:00')",
            (h,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO api_tokens (token_hash, role, created_at)"
                " VALUES (?, 'viewer', '2026-01-01T00:00:00+00:00')",
                (h,),
            )
    finally:
        conn.close()


# ============================================================
# AC-07 token 管理端点仅 admin（P0）
# ============================================================


@pytest.mark.parametrize("role", ["registry", "viewer", "probe"])
def test_ac07_token_endpoints_forbid_non_admin(tmp_path, monkeypatch, role):
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch)
    _insert_db_token(db, f"{role}-tok", role)
    h = _auth(f"{role}-tok")
    assert (
        client.post("/api/v1/tokens", json={"role": "viewer"}, headers=h).status_code
        == 403
    )
    assert client.get("/api/v1/tokens", headers=h).status_code == 403
    assert client.delete("/api/v1/tokens/1", headers=h).status_code == 403


def test_ac07_token_endpoints_allow_admin(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch)
    h = _auth(ADMIN_TOKEN)
    r = client.post(
        "/api/v1/tokens", json={"description": "ci", "role": "viewer"}, headers=h
    )
    assert r.status_code == 201
    token_id = r.json()["id"]
    assert client.get("/api/v1/tokens", headers=h).status_code == 200
    assert client.delete(f"/api/v1/tokens/{token_id}", headers=h).status_code == 200


# ============================================================
# AC-08 token 只存 SHA-256 哈希，明文仅创建时返回一次（P0）
# ============================================================


def test_ac08_token_hashed_and_shown_once(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch)
    h = _auth(ADMIN_TOKEN)
    r = client.post(
        "/api/v1/tokens", json={"description": "ci", "role": "viewer"}, headers=h
    )
    assert r.status_code == 201
    plaintext = r.json()["token"]

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT token_hash FROM api_tokens WHERE id = ?", (r.json()["id"],)
        ).fetchone()
        assert row[0] == hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        assert row[0] != plaintext
        # 表内没有明文列
        cols = {c[1] for c in conn.execute("PRAGMA table_info(api_tokens)")}
        assert "token" not in cols
    finally:
        conn.close()

    # 列表端点不再返回完整 token（也不返回哈希）
    listed = client.get("/api/v1/tokens", headers=h).json()
    assert listed
    for item in listed:
        assert "token" not in item
        assert "token_hash" not in item


def test_ac08_create_token_rejects_invalid_role(tmp_path, monkeypatch):
    client = _make_client(tmp_path / "t.db", monkeypatch)
    r = client.post(
        "/api/v1/tokens",
        json={"description": "bad", "role": "superuser"},
        headers=_auth(ADMIN_TOKEN),
    )
    assert r.status_code == 400


# ============================================================
# AC-09 吊销立即生效（P1）
# ============================================================


def test_ac09_revoked_token_401(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch)
    token_id = _insert_db_token(db, "revoke-me", "viewer")
    assert client.get("/atoms", headers=_auth("revoke-me")).status_code == 200

    r = client.delete(f"/api/v1/tokens/{token_id}", headers=_auth(ADMIN_TOKEN))
    assert r.status_code == 200

    assert client.get("/atoms", headers=_auth("revoke-me")).status_code == 401
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT revoked_at FROM api_tokens WHERE id = ?", (token_id,)
        ).fetchone()
        assert row[0]
    finally:
        conn.close()


# ============================================================
# AC-10 过期 token → 401（P1）
# ============================================================


def test_ac10_expired_token_401(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _insert_db_token(db, "expired-tok", "viewer", expires_at=past)
    _insert_db_token(db, "fresh-tok", "viewer", expires_at=future)

    assert client.get("/atoms", headers=_auth("expired-tok")).status_code == 401
    assert client.get("/atoms", headers=_auth("fresh-tok")).status_code == 200


# ============================================================
# AC-11 RBAC 权限矩阵（P0，逐格断言）
# ============================================================

#: (role, action, expected)；expected 为 "2xx" 或具体状态码。
#: 对应验收文档矩阵（POST /search 列在 api.py 中不存在，不在矩阵内）。
MATRIX = [
    ("admin", "list", 200),
    ("admin", "submit", "2xx"),
    ("admin", "status", "2xx"),
    ("admin", "review", "2xx"),
    ("admin", "rollback", "2xx"),
    ("admin", "probe", "2xx"),
    ("registry", "list", 200),
    ("registry", "submit", "2xx"),
    ("registry", "status", "2xx"),
    ("registry", "review", 403),
    ("registry", "rollback", 403),
    ("registry", "probe", 403),
    ("viewer", "list", 200),
    ("viewer", "submit", 403),
    ("viewer", "status", 403),
    ("viewer", "review", 403),
    ("viewer", "rollback", 403),
    ("viewer", "probe", 403),
    ("probe", "list", 200),
    ("probe", "submit", 403),
    ("probe", "status", 403),
    ("probe", "review", 403),
    ("probe", "rollback", 403),
    ("probe", "probe", "2xx"),
]


@pytest.mark.parametrize(
    "role,action,expected", MATRIX, ids=[f"{r}-{a}" for r, a, _ in MATRIX]
)
def test_ac11_rbac_matrix(tmp_path, monkeypatch, role, action, expected):
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch)
    if role == "admin":
        headers = _auth(ADMIN_TOKEN)
    else:
        _insert_db_token(db, f"{role}-tok", role)
        headers = _auth(f"{role}-tok")
    _seed_registry(client)
    _stub_probe_ok(monkeypatch)

    if action == "list":
        r = client.get("/atoms", headers=headers)
    elif action == "submit":
        r = client.post(
            "/atoms",
            json=_atom(f"com.example.{role}.new", functions=(f"fn_{role}",)),
            headers=headers,
        )
    elif action == "status":
        r = client.post(
            "/atoms/com.example.sum/status",
            json={"status": "offline"},
            headers=headers,
        )
    elif action == "review":
        r = client.post(
            "/atoms/com.example.sum/review",
            json={"approved": True},
            headers=headers,
        )
    elif action == "rollback":
        r = client.post("/atoms/com.example.sum/rollback/1.0.0", headers=headers)
    elif action == "probe":
        r = client.post("/atoms/com.example.sum/probe", headers=headers)

    if expected == "2xx":
        assert 200 <= r.status_code < 300, r.text
    else:
        assert r.status_code == expected, r.text


@pytest.mark.parametrize(
    "role,expected",
    [("admin", 200), ("probe", 200), ("registry", 403), ("viewer", 403)],
)
def test_ac11_batch_probe_roles(tmp_path, monkeypatch, role, expected):
    """POST /probe（批量）绑定 probe+（admin 含）。"""
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch)
    if role == "admin":
        headers = _auth(ADMIN_TOKEN)
    else:
        _insert_db_token(db, f"{role}-tok", role)
        headers = _auth(f"{role}-tok")
    _seed_registry(client)
    _stub_probe_ok(monkeypatch)
    assert client.post("/probe", headers=headers).status_code == expected


def test_ac11_get_routes_allow_all_roles(tmp_path, monkeypatch):
    """GET 类路由（viewer+）四种角色全部放行。"""
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch)
    _seed_registry(client)
    get_paths = [
        "/health",
        "/stats",
        "/atoms",
        "/atoms/com.example.sum",
        "/atoms/com.example.sum/versions",
        "/atoms/com.example.sum/versions/1.0.0",
        "/atoms/com.example.sum/dependencies",
        "/audit",
    ]
    tokens = {"admin": ADMIN_TOKEN}
    for role in ("registry", "viewer", "probe"):
        _insert_db_token(db, f"{role}-tok", role)
        tokens[role] = f"{role}-tok"
    for role, tok in tokens.items():
        for path in get_paths:
            r = client.get(path, headers=_auth(tok))
            assert r.status_code == 200, f"{role} GET {path} -> {r.status_code}"


# ============================================================
# AC-12 14 条路由全部绑定 require_role（P0）
# ============================================================


def test_ac12_all_business_routes_bound(tmp_path, monkeypatch):
    app = create_app(tmp_path / "t.db")
    bound = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.dependencies:
            for method in route.methods:
                bound.add((method, route.path))
    expected = {
        ("GET", "/health"),
        ("GET", "/stats"),
        ("GET", "/atoms"),
        ("POST", "/atoms"),
        ("GET", "/atoms/{atom_id}"),
        ("POST", "/atoms/{atom_id}/review"),
        ("POST", "/atoms/{atom_id}/status"),
        ("POST", "/atoms/{atom_id}/probe"),
        ("POST", "/probe"),
        ("GET", "/atoms/{atom_id}/versions"),
        ("GET", "/atoms/{atom_id}/versions/{version}"),
        ("POST", "/atoms/{atom_id}/rollback/{version}"),
        ("GET", "/atoms/{atom_id}/dependencies"),
        ("GET", "/audit"),
    }
    assert len(expected) == 14
    assert expected <= bound
    # token 管理端点同样绑定（admin）
    assert {
        ("POST", "/api/v1/tokens"),
        ("GET", "/api/v1/tokens"),
        ("DELETE", "/api/v1/tokens/{token_id}"),
    } <= bound


# ============================================================
# AC-13 401/403 写安全审计（P1）
# ============================================================


def test_ac13_auth_events_audited(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    client = _make_client(db, monkeypatch)

    # 一次 401（无 token）
    assert client.get("/atoms").status_code == 401
    # 一次 403（viewer 调写路由）
    _insert_db_token(db, "viewer-tok", "viewer")
    assert (
        client.post(
            "/atoms", json=_atom("com.example.deny"), headers=_auth("viewer-tok")
        ).status_code
        == 403
    )

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM security_audit_log ORDER BY id").fetchall()
    finally:
        conn.close()
    by_result = {row["result"]: row for row in rows}
    assert 401 in by_result
    assert 403 in by_result

    e401 = by_result[401]
    assert e401["subject"]
    assert e401["route"] == "/atoms"
    assert e401["method"] == "GET"
    assert e401["created_at"]

    e403 = by_result[403]
    assert e403["subject"].startswith("api_token:")
    assert e403["route"] == "/atoms"
    assert e403["method"] == "POST"
    assert e403["created_at"]
