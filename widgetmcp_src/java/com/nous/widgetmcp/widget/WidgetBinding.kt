package com.nous.widgetmcp.widget

import android.content.Context

/**
 * 内部 widgetId ↔ 系统 appWidgetId 映射
 *
 * pin 前: markPending(context, internalId)
 * pin 后 (onUpdate): consumePending(context) → bind(systemId, internalId)
 *
 * pending 同时持久化到 SharedPreferences：MIUI 弹确认框时 App 进程可能被冻结/杀死，
 * 仅存内存会导致 onUpdate 时拿不到内部 ID，widget 永远处于未绑定状态。
 */
object WidgetBinding {
    private const val SP = "widget_binding"
    private const val KEY_PENDING = "pending_internal_id"

    @Volatile private var pendingInternalId: Int? = null

    private fun sp(context: Context) = context.getSharedPreferences(SP, Context.MODE_PRIVATE)

    fun markPending(context: Context, internalId: Int) {
        pendingInternalId = internalId
        // 必须同步落盘：MIUI Greezer 会在 requestPin 后立即冻结/杀死进程，
        // apply() 的异步写根本来不及写进文件，onUpdate 时就拿不到 pending。
        sp(context).edit().putInt(KEY_PENDING, internalId).commit()
    }

    fun consumePending(context: Context): Int? {
        val fromMem = pendingInternalId
        val fromSp = sp(context).getInt(KEY_PENDING, -1).takeIf { it != -1 }
        pendingInternalId = null
        sp(context).edit().remove(KEY_PENDING).apply()
        return fromMem ?: fromSp
    }

    fun bind(context: Context, systemId: Int, internalId: Int) =
        sp(context).edit().putInt("sys_$systemId", internalId).commit()

    fun unbind(context: Context, systemId: Int) =
        sp(context).edit().remove("sys_$systemId").apply()

    fun internalId(context: Context, systemId: Int): Int? =
        sp(context).getInt("sys_$systemId", -1).takeIf { it != -1 }

    fun isPinned(context: Context, internalId: Int): Boolean {
        val prefs = sp(context)
        return prefs.all.entries.any { it.key.startsWith("sys_") && it.value == internalId }
    }
}
