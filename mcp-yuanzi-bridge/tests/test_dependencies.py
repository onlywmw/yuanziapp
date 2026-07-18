"""Tests for registry.resolve_dependencies."""

from __future__ import annotations

import sqlite3

import pytest
from registry import ensure_registry_schema, resolve_dependencies, submit_atom


def _atom(atom_id, deps=()):
    return {
        "atom_id": atom_id,
        "name": atom_id,
        "version": "1.0.0",
        "description": "",
        # 功能名随 atom_id 变化：BUG-016 起同能力（同 content_hash）的
        # 不同 atom_id 会被判为重复能力而拒绝注册。
        "purpose": {"functions": [{"name": f"f_{atom_id}"}]},
        "architecture": {
            "type": "python_script",
            "runtime": "python3.12",
            "dependencies": list(deps),
        },
        "ownership": {"author": "test", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_registry_schema(c)
    yield c
    c.close()


def test_linear_chain_topological_order(conn):
    submit_atom(conn, _atom("com.example.c"))
    submit_atom(conn, _atom("com.example.b", deps=["com.example.c"]))
    submit_atom(conn, _atom("com.example.a", deps=["com.example.b"]))

    result = resolve_dependencies(conn, "com.example.a")
    assert result["ok"]
    assert result["order"] == ["com.example.c", "com.example.b", "com.example.a"]
    assert result["missing"] == []
    assert result["cycles"] == []


def test_missing_dependency_detected(conn):
    submit_atom(conn, _atom("com.example.a", deps=["com.example.ghost"]))

    result = resolve_dependencies(conn, "com.example.a")
    assert not result["ok"]
    assert result["missing"] == ["com.example.ghost"]
    assert result["order"] == ["com.example.a"]


def test_cycle_detected(conn):
    submit_atom(conn, _atom("com.example.a", deps=["com.example.b"]))
    submit_atom(conn, _atom("com.example.b", deps=["com.example.a"]))

    result = resolve_dependencies(conn, "com.example.a")
    assert not result["ok"]
    assert result["cycles"] == [["com.example.a", "com.example.b", "com.example.a"]]


def test_diamond_dependency_visits_once(conn):
    submit_atom(conn, _atom("com.example.d"))
    submit_atom(conn, _atom("com.example.b", deps=["com.example.d"]))
    submit_atom(conn, _atom("com.example.c", deps=["com.example.d"]))
    submit_atom(conn, _atom("com.example.a", deps=["com.example.b", "com.example.c"]))

    result = resolve_dependencies(conn, "com.example.a")
    assert result["ok"]
    assert result["order"].count("com.example.d") == 1
    assert result["order"][0] == "com.example.d"
    assert result["order"][-1] == "com.example.a"


def test_self_cycle_detected(conn):
    submit_atom(conn, _atom("com.example.a", deps=["com.example.a"]))

    result = resolve_dependencies(conn, "com.example.a")
    assert not result["ok"]
    assert result["cycles"] == [["com.example.a", "com.example.a"]]


def test_unknown_root_atom(conn):
    result = resolve_dependencies(conn, "com.example.ghost")
    assert not result["ok"]
    assert result["missing"] == ["com.example.ghost"]
    assert result["order"] == []
