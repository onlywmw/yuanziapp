package com.nous.widgetmcp.yuanzi

import android.content.Context
import com.nous.widgetmcp.*
import com.nous.widgetmcp.widget.WidgetBinding

/**
 * Yuanzi 数据同步器
 *
 * 1. 拉取 Yuanzi /agent/widgets
 * 2. 与本地的 widget_instances/widget_state 对齐
 * 3. 触发桌面 widget 刷新
 */
object YuanziSync {

    private val ctrl get() = ServiceLocator.controller

    /**
     * 执行一次同步。返回同步到的 widget 数量，失败返回负数错误码。
     */
    fun syncOnce(context: Context): Result<Int> {
        if (!YuanziConfig.enabled) return Result.success(0)
        return try {
            val remote = YuanziApi.fetchWidgets().getOrThrow()
            applyRemoteWidgets(context, remote)
            YuanziConfig.lastSync = System.currentTimeMillis()
            YuanziConfig.lastError = null
            Result.success(remote.size)
        } catch (e: Exception) {
            YuanziConfig.lastError = e.message
            AppLogger.e("YUANZI_SYNC", "sync failed: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * 将 Yuanzi widget 列表应用到本地缓存。
     * - Yuanzi 有、本地无：创建内部 widget 实例并绑定到桌面（如果已存在系统 widgetId 映射）
     * - Yuanzi 有、本地有：更新 config / state
     * - Yuanzi 无、本地有（且来源为 YUANZI）：删除本地实例
     */
    private fun applyRemoteWidgets(context: Context, remote: List<YuanziWidget>) {
        val localConfigs = ctrl.list().toMutableList()
        val localByYuanziId = localConfigs
            .filter { it.yuanziId != null }
            .associateBy { it.yuanziId }
            .toMutableMap()

        for (hw in remote) {
            val existing = localByYuanziId[hw.widgetId]
            if (existing != null) {
                // 更新现有 widget
                updateFromYuanzi(existing.widgetId, hw)
            } else {
                // 新建 widget
                val internalId = createFromYuanzi(hw)
                // 若桌面已有同 yuanziId 的系统 widget 绑定，需要重新绑定（通常由系统重新触发）
                localByYuanziId[hw.widgetId] = ctrl.snapshot(internalId)?.config ?: continue
            }
        }

        // 清理 Yuanzi 已删除、但本地仍存在的 YUANZI 来源 widget
        val remoteIds = remote.map { it.widgetId }.toSet()
        for (cfg in localConfigs) {
            if (cfg.source == WidgetSource.YUANZI && cfg.yuanziId !in remoteIds) {
                ctrl.delete(cfg.widgetId)
            }
        }

        // 刷新所有已绑定到桌面的 widget
        refreshBoundWidgets(context)
    }

    private fun createFromYuanzi(hw: YuanziWidget): Int {
        val internalId = ctrl.create(
            typeId = mapYuanziType(hw.type),
            dataSourceId = hw.config.dataSourceId ?: hw.type,
            source = WidgetSource.YUANZI,
            credentialRef = hw.config.credentialRef
        )
        // 回填 yuanziId
        val cfg = ctrl.snapshot(internalId)?.config ?: return internalId
        ServiceLocator.repository.saveConfig(cfg.copy(yuanziId = hw.widgetId))
        // 写入初始数据
        pushData(internalId, hw)
        return internalId
    }

    private fun updateFromYuanzi(internalId: Int, hw: YuanziWidget) {
        val cfg = ctrl.snapshot(internalId)?.config ?: return
        ServiceLocator.repository.saveConfig(cfg.copy(
            dataSourceId = hw.config.dataSourceId ?: cfg.dataSourceId,
            credentialRef = hw.config.credentialRef ?: cfg.credentialRef,
            refreshInterval = hw.config.refreshIntervalMs
        ))
        pushData(internalId, hw)
        // push 会清空 lastError，这里根据 Yuanzi 状态重新写回
        if (hw.lastError != null || hw.status == "error") {
            val refreshed = ctrl.snapshot(internalId)?.config ?: return
            ServiceLocator.repository.saveConfig(refreshed.copy(
                lastError = hw.lastError ?: refreshed.lastError
            ))
        }
    }

    private fun pushData(internalId: Int, hw: YuanziWidget) {
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

    private fun mapYuanziType(type: String): String {
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
     * 报告 widget 点击事件给 Yuanzi，并在 widget 上显示乐观加载态。
     */
    fun reportWidgetClick(context: Context, systemWidgetId: Int, action: String = "refresh") {
        val internalId = WidgetBinding.internalId(context, systemWidgetId) ?: return
        val cfg = ctrl.snapshot(internalId)?.config ?: return
        val yuanziId = cfg.yuanziId ?: return

        // 乐观更新：先显示加载中
        WidgetRenderer.showLoading(context, systemWidgetId)

        // 上报 Yuanzi
        val event = YuanziEvent(
            source = "widget",
            toolId = "widget/click",
            args = mapOf(
                "widget_id" to yuanziId,
                "internal_id" to internalId,
                "action" to action
            )
        )
        WidgetExecutor.pool.submit {
            val result = YuanziApi.reportEvent(event)
            result.onSuccess {
                // 上报成功后立即拉取一次最新状态
                syncOnce(context)
            }.onFailure { e ->
                AppLogger.e("YUANZI_SYNC", "report click failed: ${e.message}", e)
                // 失败：恢复显示本地缓存数据（或错误提示）
                WidgetRenderer.refreshBySystemId(context, systemWidgetId)
            }
        }
    }
}
