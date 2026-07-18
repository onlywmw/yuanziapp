# Yuanzi 架构评估报告

> **作者**: Arch
> **日期**: 2026-07-18
> **性质**: 系统性架构审查，非功能设计

---

## 三个结构性缺陷

### 缺陷一：单分支碰撞 — 没有开发流程架构

```
main 分支上的实际发生:
  
  Eng 修 Bug ──→ main
     ←── Arch 推送配置 ──→ main
  Eng 再修 Bug ──→ main
     ←── Arch 推送调度器 ──→ main
  合并冲突 ←── 💥
     ←── Arch 推送 watchdog/chat ──→ main
     ←── Arch 回滚代码 ──→ main
  CI 红灯，30 测试失败，无人阻止推送
```

**根因**: 没有分支策略。Arch 的设计文档、Eng 的代码实现、Fixer 的紧急修复全部直推 main。没有 PR，没有 Review 门禁，没有合并前检查。

**症状**: 
- 两个智能体（Arch 和 Eng）在不知道对方工作的情况下修改同一批文件
- 合并冲突发生时没有仲裁机制
- `1a61a86`（我们的桥接提交）覆盖了 `689ad4e`（Eng 的完整实现）

**这不是代码 Bug，是流程架构缺失。**

---

### 缺陷二：DDL 三源分裂 — 没有 Schema 权威源

同一个数据库 `agent.db` 的表结构，定义在三个地方：

```
定义位置                          创建方式              跟踪方式
─────────────────────────────────────────────────────────────
registry.py:ensure_registry_schema()  CREATE TABLE IF NOT EXISTS   无
migrations/001_init.sql               CREATE TABLE IF NOT EXISTS   schema_migrations 表
migrations/002_atoms_view.sql         CREATE VIEW                  schema_migrations 表
register_mcp_atoms.py:sync_atoms_table() CREATE TABLE IF NOT EXISTS 无 (legacy atoms 表)
insert_atoms.py                       CREATE TABLE IF NOT EXISTS   无 (legacy atoms 表)
```

**问题**:
- 哪个是权威的？修改表结构应该在哪个文件里改？
- `registry.py` 新增了 `content_hash`/`identity_hash` 列，但 `001_init.sql` 没有
- `002_atoms_view.sql` 把 `atoms` 表改成了 VIEW，但 `sync_atoms_table()` 还在往 `atoms` 表 INSERT
- `registry_meta` 和 `schema_migrations` 两个版本跟踪表并存

**这不是实现错误，是 Schema 治理缺失。**

---

### 缺陷三：接口无契约 — 没有 API 版本化

```
resolve_dependencies() 的返回值在两次提交中不同:

远程版本 (689ad4e):
  {"ok": true, "order": [...], "missing": [...], "cycles": [...]}

我们的版本 (1a61a86):
  {"ok": true, "dependencies": [...], "missing_dependencies": [...], "has_cycle": true}

结果: 6 个测试失败 (KeyError: 'order'/'missing'/'cycles')
```

同样的问题出现在 `probe_atom`、`list_atom_versions`、迁移系统 API。

**根因**: 模块间接口没有契约定义。函数签名和返回值格式变更时，没有机制检测下游影响。

---

## 架构修复方案

### 修复一：分支策略（流程架构）

```
分支模型:

main          ← 只接受 PR，不允许直推
  │
  ├─ design/m6-security     ← Arch 设计文档分支
  ├─ feat/api-auth          ← Eng 功能分支
  ├─ fix/bug-025-auth       ← Fixer 修复分支
  └─ chore/agent-roles      ← Hub 配置分支

规则:
1. main 分支开启保护: 要求 PR + 1 Review + CI 通过
2. 每个 Issue 一个分支
3. 合并前必须 rebase main（检测冲突）
4. CI 红灯 = 禁止合并
```

### 修复二：Schema 单一权威源（数据架构）

```
migrations/*.sql 是唯一权威的 DDL 来源。

消除重复:
  ❌ 删除 registry.py:ensure_registry_schema() 中的 CREATE TABLE
  ❌ 删除 register_mcp_atoms.py:sync_atoms_table() 中的 CREATE TABLE
  ❌ 删除 insert_atoms.py 中的 CREATE TABLE
  ✅ 所有 DDL 只在 migrations/*.sql 中定义
  ✅ registry.py 启动时只调用 migrate(conn)
  ✅ 废弃 registry_meta 表，统一用 schema_migrations

atoms VIEW 一致性:
  ✅ 保留 002_atoms_view.sql 的 VIEW 定义
  ❌ 删除 sync_atoms_table() 中向 atoms 写入的代码
  ✅ 所有读取 atoms 的代码直接读 VIEW
```

### 修复三：接口契约注册（接口架构）

```
每个公开函数在 registry.py 中附带契约注释:

```python
def resolve_dependencies(conn, atom_id) -> Dict[str, Any]:
    \"\"\"解析原子依赖图。
    
    契约: (v1.0 — 不可变)
    返回: {
        "ok": bool,           # 所有依赖可解析且无循环
        "order": [str],       # 拓扑排序的 atom_id 列表
        "missing": [str],     # 不存在的依赖 atom_id
        "cycles": [[str]],    # 检测到的循环依赖
        "deps": [dict],       # 解析后的依赖详情
    }
    \"\"\"
```

契约测试:
  tests/test_contracts.py — 验证每个公开函数的返回值结构
  不测试业务逻辑，只测试键名和类型
  接口变更 → 契约测试失败 → CI 阻止合并 → 强制更新文档
```

---

## 优先级建议

| 优先级 | 修复 | 影响范围 | 工作量 |
|--------|------|----------|--------|
| P0 | 分支保护 + PR 门禁 | 流程 | 配置 GitHub Settings |
| P0 | Schema 单一源 | 数据完整性 | 重构 3 个文件 |
| P1 | 接口契约注册 | 多智能体协作 | 新增契约测试 |
| P2 | 版本跟踪统一 | 技术债务 | 迁移合并 |

---

> **Arch 结论**: 30 个测试失败、`probe_atom` 被覆盖、DDL 三源分裂——这些不是独立 Bug，是**架构层面缺乏流程治理、Schema 治理、接口治理**的系统性表现。先修架构，再修 Bug。
