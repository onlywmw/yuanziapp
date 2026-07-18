# Yuanzi App

> **让每一个 AI 能力都成为一个可被发现、可被组合、可被验证的"原子"。**

## 宗旨

现有的 AI 工具生态是碎片化的——每个 MCP 服务器、API、脚本各自独立，互不知道对方存在。
Yuanzi 解决这个问题：把能力拆成独立"原子"，通过注册中心统一管理，让它们能被**发现**（语义搜索）、
能被**组合**（工作流编排）、能被**验证**（健康探针 + 签名去重）。

## 目标

在 Android 设备上构建一个**可生长的 AI 工具生态系统**——61 个原子以知识图谱形式可视化呈现，
用户可以自然语言搜索匹配的原子能力，最终像应用商店一样自由组合使用。

---

## 项目状态

| 里程碑 | 目标 | 状态 |
|--------|------|------|
| M1 | 原子开发基础设施 | ✅ |
| M2 | 部署与配置管理 | ✅ |
| M3 | 测试与质量门禁 | ✅ |
| M4 | 注册中心服务化 | ✅ |
| M5 | 能力搜索与匹配 | ✅ |
| M6 | 安全与多租户 | 📐 设计就绪 |
| M7 | 原子市场与工作流 | ⭕ 未开始 |

:point_right: **完整计划表请查看 [PROJECT_PLAN.md](./PROJECT_PLAN.md)**

---

## 项目结构

```
yuanziapp/
├── yuanzi-cli/               # 原子开发 CLI（init / validate / test）
├── yuanzi-atom-templates/    # 标准化原子模板（Cookiecutter）
├── yuanzi-atoms/             # Yuanzi 核心原子服务
├── mcp-yuanzi-bridge/        # MCP 原子注册中心与桥接
├── widgetmcp_src/            # Android 客户端源码
├── scripts/                  # 开发辅助脚本（adb 同步等）
├── atoms/                    # 基础示例原子
├── atom-registry-schema.json # 原子注册标准 Schema
├── yuanzi-config.yaml        # 项目配置与同步清单
├── start_yuanzi_termux.sh    # Termux 启动脚本
└── PROJECT_PLAN.md           # 项目计划表
```

## 快速开始

### 1. 在平板上启动 Yuanzi

```bash
sh start_yuanzi_termux.sh
```

### 2. 安装 CLI

```bash
cd yuanzi-cli
python -m pip install -e .
```

### 3. 创建新原子

```bash
yuanzi init com.example.my-atom
```

### 4. 校验并测试原子

```bash
cd com.example.my-atom
yuanzi validate
yuanzi test
```

### 5. 同步到 Android 平板

确保平板通过 adb 连接，然后：

```bash
scripts/sync-to-device.sh
```

或使用 Python 脚本：

```bash
python scripts/sync-to-device.py
```

### 6. 在平板上启动 Yuanzi

```bash
sh /data/data/com.termux/files/home/yuanzi-project/start_yuanzi_termux.sh
```

## 代码质量门禁

安装 pre-commit 钩子后，每次 `git commit` 会自动运行格式化、lint 和示例原子测试：

```bash
scripts/install-hooks.sh
```

手动跑所有检查：

```bash
pre-commit run --all-files
```

手动格式化全部代码：

```bash
scripts/format-all.sh
```

## 注册中心

`mcp-yuanzi-bridge/` 包含：

- `registry.py` — 原子注册中心核心
- `register_mcp_atoms.py` — MCP 原子批量注册
- `ATOM_REGISTRY_LEDGER.md` — 注册登记表

## 许可证

MIT
