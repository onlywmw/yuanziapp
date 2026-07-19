package com.nous.widgetmcp.graph.templates

import android.graphics.Canvas
import com.nous.widgetmcp.graph.engine.AnimationQueue
import com.nous.widgetmcp.graph.engine.Camera
import com.nous.widgetmcp.graph.engine.GraphState
import com.nous.widgetmcp.graph.engine.GraphStore
import com.nous.widgetmcp.graph.engine.ParticleSystem
import com.nous.widgetmcp.graph.engine.RenderState
import com.nous.widgetmcp.ui.GraphEdge
import com.nous.widgetmcp.ui.GraphNode

/**
 * M8 · Graph SDK 模板接口（设计文档第一节）。
 *
 * 地基（引擎）零审美，模板全审美。引擎在绘制节点/连线/背景时优先调用
 * 已应用模板的 renderXxx；模板未设置（template 为 null，即
 * template?.renderXxx(...) 返回 null）时引擎回退到现有的默认几何渲染
 * —— 零破坏原则。
 *
 * 模板引用的 GraphNode / GraphEdge 是现有的
 * com.nous.widgetmcp.ui.GraphNode / GraphEdge。
 */
interface GraphTemplate {
    val id: String
    val name: String

    // ---- 渲染 ----

    /**
     * 背景绘制。引擎每帧最先调用；模板未设置（template 为 null，
     * 即 template?.renderBackground(...) 返回 null）时引擎使用现有默认背景。
     */
    fun renderBackground(canvas: Canvas, state: GraphState)

    /**
     * 节点绘制。模板未设置时引擎使用现有默认几何（圆点 + 描边 + 文字）绘制。
     */
    fun renderNode(canvas: Canvas, node: GraphNode, state: RenderState)

    /**
     * 连线绘制。模板未设置时引擎使用现有默认直线绘制。
     *
     * 端点坐标由引擎在每帧绘制前写入 edge.sourcePos / edge.targetPos。
     */
    fun renderEdge(canvas: Canvas, edge: GraphEdge, state: RenderState)

    // ---- 交互 ----

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

    // ---- 参数 ----

    fun getDefaultParams(): TemplateParams
}

/**
 * 参数可直接写入的模板（M8 接线用）。
 *
 * 参数面板 / 引擎在参数变更时同步更新 [params]，模板在渲染路径逐帧读取，
 * 实时生效（配色、节点大小倍率、连线粗细、文字透明度、混音台等）。
 * GraphView.setTemplateParams 会把新参数灌入实现了本接口的当前模板。
 */
interface MutableParamsTemplate {
    var params: TemplateParams
}

/**
 * 模板参数（设计文档第一节）。
 */
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

/**
 * 配色方案（设计文档第一节）。
 */
enum class ColorScheme {
    PATH,
    TAG,
    STYLE,
    ATTRIBUTE,
    SOUL
}
