"""Tests for atom combination recommendations (M5 task 5.3)."""

from __future__ import annotations

import sqlite3

import pytest
from migrations import migrate
from recommend import find_dependents, recommend_combination, recommend_for_atom
from registry import submit_atom


def _atom(atom_id, deps=(), category="Database"):
    return {
        "atom_id": atom_id,
        "name": atom_id.split(".")[-1],
        "version": "1.0.0",
        "description": "",
        "purpose": {"functions": [{"name": f"f_{atom_id}"}]},
        "architecture": {
            "type": "t",
            "runtime": "r",
            "dependencies": list(deps),
        },
        "ownership": {"author": "t", "license": "MIT"},
        "classification": {"category": category},
        "lifecycle": {"status": "registered"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    submit_atom(c, _atom("com.example.base", category="Database"))
    submit_atom(
        c, _atom("com.example.cache", deps=["com.example.base"], category="Database")
    )
    submit_atom(
        c,
        _atom(
            "com.example.api", deps=["com.example.cache"], category="Cloud & Storage"
        ),
    )
    submit_atom(c, _atom("com.example.other", category="Observability"))
    yield c
    c.close()


def test_find_dependents(conn):
    assert find_dependents(conn, "com.example.base") == ["com.example.cache"]
    assert find_dependents(conn, "com.example.other") == []


def test_recommend_dependency_outranks_category(conn):
    recs = recommend_for_atom(conn, "com.example.api")
    by_id = {r["atom_id"]: r for r in recs}
    # cache 是直接依赖（1.0），必须排第一
    assert recs[0]["atom_id"] == "com.example.cache"
    assert "dependency" in recs[0]["reasons"]
    # base 不在 api 的直接依赖里，但类别信号不会误伤不存在的关系
    assert "com.example.other" not in by_id or by_id["com.example.other"]["score"] < 1.0


def test_recommend_dependent_and_category(conn):
    recs = recommend_for_atom(conn, "com.example.base")
    by_id = {r["atom_id"]: r for r in recs}
    # cache 既是被依赖方（0.8）又同类（0.3）= 1.1，权重叠加
    assert by_id["com.example.cache"]["score"] == pytest.approx(1.1)
    assert set(by_id["com.example.cache"]["reasons"]) == {
        "dependent",
        "same_category",
    }


def test_recommend_excludes_self_and_missing(conn):
    recs = recommend_for_atom(conn, "com.example.base")
    assert all(r["atom_id"] != "com.example.base" for r in recs)


def test_recommend_unknown_atom(conn):
    with pytest.raises(ValueError, match="not found"):
        recommend_for_atom(conn, "com.example.ghost")


def test_combination_topological_closure(conn):
    result = recommend_combination(conn, "com.example.api")
    assert result["ok"]
    order = [c["atom_id"] for c in result["combination"]]
    assert order == ["com.example.base", "com.example.cache", "com.example.api"]


def test_combination_with_missing_dep(conn):
    submit_atom(conn, _atom("com.example.broken", deps=["com.example.ghost"]))
    result = recommend_combination(conn, "com.example.broken")
    assert not result["ok"]
    assert result["missing"] == ["com.example.ghost"]


def test_recommend_limit(conn):
    for i in range(6):
        submit_atom(conn, _atom(f"com.example.extra{i}", category="Database"))
    recs = recommend_for_atom(conn, "com.example.base", limit=3)
    assert len(recs) == 3
