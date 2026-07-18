package com.nous.widgetmcp.hermes

import android.content.Context
import com.nous.widgetmcp.*
import com.nous.widgetmcp.widget.WidgetBinding

/**
 * Hermes 数据同步器
 *
 * 1. 拉取 Hermes /agent/widgets
 * 2. 与本地的 widget_instances/widget_state 对齐
 * 3. 触发桌面 widget 刷新
 */
object HermesSync {

    private val ctrl get() = ServiceLocator.controller

    /**
     * 执行一次同步。返回同步到的 widget 数量，失败返回负数错误码。
     */
    fun syncOnce(context: Context): Result<Int> {
        if (!HermesConfig.enabled) return Result.success(0)
        return try {
            val remote = HermesApi.fetchWidgets().getOrThrow()
            applyRemoteWidgets(context, remote)
            HermesConfig.lastSync = System.currentTimeMillis()
            HermesConfig.lastError = null
            Result.success(remote.size)
        } catch (e: Exception) {
            HermesConfig.lastError = e.message
            AppLogger.e("HERMES_SYNC", "sync failed: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * 将 Hermes widget 列表应用到本地缓存。
     * - Hermes 有、本地无：创建内部 widget 实例并绑定到桌面（如果已存在系统 widgetId 映射）
     * - Hermes 有、本地有：更新 config / state
     * - Hermes 无、本地有（且来源为 HERMES）：删除本地实例
     */
    private fun applyRemoteWidgets(context: Context, remote: List<HermesWidget>) {
        val localConfigs = ctrl.list().toMutableList()
        val localByHermesId = localConfigs
            .filter { it.hermesId != null }
            .associateBy { it.hermesId }
            .toMutableMap()

        for (hw in remote) {
            val existing = localByHermesId[hw.widgetId]
            if (existing != null) {
                // 更新现有 widget
                updateFromHermes(existing.widgetId, hw)
            } else {
                // 新建 widget
                val internalId = createFromHermes(hw)
                // 若桌面已有同 hermesId 的系统 widget 绑定，需要重新绑定（通常由系统重新触发）
                localByHermesId[hw.widgetId] = ctrl.snapshot(internalId)?.config ?: continue
            }
        }

        // 清理 Hermes 已删除、但本地仍存在的 HERMES 来源 widget
        val remoteIds = remote.map { it.widgetId }.toSet()
        for (cfg in localConfigs) {
            if (cfg.source == WidgetSource.HERMES && cfg.hermesId !in remoteIds) {
                ctrl.delete(cfg.widgetId)
            }
        }

        // 刷新所有已绑定到桌面的 widget
        refreshBoundWidgets(context)
    }

    private fun createFromHermes(hw: HermesWidget): Int {
        val internalId = ctrl.create(
            typeId = mapHermesType(hw.type),
            dataSourceId = hw.config.dataSourceId ?: hw.type,
            source = WidgetSource.HERMES,
            credentialRef = hw.config.credentialRef
        )
        // 回填 hermesId
        val cfg = ctrl.snapshot(internalId)?.config ?: return internalId
        ServiceLocator.repository.saveConfig(cfg.copy(hermesId = hw.widgetId))
        // 写入初始数据
        pushData(internalId, hw)
        return internalId
    }

    private fun updateFromHermes(internalId: Int, hw: HermesWidget) {
        val cfg = ctrl.snapshot(internalId)?.config ?: return
        ServiceLocator.repository.saveConfig(cfg.copy(
            dataSourceId = hw.config.dataSourceId ?: cfg.dataSourceId,
            credentialRef = hw.config.credentialRef ?: cfg.credentialRef,
            refreshInterval = hw.config.refreshIntervalMs
        ))
        pushData(internalId, hw)
        // push 会清空 lastError，这里根据 Hermes 状态重新写回
        if (hw.lastError != null || hw.status == "error") {
            val refreshed = ctrl.snapshot(internalId)?.config ?: return
            ServiceLocator.repository.saveConfig(refreshed.copy(
                lastError = hw.lastError ?: refreshed.lastError
            ))
        }
    }

    private fun pushData(internalId: Int, hw: HermesWidget) {
        val data = when {
            hw.config.value != null -> WidgetData.Number(
                value = hw.config.value ?: 0.0,
                unit = hw.config.unit,
                trend = hw.config.display["trend"]
            )
            hw.config.items.isNotEmpty() -> WidgetData.ListItems(
                hw.config.items.map { ListItem(it.title, it.subtitle ?: "", it.value ?: "") }
            )
            hw.config.content != null -> WidgetData.Text(hw.config.content ?: "")
            hw.config.title != null -> WidgetData.Text(hw.config.title ?: "")
            else -> WidgetData.Text("")
        }
        ctrl.push(internalId, data)
    }

    private fun mapHermesType(type: String): String {
        return when (type) {
            "balance" -> "balance"
            "text" -> "text"
            "card_list" -> "obsidian-card"
            else -> type
        }
    }

    private fun refreshBoundWidgets(context: Context) {
        val mgr = android.appwidget.AppWidgetManager.getInstance(context)
        val cn = android.content.ComponentName(context, com.nous.widgetmcp.widget.McpWidgetProvider::class.java)
        val ids = mgr.getAppWidgetIds(cn)
        for (systemId in ids) {
            WidgetRenderer.refreshBySystemId(context, systemId)
        }
    }

    /**
     * 报告 widget 点击事件给 Hermes，并在 widget 上显示乐观加载态。
     */
    fun reportWidgetClick(context: Context, systemWidgetId: Int, action: String = "refresh") {
        val internalId = WidgetBinding.internalId(context, systemWidgetId) ?: return
        val cfg = ctrl.snapshot(internalId)?.config ?: return
        val hermesId = cfg.hermesId ?: return

        // 乐观更新：先显示加载中
        WidgetRenderer.showLoading(context, systemWidgetId)

        // 上报 Hermes
        val event = HermesEvent(
            source = "widget",
            toolId = "widget/click",
            args = mapOf(
                "widget_id" to hermesId,
                "internal_id" to internalId,
                "action" to action
            )
        )
        WidgetExecutor.pool.submit {
            val result = HermesApi.reportEvent(event)
            result.onSuccess {
                // 上报成功后立即拉取一次最新状态
                syncOnce(context)
            }.onFailure { e ->
                AppLogger.e("HERMES_SYNC", "report click failed: ${e.message}", e)
                // 失败：恢复显示本地缓存数据（或错误提示）
                WidgetRenderer.refreshBySystemId(context, systemWidgetId)
            }
        }
    }
}
