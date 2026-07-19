package com.nous.widgetmcp.graph.engine

import com.nous.widgetmcp.graph.templates.TemplateParams
import com.nous.widgetmcp.ui.GraphEdge
import com.nous.widgetmcp.ui.GraphNode

/**
 * M8 · 模板可用的能力类型（设计文档第一/二节）。
 *
 * 这些类型由引擎（GraphView）提供实现，模板通过它们读取图数据、
 * 驱动相机、排队动画、发射粒子。地基只暴露接口，不内置任何审美。
 */

/**
 * 单帧渲染状态（设计文档第三节）。引擎在调用模板 renderXxx 时按
 * 当前 hover / focus / search 状态填充。
 */
data class RenderState(
    val isHovered: Boolean,
    val isSelected: Boolean,
    val isSearchMatch: Boolean,
    val isNeighbor: Boolean,
    val zoom: Float
)

/**
 * 整图快照（设计文档第一节 renderBackground 的 state 参数）。
 */
data class GraphState(
    val nodeCount: Int,
    val edgeCount: Int,
    val zoom: Float,
    val viewWidth: Float,
    val viewHeight: Float,
    val params: TemplateParams
)

/**
 * 动画队列。模板通过它安排属性动画与延迟动作；所有回调都在主线程。
 */
interface AnimationQueue {
    /** 尽快在主线程执行。 */
    fun post(action: () -> Unit)

    /** 延迟 delayMs 毫秒后在主线程执行。 */
    fun postDelayed(delayMs: Long, action: () -> Unit)

    /**
     * 时长为 durationMs 的 0→1 进度动画，每帧回调 update(fraction)，
     * 结束时回调 onEnd（可为空）。
     */
    fun animateFloat(durationMs: Long, update: (fraction: Float) -> Unit, onEnd: (() -> Unit)? = null)

    /** 取消该队列中的所有待执行动作与进行中的动画。 */
    fun cancelAll()
}

/**
 * 粒子系统接口。此处只定义接口；具体实现由同包
 * graph/engine/ParticleSystem.kt 的 DefaultParticleSystem 提供，
 * 引擎只依赖本接口。
 *
 * 方法集与该实现已落地的 override 面严格对齐（emitFlow / emitBurst /
 * update / render / clear）。实现类另暴露 nodeResolver（节点坐标解析器）
 * 等具体配置项，安装方请在把实现交给引擎前在具体类型上配置好。
 */
interface ParticleSystem {
    /** 沿连线在 progress（0=source，1=target）处发射数据流光尾粒子。 */
    fun emitFlow(edge: GraphEdge, progress: Float)

    /** 从节点位置迸发放射状粒子（节点出现/消失/拖拽收尾用）。 */
    fun emitBurst(node: GraphNode)

    /** 单帧推进，dtMs 为距上一帧的毫秒数（引擎节拍 16ms）。 */
    fun update(dtMs: Long)

    /** 把存活粒子叠加绘制到 canvas（在连线/节点之后调用）。 */
    fun render(canvas: Canvas)

    /** 清空所有存活粒子。 */
    fun clear()
}

/**
 * 空实现粒子系统：在真实实现接入前作为默认占位，保证引擎可独立编译运行。
 */
object NoOpParticleSystem : ParticleSystem {
    override fun emitFlow(edge: GraphEdge, progress: Float) {}
    override fun emitBurst(node: GraphNode) {}
    override fun update(dtMs: Long) {}
    override fun render(canvas: Canvas) {}
    override fun clear() {}
}

/**
 * 相机。模板通过它移动视口（聚焦动画等）。
 *
 * 注意：当前基座引擎无视口变换，本实现只记录状态并触发重绘；
 * 缩放/平移值会如实反映在 RenderState.zoom 中供模板使用。
 */
interface Camera {
    val zoom: Float
    val centerX: Float
    val centerY: Float

    fun centerOn(x: Float, y: Float, animate: Boolean = true)
    fun zoomTo(factor: Float, animate: Boolean = true)
    fun panBy(dx: Float, dy: Float, animate: Boolean = true)
    fun reset(animate: Boolean = true)
}

/**
 * 图数据只读视图。模板通过它查询节点/连线/邻居关系。
 */
interface GraphStore {
    val nodes: List<GraphNode>
    val edges: List<GraphEdge>
    fun findNode(id: String): GraphNode?
    fun neighborsOf(nodeId: String): Set<GraphNode>
    fun edgesOf(nodeId: String): List<GraphEdge>
}

/**
 * 引擎暴露给模板的能力集合（设计文档第二节 getHooks() 的返回类型）。
 */
interface TemplateHooks {
    val store: GraphStore
    val camera: Camera
    val animator: AnimationQueue

    /**
     * 粒子系统。默认是 [NoOpParticleSystem]；真实实现就绪后通过
     * 引擎的安装入口替换，模板代码无需改动。
     */
    var particleSystem: ParticleSystem

    /** 当前生效的模板参数（参数面板写入，模板读取）。 */
    var params: TemplateParams

    /** 请求引擎下一帧重绘。 */
    fun requestRender()
}
