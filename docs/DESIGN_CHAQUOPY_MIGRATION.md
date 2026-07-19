# Chaquopy 嵌入式迁移方案

> **状态**: `📐 design-ready`
> **目标**: 去掉 Termux 依赖，Python 直接跑在 APK 里
> **原则**: 不改 Python 代码，不重写测试

---

## 一、架构变化

```
迁移前:
  ┌──────┐    localhost     ┌──────────────────┐
  │ APK  │ ──── HTTP ────→  │ Termux (独立App) │
  │      │ ←── HTTP ────    │ Python 后端      │
  └──────┘                  │ agent.db         │
                            └──────────────────┘

迁移后:
  ┌──────────────────────────┐
  │         APK               │
  │  ┌────────────────────┐  │
  │  │ Chaquopy (Python)  │  │
  │  │ registry.py        │  │
  │  │ api.py             │  │
  │  │ yuanzi-atoms/      │  │
  │  │ agent.db           │  │
  │  └────────────────────┘  │
  │  ┌────────────────────┐  │
  │  │ Kotlin UI          │  │
  │  │ GraphView          │  │
  │  │ McpServer          │  │
  │  └────────────────────┘  │
  └──────────────────────────┘
```

API 通信从 `localhost HTTP` 变为 `进程内调用`。

---

> 计数已按代码现状刷新：APK 内嵌 `app/src/main/python/migrations/` 为 11 个
> （001–011，含 009_workflows、010_atom_reviews、011_federation_peers）；
> mcp-yuanzi-bridge 仓库侧已增至 13 个（001–013），后续同步需跟随。

## 二、不变的部分

```
✅ registry.py (957 行)      — 一行不改
✅ api.py (200+ 行)          — 一行不改
✅ register_mcp_atoms.py     — 一行不改
✅ migrations/*.sql (11 个, 001–011) — 一行不改
✅ yuanzi-atoms/*/           — 一行不改
✅ base-atoms/*/             — 一行不改
✅ 277 测试                   — 一条不改
✅ atom-registry-schema.json — 不改
```

---

## 三、需要改的部分

### 3.1 目录结构

```
widgetmcp_src/
├── app/
│   ├── build.gradle              ← 添加 Chaquopy 插件
│   ├── src/
│   │   ├── main/
│   │   │   ├── java/              ← Kotlin 代码 (不变)
│   │   │   ├── python/            ← 新增: Python 源码
│   │   │   │   ├── registry.py
│   │   │   │   ├── api.py
│   │   │   │   ├── register_mcp_atoms.py
│   │   │   │   ├── generate_registry_ledger.py
│   │   │   │   ├── mcp_atoms.json
│   │   │   │   ├── migrations/
│   │   │   │   │   ├── 001_init.sql
│   │   │   │   │   └── ...
│   │   │   │   └── yuanzi-atoms/
│   │   │   │       ├── core/
│   │   │   │       ├── browser/
│   │   │   │       └── ...
│   │   │   ├── res/               ← 资源 (不变)
│   │   │   └── AndroidManifest.xml
```

### 3.2 build.gradle 变更

```groovy
plugins {
    id 'com.chaquo.python' version '16.0.0'
}

android {
    defaultConfig {
        python {
            buildPython "/usr/bin/python3"
            pip {
                install "fastapi"
                install "uvicorn"
                install "pydantic"
                install "requests"
                install "jsonschema"
                install "pyyaml"
                install "cryptography"
            }
        }
        // ABI 裁剪: 只打 ARM 平板所需架构, 控制体积
        ndk { abiFilters "arm64-v8a", "armeabi-v7a" }
    }
}
```

> pip 清单已与 `app/build.gradle:23-31` 现状对齐：在最初的 fastapi/uvicorn/pydantic
> 之上，实际还安装 requests/jsonschema/pyyaml/cryptography 四个包。

### 3.3 DB 路径变更

```
迁移前:
  /data/data/com.termux/files/home/yuanzi-data/agent.db

迁移后:
  context.getFilesDir() + "/agent.db"
  → /data/data/com.nous.widgetmcp/files/agent.db
```

共两处硬编码要改（均为 env `YUANZI_DB_PATH` 兜底 filesDir 的同一模式）：
`register_mcp_atoms.py` 与 `generate_registry_ledger.py`。

```python
# 改前
DB_PATH = Path("/data/data/com.termux/files/home/yuanzi-data/agent.db")

# 改后
import os
DB_PATH = Path(os.environ.get("YUANZI_DB_PATH",
    "/data/data/com.nous.widgetmcp/files/agent.db"))
```

### 3.4 启动流程变更

```
迁移前:
  Termux: sh start_yuanzi_termux.sh
  APK: 等待 :8081 可达

迁移后:
  APK 启动 → Chaquopy 初始化 → Python 服务启动
  → :8081 立即可达
  → 零等待
```

start_yuanzi_termux.sh 不再需要。

---

## 四、Chaquopy 调用方式

Kotlin 调用 Python:

```kotlin
// 启动 API 服务
val py = Python.getInstance()
val apiModule = py.getModule("api")
apiModule.callAttr("start_server", filesDir.absolutePath)

// 注册原子
val registry = py.getModule("register_mcp_atoms")
registry.callAttr("main")

// 查询原子
val atom = py.getModule("registry").callAttr("get_atom", "mcp.postgres")
```

或者保持 HTTP 调用不变——Python FastAPI 仍然监听 `127.0.0.1:8081`，Kotlin 照旧用 `YuanziApi.kt` 发 HTTP 请求。两种方式都行。

**建议：保持 HTTP 调用。Kotlin 代码一行不改。**

---

## 五、依赖检查

```
当前 Python 依赖 (与 app/build.gradle pip 清单一致):
  ✅ fastapi         ← 纯 Python, Chaquopy 支持
  ✅ uvicorn         ← 纯 Python, Chaquopy 支持
  ✅ pydantic        ← 纯 Python, Chaquopy 支持
  ✅ requests        ← 纯 Python, Chaquopy 支持
  ✅ jsonschema      ← 纯 Python, Chaquopy 支持
  ✅ pyyaml          ← 纯 Python (libyaml 可选), Chaquopy 支持
  ⚠️ cryptography    ← 含 C 扩展, 但 Chaquopy 官方提供预编译 wheel, 可用
  ✅ cookiecutter    ← 纯 Python
  ✅ typer           ← 纯 Python
  ✅ sqlite3         ← 标准库, Chaquopy 内置

  ❌ numpy           ← 未使用
  ❌ lxml            ← 未使用
  ❌ sentence-transformers ← M5 可选, 可装
```

除 cryptography 外全部纯 Python。cryptography 虽含 C 扩展，但 Chaquopy
官方仓库提供其预编译包，无需本机编译——"零 C 扩展"的原结论按此修正。

---

## 六、APK 体积影响

> 现状注记: `app/build.gradle:34` 已启用 ABI 裁剪
> (`abiFilters arm64-v8a, armeabi-v7a`)，仅打两种 ARM 架构；
> 下列估算为全 ABI 口径，裁剪后实际体积应低于此。

```
Kotlin 代码 (编译后)     ~500KB
Chaquopy Python 运行时    ~20MB
Python 源码 + 依赖         ~5MB
agent.db (61 atoms)       ~500KB
SQL 迁移文件               ~10KB
─────────────────────────────────
总计新增                   ~25MB
APK 总体积                 ~30MB
```

---

## 七、实施步骤

| # | 步骤 | 工作量 |
|---|------|--------|
| 1 | 添加 Chaquopy Gradle 插件 | 10 min |
| 2 | 复制 Python 源码到 `src/main/python/` | 5 min |
| 3 | 修改 DB_PATH (2 个文件) | 5 min |
| 4 | Kotlin 启动时初始化 Python | 30 min |
| 5 | 删除 Termux 启动脚本依赖 | 10 min |
| 6 | 277 测试验证 (pytest 照常) | 10 min |
| 7 | APK 构建 + 真机验证 | 30 min |

**总工作量: ~2 小时。Python 代码零改动。**

---

> **Termux 是临时的脚手架。Chaquopy 是终点——一个 APK，安装即用，无需额外环境。**
