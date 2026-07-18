"""Tests for registry.probe_atom / probe_atoms (HTTP layer is stubbed)."""

from __future__ import annotations

import sqlite3
import urllib.error

import pytest
import registry
from registry import (
    ensure_registry_schema,
    get_atom,
    probe_atom,
    probe_atoms,
    review_atom,
    submit_atom,
)


def _atom(atom_id="com.example.probe", runtime=None):
    if runtime is None:
        runtime = {
            "endpoint": "http://127.0.0.1:9000/x",
            "health_url": "http://127.0.0.1:9000/x/health",
        }
    return {
        "atom_id": atom_id,
        "name": "Probe",
        "version": "1.0.0",
        "description": "probe target",
        "purpose": {"functions": [{"name": "ping"}]},
        "architecture": {"type": "python_script", "runtime": "python3.12"},
        "ownership": {"author": "test", "license": "MIT"},
        "runtime": runtime,
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_registry_schema(c)
    yield c
    c.close()


def _register(conn, atom_id="com.example.probe", runtime=None, status="registered"):
    submit_atom(conn, _atom(atom_id, runtime))
    review_atom(conn, atom_id, approved=True)
    if status != "registered":
        registry.set_atom_status(conn, atom_id, status)


class _FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _stub_urlopen(monkeypatch, behavior):
    def fake_urlopen(url, timeout=None):
        if isinstance(behavior, Exception):
            raise behavior
        return behavior(url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


def test_probe_ok_marks_running(conn, monkeypatch):
    _register(conn)
    _stub_urlopen(monkeypatch, lambda url: _FakeResponse(200))

    result = probe_atom(conn, "com.example.probe")
    assert result["success"] and result["ok"]
    assert result["new_status"] == "running"
    assert result["probe_status"] == "ok"

    atom = get_atom(conn, "com.example.probe")
    assert atom["lifecycle"]["status"] == "running"
    assert atom["runtime"]["last_probe_status"] == "ok"
    assert atom["runtime"]["consecutive_failures"] == 0
    assert atom["runtime"]["last_probe_latency_ms"] >= 0


def test_probe_http_500_marks_unreachable(conn, monkeypatch):
    _register(conn)
    err = urllib.error.HTTPError(
        "http://x/health", 500, "Server Error", hdrs=None, fp=None
    )
    _stub_urlopen(monkeypatch, err)

    result = probe_atom(conn, "com.example.probe")
    assert result["success"] and not result["ok"]
    assert result["new_status"] == "unreachable"
    assert result["probe_status"] == "http_500"


def test_probe_connection_error_marks_unreachable(conn, monkeypatch):
    _register(conn)
    _stub_urlopen(monkeypatch, urllib.error.URLError("connection refused"))

    result = probe_atom(conn, "com.example.probe")
    assert result["success"] and not result["ok"]
    assert result["probe_status"] == "connection_error"
    assert "connection refused" in str(
        conn.execute(
            "SELECT detail FROM atom_audit_log WHERE action='probe'"
        ).fetchone()[0]
    )


def test_probe_increments_consecutive_failures(conn, monkeypatch):
    _register(conn)
    _stub_urlopen(monkeypatch, urllib.error.URLError("down"))
    probe_atom(conn, "com.example.probe")
    probe_atom(conn, "com.example.probe")

    atom = get_atom(conn, "com.example.probe")
    assert atom["runtime"]["consecutive_failures"] == 2

    _stub_urlopen(monkeypatch, lambda url: _FakeResponse(200))
    probe_atom(conn, "com.example.probe")
    atom = get_atom(conn, "com.example.probe")
    assert atom["runtime"]["consecutive_failures"] == 0


def test_probe_deprecated_keeps_status_but_records(conn, monkeypatch):
    _register(conn, status="offline")
    registry.set_atom_status(conn, "com.example.probe", "deprecated")
    _stub_urlopen(monkeypatch, lambda url: _FakeResponse(200))

    result = probe_atom(conn, "com.example.probe")
    assert result["ok"]
    assert result["new_status"] == "deprecated"  # 不被探测改写

    atom = get_atom(conn, "com.example.probe")
    assert atom["runtime"]["last_probe_status"] == "ok"


def test_probe_not_found(conn):
    result = probe_atom(conn, "com.example.missing")
    assert not result["success"]
    assert result["error"] == "not_found"


def test_probe_no_endpoint(conn):
    _register(conn, runtime={})
    result = probe_atom(conn, "com.example.probe")
    assert not result["success"]
    assert result["error"] == "no_endpoint"


def test_probe_atoms_batch(conn, monkeypatch):
    _register(conn, "com.example.a")
    _register(conn, "com.example.b")
    _stub_urlopen(monkeypatch, lambda url: _FakeResponse(200))

    results = probe_atoms(conn)
    assert len(results) == 2
    assert all(r["ok"] for r in results)

    results = probe_atoms(conn, atom_ids=["com.example.a"])
    assert len(results) == 1
    assert results[0]["atom_id"] == "com.example.a"


def test_probe_falls_back_to_endpoint(conn, monkeypatch):
    _register(conn, runtime={"endpoint": "http://127.0.0.1:9000/x"})
    seen = []

    def fake(url):
        seen.append(url)
        return _FakeResponse(200)

    _stub_urlopen(monkeypatch, fake)
    probe_atom(conn, "com.example.probe")
    assert seen == ["http://127.0.0.1:9000/x"]
