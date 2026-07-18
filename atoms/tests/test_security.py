"""Security regression tests for atoms (BUG-005/007/008/009)."""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import pytest

ATOMS_DIR = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def file_read():
    return _load_module("file_read_core", ATOMS_DIR / "atom-file-read" / "core.py")


@pytest.fixture()
def http_get():
    return _load_module("http_get_core", ATOMS_DIR / "atom-http-get" / "core.py")


# ---------- BUG-007：file-read 沙箱 ----------


def test_file_read_allows_whitelisted_root(file_read, tmp_path, monkeypatch):
    monkeypatch.setenv("ATOM_FILE_READ_ROOTS", str(tmp_path))
    target = tmp_path / "ok.txt"
    target.write_text("hello", encoding="utf-8")

    result = file_read.handler({"path": str(target)})
    assert result["status"] == "success"
    assert result["data"]["content"] == "hello"


def test_file_read_rejects_outside_path(file_read, tmp_path, monkeypatch):
    monkeypatch.setenv("ATOM_FILE_READ_ROOTS", str(tmp_path))
    result = file_read.handler({"path": "C:/Windows/System32/drivers/etc/hosts"})
    assert result["status"] == "error"
    assert "outside allowed roots" in result["message"]


def test_file_read_rejects_dotdot_traversal(file_read, tmp_path, monkeypatch):
    allowed = tmp_path / "sandbox"
    allowed.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    monkeypatch.setenv("ATOM_FILE_READ_ROOTS", str(allowed))

    result = file_read.handler({"path": str(allowed / ".." / "secret.txt")})
    assert result["status"] == "error"
    assert "outside allowed roots" in result["message"]


# ---------- BUG-008：http-get SSRF ----------


def _fake_getaddrinfo(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]


def test_http_get_rejects_non_http_scheme(http_get):
    result = http_get.handler({"url": "file:///C:/Windows/win.ini"})
    assert result["status"] == "error"
    assert "not allowed" in result["message"]


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "192.168.1.10", "10.0.0.5", "169.254.169.254"]
)
def test_http_get_rejects_internal_addresses(http_get, monkeypatch, ip):
    monkeypatch.delenv("ATOM_HTTP_GET_ALLOW_PRIVATE", raising=False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: _fake_getaddrinfo(ip))
    result = http_get.handler({"url": f"http://{ip}/internal"})
    assert result["status"] == "error"
    assert "internal address" in result["message"]


def test_http_get_allows_public_address(http_get, monkeypatch):
    monkeypatch.delenv("ATOM_HTTP_GET_ALLOW_PRIVATE", raising=False)
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port: _fake_getaddrinfo("93.184.216.34")
    )

    class _Resp:
        status_code = 200
        url = "http://example.com"
        headers = {}
        text = "ok"
        encoding = "utf-8"

    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    result = http_get.handler({"url": "http://example.com/data"})
    assert result["status"] == "success"
    assert result["data"]["status_code"] == 200


def test_http_get_private_override(http_get, monkeypatch):
    monkeypatch.setenv("ATOM_HTTP_GET_ALLOW_PRIVATE", "1")

    class _Resp:
        status_code = 200
        url = "http://127.0.0.1:9"
        headers = {}
        text = "local"
        encoding = "utf-8"

    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    result = http_get.handler({"url": "http://127.0.0.1:9/health"})
    assert result["status"] == "success"


# ---------- BUG-009：token 鉴权与默认绑定 ----------


def test_server_binds_loopback_by_default():
    for server in ATOMS_DIR.glob("atom-*/server.py"):
        content = server.read_text(encoding="utf-8")
        assert 'HOST", "127.0.0.1"' in content, server
        assert "0.0.0.0" not in content, server


def test_server_token_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("YUANZI_TOKEN", "s3cret")
    monkeypatch.chdir(tmp_path)
    # server.py 以 `import core` 导入同目录内核
    monkeypatch.syspath_prepend(str(ATOMS_DIR / "atom-template"))
    server = _load_module("template_server", ATOMS_DIR / "atom-template" / "server.py")
    client = server.app.test_client()

    assert client.get("/health").status_code == 200  # health 不需要 token

    denied = client.post("/run", json={})
    assert denied.status_code == 401

    allowed = client.post("/run", json={}, headers={"Yuanzi-Token": "s3cret"})
    assert allowed.status_code == 200
