#!/usr/bin/env python3
"""原子公证核心模块（轻量公证处）。

规格来源：docs/DESIGN_ATOM_NOTARIZATION.md
定位：资产类原子的不可篡改时间戳 + 所有权证明——不上合约、不搞代币。

组成：
- build_notary_payload：构造约 300 字节的上链 JSON（七字段纯函数）
- Provider 抽象（参考 embeddings.py 的可插拔范式）：
  - YuanziChainProvider：默认，仓库根 yuanzi_chain 包（本地单节点链，
    Merkle 证明 + prev_hash 链完整性），惰性导入、容错降级
  - LocalLedgerProvider：兜底，零配置零外网，tx 追加写本地 JSONL 账本
- notarize_atom / verify_notarization：公证写入与链上比对，
  公证数据落 atom.runtime_json（JSON 列，零迁移），审计复用 registry 审计链。

安全约束：
- 不持有任何私钥、不触外网（yuanzi_chain 为本地链，LocalLedger 为本地文件）
- 任何异常吞掉返回 {"ok": False, "reason": ...}，绝不抛出
- yuanzi_chain 包缺失/损坏时自动回退 LocalLedger，绝不让本模块崩溃
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from registry import REGISTRY_TABLE, ConcurrentModificationError, get_atom, now_iso
from registry.audit import _audit
from registry.hashing import _canonical_json

# 四种公证触发时机（沿用 DESIGN_ATOM_NOTARIZATION.md §二的生命周期动作）
NOTARY_ACTIONS = ("register", "transfer", "version", "deprecate")

# metadata_uri 的固定前缀
_METADATA_URI_BASE = "https://yuanzi.app/atoms"

# 仓库根目录（mcp-yuanzi-bridge 的上一级），yuanzi_chain 包所在处
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _failure(reason: str) -> Dict[str, Any]:
    """统一失败返回面，键与成功路径保持一致。"""
    return {
        "ok": False,
        "skipped": False,
        "reason": reason,
        "network": None,
        "tx_hash": None,
        "payload": None,
        "notarized_at": None,
    }


def _import_yuanzi_chain():
    """惰性导入仓库根的 yuanzi_chain 包；缺失/损坏时返回 None（绝不抛出）。

    定位方式：notarize.py 的 __file__ 向上推一级得仓库根，插入 sys.path。
    包能 import 但缺关键导出（包结构损坏）同样视为不可用。
    """
    try:
        root = str(_REPO_ROOT)
        if root not in sys.path:
            sys.path.insert(0, root)
        import yuanzi_chain  # 惰性 import：默认路径不加载链依赖

        for attr in ("YuanziChain", "get_chain", "hash_tx"):
            if not hasattr(yuanzi_chain, attr):
                return None
        return yuanzi_chain
    except Exception:
        return None


def build_notary_payload(
    atom: Dict[str, Any], action: str, actor: str = "system"
) -> Dict[str, Any]:
    """按 DESIGN_ATOM_NOTARIZATION.md 的交易形状构造上链 payload（纯函数，不触库不触网）。

    字段严格为 {version, atom_id, signature_hash, author, timestamp, action,
    metadata_uri} 七项。action 非法或 atom 缺 atom_id 时抛 ValueError
    （调用方 notarize_atom 统一兜底）。
    """
    if action not in NOTARY_ACTIONS:
        raise ValueError(
            f"invalid notary action: {action!r} (allowed: {list(NOTARY_ACTIONS)})"
        )
    atom_id = atom.get("atom_id")
    if not atom_id:
        raise ValueError("atom_id is required")
    signature_hash = atom.get("signature_hash") or atom.get("signature", {}).get(
        "hash"
    ) or ""
    author = atom.get("ownership", {}).get("author") or actor
    return {
        "version": 1,
        "atom_id": atom_id,
        "signature_hash": signature_hash,
        "author": author,
        "timestamp": now_iso(),  # ISO UTC
        "action": action,
        "metadata_uri": f"{_METADATA_URI_BASE}/{atom_id}",
    }


class YuanziChainProvider:
    """Yuanzi Chain provider（默认）：仓库根 yuanzi_chain 包，本地单节点链。

    tx 打包进新区块（Merkle 证明 + prev_hash 链），tx_hash = hash_tx(tx)
    （add_block 返回的是块哈希，不用）。链数据目录默认为仓库内
    yuanzi_chain/blocks/ + chain_state.json，环境变量 YUANZI_CHAIN_HOME 可改。
    对 yuanzi_chain 的导入惰性且容错：包缺失/损坏、链目录不可写时
    is_available() 返回 (False, reason)，绝不抛出。
    """

    name = "yuanzi-chain"
    network = "yuanzi-chain"

    def is_available(self) -> Tuple[bool, str]:
        if _import_yuanzi_chain() is None:
            return False, "yuanzi_chain_unavailable: yuanzi_chain 包不可导入"
        chain_home = Path(
            os.environ.get("YUANZI_CHAIN_HOME") or (_REPO_ROOT / "yuanzi_chain")
        )
        try:
            chain_home.mkdir(parents=True, exist_ok=True)
            probe = chain_home / ".notary_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            return False, f"yuanzi_chain_unavailable: 链目录不可写 ({exc})"
        return True, ""

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        available, reason = self.is_available()
        if not available:
            raise RuntimeError(reason)
        yc = _import_yuanzi_chain()
        tx = {
            "type": "notarize",
            "atom_id": payload.get("atom_id"),
            "action": payload.get("action"),
            "actor": payload.get("author") or "system",
            "author": payload.get("author") or "system",
            "signature_hash": payload.get("signature_hash") or "",
            "payload_hash": hashlib.sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest(),
            "timestamp": payload.get("timestamp") or now_iso(),
        }
        chain = yc.get_chain()
        chain.add_block([tx])  # 返回块哈希；交易哈希由调用方用 hash_tx(tx) 计算
        return {
            "network": self.network,
            "tx_hash": yc.hash_tx(tx),
            "notarized_at": tx["timestamp"],
        }

    def fetch(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """按 tx_hash 走 get_chain().get_tx 查链，归一化为 verify 路径期望的记录形状。"""
        yc = _import_yuanzi_chain()
        if yc is None:
            return None
        hit = yc.get_chain().get_tx(tx_hash)
        if not hit:
            return None
        tx = hit.get("tx") or {}
        return {
            "network": self.network,
            "tx_hash": tx_hash,
            "payload": tx,  # 链上交易本体即 payload（含 signature_hash）
            # 优先交易自身时间戳，与 submit 返回的 notarized_at 保持一致
            "notarized_at": tx.get("timestamp") or hit.get("timestamp"),
            "block_height": hit.get("block_height"),
        }


class LocalLedgerProvider:
    """本地账本 provider（兜底）：零配置零外网。

    tx_hash = sha256(canonical(payload) + nonce)，记录追加写 JSONL 账本文件。
    账本路径默认 registry.db 同目录 notary_ledger.jsonl，
    环境变量 NOTARY_LEDGER_PATH 可改。
    """

    name = "local"
    network = "local"

    def __init__(self, ledger_path: Optional[str] = None):
        self.ledger_path = (
            ledger_path
            or os.environ.get("NOTARY_LEDGER_PATH")
            or str(Path(__file__).resolve().parent / "notary_ledger.jsonl")
        )

    def is_available(self) -> Tuple[bool, str]:
        # 本地账本永远可用（写文件失败会在 submit 阶段暴露并被上层兜底）
        return True, ""

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        nonce = secrets.token_hex(16)
        tx_hash = hashlib.sha256(
            (_canonical_json(payload) + nonce).encode("utf-8")
        ).hexdigest()
        notarized_at = now_iso()
        record = {
            "network": self.network,
            "tx_hash": tx_hash,
            "nonce": nonce,
            "payload": payload,
            "notarized_at": notarized_at,
        }
        path = Path(self.ledger_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {
            "network": self.network,
            "tx_hash": tx_hash,
            "notarized_at": notarized_at,
        }

    def fetch(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """按 tx_hash 扫描账本文件，命中返回整条记录，否则 None。"""
        path = Path(self.ledger_path)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 容忍半行/坏行，不整文件失败
                if record.get("tx_hash") == tx_hash:
                    return record
        return None


def get_provider(name: Optional[str] = None):
    """集中选择 provider。

    - 显式 name 或 NOTARY_PROVIDER=yuanzi-chain 强制 Yuanzi Chain
    - NOTARY_PROVIDER=local 强制本地账本
    - 默认：yuanzi-chain 可用则 yuanzi-chain，否则本地账本（零外网兜底）
    """
    forced = (name or os.environ.get("NOTARY_PROVIDER") or "").strip().lower()
    if forced in ("yuanzi-chain", "yuanzi_chain", "yuanzichain"):
        return YuanziChainProvider()
    if forced == "local":
        return LocalLedgerProvider()
    chain_provider = YuanziChainProvider()
    available, _ = chain_provider.is_available()
    if available:
        return chain_provider
    return LocalLedgerProvider()


def _provider_for_network(network: str):
    """verify 时按 atom 记录的网络选 provider，不跟默认选择漂移。

    "yuanzi-chain" → YuanziChainProvider，"local" → LocalLedgerProvider
    （老 local 记录的 verify 路径保持兼容）。
    """
    if network == YuanziChainProvider.network:
        return YuanziChainProvider()
    if network == LocalLedgerProvider.network:
        return LocalLedgerProvider()
    return None


def _find_tx(txs: List[Dict[str, Any]], action: str) -> Optional[Dict[str, Any]]:
    for tx in txs:
        if isinstance(tx, dict) and tx.get("action") == action:
            return tx
    return None


def _verify_on_chain(atom_id: str) -> Optional[Dict[str, Any]]:
    """yuanzi-chain 记录的链上校验（DESIGN_ATOM_NOTARIZATION.md §五）。

    Merkle 证明（交易确实在区块中，经 chain.verify_atom）+ 全链完整性
    （prev_hash / merkle_root 从头一致，经 chain.verify_full_chain）。
    包不可用或任何异常返回 None（调用方视为链校验不通过）。
    """
    yc = _import_yuanzi_chain()
    if yc is None:
        return None
    try:
        chain = yc.get_chain()
        atom_check = chain.verify_atom(atom_id)
        full_check = chain.verify_full_chain()
        return {
            "block_height": atom_check.get("block_height"),
            "chain_integrity": bool(atom_check.get("verified"))
            and bool(full_check.get("valid")),
        }
    except Exception:
        return None


def _persist_notary(
    conn: sqlite3.Connection,
    atom_id: str,
    action: str,
    actor: str,
    network: str,
    tx_hash: str,
    payload: Dict[str, Any],
    notarized_at: str,
    max_retries: int = 3,
) -> Tuple[Dict[str, Any], bool]:
    """把公证结果写入 atom.runtime_json（乐观锁重试，沿用 probe 写入范式）。

    - runtime.blockchain = {network, tx_hash, notarized_at, verified}（最新一笔）
    - runtime.blockchain_txs 追加完整记录（新交易不覆盖旧交易）
    返回 (记录, 是否并发命中已有记录)。
    """
    for _ in range(max_retries):
        atom = get_atom(conn, atom_id)
        if not atom:
            raise ValueError(f"Atom '{atom_id}' not found")
        expected_counter = int(atom.get("version_counter") or 0)
        runtime = dict(atom.get("runtime") or {})
        txs = list(runtime.get("blockchain_txs") or [])
        # 并发重读后再查一次防重放：已被并发写入则直接复用旧记录
        existing = _find_tx(txs, action)
        if existing is not None:
            return existing, True
        record = {
            "action": action,
            "actor": actor,
            "network": network,
            "tx_hash": tx_hash,
            "payload": payload,
            "notarized_at": notarized_at,
        }
        txs.append(record)
        runtime["blockchain_txs"] = txs
        runtime["blockchain"] = {
            "network": network,
            "tx_hash": tx_hash,
            "notarized_at": notarized_at,
            "verified": True,
        }
        cursor = conn.execute(
            f"UPDATE {REGISTRY_TABLE} SET runtime_json = ?, updated_at = ?, "
            "version_counter = version_counter + 1 "
            "WHERE atom_id = ? AND version_counter = ?",
            (
                json.dumps(runtime, ensure_ascii=False),
                now_iso(),
                atom_id,
                expected_counter,
            ),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            continue
        conn.commit()
        return record, False
    raise ConcurrentModificationError(
        f"notarize of '{atom_id}' failed after {max_retries} retries"
    )


def notarize_atom(
    conn: sqlite3.Connection,
    atom_id: str,
    action: str = "register",
    actor: str = "system",
) -> Dict[str, Any]:
    """对原子执行一次链上公证（同步函数，绝不抛异常）。

    返回 {ok, skipped, reason?, network, tx_hash, payload, notarized_at}：
    - 原子不存在 → ok:False, reason='not_found'
    - version/transfer/deprecate 且无首次 register 记录 → ok:False,
      reason='missing_register'（先注册再谈生命周期）
    - 同一 action 链上已有记录 → ok:True, skipped:True（防重放）
    - 成功后写 runtime_json.blockchain / blockchain_txs，并落审计
      （action='notarize_<action>'，沿用现有小写动词哨兵风格）
    """
    try:
        if action not in NOTARY_ACTIONS:
            return _failure(f"invalid_action: {action!r}")
        atom = get_atom(conn, atom_id)
        if not atom:
            return _failure("not_found")

        runtime = atom.get("runtime") or {}
        txs = runtime.get("blockchain_txs") or []
        existing = _find_tx(txs, action)
        if existing is not None:
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_notarized",
                "network": existing.get("network"),
                "tx_hash": existing.get("tx_hash"),
                "payload": existing.get("payload"),
                "notarized_at": existing.get("notarized_at"),
            }
        if action != "register" and _find_tx(txs, "register") is None:
            return _failure("missing_register")

        payload = build_notary_payload(atom, action, actor)
        provider = get_provider()
        available, reason = provider.is_available()
        if not available:
            return _failure(reason)
        submitted = provider.submit(payload)

        record, raced = _persist_notary(
            conn,
            atom_id,
            action,
            actor,
            submitted["network"],
            submitted["tx_hash"],
            payload,
            submitted["notarized_at"],
        )
        if raced:
            # 并发下另一进程已完成同 action 公证：按防重放语义返回 skipped
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_notarized",
                "network": record.get("network"),
                "tx_hash": record.get("tx_hash"),
                "payload": record.get("payload"),
                "notarized_at": record.get("notarized_at"),
            }

        status = (atom.get("lifecycle") or {}).get("status")
        _audit(
            conn,
            atom_id,
            f"notarize_{action}",
            status,
            status,
            actor,
            f"network={submitted['network']} tx_hash={submitted['tx_hash']}",
        )
        return {
            "ok": True,
            "skipped": False,
            "network": submitted["network"],
            "tx_hash": submitted["tx_hash"],
            "payload": payload,
            "notarized_at": submitted["notarized_at"],
        }
    except Exception as exc:  # 任何异常吞掉，绝不抛出
        return _failure(f"{type(exc).__name__}: {exc}")


def verify_notarization(conn: sqlite3.Connection, atom_id: str) -> Dict[str, Any]:
    """链上验证（DESIGN_ATOM_NOTARIZATION.md §五）：比对链上 signature_hash 与原子当前签名。

    返回 {verified, blockchain, tx_hash, confirmed_at, data_matches, reason?}。
    记录在 yuanzi-chain 上时追加链上校验（Merkle 证明 + 链完整性），
    新增 block_height / chain_integrity 键，此时 verified 还需链校验通过；
    其余网络语义不变。verified 仅在交易可查且数据一致时为 True。绝不抛异常。
    """
    base: Dict[str, Any] = {
        "verified": False,
        "blockchain": None,
        "tx_hash": None,
        "confirmed_at": None,
        "data_matches": False,
    }
    try:
        atom = get_atom(conn, atom_id)
        if not atom:
            return {**base, "reason": "not_found"}
        blockchain = (atom.get("runtime") or {}).get("blockchain") or {}
        network = blockchain.get("network")
        tx_hash = blockchain.get("tx_hash")
        if not network or not tx_hash:
            return {**base, "reason": "not_notarized"}
        base.update({"blockchain": network, "tx_hash": tx_hash})

        provider = _provider_for_network(network)
        if provider is None:
            return {**base, "reason": f"unknown_network: {network}"}
        available, reason = provider.is_available()
        if not available:
            return {**base, "reason": reason}
        record = provider.fetch(tx_hash)
        if record is None:
            return {**base, "reason": "tx_not_found"}

        on_chain_sig = ((record.get("payload") or {}).get("signature_hash")) or ""
        current_sig = atom.get("signature_hash") or atom.get("signature", {}).get(
            "hash"
        ) or ""
        data_matches = bool(on_chain_sig) and on_chain_sig == current_sig
        confirmed_at = record.get("notarized_at") or blockchain.get("notarized_at")
        result: Dict[str, Any] = {
            "verified": data_matches,
            "blockchain": network,
            "tx_hash": tx_hash,
            "confirmed_at": confirmed_at,
            "data_matches": data_matches,
        }
        if network == YuanziChainProvider.network:
            # DESIGN_ATOM_NOTARIZATION.md §五：verified = Merkle 证明
            # + 链完整性 + 签名匹配，三者缺一即 False（additive 新键，
            # 不改变 data_matches 等既有键的含义）
            chain_check = _verify_on_chain(atom_id)
            chain_integrity = bool(chain_check and chain_check.get("chain_integrity"))
            result["block_height"] = (chain_check or {}).get("block_height")
            result["chain_integrity"] = chain_integrity
            result["verified"] = bool(data_matches and chain_integrity)
        return result
    except Exception as exc:  # 任何异常吞掉，绝不抛出
        return {**base, "reason": f"{type(exc).__name__}: {exc}"}
