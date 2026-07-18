# Yuanzi 原子生态 (Yuanzi App)

> 把 MCP 服务器、工具、模块拆成独立"原子"，通过注册中心管理，在 Android 设备上以知识图谱形式呈现。

---

## 项目哲学与初衷

> **让每一个 AI 能力都成为一个可被发现、可被组合、可被验证的"原子"。**

Yuanzi 解决 AI 工具碎片化问题：

1. **万物皆原子**：能力拆为基础原子（13 个内置标准件）和注册原子（61+ 可发现的专用件）
2. **线是活的通道**：原子间的连接线不是死路径，是数据血管——直通/映射/转换/合并/分流五种类型
3. **知识图谱即界面**：原子关系在 Android 设备上可视化为知识图谱，基础原子灰色边框、注册原子可交互
4. **作者第一**：每个注册原子必须有作者，人通过创造的工具连接彼此
5. **最终形态 = 原子市场**：原子可被评分、组合成工作流 DAG、跨注册中心联邦共享

**作者的初衷**：构建一个真正可生长的 AI 工具生态——不是一个大而全的 Monolith，而是无数小而美的原子，通过知识图谱自然发现和组合。

---

## 技术架构

```
┌─────────────────────────────────────────────┐
│           Android 设备 (Termux)              │
│  ┌──────────────────┐  ┌──────────────────┐ │
│  │  Widget MCP APK  │  │  yuanzi-atoms/   │ │
│  │  (Kotlin + Nano) │  │  core, browser,  │ │
│  │  MCP JSON-RPC    │◄─┤  widget,         │ │
│  │  :McpServer port │  │  deepseek,       │ │
│  │  知识图谱 UI     │  │  obsidian        │ │
│  └──────┬───────────┘  └────┬─────────────┘ │
│         │                   │               │
│         └───────┬───────────┘               │
│                 │                           │
│         ┌───────▼──────────┐                │
│         │  agent.db (SQLite)│               │
│         │  atom_registry   │               │
│         │  atoms (legacy)  │               │
│         └──────────────────┘               │
└─────────────────────────────────────────────┘
         ▲                    ▲
         │ ADB sync           │ git push → CI
         │                    │
┌────────┴────────┐  ┌───────┴──────────────┐
│  开发机 (Win)   │  │  GitHub Actions CI   │
│  yuanzi-cli     │  │  black + ruff + test │
│  mcp-bridge     │  │  yuanzi validate     │
│  atoms/         │  └──────────────────────┘
└────────────────┘
```

### 原子系统架构

```
基础原子 (13个, 系统内置, 不可注册/不可删除)
  system.file-dir, system.file-read, system.file-write
  system.http-get, system.http-post
  system.math-calc, system.string-split, system.string-match
  system.json-parse, system.date-time
  system.hash-digest, system.encrypt-aes, system.decrypt-aes

注册原子 (61+, 可注册/可发现/可组合/可删除)
  mcp.postgres, mcp.mysql, mcp.s3, mcp.iam ...

通道 (5种类型, 原子间的数据血管)
  直通线 / 映射线 / 转换线 / 合并线 / 分流线
```

### 核心模块

| 模块 | 路径 | 职责 | 技术 |
|------|------|------|------|
| CLI 工具 | `yuanzi-cli/` | 原子开发：init / validate / test / build | Python 3.10+ |
| 原子模板 | `yuanzi-atom-templates/` | Cookiecutter 模板，标准化原子结构 | Cookiecutter |
| 原子服务 | `yuanzi-atoms/` | Android 运行时原子：core, browser, widget, deepseek, obsidian | Python 3 |
| MCP 桥接 | `mcp-yuanzi-bridge/` | 注册中心、原子导入、分类、登记表生成 | Python 3 + SQLite |
| 示例原子 | `atoms/` | 5 个基础示例：file-read, http-get, math-sum, string-split, template | Python + Docker |
| Android 客户端 | `widgetmcp_src/` | 知识图谱 UI、MCP 服务器、桌面小组件 | Kotlin + NanoHTTPD |

---

## 不可变的架构约束 (Invariants)

以下约束**不可自行修改**，涉及重大架构决策必须征求作者意见：

1. **atom_id 命名规范**：反向域名风格 `mcp.<name>` 或 `<org>.<domain>.<name>`，必须包含至少一个 `.`
2. **注册 Schema 不可降级**：`atom-registry-schema.json` 定义的必填字段（atom_id, name, purpose, architecture, ownership, lifecycle, signature）不可减少
3. **签名机制不可绕过**：每个原子必须通过 `compute_signature()` 生成内容+身份组合指纹，禁止手动写入 signature
4. **生命周期状态机不可简并**：submitted → reviewed → registered → running/offline/deprecated，状态转换路径不可跳过
5. **SQLite 表结构兼容**：`atom_registry` 和 `atoms` 表结构变更必须向后兼容，已有 61 个原子的数据不可丢失
6. **Android 是唯一运行时平台**：所有功能必须能在 Android Termux 环境中运行，不做传统服务器部署假设
7. **MCP JSON-RPC 接口不可变**：`McpServer.kt` 定义的 widget.* / system.health 方法签名不可改变（已有 Android 客户端依赖）

---

## 开发工作流

### 日常开发循环

```bash
# 1. 修改代码（在开发机上）
# 2. 运行本地测试
python -m pytest yuanzi-cli/tests -q
python -m pytest mcp-yuanzi-bridge/tests -q

# 3. 代码质量检查
black --check --config pyproject.toml .
ruff check --config pyproject.toml .

# 4. 同步到 Android 设备验证（需要 adb 连接）
scripts/sync-to-device.sh

# 5. 在 Android 设备上重启原子服务
sh /data/data/com.termux/files/home/yuanzi-project/start_yuanzi_termux.sh

# 6. 在 Android 设备上打开 Widget MCP App 验证图谱和小组件
```

### Git 工作流

- **主分支**：`main`（远程），本地 `main` 跟踪 `origin/main`
- **提交前必须**：pre-commit hooks 通过（black + ruff + yuanzi tests）
- **CI 触发**：push/PR 到 `main` 自动运行 `.github/workflows/ci.yml`
- **禁止**：直接在 Android 设备上修改代码然后提交（设备文件可能不同步）

### 安装 pre-commit hooks

```bash
scripts/install-hooks.sh
# 或
yuanzi install-hooks
```

---

## 多智能体协作规则

多个 AI 智能体同时在此项目上工作时，遵循以下协调规则：

### 模块所有权

| 模块 | 排他性 | 说明 |
|------|--------|------|
| `atom-registry-schema.json` | **全局锁** | 修改 schema 影响所有原子，需作者确认 |
| `mcp-yuanzi-bridge/registry.py` | **全局锁** | 注册中心核心逻辑，影响所有已注册原子 |
| `mcp-yuanzi-bridge/register_mcp_atoms.py` | 共享 | 分类逻辑、原子导入流程 |
| `mcp-yuanzi-bridge/tests/` | 共享 | 测试文件，添加新测试不冲突 |
| `yuanzi-cli/` | 共享 | CLI 命令独立，不同命令可并行开发 |
| `yuanzi-atoms/*/` | **每原子独立** | 每个子目录（core/browser/widget/deepseek/obsidian）独立 |
| `widgetmcp_src/` | **全局锁** | Android 客户端，Kotlin 代码耦合度高 |
| `atoms/` | **每原子独立** | 每个示例原子目录独立 |
| `scripts/` | 共享 | 脚本文件独立 |
| `ATOM_REGISTRY_LEDGER.*` | **自动生成** | 禁止手动编辑，通过 `register_mcp_atoms.py` 生成 |

### 冲突避免策略

1. **模块全局锁文件**：修改前检查是否有其他 agent 正在修改同一文件（通过 git diff 检查）
2. **原子级独立**：添加新原子或修改现有原子时，只影响自己的原子目录
3. **注册中心写入**：`submit_atom()` 使用 `ON CONFLICT DO UPDATE`，天然支持幂等写入
4. **测试隔离**：每个模块的测试独立运行，不依赖全局状态

### 重大改动决策矩阵

| 改动范围 | 决策方式 |
|----------|----------|
| 修改 `atom-registry-schema.json` 必填字段 | **必须征求作者** |
| 修改 `registry.py` 签名/去重算法 | **必须征求作者** |
| 修改 `McpServer.kt` MCP 方法签名 | **必须征求作者** |
| 添加新 MCP 方法（不改变现有） | 可自主决定 |
| 添加新原子 | 可自主决定 |
| 修改分类关键词 `CATEGORY_KEYWORDS` | 可自主决定（需更新测试） |
| 修改 CLI 命令行为 | 小改动自主，大改动征求 |
| 修改 CI 配置 | 可自主决定 |
| 修改 Android 部署脚本 | 可自主决定（需在 Android 设备上验证） |

---

## 代码规范

### Python（全项目通用）

```yaml
# 格式化：black (line-length=88)
# Lint：ruff (E, F, I, N, W)
# 类型注解：鼓励但非强制（pyproject.toml 未配置 mypy）
# Docstring：Google 风格
# Python 版本：3.10-3.12
```

**关键约定**：
- `from __future__ import annotations` 在所有新文件中使用
- 原子代码放在 `core.py`，HTTP 服务器放在 `server.py`
- 使用 `dataclass` 定义数据模型
- SQLite 操作使用 `sqlite3.Row` 作为 row_factory
- JSON 序列化使用 `json.dumps(..., ensure_ascii=False)`

### Kotlin（Android 客户端）

**关键约定**：
- Activity 使用代码布局（`LinearLayout` + 手动构建 View），不使用 XML
- 网络请求使用 `Thread {}` + `runOnUiThread {}` 模式
- 颜色使用 `getColor(R.color.xxx)`，不硬编码
- 日志使用 `AppLogger.i/e/d(tag, msg)`
- SharedPreferences 用于简单 KV 存储
- 小组件通过 `WidgetController` 管理生命周期

### 原子开发规范

每个原子目录必须包含：
```
<atom-id>/
├── Dockerfile
├── core.py          # 核心逻辑
├── server.py        # HTTP/MCP 接口
└── requirements.txt # 依赖
```

---

## 当前项目状态

### 阶段进度

| 阶段 | 状态 | 完成度 |
|------|------|--------|
| M1: 开发基础设施 | ✅ 已完成 | 100% |
| M2: 部署与配置 | ✅ 已完成 | 100% |
| M3: 测试与质量门禁 | 🔧 进行中 | ~90% |
| M4: 注册中心服务化 | 🔧 进行中 | ~15% |
| M5: 能力搜索与匹配 | ⭕ 未开始 | 0% |
| M6: 安全与多租户 | ⭕ 未开始 | 0% |
| M7: 原子市场与工作流 | ⭕ 未开始 | 0% |

### 已注册原子：61 个（全部 registered）

### M4 当前进展

- [x] Schema 迁移系统（任务 4.1）→ `mcp-yuanzi-bridge/migrations/`
- [ ] 原子版本化表（任务 4.2）
- [ ] REST API / FastAPI（任务 4.3）
- [ ] 健康探针系统（任务 4.4）
- [ ] 依赖图解析（任务 4.5）
- [x] 修复分类误判（任务 4.6）

### 技术债务

1. **分类误判修复**（已完成 2026-07-17）：token-based 分类替换子串匹配，测试覆盖 11 个场景
2. **Schema 迁移系统**（M4 计划）：当前无版本迁移机制
3. **原子覆盖率**：5 个示例原子有 smoke test（25 用例），61 个已注册 MCP 原子仍无自动化测试
4. **API Key 管理**：DeepSeek key 以 SharedPreferences 明文存储（M6 计划改进）
5. **Android 端口冲突**：硬编码端口，需支持环境变量覆盖

---

## 关键文件速查

| 用途 | 文件 |
|------|------|
| 项目计划 | `PROJECT_PLAN.md` |
| 注册 Schema | `atom-registry-schema.json` |
| 注册中心核心 | `mcp-yuanzi-bridge/registry.py` |
| Schema 迁移引擎 | `mcp-yuanzi-bridge/migrations/__init__.py` |
| 原子导入与分类 | `mcp-yuanzi-bridge/register_mcp_atoms.py` |
| 登记表 | `mcp-yuanzi-bridge/ATOM_REGISTRY_LEDGER.md` |
| CLI 入口 | `yuanzi-cli/yuanzi_cli/` |
| CI 配置 | `.github/workflows/ci.yml` |
| Pre-commit | `.pre-commit-config.yaml` |
| Python 配置 | `pyproject.toml` |
| Android 主 Activity | `widgetmcp_src/java/com/nous/widgetmcp/MainActivity.kt` |
| MCP 服务器 | `widgetmcp_src/java/com/nous/widgetmcp/McpServer.kt` |
| Termux 启动脚本 | `start_yuanzi_termux.sh` |
| ADB 同步 | `scripts/sync-to-device.sh` |

---

## 快速决策参考

**问：我该用 Python 还是 Kotlin 实现新功能？**
→ 后端逻辑（注册、分类、CLI）用 Python；Android UI/交互用 Kotlin

**问：新原子应该放在哪里？**
→ 核心服务原子放 `yuanzi-atoms/<name>/`；独立示例放 `atoms/<name>/`

**问：如何添加新的原子分类？**
→ 在 `register_mcp_atoms.py` 的 `CATEGORY_KEYWORDS` 中添加新类别和关键词，同时更新 `test_classification.py`

**问：registry.db 在开发机上不存在怎么办？**
→ 正常，registry.db 只在 Android 设备上（`/data/data/com.termux/files/home/yuanzi-data/agent.db`）运行，开发机只做代码逻辑验证

**问：如何验证 Android 设备上的改动生效？**
→ `scripts/sync-to-device.sh` 同步后，在 Termux 中运行 `start_yuanzi_termux.sh` 重启服务
