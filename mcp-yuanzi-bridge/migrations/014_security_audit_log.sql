-- 014_security_audit_log: 认证/授权拒绝事件审计（BUG-037）。
-- 401（Missing/Invalid token）与 403（角色不足）此前无任何落库记录。
-- 只记拒绝事件；subject 为主体标识（dev-mode/env-token/token-{id}/anonymous），
-- 绝不记录 token 本体。

CREATE TABLE IF NOT EXISTS security_audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,
    route       TEXT NOT NULL,
    method      TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
