# Yuanzi Graph Engine 架构设计

> **状态**: `📐 design-ready`
> **定位**: 可商用的知识图谱渲染 SDK
> **规模**: ~7000-10000 行, 分 3 层 8 模块
> **平台**: Android Canvas (首版) / WebGL (后续)

---

## 一、三层架构

```
┌─────────────────────────────────────────────┐
│                  App 层                      │
│  入口 Activity, 路由, 生命周期               │
├─────────────────────────────────────────────┤
│                  UI 层 (~2000行)             │
│  SearchBar │ Toolbar │ DetailPanel │ MiniMap │
│  Toast │ Dialog │ ContextMenu │ Navigator   │
├─────────────────────────────────────────────┤
│               Interaction 层 (~2000行)       │
│  LocalGraph │ DoubleTap │ AutoLayout        │
│  SearchAnim │ DataFlowAnim │ UndoRedo        │
├─────────────────────────────────────────────┤
│              Graph Engine 层 (~3000行)        │
│  Renderer │ ForceLayout │ Camera │ Store     │
│  NodeMgr │ EdgeMgr │ Animation │ Interaction │
└─────────────────────────────────────────────┘
```

**调用规则**: 上层可以调下层, 下层不知道上层。Engine 层零 UI 依赖, 纯计算+渲染。

---

## 二、Graph Engine 层 (SDK 核心)

### 2.1 模块拆解

```
graph/
├── engine/
│   ├── GraphEngine.kt        ← 总入口, 持有所有子模块
│   ├── Store.kt              ← 状态管理 (响应式数据)
│   ├── NodeManager.kt        ← 节点生命周期
│   ├── EdgeManager.kt        ← 连线生命周期 + 5 种通道类型
│   ├── ForceLayout.kt        ← 力导向布局算法
│   ├── Renderer.kt           ← Canvas 渲染器
│   ├── Camera.kt             ← 视口管理 (平移/缩放/惯性)
│   ├── Interaction.kt        ← 手势处理 (点击/拖拽/框选)
│   ├── Animation.kt          ← 动画引擎 (补间/粒子/呼吸)
│   └── Virtualization.kt     ← 虚拟化渲染 (LOD/视口裁剪)
```

### 2.2 Store (状态管理)

```
GraphStore:
  nodes: Map<String, GraphNode>       ← 节点注册表
  edges: Map<String, GraphEdge>       ← 连线注册表
  selection: Set<String>              ← 选中节点 ID
  hovered: String | null              ← 悬停节点 ID
  camera: CameraState                 ← 视口位置 + 缩放
  layout: LayoutState                 ← 布局算法状态
  animation: AnimationQueue           ← 动画队列

GraphStore 是单一数据源。
Renderer 只读取 Store, 不修改。
Interaction 和 ForceLayout 写入 Store。
Store 变更 → 自动触发 Renderer 重绘。
```

### 2.3 NodeManager

```
职责:
  · 节点的创建/更新/删除
  · 节点类型判断 (CENTER / BASE / REGISTERED / YUANZI / BROWSER)
  · 节点样式映射 (类型 → 颜色/半径/边框)
  · 节点数据与视图状态分离

API:
  addNode(node: GraphNode): void
  removeNode(id: String): void
  updateNode(id: String, patch: NodePatch): void
  getVisibleNodes(camera: CameraState): List<GraphNode>  ← 视口裁剪
  getNeighbors(id: String, depth: Int): List<GraphNode>  ← 局部图谱
```

### 2.4 EdgeManager

```
职责:
  · 连线的创建/更新/删除
  · 5 种通道类型绘制逻辑 (直通/映射/转换/合并/分流)
  · 数据流动画粒子管理

API:
  addEdge(edge: GraphEdge): void
  removeEdge(id: String): void
  getEdgesForNode(nodeId: String): List<GraphEdge>
  getChannelType(edge: GraphEdge): ChannelType
  updateDataFlow(edgeId: String, progress: Float): void  ← 粒子位置
```

### 2.5 通道运行时渲染

工作流执行时, 通道不只是数据流过——是可见的。Renderer 负责通道的视觉状态。

```
执行前 (静态):
  连线: 虚线, 灰色, 标注通道类型

执行中 (数据流过):
  连线: 实线, 颜色=数据类型, 动画=流速
  通道节点短暂出现 (像一个半透明的菱形):
    显示: "映射: body → text · 12ms"
    然后消失

执行后:
  成功: 连线变为绿色, 显示耗时
  失败: 连线变为红色, 显示错误类型
  降级: 连线变为 amber, 显示 fallback 原因
  跳过: 连线变为灰色虚线

点击通道节点:
  展开详情: 输入采样、输出采样、耗时、重试次数
```

通道渲染状态由 `GraphStore` 中的 `channelStates` 维护, 执行引擎更新状态, Renderer 每帧读取并绘制。

### 2.6 ForceLayout (力导向布局)

```
算法: Barnes-Hut 优化力导向

力模型:
  F_spring(u, v)   = k * (distance - restLength)    ← 连线引力
  F_repulsion(u, v) = k_rep / distance^2            ← 节点斥力
  F_center(u)       = k_center * (center - u.pos)    ← 中心引力
  F_gravity(u)      = k_gravity * mass(u)            ← 全局重力

性能:
  · Barnes-Hut 四叉树 → O(n log n) (vs O(n^2) 暴力)
  · 每帧迭代 1 次, 60fps 下达到稳定
  · 稳定后只微动 ±2dp (呼吸效果)
  · 新增节点: 只计算局部 (该节点 + 邻居)

API:
  start(): void               ← 开始计算
  stop(): void                ← 停止 (稳定后自动停)
  addNode(id: String): void   ← 新节点参与布局
  setStable(): void           ← 标记稳定, 降低迭代频率
  isStable(): Boolean
```

### 2.7 Renderer (Canvas 渲染器)

```
绘制顺序 (每帧):
  1. 清空画布 (#1A1A1A)
  2. 绘制网格 (可选, 缩放 > 0.5x 时)
  3. 绘制连线层:
     a. 数据流动画粒子 (执行中)
     b. 连线本体 (按通道类型)
     c. 连线标签 (缩放 > 1.0x)
  4. 绘制节点层 (按 z-index 排序):
     a. 基础原子 (灰底, 最底层)
     b. 注册原子 (按分类着色)
     c. CENTER + YUANZI + BROWSER
     d. 选中高亮光晕
     e. 搜索高亮光晕
  5. 绘制调试信息 (开发模式)

每帧耗时目标: < 16ms (60fps)
```

### 2.8 Camera (视口)

```
状态:
  offsetX, offsetY: Float    ← 平移偏移
  zoom: Float (0.3 ~ 3.0)    ← 缩放级别
  targetZoom: Float           ← 目标缩放 (动画用)
  velocityX, velocityY: Float ← 惯性速度

操作:
  pan(dx, dy): void           ← 平移
  zoomTo(level, cx, cy): void ← 缩放到指定点
  fitBounds(nodes): void      ← 适配节点到视口
  reset(): void               ← 回到 CENTER 节点
  getVisibleRect(): Rect      ← 视口裁剪矩形

惯性:
  手指抬起 → velocity 衰减 (摩擦系数 0.95)
  velocity < 0.5 → 停止
```

### 2.9 Interaction (手势)

```
手势处理:
  singleTap(x, y):
    → 选中节点 (如果在节点上)
    → 取消选中 (如果在空白处)

  doubleTap(x, y):
    → 在节点上 → 进入局部图谱模式
    → 在空白处 → 全局复位

  longPress(x, y):
    → 在注册原子节点上 → 显示 ContextMenu (详情/删除/添加到工作流)
    → 在基础原子节点上 → 无反应 (不可操作)

  pinch(scale, cx, cy):
    → Camera.zoomTo(scale, cx, cy)

  drag(dx, dy):
    → 在选中节点上 → 拖拽移动节点
    → 在空白处 → Camera.pan(dx, dy)

  boxSelect(startX, startY, endX, endY):
    → 选中框内所有注册原子
```

### 2.10 Animation (动画引擎)

```
动画类型:

  Tween (补间):
    · 节点 scale 0→1 (出现)
    · 节点 alpha 1→0 (消失)
    · 节点移动到新位置
    · 颜色渐变

  Particle (粒子):
    · 数据流小圆点沿连线移动
    · 速度: 2px/帧 (动脉) / 1px/帧 (静脉)

  Pulse (脉冲):
    · 选中节点光晕扩大缩小 (循环)
    · 运行中节点 amber 边框闪烁

  Spring (弹簧):
    · 力导向节点移动的惯性动画
    · dampening: 0.85, stiffness: 0.1

AnimationQueue:
  · 按优先级排序 (交互 > 数据更新 > 装饰)
  · 每帧处理队列中所有动画
  · 完成自动移出队列
```

### 2.11 Virtualization (虚拟化)

```
视口裁剪:
  · 计算 Camera.getVisibleRect()
  · 只渲染视口内 ±20% 的节点
  · 视口外节点: 不绘制, 但仍参与布局

LOD (细节层次):
  缩放 < 0.5x: 节点缩小为光点 (4dp), 不显示文字
  缩放 0.5-1.0x: 正常节点, 12sp 文字
  缩放 1.0-2.0x: 正常节点, 14sp 文字, 连线标签可见
  缩放 > 2.0x: 节点放大, 16sp 文字, 详情摘要可见

  缩放级别切换: 无跳变, 渐变过渡

性能目标:
  100 节点: 60fps (零虚拟化)
  500 节点: 60fps (视口裁剪)
  2000 节点: 30fps (LOD + 视口裁剪 + 四叉树)
```

---

## 三、UI 层

### 3.1 组件树

```
GraphActivity
├── GraphSurface (Canvas, 全屏)
├── SearchBar (顶部, 半透明浮层)
│   ├── 输入框
│   └── 搜索结果下拉
├── DetailPanel (右侧滑出, 320dp 宽)
│   ├── 原子名 + 评分
│   ├── 作者信息
│   ├── 功能列表
│   └── [添加到工作流] [查看版本]
├── MiniMap (右下角, 120x80dp, 缩放 0.1x)
│   └── 视口矩形指示器
├── Toolbar (底部, 半透明)
│   ├── [全局] [局部] [市场] [工作流]
│   └── [＋] 添加节点
├── ContextMenu (长按弹出)
│   ├── 查看详情
│   ├── 添加到工作流
│   └── 删除 (仅注册原子)
└── Toast (底部居中)
```

### 3.2 SearchBar

```
状态:
  idle:      搜索图标 + 占位文字 "搜索原子..."
  focused:   输入框展开, 显示历史搜索
  searching: 输入中, 下拉显示匹配结果 (最多 5 个)
  selected:  选中一个结果, 图谱跳转到该节点 + 高亮

搜索防抖: 300ms
结果排序: 匹配度 > 评分 > 连接数
```

### 3.3 DetailPanel

```
滑出动画: 300ms, 从右侧滑入
宽度: 320dp (手机) / 400dp (平板)
内容:
  头部: 原子名 (18sp bold) + 评分 (⭐ + 数字)
  作者行: 头像占位 + 作者名 + License
  功能列表: 可滚动, 每项显示函数名 + 描述
  底部按钮: [添加到工作流] [查看版本历史]
关闭: 点击面板外区域 或 返回键
```

### 3.4 MiniMap

```
位置: 右下角, 距边缘 16dp
尺寸: 120x80dp
内容:
  · 所有节点的缩略图 (不分类型, 统一小方点)
  · 当前视口矩形 (白色半透明)
  · 拖动视口矩形 → 平移主画布
点击 MiniMap 某位置 → 主画布移动到对应位置
```

---

## 四、Interaction 层

### 4.1 局部图谱

```
进入: 双击注册原子 → 当前节点居中, 其余淡出
显示: 该节点 + 一级邻居 (depth=1)
连线: 只显示与该节点直接相连的线
导航: 顶部面包屑 "全局 > mcp.postgres > 邻居"
退出: 双击空白 或 点击面包屑 "全局"
```

### 4.2 工作流模式

```
进入: 从底部 Toolbar 点击 "工作流"
切换:
  · 节点样式不变
  · 连线变为可拖拽 (输入端 ↔ 输出端)
  · 底部显示 [＋添加节点] [＋添加连线] [▶ 运行] [💾 保存]
  · 拖拽连线时弹出通道类型选择
退出: 点击 Toolbar "全局"
```

### 4.3 Undo/Redo

```
操作栈 (Command Pattern):
  MoveNode(nodeId, from, to)
  DeleteNode(nodeId, snapshot)
  AddEdge(edgeId, edge)
  DeleteEdge(edgeId, snapshot)

栈深度: 50 步
快捷键: 未定 (Android 无标准键盘)
入口: Toolbar [↩] [↪] 按钮 或 摇晃撤销
```

---

## 五、模块 API 契约

### GraphEngine → 外部

```kotlin
interface GraphEngine {
    // 数据
    fun loadGraph(nodes: List<GraphNode>, edges: List<GraphEdge>)
    fun addNode(node: GraphNode)
    fun removeNode(id: String)
    fun addEdge(edge: GraphEdge)

    // 视图
    fun focusNode(id: String, animate: Boolean = true)
    fun highlightNodes(ids: Set<String>)
    fun resetView()

    // 模式
    fun enterLocalGraph(centerId: String)
    fun exitLocalGraph()
    fun enterWorkflowMode()
    fun exitWorkflowMode()

    // 动画
    fun animateDataFlow(edgeId: String)
    fun animateNodeAppear(nodeId: String)
    fun animateNodeDisappear(nodeId: String)

    // 查询
    fun getNode(id: String): GraphNode?
    fun getSelectedNodes(): List<GraphNode>
    fun getVisibleNodes(): List<GraphNode>

    // 事件
    fun setOnNodeClick(handler: (String) -> Unit)
    fun setOnNodeDoubleClick(handler: (String) -> Unit)
    fun setOnNodeLongPress(handler: (String) -> Unit)
    fun setOnCanvasClick(handler: () -> Unit)
}
```

---

## 六、实施计划

### Phase 1: Engine Core (1500 行, 3 天)

```
文件:
  graph/engine/Store.kt           ← 状态管理 (~200行)
  graph/engine/NodeManager.kt     ← 节点管理 (~200行)
  graph/engine/EdgeManager.kt     ← 连线管理 (~250行)
  graph/engine/Camera.kt          ← 视口 (~250行)
  graph/engine/Renderer.kt        ← Canvas 渲染 (~400行)
  graph/engine/GraphEngine.kt     ← 总入口 (~200行)

验收:
  · 100 个节点稳定 60fps
  · 拖拽缩放流畅
  · 节点点击选中
  · 连线正确绘制
```

### Phase 2: Layout & Animation (1000 行, 2 天)

```
文件:
  graph/engine/ForceLayout.kt     ← 力导向 (~350行)
  graph/engine/Animation.kt       ← 动画引擎 (~300行)
  graph/engine/Interaction.kt     ← 手势处理 (~250行)
  graph/engine/Virtualization.kt  ← 虚拟化 (~100行)

验收:
  · 力导向布局收敛
  · 新增/删除节点动画
  · 数据流粒子动画
  · 500 节点保持 30fps
```

### Phase 3: UI Components (2000 行, 3 天)

```
文件:
  graph/ui/SearchBar.kt           ← 搜索 (~300行)
  graph/ui/DetailPanel.kt         ← 详情面板 (~400行)
  graph/ui/MiniMap.kt             ← 小地图 (~250行)
  graph/ui/Toolbar.kt             ← 工具栏 (~200行)
  graph/ui/ContextMenu.kt         ← 右键菜单 (~150行)
  graph/ui/Toast.kt               ← 提示 (~100行)
  graph/ui/Dialog.kt              ← 对话框 (~200行)
  graph/ui/GraphActivity.kt       ← 主 Activity (~400行)

验收:
  · 搜索高亮动画
  · 详情面板滑出
  · MiniMap 联动
  · 完整 UI 流程
```

### Phase 4: Interaction (1000 行, 2 天)

```
文件:
  graph/interaction/LocalGraph.kt    ← 局部图谱 (~300行)
  graph/interaction/WorkflowMode.kt  ← 工作流模式 (~300行)
  graph/interaction/UndoRedo.kt      ← 撤销重做 (~200行)
  graph/interaction/Clipboard.kt     ← 复制粘贴 (~200行)

验收:
  · 局部图谱模式正常
  · 工作流模式拖拽连线
  · Undo/Redo 50 步
```

---

## 七、性能基线

```
场景             节点数   连线数   帧率     内存
────────────────────────────────────────────
空图谱            0        0        60fps    < 30MB
标准知识图谱      80       120      60fps    < 50MB
大型图谱          500      800      30fps    < 100MB
极限压力          2000     3000     15fps    < 200MB

Canvas 渲染策略:
  · 视口外节点不绘制 (Virtualization)
  · 缩放 < 0.5x 时节点缩为光点 (LOD)
  · 静态节点缓存为 Bitmap (无需每帧重绘)
  · 连线合并为 Path (减少 drawLine 调用)
  · 动画粒子使用对象池 (复用 Particle 实例)
```

---

> **这不是一个 Demo 页面。这是一套可商用的图谱引擎 SDK。**
> **先做 Engine, 再做 UI, 最后做交互。每个模块独立可测。**
