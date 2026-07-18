# Yuanzi 架构文档总目

> 最后更新: 2026-07-18

---

## 基座设计 (Foundation)

| 文档 | 内容 |
|------|------|
| [ADR_ATOM_MODEL.md](ADR_ATOM_MODEL.md) | 原子分层模型：基础原子 + 注册原子 |
| [CHANNEL_MODEL.md](CHANNEL_MODEL.md) | 通道模型：线是活的转换器，五种类型 |
| [SCHEMA_AUTHORITY.md](SCHEMA_AUTHORITY.md) | Schema 权威源：DDL 只在 migrations/ |
| [INTERFACE_CONTRACTS.md](INTERFACE_CONTRACTS.md) | 接口契约注册表：14 个公开函数 |

## 规格定义 (Specification)

| 文档 | 内容 |
|------|------|
| [BASE_ATOMS_SPEC.md](BASE_ATOMS_SPEC.md) | 13 个基础原子完整规格 |
| [REGISTERED_ATOM_RULES.md](REGISTERED_ATOM_RULES.md) | 注册原子规则 — 作者第一 |
| [SMOKE_TEST_SPEC.md](SMOKE_TEST_SPEC.md) | 原子冒烟测试规范 |

## 连线规则 (Connection Rules)

| 文档 | 内容 |
|------|------|
| [ATOM_CONNECTION_RULES.md](ATOM_CONNECTION_RULES.md) | 原子依赖关系：层级规则 + 5 种危险链 |
| [WORKFLOW_CONNECTION_RULES.md](WORKFLOW_CONNECTION_RULES.md) | 工作流连线：类型匹配 + 无效连线速查 |

## 阶段设计 (Phase Design)

| 文档 | 内容 | 状态 |
|------|------|------|
| [DESIGN_M4_REGISTRY_API.md](DESIGN_M4_REGISTRY_API.md) | REST API 服务化 | ✅ 已实现 |
| [DESIGN_M5_SEMANTIC_SEARCH.md](DESIGN_M5_SEMANTIC_SEARCH.md) | 语义搜索 | ✅ 已实现 |
| [DESIGN_M6_SECURITY.md](DESIGN_M6_SECURITY.md) | 安全与多租户 | 📐 设计就绪 |
| [DESIGN_M7_MARKETPLACE_WORKFLOW.md](DESIGN_M7_MARKETPLACE_WORKFLOW.md) | 原子市场与工作流 | 📐 设计就绪 |

## 质量治理 (Governance)

| 文档 | 内容 |
|------|------|
| [ARCHITECTURE_ASSESSMENT.md](ARCHITECTURE_ASSESSMENT.md) | 三个结构性缺陷诊断 |
| [M4_QUALITY_ASSESSMENT.md](M4_QUALITY_ASSESSMENT.md) | M4 质量评估 v2 — 6/6 通过 |
| [BUG_REGISTRY.md](BUG_REGISTRY.md) | 16 个 Bug 总览 (Audit #1/#2) |
| [CLEANUP_PLAN.md](CLEANUP_PLAN.md) | 遗留代码清理方案 |

---

## 核心概念关系

```
基座层
  ┌─────────────────────────────────────────────┐
  │  原子分层模型 (ADR)                          │
  │  ├─ 基础原子 (13个, 内置, 不可删)           │
  │  └─ 注册原子 (61+, 可注册/发现/组合)        │
  │                                              │
  │  通道模型 (CHANNEL)                          │
  │  ├─ 直通线 / 映射线 / 转换线 / 合并线 / 分流线 │
  │  └─ 线是活的转换器, 血液般的血管系统          │
  └─────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
规格层                        连线层
┌──────────────┐    ┌──────────────────────┐
│ BASE_ATOMS   │    │ ATOM_CONNECTION      │
│ 13 原子规格   │    │ 依赖规则 + 危险链    │
│              │    │                      │
│ REGISTERED   │    │ WORKFLOW_CONNECTION  │
│ 注册规则     │    │ 类型匹配 + 无效连线   │
└──────────────┘    └──────────────────────┘
         │                    │
         └────────┬───────────┘
                  ▼
          实现层 (M4/M5/M6)
```

---

> **15 份架构文档，5 个分组。从基座到实现，从规格到治理。**
