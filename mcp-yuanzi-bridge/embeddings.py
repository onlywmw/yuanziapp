#!/usr/bin/env python3
"""函数级 embedding 生成（M5 任务 5.1）。

Provider 抽象：
- MockEmbeddingProvider：离线确定性 hash bag-of-words，供测试/CI/无网环境
- OpenAIEmbeddingProvider：OpenAI 兼容 /embeddings 接口，生产用，
  通过环境变量 EMBEDDING_API_BASE / EMBEDDING_API_KEY / EMBEDDING_MODEL 配置

向量存入 function_embeddings 表（迁移 004），同一功能换模型可并存。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import urllib.request
from typing import Any, Dict, List

from registry import get_atom, list_atoms, now_iso

EMBEDDINGS_TABLE = "function_embeddings"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def function_text(func: Dict[str, Any]) -> str:
    """把功能定义拼成用于 embedding 的文本。"""
    name = func.get("name", "")
    description = func.get("description", "")
    return f"{name}: {description}".strip().strip(":")


class MockEmbeddingProvider:
    """离线确定性 embedding：token hash 映射到固定维度后 L2 归一化。

    不具备真实语义，但相似文本会得到相似向量，足以打通存储/检索链路。
    """

    name = "mock"
    model = "hash-bow-v1"

    def __init__(self, dim: int = 128):
        self.dim = dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> List[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[slot] += sign
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [round(v / norm, 6) for v in vector]


class OpenAIEmbeddingProvider:
    """OpenAI 兼容 embedding 接口（/v1/embeddings）。"""

    name = "openai"

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ):
        self.api_base = (api_base or os.environ.get("EMBEDDING_API_BASE") or "").rstrip(
            "/"
        )
        self.api_key = api_key or os.environ.get("EMBEDDING_API_KEY") or ""
        self.model = model or os.environ.get("EMBEDDING_MODEL") or ""
        self.timeout = timeout
        if not self.api_base or not self.model:
            raise ValueError(
                "OpenAI provider requires api_base and model "
                "(or EMBEDDING_API_BASE / EMBEDDING_MODEL env vars)"
            )

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        request = urllib.request.Request(
            f"{self.api_base}/embeddings",
            data=json.dumps({"model": self.model, "input": texts}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        data = sorted(payload["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]


def get_provider(name: str, **kwargs: Any):
    """按名称构造 provider：mock / openai。"""
    if name == "mock":
        return MockEmbeddingProvider(**kwargs)
    if name == "openai":
        return OpenAIEmbeddingProvider(**kwargs)
    raise ValueError(f"Unknown embedding provider: {name!r}")


def _upsert_embedding(
    conn: sqlite3.Connection,
    atom_id: str,
    function_name: str,
    text: str,
    provider: Any,
    vector: List[float],
) -> None:
    now = now_iso()
    existing = conn.execute(
        f"SELECT created_at FROM {EMBEDDINGS_TABLE} "
        "WHERE atom_id = ? AND function_name = ? AND model = ?",
        (atom_id, function_name, provider.model),
    ).fetchone()
    created_at = existing[0] if existing else now
    conn.execute(
        f"""
        INSERT INTO {EMBEDDINGS_TABLE}
        (atom_id, function_name, text, provider, model, dim, vector_json,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(atom_id, function_name, model) DO UPDATE SET
            text=excluded.text,
            provider=excluded.provider,
            dim=excluded.dim,
            vector_json=excluded.vector_json,
            updated_at=excluded.updated_at
        """,
        (
            atom_id,
            function_name,
            text,
            provider.name,
            provider.model,
            len(vector),
            json.dumps(vector),
            created_at,
            now,
        ),
    )


def embed_atom_functions(conn: sqlite3.Connection, atom_id: str, provider: Any) -> int:
    """为单个原子的全部功能生成/更新 embedding，返回处理数量。"""
    atom = get_atom(conn, atom_id)
    if not atom:
        raise ValueError(f"Atom '{atom_id}' not found")
    functions = atom.get("purpose", {}).get("functions", []) or []
    functions = [f for f in functions if f.get("name")]

    # 清理已删除/改名函数残留的旧 embedding（同 atom 同 model 范围内），
    # 否则 search 仍能命中已不存在的函数。
    names = [f["name"] for f in functions]
    if names:
        placeholders = ",".join("?" for _ in names)
        conn.execute(
            f"DELETE FROM {EMBEDDINGS_TABLE} "
            f"WHERE atom_id = ? AND model = ? "
            f"AND function_name NOT IN ({placeholders})",
            (atom_id, provider.model, *names),
        )
    else:
        conn.execute(
            f"DELETE FROM {EMBEDDINGS_TABLE} WHERE atom_id = ? AND model = ?",
            (atom_id, provider.model),
        )
    if not functions:
        conn.commit()
        return 0

    texts = [function_text(f) for f in functions]
    vectors = provider.embed(texts)
    if len(vectors) != len(texts):
        raise ValueError(
            f"Provider returned {len(vectors)} vectors for {len(texts)} texts"
        )
    for func, text, vector in zip(functions, texts, vectors):
        _upsert_embedding(conn, atom_id, func["name"], text, provider, vector)
    conn.commit()
    return len(functions)


def embed_all_functions(conn: sqlite3.Connection, provider: Any) -> Dict[str, int]:
    """为注册表中所有原子生成 embedding，返回 {atom_id: count}。"""
    result: Dict[str, int] = {}
    for atom in list_atoms(conn):
        result[atom["atom_id"]] = embed_atom_functions(conn, atom["atom_id"], provider)
    return result


def list_function_embeddings(
    conn: sqlite3.Connection, atom_id: str | None = None, model: str | None = None
) -> List[Dict[str, Any]]:
    """查询已存的 embedding（不含向量本体，避免大结果集）。"""
    query = (
        f"SELECT atom_id, function_name, text, provider, model, dim, updated_at "
        f"FROM {EMBEDDINGS_TABLE} WHERE 1=1"
    )
    params: List[Any] = []
    if atom_id:
        query += " AND atom_id = ?"
        params.append(atom_id)
    if model:
        query += " AND model = ?"
        params.append(model)
    query += " ORDER BY atom_id, function_name"
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """余弦相似度。假定向量已归一化时退化为点积（仍做完整计算保证正确）。"""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def search_functions(
    conn: sqlite3.Connection,
    query: str,
    provider: Any,
    limit: int = 10,
    model: str | None = None,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """语义搜索：把 query 编码后与库中函数向量做余弦相似度排序。

    返回按分数降序的前 limit 条，含 atom 名称/状态/分类信息。
    维度不匹配的向量（不同 provider 混存）自动跳过。
    """
    if limit <= 0:
        return []
    query_vector = provider.embed([query])[0]
    model = model or provider.model

    rows = conn.execute(
        f"SELECT atom_id, function_name, text, vector_json "
        f"FROM {EMBEDDINGS_TABLE} WHERE model = ?",
        (model,),
    ).fetchall()

    scored: List[Dict[str, Any]] = []
    for atom_id, function_name, text, vector_json in rows:
        vector = json.loads(vector_json)
        if len(vector) != len(query_vector):
            continue
        score = cosine_similarity(query_vector, vector)
        if score >= min_score:
            scored.append(
                {
                    "atom_id": atom_id,
                    "function_name": function_name,
                    "text": text,
                    "score": round(score, 6),
                }
            )
    scored.sort(key=lambda item: item["score"], reverse=True)

    results: List[Dict[str, Any]] = []
    for item in scored[:limit]:
        atom = get_atom(conn, item["atom_id"]) or {}
        item["atom_name"] = atom.get("name", "")
        item["status"] = atom.get("lifecycle", {}).get("status", "")
        item["category"] = atom.get("classification", {}).get("category", "")
        results.append(item)
    return results
