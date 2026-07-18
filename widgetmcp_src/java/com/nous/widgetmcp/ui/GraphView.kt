package com.nous.widgetmcp.ui

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
        startAnimation()
    }

    fun setData(nodes: List<GraphNode>, edges: List<GraphEdge>) {
        this.nodes.clear()
        this.edges.clear()
        this.nodeMap.clear()

        this.nodes.addAll(nodes)
        this.edges.addAll(edges)
        nodes.forEach { nodeMap[it.id] = it }

        resetLayout()
        invalidate()
    }

    /** 按节点 id 查找（搜索定位用，M5 任务 5.4）。 */
    fun findNode(id: String): GraphNode? = nodeMap[id]

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

        // 斥力
        for (i in nodes.indices) {
            for (j in i + 1 until nodes.size) {
                val a = nodes[i]
                val b = nodes[j]
                val dx = a.pos.x - b.pos.x
                val dy = a.pos.y - b.pos.y
                val dist = sqrt(dx * dx + dy * dy).coerceAtLeast(1f)
                val force = 3000f / (dist * dist)
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
            val targetLen = a.radius + b.radius + 80f
            val force = (dist - targetLen) * 0.02f
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
            node.vel.x += dx * 0.003f
            node.vel.y += dy * 0.003f

            node.vel.x *= 0.85f
            node.vel.y *= 0.85f

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
        canvas.drawColor(Color.parseColor("#F7F4EE"))

        // 画线
        edges.forEach { edge ->
            val a = nodeMap[edge.sourceId] ?: return@forEach
            val b = nodeMap[edge.targetId] ?: return@forEach
            linePaint.color = edge.color
            linePaint.strokeWidth = edge.width
            canvas.drawLine(a.pos.x, a.pos.y, b.pos.x, b.pos.y, linePaint)
        }

        // 画节点
        nodes.forEach { node ->
            nodePaint.color = node.color
            canvas.drawCircle(node.pos.x, node.pos.y, node.radius, nodePaint)
            canvas.drawCircle(node.pos.x, node.pos.y, node.radius, strokePaint)

            textPaint.color = node.textColor
            textPaint.textSize = node.radius * 0.30f
            val lines = wrapLabel(node.label, node.radius * 2.2f)
            val lineHeight = textPaint.fontMetrics.descent - textPaint.fontMetrics.ascent
            val totalHeight = lines.size * lineHeight
            var y = node.pos.y - totalHeight / 2f - textPaint.fontMetrics.ascent
            lines.forEach { line ->
                canvas.drawText(line, node.pos.x, y, textPaint)
                y += lineHeight
            }
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
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        if (nodes.isNotEmpty() && (oldw == 0 || oldh == 0)) {
            resetLayout()
        }
    }
}
