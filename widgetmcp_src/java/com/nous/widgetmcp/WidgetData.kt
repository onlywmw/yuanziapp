package com.nous.widgetmcp

sealed class WidgetData {
    data class Text(val content: String, val metadata: Map<String, Any> = emptyMap()) : WidgetData()
    data class Markdown(val raw: String, val rendered: String) : WidgetData()
    data class Number(val value: Double, val unit: String? = null, val trend: String? = null) : WidgetData()
    data class ListItems(val items: List<ListItem>) : WidgetData()
}

data class ListItem(val title: String, val subtitle: String = "", val value: String = "")
