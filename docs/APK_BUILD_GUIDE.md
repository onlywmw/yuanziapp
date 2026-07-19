# APK 构建指南

> **用途**: 构建 Widget MCP Android 客户端
> **源码**: `widgetmcp_src/`
> **注意**: 不是通用 Android 指南——只写这个项目的特定风险点

---

## 一、APK 定位

APK 是整个 Yuanzi 系统的**唯一用户界面**。它不包含业务逻辑——所有计算在 Python 后端完成。

```
APK (Android UI)
  ├─ 知识图谱渲染       ← GraphView (基础原子灰底 + 注册原子白底 + 通道动画)
  ├─ 原子市场浏览       ← M7 市场视图 (评分/评论/排行)
  ├─ 工作流画布         ← M7 DAG 编辑器 (拖拽连线)
  ├─ MCP Server         ← NanoHTTPD :8766 (widget 操作, McpService 默认端口)
  └─ REST Client        ← 调用 :8080 (Yuanzi Core /graph、/agent/*)
                          调用 :8081 (注册中心 /health、/search 等)

Python 后端 (Chaquopy 内嵌于 APK)
  ├─ yuanzi-atoms/      ← 核心原子服务 (Core :8080)
  ├─ api.py             ← FastAPI 注册中心 :8081
  └─ agent.db           ← 注册中心
```

**APK 和后端通过 localhost 通信。** 这是最关键的设计约束。

---

## 二、构建依赖

### 真实构建入口：Gradle

Chaquopy 迁移后，APK 构建的唯一真实入口是 Gradle：

```
widgetmcp_src/settings.gradle   ← rootProject "widgetmcp", include ':app'
widgetmcp_src/app/build.gradle  ← com.android.application + kotlin-android
                                  + com.chaquo.python 16.0.0 插件
                                  (Kotlin 源指向 ../java，资源 ../res，
                                   Python 源在 app/src/main/python)
```

```bash
cd widgetmcp_src
gradle :app:assembleDebug      # 仓库未附 gradlew，需本机已安装 Gradle
```

注意：仓库**没有 gradlew**，需使用系统 Gradle（版本需支持 Chaquopy 16.0.0 与
compileSdk 34）。`build.sh` / `build_adb.sh` 是 Termux/proot 时代的**辅助同步
脚本**（tar 同步源码 + 远端 aapt2/d8 手工链路），不含 Chaquopy 插件与内嵌
Python 打包，无法产出当前形态的 APK，仅保留给无 Gradle 的环境应急。

### 手工链路依赖（仅 build.sh 旧链路需要，不在 git 仓库中）

| 文件 | 位置 | 获取方式 |
|------|------|----------|
| android.jar | `widgetmcp_src/android.jar` | 从 Android SDK `platforms/android-34/android.jar` 复制 |
| kotlin-stdlib | `widgetmcp_src/libs/kotlin-stdlib-1.9.20.jar` | Maven 下载 |
| nanohttpd | `widgetmcp_src/libs/nanohttpd-2.3.1.jar` | Maven 下载 |

Gradle 链路不需要手动准备上述 jar（Kotlin/依赖由插件自动解析），但需要
Android SDK + 本机 Python 3.x（Chaquopy `buildPython` 指向）。

### 旧手工链路命令（辅助，已非真实入口）

```bash
cd widgetmcp_src
sh build.sh          # 仅编译 APK（Termux/proot 远端手工链路）
sh build_adb.sh      # 编译 + adb 安装到设备
```

---

## 三、通信架构

```
APK 内部                          Python 后端 (Chaquopy 内嵌)
────────                          ─────────────────────────
YuanziApi.kt ──→ Core :8080 ───→ yuanzi-atoms/core/main.py
  (图谱/代理)    /graph           (/health、/graph、/register、
                /agent/event      /agent/command、/agent/command/poll、
                /agent/command/*  /agent/event)

YuanziApi.kt ──→ REST :8081 ───→ api.py → registry.py → agent.db
  (查询/搜索)    /health           (FastAPI 注册中心, 内嵌启动)
                /search (GET/POST)
                /atoms ...

McpServer.kt ←── MCP :8766 ───→ widget 操作
  (JSON-RPC)    widget.create     (McpService 默认 mcp_port=8766,
                widget.update      SharedPreferences 可改)
                widget.delete

YuanziSync.kt ──→ :8080/graph ──→ 知识图谱数据
  (图谱轮询)
```

### 端口约定（以代码现实为准）

| 端口 | 服务 | 说明 |
|------|------|------|
| 8766 | McpServer (APK 内嵌) | widget JSON-RPC，McpService 默认 `mcp_port` |
| 8080 | Yuanzi Core (Python) | /graph、/agent/*，env `YUANZI_CORE_PORT` |
| 8081 | 注册中心 FastAPI (Python) | /health、/search、/atoms 等，`api.start_server` 默认端口 |

### localhost 通信的特殊处理

```
AndroidManifest.xml 必须声明:
  android:usesCleartextTraffic="true"

原因: APK 与内嵌 Python 服务（Core :8080 / 注册中心 :8081）都在同一设备上，
     通过 http://127.0.0.1 通信，不走 TLS。
     没有这个声明，Android 9+ 会拦截 HTTP 请求。
```

---

## 四、知识图谱渲染

### 节点类型 → 视觉样式

| 原子类型 | 边框 | 底色 | 交互 |
|----------|------|------|------|
| 基础原子 (system.*) | 灰色虚线 | 浅灰 | 不可点击删除 |
| 注册原子 | 白色实线 | 按分类着色 | 可点击/删除 |
| CENTER (组件MCP) | clay色 | 深底白字 | 固定位置 |
| YUANZI (中枢) | 状态色 | 深底白字 | 配置入口 |
| BROWSER (浏览器) | 深clay色 | 深底白字 | 跳转浏览器 |
| ADD_TEMPLATE | 浅色 | 白底黑字 | 添加组件 |

### 通道渲染（新需求 - M7）

```
GraphView 需要新增通道绘制:

  直通线: 实线, 数据流箭头
  映射线: 虚线, 字段名标注
  转换线: 波浪线, 类型标注
  合并线: 汇聚节点 → 宽箭头
  分流线: 分叉节点 → 多个细箭头

  动脉 (输出): 红色动画, 快流速
  静脉 (输入): 蓝色动画, 慢流速
  阻断 (错误): 红色虚线, 闪烁

通道渲染在 GraphEdge.kt 中实现，
或新增 ChannelRenderer.kt 专门处理。
```

---

## 五、必须小心的 6 个坑

### 1. atoms VIEW 不可写入

```
APK 中的 WidgetInstanceManager 或同步逻辑
如果直接写入 atoms 表 → 会失败（atoms 现在是 VIEW）

正确做法: 所有数据变更走 REST API → registry.py → atom_registry
```

### 2. 基础原子不可删除

```
GraphView 的 onNodeClick 需要检查节点类型:
  if (node.type == BASE_ATOM) → 不显示删除选项
  if (node.type == REGISTERED) → 可以删除
```

### 3. 作者字段必须展示

```
原子详情面板必须显示 ownership.author。
没有作者的原子 = 数据不完整。
```

### 4. 端口 8766/8080/8081 冲突

```
如果设备上已有其他服务占用这三个端口之一:
  McpServer: 默认 8766，SharedPreferences "widget_mcp".mcp_port 可配置
  Yuanzi Core: 默认 8080，env YUANZI_CORE_PORT 可改
  注册中心: 默认 8081，api.start_server(port=...) 参数可改
  APK 侧对应: YuanziConfig.port (Core) / YuanziConfig.registryPort (注册中心)
```

### 5. Termux 环境重置

> 现状注记: Chaquopy 迁移后 Python 已内嵌 APK，Termux 进程被杀的场景不再适用；
> 等价风险变为内嵌 Python 启动失败（PythonBridge.ensureStarted 返回 false），
> 下述"检查 /health + 重试不崩溃"的防御逻辑仍然需要。

```
Android 系统可能杀死 Termux 后台进程。
APK 需要:
  · 启动时检查后端是否可达 (/health)
  · 不可达时显示"等待 Yuanzi Core 启动"
  · 不崩溃，持续重试
```

### 6. 基础原子随 APK 版本升级

> 现状注记: 当前 Kotlin 侧并无基础原子硬编码列表（全库 Grep 无 BASE_ATOM/file-read 痕迹），
> 基础原子随内嵌 Python 源码（base-atoms/）进 APK，升级时一并更新。

```
基础原子列表硬编码在 APK 中（不是从后端动态获取）:
  · APK 升级时基础原子列表同步更新
  · 或者从 /api/v1/atoms?type=base 动态获取
```

---

## 六、与后端版本绑定

```
APK 版本          要求的后端版本
────────          ──────────────
v1.0 (当前)       注册中心 v2 + 61 atoms
v2.0 (M7 后)      需要 /api/v1/workflows 端点
                  需要 /api/v1/market 端点
                  需要基础原子 GET /atoms?type=base

APK 启动时检查版本兼容性:
  GET /health → {"version": "2.0", "schema_version": "008"}
  APK 检查 version 字段，不兼容时提示升级
```

---

## 七、签名与发布

```
debug APK (开发用):
  keytool 自动生成，可直接 adb install

release APK (发布用):
  需要正式的 keystore
  签名后才能发布到市场或分发给用户

注意:
  · debug 和 release 签名不同 → 数据不互通
  · 升级时签名必须一致
  · McpWidgetProvider 在 AndroidManifest 中注册
    → 签名变更会导致桌面小组件失效
```

---

> **APK 是用户唯一能触摸到的部分。后端做得再好，APK 卡顿或崩溃 = 整个系统失败。**
