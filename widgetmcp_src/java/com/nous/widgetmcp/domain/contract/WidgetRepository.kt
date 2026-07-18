package com.nous.widgetmcp.domain.contract

/**
 * [架构分层] 数据层抽象 — 纯 Kotlin 接口, 不依赖 Android
 *
 * UI/Server 层只依赖此接口, 不直接触碰 SQLite/SharedPreferences。
 * 修改存储方式时只需换实现类, 上层代码无感知。
 */
interface WidgetRepository {
    fun getConfig(widgetId: Int): com.nous.widgetmcp.WidgetConfig?
    fun saveConfig(config: com.nous.widgetmcp.WidgetConfig)
    fun deleteConfig(widgetId: Int)
    fun listConfigs(): List<com.nous.widgetmcp.WidgetConfig>

    fun getState(widgetId: Int): com.nous.widgetmcp.WidgetData?
    fun saveState(widgetId: Int, data: com.nous.widgetmcp.WidgetData)
}
