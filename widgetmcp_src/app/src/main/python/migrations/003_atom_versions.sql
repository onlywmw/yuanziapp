-- 003_atom_versions: 原子版本化表。
-- atom_registry 只保存每个原子的当前版本；atom_versions 保存每一次
-- 提交的内容快照（含分层签名），支持版本回溯与回滚。

CREATE TABLE IF NOT EXISTS atom_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atom_id TEXT NOT NULL,
    version TEXT NOT NULL,
    name TEXT,
    description TEXT,
    purpose_json TEXT,
    architecture_json TEXT,
    ownership_json TEXT,
    classification_json TEXT,
    compliance_json TEXT,
    quality_json TEXT,
    runtime_json TEXT,
    signature_hash TEXT,
    content_hash TEXT,
    identity_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (atom_id, version)
);

CREATE INDEX IF NOT EXISTS idx_atom_versions_atom_id ON atom_versions(atom_id);

-- 回填：把现有注册原子的当前版本归档为初始版本记录。
INSERT OR IGNORE INTO atom_versions (
    atom_id, version, name, description, purpose_json, architecture_json,
    ownership_json, classification_json, compliance_json, quality_json,
    runtime_json, signature_hash, created_at, updated_at
)
SELECT
    atom_id, version, name, description, purpose_json, architecture_json,
    ownership_json, classification_json, compliance_json, quality_json,
    runtime_json, signature_hash,
    COALESCE(created_at, ''), COALESCE(updated_at, '')
FROM atom_registry;
