# 原子 App (Yuanzi App)

Yuanzi 原子化服务生态：把 MCP 服务器、工具、模块拆成独立"原子"，通过注册中心管理，并在 Android 平板上以知识图谱形式呈现。

---

## :rocket: 项目计划

**当前阶段：第一阶段 — 开发体验基础设施**

| 里程碑 | 目标 | 预计完成 | 状态 |
|--------|------|----------|------|
| M1 | 原子开发基础设施就绪 | 2026-07-25 | :construction: 进行中 |
| M2 | 部署与配置管理就绪 | 2026-08-01 | :white_circle: 未开始 |
| M3 | 测试与质量门禁就绪 | 2026-08-08 | :white_circle: 未开始 |
| M4 | 注册中心服务化 | 2026-08-22 | :white_circle: 未开始 |
| M5 | 能力搜索与匹配 | 2026-09-05 | :white_circle: 未开始 |
| M6 | 安全与多租户 | 2026-09-19 | :white_circle: 未开始 |
| M7 | 原子市场与工作流 | 2026-10-10 | :white_circle: 未开始 |

:point_right: **完整计划表请查看 [PROJECT_PLAN.md](./PROJECT_PLAN.md)**

---

## 项目结构

```
yuanziapp/
├── yuanzi-atom-templates/    # 标准化原子模板（Cookiecutter）
├── yuanzi-atoms/             # Yuanzi 核心原子服务
├── mcp-yuanzi-bridge/        # MCP 原子注册中心与桥接
├── widgetmcp_src/            # Android 客户端源码
├── atoms/                    # 基础示例原子
├── atom-registry-schema.json # 原子注册标准 Schema
├── start_yuanzi_termux.sh    # Termux 启动脚本
└── PROJECT_PLAN.md           # 项目计划表
```

## 快速开始

### 1. 在平板上启动 Yuanzi

```bash
sh start_yuanzi_termux.sh
```

### 2. 创建新原子

```bash
cd yuanzi-atom-templates
cookiecutter . --output-dir ../atoms
```

### 3. 运行示例原子测试

```bash
cd examples/com.example.sum
pytest tests/
```

## 注册中心

`mcp-yuanzi-bridge/` 包含：

- `registry.py` — 原子注册中心核心
- `register_mcp_atoms.py` — MCP 原子批量注册
- `ATOM_REGISTRY_LEDGER.md` — 注册登记表

## 许可证

MIT
