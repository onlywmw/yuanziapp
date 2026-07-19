package com.nous.widgetmcp.graph.engine

import android.graphics.Canvas
import android.graphics.Paint
import com.nous.widgetmcp.ui.GraphEdge
import com.nous.widgetmcp.ui.GraphNode
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.random.Random

/**
 * D3 · ParticleSystem 粒子系统（M8 设计文档第一节 `onDataFlow(edge, progress, animator)` 所需能力）。
 *
 * 职责：
 *  1. 光尾粒子 —— 沿 [GraphEdge] 两端节点按 progress 插值定位，粒子继续沿边方向流动，拖尾渐隐；
 *  2. 爆炸粒子 —— 节点出现 / 删除 / 拖拽结束时从节点位置迸发，放射状扩散 + 阻尼衰减；
 *  3. 固定容量粒子池，环形复用，update/render 全程零分配，目标 60fps；
 *  4. 容量上限与降级 —— 池满时环形覆盖（等价丢弃最旧），高占用时自动降低发射密度。
 *
 * ── 接口对齐说明 ─────────────────────────────────────────────────────────────
 * 本类实现同包 TemplateHooks.kt 中的 `ParticleSystem` 接口（由并行任务提供）。
 * 与设计文档第一节用法自洽的假定签名如下；若落地接口略有出入，仅需调整本类
 * override 签名，核心实现不变：
 *
 * ```kotlin
 * interface ParticleSystem {
 *     var nodeResolver: ((String) -> GraphNode?)?
 *     fun emitFlow(edge: GraphEdge, progress: Float)
 *     fun emitBurst(node: GraphNode)
 *     fun update(dtMs: Long)
 *     fun render(canvas: Canvas)
 *     fun clear()
 * }
 * ```
 * ────────────────────────────────────────────────────────────────────────────
 *
 * 引擎侧使用示例（GraphView / Animation 钩子接线）：
 *
 * ```kotlin
 * // GraphView 初始化一次：
 * private val particles = DefaultParticleSystem(maxParticles = 512).apply {
 *     nodeResolver = { id -> findNode(id) }   // GraphView.findNode 已存在（M5）
 * }
 *
 * // ① 数据流钩子（模板 onDataFlow 内，或引擎 Animation.kt 转发处）：
 * override fun onDataFlow(edge: GraphEdge, progress: Float, animator: ParticleSystem) {
 *     animator.emitFlow(edge, progress)       // progress ∈ [0,1]，边上发射流动光尾粒子
 * }
 *
 * // ② 节点出现 / 删除 / 拖拽结束：
 * override fun onNodeAppear(node: GraphNode, animator: AnimationQueue) {
 *     particles.emitBurst(node)               // 放射状迸发
 * }
 * override fun onDragEnd(node: GraphNode, animator: AnimationQueue) {
 *     particles.emitBurst(node, count = 16)   // 轻量收尾迸发
 * }
 *
 * // ③ 帧驱动：GraphView 已有的 animator Runnable（16ms 节拍）里：
 * particles.update(16L)
 * invalidate()
 *
 * // ④ onDraw 中，连线与节点绘制之后叠加：
 * particles.render(canvas)
 *
 * // ⑤ setData / 视图 detached 时：
 * particles.clear()
 * ```
 *
 * 仅依赖 android.graphics.Canvas/Paint，无第三方库；所有调用约定在 UI 线程。
 */
class DefaultParticleSystem(
    /** 粒子池硬上限；超出后环形覆盖最旧粒子。 */
    private val maxParticles: Int = DEFAULT_MAX_PARTICLES
) : ParticleSystem {

    // ------------------------------------------------------------------ 池

    /** 粒子类别。 */
    private enum class Kind { FLOW, BURST }

    /**
     * 池化粒子。全部为可复写字段，避免任何堆分配。
     * 速度单位 px/ms，时间单位 ms。
     */
    private class Particle {
        var active = false
        var kind = Kind.FLOW
        var x = 0f
        var y = 0f
        var vx = 0f
        var vy = 0f
        var ageMs = 0f
        var lifeMs = 1f
        var size = 0f          // 头部半径（px）
        var color = 0          // 基础色（含 alpha）
        var drag = 1f          // 每 ms 速度保留系数

        fun reset() {
            active = false
            x = 0f; y = 0f; vx = 0f; vy = 0f
            ageMs = 0f; lifeMs = 1f; size = 0f; color = 0; drag = 1f
        }
    }

    private val pool = Array(maxParticles) { Particle() }

    /** 环形写入游标：池满后覆盖最旧写入位置（近似丢弃最旧）。 */
    private var cursor = 0

    /** 当前存活粒子数。 */
    var activeCount = 0
        private set

    /**
     * 由引擎注入的节点定位器（GraphEdge 只存 sourceId/targetId，
     * 发射光尾粒子前需要解析两端节点坐标）。典型实现：`{ id -> findNode(id) }`。
     */
    var nodeResolver: ((String) -> GraphNode?)? = null

    /** 全局发射密度倍率（1.0 = 正常；引擎可在低端机上整体调低）。 */
    var density = 1.0f

    // ------------------------------------------------------------------ 绘制工具（复用，零分配）

    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }

    private val random = Random(System.currentTimeMillis())

    // ------------------------------------------------------------------ 发射 API

    /**
     * 光尾：在 [edge] 两端节点间按 [progress]（0=source, 1=target）插值定位，
     * 发射 [count] 个沿边方向流动的粒子；节点缺失或 resolver 未注入时静默跳过。
     */
    override fun emitFlow(edge: GraphEdge, progress: Float) {
        emitFlow(edge, progress, count = FLOW_PARTICLES_PER_TICK)
    }

    /** 同 [emitFlow]，可指定粒子数（供模板自定义强度）。 */
    fun emitFlow(edge: GraphEdge, progress: Float, count: Int) {
        val resolver = nodeResolver ?: return
        val a = resolver(edge.sourceId) ?: return
        val b = resolver(edge.targetId) ?: return
        val t = progress.coerceIn(0f, 1f)
        emitFlow(
            x0 = a.pos.x, y0 = a.pos.y,
            x1 = b.pos.x, y1 = b.pos.y,
            progress = t,
            color = edge.color,
            count = count
        )
    }

    /** 坐标直给版光尾发射（不依赖 nodeResolver，测试/自定义可用）。 */
    fun emitFlow(x0: Float, y0: Float, x1: Float, y1: Float, progress: Float, color: Int, count: Int) {
        val hx = x0 + (x1 - x0) * progress
        val hy = y0 + (y1 - y0) * progress
        val dx = x1 - x0
        val dy = y1 - y0
        val len = sqrt(dx * dx + dy * dy)
        if (len < 1f) return
        val ux = dx / len
        val uy = dy / len
        val n = effectiveCount(count)
        repeat(n) {
            val speed = FLOW_SPEED_MIN + random.nextFloat() * (FLOW_SPEED_MAX - FLOW_SPEED_MIN)
            val jitter = (random.nextFloat() - 0.5f) * FLOW_JITTER
            spawn(
                kind = Kind.FLOW,
                x = hx + (random.nextFloat() - 0.5f) * FLOW_SPAWN_SPREAD,
                y = hy + (random.nextFloat() - 0.5f) * FLOW_SPAWN_SPREAD,
                vx = ux * speed - uy * jitter,   // 垂直分量做轻微抖动
                vy = uy * speed + ux * jitter,
                lifeMs = FLOW_LIFE_MIN + random.nextFloat() * (FLOW_LIFE_MAX - FLOW_LIFE_MIN),
                size = FLOW_SIZE_MIN + random.nextFloat() * (FLOW_SIZE_MAX - FLOW_SIZE_MIN),
                color = color,
                drag = FLOW_DRAG
            )
        }
    }

    /** 爆炸：从 [node] 位置迸发 [count] 个放射状粒子，颜色取节点色。 */
    override fun emitBurst(node: GraphNode) {
        emitBurst(node.pos.x, node.pos.y, node.color, BURST_PARTICLES_DEFAULT)
    }

    /** 同 [emitBurst]，可指定粒子数（如拖拽结束时用小数量）。 */
    fun emitBurst(node: GraphNode, count: Int) {
        emitBurst(node.pos.x, node.pos.y, node.color, count)
    }

    /** 坐标/颜色直给版爆炸发射。 */
    fun emitBurst(x: Float, y: Float, color: Int, count: Int) {
        val n = effectiveCount(count)
        repeat(n) {
            val angle = random.nextFloat() * TWO_PI
            val speed = BURST_SPEED_MIN + random.nextFloat() * (BURST_SPEED_MAX - BURST_SPEED_MIN)
            spawn(
                kind = Kind.BURST,
                x = x,
                y = y,
                vx = cos(angle) * speed,
                vy = sin(angle) * speed,
                lifeMs = BURST_LIFE_MIN + random.nextFloat() * (BURST_LIFE_MAX - BURST_LIFE_MIN),
                size = BURST_SIZE_MIN + random.nextFloat() * (BURST_SIZE_MAX - BURST_SIZE_MIN),
                color = color,
                drag = BURST_DRAG
            )
        }
    }

    // ------------------------------------------------------------------ 帧更新 / 绘制

    /**
     * 单帧推进。[dtMs] 为距上一帧的毫秒数（GraphView 节拍为 16）。
     * 只做标量运算，无分配。
     */
    override fun update(dtMs: Long) {
        if (dtMs <= 0L || activeCount == 0) return
        val dt = dtMs.toFloat()
        for (i in pool.indices) {
            val p = pool[i]
            if (!p.active) continue
            p.ageMs += dt
            if (p.ageMs >= p.lifeMs) {
                p.active = false
                activeCount--
                continue
            }
            // 阻尼：drag 为每 ms 保留系数，用一阶近似避免 pow 开销
            val damp = 1f - (1f - p.drag) * dt
            p.vx *= damp
            p.vy *= damp
            p.x += p.vx * dt
            p.y += p.vy * dt
        }
    }

    /**
     * 把存活粒子绘制到 [canvas]。应在连线/节点之后叠加调用。
     * 光尾粒子画成速度方向的渐隐线段（头亮尾淡），爆炸粒子画成渐隐收缩圆点。
     */
    override fun render(canvas: Canvas) {
        if (activeCount == 0) return
        for (i in pool.indices) {
            val p = pool[i]
            if (!p.active) continue
            val lifeT = p.ageMs / p.lifeMs          // 0 → 1
            val fade = 1f - lifeT
            when (p.kind) {
                Kind.FLOW -> renderFlowParticle(canvas, p, fade)
                Kind.BURST -> renderBurstParticle(canvas, p, fade)
            }
        }
    }

    /** 清空全部粒子（setData 重建图谱 / 视图销毁时调用）。 */
    override fun clear() {
        for (i in pool.indices) pool[i].reset()
        activeCount = 0
        cursor = 0
    }

    // ------------------------------------------------------------------ 内部

    /** 池满时环形覆盖最旧；占用过高时自动降密度（降级策略）。 */
    private fun effectiveCount(requested: Int): Int {
        val utilization = activeCount.toFloat() / maxParticles
        val scale = when {
            utilization > 0.9f -> 0.25f
            utilization > 0.75f -> 0.5f
            else -> 1f
        }
        return (requested * density * scale).toInt().coerceAtLeast(if (requested > 0) 1 else 0)
    }

    /** 写入一个粒子；池满时覆盖环形游标处（即最旧写入位置）。 */
    private fun spawn(
        kind: Kind, x: Float, y: Float, vx: Float, vy: Float,
        lifeMs: Float, size: Float, color: Int, drag: Float
    ) {
        val p = pool[cursor]
        cursor = (cursor + 1) % maxParticles
        if (!p.active) activeCount++   // 覆盖活跃槽位 = 丢弃最旧，计数不变
        p.active = true
        p.kind = kind
        p.x = x; p.y = y
        p.vx = vx; p.vy = vy
        p.ageMs = 0f
        p.lifeMs = lifeMs
        p.size = size
        p.color = color
        p.drag = drag
    }

    /** 光尾粒子：沿速度方向画 [TAIL_SEGMENTS] 段渐隐线段，头部带亮点。 */
    private fun renderFlowParticle(canvas: Canvas, p: Particle, fade: Float) {
        val speed = sqrt(p.vx * p.vx + p.vy * p.vy)
        if (speed < 0.001f) return
        val ux = p.vx / speed
        val uy = p.vy / speed
        val tailLen = min(speed * TAIL_LENGTH_FACTOR, TAIL_LENGTH_MAX) * fade
        val baseAlpha = (p.color ushr 24) and 0xFF
        val rgb = p.color and 0x00FFFFFF

        var segStartX = p.x
        var segStartY = p.y
        // 从头向尾逐段绘制，alpha 与线宽递减，伪造“拖尾渐隐”
        for (seg in 0 until TAIL_SEGMENTS) {
            val segT0 = seg.toFloat() / TAIL_SEGMENTS
            val segT1 = (seg + 1).toFloat() / TAIL_SEGMENTS
            val segEndX = p.x - ux * tailLen * segT1
            val segEndY = p.y - uy * tailLen * segT1
            val alpha = (baseAlpha * fade * (1f - segT0)).toInt().coerceIn(0, 255)
            strokePaint.color = rgb or (alpha shl 24)
            strokePaint.strokeWidth = (p.size * 1.2f * (1f - segT0)).coerceAtLeast(0.5f)
            canvas.drawLine(segStartX, segStartY, segEndX, segEndY, strokePaint)
            segStartX = segEndX
            segStartY = segEndY
        }
        // 头部亮点
        val headAlpha = (baseAlpha * fade).toInt().coerceIn(0, 255)
        fillPaint.color = rgb or (headAlpha shl 24)
        canvas.drawCircle(p.x, p.y, p.size, fillPaint)
    }

    /** 爆炸粒子：渐隐 + 半径随生命收缩的圆点。 */
    private fun renderBurstParticle(canvas: Canvas, p: Particle, fade: Float) {
        val baseAlpha = (p.color ushr 24) and 0xFF
        val alpha = (baseAlpha * fade * fade).toInt().coerceIn(0, 255)   // 平方衰减更快收尾
        fillPaint.color = (p.color and 0x00FFFFFF) or (alpha shl 24)
        canvas.drawCircle(p.x, p.y, (p.size * fade).coerceAtLeast(0.5f), fillPaint)
    }

    // ------------------------------------------------------------------ 常量

    companion object {
        const val DEFAULT_MAX_PARTICLES = 512

        private const val TWO_PI = (2.0 * Math.PI).toFloat()

        // 光尾粒子参数
        private const val FLOW_PARTICLES_PER_TICK = 3
        private const val FLOW_SPEED_MIN = 0.12f      // px/ms
        private const val FLOW_SPEED_MAX = 0.30f      // px/ms
        private const val FLOW_JITTER = 0.03f         // 垂直抖动 px/ms
        private const val FLOW_SPAWN_SPREAD = 6f      // 出生点散布 px
        private const val FLOW_LIFE_MIN = 350f        // ms
        private const val FLOW_LIFE_MAX = 650f        // ms
        private const val FLOW_SIZE_MIN = 2f          // px
        private const val FLOW_SIZE_MAX = 4.5f        // px
        private const val FLOW_DRAG = 0.999f          // 每 ms 速度保留（≈ 无阻尼）

        // 爆炸粒子参数
        private const val BURST_PARTICLES_DEFAULT = 24
        private const val BURST_SPEED_MIN = 0.10f     // px/ms
        private const val BURST_SPEED_MAX = 0.55f     // px/ms
        private const val BURST_LIFE_MIN = 400f       // ms
        private const val BURST_LIFE_MAX = 900f       // ms
        private const val BURST_SIZE_MIN = 2f         // px
        private const val BURST_SIZE_MAX = 5f         // px
        private const val BURST_DRAG = 0.996f         // 每 ms 速度保留（放射衰减）

        // 拖尾渲染参数
        private const val TAIL_SEGMENTS = 3
        private const val TAIL_LENGTH_FACTOR = 90f    // tail = speed * factor
        private const val TAIL_LENGTH_MAX = 48f       // px
    }
}
