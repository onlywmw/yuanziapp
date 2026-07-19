"""Merkle tree for Yuanzi Chain transactions."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def hash_tx(tx: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(tx)).hexdigest()


def merkle_root(transactions: List[Dict[str, Any]]) -> str:
    if not transactions:
        return hashlib.sha256(b"").hexdigest()
    hashes = [hash_tx(tx) for tx in transactions]
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])
        hashes = [
            hashlib.sha256((hashes[i] + hashes[i + 1]).encode()).hexdigest()
            for i in range(0, len(hashes), 2)
        ]
    return hashes[0]


def merkle_proof(txs: List[Dict[str, Any]], idx: int) -> List[Dict[str, str]]:
    if not txs or idx >= len(txs):
        return []
    hashes = [hash_tx(tx) for tx in txs]
    proof = []
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])
        sibling_idx = idx + 1 if idx % 2 == 0 else idx - 1
        proof.append({"sibling_hash": hashes[sibling_idx], "direction": "right" if idx % 2 == 0 else "left"})
        idx //= 2
        hashes = [hashlib.sha256((hashes[i] + hashes[i + 1]).encode()).hexdigest() for i in range(0, len(hashes), 2)]
    return proof


def verify_proof(tx_hash: str, proof: List[Dict[str, str]], root: str) -> bool:
    current = tx_hash
    for step in proof:
        sibling = step["sibling_hash"]
        current = hashlib.sha256((current + sibling).encode()).hexdigest() if step["direction"] == "right" else hashlib.sha256((sibling + current).encode()).hexdigest()
    return current == root
