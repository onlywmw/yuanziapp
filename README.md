# 原子 App (Yuanzi App)

Hermes 原子化服务生态：把 MCP 服务器、工具、模块拆成独立"原子"，通过注册中心管理，并在 Android 平板上以知识图谱形式呈现。

## 项目结构

```
yuanziapp/
├── hermes-atom-templates/    # 标准化原子模板（Cookiecutter）
├── hermes-atoms/             # Hermes 核心原子服务
├── mcp-hermes-bridge/        # MCP 原子注册中心与桥接
├── atoms/                    # 基础示例原子
├── atom-registry-schema.json # 原子注册标准 Schema
└── start_hermes_termux.sh    # Termux 启动脚本
```

## 快速开始

### 1. 在平板上启动 Hermes

```bash
sh start_hermes_termux.sh
```

### 2. 创建新原子

```bash
cd hermes-atom-templates
cookiecutter . --output-dir ../atoms
```

### 3. 运行示例原子测试

```bash
cd examples/com.example.sum
pytest tests/
```

## 注册中心

`mcp-hermes-bridge/` 包含：

- `registry.py` — 原子注册中心核心
- `register_mcp_atoms.py` — MCP 原子批量注册
- `ATOM_REGISTRY_LEDGER.md` — 注册登记表

## 许可证

MIT
