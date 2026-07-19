"""Yuanzi Chain — local single-node blockchain for atom notarization."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from merkle import hash_tx, merkle_root, merkle_proof, verify_proof

CHAIN_DIR = Path(__file__).resolve().parent
BLOCKS_DIR = CHAIN_DIR / "blocks"
STATE_FILE = CHAIN_DIR / "chain_state.json"
BACKUP_REPO = os.environ.get("YUANZI_CHAIN_REPO", "")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rj(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _wj(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def hash_block(block: Dict[str, Any]) -> str:
    payload = f"{block['height']}|{block['prev_hash']}|{block['merkle_root']}|{block['timestamp']}"
    return hashlib.sha256(payload.encode()).hexdigest()


class YuanziChain:
    def __init__(self, backup_repo: str = "") -> None:
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        self.backup_repo = backup_repo or BACKUP_REPO
        self._ensure_genesis()

    def add_block(self, transactions: List[Dict[str, Any]]) -> str:
        state = _rj(STATE_FILE)
        prev = self.get_block(state["height"])
        block = {
            "height": state["height"] + 1,
            "prev_hash": hash_block(prev),
            "timestamp": now_iso(),
            "merkle_root": merkle_root(transactions),
            "transactions": transactions,
        }
        _wj(BLOCKS_DIR / f"{block['height']:06d}.json", block)
        state.update(height=block["height"], head_hash=hash_block(block), updated_at=now_iso())
        _wj(STATE_FILE, state)
        self._backup(block)
        return hash_block(block)

    def get_block(self, height: int) -> Optional[Dict[str, Any]]:
        p = BLOCKS_DIR / f"{height:06d}.json"
        return _rj(p) if p.exists() else None

    def get_tx(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        for h in range(_rj(STATE_FILE)["height"], -1, -1):
            block = self.get_block(h)
            if not block:
                continue
            for tx in block["transactions"]:
                if hash_tx(tx) == tx_hash:
                    return {"tx": tx, "block_height": h, "block_hash": hash_block(block), "timestamp": block["timestamp"]}
        return None

    def verify_atom(self, atom_id: str) -> Dict[str, Any]:
        state = _rj(STATE_FILE)
        for h in range(state["height"], -1, -1):
            block = self.get_block(h)
            if not block:
                continue
            for idx, tx in enumerate(block["transactions"]):
                if tx.get("atom_id") == atom_id:
                    tx_h = hash_tx(tx)
                    proof = merkle_proof(block["transactions"], idx)
                    merkle_ok = verify_proof(tx_h, proof, block["merkle_root"])
                    chain_ok = all(
                        self.get_block(i) and self.get_block(i)["prev_hash"] == hash_block(self.get_block(i - 1))
                        for i in range(h, 0, -1)
                    ) if h > 0 else True
                    return {
                        "verified": merkle_ok and chain_ok, "atom_id": atom_id, "tx_hash": tx_h,
                        "block_height": h, "block_hash": hash_block(block), "timestamp": block["timestamp"],
                        "chain_integrity": chain_ok,
                    }
        return {"verified": False, "atom_id": atom_id, "error": "not found on chain"}

    def verify_full_chain(self) -> Dict[str, Any]:
        state = _rj(STATE_FILE)
        issues = []
        prev_hash = ""
        for h in range(state["height"] + 1):
            block = self.get_block(h)
            if not block:
                issues.append(f"Block {h}: missing")
                continue
            if h == 0:
                if block["prev_hash"] != "0" * 64:
                    issues.append("Genesis: prev_hash != 64 zeros")
            elif block["prev_hash"] != prev_hash:
                issues.append(f"Block {h}: prev_hash mismatch")
            if block["merkle_root"] != merkle_root(block["transactions"]):
                issues.append(f"Block {h}: merkle_root mismatch")
            prev_hash = hash_block(block)
        return {"valid": len(issues) == 0, "total_blocks": state["height"] + 1, "chain_head": state["head_hash"], "issues": issues}

    def get_status(self) -> Dict[str, Any]:
        s = _rj(STATE_FILE)
        return {"height": s["height"], "head_hash": s["head_hash"], "total_blocks": s["height"] + 1, "updated_at": s["updated_at"]}

    def _ensure_genesis(self) -> None:
        if STATE_FILE.exists():
            return
        tx = [{"type": "notarize", "atom_id": "yuanzi.chain", "signature_hash": "genesis", "author": "Yuanzi", "action": "genesis", "description": "Yuanzi Chain genesis"}]
        block = {"height": 0, "prev_hash": "0" * 64, "timestamp": "2026-07-19T00:00:00Z", "merkle_root": merkle_root(tx), "transactions": tx}
        _wj(BLOCKS_DIR / "000000.json", block)
        _wj(STATE_FILE, {"height": 0, "head_hash": hash_block(block), "created_at": now_iso(), "updated_at": now_iso()})

    def _backup(self, block: Dict[str, Any]) -> None:
        if not self.backup_repo:
            return
        try:
            for cmd in [
                ["git", "add", "blocks/", "chain_state.json"],
                ["git", "commit", "-m", f"block #{block['height']}"],
                ["git", "push", "origin", "main"],
            ]:
                subprocess.run(cmd, cwd=str(CHAIN_DIR), capture_output=True, timeout=15)
        except Exception:
            pass


_chain: Optional[YuanziChain] = None


def get_chain() -> YuanziChain:
    global _chain
    if _chain is None:
        _chain = YuanziChain()
    return _chain


if __name__ == "__main__":
    import sys
    chain = get_chain()
    if len(sys.argv) < 2:
        print("Usage: python chain.py [status|verify|add|get <id>]")
    elif sys.argv[1] == "status":
        print(json.dumps(chain.get_status(), ensure_ascii=False, indent=2))
    elif sys.argv[1] == "verify":
        print(json.dumps(chain.verify_full_chain(), ensure_ascii=False, indent=2))
    elif sys.argv[1] == "add":
        h = chain.add_block([{"type": "notarize", "atom_id": "com.test.sample", "signature_hash": hashlib.sha256(b"test").hexdigest(), "author": "Test", "action": "register"}])
        print(f"Block added: {h}")
    elif sys.argv[1] == "get":
        aid = sys.argv[2] if len(sys.argv) > 2 else "yuanzi.chain"
        print(json.dumps(chain.verify_atom(aid), ensure_ascii=False, indent=2))
