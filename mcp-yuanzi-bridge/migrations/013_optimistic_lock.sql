-- 013_optimistic_lock: atom_registry 乐观锁（ISOLATION_HARDENING_PLAN 加固2）。
-- 读-改-写路径（probe 等）写入时带 version_counter 条件，
-- 并发写入互相覆盖时抛 ConcurrentModificationError 并重试。

ALTER TABLE atom_registry ADD COLUMN version_counter INTEGER NOT NULL DEFAULT 0;
