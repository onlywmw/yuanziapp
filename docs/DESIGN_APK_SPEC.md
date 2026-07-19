# APK 完整规格

> **定位**: 一份文档涵盖 APK 的架构、视觉、构建
> **合并**: DESIGN_APK_ARCHITECTURE + DESIGN_FRONTEND_UI + APK_BUILD_GUIDE

---

## 一、架构

### 三层

```
App 层:   Activity、路由、生命周期
UI 层:    SearchBar、DetailPanel、MiniMap、Toolbar
Engine 层: GraphEngine SDK (渲染/力导向/相机/交互)
```

### 页面

```
ViewFlipper (三页):
  Page 0 — 知识图谱首页 (GraphView + 状态卡片 + 添加快捷)
  Page 1 — DeepSeek 配置 (API Key/连接测试/预览)
  Page 2 — Yuanzi 设置 (连接地址/同步/开关)
```

### 模块清单

```
核心:     WidgetMCPApp / MainActivity / McpServer / McpService / ServiceLocator
数据:     WidgetController / WidgetInstanceManager / WidgetStateStore / WidgetRegistry / CredentialStore
图谱:     GraphView / GraphNode / GraphEdge
桥接:     YuanziApi / YuanziConfig / YuanziSync / YuanziSearch
浏览器:   BrowserActivity / BrowserBridge
小组件:   McpWidgetProvider / WidgetBinding
```

### 通信

```
APK ←→ Python 后端 (同一设备, localhost):

  REST:   :8081 → api.py → registry.py → agent.db
  MCP:    :8080 → McpServer.kt (widget JSON-RPC)

启动握手:
  1. APK 启动 → GET :8081/health
  2. 可达 → 拉取图谱 → 渲染
  3. 不可达 → "等待 Yuanzi Core" → 每 5s 重试
```

---

## 二、视觉

### 色彩

```
主色 (clay):    #B85C38 / #D4956E / #8B3A1E
功能色 (sage):  #6B8E6B / #A3C4A3 / #4A6B4A
警告 (rust):    #C23B22 / #E8A090 / #8B1A0A
提醒 (amber):   #D4A017 / #F0D080
中性:           #2C2C2C / #8C8C8C / #C0C0C0 / #E0E0E0 / #FAFAFA
```

### 字体

```
标题: 22sp Bold · 正文: 15sp Normal · 辅助: 13sp Bold · 说明: 12sp Normal
```

### 间距

```
页面: 20dp · 卡片内: 16dp · 元素间: 12dp/8dp/4dp · 按钮: 52dp
```

### 节点样式

```
CENTER:       圆形 56dp, clay, 白字, 固定
YUANZI:       圆形 48dp, sage(连)/rust(断)/amber(未配置), 白字
BROWSER:      圆形 44dp, clay_deep, 白字
BASE:          圆角矩形 40dp, 灰底虚线, 不可交互
REGISTERED:    圆角矩形 42dp, 分类色, 白边, 可点击
```

### 连线样式

```
默认:     1dp 细线, hairline, 无动画
直通:     实线
映射:     虚线, 标注字段名
转换:     波浪线, 标注类型
合并:     汇聚 → 宽箭头
分流:     分叉 → 多细箭头
数据流:   红色(输出)/蓝色(输入) 光点沿连线移动, 2px/帧
```

### 页面布局

```
知识图谱首页: 状态卡片(顶) → 图谱(中) → 添加按钮(底)
市场页面:     搜索栏(顶) → Tab(热门/高分/最新) → 卡片列表
工作流画布:   工具栏(顶) → 画布(拖拽连线) → 工具箱(底)
详情浮层:     右侧滑出, 320dp宽, 原子名+作者+功能+安装按钮
```

### 动画

```
节点出现:    scale 0→1 + alpha, 300ms
页面切换:    淡入淡出, 200ms
数据流:      光点沿连线, 2px/帧, 循环
状态切换:    颜色渐变, 500ms
详情滑出:    右侧滑入, 300ms
```

---

## 三、构建

### 依赖准备

```
android.jar         Android SDK → 复制到 widgetmcp_src/
kotlin-stdlib       Maven 下载 → widgetmcp_src/libs/
nanohttpd           Maven 下载 → widgetmcp_src/libs/
```

### 构建命令

```
cd widgetmcp_src
sh build.sh          # 编译 APK
sh build_adb.sh      # 编译 + adb 安装
```

### 签名

```
debug:   自动生成, adb install
release: 正式 keystore, 签名后发布
```

### 6 个坑

```
1. atoms 是 VIEW → 不可直接 INSERT
2. 基础原子不可删 → UI 必须区分
3. 作者必展示 → 详情面板 author 字段
4. 端口 8080/8081 可配置 → 避免冲突
5. Termux 可能被杀 → APK 不能崩溃, 持续重试
6. localhost HTTP → AndroidManifest 必须声明 cleartext
```
