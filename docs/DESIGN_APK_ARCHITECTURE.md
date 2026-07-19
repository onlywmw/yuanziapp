# APK 客户端架构设计

> **状态**: `📐 design-ready`
> **作者**: Arch
> **日期**: 2026-07-19
> **前置**: M1-M7 后端全部就绪

---

## 1. 定位

APK 是 Yuanzi 系统的**唯一人机界面**。它不包含业务逻辑——所有计算、存储、搜索在后端完成。

```
┌──────────────────────────────────────────────────┐
│  Android 设备                                     │
│                                                   │
│  ┌─────────────┐     HTTP       ┌──────────────┐ │
│  │   APK        │ ←──────────→  │ Python 后端   │ │
│  │  (Kotlin)   │  localhost    │ (Chaquopy     │ │
│  │             │  :8081 注册中心│  内嵌)        │ │
│  │  知识图谱    │  :8080 Core   │  api.py      │ │
│  │  原子市场    │  :8766 内嵌MCP│  registry.py │ │
│  │  工作流画布  │               │  agent.db    │ │
│  └─────────────┘               └──────────────┘ │
│                                                   │
│  用户触摸              后端运算                   │
└──────────────────────────────────────────────────┘

端口矩阵（以代码现实为准）:
  8766  APK 内嵌 McpServer (McpService 默认 mcp_port, widget JSON-RPC)
  8080  Yuanzi Core (yuanzi-atoms/core/main.py, /graph、/agent/*)
  8081  注册中心 FastAPI (内嵌 api.py, /health、/search、/atoms 等)
```

---

## 2. 页面架构

```
ViewFlipper (三页切换)

  Page 0: 首页 (知识图谱)
    ├─ GraphView (自定义 Canvas)
    │   ├─ 节点渲染 (基础/注册/CENTER/YUANZI/BROWSER)
    │   ├─ 连线渲染 (直通/映射/转换/合并/分流)
    │   └─ 触摸交互 (点击/拖拽/缩放)
    ├─ 本地添加节点 (余额/文本/Obsidian)
    └─ 状态卡片 (Yuanzi 连接状态)

  Page 1: DeepSeek 配置
    ├─ API Key 输入
    ├─ 连接测试
    ├─ 桌面预览
    └─ 刷新间隔设置

  Page 2: Yuanzi 设置
    ├─ 连接地址配置
    ├─ 同步控制
    ├─ 事件上报测试
    └─ 轮询开关
```

---

## 3. 知识图谱渲染

### 3.1 节点规格

| 节点类型 | 形状 | 底色 | 边框 | 文字色 | 半径 | 交互 |
|----------|------|------|------|--------|------|------|
| CENTER (组件MCP) | 圆形 | clay | 无 | 白 | 56dp | 无 |
| YUANZI (中枢) | 圆形 | sage/amber/rust | 无 | 白 | 48dp | 跳转设置 |
| BROWSER (浏览器) | 圆形 | clay深 | 无 | 白 | 44dp | 打开浏览器 |
| **BASE (基础原子)** | **圆角矩形** | **灰底** | **灰色虚线** | **黑** | **40dp** | **不可删** |
| **REGISTERED (注册原子)** | **圆角矩形** | **按分类着色** | **白色实线** | **黑** | **42dp** | **可点击看详情** |
| ADD_TEMPLATE | 圆角矩形 | 浅色 | 无 | 黑 | 40dp | 添加组件 |
| **AUTHOR_NODE (作者)** | **菱形** | **金色** | **无** | **白** | **36dp** | **查看作者所有原子** |

### 3.2 连线规格（通道渲染）

```
每种线有独立绘制逻辑:

  直通线 (DIRECT)
    实线, 2dp 粗, 颜色=hairline
    箭头指向数据流方向
    动画: 无

  映射线 (MAP)
    虚线 (4dp dash + 2dp gap), 1.5dp 粗, 颜色=clay
    中间标注字段名 (body→text)
    动画: 无

  转换线 (TRANSFORM)
    波浪线 (sin 曲线), 1.5dp 粗, 颜色=amber
    中间标注类型名 (number→string)
    动画: 无

  合并线 (MERGE)
    两条源线汇聚为一个节点 → 宽箭头 (3dp)
    颜色=sage
    动画: 汇聚动画 (两个小点流向一个点)

  分流线 (SPLIT)
    一个源节点分叉为两条目标线
    颜色=clay_light
    动画: 分流动画 (一个点分裂为两个)

数据流动画:
  动脉 (输出): 红色小点沿连线流动, 速度 2px/帧
  静脉 (输入): 蓝色小点反向流动, 速度 1px/帧
  阻断 (错误): 红色虚线, 静止, 节点边框闪烁
```

### 3.3 颜色映射

```
分类颜色:
  Database          → amber
  Cloud & Storage   → clay_light
  Document & Data   → sage
  Web & Browser     → clay_deep
  AI & Model        → rust
  Integration       → sage_light
  Security          → rust_deep

数据类型颜色 (通道用):
  string  → 蓝
  number  → 绿
  object  → 橙
  binary  → 紫
```

---

## 4. 数据流

### 4.1 图谱数据获取

```
YuanziApi.fetchGraph()
  → GET http://127.0.0.1:8080/graph        (Yuanzi Core, 非注册中心)
  → 解析 JSON → GraphTopology(nodes, edges)
  → GraphView.setData(nodes, edges)
  → 重绘 Canvas

轮询: YuanziPollScheduler (可配置间隔)
  默认: 30 分钟
  可选手动刷新
```

### 4.2 原子搜索 (M5.4)

```
YuanziSearch.search(query)
  → GET http://127.0.0.1:8081/search?q=... (注册中心; 后端同时提供 POST)
  → 返回匹配原子列表
  → 高亮匹配节点, 其他节点变灰
```

### 4.3 工作流执行 (M7)

```
YuanziApi.executeWorkflow(workflowId)
  → POST http://127.0.0.1:8081/workflows/{id}/run
  → SSE 流式返回节点状态
  → GraphView 实时更新节点和通道颜色
```

---

## 5. 与后端协议

### 5.1 启动握手

```
1. APK 启动
2. 检查后端可达: GET :8081/health
3. 可达 → 拉取图谱数据
4. 不可达 → 显示"等待 Yuanzi Core 启动", 每 5 秒重试
5. 拉取成功 → 渲染图谱
6. 启动轮询定时器
```

### 5.2 版本兼容检查

```
GET :8081/health
→ {"version": "1.0", "schema_version": "008_audit_chain"}

APK 检查 version:
  主版本号匹配 → 正常启动
  主版本号不匹配 → 提示升级 APK
```

---

## 6. 小组件 (Widget)

### 6.1 已支持的小组件

| 组件 | 数据源 | 刷新 |
|------|--------|------|
| 余额 (balance) | DeepSeek API | 可配置 (15min/30min/1h/手动) |
| 文本 (text) | 用户输入 | 手动 |
| Obsidian 卡片 | Obsidian API | 可配置 |

### 6.2 小组件生命周期

```
用户创建 → WidgetController.create()
  → WidgetInstanceManager 分配 ID
  → WidgetExecutor 启动刷新任务
  → WidgetRenderer 推送到桌面
  → McpWidgetProvider.onUpdate() 更新 UI

用户删除 → WidgetController.delete()
  → 移除刷新任务
  → 从桌面移除
```

---

## 7. 模块清单

```
widgetmcp_src/java/com/nous/widgetmcp/

  核心层:
    WidgetMCPApp.kt          Application 入口
    MainActivity.kt          主界面 (ViewFlipper 三页)
    McpServer.kt             MCP JSON-RPC 服务器 :8766 (McpService 默认端口)
    McpService.kt            前台服务 (保活)
    ServiceLocator.kt        依赖注入

  数据层:
    WidgetController.kt      组件 CRUD
    WidgetInstanceManager.kt 组件实例管理
    WidgetExecutor.kt        组件执行器
    WidgetStateStore.kt      组件状态存储
    WidgetRegistry.kt        组件类型注册
    WidgetConfig/Data/Type   数据模型
    CredentialStore.kt       凭证存储
    DataSource.kt            数据源抽象
    DataSourceManager.kt     数据源管理

  知识图谱:
    ui/GraphView.kt          画布 (自定义 View)
    ui/GraphNode.kt          节点模型
    ui/GraphEdge.kt          连线模型

  Yuanzi 桥接:
    yuanzi/YuanziApi.kt       REST API 调用 (双 baseUrl: Core :8080 + 注册中心 :8081)
    yuanzi/YuanziConfig.kt    连接配置 (host/port + registryPort)
    yuanzi/YuanziSync.kt      数据同步
    yuanzi/YuanziSearch.kt    语义搜索
    yuanzi/YuanziPollReceiver.kt 定时轮询
    yuanzi/GraphTopology.kt   图谱拓扑模型

  浏览器:
    browser/BrowserActivity.kt
    browser/BrowserBridge.kt
    browser/BrowserCommandProcessor.kt

  小组件:
    widget/McpWidgetProvider.kt 桌面小组件 Provider
    widget/WidgetBinding.kt     桌面绑定
```

---

## 8. 权限

```xml
INTERNET               ← localhost HTTP 通信
FOREGROUND_SERVICE     ← 保活 (后台轮询)
POST_NOTIFICATIONS     ← 前台服务通知
WAKE_LOCK              ← 定时唤醒
RECEIVE_BOOT_COMPLETED ← 开机自启
SCHEDULE_EXACT_ALARM   ← 精确定时
```

---

> **APK 是用户唯一触摸到的部分。后端的 18 份设计文档、277 个测试、61 个原子——最终都浓缩在这个 APK 的知识图谱上。**
