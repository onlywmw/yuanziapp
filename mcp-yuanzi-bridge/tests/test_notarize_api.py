"""区块链公证：注册流程接入 + 验证接口集成测试（DESIGN_BLOCKCHAIN_NOTARY §二/§五/§六）。

notarize 模块由并行代理实现；未落盘时整个模块跳过（importorskip），
待该代理完成后复跑即转活。测试统一用 YUANZI_NOTARIZE_SYNC=1 走同步公证保证确定性。
"""

from __future__ import annotations

import sqlite3

import pytest

notarize = pytest.importorskip("notarize")  # noqa: F841 - 仅作落盘守卫

from api import create_app
from auth import ACTION_AUTHZ_DENIED, SECURITY_ATOM_ID, create_token
from fastapi.testclient import TestClient
from migrations import migrate

ADMIN_TOKEN = "admin-secret"
VIEWER_TOKEN = "viewer-secret"


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _atom(atom_id, category=None):
    """最小合法原子；category 为 None 时不带 classification 字段。"""
    atom = {
        "atom_id": atom_id,
        "name": atom_id,
        "version": "1.0.0",
        "description": "",
        "purpose": {"functions": [{"name": f"f_{atom_id}"}]},
        "architecture": {"type": "t", "runtime": "r", "dependencies": []},
        "ownership": {"author": "张三", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }
    if category is not None:
        atom["classification"] = {"category": category}
    return atom


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("YUANZI_API_TOKEN", raising=False)
    monkeypatch.setenv("YUANZI_NOTARIZE_SYNC", "1")  # 同步公证，测试确定性
    db = tmp_path / "notarize.db"
    conn = sqlite3.connect(str(db))
    migrate(conn)
    create_token(conn, ADMIN_TOKEN, role="admin")
    create_token(conn, VIEWER_TOKEN, role="viewer")
    conn.close()
    with TestClient(create_app(db)) as c:
        yield c


def _submit(client, atom_id, category=None):
    r = client.post("/atoms", json=_atom(atom_id, category), headers=_h(ADMIN_TOKEN))
    assert r.status_code == 201, r.text


def _review(client, atom_id, approved=True):
    r = client.post(
        f"/atoms/{atom_id}/review",
        json={"approved": approved, "reviewer": "admin-reviewer"},
        headers=_h(ADMIN_TOKEN),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _submit_and_approve(client, atom_id, category=None):
    _submit(client, atom_id, category)
    result = _review(client, atom_id, approved=True)
    assert result["status"] == "registered"


def _get_atom(client, atom_id):
    r = client.get(f"/atoms/{atom_id}", headers=_h(VIEWER_TOKEN))
    assert r.status_code == 200, r.text
    return r.json()


# ---------- 注册流程接入：审核通过后的公证钩子 ----------


def test_approve_asset_atom_writes_blockchain_runtime(client):
    """资产类原子审核通过后（同步模式）runtime_json.blockchain 落账。"""
    _submit_and_approve(client, "com.example.asset-a", "asset")
    atom = _get_atom(client, "com.example.asset-a")
    chain = atom["runtime"].get("blockchain")
    assert chain is not None
    assert chain.get("tx_hash")
    assert chain.get("network")
    assert chain.get("notarized_at")


def test_approve_non_asset_atom_skips_notarize(client):
    """非资产类（tool）与无 classification 的原子不触发公证。"""
    _submit_and_approve(client, "com.example.tool-a", "tool")
    assert "blockchain" not in _get_atom(client, "com.example.tool-a").get("runtime", {})

    _submit_and_approve(client, "com.example.noclass-a", None)
    assert "blockchain" not in _get_atom(client, "com.example.noclass-a").get(
        "runtime", {}
    )


def test_rejected_asset_atom_not_notarized(client):
    """审核拒绝（rejected）不触发公证。"""
    _submit(client, "com.example.asset-rej", "asset")
    result = _review(client, "com.example.asset-rej", approved=False)
    assert result["status"] == "rejected"
    assert "blockchain" not in _get_atom(client, "com.example.asset-rej").get(
        "runtime", {}
    )


# ---------- GET /atoms/{atom_id}/verify ----------


def test_verify_unnotarized_atom_returns_full_structure(client):
    """未公证原子返回 verified:false 且结构完整（文档 §六）。"""
    _submit_and_approve(client, "com.example.tool-b", "tool")
    r = client.get("/atoms/com.example.tool-b/verify", headers=_h(VIEWER_TOKEN))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is False
    for key in ("blockchain", "tx_hash", "confirmed_at", "data_matches"):
        assert key in body


def test_verify_notarized_asset(client):
    """已公证资产验证通过，tx_hash 与 runtime 落账一致。"""
    _submit_and_approve(client, "com.example.asset-b", "asset")
    r = client.get("/atoms/com.example.asset-b/verify", headers=_h(VIEWER_TOKEN))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is True
    assert body["data_matches"] is True
    chain = _get_atom(client, "com.example.asset-b")["runtime"]["blockchain"]
    assert body["tx_hash"] == chain["tx_hash"]


def test_verify_unknown_atom_404(client):
    r = client.get("/atoms/com.example.missing/verify", headers=_h(VIEWER_TOKEN))
    assert r.status_code == 404


def test_verify_requires_auth(client):
    """viewer 可读，但无凭证 401（require_role 绑定生效）。"""
    _submit_and_approve(client, "com.example.tool-c", "tool")
    assert client.get("/atoms/com.example.tool-c/verify").status_code == 401


# ---------- POST /atoms/{atom_id}/notarize ----------


def test_post_notarize_viewer_403_and_security_audit(client):
    """viewer 调手动公证 403，且 403 落安全审计（BUG-037 文化）。"""
    _submit_and_approve(client, "com.example.asset-c", "asset")
    r = client.post(
        "/atoms/com.example.asset-c/notarize",
        json={"action": "transfer"},
        headers=_h(VIEWER_TOKEN),
    )
    assert r.status_code == 403
    r = client.get(
        "/audit", params={"atom_id": SECURITY_ATOM_ID}, headers=_h(ADMIN_TOKEN)
    )
    assert r.status_code == 200
    assert any(e["action"] == ACTION_AUTHZ_DENIED for e in r.json())


def test_post_notarize_requires_auth(client):
    _submit_and_approve(client, "com.example.asset-d", "asset")
    r = client.post(
        "/atoms/com.example.asset-d/notarize", json={"action": "transfer"}
    )
    assert r.status_code == 401


def test_post_notarize_four_actions_flow(client):
    """register（审核钩子）→ transfer → version → deprecate 全流转；重复 register 防重放。"""
    _submit_and_approve(client, "com.example.asset-e", "asset")
    # 审核钩子已完成 register；手动补登同 action 必须 skipped（防重放）
    r = client.post(
        "/atoms/com.example.asset-e/notarize",
        json={"action": "register"},
        headers=_h(ADMIN_TOKEN),
    )
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] is True

    for action in ("transfer", "version", "deprecate"):
        r = client.post(
            "/atoms/com.example.asset-e/notarize",
            json={"action": action},
            headers=_h(ADMIN_TOKEN),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["skipped"] is False
        assert body["tx_hash"]
        assert body["network"]
        assert body["notarized_at"]


def test_replay_register_skipped(client):
    """非资产原子手动补登 register：首次成功，重复 skipped。"""
    _submit_and_approve(client, "com.example.tool-d", "tool")
    r = client.post(
        "/atoms/com.example.tool-d/notarize",
        json={"action": "register"},
        headers=_h(ADMIN_TOKEN),
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["skipped"] is False

    r = client.post(
        "/atoms/com.example.tool-d/notarize",
        json={"action": "register"},
        headers=_h(ADMIN_TOKEN),
    )
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] is True


def test_post_notarize_invalid_action_400(client):
    _submit_and_approve(client, "com.example.tool-e", "tool")
    r = client.post(
        "/atoms/com.example.tool-e/notarize",
        json={"action": "bogus"},
        headers=_h(ADMIN_TOKEN),
    )
    assert r.status_code == 400


def test_post_notarize_unknown_atom_404(client):
    r = client.post(
        "/atoms/com.example.missing/notarize",
        json={"action": "register"},
        headers=_h(ADMIN_TOKEN),
    )
    assert r.status_code == 404
