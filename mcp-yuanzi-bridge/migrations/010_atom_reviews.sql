-- 010_atom_reviews: 原子市场评分与评论（M7 任务 7.1）。
-- 同一作者对同一原子一条评论（更新即改分），UNIQUE(atom_id, author)。

CREATE TABLE IF NOT EXISTS atom_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atom_id TEXT NOT NULL,
    author TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (atom_id, author)
);

CREATE INDEX IF NOT EXISTS idx_atom_reviews_atom ON atom_reviews(atom_id);
