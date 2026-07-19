"""Yuanzi Chain — local single-node blockchain for atom notarization.

Chain data lives in ``<home>/blocks/`` + ``<home>/chain_state.json``.
``<home>`` defaults to this package directory (i.e. ``yuanzi_chain/`` inside
the repository) and can be overridden with the ``YUANZI_CHAIN_HOME``
environment variable (evaluated when a ``YuanziChain`` instance is created).

Backup is opt-in: ``YUANZI_CHAIN_REPO`` must point to an *independent* git
repository directory; the blocks/state are copied there and pushed. The
current main repository is never pushed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .merkle import hash_tx, merkle_root, merkle_proof, verify_proof
except ImportError:  # pragma: no cover - direct CLI run: python yuanzi_chain/chain.py
    from merkle import hash_tx, merkle_root, merkle_proof, verify_proof

_PKG_DIR = Path(__file__).resolve().parent


def resolve_chain_home() -> Path:
    """Return the chain data home directory.

    ``YUANZI_CHAIN_HOME`` overrides the default (the package directory).
    The directory contains ``blocks/`` and ``chain_state.json``.
    """
    env = os.environ.get("YUANZI_CHAIN_HOME", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return _PKG_DIR


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rj(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _wj(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def hash_block(block: Dict[str, Any]) -> str:
    payload = f"{block['height']}|{block['prev_hash']}|{block['merkle_root']}|{block['timestamp']}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _git_toplevel(cwd: Path) -> Optional[Path]:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd), capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return Path(r.stdout.strip()).resolve()


class YuanziChain:
    def __init__(self, backup_repo: str = "", chain_home: Optional[str] = None) -> None:
        home = Path(chain_home).expanduser().resolve() if chain_home else resolve_chain_home()
        self.home = home
        self.blocks_dir = home / "blocks"
        self.state_file = home / "chain_state.json"
        self.blocks_dir.mkdir(parents=True, exist_ok=True)
        self.backup_repo = backup_repo or os.environ.get("YUANZI_CHAIN_REPO", "")
        self._ensure_genesis()

    def add_block(self, transactions: List[Dict[str, Any]]) -> str:
        state = _rj(self.state_file)
        prev = self.get_block(state["height"])
        block = {
            "height": state["height"] + 1,
            "prev_hash": hash_block(prev),
            "timestamp": now_iso(),
            "merkle_root": merkle_root(transactions),
            "transactions": transactions,
        }
        _wj(self.blocks_dir / f"{block['height']:06d}.json", block)
        state.update(height=block["height"], head_hash=hash_block(block), updated_at=now_iso())
        _wj(self.state_file, state)
        self._backup(block)
        return hash_block(block)

    def get_block(self, height: int) -> Optional[Dict[str, Any]]:
        p = self.blocks_dir / f"{height:06d}.json"
        return _rj(p) if p.exists() else None

    def get_tx(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        for h in range(_rj(self.state_file)["height"], -1, -1):
            block = self.get_block(h)
            if not block:
                continue
            for tx in block["transactions"]:
                if hash_tx(tx) == tx_hash:
                    return {"tx": tx, "block_height": h, "block_hash": hash_block(block), "timestamp": block["timestamp"]}
        return None

    def verify_atom(self, atom_id: str) -> Dict[str, Any]:
        state = _rj(self.state_file)
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
        state = _rj(self.state_file)
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
        s = _rj(self.state_file)
        return {"height": s["height"], "head_hash": s["head_hash"], "total_blocks": s["height"] + 1, "updated_at": s["updated_at"]}

    def _ensure_genesis(self) -> None:
        if self.state_file.exists():
            return
        tx = [{"type": "notarize", "atom_id": "yuanzi.chain", "signature_hash": "genesis", "author": "Yuanzi", "action": "genesis", "description": "Yuanzi Chain genesis"}]
        block = {"height": 0, "prev_hash": "0" * 64, "timestamp": "2026-07-19T00:00:00Z", "merkle_root": merkle_root(tx), "transactions": tx}
        _wj(self.blocks_dir / "000000.json", block)
        _wj(self.state_file, {"height": 0, "head_hash": hash_block(block), "created_at": now_iso(), "updated_at": now_iso()})

    def _backup(self, block: Dict[str, Any]) -> None:
        """Copy chain data into an independent backup git repo and push it.

        Disabled by default. Only active when ``YUANZI_CHAIN_REPO`` (or the
        ``backup_repo`` constructor arg) points to a directory that is its own
        git repository. The current main repository is never pushed: the
        backup is skipped when the target resolves to the same git top-level
        as this package, or when the target contains this package / chain data.
        """
        if not self.backup_repo:
            return
        try:
            repo = Path(self.backup_repo).expanduser().resolve()
            if not repo.is_dir() or not (repo / ".git").exists():
                return
            if repo == _PKG_DIR or repo in _PKG_DIR.parents:
                return
            if repo == self.home or repo in self.home.parents:
                return
            main_top = _git_toplevel(_PKG_DIR)
            backup_top = _git_toplevel(repo)
            if backup_top is None or backup_top != repo:
                return  # must be its own repo root, not a subdir of another repo
            if main_top is not None and backup_top == main_top:
                return  # never push the main repository
            shutil.copytree(self.blocks_dir, repo / "blocks", dirs_exist_ok=True)
            shutil.copy2(self.state_file, repo / "chain_state.json")
            for cmd in [
                ["git", "add", "blocks/", "chain_state.json"],
                ["git", "commit", "-m", f"block #{block['height']}"],
                ["git", "push", "origin", "main"],
            ]:
                subprocess.run(cmd, cwd=str(repo), capture_output=True, timeout=15)
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
