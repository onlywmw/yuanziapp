-- 001_init: 注册中心 v2 基线表结构。
-- 已存在 atom_registry 的旧库会被 migrate() 标记为 baseline，跳过本文件。

CREATE TABLE IF NOT EXISTS atom_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atom_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0.0',
    description TEXT,
    purpose_json TEXT NOT NULL,
    architecture_json TEXT NOT NULL,
    ownership_json TEXT NOT NULL,
    classification_json TEXT,
    compliance_json TEXT,
    quality_json TEXT,
    runtime_json TEXT,
    lifecycle_json TEXT NOT NULL,
    signature_hash TEXT UNIQUE NOT NULL,
    signature_algorithm TEXT NOT NULL DEFAULT 'sha256',
    alias TEXT,
    content_hash TEXT,
    identity_hash TEXT,
    created_at TEXT,
    submitted_at TEXT,
    registered_at TEXT,
    updated_at TEXT,
    reviewed_at TEXT,
    reviewed_by TEXT,
    review_comments TEXT,
    review_score REAL
);

CREATE TABLE IF NOT EXISTS atom_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atom_id TEXT NOT NULL,
    action TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    actor TEXT,
    detail TEXT,
    created_at TEXT
);
