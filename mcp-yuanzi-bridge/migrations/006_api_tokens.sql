-- 006_api_tokens: API token 管理表（M6 任务 6.1，DESIGN_M6 §4）。
-- token 本体不落库，只存 SHA-256(token)；角色驱动 RBAC。

CREATE TABLE IF NOT EXISTS api_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash  TEXT UNIQUE NOT NULL,
    description TEXT,
    role        TEXT NOT NULL DEFAULT 'viewer',
    created_by  TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT,
    revoked_at  TEXT
);
