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
        "purpose": {"functions": [{"name": f"ping_{atom_id}"}]},
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


# ---------- BUG-014/017/018/019/020/021/022 回归 ----------


def test_probe_invalid_scheme_no_crash(conn):
    """BUG-014/020：file:// 不崩溃、不发请求、记 invalid_url。"""
    _register(conn, runtime={"health_url": "file:///C:/Windows/win.ini"})
    result = probe_atom(conn, "com.example.probe")
    assert not result["success"]
    assert result["error"] == "invalid_url"
    assert result["new_status"] == "registered"  # 生命周期不被非法 URL 改写

    atom = get_atom(conn, "com.example.probe")
    assert atom["runtime"]["last_probe_status"] == "invalid_url"


def test_probe_batch_isolates_bad_atoms(conn):
    """BUG-014：一个坏原子不中断批量探测。"""
    _register(conn, "com.example.a", runtime={"health_url": "file:///etc/passwd"})
    _register(conn, "com.example.b")

    def fake(url, timeout=None):
        class R:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return R()

    import registry as reg

    orig = reg.urllib.request.urlopen
    reg.urllib.request.urlopen = fake
    try:
        results = probe_atoms(conn)
    finally:
        reg.urllib.request.urlopen = orig

    by_id = {r["atom_id"]: r for r in results}
    assert by_id["com.example.a"]["error"] == "invalid_url"
    assert by_id["com.example.b"]["ok"]


def test_probe_crash_leaves_probing_marker(conn, monkeypatch):
    """BUG-017：探测中途崩溃，原子停留在 probing 可识别。"""
    _register(conn)

    def boom(url, timeout=None):
        raise RuntimeError("unexpected explosion")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    results = probe_atoms(conn)  # 批量层隔离异常
    assert results[0]["error"] == "probe_exception"

    atom = get_atom(conn, "com.example.probe")
    assert atom["lifecycle"]["status"] == "probing"


def test_probe_audit_throttled_when_nothing_changes(conn, monkeypatch):
    """BUG-022：状态与探测结果不变时不重复记审计。"""
    _register(conn)
    _stub_urlopen(monkeypatch, urllib.error.URLError("down"))
    probe_atom(conn, "com.example.probe")  # registered -> unreachable，记一条
    probe_atom(conn, "com.example.probe")  # unreachable -> unreachable，不记
    probe_atom(conn, "com.example.probe")  # 同上，不记

    rows = conn.execute(
        "SELECT COUNT(*) FROM atom_audit_log WHERE action='probe'"
    ).fetchone()
    assert rows[0] == 1


def test_probe_no_endpoint_writes_audit(conn):
    """BUG-018：no_endpoint 也记一条探测审计。"""
    _register(conn, runtime={})
    probe_atom(conn, "com.example.probe")
    row = conn.execute(
        "SELECT detail FROM atom_audit_log WHERE action='probe'"
    ).fetchone()
    assert row is not None
    assert "no_endpoint" in row[0]

    # 第二次 no_endpoint 不重复记（节流）
    probe_atom(conn, "com.example.probe")
    count = conn.execute(
        "SELECT COUNT(*) FROM atom_audit_log WHERE action='probe'"
    ).fetchone()[0]
    assert count == 1


def test_probe_offline_to_unreachable_allowed(conn, monkeypatch):
    """BUG-019：offline -> unreachable 是流转表内的合法转换。"""
    _register(conn, status="offline")
    _stub_urlopen(monkeypatch, urllib.error.URLError("down"))
    result = probe_atom(conn, "com.example.probe")
    assert result["new_status"] == "unreachable"


def test_probe_status_change_records_audit(conn, monkeypatch):
    """BUG-017 两阶段：probing 不出现在审计里，old/new 是真实状态。"""
    _register(conn)
    _stub_urlopen(monkeypatch, lambda url: _FakeResponse(200))
    probe_atom(conn, "com.example.probe")
    row = conn.execute(
        "SELECT old_status, new_status FROM atom_audit_log WHERE action='probe'"
    ).fetchone()
    assert tuple(row) == ("registered", "running")


# ---------- M6.5b：probe CIDR 限制（裁决 2026-07-18-01） ----------


def _fake_dns(ip):
    import socket as _socket

    return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (ip, 0))]


def test_probe_blocks_non_loopback_by_default(conn, monkeypatch):
    """默认仅允许 127.0.0.0/8：私网地址被拒，不发请求。"""
    import socket as _socket

    monkeypatch.setattr(_socket, "getaddrinfo", lambda h, p: _fake_dns("192.168.1.50"))
    monkeypatch.delenv("YUANZI_PROBE_ALLOWED_CIDR", raising=False)
    _register(conn, runtime={"health_url": "http://internal.local/health"})

    result = probe_atom(conn, "com.example.probe")
    assert not result["success"]
    assert result["error"] == "blocked_address"
    assert result["new_status"] == "registered"  # 生命周期不改写

    atom = get_atom(conn, "com.example.probe")
    assert atom["runtime"]["last_probe_status"] == "blocked_address"


def test_probe_loopback_allowed_by_default(conn, monkeypatch):
    """回环地址默认放行。"""
    import socket as _socket

    monkeypatch.setattr(_socket, "getaddrinfo", lambda h, p: _fake_dns("127.0.0.1"))
    monkeypatch.delenv("YUANZI_PROBE_ALLOWED_CIDR", raising=False)
    _register(conn)
    _stub_urlopen(monkeypatch, lambda url: _FakeResponse(200))

    result = probe_atom(conn, "com.example.probe")
    assert result["ok"]


def test_probe_cidr_env_override(conn, monkeypatch):
    """YUANZI_PROBE_ALLOWED_CIDR 可追加放行网段。"""
    import socket as _socket

    monkeypatch.setattr(_socket, "getaddrinfo", lambda h, p: _fake_dns("192.168.1.50"))
    monkeypatch.setenv("YUANZI_PROBE_ALLOWED_CIDR", "127.0.0.0/8,192.168.1.0/24")
    _register(conn)
    _stub_urlopen(monkeypatch, lambda url: _FakeResponse(200))

    result = probe_atom(conn, "com.example.probe")
    assert result["ok"]


def test_probe_unresolvable_host_blocked(conn, monkeypatch):
    """DNS 解析失败按 blocked_address 处理（不发请求）。"""
    import socket as _socket

    def _raise(host, port):
        raise _socket.gaierror("nxdomain")

    monkeypatch.setattr(_socket, "getaddrinfo", _raise)
    _register(conn, runtime={"health_url": "http://no-such-host.invalid/health"})

    result = probe_atom(conn, "com.example.probe")
    assert result["error"] == "blocked_address"
    assert "cannot resolve" in result["message"]
