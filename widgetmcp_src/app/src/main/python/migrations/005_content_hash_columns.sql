-- 005_content_hash_columns: content_hash / identity_hash 落库（BUG-016）。
-- 能力指纹持久化后，submit_atom 才能做跨 atom_id 的能力去重。
-- 历史行的 hash 由 registry.backfill_content_hashes() 回填（Python 计算）。

ALTER TABLE atom_registry ADD COLUMN content_hash TEXT;
ALTER TABLE atom_registry ADD COLUMN identity_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_atom_registry_content_hash
    ON atom_registry(content_hash);
