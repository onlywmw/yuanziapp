# M8 模板系统

> **定位**: 地基 (SDK) + 模板层 (审美)。SDK 零审美, 模板全审美。
> **合并**: DESIGN_M8_HUMAN_EXPERIENCE + DESIGN_M8_IMPLEMENTATION

---

## 一、分层

```
┌─────────────────────────────────┐
│  模板层                          │
│  Obsidian 星系 / 极简 / 赛博朋克  │  ← 审美在这里
├─────────────────────────────────┤
│  钩子层 (SDK 开放接口)           │
│  onRender / onHover / onFocus    │  ← 地基暴露的钩子
├─────────────────────────────────┤
│  地基 (Graph SDK)                │
│  Store / Renderer / Camera ...   │  ← 纯函数, 零审美
└─────────────────────────────────┘
```

---

## 二、钩子接口

```kotlin
interface GraphTemplate {
    val id: String
    val name: String

    // 渲染
    fun renderBackground(canvas: Canvas, state: GraphState)
    fun renderNode(canvas: Canvas, node: GraphNode, state: RenderState)
    fun renderEdge(canvas: Canvas, edge: GraphEdge, state: RenderState)

    // 交互
    fun onNodeAppear(node: GraphNode, animator: AnimationQueue)
    fun onNodeDisappear(node: GraphNode, animator: AnimationQueue)
    fun onHoverEnter(node: GraphNode, neighbors: Set<GraphNode>, store: GraphStore)
    fun onHoverLeave(store: GraphStore)
    fun onFocusEnter(node: GraphNode, depth: Int, camera: Camera)
    fun onFocusLeave(camera: Camera)
    fun onSearch(matches: Set<String>, store: GraphStore)
    fun onSearchClear(store: GraphStore)
    fun onDragStart(node: GraphNode)
    fun onDragEnd(node: GraphNode, animator: AnimationQueue)
    fun onDataFlow(edge: GraphEdge, progress: Float, particles: ParticleSystem)

    fun getDefaultParams(): TemplateParams
}
```

SDK 调用方式:
```kotlin
// Renderer: 绘制前调模板
template?.renderNode(canvas, node, state) ?: defaultRenderNode(canvas, node)

// Interaction: 事件发生时调模板
template?.onHoverEnter(node, neighbors, store)
```

---

## 三、Obsidian 星系模板

### 节点

```
颜色: 底色按配色方案, 无边框
光晕: setShadowLayer(2dp, 0, 0, 节点色) — alpha 20%
大小: 半径 = 8dp + 连接数 × 2dp
CENTER: 半径 24dp, 纯白, 呼吸光晕 (亮度波动 ±10%, 周期 3s)
```

### 连线

```
基础: 1dp 细线, alpha 15%
悬停: 粗 3dp, alpha 80%
数据流: 红色(动脉) / 蓝色(静脉) 光粒子沿连线移动, 尾部带光尾
```

### 背景

```
纯黑 #0D0D0D
缩放 > 0.8x: 极淡六角网格 #151515
```

### 交互

```
onHover: 目标放大 1.15x + 光晕扩大; 邻居微亮 (alpha +10%); 非邻居微暗 (alpha -20%)
onFocus: 目标弹簧动画移到中心 (400ms); 一级邻居可见, 其余淡出; 面包屑: "全局 > 节点名"
onSearch: 匹配节点 amber 光环; 不匹配 alpha → 20%
onNodeAppear: 从 CENTER 位置 scale 0→1, 贝塞尔曲线飞向目标, 光尾拖影
onNodeDisappear: 爆炸为 8-12 个粒子, 邻居被推开 ±10dp
```

---

## 四、模板注册与切换

```
graph.registerTemplate("obsidian", ObsidianTemplate())
graph.registerTemplate("minimal", MinimalTemplate())
graph.applyTemplate("obsidian")

切换动画:
  不是刷新 — 跨渐变 (crossfade)
  节点形状、颜色、连线风格 300ms 过渡
```

---

## 五、实施

```
Day 1: GraphTemplate 接口 + DefaultTemplate (纯几何)
Day 2: ObsidianTemplate (恒星/引力线/粒子)
Day 3: 模板注册/切换 + 参数存储
```
