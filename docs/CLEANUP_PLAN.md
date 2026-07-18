# 原子入库链路清理方案

> **作者**: Arch
> **日期**: 2026-07-18
> **目标**: 消除 Schema 三源分裂，拆除遗留炸弹，使原子拆分→注册→入库完全顺畅

---

## 清理前状态

```
mcp-yuanzi-bridge/
├── registry.py              ← 80 行冗余 DDL (重复 migrations/ 定义)
├── register_mcp_atoms.py    ← ✅ 主入口，已清理
├── insert_atoms.py          ← 💣 写入废弃 atoms TABLE
├── import_mcp_servers.py    ← 💣 写入废弃 atoms TABLE
└── migrations/
    ├── 001_init.sql         ← ✅ 权威 DDL: atom_registry + atom_audit_log
    ├── 002_atoms_view.sql   ← ✅ DROP TABLE atoms; CREATE VIEW atoms
    ├── 003_atom_versions.sql← ✅ atom_versions 表
    └── 004_function_embeddings.sql ← ✅ M5 嵌入表
```

**问题**: 同一个数据库 `agent.db` 的表结构定义在 5 个不同文件中。

---

## 清理步骤

### 步骤 1: 移除 `insert_atoms.py`

```
当前: 直接往 atoms 表写数据 + 创建表
清理: 整个文件删除

理由:
  - atoms 已改为 VIEW（002_atoms_view.sql），不可写入
  - 功能已被 register_mcp_atoms.py 完全替代
  - 无其他文件引用（仅测试文件 test_insert_atoms.py）
```

### 步骤 2: 移除 `import_mcp_servers.py`

```
当前: 扫描 MCP 服务器目录 → 往 atoms 表写入
清理: 整个文件删除

理由:
  - 功能已被 register_mcp_atoms.py 完全替代
  - 批量导入统一走 register_mcp_atoms
  - 无其他文件引用（仅测试文件 test_import_mcp.py）
```

### 步骤 3: 精简 `registry.py:ensure_registry_schema()`

```
当前:
  def ensure_registry_schema(conn):
      CREATE TABLE IF NOT EXISTS atom_registry (...)
      CREATE TABLE IF NOT EXISTS atom_audit_log (...)
      CREATE TABLE IF NOT EXISTS atom_versions (...)
      conn.commit()

清理后:
  def ensure_registry_schema(conn):
      migrate(conn)  # 唯一入口

理由:
  - DDL 权威源是 migrations/*.sql
  - registry.py 不应重复定义表结构
  - 新增列/表只在 SQL 迁移文件中添加
```

### 步骤 4: 同步清理测试文件

```
待删除:
  mcp-yuanzi-bridge/tests/test_insert_atoms.py  ← 测试已删除的 insert_atoms.py
  mcp-yuanzi-bridge/tests/test_import_mcp.py    ← 测试已删除的 import_mcp_servers.py

待更新:
  mcp-yuanzi-bridge/tests/test_migrations.py    ← 确认只使用 migrate() API，不依赖 MigrationRunner
```

### 步骤 5: 添加 atoms VIEW 完整性测试

```
新增: mcp-yuanzi-bridge/tests/test_atoms_view.py

测试内容:
  test_atoms_view_exists              ← 确认 atoms 是 VIEW 不是 TABLE
  test_view_mirrors_registry          ← INSERT atom_registry → atoms VIEW 自动出现
  test_view_is_read_only              ← INSERT INTO atoms → 报错
  test_view_columns_match_legacy      ← label, atom_type, endpoint, capabilities 列存在
```

---

## 清理后状态

```
mcp-yuanzi-bridge/
├── registry.py              ← 精简: ensure_registry_schema() = migrate(conn)
├── register_mcp_atoms.py    ← 主入口 (不变)
└── migrations/              ← DDL 唯一权威源
    ├── 001_init.sql
    ├── 002_atoms_view.sql
    ├── 003_atom_versions.sql
    └── 004_function_embeddings.sql

原子入库路径 (唯一条):
  mcp_atoms.json → register_mcp_atoms.py → submit_atom() → agent.db
                                               │
                                         migrate(conn) ← 唯一 DDL 入口
```

---

## 影响评估

| 文件 | 动作 | 影响 |
|------|------|------|
| insert_atoms.py | 删除 | 无影响，无调用方 |
| import_mcp_servers.py | 删除 | 无影响，无调用方 |
| test_insert_atoms.py | 删除 | 24 个测试移除 |
| test_import_mcp.py | 删除 | 15 个测试移除 |
| registry.py | 精简 80 行 DDL | migrate(conn) 替代 |
| test_migrations.py | 更新 | 适配统一 API |
| test_atoms_view.py | 新增 | 保护 VIEW 不被回退为 TABLE |

---

## 验证方案

```bash
# 1. 确认原子注册功能正常
python mcp-yuanzi-bridge/register_mcp_atoms.py
# → Registered 61/61 atoms; failed: 0

# 2. 确认 atoms VIEW 正常
python -c "
import sqlite3
conn = sqlite3.connect('agent.db')
row = conn.execute(\"SELECT type FROM sqlite_master WHERE name='atoms'\").fetchone()
assert row[0] == 'view', f'Expected VIEW, got {row[0]}'
print('OK: atoms is a VIEW')
"

# 3. 确认 DDL 不在 registry.py 中
grep -c 'CREATE TABLE' mcp-yuanzi-bridge/registry.py
# → 0 (或只有注释中出现)

# 4. 全量测试
python -m pytest mcp-yuanzi-bridge/tests/ -v
# → 零失败
```

---

> **预计清理时间**: 1 小时。6 个文件变更（3 删 2 改 1 增）。
