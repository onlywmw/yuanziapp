# Yuanzi 架构文档总目

> 35 份设计文档 · 2026-07-19

---

## 一、原子体系

| 文档 | 内容 |
|------|------|
| ADR_ATOM_MODEL.md | 原子分层: 基础原子 + 注册原子 |
| DESIGN_ATOM_V2_CLASSIFICATION.md | 五类原子: 工具/感知/融合/决策/执行 |
| BASE_ATOMS_SPEC.md | 13 个基础工具原子规格 |
| ATOM_SENSOR_LAYER.md | 12 个感知/融合/决策/执行原子 |
| REGISTERED_ATOM_RULES.md | 注册原子规则 — 作者第一 |

## 二、原子灵魂与可见性

| 文档 | 内容 |
|------|------|
| DESIGN_SOUL_VISIBILITY.md | 六字段/浮现算法/作者指南/校验/混音台联动 |

## 三、连线与通道

| 文档 | 内容 |
|------|------|
| CHANNEL_MODEL.md | 通道: 直通/映射/转换/合并/分流 |
| ATOM_CONNECTION_RULES.md | 原子依赖层级规则 + 5 种危险链 |
| WORKFLOW_CONNECTION_RULES.md | 工作流连线: 类型匹配 + 无效连线速查 |
| DESIGN_WORKFLOW_RESILIENCE.md | 工作流容错: retry/fallback/skip/timeout/abort |

## 四、图谱引擎

| 文档 | 内容 |
|------|------|
| DESIGN_GRAPH_ENGINE.md | SDK 架构: 三层/8模块/10000行 |
| DESIGN_GRAPH_REFERENCE.md | Obsidian 风格视觉方案 (给设计师) |
| GRAPH_MIXER_MODEL.md | 管道↔作品视角混合器 |
| GRAPH_PARAMETER_PANEL.md | 8 推子 + 4 配色 + 5 预设 |

## 五、阶段设计

| 文档 | 状态 |
|------|------|
| DESIGN_M4_REGISTRY_API.md | ✅ |
| DESIGN_M5_SEMANTIC_SEARCH.md | ✅ |
| DESIGN_M6_SECURITY.md | ✅ |
| DESIGN_M7_MARKETPLACE_WORKFLOW.md | 📐 |
| DESIGN_M8_HUMAN_EXPERIENCE.md | 📐 |
| DESIGN_M8_IMPLEMENTATION.md | 📐 |

## 六、终端 & APK

| 文档 | 内容 |
|------|------|
| DESIGN_APK_ARCHITECTURE.md | APK 客户端架构 |
| DESIGN_CHAQUOPY_MIGRATION.md | Python 内嵌 APK |
| DESIGN_FRONTEND_UI.md | Android UI 视觉规格 |
| APK_BUILD_GUIDE.md | 构建指南 |

## 七、AI & 区块链 & 体验

| 文档 | 内容 |
|------|------|
| DESIGN_AI_INTENT_ATOM.md | AI 意图理解原子 (本地 ONNX) |
| DESIGN_ATOM_NOTARIZATION.md | 原子公证 — 自己的链 |
| DESIGN_EXPERIENCE_SCENARIOS.md | 8 个场景 15 个体验缺口 |

## 八、质量治理

| 文档 | 内容 |
|------|------|
| INTERFACE_CONTRACTS.md | 14 个公开函数契约 |
| SCHEMA_AUTHORITY.md | DDL 单一权威源 |
| ISOLATION_HARDENING_PLAN.md | 隔离加固 4 步方案 |
| SMOKE_TEST_SPEC.md | 冒烟测试规范 |
| FULL_VERIFICATION_PLAN.md | 全量验证方案 |

---

> 35 份 · 原子体系 → 灵魂 → 连线 → 图谱 → 阶段 → 终端 → AI/链 → 治理
