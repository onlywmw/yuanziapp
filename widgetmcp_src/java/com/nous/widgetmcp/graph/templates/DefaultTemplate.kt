package com.nous.widgetmcp.graph.templates

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import com.nous.widgetmcp.graph.engine.AnimationQueue
import com.nous.widgetmcp.graph.engine.Camera
import com.nous.widgetmcp.graph.engine.GraphState
import com.nous.widgetmcp.graph.engine.GraphStore
import com.nous.widgetmcp.graph.engine.ParticleSystem
import com.nous.widgetmcp.graph.engine.RenderState
import com.nous.widgetmcp.ui.GraphEdge
import com.nous.widgetmcp.ui.GraphNode

/**
 * M8 · 基座模板（设计文档第一节/第七节 Day 1）。
 *
 * 纯几何，零审美：简单圆点 + 直线 + 无配色方案。
 * 所有渲染方法完整复刻 GraphView 现有默认绘制行为，交互钩子为空实现
 * —— 应用本模板后视觉效果与引擎未设置模板时完全一致。
 */
class DefaultTemplate : GraphTemplate, MutableParamsTemplate {

    override val id: String = "default"
    override val name: String = "基础几何"

    /**
     * 当前生效参数（M8 接线：参数面板经 GraphView.setTemplateParams 写入）。
     * 默认值时渲染与引擎原默认行为完全一致；仅 nodeBaseSize / textOpacity /
     * edgeThickness / mixerPosition 四个字段影响本模板的纯几何渲染。
     */
    override var params: TemplateParams = TemplateParams()

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

    // ---- 渲染（等价于引擎现有默认行为） ----

    override fun renderBackground(canvas: Canvas, state: GraphState) {
        canvas.drawColor(Color.parseColor("#F7F4EE"))
    }

    override fun renderEdge(canvas: Canvas, edge: GraphEdge, state: RenderState) {
        // 连线粗细参数（GRAPH_PARAMETER_PANEL §四，0.5~5dp，默认 2.0 → 倍率 1）
        val thicknessScale = params.edgeThickness / DEFAULT_EDGE_THICKNESS
        // 混音台调制（GRAPH_MIXER_MODEL §四）：作品端连线更细、更半透明
        val mixer = params.mixerPosition.coerceIn(0f, 1f)
        val widthScale = 1f - MIXER_EDGE_WIDTH_CUT * mixer
        val alphaScale = 1f - MIXER_EDGE_ALPHA_CUT * mixer

        linePaint.color = edge.color
        linePaint.alpha = (alphaScale * 255).toInt().coerceIn(0, 255)
        linePaint.strokeWidth = edge.width * thicknessScale * widthScale
        canvas.drawLine(
            edge.sourcePos.x, edge.sourcePos.y,
            edge.targetPos.x, edge.targetPos.y,
            linePaint
        )
        linePaint.alpha = 255
    }

    override fun renderNode(canvas: Canvas, node: GraphNode, state: RenderState) {
        // 节点大小参数（GRAPH_PARAMETER_PANEL §四，0.5~2.0x，默认 1.0 不变）
        val radius = node.radius * params.nodeBaseSize

        nodePaint.color = node.color
        canvas.drawCircle(node.pos.x, node.pos.y, radius, nodePaint)
        canvas.drawCircle(node.pos.x, node.pos.y, radius, strokePaint)

        // 文字透明度参数（GRAPH_PARAMETER_PANEL §四，0~100%，默认 0.7）
        textPaint.color = node.textColor
        textPaint.alpha = (params.textOpacity.coerceIn(0f, 1f) * 255).toInt()
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

    /** 与 GraphView.wrapLabel 逻辑一致：按节点宽度逐字换行。 */
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

    private companion object {
        /** TemplateParams.edgeThickness 的默认值，用于把参数归一化为倍率。 */
        const val DEFAULT_EDGE_THICKNESS = 2.0f

        // 混音台连线调制强度（GRAPH_MIXER_MODEL §四）：mixer=1（纯作品）时
        // 连线宽度 -40%、alpha -50%；mixer=0（纯管道）时不调制
        const val MIXER_EDGE_WIDTH_CUT = 0.4f
        const val MIXER_EDGE_ALPHA_CUT = 0.5f
    }

    // ---- 交互（空实现 / 最简实现） ----

    override fun onNodeAppear(node: GraphNode, animator: AnimationQueue) {}
    override fun onNodeDisappear(node: GraphNode, animator: AnimationQueue) {}
    override fun onHoverEnter(node: GraphNode, neighbors: Set<GraphNode>, store: GraphStore) {}
    override fun onHoverLeave(store: GraphStore) {}
    override fun onFocusEnter(node: GraphNode, depth: Int, camera: Camera) {}
    override fun onFocusLeave(camera: Camera) {}
    override fun onSearch(matches: Set<String>, store: GraphStore) {}
    override fun onSearchClear(store: GraphStore) {}
    override fun onDragStart(node: GraphNode) {}
    override fun onDragEnd(node: GraphNode, animator: AnimationQueue) {}
    override fun onDataFlow(edge: GraphEdge, progress: Float, animator: ParticleSystem) {}

    // ---- 参数 ----

    override fun getDefaultParams(): TemplateParams = TemplateParams()
}
