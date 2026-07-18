package com.nous.widgetmcp.ui

import android.graphics.PointF

/**
 * 知识图谱节点
 */
data class GraphNode(
    val id: String,
    val label: String,
    val type: NodeType,
    val color: Int,
    val textColor: Int,
    val radius: Float = 48f,
    val payload: Any? = null
) {
    val pos = PointF(0f, 0f)
    val vel = PointF(0f, 0f)

    enum class NodeType {
        CENTER,       // 中心「组件 MCP」
        WIDGET,       // 已添加的 widget 实例
        ADD_TEMPLATE, // 添加模块（余额 / 文本 / Obsidian）
        YUANZI,       // Yuanzi 中枢
        BROWSER,      // 浏览器
        SETTINGS      // 设置
    }
}
