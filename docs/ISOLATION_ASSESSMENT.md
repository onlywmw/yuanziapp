# 系统隔离性评估

> **评估人**: Arch
> **日期**: 2026-07-19
> **结论**: 部分隔离, 有几个单点改了会炸

---

## 一、炸点地图

```
改了这里              →        这里会炸              严重度
─────────────────────────────────────────────────────────
atom_registry 表结构   →  atoms VIEW + api.py + registry.py   🔴
registry.py 公开函数签名 →  api.py + 277 测试              🔴
migrations/*.sql       →  所有依赖该表的代码               🔴
agent.db 文件          →  整个后端                          🔴
base-atoms/*/core.py   →  只有那个原子 (隔离良好)          🟢
单个注册原子            →  只有那个原子 (隔离良好)          🟢
Kotlin UI              →  Python 后端不受影响               🟢
```

## 二、具体分析

### 🔴 registry.py: 单点故障

```
957 行, 14 个公开函数, 全部在一个文件

_probe_atom() 的副作用链:
  probe_atom()
    → set_atom_status()     ← 改 lifecycle
    → 写 runtime_json       ← 改注册表
    → _audit()              ← 写审计表
    → 如果失败, 以上全回滚

一个 probe 操作碰了 3 张表。如果 probe 逻辑有 bug,
后果不是"这个原子探测失败", 而是"全局状态被污染"。
```

### 🔴 atom_registry 表: 共享可变状态

```
atom_registry 表被以下模块同时读写:

  读: api.py (14 个路由)
  读: GraphView (通过 REST API)
  读: atoms VIEW
  读: yuanzi-atoms/core

  写: register_mcp_atoms.py (批量注册)
  写: api.py POST 路由 (提交/审核/状态变更)
  写: probe_atom (自动状态更新)
  写: rollback_atom (版本回滚)

没有写锁, 没有乐观锁, 没有 MVCC。
SQLite 的 WAL 模式提供基本并发, 但不提供应用层隔离。
```

### 🔴 atoms VIEW: 隐藏依赖

```sql
CREATE VIEW atoms AS
SELECT
    r.atom_id AS atom_id,
    r.name AS label,
    json_extract(r.architecture_json, '$.type') AS atom_type,
    ...
FROM atom_registry r;
```

如果 `architecture_json` 的 JSON 结构变了, VIEW 不会报错——它会静默返回 NULL。
APK 的 GraphView 读到 NULL → 崩溃或白屏。没有编译时检查。

### 🟢 base-atoms/: 良好隔离

```
每个基础原子是独立目录:
  base-atoms/file-read/
    ├── core.py        ← 只被自己的 server.py import
    ├── server.py      ← 独立进程
    └── Dockerfile

改 file-read 不会影响 math-calc。
改 server.py 不会影响其他原子。
```

### 🟢 APK ↔ 后端: 物理隔离

```
Kotlin 代码和 Python 代码通过 HTTP 通信。
Kotlin 改了不影响 Python。Python 改了不影响 Kotlin 编译。
唯一耦合点: API 契约 (JSON 字段名)。
```

## 三、隔离改造建议

### 改 1: registry.py 拆模块

```
registry.py (957 行, 单一巨石)
    ↓
registry/
├── __init__.py      ← 公开 API (不变)
├── core.py          ← submit/review/status/get/list
├── probe.py         ← probe_atom/probe_atoms (独立副作用)
├── deps.py          ← resolve_dependencies (纯计算)
├── versions.py      ← list_atom_versions/rollback (只读+写版本表)
├── hashing.py       ← compute_signature/content_hash (纯函数)
└── db.py            ← ensure_schema/migrate (DDL 入口)
```

收益: 改 probe 逻辑 → 只动 `probe.py`，不影响提交/审核。

### 改 2: atom_registry 表加乐观锁

```sql
ALTER TABLE atom_registry ADD COLUMN version_counter INTEGER DEFAULT 0;

UPDATE atom_registry SET
  lifecycle_json = ?, version_counter = version_counter + 1
WHERE atom_id = ? AND version_counter = ?

-- 如果 affected rows = 0 → 并发冲突 → 重试
```

收益: 并发写入安全, 防止静默覆盖。

### 改 3: atoms VIEW 加防御

```sql
-- 在 VIEW 定义中加 COALESCE, 防止 NULL 崩溃
COALESCE(json_extract(r.architecture_json, '$.type'), 'unknown') AS atom_type
```

收益: JSON 结构变更时 VIEW 返回降级值, 不崩溃。

### 改 4: 基础原子命名空间保护

```python
# registry.py: submit_atom() 中加检查
if atom_id.startswith("system."):
    return {"success": False, "error": "reserved_namespace"}

# 同理: DELETE /atoms/system.* → 拒绝
```

收益: 基础原子永不被误注册或误删除。

---

## 四、总结

```
当前隔离度: ★★☆☆☆

做得好的:
  ✅ 基础原子: 独立目录, 改了不炸别人
  ✅ APK ↔ 后端: HTTP 物理隔离
  ✅ 测试: 每模块独立, 改了能检测

需要加固的:
  ❌ registry.py: 巨石文件, 副作用链长
  ❌ atom_registry: 共享可变状态, 无并发保护
  ❌ atoms VIEW: 隐藏依赖, 静默失败
  ❌ 基础原子命名空间: 无保护, 可被误注册
```

> **改了 probe → 可能炸状态机。改了表结构 → 可能炸 VIEW + API。改了 registry 签名 → 可能炸全体。这三个是当前最脆弱的点。**
