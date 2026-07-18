"""Regression tests for BUG-037: 401/403 auth failures must be audited.

Before the fix, ``auth.py`` raised 401 (Missing/Invalid token) and 403
(require_role) without recording anything. The fix adds the
``security_audit_log`` table (migration 014) and writes one row per
rejected request: subject, route, method, result, created_at.
"""

from __future__ import annotations

import sqlite3

import pytest
from api import create_app
from auth import create_token
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


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("YUANZI_API_TOKEN", raising=False)
    db = tmp_path / "sec-audit.db"
    conn = sqlite3.connect(str(db))
    migrate(conn)
    create_token(conn, ADMIN_TOKEN, role="admin")
    create_token(conn, VIEWER_TOKEN, role="viewer")
    conn.close()
    with TestClient(create_app(db)) as c:
        yield c, str(db)


def _events(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT subject, route, method, result, created_at "
        "FROM security_audit_log ORDER BY id"
    ).fetchall()
    conn.close()
    return [
        {
            "subject": r[0],
            "route": r[1],
            "method": r[2],
            "result": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


def test_missing_token_401_is_audited(env):
    client, db = env
    assert client.get("/atoms").status_code == 401
    events = _events(db)
    assert len(events) == 1
    e = events[0]
    assert e["subject"] == "anonymous"
    assert e["route"] == "/atoms"
    assert e["method"] == "GET"
    assert "401" in e["result"]
    assert e["created_at"]


def test_invalid_token_401_is_audited(env):
    client, db = env
    r = client.get("/stats", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    events = _events(db)
    assert len(events) == 1
    assert events[0]["subject"] == "anonymous"
    assert events[0]["route"] == "/stats"
    assert "401" in events[0]["result"]


def test_forbidden_role_403_is_audited(env):
    client, db = env
    r = client.post(
        "/atoms",
        json=_atom(),
        headers={"Authorization": f"Bearer {VIEWER_TOKEN}"},
    )
    assert r.status_code == 403
    events = _events(db)
    assert len(events) == 1
    e = events[0]
    assert e["subject"].startswith("token-")  # 已识别主体，记录 token-{id}
    assert e["route"] == "/atoms"
    assert e["method"] == "POST"
    assert "403" in e["result"]
    assert e["created_at"]


def test_allowed_requests_are_not_audited(env):
    client, db = env
    assert (
        client.get("/atoms", headers={"Authorization": f"Bearer {VIEWER_TOKEN}"}).status_code
        == 200
    )
    assert _events(db) == []


def test_audit_verify_reports_security_event_count(env):
    client, db = env
    client.get("/atoms")  # 401 → 1 security event
    r = client.get("/audit/verify", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
    assert r.status_code == 200
    assert r.json()["security_audit_events"] == 1
