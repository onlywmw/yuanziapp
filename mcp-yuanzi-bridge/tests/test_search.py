"""Tests for semantic function search (M5 task 5.2)."""

from __future__ import annotations

import sqlite3

import pytest
from embeddings import (
    MockEmbeddingProvider,
    cosine_similarity,
    embed_atom_functions,
    search_functions,
)
from migrations import migrate
from registry import review_atom, submit_atom


def _atom(atom_id, functions):
    return {
        "atom_id": atom_id,
        "name": atom_id.split(".")[-1],
        "version": "1.0.0",
        "description": "",
        "purpose": {"functions": [{"name": n, "description": d} for n, d in functions]},
        "architecture": {"type": "t", "runtime": "r"},
        "ownership": {"author": "t", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    submit_atom(c, _atom("com.example.math", [("sum", "add two numbers together")]))
    submit_atom(c, _atom("com.example.fs", [("read_file", "read a file from disk")]))
    submit_atom(c, _atom("com.example.net", [("http_get", "fetch a url over http")]))
    for aid in ("com.example.math", "com.example.fs", "com.example.net"):
        review_atom(c, aid, approved=True)
        embed_atom_functions(c, aid, MockEmbeddingProvider())
    yield c
    c.close()


def test_cosine_similarity_basics():
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1, 0], [1, 0, 0]) == 0.0  # 维度不匹配


def test_search_ranks_relevant_first(conn):
    results = search_functions(conn, "add numbers", MockEmbeddingProvider())
    assert results
    assert results[0]["function_name"] == "sum"
    assert results[0]["atom_id"] == "com.example.math"
    # 相似查询的分数必须高于无关函数
    scores = {r["function_name"]: r["score"] for r in results}
    assert scores["sum"] > scores["http_get"]


def test_search_enriches_atom_info(conn):
    results = search_functions(conn, "read file", MockEmbeddingProvider())
    top = results[0]
    assert top["function_name"] == "read_file"
    assert top["status"] == "registered"
    assert top["atom_name"] == "fs"


def test_search_limit(conn):
    results = search_functions(conn, "anything", MockEmbeddingProvider(), limit=2)
    assert len(results) <= 2


def test_search_min_score_filter(conn):
    all_results = search_functions(conn, "add numbers", MockEmbeddingProvider())
    filtered = search_functions(
        conn, "add numbers", MockEmbeddingProvider(), min_score=0.99
    )
    assert len(filtered) <= len(all_results)
    assert all(r["score"] >= 0.99 for r in filtered)


def test_search_empty_db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    assert search_functions(c, "x", MockEmbeddingProvider()) == []
    c.close()


def test_search_negative_limit_returns_empty(conn):
    """M5 review: 负 limit 会被 Python 切片解释为"去掉尾部 N 条"，
    静默返回结果；必须按空结果处理。"""
    assert (
        search_functions(conn, "add numbers", MockEmbeddingProvider(), limit=-1) == []
    )


def test_search_zero_vector_query_no_crash(conn):
    """M5 review: 查询无任何 [a-z0-9] token 时 mock 产生零向量，
    余弦必须安全返回 0 分而不是除零崩溃。"""
    results = search_functions(conn, "！！！", MockEmbeddingProvider())
    assert isinstance(results, list)
    assert all(r["score"] == 0.0 for r in results)
