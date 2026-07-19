# Yuanzi 架构文档总目

> 38 份 · 按三层架构 + 质量治理分组

---

## 架构导航

| 文档 | 内容 |
|------|------|
| ARCHITECTURE_LAYERS.md | 三层架构: 基础层定义 → 发现层分发 → 引擎层组合 |

---

## 一、基础层 — 定义原子、通道、工作流是什么

### 原子体系

| 文档 | 内容 |
|------|------|
| ADR_ATOM_MODEL.md | 原子分层: 基础原子 + 注册原子 |
| DESIGN_ATOM_FOUNDATION_V2.md | 基座: 生命周期/I-O Schema/版本/依赖/安全/测试/星级 |
| DESIGN_ATOM_V2_CLASSIFICATION.md | 五类: 工具/感知/融合/决策/执行 + 连接器 |
| DESIGN_CONNECTOR_ATOM.md | 连接原子: 借力设备已有能力 |
| DESIGN_CONNECTOR_IMPLEMENTATION.md | 连接原子实现: compatibility 字段 |
| BASE_ATOMS_SPEC.md | 13 个基础工具原子 |
| ATOM_SENSOR_LAYER.md | 12 个感知/融合/决策/执行原子 |
| REGISTERED_ATOM_RULES.md | 注册规则 — 作者第一 |

### 通道体系

| 文档 | 内容 |
|------|------|
| DESIGN_CHANNEL_SPEC.md | 五种通道/映射语法/合并时序/分流路由/容错/版本 |
| DESIGN_CHANNEL_V2.md | 通道升级: 通道即原子/复用/推荐/测试 |

### 注册中心 & API

| 文档 | 内容 |
|------|------|
| DESIGN_M4_REGISTRY_API.md | REST API 服务化 |
| DESIGN_M5_SEMANTIC_SEARCH.md | 语义搜索 |
| DESIGN_M6_SECURITY.md | 安全加固 |
| INTERFACE_CONTRACTS.md | 14 个公开函数契约 |
| SCHEMA_AUTHORITY.md | DDL 单一权威源 |

### AI & 区块链

| 文档 | 内容 |
|------|------|
| DESIGN_AI_INTENT_ATOM.md | 本地 ONNX 意图理解原子 |
| DESIGN_ATOM_NOTARIZATION.md | 原子公证 — 自己的链 |
| DESIGN_GRAPH_QUERY.md | 图查询: Cypher→SQLite |

---

## 二、发现层 — 怎么找到、怎么安装、怎么信任

| 文档 | 内容 |
|------|------|
| DESIGN_M7_MARKETPLACE_WORKFLOW.md | 原子市场/工作流模板市场/评分/联邦注册 |

---

## 三、引擎层 — 怎么渲染、怎么执行、怎么交互

| 文档 | 内容 |
|------|------|
| DESIGN_GRAPH_ENGINE.md | 图谱 SDK: 三层/11模块/力导向/虚拟化 |
| DESIGN_GRAPH_CONTROLS.md | 混音台 + 参数面板 + 配色方案 |
| DESIGN_M8_TEMPLATE_SYSTEM.md | 模板系统: 钩子接口/Obsidian星系/模板切换 |
| DESIGN_GRAPH_REFERENCE.md | Obsidian 风格视觉方案 (给设计师) |

---

## 四、终端 — APK 完整规格

| 文档 | 内容 |
|------|------|
| DESIGN_APK_SPEC.md | 架构 + 视觉 + 构建 — 一份文档涵盖 APK 全部 |
| DESIGN_CHAQUOPY_MIGRATION.md | Python 内嵌 APK 方案 |

---

## 五、质量治理 — 怎么保证规范被执行

### 规范

| 文档 | 内容 |
|------|------|
| SMOKE_TEST_SPEC.md | 冒烟测试规范 |
| ISOLATION_HARDENING_PLAN.md | 隔离加固 4 步方案 |

### 工具

| 文档 | 内容 |
|------|------|
| FULL_VERIFICATION_PLAN.md | 7 层全量验证方案 |

### 执行计划

| 文档 | 内容 |
|------|------|
| DESIGN_EXPERIENCE_SCENARIOS.md | 8 个场景 15 个体验缺口 |
| SOUL_DISASSEMBLE_PLAN.md | "灵魂"概念拆解执行 |
| LEARN_FROM_CODEBASE_MEMORY.md | 借鉴: 安装体验/Web图谱/图查询 |

---

> **基础层定义 → 发现层分发 → 引擎层组合 → 终端呈现 → 质量治理贯穿全程**
