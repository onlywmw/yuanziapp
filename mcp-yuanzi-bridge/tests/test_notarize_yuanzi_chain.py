"""YuanziChainProvider 与链上 verify 集成测试（DESIGN_ATOM_NOTARIZATION.md §三/§五）。

覆盖合并契约：
- YuanziChainProvider 五件套接口与 LocalLedgerProvider 对齐
  （name/network/is_available/submit/fetch），network == "yuanzi-chain"
- submit/fetch 回环：tx_hash == hash_tx(链上交易)，fetch 归一化为 verify 路径
  期望的记录形状（payload 内可取回 signature_hash）
- provider 选择：默认优先 yuanzi-chain，链不可用回退 local；NOTARY_PROVIDER 强制；
  _provider_for_network 同时映射 "yuanzi-chain" 与 "local"
- verify_notarization 对 yuanzi-chain 记录追加链上校验（Merkle 证明 + 链完整性），
  返回新键 block_height / chain_integrity，现有键语义不变
- 篡改链上数据（块内交易 / prev_hash 链式结构）→ 验证失败
- yuanzi_chain 包缺失/损坏时 is_available() 为 False 且 notarize 不崩溃
- 老 local 记录 verify 兼容；ArweaveProvider 已整体删除

全部 hermetic：YUANZI_CHAIN_HOME 与账本指向 tmp_path，链单例逐用例重置，
不读仓库内真实 blocks 数据、不访问网络。
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from migrations import migrate
from registry import get_atom, submit_atom

import notarize
from notarize import (
    LocalLedgerProvider,
    build_notary_payload,
    get_provider,
    notarize_atom,
    verify_notarization,
)

ATOM_ID = "com.zhangsan.onchain-music"
AUTHOR = "张三"


def _yuanzi_chain_provider_cls():
    """惰性取 YuanziChainProvider：实现未合入时单测试清晰失败，而非整文件收集错误。"""
    cls = getattr(notarize, "YuanziChainProvider", None)
    if cls is None:
        pytest.fail("notarize.YuanziChainProvider 尚未实现（等待并行任务合入）")
    return cls


def _yuanzi_chain():
    """惰性导入链包：包未就绪时单测试清晰失败。"""
    try:
        import yuanzi_chain
    except Exception as exc:
        pytest.fail(f"yuanzi_chain 包不可导入（等待并行任务合入）: {exc!r}")
    return yuanzi_chain


@pytest.fixture(autouse=True)
def _isolated_chain(tmp_path, monkeypatch):
    """链数据与账本全部指向 tmp_path；关备份推送；逐用例重置链单例；走真实默认 provider。"""
    monkeypatch.setenv("YUANZI_CHAIN_HOME", str(tmp_path / "yuanzi_chain_home"))
    monkeypatch.setenv("NOTARY_LEDGER_PATH", str(tmp_path / "notary_ledger.jsonl"))
    monkeypatch.delenv("YUANZI_CHAIN_REPO", raising=False)
    monkeypatch.delenv("NOTARY_PROVIDER", raising=False)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    try:
        import yuanzi_chain.chain as chain_mod

        monkeypatch.setattr(chain_mod, "_chain", None)
    except Exception:
        pass  # 链包未就绪：相关用例会自行给出清晰失败


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def _atom(atom_id=ATOM_ID, author=AUTHOR):
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


def _register_atom(conn, atom_id=ATOM_ID):
    result = submit_atom(conn, _atom(atom_id), actor="tester")
    assert result["success"] is True
    return get_atom(conn, atom_id)


def _sample_payload():
    return build_notary_payload(
        {
            "atom_id": ATOM_ID,
            "signature_hash": "a" * 64,
            "ownership": {"author": AUTHOR},
        },
        "register",
        actor="tester",
    )


def _chain_home(tmp_path) -> Path:
    return tmp_path / "yuanzi_chain_home"


def _rewrite_block(home: Path, height: int, mutate) -> None:
    path = home / "blocks" / f"{height:06d}.json"
    block = json.loads(path.read_text(encoding="utf-8"))
    mutate(block)
    path.write_text(json.dumps(block, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------- provider 接口形状


def test_provider_contract_interface():
    """五件套与 LocalLedgerProvider 对齐；network == 'yuanzi-chain'；健康环境下可用。"""
    provider = _yuanzi_chain_provider_cls()()
    for attr in ("name", "network", "is_available", "submit", "fetch"):
        assert hasattr(provider, attr), attr
    assert provider.network == "yuanzi-chain"
    available, reason = provider.is_available()
    assert available is True
    assert isinstance(reason, str)


# ------------------------------------------------------- submit/fetch 回环


def test_submit_fetch_roundtrip(tmp_path):
    provider = _yuanzi_chain_provider_cls()()
    payload = _sample_payload()
    submitted = provider.submit(payload)
    assert submitted["network"] == "yuanzi-chain"
    assert len(submitted["tx_hash"]) == 64
    int(submitted["tx_hash"], 16)  # 十六进制 sha256
    assert submitted["notarized_at"]

    fetched = provider.fetch(submitted["tx_hash"])
    assert fetched is not None
    assert fetched["network"] == "yuanzi-chain"
    assert fetched["tx_hash"] == submitted["tx_hash"]
    # 归一化记录形状满足 verify 路径：payload 内可取回签名哈希
    assert fetched["payload"]["atom_id"] == ATOM_ID
    assert fetched["payload"]["action"] == "register"
    assert fetched["payload"]["signature_hash"] == payload["signature_hash"]
    assert provider.fetch("0" * 64) is None


def test_submit_tx_hash_matches_hash_tx_on_chain(tmp_path):
    """submit 返回的 tx_hash 就是链上交易的 hash_tx，且块文件真实落盘。"""
    yc = _yuanzi_chain()
    provider = _yuanzi_chain_provider_cls()()
    before = yc.get_chain().get_status()["height"]
    submitted = provider.submit(_sample_payload())

    after = yc.get_chain().get_status()
    assert after["height"] == before + 1
    found = yc.get_chain().get_tx(submitted["tx_hash"])
    assert found is not None
    assert yc.hash_tx(found["tx"]) == submitted["tx_hash"]
    assert found["block_height"] == after["height"]
    # 块文件落在 YUANZI_CHAIN_HOME 指向的 tmp 目录，而非仓库内真实链目录
    block_file = _chain_home(tmp_path) / "blocks" / f"{after['height']:06d}.json"
    assert block_file.exists()


# ------------------------------------------------------------- provider 选择


def test_get_provider_default_prefers_yuanzi_chain():
    provider = get_provider()
    assert isinstance(provider, _yuanzi_chain_provider_cls())
    assert provider.network == "yuanzi-chain"


def test_get_provider_falls_back_to_local_when_chain_unavailable(monkeypatch):
    provider_cls = _yuanzi_chain_provider_cls()
    monkeypatch.setattr(
        provider_cls,
        "is_available",
        lambda self: (False, "yuanzi_chain_unavailable: simulated"),
    )
    provider = get_provider()
    assert isinstance(provider, LocalLedgerProvider)
    assert provider.network == "local"


def test_get_provider_forced_by_notary_provider_env(monkeypatch):
    monkeypatch.setenv("NOTARY_PROVIDER", "yuanzi-chain")
    assert isinstance(get_provider(), _yuanzi_chain_provider_cls())
    monkeypatch.setenv("NOTARY_PROVIDER", "local")
    assert isinstance(get_provider(), LocalLedgerProvider)


def test_provider_for_network_maps_both_networks():
    """verify 路由："yuanzi-chain" 与 "local" 各自映射；arweave 引用已删除。"""
    provider_cls = _yuanzi_chain_provider_cls()
    assert isinstance(notarize._provider_for_network("yuanzi-chain"), provider_cls)
    assert isinstance(notarize._provider_for_network("local"), LocalLedgerProvider)
    assert notarize._provider_for_network("arweave") is None
    assert notarize._provider_for_network("bogus") is None


# ------------------------------------------------------- 端到端：公证 + 链上验证


def test_notarize_and_verify_on_chain_end_to_end(conn, tmp_path):
    _register_atom(conn)
    result = notarize_atom(conn, ATOM_ID, action="register", actor="tester")
    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["network"] == "yuanzi-chain"

    atom = get_atom(conn, ATOM_ID)
    blockchain = atom["runtime"]["blockchain"]
    assert blockchain["network"] == "yuanzi-chain"
    assert blockchain["tx_hash"] == result["tx_hash"]
    # 默认链路径不应产生 local 账本文件
    assert not (tmp_path / "notary_ledger.jsonl").exists()

    verified = verify_notarization(conn, ATOM_ID)
    assert verified["verified"] is True
    assert verified["data_matches"] is True
    assert verified["blockchain"] == "yuanzi-chain"
    assert verified["tx_hash"] == result["tx_hash"]
    # 链上校验新键：Merkle 证明所在高度 + prev_hash 链完整性
    assert verified["chain_integrity"] is True
    assert isinstance(verified["block_height"], int)
    assert verified["block_height"] >= 1


def test_verify_fails_when_on_chain_tx_tampered(conn, tmp_path):
    """篡改块内交易内容：交易哈希改变、Merkle 证明不再成立，验证必须失败。"""
    yc = _yuanzi_chain()
    _register_atom(conn)
    result = notarize_atom(conn, ATOM_ID, action="register", actor="tester")
    assert result["ok"] is True

    found = yc.get_chain().get_tx(result["tx_hash"])
    assert found is not None

    def _mutate(block):
        block["transactions"][0]["signature_hash"] = "f" * 64

    _rewrite_block(_chain_home(tmp_path), found["block_height"], _mutate)

    verified = verify_notarization(conn, ATOM_ID)
    assert verified["verified"] is False
    assert verified["data_matches"] is False


def test_verify_fails_when_chain_linkage_tampered(conn, tmp_path):
    """篡改创世块使 prev_hash 链断裂：交易本身未动（签名仍匹配），
    但链完整性校验必须把 verified 拉成 False。"""
    yc = _yuanzi_chain()
    _register_atom(conn)
    result = notarize_atom(conn, ATOM_ID, action="register", actor="tester")
    assert result["ok"] is True

    def _mutate(genesis):
        genesis["timestamp"] = "2030-01-01T00:00:00+00:00"  # hash_block 输入变化

    _rewrite_block(_chain_home(tmp_path), 0, _mutate)

    # sanity：链自检确实能发现断裂（直接钉住 chain.py 的完整性语义）
    assert yc.get_chain().verify_full_chain()["valid"] is False

    verified = verify_notarization(conn, ATOM_ID)
    assert verified["data_matches"] is True  # 块内交易未动，签名仍匹配
    assert verified["chain_integrity"] is False
    assert verified["verified"] is False


# ------------------------------------------------------- 容错与兼容


def test_chain_package_broken_falls_back_to_local(conn, tmp_path, monkeypatch):
    """yuanzi_chain 包缺失/损坏：is_available() 为 False，默认公证回退 local，
    notarize 主流程绝不崩溃。"""
    monkeypatch.setitem(sys.modules, "yuanzi_chain", None)
    monkeypatch.setitem(sys.modules, "yuanzi_chain.chain", None)
    monkeypatch.setitem(sys.modules, "yuanzi_chain.merkle", None)
    # 防御性清掉 notarize 侧可能的模块级缓存（实现对导入必须惰性+容错）
    for attr in ("yuanzi_chain", "_yuanzi_chain", "_yc"):
        monkeypatch.delattr(notarize, attr, raising=False)

    provider_cls = _yuanzi_chain_provider_cls()
    available, reason = provider_cls().is_available()
    assert available is False
    assert reason

    _register_atom(conn)
    result = notarize_atom(conn, ATOM_ID, action="register", actor="tester")
    assert result["ok"] is True
    assert result["network"] == "local"
    assert (tmp_path / "notary_ledger.jsonl").exists()


def test_verify_legacy_local_record_still_compatible(conn, monkeypatch):
    """老 local 记录：_provider_for_network('local') 路由不变，verify 依旧通过。"""
    monkeypatch.setenv("NOTARY_PROVIDER", "local")
    _register_atom(conn)
    result = notarize_atom(conn, ATOM_ID, action="register", actor="tester")
    assert result["ok"] is True
    assert result["network"] == "local"

    monkeypatch.delenv("NOTARY_PROVIDER", raising=False)  # 默认选择漂移不影响老记录
    verified = verify_notarization(conn, ATOM_ID)
    assert verified["verified"] is True
    assert verified["data_matches"] is True
    assert verified["blockchain"] == "local"
    assert verified["tx_hash"] == result["tx_hash"]


def test_arweave_provider_removed():
    """ArweaveProvider 已从 notarize 整体删除。"""
    assert not hasattr(notarize, "ArweaveProvider")
