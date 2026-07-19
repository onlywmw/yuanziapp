"""区块链公证核心模块测试（notarize.py）。

全部离线：LocalLedger 落临时账本文件（tmp_path），不触网；
ArweaveProvider 只测可用性判定，不发起任何请求。
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from migrations import migrate
from registry import AUDIT_TABLE, REGISTRY_TABLE, get_atom, submit_atom

import notarize
from notarize import (
    ArweaveProvider,
    LocalLedgerProvider,
    build_notary_payload,
    get_provider,
    notarize_atom,
    verify_notarization,
)

AUTHOR = "张三"


def _atom(atom_id="com.zhangsan.premium-music", author=AUTHOR):
    return {
        "atom_id": atom_id,
        "name": atom_id,
        "version": "1.0.0",
        "description": "",
        "purpose": {"functions": [{"name": "play", "description": "play music"}]},
        "architecture": {"type": "python_script", "runtime": "python3.12"},
        "ownership": {"author": author, "license": "MIT"},
        "classification": {"category": "asset"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    """内存库 + 临时账本文件，强制 local provider，屏蔽 Arweave 环境。"""
    monkeypatch.setenv("NOTARY_PROVIDER", "local")
    monkeypatch.setenv("NOTARY_LEDGER_PATH", str(tmp_path / "notary_ledger.jsonl"))
    monkeypatch.delenv("ARWEAVE_JWK", raising=False)
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def _register_atom(conn, atom_id="com.zhangsan.premium-music"):
    result = submit_atom(conn, _atom(atom_id), actor="tester")
    assert result["success"] is True
    return get_atom(conn, atom_id)


# ---------------------------------------------------------------- payload


def test_build_payload_fields_exact(conn):
    atom = _register_atom(conn)
    payload = build_notary_payload(atom, "register", actor="tester")
    # 严格按文档§四：七个字段，不多不少
    assert set(payload.keys()) == {
        "version",
        "atom_id",
        "signature_hash",
        "author",
        "timestamp",
        "action",
        "metadata_uri",
    }
    assert payload["version"] == 1
    assert payload["atom_id"] == "com.zhangsan.premium-music"
    assert payload["signature_hash"] == atom["signature_hash"]
    assert payload["author"] == AUTHOR
    assert payload["action"] == "register"
    assert payload["metadata_uri"] == (
        "https://yuanzi.app/atoms/com.zhangsan.premium-music"
    )
    assert payload["timestamp"].endswith("+00:00")  # ISO UTC


@pytest.mark.parametrize("action", ["register", "transfer", "version", "deprecate"])
def test_build_payload_all_actions(conn, action):
    atom = _register_atom(conn)
    payload = build_notary_payload(atom, action)
    assert payload["action"] == action


def test_build_payload_invalid_action(conn):
    atom = _register_atom(conn)
    with pytest.raises(ValueError):
        build_notary_payload(atom, "burn")


# ------------------------------------------------------------ notarize


def test_notarize_register_success(conn):
    _register_atom(conn)
    result = notarize_atom(
        conn, "com.zhangsan.premium-music", action="register", actor="tester"
    )
    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["network"] == "local"
    assert len(result["tx_hash"]) == 64
    int(result["tx_hash"], 16)  # 十六进制 sha256
    assert result["payload"]["action"] == "register"
    assert result["notarized_at"]

    # runtime_json.blockchain 按文档§七写入，blockchain_txs 追加完整记录
    atom = get_atom(conn, "com.zhangsan.premium-music")
    blockchain = atom["runtime"]["blockchain"]
    assert blockchain["network"] == "local"
    assert blockchain["tx_hash"] == result["tx_hash"]
    assert blockchain["notarized_at"] == result["notarized_at"]
    assert blockchain["verified"] is True
    txs = atom["runtime"]["blockchain_txs"]
    assert len(txs) == 1
    assert txs[0]["action"] == "register"
    assert txs[0]["actor"] == "tester"
    assert txs[0]["tx_hash"] == result["tx_hash"]
    assert txs[0]["payload"] == result["payload"]


def test_notarize_register_replay_skipped(conn):
    _register_atom(conn)
    first = notarize_atom(conn, "com.zhangsan.premium-music", action="register")
    second = notarize_atom(conn, "com.zhangsan.premium-music", action="register")
    assert second["ok"] is True
    assert second["skipped"] is True
    assert second["reason"] == "already_notarized"
    assert second["tx_hash"] == first["tx_hash"]  # 复用旧交易，不产生新交易
    atom = get_atom(conn, "com.zhangsan.premium-music")
    assert len(atom["runtime"]["blockchain_txs"]) == 1


@pytest.mark.parametrize("action", ["transfer", "version", "deprecate"])
def test_lifecycle_actions_require_register_first(conn, action):
    _register_atom(conn)
    result = notarize_atom(conn, "com.zhangsan.premium-music", action=action)
    assert result["ok"] is False
    assert result["reason"] == "missing_register"


def test_four_actions_append_not_overwrite(conn):
    _register_atom(conn)
    hashes = []
    for action in ("register", "transfer", "version", "deprecate"):
        result = notarize_atom(conn, "com.zhangsan.premium-music", action=action)
        assert result["ok"] is True and result["skipped"] is False
        hashes.append(result["tx_hash"])
    assert len(set(hashes)) == 4  # 每次新交易

    atom = get_atom(conn, "com.zhangsan.premium-music")
    txs = atom["runtime"]["blockchain_txs"]
    assert [t["action"] for t in txs] == ["register", "transfer", "version", "deprecate"]
    # blockchain 指向最新一笔，旧交易不被覆盖（文档§十）
    assert atom["runtime"]["blockchain"]["tx_hash"] == hashes[-1]
    # 每个 action 再公证都 skipped（防重放）
    for action in ("register", "transfer", "version", "deprecate"):
        again = notarize_atom(conn, "com.zhangsan.premium-music", action=action)
        assert again["skipped"] is True
    assert len(get_atom(conn, "com.zhangsan.premium-music")["runtime"]["blockchain_txs"]) == 4


def test_notarize_invalid_action(conn):
    _register_atom(conn)
    result = notarize_atom(conn, "com.zhangsan.premium-music", action="burn")
    assert result["ok"] is False
    assert "invalid_action" in result["reason"]


def test_notarize_atom_not_found(conn):
    result = notarize_atom(conn, "com.ghost.missing", action="register")
    assert result["ok"] is False
    assert result["reason"] == "not_found"


def test_notarize_never_raises_on_broken_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTARY_PROVIDER", "local")
    monkeypatch.setenv("NOTARY_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    c = sqlite3.connect(":memory:")
    c.close()  # 已关闭的连接：任何异常都必须吞掉
    result = notarize_atom(c, "com.x.y", action="register")
    assert result["ok"] is False
    assert result["reason"]


# ------------------------------------------------------- local ledger 落账


def test_local_ledger_file_written_and_fetchable(conn, tmp_path):
    _register_atom(conn)
    result = notarize_atom(conn, "com.zhangsan.premium-music", action="register")
    ledger = tmp_path / "notary_ledger.jsonl"
    assert ledger.exists()
    lines = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tx_hash"] == result["tx_hash"]
    assert record["network"] == "local"
    assert record["payload"] == result["payload"]

    provider = LocalLedgerProvider()
    fetched = provider.fetch(result["tx_hash"])
    assert fetched is not None
    assert fetched["payload"]["atom_id"] == "com.zhangsan.premium-music"
    assert provider.fetch("0" * 64) is None


# ---------------------------------------------------------------- verify


def test_verify_data_matches_true(conn):
    _register_atom(conn)
    notarized = notarize_atom(conn, "com.zhangsan.premium-music", action="register")
    result = verify_notarization(conn, "com.zhangsan.premium-music")
    assert result["verified"] is True
    assert result["data_matches"] is True
    assert result["blockchain"] == "local"
    assert result["tx_hash"] == notarized["tx_hash"]
    assert result["confirmed_at"] == notarized["notarized_at"]
    assert "reason" not in result


def test_verify_data_matches_false_after_tamper(conn):
    _register_atom(conn)
    notarize_atom(conn, "com.zhangsan.premium-music", action="register")
    # 篡改原子当前签名：链上快照与现状必然不一致
    conn.execute(
        f"UPDATE {REGISTRY_TABLE} SET signature_hash = ? WHERE atom_id = ?",
        ("f" * 64, "com.zhangsan.premium-music"),
    )
    conn.commit()
    result = verify_notarization(conn, "com.zhangsan.premium-music")
    assert result["verified"] is False
    assert result["data_matches"] is False
    assert result["blockchain"] == "local"  # 仍能定位链与交易


def test_verify_not_notarized(conn):
    _register_atom(conn)
    result = verify_notarization(conn, "com.zhangsan.premium-music")
    assert result["verified"] is False
    assert result["reason"] == "not_notarized"
    assert result["data_matches"] is False


def test_verify_atom_not_found(conn):
    result = verify_notarization(conn, "com.ghost.missing")
    assert result["verified"] is False
    assert result["reason"] == "not_found"


def test_verify_tx_missing_from_ledger(conn, tmp_path):
    _register_atom(conn)
    notarize_atom(conn, "com.zhangsan.premium-music", action="register")
    # 账本文件被清空：交易查不到
    (tmp_path / "notary_ledger.jsonl").write_text("", encoding="utf-8")
    result = verify_notarization(conn, "com.zhangsan.premium-music")
    assert result["verified"] is False
    assert result["reason"] == "tx_not_found"


# ---------------------------------------------------------------- audit


def test_audit_written_for_each_action(conn):
    _register_atom(conn)
    first = notarize_atom(
        conn, "com.zhangsan.premium-music", action="register", actor="tester"
    )
    second = notarize_atom(
        conn, "com.zhangsan.premium-music", action="transfer", actor="tester"
    )
    rows = conn.execute(
        f"SELECT action, actor, detail FROM {AUDIT_TABLE} "
        "WHERE atom_id = ? AND action LIKE 'notarize_%' ORDER BY id",
        ("com.zhangsan.premium-music",),
    ).fetchall()
    assert [r[0] for r in rows] == ["notarize_register", "notarize_transfer"]
    assert all(r[1] == "tester" for r in rows)
    assert first["tx_hash"] in rows[0][2]
    assert second["tx_hash"] in rows[1][2]

    # skipped 的防重放不落新审计
    notarize_atom(conn, "com.zhangsan.premium-music", action="register")
    count = conn.execute(
        f"SELECT COUNT(*) FROM {AUDIT_TABLE} "
        "WHERE atom_id = ? AND action LIKE 'notarize_%'",
        ("com.zhangsan.premium-music",),
    ).fetchone()[0]
    assert count == 2


# -------------------------------------------------------------- provider


def test_get_provider_defaults_to_local_without_arweave(monkeypatch):
    monkeypatch.delenv("NOTARY_PROVIDER", raising=False)
    monkeypatch.delenv("ARWEAVE_JWK", raising=False)
    assert isinstance(get_provider(), LocalLedgerProvider)


def test_get_provider_forced_by_env(monkeypatch):
    monkeypatch.setenv("NOTARY_PROVIDER", "local")
    assert isinstance(get_provider(), LocalLedgerProvider)
    monkeypatch.setenv("NOTARY_PROVIDER", "arweave")
    assert isinstance(get_provider(), ArweaveProvider)


def test_arweave_unavailable_without_jwk(monkeypatch):
    monkeypatch.delenv("ARWEAVE_JWK", raising=False)
    available, reason = ArweaveProvider().is_available()
    assert available is False
    assert "ARWEAVE_JWK" in reason


def test_notarize_fails_cleanly_when_provider_unavailable(conn, monkeypatch):
    """强制 arweave 但缺私钥：ok:False + reason，绝不抛出。"""
    monkeypatch.setenv("NOTARY_PROVIDER", "arweave")
    monkeypatch.delenv("ARWEAVE_JWK", raising=False)
    _register_atom(conn)
    result = notarize_atom(conn, "com.zhangsan.premium-music", action="register")
    assert result["ok"] is False
    assert "arweave_unavailable" in result["reason"]
    # 失败不留痕：runtime_json 未被写入
    atom = get_atom(conn, "com.zhangsan.premium-music")
    assert "blockchain" not in (atom.get("runtime") or {})
