"""Regression tests for BUG-036: env-token comparison must be constant-time.

``credentials.credentials == env_token`` leaks timing information; the fix
uses ``secrets.compare_digest``. These tests pin both the behavior
(env token accepted / near-miss rejected) and the implementation.
"""

from __future__ import annotations

import inspect
import sqlite3

import auth
from api import create_app
from auth import create_token
from fastapi.testclient import TestClient
from migrations import migrate

ENV_TOKEN = "env-secret-token"


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("YUANZI_API_TOKEN", ENV_TOKEN)
    db = tmp_path / "timing.db"
    conn = sqlite3.connect(str(db))
    migrate(conn)
    create_token(conn, "viewer-only", role="viewer")  # avoid dev mode
    conn.close()
    return TestClient(create_app(db))


def test_env_token_comparison_uses_compare_digest():
    """auth.py must compare the env token with secrets.compare_digest."""
    src = inspect.getsource(auth)
    assert "secrets.compare_digest" in src
    assert "credentials.credentials == env_token" not in src


def test_env_token_accepted(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.get("/atoms", headers={"Authorization": f"Bearer {ENV_TOKEN}"})
        assert r.status_code == 200


def test_env_token_near_miss_rejected(tmp_path, monkeypatch):
    """Same-prefix / same-length tokens must still be rejected."""
    with _client(tmp_path, monkeypatch) as c:
        for bad in (ENV_TOKEN[:-1] + "X", ENV_TOKEN + "x", ENV_TOKEN[:-1]):
            r = c.get("/atoms", headers={"Authorization": f"Bearer {bad}"})
            assert r.status_code == 401, bad
