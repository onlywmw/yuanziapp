-- 004_function_embeddings: 函数级 embedding 表。
-- 为能力搜索（M5）做准备：每个原子的每个功能一条向量记录，
-- 同一 (atom_id, function_name, model) 组合唯一，换模型可并存。

CREATE TABLE IF NOT EXISTS function_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atom_id TEXT NOT NULL,
    function_name TEXT NOT NULL,
    text TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (atom_id, function_name, model)
);

CREATE INDEX IF NOT EXISTS idx_function_embeddings_atom
    ON function_embeddings(atom_id);
