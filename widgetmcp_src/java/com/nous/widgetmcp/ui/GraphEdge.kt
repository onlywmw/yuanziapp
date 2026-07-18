package com.nous.widgetmcp.ui

/**
 * 知识图谱连线
 */
data class GraphEdge(
    val sourceId: String,
    val targetId: String,
    val color: Int,
    val width: Float = 2f
)
