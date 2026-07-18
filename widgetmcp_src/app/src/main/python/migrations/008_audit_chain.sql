-- 008_audit_chain: 审计哈希链（M6.4，DESIGN_M6 §3.5）。
-- 每行审计日志记录 chain_hash = SHA-256(prev_chain_hash + 本行内容)，
-- 任何篡改/删除中间行都会破坏链条，可用 verify_audit_chain() 检测。

ALTER TABLE atom_audit_log ADD COLUMN chain_hash TEXT;
