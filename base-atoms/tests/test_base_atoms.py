"""基础原子测试：13 个 handler 的功能与安全约束（BASE_ATOMS_SPEC）。

包含从旧 atoms/ 移植的安全回归（原 BUG-007/008/009）。
"""

from __future__ import annotations

import base64
import importlib.util
import os
import socket
from pathlib import Path

import pytest

ATOMS_DIR = Path(__file__).resolve().parents[1]


def _load(atom_dir: str):
    path = ATOMS_DIR / atom_dir / "core.py"
    spec = importlib.util.spec_from_file_location(f"core_{atom_dir}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------- 文件系（沙箱） ----------


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("ATOM_FILE_ROOTS", str(tmp_path))
    return tmp_path


def test_file_read_write_roundtrip(sandbox):
    target = sandbox / "a.txt"
    w = _load("file-write").handler({"path": str(target), "content": "hello"})
    assert w["status"] == "success" and w["data"]["written"] == 5

    r = _load("file-read").handler({"path": str(target)})
    assert r["status"] == "success"
    assert r["data"]["content"] == "hello"


def test_file_read_base64(sandbox):
    target = sandbox / "b.bin"
    target.write_bytes(b"\x01\x02")
    r = _load("file-read").handler({"path": str(target), "mode": "base64"})
    assert r["status"] == "success"
    assert base64.b64decode(r["data"]["content"]) == b"\x01\x02"


def test_file_atoms_reject_outside_sandbox(sandbox):
    outside = "C:/Windows/System32/drivers/etc/hosts"
    for atom in ("file-read", "file-write", "file-dir"):
        core = _load(atom)
        payload = {"path": outside, "content": "x", "action": "list"}
        result = core.handler(payload)
        assert result["status"] == "error", atom
        assert "outside allowed roots" in result["message"]


def test_file_atoms_reject_dotdot(sandbox):
    (sandbox / "secret.txt").write_text("s", encoding="utf-8")
    sub = sandbox / "sub"
    sub.mkdir()
    os.environ["ATOM_FILE_ROOTS"] = str(sub)
    r = _load("file-read").handler({"path": str(sub / ".." / "secret.txt")})
    assert r["status"] == "error"


def test_file_dir_list_create_delete(sandbox):
    core = _load("file-dir")
    assert (
        core.handler({"action": "create", "path": str(sandbox / "d1")})["status"]
        == "success"
    )
    listed = core.handler({"action": "list", "path": str(sandbox)})
    assert listed["status"] == "success"
    assert any(
        e["name"] == "d1" and e["type"] == "dir" for e in listed["data"]["entries"]
    )
    assert (
        core.handler({"action": "delete", "path": str(sandbox / "d1")})["status"]
        == "success"
    )


def test_file_write_append(sandbox):
    core = _load("file-write")
    target = str(sandbox / "c.txt")
    core.handler({"path": target, "content": "ab"})
    core.handler({"path": target, "content": "cd", "append": True})
    assert Path(target).read_text() == "abcd"


# ---------- HTTP 系（SSRF 防护，移植自 BUG-008） ----------


def _fake_dns(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]


@pytest.mark.parametrize("atom", ["http-get", "http-post"])
def test_http_rejects_non_http_scheme(atom):
    result = _load(atom).handler({"url": "file:///etc/passwd"})
    assert result["status"] == "error"
    assert "not allowed" in result["message"]


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "192.168.1.10", "10.0.0.5", "169.254.169.254"]
)
def test_http_get_rejects_internal_ip(monkeypatch, ip):
    monkeypatch.delenv("ATOM_HTTP_ALLOW_PRIVATE", raising=False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: _fake_dns(ip))
    result = _load("http-get").handler({"url": f"http://{ip}/x"})
    assert result["status"] == "error"
    assert "internal address" in result["message"]


def test_http_get_allows_public(monkeypatch):
    monkeypatch.delenv("ATOM_HTTP_ALLOW_PRIVATE", raising=False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: _fake_dns("93.184.216.34"))

    class _Resp:
        status_code = 200
        headers = {}
        text = "ok-body"

    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    result = _load("http-get").handler({"url": "http://example.com"})
    assert result["status"] == "success"
    assert result["data"]["body"] == "ok-body"


def test_http_post_sends_json(monkeypatch):
    monkeypatch.setenv("ATOM_HTTP_ALLOW_PRIVATE", "1")
    captured = {}

    class _Resp:
        status_code = 201
        headers = {}
        text = "{}"

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return _Resp()

    monkeypatch.setattr("requests.post", fake_post)
    result = _load("http-post").handler(
        {"url": "http://127.0.0.1:9/x", "body": {"a": 1}}
    )
    assert result["status"] == "success"
    assert captured["json"] == {"a": 1}


# ---------- 计算系 ----------


def test_math_calc_basic():
    core = _load("math-calc")
    assert core.handler({"expression": "2 + 3 * 4"})["data"]["result"] == 14
    assert core.handler({"expression": "sqrt(16) + abs(-2)"})["data"]["result"] == 6.0
    assert core.handler({"expression": "1/3", "precision": 2})["data"]["result"] == 0.33


def test_math_calc_rejects_injection():
    core = _load("math-calc")
    for bad in ("__import__('os')", "open('/etc/passwd')", "x = 1", "1; 2"):
        assert core.handler({"expression": bad})["status"] == "error", bad


def test_string_split():
    core = _load("string-split")
    r = core.handler({"text": "a,b,c", "delimiter": ","})
    assert r["data"] == {"parts": ["a", "b", "c"], "count": 3}
    r = core.handler({"text": "a,b,c", "delimiter": ",", "maxsplit": 1})
    assert r["data"]["parts"] == ["a", "b,c"]


def test_string_match():
    core = _load("string-match")
    r = core.handler({"text": "hello world", "pattern": r"\w+"})
    assert r["data"] == {"matches": ["hello", "world"], "count": 2}
    r = core.handler({"text": "Hello", "pattern": "hello", "flags": "i"})
    assert r["data"]["count"] == 1


def test_json_parse():
    core = _load("json-parse")
    assert core.handler({"text": '{"key": "value"}'})["data"]["data"] == {
        "key": "value"
    }
    assert core.handler({"text": "not json"})["status"] == "error"


def test_date_time():
    core = _load("date-time")
    assert core.handler({"action": "now"})["status"] == "success"
    r = core.handler(
        {"action": "format", "value": "2026-07-18T10:00:00Z", "format": "%Y-%m-%d"}
    )
    assert r["data"]["result"] == "2026-07-18"
    r = core.handler(
        {
            "action": "diff",
            "value": "2026-07-18T00:00:00Z",
            "value2": "2026-07-19T00:00:00Z",
        }
    )
    assert r["data"]["result"] == 86400.0


def test_hash_digest():
    core = _load("hash-digest")
    r = core.handler({"text": "", "algorithm": "sha256"})
    assert r["data"]["digest"].startswith("e3b0c442")
    assert core.handler({"text": "x", "algorithm": "sha1"})["status"] == "error"


# ---------- AES 系 ----------


def test_aes_roundtrip():
    key = base64.b64encode(os.urandom(32)).decode()
    enc = _load("encrypt-aes").handler({"text": "机密内容", "key": key})
    assert enc["status"] == "success"
    dec = _load("decrypt-aes").handler(
        {
            "ciphertext": enc["data"]["ciphertext"],
            "iv": enc["data"]["iv"],
            "key": key,
        }
    )
    assert dec["status"] == "success"
    assert dec["data"]["text"] == "机密内容"


def test_aes_tampered_ciphertext_fails():
    key = base64.b64encode(os.urandom(32)).decode()
    enc = _load("encrypt-aes").handler({"text": "data", "key": key})
    raw = bytearray(base64.b64decode(enc["data"]["ciphertext"]))
    raw[0] ^= 0xFF  # GCM 认证必须发现篡改
    dec = _load("decrypt-aes").handler(
        {
            "ciphertext": base64.b64encode(bytes(raw)).decode(),
            "iv": enc["data"]["iv"],
            "key": key,
        }
    )
    assert dec["status"] == "error"


def test_aes_key_from_env(monkeypatch):
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("ATOM_AES_KEY", key)
    enc = _load("encrypt-aes").handler({"text": "env-key"})
    assert enc["status"] == "success"


def test_aes_rejects_bad_key():
    bad = base64.b64encode(b"short").decode()
    assert _load("encrypt-aes").handler({"text": "x", "key": bad})["status"] == "error"


# ---------- 服务层（移植自 BUG-009） ----------


def test_servers_bind_loopback_by_default():
    for server in ATOMS_DIR.glob("*/server.py"):
        content = server.read_text(encoding="utf-8")
        assert 'HOST", "127.0.0.1"' in content, server
        assert "0.0.0.0" not in content.split("Dockerfile")[0], server


def test_all_atoms_meta_complete():
    """每个原子的 META 都带 id/name/author/builtin（REGISTERED_ATOM_RULES）。"""
    for server in sorted(ATOMS_DIR.glob("*/server.py")):
        if server.parent.name == "tests":
            continue
        spec = importlib.util.spec_from_file_location(
            f"server_{server.parent.name}", server
        )
        module = importlib.util.module_from_spec(spec)
        import sys as _sys

        _sys.path.insert(0, str(server.parent.resolve()))
        try:
            spec.loader.exec_module(module)
        finally:
            _sys.path.pop(0)
        meta = module.META
        assert meta["id"].startswith("system.")
        assert meta["author"] == "system"
        assert meta["builtin"] is True
        assert meta["name"]
