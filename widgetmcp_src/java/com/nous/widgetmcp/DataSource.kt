package com.nous.widgetmcp

enum class DataSourceType { LOCAL_FILE, HTTP_API, MCP_PUSH, SYSTEM_CONTENT }

interface DataSource {
    val id: String
    val type: DataSourceType
    fun fetchData(): Result<WidgetData>
    fun isValid(): Boolean
}
