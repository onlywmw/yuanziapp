"""Tests for registry.compute_signature."""

from __future__ import annotations

import copy

from registry import compute_signature

BASE_ATOM = {
    "atom_id": "com.example.sum",
    "name": "Sum",
    "version": "1.0.0",
    "description": "adds numbers",
    "purpose": {"functions": [{"name": "sum"}, {"name": "sum_many"}]},
    "architecture": {
        "type": "python_script",
        "runtime": "python3.12",
        "interface": "std-atom-http-v1",
        "dependencies": ["com.example.base"],
    },
}


def test_signature_is_full_sha256():
    sig = compute_signature(BASE_ATOM)
    assert len(sig) == 64
    int(sig, 16)  # valid hex


def test_signature_ignores_identity_fields():
    other = copy.deepcopy(BASE_ATOM)
    other["atom_id"] = "com.example.clone"
    other["name"] = "Clone"
    other["version"] = "9.9.9"
    other["description"] = "totally different text"
    assert compute_signature(other) == compute_signature(BASE_ATOM)


def test_signature_detects_capability_clones():
    # two atoms with identical capabilities must collide (dedup)
    clone = copy.deepcopy(BASE_ATOM)
    clone["atom_id"] = "org.copy.sum"
    assert compute_signature(clone) == compute_signature(BASE_ATOM)


def test_signature_changes_with_functions():
    other = copy.deepcopy(BASE_ATOM)
    other["purpose"]["functions"].append({"name": "multiply"})
    assert compute_signature(other) != compute_signature(BASE_ATOM)


def test_signature_stable_to_function_order():
    other = copy.deepcopy(BASE_ATOM)
    other["purpose"]["functions"] = list(reversed(other["purpose"]["functions"]))
    assert compute_signature(other) == compute_signature(BASE_ATOM)


def test_signature_changes_with_dependencies():
    other = copy.deepcopy(BASE_ATOM)
    other["architecture"]["dependencies"].append("com.example.extra")
    assert compute_signature(other) != compute_signature(BASE_ATOM)
