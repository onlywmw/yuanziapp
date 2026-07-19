package com.nous.widgetmcp.ui

import android.graphics.PointF

/**
 * 知识图谱连线
 */
data class GraphEdge(
    val sourceId: String,
    val targetId: String,
    val color: Int,
    val width: Float = 2f
) {
    /**
     * 端点坐标（M8）。引擎在每帧绘制前根据 sourceId/targetId
     * 对应节点的当前位置填充，供模板 renderEdge 使用。
     */
    val sourcePos = PointF(0f, 0f)
    val targetPos = PointF(0f, 0f)
}
