# Yuanzi 架构文档总目

> 36 份设计文档 · 最后更新 2026-07-19

---

## 基座设计

| 文档 | 内容 |
|------|------|
| ADR_ATOM_MODEL.md | 原子分层: 基础原子 + 注册原子 |
| DESIGN_ATOM_V2_CLASSIFICATION.md | 五类原子: 工具/感知/融合/决策/执行 |
| CHANNEL_MODEL.md | 通道: 直通/映射/转换/合并/分流 |
| SCHEMA_AUTHORITY.md | DDL 只在 migrations/ |
| INTERFACE_CONTRACTS.md | 14 个公开函数契约 |

## 原子规格

| 文档 | 内容 |
|------|------|
| BASE_ATOMS_SPEC.md | 13 个基础工具原子 |
| ATOM_SENSOR_LAYER.md | 12 个感知/融合/决策/执行原子 |
| REGISTERED_ATOM_RULES.md | 注册原子规则 — 作者第一 |
| ATOM_SOUL_MODEL.md | 灵魂模型: 风格/受众/基调/品质/叙事 |
| ATOM_VISIBILITY_MODEL.md | 可见性: soul 饱满上浮, 空心下沉 |
| ATOM_CONNECTION_RULES.md | 原子依赖层级规则 + 5 种危险链 |
| WORKFLOW_CONNECTION_RULES.md | 工作流连线: 类型匹配 + 无效连线速查 |

## 图谱引擎

| 文档 | 内容 |
|------|------|
| DESIGN_GRAPH_ENGINE.md | SDK 架构: 三层/8模块/10000行 |
| DESIGN_GRAPH_REFERENCE.md | Obsidian 风格视觉方案 (给设计师) |
| GRAPH_MIXER_MODEL.md | 管道↔作品视角混合器 |
| GRAPH_PARAMETER_PANEL.md | 8 推子 + 4 配色 + 5 预设 |

## 阶段设计

| 文档 | 内容 | 状态 |
|------|------|------|
| DESIGN_M4_REGISTRY_API.md | REST API 服务化 | ✅ |
| DESIGN_M5_SEMANTIC_SEARCH.md | 语义搜索 | ✅ |
| DESIGN_M6_SECURITY.md | 安全与多租户 | 📐 |
| DESIGN_M7_MARKETPLACE_WORKFLOW.md | 原子市场与工作流 | 📐 |
| DESIGN_M8_HUMAN_EXPERIENCE.md | 人机体验层 (Obsidian 星系) | 📐 |
| DESIGN_M8_IMPLEMENTATION.md | M8 实施方案 | 📐 |

## 终端

| 文档 | 内容 |
|------|------|
| DESIGN_APK_ARCHITECTURE.md | APK 客户端架构 |
| DESIGN_CHAQUOPY_MIGRATION.md | Python 内嵌 APK 方案 |
| DESIGN_FRONTEND_UI.md | Android UI 视觉规格 |
| APK_BUILD_GUIDE.md | 构建指南 + 6 个坑 |

## 质量治理

| 文档 | 内容 |
|------|------|
| ARCHITECTURE_ASSESSMENT.md | 三个结构性缺陷 |
| ISOLATION_ASSESSMENT.md | 系统隔离性评估 |
| ISOLATION_HARDENING_PLAN.md | 隔离加固 4 步方案 |
| M4_QUALITY_ASSESSMENT.md | M4 质量评估 v2 |
| BUG_REGISTRY.md | 16 个 Bug 总览 |
| CLEANUP_PLAN.md | 遗留代码清理 |
| SOUL_MODEL_IMPLEMENTATION.md | 灵魂模型实施 |
| SMOKE_TEST_SPEC.md | 冒烟测试规范 |
| FULL_VERIFICATION_PLAN.md | 7 层全量验证 |

---

> 36 份文档 · 从基座到终端 · 从工具到感知 · 从代码到体验
