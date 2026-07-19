"""Yuanzi Chain — local single-node blockchain for atom notarization.

See docs/DESIGN_ATOM_NOTARIZATION.md for the design.
"""

from yuanzi_chain.chain import YuanziChain, get_chain
from yuanzi_chain.merkle import hash_tx, merkle_proof, merkle_root, verify_proof

__all__ = [
    "YuanziChain",
    "get_chain",
    "hash_tx",
    "merkle_root",
    "merkle_proof",
    "verify_proof",
]
