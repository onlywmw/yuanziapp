package com.nous.widgetmcp

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.widget.RemoteViews
import com.nous.widgetmcp.hermes.HermesPollReceiver
import com.nous.widgetmcp.widget.WidgetBinding

object WidgetRenderer {
    const val ACTION_WIDGET_CLICK = "com.nous.widgetmcp.action.WIDGET_CLICK"
    private const val EXTRA_SYSTEM_WIDGET_ID = "system_widget_id"
    private const val EXTRA_CLICK_ACTION = "click_action"

    private val ctrl get() = ServiceLocator.controller

    fun refresh(context: Context, widgetId: Int) {
        val mgr = AppWidgetManager.getInstance(context)
        val snap = ctrl.snapshot(widgetId)
        val views = if (snap != null) {
            WidgetRegistry.get(snap.config.typeId)?.render(context, snap.config, snap.data)
                ?.withClick(context, widgetId) ?: fallback(context)
        } else fallback(context)
        mgr.updateAppWidget(widgetId, views)
    }

    fun refreshAll(context: Context, ids: IntArray) {
        for (id in ids) refresh(context, id)
    }

    fun pushAndRefresh(context: Context, widgetId: Int, data: WidgetData) {
        ctrl.push(widgetId, data)
        refresh(context, widgetId)
    }

    /** 按系统 appWidgetId 刷新 — 内部 ID 从 WidgetBinding 查 */
    fun refreshBySystemId(context: Context, systemId: Int) {
        val internalId = WidgetBinding.internalId(context, systemId)
        val views = internalId
            ?.let { ctrl.snapshot(it) }
            ?.let { snap ->
                WidgetRegistry.get(snap.config.typeId)?.render(context, snap.config, snap.data)
                    ?.withClick(context, systemId)
            }
            ?: fallback(context)
        AppWidgetManager.getInstance(context).updateAppWidget(systemId, views)
    }

    /** 显示加载态（乐观更新） */
    fun showLoading(context: Context, systemId: Int) {
        val views = RemoteViews(context.packageName, R.layout.widget_minimal)
        views.setTextViewText(R.id.widget_minimal_text, "加载中…")
        AppWidgetManager.getInstance(context).updateAppWidget(systemId, views)
    }

    /** 给 RemoteViews 添加点击 PendingIntent */
    private fun RemoteViews.withClick(context: Context, systemWidgetId: Int): RemoteViews {
        val intent = Intent(context, com.nous.widgetmcp.widget.McpWidgetProvider::class.java).apply {
            action = ACTION_WIDGET_CLICK
            putExtra(EXTRA_SYSTEM_WIDGET_ID, systemWidgetId)
            putExtra(EXTRA_CLICK_ACTION, "refresh")
        }
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        val pending = PendingIntent.getBroadcast(context, systemWidgetId, intent, flags)
        setOnClickPendingIntent(R.id.widget_root_click_area, pending)
        return this
    }

    private fun fallback(context: Context): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.widget_minimal)
        views.setTextViewText(R.id.widget_minimal_text, "暂无数据")
        return views
    }

    fun isWidgetClick(intent: Intent): Boolean = intent.action == ACTION_WIDGET_CLICK

    fun getSystemWidgetId(intent: Intent): Int = intent.getIntExtra(EXTRA_SYSTEM_WIDGET_ID, -1)

    fun getClickAction(intent: Intent): String = intent.getStringExtra(EXTRA_CLICK_ACTION) ?: "refresh"
}
