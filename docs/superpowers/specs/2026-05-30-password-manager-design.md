# PM — 本地密码管理器设计规格

## 概述

PM 是一个本地优先的密码管理器，管理账号密码、API 密钥、云服务器信息、代码仓库令牌等凭据。CLI + 本地 Web 界面，纯本地加密存储，支持手动导出/导入跨设备同步，提供 MCP Server 供 Claude Code 集成调用。

## 核心架构：Daemon 模式

CLI 和 Web 共用一个后台守护进程持有解密数据：

```
pm unlock / pm web → 启动 pm-daemon（解密 vault 到内存）
pm get / pm list  → CLI → HTTP(127.0.0.1) → daemon → 返回结果
浏览器             → HTTP(127.0.0.1) → daemon → Web 页面 + API
Claude Code        → MCP(stdio) → pm mcp → HTTP → daemon
pm lock            → daemon 清空内存并退出
```

- **daemon**：唯一持有明文数据，启动时随机端口，端口写入 `~/.pm/runtime`
- **自动锁定**：默认 5 分钟无操作自动退出
- **CLI 和 Web 是平行客户端**，共享同一份解密数据

## 数据模型

四种凭据类型，JSON 结构，`fields` 按类型不同：

### account（账号密码）

| 字段 | 说明 |
|------|------|
| username | 用户名/邮箱 |
| password | 密码 |
| url | 登录地址 |
| email | 关联邮箱 |

### api_key（API 密钥）

| 字段 | 说明 |
|------|------|
| key | API Key |
| secret | API Secret |
| endpoint | API 端点 URL |

### server（云服务器）

| 字段 | 说明 |
|------|------|
| host | IP 或域名 |
| port | 端口（默认 22） |
| username | 登录用户 |
| password | 密码或密钥路径 |
| provider | 云厂商 |
| region | 地域 |

### token（代码仓库令牌）

| 字段 | 说明 |
|------|------|
| token | 令牌值 |
| repo_url | 仓库地址 |
| username | 关联用户名 |
| expires_at | 过期日期 |

每条记录通用字段：`id`、`type`、`title`、`notes`、`created_at`、`updated_at`。

## 加密与安全

### 密钥派生

```
主密码 → Argon2id(salt=16B, memory=64MB, iterations=3) → AES-256 密钥(32B)
```

- salt 在 `pm init` 时生成，明文存储
- 不解密无法验证密码正确性（不存密码哈希）

### 数据加密

```
明文 JSON → AES-256-GCM(密钥, nonce=12B) → 密文 + nonce + auth_tag → vault.pm
```

- 每次保存生成新 nonce，相同明文产生不同密文
- GCM 模式同时提供加密和防篡改
- 整个 vault 整体加密

### 运行时措施

- 磁盘始终密文
- 明文仅存在于 daemon 进程内存
- 自动锁定 5 分钟（可配置）
- `pm copy` 剪切板 30 秒后清除
- 绝不以任何形式记录密钥到日志

## CLI 命令

```
pm init              初始化 vault，设置主密码
pm unlock            解锁 vault（启动 daemon）
pm lock              锁定 vault（停止 daemon）
pm add               交互式添加凭据
pm add -t api_key    指定类型添加
pm scan              粘贴原始文本，自动识别类型和字段
pm list              列出所有凭据标题
pm list -t server    按类型列出
pm get <query>       搜索凭据
pm show <id>         查看完整详情（含密钥）
pm copy <id>         复制密码/密钥到剪切板
pm edit <id>         编辑凭据
pm rm <id>           删除凭据
pm export [path]     导出加密备份
pm import <file>     导入并合并备份
pm web               启动 Web 界面
pm mcp               启动 MCP Server（供 Claude Code 调用）
pm status            查看 daemon 运行状态
```

### pm scan 工作流

粘贴任意格式文本，两层识别：
1. **规则层**：正则匹配 IP、域名、端口、URL、常见 key 前缀（`sk-`、`ghp_`、`glpat-`）、SSH 连接串
2. **关键词层**：字段映射（"密码"→password、"服务器"→host、"密钥"→key）
3. 自动推断 type，展示解析结果，用户确认后保存

## Web 界面

本地单页应用，`localhost:<port>`：

- **搜索页**：顶部搜索框，实时过滤，按类型切换标签
- **详情面板**：点击条目展开，显示字段，一键复制
- **添加/编辑**：模态表单，按类型切换字段
- **锁定页**：未解锁时显示主密码输入框

技术：FastAPI 提供 API + 静态页面，前端原生 HTML/JS，无框架依赖。

## MCP Server（Claude Code 集成）

`pm mcp` 启动 stdio MCP Server，暴露：

| Tool | 用途 |
|------|------|
| `search_credentials(query, type?)` | 搜索凭据，返回匹配列表（不含密钥） |
| `get_credential(id)` | 获取完整凭据信息（需用户批准） |
| `list_credentials(type?)` | 列出所有凭据摘要 |
| `add_credential(type, fields)` | 新增凭据 |

Claude Code 配置（`.claude.json` 或 `settings.json`）：

```json
{
  "mcpServers": {
    "pm": {
      "command": "pm",
      "args": ["mcp"]
    }
  }
}
```

`get_credential` 返回密钥内容时要求用户手动批准，确保敏感信息不会自动泄露。

## 备份与同步

```
pm export → vault_2026-05-30.pm.backup
           ↓ 手动拷贝（U盘/云盘/内网传输）
pm import ./vault_2026-05-30.pm.backup
```

- 导出文件与原文件使用相同 AES 加密，备份丢失仍是密文
- 导入时按 id 合并去重，同名条目保留最新修改时间

## 文件结构

```
~/.pm/
├── runtime              # daemon 端口号（daemon 运行时存在）
├── vault.pm             # 加密后的凭据数据
├── salt                 # Argon2id salt
└── config.json          # 配置（自动锁定时间等）
```

## 技术栈

| 层 | 选型 |
|----|------|
| 语言 | Python 3.12+ |
| CLI | Click + Rich |
| Web 后端 | FastAPI + uvicorn |
| Web 前端 | 原生 HTML/JS，无框架 |
| 加密 | cryptography (AES-256-GCM, Argon2id) |
| MCP | mcp (Python SDK) |
| 数据格式 | JSON，整体加密后存文件 |
