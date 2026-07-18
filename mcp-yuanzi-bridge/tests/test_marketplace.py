"""Tests for the atom marketplace (M7 task 7.1)."""

from __future__ import annotations

import sqlite3

import pytest
from marketplace import (
    add_review,
    atom_rating,
    composite_score,
    list_reviews,
    marketplace_board,
)
from migrations import migrate
from registry import submit_atom


def _atom(atom_id, description="desc", examples=None, test_status="passed"):
    return {
        "atom_id": atom_id,
        "name": atom_id.split(".")[-1],
        "version": "1.0.0",
        "description": description,
        "purpose": {
            "functions": [{"name": f"f_{atom_id}"}],
            "examples": examples or [],
        },
        "architecture": {"type": "t", "runtime": "r", "dependencies": []},
        "ownership": {"author": "someone", "license": "MIT"},
        "classification": {"category": "Database"},
        "quality": {"test_status": test_status},
        "lifecycle": {"status": "registered"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    submit_atom(c, _atom("com.example.alpha"))
    submit_atom(c, _atom("com.example.beta"))
    yield c
    c.close()


def test_add_and_list_reviews(conn):
    assert add_review(conn, "com.example.alpha", "张三", 5, "稳定")["success"]
    assert add_review(conn, "com.example.alpha", "李四", 3, "文档少")["success"]

    reviews = list_reviews(conn, "com.example.alpha")
    assert len(reviews) == 2
    assert {r["author"] for r in reviews} == {"张三", "李四"}


def test_review_upsert_same_author(conn):
    add_review(conn, "com.example.alpha", "张三", 5)
    add_review(conn, "com.example.alpha", "张三", 2, "改主意了")
    reviews = list_reviews(conn, "com.example.alpha")
    assert len(reviews) == 1
    assert reviews[0]["rating"] == 2


def test_rating_summary(conn):
    add_review(conn, "com.example.alpha", "a", 5)
    add_review(conn, "com.example.alpha", "b", 4)
    add_review(conn, "com.example.alpha", "c", 3)
    rating = atom_rating(conn, "com.example.alpha")
    assert rating["average"] == 4.0
    assert rating["count"] == 3
    assert rating["distribution"] == {"5": 1, "4": 1, "3": 1}


def test_review_validation(conn):
    assert not add_review(conn, "com.example.alpha", "", 5)["success"]
    assert not add_review(conn, "com.example.alpha", "a", 0)["success"]
    assert not add_review(conn, "com.example.alpha", "a", 6)["success"]
    assert not add_review(conn, "com.example.ghost", "a", 5)["success"]


def test_composite_score_weights(conn):
    # 无评论 + 无探测 + 有 description + passed 测试：
    # 0.3*2.5 + 0.2*2.5 + 0.4*0 + 0.1*5 = 1.75
    result = composite_score(conn, "com.example.alpha")
    assert result["score"] == pytest.approx(1.75)

    # 加社区 5 分后：+ 0.4*5 = 3.75
    add_review(conn, "com.example.alpha", "a", 5)
    result = composite_score(conn, "com.example.alpha")
    assert result["score"] == pytest.approx(3.75)


def test_marketplace_tabs(conn):
    add_review(conn, "com.example.alpha", "a", 5)
    hot = marketplace_board(conn, tab="hot")
    assert hot[0]["atom_id"] == "com.example.alpha"  # 有评论的热度更高

    top = marketplace_board(conn, tab="top")
    assert top[0]["atom_id"] == "com.example.alpha"

    new = marketplace_board(conn, tab="new")
    assert len(new) == 2

    entry = hot[0]
    for key in ("atom_id", "name", "author", "score", "reviews", "functions"):
        assert key in entry
