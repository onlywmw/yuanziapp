# M4 注册中心服务化 — 质量评估报告 (v2)

> **评估人**: Arch | **复核**: QA (66d47f3)
> **日期**: 2026-07-18 | **版本**: v2

---

## 评估总览

| 子任务 | v1 判决 (30 失败) | v2 判决 (277 通过) |
|--------|-------------------|---------------------|
| 4.1 Schema 迁移 | 不通过 | ✅ 通过 |
| 4.2 原子版本化表 | 不通过 | ✅ 通过 |
| 4.3 REST API | 有条件通过 | ✅ 通过 |
| 4.4 健康探针 | 不通过 | ✅ 通过 |
| 4.5 依赖图解析 | 不通过 | ✅ 通过 |
| 4.6 分类修复 | 通过 | ✅ 通过 |

**v2: 6/6 通过 ✅**

---

## 测试对比

```
v1: 30 失败, CI 红灯, 6 个测试文件报错
v2: 277 通过, CI 绿灯, 零失败

bridge: 224 passed  (was 136)
atoms:   37 passed  (was 25)
cli:     16 passed  (was 11)
```

---

## 关键修复

| BUG | 描述 | 修复提交 | 状态 |
|-----|------|----------|------|
| BUG-023 | changelog 列缺失 | Eng M5 review | ✅ |
| BUG-023 | resolve_deps 键名不一致 (order/missing) | Eng M5 review | ✅ |
| BUG-024 | probe 功能桩恢复 → 完整语义 | Eng M5 review | ✅ |
| BUG-020 | probe SSRF → CIDR 白名单 | 9a1bbbc | ✅ |
| BUG-033 | probe CIDR DNS 超时/DNS rebinding | 1b1d1d3 | ✅ |
| BUG-022 | 审计刷爆 → 节流机制 | Eng M5 review | ✅ |
| BUG-016 | content_hash 不回填 → backfill 函数 | Eng M5 review | ✅ |

---

## 残留问题

| 问题 | 严重度 | 处理方案 |
|------|--------|----------|
| API 14 路由零认证 | P0 | M6 实施 (docs/DESIGN_M6_SECURITY.md) |
| registry.py 冗余 DDL | P2 | 清理方案 (docs/CLEANUP_PLAN.md) |
| insert_atoms.py / import_mcp_servers.py 遗留 | P2 | 清理方案 |
| RBAC 未实现 | P1 | M6 |
| 审计哈希链 | P2 | M6 |

---

> **结论: M4 不再阻塞。清理方案执行后收尾。M6 安全加固是下一优先级。**
