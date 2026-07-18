-- 006_api_tokens: API 认证 token 与安全审计（BUG-025 / M6.1a/1b/2a）。
-- api_tokens 只存 SHA-256(token) 哈希，明文永不落库；
-- registry_meta 是 kv 配置表（key='api_token' 为静态引导 token 来源之一）；
-- security_audit_log 记录 401/403 安全事件（AC-13）。

CREATE TABLE IF NOT EXISTS api_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash  TEXT UNIQUE NOT NULL,          -- SHA-256(token)
    description TEXT,
    role        TEXT NOT NULL DEFAULT 'viewer', -- admin/registry/viewer/probe
    created_by  TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT,                          -- NULL = 永不过期
    revoked_at  TEXT                           -- NULL = 有效
);

CREATE TABLE IF NOT EXISTS registry_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS security_audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    subject    TEXT,                           -- 主体标识（不记明文 token）
    method     TEXT,
    route      TEXT,
    result     INTEGER NOT NULL,               -- 401 / 403
    detail     TEXT,
    created_at TEXT NOT NULL
);
