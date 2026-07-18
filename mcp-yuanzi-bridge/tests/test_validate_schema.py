"""Tests for jsonschema-based validate_atom."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from register_mcp_atoms import build_registry_atom, validate_atom

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "atom-registry-schema.json").read_text(
        encoding="utf-8"
    )
)

MCP_ATOMS = Path(__file__).resolve().parents[1] / "mcp_atoms.json"


def _valid_atom():
    return build_registry_atom(
        {
            "atom_id": "mcp.demo",
            "label": "Demo",
            "description": "demo atom",
            "capabilities": ["mcp/demo/ping"],
        }
    )


def test_valid_atom_passes():
    assert validate_atom(_valid_atom(), SCHEMA) == []


def test_missing_required_field_fails():
    atom = _valid_atom()
    del atom["name"]
    errors = validate_atom(atom, SCHEMA)
    assert any("name" in e for e in errors)


def test_bad_atom_id_pattern_fails():
    atom = _valid_atom()
    atom["atom_id"] = "not reverse domain!"
    errors = validate_atom(atom, SCHEMA)
    assert any("atom_id" in e for e in errors)


def test_bad_lifecycle_status_fails():
    atom = _valid_atom()
    atom["lifecycle"]["status"] = "flying"
    errors = validate_atom(atom, SCHEMA)
    assert any("lifecycle.status" in e for e in errors)


def test_probing_and_unreachable_are_valid_statuses():
    for status in ("probing", "unreachable"):
        atom = _valid_atom()
        atom["lifecycle"]["status"] = status
        assert validate_atom(atom, SCHEMA) == []


@pytest.mark.parametrize("index", range(61))
def test_all_real_mcp_atoms_validate(index):
    """mcp_atoms.json 里的每一个原子都必须通过 schema 校验。"""
    raw_atoms = json.loads(MCP_ATOMS.read_text(encoding="utf-8"))
    atom = build_registry_atom(raw_atoms[index])
    assert validate_atom(atom, SCHEMA) == [], atom["atom_id"]
