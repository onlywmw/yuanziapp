package com.nous.widgetmcp.data.repo

import com.nous.widgetmcp.WidgetConfig
import com.nous.widgetmcp.WidgetData
import com.nous.widgetmcp.WidgetInstanceManager
import com.nous.widgetmcp.WidgetStateStore
import com.nous.widgetmcp.domain.contract.WidgetRepository

/**
 * [架构分层] Repository 实现 — 委托给已有的 SQLite 存储层
 *
 * WidgetInstanceManager 和 WidgetStateStore 已经是 SQLite,
 * 这里只是把它们包装成接口, 实现依赖倒置。
 */
class WidgetRepositoryImpl : WidgetRepository {

    override fun getConfig(widgetId: Int): WidgetConfig? =
        WidgetInstanceManager.instance?.get(widgetId)

    override fun saveConfig(config: WidgetConfig) {
        WidgetInstanceManager.instance?.save(config)
    }

    override fun deleteConfig(widgetId: Int) {
        WidgetInstanceManager.instance?.delete(widgetId)
    }

    override fun listConfigs(): List<WidgetConfig> =
        WidgetInstanceManager.instance?.list() ?: emptyList()

    override fun getState(widgetId: Int): WidgetData? =
        WidgetStateStore.get(widgetId)

    override fun saveState(widgetId: Int, data: WidgetData) {
        WidgetStateStore.put(widgetId, data)
    }
}
