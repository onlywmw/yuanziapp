# M8 实施方案

> **架构**: Graph SDK 钩子层 → 模板注册 → Obsidian 星系首版
> **原则**: SDK 零审美 · 模板可替换 · 钩子是最小接口

> ⚠️ **实现状态横幅（2026-07-19）**：`🔌 代码已落地待接线 / 部分生效`。接口、TemplateParams、ColorScheme、PRESETS 数值、SharedPreferences 键与本文档逐字对齐（`GraphTemplate.kt`、`ParameterPanel.kt:54-88,339-366`），单件质量高；但**缺最后 5% 接线，"Day 1 验收：模板可替换"在 App 内无法验证**。以代码为准的偏差点：
> 1. **致命集成缺口**：`ObsidianTemplate`（494 行完整实现）全仓库无实例化，`GraphView` 只注册 `DefaultTemplate`（`GraphView.kt:109`）；`ParameterPanel`（617 行）除自身文件外无任何引用，MainActivity 仅 `GraphView(this)`（`MainActivity.kt:78`）；粒子安装入口（`GraphView.kt:168`）悬空。
> 2. 文件布局不符：`graph/engine/` 下**没有** GraphEngine/Renderer/Interaction/Animation.kt，只有 `TemplateHooks.kt`（142 行）+ `ParticleSystem.kt`（375 行）；实际被改造的"引擎"是 `ui/GraphView.kt`（604 行），模板注册/切换/钩子分发都写在它里面（`GraphView.kt:143-222`）。
> 3. 本文档 `GraphTemplate` 接口无 `onLayoutTick`，与 HUMAN_EXPERIENCE §二 的 13 钩子清单不一致（代码跟随后者）。

---

## 一、钩子接口定义

```kotlin
// GraphEngine 暴露的模板接口

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
    fun onDataFlow(edge: GraphEdge, progress: Float, animator: ParticleSystem)

    // 参数
    fun getDefaultParams(): TemplateParams
}

data class TemplateParams(
    val nodeBaseSize: Float = 1.0f,
    val textOpacity: Float = 0.7f,
    val edgeThickness: Float = 2.0f,
    val edgeLength: Float = 180f,
    val centripetal: Float = 0.5f,
    val repulsion: Float = 0.5f,
    val attraction: Float = 0.5f,
    val layoutSpeed: Float = 0.5f,
    val colorScheme: ColorScheme = ColorScheme.TAG,
    val mixerPosition: Float = 0.5f
)
```

## 二、GraphEngine 改动

```
文件: graph/engine/GraphEngine.kt

新增:
  + template: GraphTemplate?           ← 当前模板
  + fun registerTemplate(t: GraphTemplate)
  + fun applyTemplate(id: String)
  + fun getHooks(): TemplateHooks       ← 给模板调用的能力

文件: graph/engine/Renderer.kt

改动:
  绘制节点前 → 调 template?.renderNode()
  绘制连线前 → 调 template?.renderEdge()
  绘制背景   → 调 template?.renderBackground()
  模板返回 null → 用默认几何渲染 (纯函数)

文件: graph/engine/Interaction.kt

改动:
  hover  → template?.onHoverEnter / onHoverLeave
  focus  → template?.onFocusEnter / onFocusLeave
  search → template?.onSearch / onSearchClear
  drag   → template?.onDragStart / onDragEnd

文件: graph/engine/Animation.kt

改动:
  节点新增 → template?.onNodeAppear
  节点删除 → template?.onNodeDisappear
  数据流   → template?.onDataFlow
```

## 三、Obsidian 模板实现

```
文件: graph/templates/ObsidianTemplate.kt

实现 GraphTemplate 接口

配色:
  背景: #0D0D0D
  节点: 按 ColorScheme 着色 + 光晕 (Paint.setShadowLayer)
  连线: 1dp + alpha 15%, hover 时 3dp + alpha 80%
  网格: 缩放 > 0.8x 时六角网格 #151515

RenderState:
  data class RenderState(
      val isHovered: Boolean,
      val isSelected: Boolean,
      val isSearchMatch: Boolean,
      val isNeighbor: Boolean,
      val zoom: Float
  )

节点渲染逻辑:
  renderNode:
    基础圆 → 底色 + 无边框
    光晕 → setShadowLayer(模糊半径, 0, 0, 节点色)
    大小 → 8dp + 连接数 * 2dp
    CENTER → 24dp, 白色, 呼吸光晕
    hover → 放大 1.15x
    select → 光晕 12dp, alpha 60%
    搜索匹配 → amber 光环

邻居调制:
  onHoverEnter:
    targetNode.scale = 1.15
    neighbors.forEach { it.alpha = 1.0 }
    nonNeighbors.forEach { it.alpha = 0.8 }
    relatedEdges.forEach { it.thickness = 3.0; it.alpha = 0.8 }
    unrelatedEdges.forEach { it.alpha = 0.1 }

  onHoverLeave:
    所有恢复默认值, 动画 200ms
```

## 四、参数面板

```
文件: graph/ui/ParameterPanel.kt

UI:
  底部滑出, 半透明 + 高斯模糊背景
  8 个滑块 + 4 个配色按钮 + 5 个预设按钮

滑块映射:
  节点大小      → params.nodeBaseSize      (0.5 ~ 2.0)
  文字透明度    → params.textOpacity       (0.0 ~ 1.0)
  连线粗细      → params.edgeThickness     (0.5 ~ 5.0)
  连线长度      → params.edgeLength        (80 ~ 300)
  向心力        → params.centripetal       (0.0 ~ 1.0)
  排斥力        → params.repulsion         (0.0 ~ 1.0)
  吸引力        → params.attraction        (0.0 ~ 1.0)
  布局速度      → params.layoutSpeed       (0.1 ~ 1.0)

配色按钮:
  路径 / 标签 / 风格 / 属性 → params.colorScheme

混音台:
  管道 ◄══●══► 作品 → params.mixerPosition

预设:
  [🔧调试] [⚡工作] [🎨浏览] [💎发现] [🎛默认]
  点击 → 加载预设参数 → 动画过渡到新参数

存储:
  SharedPreferences
  键: graph_params
```

## 五、混音台预设值

```kotlin
val PRESETS = mapOf(
    "debug" to TemplateParams(
        mixerPosition = 0.0f,
        nodeBaseSize = 1.0f,
        textOpacity = 1.0f,
        edgeThickness = 4.0f,
        edgeLength = 120f,
        centripetal = 0.8f,
        repulsion = 0.3f,
        attraction = 0.8f,
        layoutSpeed = 1.0f,
        colorScheme = ColorScheme.TAG
    ),
    "work" to TemplateParams(
        mixerPosition = 0.3f
    ),
    "browse" to TemplateParams(
        mixerPosition = 0.7f
    ),
    "discover" to TemplateParams(
        mixerPosition = 1.0f,
        nodeBaseSize = 1.4f,
        textOpacity = 1.0f,
        edgeThickness = 1.0f,
        edgeLength = 250f,
        centripetal = 0.2f,
        repulsion = 0.8f,
        attraction = 0.2f,
        layoutSpeed = 0.3f,
        colorScheme = ColorScheme.SOUL
    ),
    "default" to TemplateParams()
)
```

## 六、文件清单

```
graph/
├── engine/
│   ├── GraphEngine.kt          ← + 模板注册/切换
│   ├── Renderer.kt             ← + 调模板钩子
│   ├── Interaction.kt          ← + 调模板钩子
│   ├── Animation.kt            ← + 调模板钩子
│   └── TemplateHooks.kt        ← 新增: 钩子接口定义
├── templates/
│   ├── GraphTemplate.kt        ← 新增: 模板接口
│   ├── ObsidianTemplate.kt     ← 新增: Obsidian 星系
│   └── DefaultTemplate.kt      ← 新增: 基础几何(无审美)
├── ui/
│   └── ParameterPanel.kt       ← 新增: 参数面板
└── ...
```

## 七、实施顺序

```
Day 1: SDK 钩子
  1. GraphTemplate 接口
  2. DefaultTemplate (纯几何, 无审美)
  3. GraphEngine + Renderer + Interaction + Animation 调用钩子
  验收: 现有功能不变, 模板可替换

Day 2: Obsidian 模板 + 参数面板
  4. ObsidianTemplate (恒星/引力线/粒子)
  5. ParameterPanel (8滑块+配色+预设)
  验收: 模板切换流畅, 参数调整实时生效

Day 3: 混音台 + 粒子
  6. 混音台主控 + 预设系统
  7. 粒子效果 (光尾/爆炸)
  8. 存储与恢复
  验收: 完整交互体验
```

## 八、验证

```
· 切换模板: Default → Obsidian → Default, 无崩溃
· 拖拽滑块: 图谱实时变化, 60fps
· 切换预设: 参数动画过渡, 不跳变
· hover 节点: 邻居亮起, 非邻居变暗
· 双击节点: 局部图谱, 面包屑显示
· 搜索: 匹配高亮, 不匹配变暗
· 关闭面板: 参数保存, 重启恢复
```

---

> **3 天, 6 个新文件, SDK 零破坏。地基不变, 审美层叠加。**
