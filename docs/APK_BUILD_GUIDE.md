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
  ├─ MCP Server         ← NanoHTTPD :8080 (widget 操作)
  └─ REST Client        ← 调用 :8081 (原子查询/搜索)

Python 后端 (Termux)
  ├─ yuanzi-atoms/      ← 核心原子服务
  ├─ api.py             ← FastAPI :8081
  └─ agent.db           ← 注册中心
```

**APK 和后端通过 localhost 通信。** 这是最关键的设计约束。

---

## 二、构建依赖

### 必须手动准备的文件（不在 git 仓库中）

| 文件 | 位置 | 获取方式 |
|------|------|----------|
| android.jar | `widgetmcp_src/android.jar` | 从 Android SDK `platforms/android-34/android.jar` 复制 |
| kotlin-stdlib | `widgetmcp_src/libs/kotlin-stdlib-1.9.20.jar` | Maven 下载 |
| nanohttpd | `widgetmcp_src/libs/nanohttpd-2.3.1.jar` | Maven 下载 |

### 构建命令

```bash
cd widgetmcp_src
sh build.sh          # 仅编译 APK
sh build_adb.sh      # 编译 + adb 安装到设备
```

---

## 三、通信架构

```
APK 内部                          Python 后端 (Termux)
────────                          ──────────────────
YuanziApi.kt ──→ REST :8081 ──→ api.py → registry.py → agent.db
  (原子查询)     /atoms            (FastAPI)
                /search
                /health

McpServer.kt ←── MCP :8080 ──→ widget 操作
  (JSON-RPC)    widget.create
                widget.update
                widget.delete

YuanziSync.kt ──→ :8081/stats ──→ 知识图谱数据
  (图谱轮询)
```

### 端口约定

| 端口 | 服务 | 说明 |
|------|------|------|
| 8080 | McpServer (APK 内嵌) | widget JSON-RPC |
| 8081 | FastAPI (Python) | 原子 REST API |

### localhost 通信的特殊处理

```
AndroidManifest.xml 必须声明:
  android:usesCleartextTraffic="true"

原因: APK 和 Termux Python 服务都在同一设备上，
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

### 4. 端口 8080/8081 冲突

```
如果设备上已有其他服务占用 8080 或 8081:
  McpServer 端口在代码中硬编码 → 需要改为可配置
  REST API 端口在 Termux 启动脚本中 → YUANZI_API_PORT 环境变量
```

### 5. Termux 环境重置

```
Android 系统可能杀死 Termux 后台进程。
APK 需要:
  · 启动时检查后端是否可达 (/health)
  · 不可达时显示"等待 Yuanzi Core 启动"
  · 不崩溃，持续重试
```

### 6. 基础原子随 APK 版本升级

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
