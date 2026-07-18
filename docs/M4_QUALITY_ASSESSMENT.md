# M4 注册中心服务化 — 质量评估报告

> **评估人**: Arch
> **日期**: 2026-07-18
> **范围**: M4.1 ~ M4.6
> **方法**: 对照 PROJECT_PLAN 声明、接口契约、Audit 实测证据逐项审查

---

## 评估总览

| 子任务 | 计划状态 | 实际状态 | 判决 |
|--------|----------|----------|------|
| 4.1 Schema 迁移系统 | ✅ 已完成 | ⚠️ 功能存在但框架分裂 | 不通过 |
| 4.2 原子版本化表 | ✅ 已完成 | ❌ changelog 缺失 → 运行时报错 | 不通过 |
| 4.3 REST API | ✅ 已完成 | ⚠️ 功能可用但零认证 | 有条件通过 |
| 4.4 健康探针系统 | ✅ 已完成 | ❌ 被回退为功能桩 | 不通过 |
| 4.5 依赖图解析 | ✅ 已完成 | ❌ 契约不一致，6 测试失败 | 不通过 |
| 4.6 分类修复 | ✅ 已完成 | ✅ 测试通过 | 通过 |

**总评: 1/6 通过，3/6 不通过，2/6 有条件通过**

---

## 4.1 Schema 迁移系统

**计划**: `migrations/` 目录，版本化管理数据库 Schema

**实际**:

```
两个并存系统:
  ① migrations/*.sql (远程 Eng)  — 基于 schema_migrations 表，4 个 SQL 文件
  ② migrations/__init__.py (我)  — 基于 MigrationRunner 类，SQL 执行器

冲突表现:
  - api.py 导入 migrate() 函数
  - registry.py 导入 MigrationRunner 类
  - test_migrations.py 期望两者的 API，6 个测试失败
  - registry_meta 和 schema_migrations 两个版本跟踪表
```

| 检查项 | 结果 |
|--------|------|
| 迁移文件可发现并按序执行 | ✅ `discover_migrations()` 工作 |
| 幂等（重复执行无副作用） | ✅ SQL 用 IF NOT EXISTS |
| 版本跟踪唯一 | ❌ 两个跟踪表 |
| API 契约一致 | ❌ migrate() vs MigrationRunner 互不兼容 |
| 旧数据库升级引导 | ✅ bootstrap 逻辑存在 |
| 测试通过 | ❌ 6 个失败 |

**判决: 不通过。两套系统需合并，统一为 SQL + schema_migrations。**

---

## 4.2 原子版本化表

**计划**: `atom_versions` 表，记录原子每次提交的完整快照

**实际**:

```
DDL (003_atom_versions.sql):
  ✅ atom_id, version, purpose_json, architecture_json, signature_hash, content_hash, created_at

代码 (list_atom_versions):
  SELECT ..., changelog, ... FROM atom_versions
  → OperationalError: no such column: changelog

根因: SQL 迁移文件缺少 changelog 列，但 Python 代码引用了它
```

| 检查项 | 结果 |
|--------|------|
| 表创建 | ✅ 迁移 003 |
| 注册时自动存档 | ✅ `submit_atom` 写入 |
| 版本列表查询 | ❌ 5 个测试 OperationalError |
| 版本回滚 | ❌ 依赖版本列表，级联失败 |
| API 端点 | ❌ `/versions` 和 `/rollback` 不可用 |

**判决: 不通过。DDL 与代码不一致，运行时崩溃。修复：003 加 changelog 列。**

---

## 4.3 REST API (FastAPI)

**计划**: FastAPI 服务，端口 8000/8081，提供原子查询/管理接口

**实际**:

```
已实现路由:
  GET  /health, /stats, /atoms, /atoms/{id}
  POST /atoms, /atoms/{id}/review, /atoms/{id}/status
  POST /atoms/{id}/probe, /atoms/{id}/rollback/{version}

读路由: 全部可用，分页/过滤/排序正常
写路由: 功能可用，但零认证
        → POST /atoms/{id}/review  无认证可自审自批
        → POST /atoms/{id}/status  无认证可任意改状态
```

| 检查项 | 结果 |
|--------|------|
| 端口监听 | ✅ 8081 |
| OpenAPI 文档 | ✅ /docs |
| 健康检查 | ✅ /health |
| 统计查询 | ✅ /stats |
| 原子 CRUD | ✅ |
| 认证 | ❌ 14 路由全部无认证 |
| RBAC | ❌ 未实现 |
| 测试 | ❌ 3 个失败 |

**判决: 有条件通过。功能可用，但 M6 安全加固前不可暴露到非 localhost。**

---

## 4.4 健康探针系统

**计划**: 探测原子 endpoint 可达性，更新状态

**实际**:

```
版本演变:
  689ad4e (v1): 完整实现 — 更新 lifecycle, 写入 runtime_json, 写审计, 返回 success
  1a61a86 (v2): 功能桩 — fix missing functions 时覆盖了 v1
  当前: v2 在 main 上

v2 缺失的功能:
  ❌ 不更新 lifecycle (原子永远不会变 running/unreachable)
  ❌ 不写 runtime_json (last_probe_at, latency, consecutive_failures)
  ❌ 不写审计日志
  ❌ 返回结构无 success 键 → 9 个测试 KeyError
```

| 检查项 | 结果 |
|--------|------|
| HTTP 请求发送 | ✅ |
| scheme 白名单 | ❌ 无校验，file:// 会崩溃 |
| 地址白名单 | ❌ 可请求内网任意地址 |
| 状态更新 | ❌ 不更新 lifecycle |
| 探测指标记录 | ❌ 不写 runtime_json |
| 审计日志 | ❌ 不写 |
| 测试 | ❌ 9 个失败 |

**判决: 不通过。当前实现是功能桩。需以 v1 为基线恢复完整语义并叠加安全加固。**

---

## 4.5 依赖图解析

**计划**: 解析原子的依赖关系，检测循环依赖

**实际**:

```
契约期望 (按接口契约 v1.0):
  {"ok": true, "order": [...], "missing": [...], "cycles": [...]}

实际返回 (当前 main):
  {"ok": true, "dependencies": [...], "missing_dependencies": [...], "has_cycle": true}

键名不一致 → 6 个测试 KeyError: 'order'/'missing'/'cycles'
```

| 检查项 | 结果 |
|--------|------|
| 直接依赖解析 | ✅ |
| 拓扑排序 | ❌ 无 order 键 |
| 缺失检测 | ⚠️ 有但键名是 missing_dependencies |
| 循环检测 | ⚠️ 有但键名是 has_cycle |
| 测试 | ❌ 6 个失败 |

**判决: 不通过。代码逻辑存在但接口契约不一致，需统一键名。**

---

## 4.6 分类误判修复

**计划**: 提升原子自动分类准确性

| 检查项 | 结果 |
|--------|------|
| token 匹配替换子串匹配 | ✅ |
| 回归测试 (11 个场景) | ✅ 全部通过 |
| 边界 case (details 不匹配 AI) | ✅ |
| 优先级 (atom_id > 函数名) | ✅ |

**判决: 通过。唯一的满分项。**

---

## 修复优先级

```
P0 - 必须立即修:
  4.4 probe 恢复 → 9 个测试
  4.2 changelog 列 → 5 个测试
  4.5 契约统一 → 6 个测试
  4.1 迁移系统统一 → 6 个测试

P1 - M6 中修:
  4.3 API 认证
  4.4 probe 安全加固

P2 - 可延后:
  4.4 probe 批量容错
  4.5 深层依赖图 (当前只解析一层)
```

---

> **结论: M4 不宜标记为"已完成"。功能骨架在，但 30 个测试失败 + 零认证 API + 功能桩探针 = 不可交付。**
> **修复工作量估算: 2-3 天（4 个 P0 修复 + 契约测试）。**
