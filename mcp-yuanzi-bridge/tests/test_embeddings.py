"""Tests for function embedding generation (mock provider + stubbed HTTP)."""

from __future__ import annotations

import json
import math
import sqlite3

import pytest
from embeddings import (
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    embed_all_functions,
    embed_atom_functions,
    function_text,
    get_provider,
    list_function_embeddings,
)
from migrations import migrate
from registry import submit_atom


def _atom(atom_id="com.example.sum", functions=("sum", "sum_many")):
    return {
        "atom_id": atom_id,
        "name": atom_id,
        "version": "1.0.0",
        "description": "",
        "purpose": {
            "functions": [{"name": f, "description": f"does {f}"} for f in functions]
        },
        "architecture": {"type": "python_script", "runtime": "python3.12"},
        "ownership": {"author": "test", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def test_mock_provider_deterministic_and_normalized():
    provider = MockEmbeddingProvider(dim=64)
    v1 = provider.embed(["sum two numbers"])[0]
    v2 = provider.embed(["sum two numbers"])[0]
    assert v1 == v2
    assert len(v1) == 64
    norm = math.sqrt(sum(x * x for x in v1))
    assert abs(norm - 1.0) < 1e-3


def test_mock_provider_similar_texts_closer_than_distant():
    provider = MockEmbeddingProvider(dim=256)

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b))

    a = provider.embed(["sum two numbers"])[0]
    b = provider.embed(["sum two integers"])[0]
    c = provider.embed(["delete kubernetes pod"])[0]
    assert cosine(a, b) > cosine(a, c)


def test_embed_atom_functions_stores_rows(conn):
    submit_atom(conn, _atom())
    count = embed_atom_functions(conn, "com.example.sum", MockEmbeddingProvider())
    assert count == 2

    rows = list_function_embeddings(conn, atom_id="com.example.sum")
    assert len(rows) == 2
    assert rows[0]["model"] == "hash-bow-v1"
    assert rows[0]["dim"] == 128
    assert "sum" in rows[0]["text"]

    stored = conn.execute(
        "SELECT vector_json FROM function_embeddings WHERE function_name = 'sum'"
    ).fetchone()[0]
    assert len(json.loads(stored)) == 128


def test_embed_is_idempotent_upsert(conn):
    submit_atom(conn, _atom())
    provider = MockEmbeddingProvider()
    embed_atom_functions(conn, "com.example.sum", provider)
    embed_atom_functions(conn, "com.example.sum", provider)
    rows = list_function_embeddings(conn, atom_id="com.example.sum")
    assert len(rows) == 2  # upsert，不重复


def test_embed_all_functions(conn):
    submit_atom(conn, _atom("com.example.a", functions=("fa",)))
    submit_atom(conn, _atom("com.example.b", functions=("fb1", "fb2")))
    counts = embed_all_functions(conn, MockEmbeddingProvider())
    assert counts == {"com.example.a": 1, "com.example.b": 2}


def test_embed_unknown_atom_raises(conn):
    with pytest.raises(ValueError, match="not found"):
        embed_atom_functions(conn, "com.example.ghost", MockEmbeddingProvider())


def test_same_function_two_models_coexist(conn):
    submit_atom(conn, _atom())

    class OtherProvider(MockEmbeddingProvider):
        model = "hash-bow-v2"

    embed_atom_functions(conn, "com.example.sum", MockEmbeddingProvider())
    embed_atom_functions(conn, "com.example.sum", OtherProvider())
    rows = list_function_embeddings(conn, atom_id="com.example.sum")
    assert {r["model"] for r in rows} == {"hash-bow-v1", "hash-bow-v2"}


def test_embed_removes_stale_function_rows(conn):
    """M5 review: 原子升级后函数被删除，重新 embed 必须清理旧函数的行，
    否则 search 仍能搜到已不存在的函数。"""
    submit_atom(conn, _atom())
    provider = MockEmbeddingProvider()
    embed_atom_functions(conn, "com.example.sum", provider)

    updated = _atom(functions=("sum",))
    updated["version"] = "1.1.0"
    submit_atom(conn, updated)
    embed_atom_functions(conn, "com.example.sum", provider)

    rows = list_function_embeddings(conn, atom_id="com.example.sum")
    assert [r["function_name"] for r in rows] == ["sum"]


def test_embed_clears_rows_when_functions_removed(conn):
    """M5 review: 原子功能清空后，旧 embedding 行也应一并清除。"""
    submit_atom(conn, _atom())
    provider = MockEmbeddingProvider()
    embed_atom_functions(conn, "com.example.sum", provider)

    updated = _atom(functions=())
    updated["version"] = "1.1.0"
    submit_atom(conn, updated)
    count = embed_atom_functions(conn, "com.example.sum", provider)

    assert count == 0
    assert list_function_embeddings(conn, atom_id="com.example.sum") == []


def test_embed_provider_vector_count_mismatch_raises(conn):
    """M5 review: provider 返回的向量数与请求文本数不一致时，
    zip 静默截断会导致 count 虚高、数据缺失，必须显式报错。"""

    class ShortProvider(MockEmbeddingProvider):
        def embed(self, texts):
            return super().embed(texts)[:1]

    submit_atom(conn, _atom())
    with pytest.raises(ValueError, match="vector"):
        embed_atom_functions(conn, "com.example.sum", ShortProvider())


def test_function_text():
    assert function_text({"name": "sum", "description": "adds"}) == "sum: adds"
    assert function_text({"name": "sum"}) == "sum"


def test_get_provider_unknown():
    with pytest.raises(ValueError, match="Unknown"):
        get_provider("wat")


def test_openai_provider_requires_config(monkeypatch):
    monkeypatch.delenv("EMBEDDING_API_BASE", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    with pytest.raises(ValueError, match="api_base"):
        OpenAIEmbeddingProvider()


def test_openai_provider_calls_api(conn, monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": [
                        {"index": 0, "embedding": [0.1, 0.2]},
                        {"index": 1, "embedding": [0.3, 0.4]},
                    ]
                }
            ).encode()

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["auth"] = request.headers["Authorization"]
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAIEmbeddingProvider(
        api_base="http://fake.local/v1", api_key="sk-test", model="embed-1"
    )
    vectors = provider.embed(["hello", "world"])

    assert captured["url"] == "http://fake.local/v1/embeddings"
    assert captured["body"] == {"model": "embed-1", "input": ["hello", "world"]}
    assert captured["auth"] == "Bearer sk-test"
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]

    submit_atom(conn, _atom())
    count = embed_atom_functions(conn, "com.example.sum", provider)
    assert count == 2
    rows = list_function_embeddings(conn, model="embed-1")
    assert len(rows) == 2
    assert rows[0]["dim"] == 2
