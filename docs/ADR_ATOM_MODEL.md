# ADR: 原子分层模型

> **性质**: 架构决策记录 (Architecture Decision Record)
> **作者**: Arch
> **日期**: 2026-07-18
> **状态**: 已决策

---

## 背景

当前项目存在两套原子模型：

- `atoms/` 下的 5 个基础原子：`core.handler(data)` 接口，三个标准端点
- `atom_registry` 表中的 61 个注册原子：MCP JSON-RPC 接口，完整元数据

两套模型互不连通——基础原子进不了注册中心，注册原子也没有标准端点。这是架构基座问题，必须统一。

---

## 决策

### 1. 两层模型

```
基础原子                    注册原子
(系统内置，不可注册/不可删除)  (可注册/可版本化/可发现)
─────────────────────────   ─────────────────────────
文件夹                       mcp.postgres
文件读写                     mcp.s3
HTTP 请求                   mcp.iam
数学运算                    mcp.cloudwatch
字符串处理                  mcp.dynamodb
日期时间                    ... (61 个)
JSON / 正则
加密解密                    特性:
                             · 可依赖基础原子
特性:                         · 有外部服务依赖
 · 单操作，无依赖             · 领域特定
 · 确定性输入输出             · 需要签名/版本/分类/合规
 · 通用，跨场景复用           · 可注册、可发现、可组合
 · 无需注册流程               · 可删除（基础原子不可删）
```

### 2. 统一接口

所有原子（基础+注册）必须实现三个标准端点：

```
GET  /health  → {"status": "ok"}
GET  /meta    → {"atom_id": "...", "name": "...", "type": "...", "schema": {...}}
POST /run     → 调用 handler(data)
```

基础原子和注册原子的 **handler 签名统一**：

```python
def handler(data: dict) -> dict:
    # 成功: {"status": "success", "data": {...}}
    # 失败: {"status": "error", "message": "..."}
```

### 3. 运行环境

所有原子运行在 **Linux** 环境（Android Termux = Android 上的 Linux 用户空间）。

```
原子运行时:
  Linux (Termux on Android)
  ├─ Python 3.10+ 
  ├─ 基础原子: 内置于系统镜像
  └─ 注册原子: 通过注册中心拉取 + Docker/进程运行
```

### 4. 知识图谱可见性

| | 基础原子 | 注册原子 |
|---|---|---|
| 图谱中可见 | ✅ 可见 | ✅ 可见 |
| 可注册 | ❌ 不可 | ✅ 可 |
| 可删除 | ❌ 不可 | ✅ 可 |
| 可搜索 | ✅ 可 | ✅ 可 |
| 可组合 | ✅ 作为依赖 | ✅ 作为目标 |

在 Android 知识图谱中，基础原子以特殊样式呈现（如灰色/虚线边框），区别于可操作的注册原子。

---

## 影响

### 需要改的

| 项目 | 变更 |
|------|------|
| 基础原子接口 | `server.py` 统一为三个端点 |
| 注册原子 | 需要实现 `/health` `/meta` `/run` 端点 |
| 注册中心 | `atom_registry` 新增 `is_base: bool` 字段 |
| 知识图谱 | UI 区分基础/注册原子样式 |
| API | 基础原子返回不可注册/不可删除 |

### 不需要改的

| 项目 | 说明 |
|------|------|
| 签名机制 | 基础原子不需要签名（内置） |
| 自动分类 | 基础原子预分类 |
| 版本管理 | 基础原子随系统版本升级 |

---

## 基础原子清单（建议）

```
系统级:
  file-dir        文件夹操作
  file-read       文件读取
  file-write      文件写入
  http-get        HTTP GET 请求
  http-post       HTTP POST 请求

计算级:
  math-calc       数学运算
  string-split    字符串拆分
  string-match    正则匹配
  json-parse      JSON 解析
  date-time       日期时间处理

安全级:
  hash-digest     哈希计算
  encrypt-aes     AES 加密
  decrypt-aes     AES 解密
```

---

> **这是原子生态的基座定义。所有后续架构决策以此为准。**
