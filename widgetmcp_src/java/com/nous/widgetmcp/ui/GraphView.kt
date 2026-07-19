package com.nous.widgetmcp.ui

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PointF
import android.os.Handler
import android.os.Looper
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.View
import com.nous.widgetmcp.graph.engine.AnimationQueue
import com.nous.widgetmcp.graph.engine.Camera
import com.nous.widgetmcp.graph.engine.GraphState
import com.nous.widgetmcp.graph.engine.GraphStore
import com.nous.widgetmcp.graph.engine.NoOpParticleSystem
import com.nous.widgetmcp.graph.engine.ParticleSystem
import com.nous.widgetmcp.graph.engine.RenderState
import com.nous.widgetmcp.graph.engine.TemplateHooks
import com.nous.widgetmcp.graph.templates.DefaultTemplate
import com.nous.widgetmcp.graph.templates.GraphTemplate
import com.nous.widgetmcp.graph.templates.MutableParamsTemplate
import com.nous.widgetmcp.graph.templates.ParticleAwareTemplate
import com.nous.widgetmcp.graph.templates.TemplateParams
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt
import kotlin.random.Random

/**
 * Obsidian 风格知识图谱自定义 View
 *
 * 简单力导向：节点斥力 + 连线弹簧引力 + 中心向心力 + 速度阻尼。
 * 支持拖拽节点、点击触发回调、双击重置布局。
 */
class GraphView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val nodes = mutableListOf<GraphNode>()
    private val edges = mutableListOf<GraphEdge>()
    private val nodeMap = mutableMapOf<String, GraphNode>()

    // ---- M8 模板钩子层（SDK 零审美，模板可替换） ----

    /** 当前应用的模板；为 null 时走现有默认渲染，行为完全不变。 */
    private var template: GraphTemplate? = null
    private val templateRegistry = mutableMapOf<String, GraphTemplate>()

    /** 暴露给模板的能力集合（store / camera / animator / particles / params）。 */
    private val hooks = GraphViewHooks()

    // 交互状态：用于构造 RenderState 并触发对应模板钩子
    private var hoveredNodeId: String? = null
    private var focusedNodeId: String? = null
    private var searchMatches: Set<String>? = null

    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }
    private val nodePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }
    private val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.parseColor("#E9E2D6")
        strokeWidth = 2f
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
        isFakeBoldText = true
    }
    /** 混音台光点档画笔（§3.3：可见度 0.2~0.5 渲染为小光点）。 */
    private val mixerDotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private var draggedNode: GraphNode? = null
    private val touchOffset = PointF()
    private val random = Random(System.currentTimeMillis())

    private var centerX = 0f
    private var centerY = 0f

    private var running = false
    private val animator = object : Runnable {
        override fun run() {
            if (running && draggedNode == null) {
                tickPhysics()
                hooks.particleSystem.update(16L)
                invalidate()
                Handler(Looper.getMainLooper()).postDelayed(this, 16)
            }
        }
    }

    var onNodeClick: ((GraphNode) -> Unit)? = null

    private val gestureDetector = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDoubleTap(e: MotionEvent): Boolean {
            resetLayout()
            return true
        }
    })

    init {
        isClickable = true
        registerTemplate(DefaultTemplate())
        startAnimation()
    }

    fun setData(nodes: List<GraphNode>, edges: List<GraphEdge>) {
        // 计算增删节点，供模板 onNodeAppear / onNodeDisappear 钩子使用
        val removedNodes = this.nodes.filter { old -> nodes.none { it.id == old.id } }
        val addedNodes = nodes.filter { new -> this.nodeMap[new.id] == null }

        this.nodes.clear()
        this.edges.clear()
        this.nodeMap.clear()

        this.nodes.addAll(nodes)
        this.edges.addAll(edges)
        nodes.forEach { nodeMap[it.id] = it }

        // 图谱重建，先清空旧图残留粒子（默认 NoOp 为空操作）；
        // 必须放在下方模板钩子之前，否则钩子里刚发射的爆发粒子会被一并清掉
        hooks.particleSystem.clear()

        template?.let { t ->
            addedNodes.forEach { t.onNodeAppear(it, hooks.animator) }
            removedNodes.forEach { t.onNodeDisappear(it, hooks.animator) }
        }

        resetLayout()
        invalidate()
    }

    /** 按节点 id 查找（搜索定位用，M5 任务 5.4）。 */
    fun findNode(id: String): GraphNode? = nodeMap[id]

    // ---- M8 模板注册 / 切换 / 能力 ----

    /** 注册模板（可重复注册，同 id 覆盖）。 */
    fun registerTemplate(t: GraphTemplate) {
        templateRegistry[t.id] = t
        // 粒子感知模板：注册时补注当前粒子系统（可能先于 installParticleSystem 注册）
        (t as? ParticleAwareTemplate)?.particleSystem = hooks.particleSystem
    }

    /** 应用已注册的模板；id 未注册时忽略。应用后加载该模板的默认参数。 */
    fun applyTemplate(id: String) {
        val t = templateRegistry[id] ?: return
        template = t
        hooks.params = t.getDefaultParams()
        invalidate()
    }

    /** 卸下模板，回退到现有默认渲染。 */
    fun clearTemplate() {
        template = null
        invalidate()
    }

    fun currentTemplate(): GraphTemplate? = template

    /** 模板可调用的能力集合。 */
    fun getHooks(): TemplateHooks = hooks

    /** 安装粒子系统实现（graph/engine/ParticleSystem.kt 就绪后接入）。 */
    fun installParticleSystem(ps: ParticleSystem) {
        hooks.particleSystem = ps
        // 同步注入所有已注册的粒子感知模板
        // （onNodeAppear / onNodeDisappear / onDragEnd 钩子只拿得到 AnimationQueue）
        templateRegistry.values.forEach { (it as? ParticleAwareTemplate)?.particleSystem = ps }
    }

    /** 参数面板写入口：更新当前模板参数并触发重绘。 */
    fun setTemplateParams(params: TemplateParams) {
        hooks.params = params
        // 同步灌入实现 MutableParamsTemplate 的模板（ObsidianTemplate /
        // DefaultTemplate），渲染路径逐帧读取，实时生效
        (template as? MutableParamsTemplate)?.params = params
        invalidate()
    }

    fun getTemplateParams(): TemplateParams = hooks.params

    // ---- M8 交互钩子入口（hover / focus / search / dataflow） ----

    /** 设置悬停节点（null 表示离开悬停），触发 onHoverEnter / onHoverLeave。 */
    fun setHoveredNode(node: GraphNode?) {
        if (node?.id == hoveredNodeId) return
        val hadHover = hoveredNodeId != null
        hoveredNodeId = node?.id
        template?.let { t ->
            if (node != null) {
                t.onHoverEnter(node, hooks.store.neighborsOf(node.id), hooks.store)
            } else if (hadHover) {
                t.onHoverLeave(hooks.store)
            }
        }
        invalidate()
    }

    /** 聚焦节点（局部图谱），触发 onFocusEnter。 */
    fun focusNode(node: GraphNode, depth: Int = 1) {
        focusedNodeId = node.id
        template?.onFocusEnter(node, depth, hooks.camera)
        invalidate()
    }

    /** 退出聚焦，触发 onFocusLeave。 */
    fun clearFocus() {
        if (focusedNodeId == null) return
        focusedNodeId = null
        template?.onFocusLeave(hooks.camera)
        invalidate()
    }

    /** 设置搜索匹配集合（null 表示清除搜索），触发 onSearch / onSearchClear。 */
    fun setSearchMatches(matches: Set<String>?) {
        searchMatches = matches
        template?.let { t ->
            if (matches != null) t.onSearch(matches, hooks.store) else t.onSearchClear(hooks.store)
        }
        invalidate()
    }

    /** 数据流事件入口：沿某条连线推进 progress（0..1），转发给模板。 */
    fun sendDataFlow(edge: GraphEdge, progress: Float) {
        template?.onDataFlow(edge, progress, hooks.particleSystem)
        invalidate()
    }

    /**
     * 便捷重载：按两端节点 id 查找真实存在的边（方向不限），找到才触发数据流；
     * 找不到返回 false 且不发射任何粒子 —— 绝不伪造装饰性数据流。
     * 供 GraphFlowBus 等只握有节点 id 的事件源使用。
     */
    fun sendDataFlowBetween(nodeA: String, nodeB: String, progress: Float = 0.5f): Boolean {
        val edge = edges.firstOrNull {
            (it.sourceId == nodeA && it.targetId == nodeB) ||
                (it.sourceId == nodeB && it.targetId == nodeA)
        } ?: return false
        sendDataFlow(edge, progress)
        return true
    }

    private fun resetLayout() {
        centerX = width / 2f
        centerY = height / 2f
        if (centerX == 0f || centerY == 0f) {
            post { resetLayout() }
            return
        }

        nodes.forEachIndexed { index, node ->
            val angle = 2 * Math.PI * index / max(1, nodes.size)
            val dist = 120f + random.nextFloat() * 120f
            node.pos.x = centerX + (dist * kotlin.math.cos(angle)).toFloat()
            node.pos.y = centerY + (dist * kotlin.math.sin(angle)).toFloat()
            node.vel.set(0f, 0f)
        }
        invalidate()
    }

    private fun startAnimation() {
        running = true
        animator.run()
    }

    private fun tickPhysics() {
        if (nodes.isEmpty()) return
        centerX = width / 2f
        centerY = height / 2f

        // 力学常数全部从 hooks.params 读取（GRAPH_PARAMETER_PANEL §四 / M8 §八验收
        // "拖拽滑块图谱实时变化"）。映射规则保证参数取默认值时手感与原硬编码一致：
        //   repulsion   0..1   → 斥力强度 0..6000f     （默认 0.5 → 3000f，原值）
        //   attraction  0..1   → 边引力系数 0..0.04f    （默认 0.5 → 0.02f，原值）
        //   centripetal 0..1   → 向心系数 0..0.006f     （默认 0.5 → 0.003f，原值）
        //   edgeLength  80..300 → 理想边长（px）        （默认 180 ≈ 原 半径和+80f 的均值 164~192）
        //   layoutSpeed 0.1..1 → 阻尼 = 1-0.3*speed     （默认 0.5 → 0.85，原值；
        //                        速度越快阻尼越小、收敛越快，0.1 时 0.97 缓慢漂浮）
        val p = hooks.params
        val repulsionStrength = p.repulsion * 6000f
        val springK = p.attraction * 0.04f
        val centerK = p.centripetal * 0.006f
        val idealEdgeLength = p.edgeLength
        val damping = (1f - 0.3f * p.layoutSpeed).coerceIn(0.5f, 0.99f)

        // 斥力
        for (i in nodes.indices) {
            for (j in i + 1 until nodes.size) {
                val a = nodes[i]
                val b = nodes[j]
                val dx = a.pos.x - b.pos.x
                val dy = a.pos.y - b.pos.y
                val dist = sqrt(dx * dx + dy * dy).coerceAtLeast(1f)
                val force = repulsionStrength / (dist * dist)
                val fx = (dx / dist) * force
                val fy = (dy / dist) * force
                a.vel.x += fx
                a.vel.y += fy
                b.vel.x -= fx
                b.vel.y -= fy
            }
        }

        // 弹簧引力
        edges.forEach { edge ->
            val a = nodeMap[edge.sourceId] ?: return@forEach
            val b = nodeMap[edge.targetId] ?: return@forEach
            val dx = b.pos.x - a.pos.x
            val dy = b.pos.y - a.pos.y
            val dist = sqrt(dx * dx + dy * dy).coerceAtLeast(1f)
            val targetLen = idealEdgeLength
            val force = (dist - targetLen) * springK
            val fx = (dx / dist) * force
            val fy = (dy / dist) * force
            a.vel.x += fx
            a.vel.y += fy
            b.vel.x -= fx
            b.vel.y -= fy
        }

        // 中心向心力 + 边界限制 + 阻尼
        nodes.forEach { node ->
            val dx = centerX - node.pos.x
            val dy = centerY - node.pos.y
            node.vel.x += dx * centerK
            node.vel.y += dy * centerK

            node.vel.x *= damping
            node.vel.y *= damping

            node.pos.x += node.vel.x
            node.pos.y += node.vel.y

            // 限制在屏幕内
            val padding = node.radius + 16f
            node.pos.x = min(max(node.pos.x, padding), width - padding)
            node.pos.y = min(max(node.pos.y, padding), height - padding)
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val t = template

        // 背景：模板优先；未设置模板（t 为 null）时走现有默认背景
        if (t != null) {
            t.renderBackground(
                canvas,
                GraphState(
                    nodeCount = nodes.size,
                    edgeCount = edges.size,
                    zoom = hooks.camera.zoom,
                    viewWidth = width.toFloat(),
                    viewHeight = height.toFloat(),
                    params = hooks.params
                )
            )
        } else {
            canvas.drawColor(Color.parseColor("#F7F4EE"))
        }

        // ---- 混音台消费者（GRAPH_MIXER_MODEL §三）----
        // 可见度 = 管道权重×(1-滑块) + 作品权重×滑块（§3.2），每帧预计算一次
        val mixer = hooks.params.mixerPosition.coerceIn(0f, 1f)
        val visibility = HashMap<String, Float>(nodes.size * 2)
        nodes.forEach { visibility[it.id] = mixerVisibility(it, mixer) }

        // 画线
        // §四：作品视角连线细、半透明；任一端点落入"不渲染"档（<0.2）的连线
        // 一并隐藏（"作品视角：只保留直接依赖线，隐藏通道细节"的最贴近实现）
        val edgeAlphaScale = 1f - MIXER_EDGE_ALPHA_CUT * mixer
        val edgeWidthScale = 1f - MIXER_EDGE_WIDTH_CUT * mixer
        edges.forEach { edge ->
            val a = nodeMap[edge.sourceId] ?: return@forEach
            val b = nodeMap[edge.targetId] ?: return@forEach
            if ((visibility[edge.sourceId] ?: 1f) < MIXER_HIDE_THRESHOLD ||
                (visibility[edge.targetId] ?: 1f) < MIXER_HIDE_THRESHOLD
            ) return@forEach
            edge.sourcePos.set(a.pos.x, a.pos.y)
            edge.targetPos.set(b.pos.x, b.pos.y)
            if (t != null) {
                t.renderEdge(canvas, edge, edgeRenderState(edge))
            } else {
                // edgeThickness 参数（PANEL §四 0.5~5dp，默认 2.0 → 倍率 1）
                linePaint.color = edge.color
                linePaint.alpha = (edgeAlphaScale * 255).toInt().coerceIn(0, 255)
                linePaint.strokeWidth =
                    edge.width * (hooks.params.edgeThickness / DEFAULT_EDGE_THICKNESS) * edgeWidthScale
                canvas.drawLine(a.pos.x, a.pos.y, b.pos.x, b.pos.y, linePaint)
                linePaint.alpha = 255
            }
        }

        // 画节点：可见度三档渲染（§3.3 阈值 0.2 / 0.5 / 0.8）
        nodes.forEach { node ->
            val v = visibility[node.id] ?: 1f
            when {
                v < MIXER_HIDE_THRESHOLD -> Unit // 0.0~0.2：不渲染
                v < MIXER_DOT_THRESHOLD -> drawMixerDot(canvas, node, v) // 0.2~0.5：小光点，无标签
                v < MIXER_FULL_THRESHOLD -> {
                    // 0.5~0.8：缩略渲染（保留标签，整体 0.75x）
                    canvas.save()
                    canvas.scale(MIXER_THUMB_SCALE, MIXER_THUMB_SCALE, node.pos.x, node.pos.y)
                    if (t != null) t.renderNode(canvas, node, nodeRenderState(node))
                    else drawNodeDefault(canvas, node)
                    canvas.restore()
                }
                else -> {
                    // 0.8~1.0：完整渲染
                    if (t != null) t.renderNode(canvas, node, nodeRenderState(node))
                    else drawNodeDefault(canvas, node)
                }
            }
        }

        // 粒子叠加层（默认 NoOp 粒子系统为空操作，不影响现有渲染）
        hooks.particleSystem.render(canvas)
    }

    // ---- 混音台：权重 / 可见度（GRAPH_MIXER_MODEL §3.1/§3.2/§六）----

    /**
     * 节点的（管道权重， 作品权重）。
     *
     * 取舍说明：文档 §六 compute_weights 依赖 atom 的 system 前缀 / mcp 前缀、
     * soul 叙事、评分数等字段，现有 GraphNode 没有这些属性，这里按 NodeType
     * 做最贴近的映射（数值取自 §3.1 表格）：
     *  - YUANZI / BROWSER / SETTINGS → 系统设施（system.* 档）→ (1.0, 0.0) 纯管道
     *  - CENTER（组件 MCP 核心）    → 基础设施（mcp.* 档）    → (0.7, 0.3) 偏管道
     *  - WIDGET（用户安装的作品实例）→ 终端原子（有 soul） → (0.2, 0.9) 偏作品
     *  - ADD_TEMPLATE（可产出作品的模板，本身无叙事）→ 半成品 → (0.4, 0.6)
     * 若后续 GraphNode 增加来源/权重字段，仅需替换本函数。
     */
    private fun pipelineWorkWeights(node: GraphNode): Pair<Float, Float> = when (node.type) {
        GraphNode.NodeType.YUANZI,
        GraphNode.NodeType.BROWSER,
        GraphNode.NodeType.SETTINGS -> 1.0f to 0.0f
        GraphNode.NodeType.CENTER -> 0.7f to 0.3f
        GraphNode.NodeType.WIDGET -> 0.2f to 0.9f
        GraphNode.NodeType.ADD_TEMPLATE -> 0.4f to 0.6f
    }

    /** §3.2：节点可见度 = 管道权重×(1-滑块) + 作品权重×滑块。 */
    private fun mixerVisibility(node: GraphNode, mixer: Float): Float {
        val (pipelineWeight, workWeight) = pipelineWorkWeights(node)
        return pipelineWeight * (1f - mixer) + workWeight * mixer
    }

    /** §3.3 光点档：小圆点、无标签，亮度随可见度在 0.2~0.5 区间内线性变化。 */
    private fun drawMixerDot(canvas: Canvas, node: GraphNode, v: Float) {
        val band = ((v - MIXER_HIDE_THRESHOLD) / (MIXER_DOT_THRESHOLD - MIXER_HIDE_THRESHOLD))
            .coerceIn(0f, 1f)
        mixerDotPaint.color = node.color
        mixerDotPaint.alpha = (band * 255).toInt().coerceIn(30, 255)
        canvas.drawCircle(
            node.pos.x, node.pos.y,
            (node.radius * MIXER_DOT_SCALE).coerceAtLeast(4f),
            mixerDotPaint
        )
    }

    /** 现有默认节点绘制（模板未处理时的回退路径）。 */
    private fun drawNodeDefault(canvas: Canvas, node: GraphNode) {
        // nodeBaseSize 参数（PANEL §四 0.5~2.0x，默认 1.0 与 M8 前一致）
        val radius = node.radius * hooks.params.nodeBaseSize

        nodePaint.color = node.color
        canvas.drawCircle(node.pos.x, node.pos.y, radius, nodePaint)
        canvas.drawCircle(node.pos.x, node.pos.y, radius, strokePaint)

        // textOpacity 参数（PANEL §四 0~100%，默认 0.7）
        textPaint.color = node.textColor
        textPaint.alpha = (hooks.params.textOpacity.coerceIn(0f, 1f) * 255).toInt()
        textPaint.textSize = radius * 0.30f
        val lines = wrapLabel(node.label, radius * 2.2f)
        val lineHeight = textPaint.fontMetrics.descent - textPaint.fontMetrics.ascent
        val totalHeight = lines.size * lineHeight
        var y = node.pos.y - totalHeight / 2f - textPaint.fontMetrics.ascent
        lines.forEach { line ->
            canvas.drawText(line, node.pos.x, y, textPaint)
            y += lineHeight
        }
        textPaint.alpha = 255
    }

    // ---- M8 RenderState 构造 ----

    private fun nodeRenderState(node: GraphNode): RenderState {
        val hovered = hoveredNodeId
        return RenderState(
            isHovered = node.id == hovered,
            isSelected = node.id == focusedNodeId,
            isSearchMatch = searchMatches?.contains(node.id) == true,
            isNeighbor = hovered != null && hovered != node.id &&
                areNeighbors(hovered, node.id),
            zoom = hooks.camera.zoom
        )
    }

    private fun edgeRenderState(edge: GraphEdge): RenderState {
        val hovered = hoveredNodeId
        val matches = searchMatches
        return RenderState(
            isHovered = hovered != null &&
                (edge.sourceId == hovered || edge.targetId == hovered),
            isSelected = focusedNodeId != null &&
                (edge.sourceId == focusedNodeId || edge.targetId == focusedNodeId),
            isSearchMatch = matches != null &&
                matches.contains(edge.sourceId) && matches.contains(edge.targetId),
            isNeighbor = false,
            zoom = hooks.camera.zoom
        )
    }

    private fun areNeighbors(a: String, b: String): Boolean {
        return edges.any {
            (it.sourceId == a && it.targetId == b) ||
                (it.sourceId == b && it.targetId == a)
        }
    }

    private fun wrapLabel(label: String, maxWidth: Float): List<String> {
        if (textPaint.measureText(label) <= maxWidth) return listOf(label)
        val result = mutableListOf<String>()
        var current = ""
        for (char in label) {
            val test = current + char
            if (textPaint.measureText(test) > maxWidth && current.isNotEmpty()) {
                result.add(current)
                current = char.toString()
            } else {
                current = test
            }
        }
        if (current.isNotEmpty()) result.add(current)
        return if (result.isEmpty()) listOf(label) else result
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        gestureDetector.onTouchEvent(event)
        val x = event.x
        val y = event.y

        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val node = findNodeAt(x, y)
                if (node != null) {
                    draggedNode = node
                    touchOffset.set(x - node.pos.x, y - node.pos.y)
                    node.vel.set(0f, 0f)
                    template?.onDragStart(node)
                    return true
                }
            }
            MotionEvent.ACTION_MOVE -> {
                draggedNode?.let {
                    it.pos.x = x - touchOffset.x
                    it.pos.y = y - touchOffset.y
                    it.vel.set(0f, 0f)
                    invalidate()
                    return true
                }
            }
            MotionEvent.ACTION_UP -> {
                draggedNode?.let {
                    val node = it
                    draggedNode = null
                    template?.onDragEnd(node, hooks.animator)
                    // 如果几乎没有位移，视为点击
                    if (kotlin.math.abs(node.vel.x) < 1f && kotlin.math.abs(node.vel.y) < 1f) {
                        onNodeClick?.invoke(node)
                    }
                    return true
                }
            }
        }
        return super.onTouchEvent(event)
    }

    private fun findNodeAt(x: Float, y: Float): GraphNode? {
        return nodes.find {
            val dx = it.pos.x - x
            val dy = it.pos.y - y
            sqrt(dx * dx + dy * dy) <= it.radius
        }
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        running = false
        hooks.animator.cancelAll()
    }

    companion object {
        // ---- 混音台渲染阈值（GRAPH_MIXER_MODEL §3.3，原档 0.2 / 0.5 / 0.8）----
        /** 可见度 < 0.2：不渲染节点。 */
        private const val MIXER_HIDE_THRESHOLD = 0.2f
        /** 可见度 0.2~0.5：渲染为小光点，无标签。 */
        private const val MIXER_DOT_THRESHOLD = 0.5f
        /** 可见度 0.5~0.8：缩略渲染；≥ 0.8：完整渲染。 */
        private const val MIXER_FULL_THRESHOLD = 0.8f
        /** 缩略档整体缩放系数（"缩略节点"的最贴近实现，标签保留）。 */
        private const val MIXER_THUMB_SCALE = 0.75f
        /** 光点档点半径 = 节点半径 × 0.25。 */
        private const val MIXER_DOT_SCALE = 0.25f

        // ---- 混音台连线调制强度（GRAPH_MIXER_MODEL §四）----
        /** mixer=1（纯作品）时连线宽度 -40%。 */
        private const val MIXER_EDGE_WIDTH_CUT = 0.4f
        /** mixer=1（纯作品）时连线 alpha -50%。 */
        private const val MIXER_EDGE_ALPHA_CUT = 0.5f

        /** TemplateParams.edgeThickness 的默认值，用于把参数归一化为倍率。 */
        private const val DEFAULT_EDGE_THICKNESS = 2.0f
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        if (nodes.isNotEmpty() && (oldw == 0 || oldh == 0)) {
            resetLayout()
        }
    }

    // ---- M8 钩子能力实现（引擎侧，模板只依赖接口） ----

    private inner class GraphViewHooks : TemplateHooks {
        override val store: GraphStore = ViewGraphStore()
        override val camera: Camera = ViewCamera()
        override val animator: AnimationQueue = ViewAnimationQueue()
        override var particleSystem: ParticleSystem = NoOpParticleSystem
        override var params: TemplateParams = TemplateParams()

        override fun requestRender() {
            invalidate()
        }
    }

    /** 图数据只读视图。 */
    private inner class ViewGraphStore : GraphStore {
        override val nodes: List<GraphNode>
            get() = this@GraphView.nodes.toList()
        override val edges: List<GraphEdge>
            get() = this@GraphView.edges.toList()

        override fun findNode(id: String): GraphNode? = nodeMap[id]

        override fun neighborsOf(nodeId: String): Set<GraphNode> {
            val result = mutableSetOf<GraphNode>()
            edges.forEach { e ->
                when (nodeId) {
                    e.sourceId -> nodeMap[e.targetId]?.let(result::add)
                    e.targetId -> nodeMap[e.sourceId]?.let(result::add)
                }
            }
            return result
        }

        override fun edgesOf(nodeId: String): List<GraphEdge> =
            edges.filter { it.sourceId == nodeId || it.targetId == nodeId }
    }

    /**
     * 相机：当前引擎无视口变换，仅记录状态并触发重绘；
     * zoom 会如实反映到 RenderState.zoom 供模板使用。
     */
    private inner class ViewCamera : Camera {
        override var zoom: Float = 1f
            private set
        override var centerX: Float = 0f
            private set
        override var centerY: Float = 0f
            private set

        override fun centerOn(x: Float, y: Float, animate: Boolean) {
            centerX = x
            centerY = y
            invalidate()
        }

        override fun zoomTo(factor: Float, animate: Boolean) {
            zoom = factor.coerceIn(0.1f, 8f)
            invalidate()
        }

        override fun panBy(dx: Float, dy: Float, animate: Boolean) {
            centerX += dx
            centerY += dy
            invalidate()
        }

        override fun reset(animate: Boolean) {
            zoom = 1f
            centerX = width / 2f
            centerY = height / 2f
            invalidate()
        }
    }

    /** 主线程动画队列（Handler + ValueAnimator）。 */
    private inner class ViewAnimationQueue : AnimationQueue {
        private val handler = Handler(Looper.getMainLooper())
        private val runningAnimators = mutableListOf<ValueAnimator>()

        override fun post(action: () -> Unit) {
            handler.post(action)
        }

        override fun postDelayed(delayMs: Long, action: () -> Unit) {
            handler.postDelayed(action, delayMs)
        }

        override fun animateFloat(
            durationMs: Long,
            update: (fraction: Float) -> Unit,
            onEnd: (() -> Unit)?
        ) {
            val anim = ValueAnimator.ofFloat(0f, 1f).setDuration(durationMs)
            anim.addUpdateListener { update(it.animatedValue as Float) }
            if (onEnd != null) {
                anim.addListener(object : AnimatorListenerAdapter() {
                    override fun onAnimationEnd(animation: Animator) {
                        onEnd()
                    }
                })
            }
            runningAnimators.add(anim)
            anim.start()
        }

        override fun cancelAll() {
            runningAnimators.forEach { it.cancel() }
            runningAnimators.clear()
            // 只移除经本 Handler 投递的回调，不影响物理循环
            handler.removeCallbacksAndMessages(null)
        }
    }
}
