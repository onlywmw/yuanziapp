package com.nous.widgetmcp.graph.templates

import android.content.res.Resources
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PointF
import android.os.SystemClock
import com.nous.widgetmcp.graph.engine.AnimationQueue
import com.nous.widgetmcp.graph.engine.Camera
import com.nous.widgetmcp.graph.engine.DefaultParticleSystem
import com.nous.widgetmcp.graph.engine.GraphState
import com.nous.widgetmcp.graph.engine.GraphStore
import com.nous.widgetmcp.graph.engine.ParticleSystem
import com.nous.widgetmcp.graph.engine.RenderState
import com.nous.widgetmcp.ui.GraphEdge
import com.nous.widgetmcp.ui.GraphNode
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * M8 模板：Obsidian 星系
 *
 * 规格来源：docs/DESIGN_M8_IMPLEMENTATION.md 第三节 + docs/DESIGN_M8_HUMAN_EXPERIENCE.md 第三节。
 *
 * 审美：节点是恒星（底色 + 同色高斯光晕，连接越多越大越亮），连线是引力线
 * （默认 1dp / alpha 15%，激活时 3dp / alpha 80%），背景是深空
 * （#0D0D0D，缩放 > 0.8x 时叠一层极淡的六角星图网格 #151515）。
 *
 * 实现要点（零破坏：不修改现有 GraphNode/GraphEdge，全部为模板内部状态）：
 *  - 邻居调制（alpha/scale/连线粗细）保存在以节点 id / 边 key 索引的覆盖表里，
 *    render 时读取；onHoverLeave 把当前覆盖值快照后以 200ms 时间插值恢复默认。
 *  - 节点大小需要“连接数”：renderEdge 每帧累计各端点连接数，
 *    renderBackground（每帧最先调用）清零，renderNode 读取本帧统计值。
 *  - 连线端点坐标：renderNode 时缓存 node.pos 的 PointF 引用（实时跟随），
 *    renderEdge 直接读取；首帧尚无坐标时跳过该边，第二帧起正常。
 *
 * 集成假设（若引擎侧命名不同，只需改 allNodes/allEdges 两个函数）：
 *  - GraphStore 暴露 `nodes: List<GraphNode>` 与 `edges: List<GraphEdge>`；
 *  - GraphState 暴露 `zoom: Float`；
 *  - Renderer 每帧调用顺序为 renderBackground → renderEdge×n → renderNode×n
 *    （乱序时连接数滞后一帧，视觉上可接受）；
 *  - 引擎保持连续重绘（现有 GraphView 为 16ms 循环），呼吸光晕与 200ms 恢复
 *    动画依赖重绘驱动；若引擎改为按需重绘，hover 离开的恢复会在下次重绘时瞬时完成。
 *  - 光晕使用 Paint.setShadowLayer，需宿主 View 开启硬件加速（引擎侧职责）。
 *
 * 线程约定：所有方法在 UI 线程调用（与现有 GraphView 一致）。
 */
class ObsidianTemplate : GraphTemplate, MutableParamsTemplate, ParticleAwareTemplate {

    override val id: String = "obsidian"
    override val name: String = "Obsidian 星系"

    /**
     * 引擎注入的粒子系统（ParticleAwareTemplate）。
     * onNodeAppear / onNodeDisappear / onDragEnd 钩子只拿得到 AnimationQueue，
     * 爆发粒子经此引用发射；为 null（或 NoOp）时静默跳过，行为与注入前一致。
     */
    override var particleSystem: ParticleSystem? = null

    /**
     * 当前生效参数。接口仅要求 [getDefaultParams]，但参数面板/引擎拿到具体
     * 模板实例后可直接更新此属性，渲染每帧读取，实时生效（配色、节点大小倍率、
     * 连线粗细倍率、文字透明度、混音台连线调制）。
     */
    override var params: TemplateParams = TemplateParams()

    // ------------------------------------------------------------------
    // 渲染
    // ------------------------------------------------------------------

    override fun renderBackground(canvas: Canvas, state: GraphState) {
        // 每帧开始：清零连接数统计，由本帧 renderEdge 重新累计
        connectionCounts.clear()

        // 深空：比 Obsidian 的 #1A1A1A 更深
        canvas.drawColor(COLOR_BACKGROUND)

        // 缩放 > 0.8x：极淡的六角星图坐标网格
        if (state.zoom > GRID_MIN_ZOOM) {
            drawHexGrid(canvas)
        }
    }

    override fun renderNode(canvas: Canvas, node: GraphNode, state: RenderState) {
        // 缓存位置引用，供 renderEdge 取端点坐标
        nodePositions[node.id] = node.pos
        // 缓存节点引用，供 onDataFlow 解析端点坐标与节点色（陶土/鼠尾草暖色粒子）
        nodeRefs[node.id] = node

        val t = restoreProgress()
        val d = density
        val isCenter = node.type == GraphNode.NodeType.CENTER
        val hovered = state.isHovered || node.id == hoveredNodeId
        // 缩放 < 0.3x：节点缩成光点（深空照片里的星星），省略光环与文字
        val deepSpace = state.zoom < DEEP_SPACE_ZOOM

        val baseColor = if (isCenter) COLOR_CENTER else colorForScheme(node)
        val alpha = effectiveNodeAlpha(node.id, t)

        // 大小：8dp + 连接数 × 2dp；CENTER 固定 24dp；hover 放大 1.15x
        val connections = connectionCounts[node.id] ?: 0
        val radiusDp = (if (isCenter) CENTER_RADIUS_DP
        else NODE_BASE_DP + connections * NODE_PER_LINK_DP) * params.nodeBaseSize
        val scale = maxOf(if (hovered) HOVER_SCALE else 1f, effectiveNodeScale(node.id, t))
        val radius = radiusDp * d * scale

        // 光晕：同色 setShadowLayer；CENTER 呼吸（±10%，周期 3s）；select 12dp/60%
        val breath = if (isCenter) breathFactor() else 1f
        val glowDp = when {
            deepSpace -> BASE_GLOW_DP
            state.isSelected -> SELECT_GLOW_DP
            hovered || state.isNeighbor -> HOVER_GLOW_DP
            isCenter -> CENTER_GLOW_DP * breath
            else -> BASE_GLOW_DP
        }
        val glowAlpha = if (state.isSelected) SELECT_GLOW_ALPHA
        else BASE_GLOW_ALPHA * breath

        nodePaint.color = applyAlpha(baseColor, alpha)
        nodePaint.setShadowLayer(glowDp * d, 0f, 0f, applyAlpha(baseColor, glowAlpha * alpha))
        canvas.drawCircle(node.pos.x, node.pos.y, radius, nodePaint)
        nodePaint.clearShadowLayer()

        // 搜索匹配：amber 光环
        if (state.isSearchMatch && !deepSpace) {
            ringPaint.color = applyAlpha(COLOR_AMBER, alpha)
            ringPaint.strokeWidth = SEARCH_RING_DP * d
            canvas.drawCircle(node.pos.x, node.pos.y, radius + SEARCH_RING_GAP_DP * d, ringPaint)
        }

        // 标签：节点下方，透明度受 textOpacity 参数控制
        if (!deepSpace) {
            textPaint.textSize = LABEL_SP * d
            textPaint.color = applyAlpha(COLOR_LABEL, alpha * params.textOpacity)
            canvas.drawText(node.label, node.pos.x, node.pos.y + radius + LABEL_OFFSET_DP * d, textPaint)
        }
    }

    override fun renderEdge(canvas: Canvas, edge: GraphEdge, state: RenderState) {
        // 累计连接数（renderNode 的节点大小依赖此值）
        connectionCounts[edge.sourceId] = (connectionCounts[edge.sourceId] ?: 0) + 1
        connectionCounts[edge.targetId] = (connectionCounts[edge.targetId] ?: 0) + 1

        val p1 = nodePositions[edge.sourceId] ?: return
        val p2 = nodePositions[edge.targetId] ?: return

        // 引力线：默认 1dp / alpha 15%；hover 激活 3dp / alpha 80%（如激光点亮）
        val t = restoreProgress()
        val key = edgeKey(edge)
        val widthDp = if (state.isHovered) EDGE_HOVER_WIDTH_DP else effectiveEdgeWidthDp(key, t)
        val alpha = if (state.isHovered) EDGE_HOVER_ALPHA else effectiveEdgeAlpha(key, t)

        // 混音台调制（GRAPH_MIXER_MODEL §四）：滑块越靠作品端，
        // 连线越细、越半透明（"作品视角：连线细，半透明"）；管道端保持原样
        val mixer = params.mixerPosition.coerceIn(0f, 1f)
        val widthScale = 1f - MIXER_EDGE_WIDTH_CUT * mixer
        val alphaScale = 1f - MIXER_EDGE_ALPHA_CUT * mixer

        edgePaint.color = applyAlpha(edge.color, alpha * alphaScale)
        edgePaint.strokeWidth = widthDp * d * widthScale
        canvas.drawLine(p1.x, p1.y, p2.x, p2.y, edgePaint)
    }

    // ------------------------------------------------------------------
    // 交互钩子：邻居调制（本模板的核心交互）
    // ------------------------------------------------------------------

    override fun onHoverEnter(node: GraphNode, neighbors: Set<GraphNode>, store: GraphStore) {
        cancelRestore()
        hoveredNodeId = node.id

        // 目标节点放大 1.15x
        nodeScaleOv[node.id] = HOVER_SCALE

        // 邻居（含目标）alpha = 1.0，非邻居 alpha = 0.8
        val highlighted = HashSet<String>(neighbors.size + 1)
        highlighted.add(node.id)
        neighbors.forEach { highlighted.add(it.id) }
        allNodes(store).forEach { n ->
            nodeAlphaOv[n.id] = if (n.id in highlighted) NEIGHBOR_ALPHA else NON_NEIGHBOR_ALPHA
        }

        // 相关连线 3dp / alpha 0.8；无关连线 alpha 0.1
        allEdges(store).forEach { e ->
            val key = edgeKey(e)
            if (e.sourceId == node.id || e.targetId == node.id) {
                edgeWidthDpOv[key] = EDGE_HOVER_WIDTH_DP
                edgeAlphaOv[key] = EDGE_HOVER_ALPHA
            } else {
                edgeAlphaOv[key] = EDGE_UNRELATED_ALPHA
            }
        }
    }

    override fun onHoverLeave(store: GraphStore) {
        hoveredNodeId = null
        // 快照当前覆盖值，200ms 动画恢复默认值（依赖引擎连续重绘逐帧插值）
        cancelRestore()
        restoreNodeAlpha.putAll(nodeAlphaOv)
        restoreNodeScale.putAll(nodeScaleOv)
        restoreEdgeAlpha.putAll(edgeAlphaOv)
        restoreEdgeWidth.putAll(edgeWidthDpOv)
        nodeAlphaOv.clear()
        nodeScaleOv.clear()
        edgeAlphaOv.clear()
        edgeWidthDpOv.clear()
        if (restoreNodeAlpha.isNotEmpty() || restoreNodeScale.isNotEmpty()
            || restoreEdgeAlpha.isNotEmpty() || restoreEdgeWidth.isNotEmpty()
        ) {
            restoreStartMs = SystemClock.uptimeMillis()
        }
    }

    override fun onSearch(matches: Set<String>, store: GraphStore) {
        // 匹配节点高亮（amber 光环由 renderNode 依据 state.isSearchMatch 绘制），
        // 不匹配节点变暗至 20%（变暗，不是消失）
        cancelRestore()
        allNodes(store).forEach { n ->
            nodeAlphaOv[n.id] = if (n.id in matches) SEARCH_MATCH_ALPHA else SEARCH_NON_MATCH_ALPHA
        }
    }

    override fun onSearchClear(store: GraphStore) {
        nodeAlphaOv.clear()
    }

    // ------------------------------------------------------------------
    // 交互钩子：粒子版本（M8 数据流 / 爆发粒子）
    // ------------------------------------------------------------------

    override fun onNodeAppear(node: GraphNode, animator: AnimationQueue) {
        // 节点出现：从节点位置迸发一簇较大的放射状粒子（恒星点亮）
        emitNodeBurst(node, BURST_COUNT_APPEAR)
    }

    override fun onNodeDisappear(node: GraphNode, animator: AnimationQueue) {
        // 节点消失：在节点最后位置迸发一簇粒子（恒星熄灭）。
        // 注意：此时节点可能即将从 store 移除，但传入的是移除前快照的旧对象，
        // pos / color 仍然可取（GraphView.setData 在清空前捕获 removedNodes）。
        emitNodeBurst(node, BURST_COUNT_DISAPPEAR)
        // 仅清理内部视觉状态，避免已删除节点的条目泄漏
        nodeRefs.remove(node.id)
        nodePositions.remove(node.id)
        connectionCounts.remove(node.id)
        nodeAlphaOv.remove(node.id)
        nodeScaleOv.remove(node.id)
        restoreNodeAlpha.remove(node.id)
        restoreNodeScale.remove(node.id)
    }

    override fun onFocusEnter(node: GraphNode, depth: Int, camera: Camera) {
        // 安全默认：局部图谱的居中弹簧动画与面包屑由引擎负责
    }

    override fun onFocusLeave(camera: Camera) {
        // 安全默认：相机动画由引擎负责
    }

    override fun onDragStart(node: GraphNode) {
        // 安全默认：拖拽过程不改变节点外观
    }

    override fun onDragEnd(node: GraphNode, animator: AnimationQueue) {
        // 拖拽收尾：轻量迸发（弹簧回弹本身仍由引擎默认动画负责）
        emitNodeBurst(node, BURST_COUNT_DRAG_END)
    }

    override fun onDataFlow(edge: GraphEdge, progress: Float, animator: ParticleSystem) {
        // 数据流：沿边在 progress 处发射一簇彗星式光尾粒子 —— 头部密、
        // 沿 progress 上游补两簇递减密度的尾迹，伪造"血液流过血管"的拖尾感。
        val t = progress.coerceIn(0f, 1f)
        val dps = animator as? DefaultParticleSystem
        if (dps == null) {
            // 接口退化路径（NoOp / 其他实现）：只保证语义正确的单次发射
            animator.emitFlow(edge, t)
            return
        }
        val a = nodeRefs[edge.sourceId]
        val b = nodeRefs[edge.targetId]
        if (a == null || b == null) {
            // 首帧渲染前尚无节点缓存：退化为边色单簇，端点解析交给粒子系统的 nodeResolver
            dps.emitFlow(edge, t, FLOW_HEAD_COUNT)
            return
        }
        // 颜色取两端节点中感知亮度更高的一端（陶土/鼠尾草暖色，深空背景上保证醒目；
        //  DESIGN_GRAPH_REFERENCE：数据流像血液，但颜色是陶土和鼠尾草的温润）
        val color = brighterColor(a.color, b.color)
        dps.emitFlow(a.pos.x, a.pos.y, b.pos.x, b.pos.y, t, color, FLOW_HEAD_COUNT)
        if (t >= FLOW_TRAIL_STEP) {
            dps.emitFlow(a.pos.x, a.pos.y, b.pos.x, b.pos.y, t - FLOW_TRAIL_STEP, color, FLOW_TRAIL_COUNT)
        }
        if (t >= FLOW_TRAIL_STEP * 2) {
            dps.emitFlow(a.pos.x, a.pos.y, b.pos.x, b.pos.y, t - FLOW_TRAIL_STEP * 2, color, FLOW_TRAIL_COUNT / 2)
        }
    }

    /** 爆发粒子：有具体实现时按 count 发射，否则退化为接口默认强度；无粒子系统时静默跳过。 */
    private fun emitNodeBurst(node: GraphNode, count: Int) {
        val ps = particleSystem ?: return
        val dps = ps as? DefaultParticleSystem
        if (dps != null) dps.emitBurst(node, count) else ps.emitBurst(node)
    }

    /** 取两个 ARGB 颜色中感知亮度更高的一端（Rec.601 亮度近似）。 */
    private fun brighterColor(c1: Int, c2: Int): Int {
        fun lum(c: Int): Float {
            val r = (c ushr 16) and 0xFF
            val g = (c ushr 8) and 0xFF
            val b = c and 0xFF
            return 0.299f * r + 0.587f * g + 0.114f * b
        }
        return if (lum(c1) >= lum(c2)) c1 else c2
    }

    // ------------------------------------------------------------------
    // 参数
    // ------------------------------------------------------------------

    override fun getDefaultParams(): TemplateParams = TemplateParams()

    // ------------------------------------------------------------------
    // 内部：视觉状态覆盖表（邻居调制 + 200ms 恢复动画）
    // ------------------------------------------------------------------

    /** 当前 hover 的节点 id；null 表示无 hover 会话。 */
    private var hoveredNodeId: String? = null

    private val nodeAlphaOv = mutableMapOf<String, Float>()
    private val nodeScaleOv = mutableMapOf<String, Float>()
    private val edgeAlphaOv = mutableMapOf<String, Float>()
    private val edgeWidthDpOv = mutableMapOf<String, Float>()

    // hover 离开时的快照，200ms 内从这些值插值回默认
    private var restoreStartMs = -1L
    private val restoreNodeAlpha = mutableMapOf<String, Float>()
    private val restoreNodeScale = mutableMapOf<String, Float>()
    private val restoreEdgeAlpha = mutableMapOf<String, Float>()
    private val restoreEdgeWidth = mutableMapOf<String, Float>()

    /** 恢复动画进度 0..1；结束后清理快照并返回 1。 */
    private fun restoreProgress(): Float {
        val start = restoreStartMs
        if (start < 0L) return 1f
        val t = (SystemClock.uptimeMillis() - start) / RESTORE_MS.toFloat()
        if (t >= 1f) {
            cancelRestore()
            return 1f
        }
        return t.coerceAtLeast(0f)
    }

    private fun cancelRestore() {
        restoreStartMs = -1L
        restoreNodeAlpha.clear()
        restoreNodeScale.clear()
        restoreEdgeAlpha.clear()
        restoreEdgeWidth.clear()
    }

    private fun effectiveNodeAlpha(id: String, t: Float): Float {
        nodeAlphaOv[id]?.let { return it }
        val from = restoreNodeAlpha[id] ?: return 1f
        return from + (1f - from) * t
    }

    private fun effectiveNodeScale(id: String, t: Float): Float {
        nodeScaleOv[id]?.let { return it }
        val from = restoreNodeScale[id] ?: return 1f
        return from + (1f - from) * t
    }

    private fun effectiveEdgeAlpha(key: String, t: Float): Float {
        edgeAlphaOv[key]?.let { return it }
        val from = restoreEdgeAlpha[key] ?: return EDGE_BASE_ALPHA
        return from + (EDGE_BASE_ALPHA - from) * t
    }

    private fun effectiveEdgeWidthDp(key: String, t: Float): Float {
        val defaultDp = EDGE_BASE_DP * (params.edgeThickness / DEFAULT_EDGE_THICKNESS)
        edgeWidthDpOv[key]?.let { return it }
        val from = restoreEdgeWidth[key] ?: return defaultDp
        return from + (defaultDp - from) * t
    }

    private fun edgeKey(edge: GraphEdge): String = edge.sourceId + "->" + edge.targetId

    // ------------------------------------------------------------------
    // 内部：渲染辅助
    // ------------------------------------------------------------------

    /** 连接数统计：renderBackground 清零，renderEdge 累计，renderNode 消费。 */
    private val connectionCounts = mutableMapOf<String, Int>()

    /** 节点位置引用缓存（PointF 为可变对象，引用实时跟随物理布局）。 */
    private val nodePositions = mutableMapOf<String, PointF>()

    /** 节点引用缓存（onDataFlow 取端点坐标与节点色用；onNodeDisappear 时清除）。 */
    private val nodeRefs = mutableMapOf<String, GraphNode>()

    // 集成点：GraphStore 访问器若与设计假设不同，只需调整这两个函数
    private fun allNodes(store: GraphStore): List<GraphNode> = store.nodes
    private fun allEdges(store: GraphStore): List<GraphEdge> = store.edges

    private val density: Float
        get() = Resources.getSystem().displayMetrics.density

    private val nodePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val ringPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val edgePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }
    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = COLOR_GRID
        strokeWidth = 1f
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
    }

    /** 按 ColorScheme 给节点着色（稳定散列，同一节点颜色不随帧变化）。 */
    private fun colorForScheme(node: GraphNode): Int = when (params.colorScheme) {
        ColorScheme.PATH -> PATH_PALETTE[stableIndex(node.id, PATH_PALETTE.size)]
        ColorScheme.TAG -> node.color // 沿用现有语义配色
        ColorScheme.STYLE -> STYLE_PALETTE[stableIndex(node.label, STYLE_PALETTE.size)]
        ColorScheme.ATTRIBUTE -> attributeColor(node.type)
        ColorScheme.SOUL -> SOUL_PALETTE[stableIndex(node.id + node.label, SOUL_PALETTE.size)]
    }

    private fun attributeColor(type: GraphNode.NodeType): Int = when (type) {
        GraphNode.NodeType.CENTER -> COLOR_CENTER
        GraphNode.NodeType.WIDGET -> 0xFF8AB4F8.toInt()
        GraphNode.NodeType.ADD_TEMPLATE -> 0xFF80CBC4.toInt()
        GraphNode.NodeType.YUANZI -> 0xFFCE93D8.toInt()
        GraphNode.NodeType.BROWSER -> 0xFF90CAF9.toInt()
        GraphNode.NodeType.SETTINGS -> 0xFFB0BEC5.toInt()
    }

    private fun stableIndex(key: String, size: Int): Int = Math.floorMod(key.hashCode(), size)

    /** CENTER 呼吸因子：1.0 ± 10%，周期 3s。 */
    private fun breathFactor(): Float {
        val phase = (SystemClock.uptimeMillis() % BREATH_PERIOD_MS) / BREATH_PERIOD_MS.toFloat()
        return 1f + BREATH_AMPLITUDE * sin(2.0 * PI * phase).toFloat()
    }

    private fun applyAlpha(color: Int, alpha: Float): Int {
        val a = (alpha.coerceIn(0f, 1f) * 255).toInt()
        return (color and 0x00FFFFFF) or (a shl 24)
    }

    /** 极淡的六角星图网格（flat-top 六边形平铺整个画布，单个 Path 一次绘制）。 */
    private fun drawHexGrid(canvas: Canvas) {
        val s = HEX_SIZE_DP * density
        val hStep = s * 1.5f
        val vStep = s * SQRT3
        val w = canvas.width.toFloat()
        val h = canvas.height.toFloat()

        hexPath.rewind()
        var col = -1
        var x = -s
        while (x < w + s) {
            val yOffset = if (col % 2 == 0) 0f else vStep / 2f
            var y = -vStep + yOffset
            while (y < h + vStep) {
                addHexagon(x, y, s)
                y += vStep
            }
            x += hStep
            col++
        }
        canvas.drawPath(hexPath, gridPaint)
    }

    private val hexPath = Path()

    private fun addHexagon(cx: Float, cy: Float, s: Float) {
        for (i in 0..6) {
            val angle = PI / 3.0 * i
            val px = cx + s * cos(angle).toFloat()
            val py = cy + s * sin(angle).toFloat()
            if (i == 0) hexPath.moveTo(px, py) else hexPath.lineTo(px, py)
        }
    }

    // ------------------------------------------------------------------
    // 常量
    // ------------------------------------------------------------------

    private companion object {
        // 配色（深空）
        val COLOR_BACKGROUND = 0xFF0D0D0D.toInt()
        val COLOR_GRID = 0xFF151515.toInt()
        val COLOR_CENTER = 0xFFFFFFFF.toInt()
        val COLOR_AMBER = 0xFFFFC107.toInt()
        val COLOR_LABEL = 0xFFE6E6E6.toInt()

        // 节点大小
        const val NODE_BASE_DP = 8f
        const val NODE_PER_LINK_DP = 2f
        const val CENTER_RADIUS_DP = 24f
        const val HOVER_SCALE = 1.15f

        // 光晕
        const val BASE_GLOW_DP = 2f
        const val HOVER_GLOW_DP = 4f
        const val CENTER_GLOW_DP = 6f
        const val SELECT_GLOW_DP = 12f
        const val BASE_GLOW_ALPHA = 0.20f
        const val SELECT_GLOW_ALPHA = 0.60f

        // 搜索
        const val SEARCH_RING_DP = 2f
        const val SEARCH_RING_GAP_DP = 4f
        const val SEARCH_MATCH_ALPHA = 1.0f
        const val SEARCH_NON_MATCH_ALPHA = 0.20f

        // 标签
        const val LABEL_SP = 10f
        const val LABEL_OFFSET_DP = 14f

        // 连线（引力线）
        const val EDGE_BASE_DP = 1f
        const val EDGE_HOVER_WIDTH_DP = 3f
        const val EDGE_BASE_ALPHA = 0.15f
        const val EDGE_HOVER_ALPHA = 0.80f
        const val EDGE_UNRELATED_ALPHA = 0.10f

        // 混音台连线调制强度（GRAPH_MIXER_MODEL §四）：mixer=1（纯作品）时
        // 连线宽度 -40%、alpha -50%；mixer=0（纯管道）时不调制
        const val MIXER_EDGE_WIDTH_CUT = 0.4f
        const val MIXER_EDGE_ALPHA_CUT = 0.5f

        /** TemplateParams.edgeThickness 的默认值，用于把参数归一化为倍率。 */
        const val DEFAULT_EDGE_THICKNESS = 2.0f

        // 邻居调制
        const val NEIGHBOR_ALPHA = 1.0f
        const val NON_NEIGHBOR_ALPHA = 0.8f

        // 背景 / 缩放阈值
        const val GRID_MIN_ZOOM = 0.8f
        const val DEEP_SPACE_ZOOM = 0.3f
        const val HEX_SIZE_DP = 48f
        const val SQRT3 = 1.7320508075688772f

        // 动画
        const val RESTORE_MS = 200L
        const val BREATH_PERIOD_MS = 3000L
        const val BREATH_AMPLITUDE = 0.1f

        // 粒子：爆发强度（出现 > 消失 > 拖拽收尾）
        const val BURST_COUNT_APPEAR = 32
        const val BURST_COUNT_DISAPPEAR = 28
        const val BURST_COUNT_DRAG_END = 14

        // 粒子：数据流彗星簇（头部密度 + 尾迹间距/密度）
        const val FLOW_HEAD_COUNT = 5
        const val FLOW_TRAIL_STEP = 0.08f
        const val FLOW_TRAIL_COUNT = 3

        // ColorScheme 调色板（深空背景上的柔和星色）
        val PATH_PALETTE = listOf(
            0xFF8AB4F8.toInt(), 0xFF80D8FF.toInt(), 0xFFB388FF.toInt(), 0xFF82B1FF.toInt()
        )
        val STYLE_PALETTE = listOf(
            0xFFFFAB91.toInt(), 0xFFFFCC80.toInt(), 0xFFFF8A80.toInt(), 0xFFFFD180.toInt()
        )
        val SOUL_PALETTE = listOf(
            0xFFEA80FC.toInt(), 0xFF84FFFF.toInt(), 0xFF8C9EFF.toInt(), 0xFFB9F6CA.toInt()
        )
    }
}
