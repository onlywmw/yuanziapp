# Yuanzi Schema 权威源定义

> **性质**: 规范文档 — 定义数据库 DDL 的唯一权威来源
> **规则**: 任何创建/修改表结构的代码必须引用本文档

---

## 核心原则

```
migrations/*.sql 是 agent.db 表结构的唯一权威来源。

其他文件中不得出现 CREATE TABLE 语句。
如果需要在代码中确保表存在，调用 migrate(conn)。
```

## 当前违规清单

以下文件包含不应存在的 CREATE TABLE，是技术债务：

| 文件 | 行数 | 创建的表 | 处理方式 |
|------|------|----------|----------|
| `registry.py:ensure_registry_schema()` | ~116-185 | atom_registry, atom_audit_log, atom_versions | **删除 DDL，改为调用 migrate(conn)** |
| `register_mcp_atoms.py:sync_atoms_table()` | ~367-379 | atoms (legacy) | **删除 CREATE TABLE，atoms 已改为 VIEW** |
| `insert_atoms.py` | ~26-38 | atoms (legacy) | **删除 CREATE TABLE** |
| `import_mcp_servers.py` | ~139-151 | atoms (legacy) | **删除 CREATE TABLE** |

共计 **4 个文件，3 种创建方式**，管理同一个数据库的表结构。

## 权威源结构

```
mcp-yuanzi-bridge/migrations/
├── 001_init.sql              # atom_registry + atom_audit_log
├── 002_atoms_view.sql        # atoms VIEW (替代 legacy TABLE)
├── 003_atom_versions.sql     # atom_versions 表
├── 004_function_embeddings.sql # atom_embeddings 表 (M5)
└── 005_content_hash_columns.sql # content_hash/identity_hash 物理列 (M6)
```

每个迁移文件是幂等的（CREATE TABLE IF NOT EXISTS / ALTER TABLE 带存在检查）。

## 版本跟踪

```
单一跟踪表: schema_migrations

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    description TEXT,
    applied_at  TEXT NOT NULL
);

废弃: registry_meta 表（与 schema_migrations 功能重叠）
```

## 迁移规则

1. 新迁移 = 新 `.sql` 文件，编号递增
2. 迁移文件必须幂等（可重复执行不报错）
3. 迁移文件不可修改（已应用的迁移就是历史记录）
4. 新增列用 ALTER TABLE ADD COLUMN
5. 修改列/删列 = 新迁移 + 数据回填
6. 禁止在迁移中写业务逻辑（.sql 文件只包含 DDL）

## atoms 表到 VIEW 的迁移路径

```
状态 A (当前, 有冲突):
  - 002_atoms_view.sql 创建 atoms VIEW
  - register_mcp_atoms.py:sync_atoms_table() 向 atoms TABLE 写入
  - insert_atoms.py 向 atoms TABLE 写入
  → VIEW 被 TABLE 覆盖，写入成功但读取不到视图数据

状态 B (目标):
  - atoms 是 VIEW，基于 atom_registry 实时查询
  - 所有代码只读取 atoms，不写入
  - sync_atoms_table() 删除（atom_registry 是唯一写入目标）
  - insert_atoms.py / import_mcp_servers.py 改用 registry.submit_atom()
```

---

> **本文档是 Schema 的"宪法"**。任何 CREATE TABLE 出现在 migrations/ 之外 = 违规。
