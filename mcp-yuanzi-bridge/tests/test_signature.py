"""Tests for registry layered signatures (content / identity / full)."""

from __future__ import annotations

import copy

from registry import (
    compute_content_hash,
    compute_identity_hash,
    compute_signature,
)

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
    "ownership": {"author": "yuanziapp", "license": "MIT"},
}


def test_hashes_are_full_sha256():
    for value in (
        compute_signature(BASE_ATOM),
        compute_content_hash(BASE_ATOM),
        compute_identity_hash(BASE_ATOM),
    ):
        assert len(value) == 64
        int(value, 16)  # valid hex


def test_full_signature_includes_identity():
    other = copy.deepcopy(BASE_ATOM)
    other["atom_id"] = "com.example.clone"
    assert compute_signature(other) != compute_signature(BASE_ATOM)


def test_full_signature_includes_version():
    other = copy.deepcopy(BASE_ATOM)
    other["version"] = "2.0.0"
    assert compute_signature(other) != compute_signature(BASE_ATOM)


def test_full_signature_includes_ownership():
    other = copy.deepcopy(BASE_ATOM)
    other["ownership"]["license"] = "Apache-2.0"
    assert compute_signature(other) != compute_signature(BASE_ATOM)


def test_content_hash_detects_capability_clones():
    # identity 不同但能力相同的原子，content_hash 必须一致（用于查重）
    clone = copy.deepcopy(BASE_ATOM)
    clone["atom_id"] = "org.copy.sum"
    clone["version"] = "9.9.9"
    assert compute_content_hash(clone) == compute_content_hash(BASE_ATOM)
    assert compute_identity_hash(clone) != compute_identity_hash(BASE_ATOM)


def test_content_hash_changes_with_functions():
    other = copy.deepcopy(BASE_ATOM)
    other["purpose"]["functions"].append({"name": "multiply"})
    assert compute_content_hash(other) != compute_content_hash(BASE_ATOM)


def test_content_hash_changes_with_function_schema():
    other = copy.deepcopy(BASE_ATOM)
    other["purpose"]["functions"][0]["input"] = {"a": "number", "b": "number"}
    assert compute_content_hash(other) != compute_content_hash(BASE_ATOM)


def test_content_hash_stable_to_function_order():
    other = copy.deepcopy(BASE_ATOM)
    other["purpose"]["functions"] = list(reversed(other["purpose"]["functions"]))
    assert compute_content_hash(other) == compute_content_hash(BASE_ATOM)


def test_content_hash_changes_with_dependencies():
    other = copy.deepcopy(BASE_ATOM)
    other["architecture"]["dependencies"].append("com.example.extra")
    assert compute_content_hash(other) != compute_content_hash(BASE_ATOM)
