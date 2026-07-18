package com.nous.widgetmcp.widget

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import com.nous.widgetmcp.*
import com.nous.widgetmcp.hermes.HermesConfig
import com.nous.widgetmcp.hermes.HermesPollScheduler
import com.nous.widgetmcp.hermes.HermesSync
import com.nous.widgetmcp.hermes.HermesSyncService

class McpWidgetProvider : AppWidgetProvider() {

    /**
     * 拦截 UPDATE 与自定义点击广播，使用 goAsync 保持广播存活期间进程优先级。
     */
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            AppWidgetManager.ACTION_APPWIDGET_UPDATE -> {
                val mgr = AppWidgetManager.getInstance(context)
                val ids = intent.getIntArrayExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS)
                    ?: mgr.getAppWidgetIds(android.content.ComponentName(context, McpWidgetProvider::class.java))
                val pending = goAsync()
                WidgetExecutor.pool.submit {
                    try {
                        ids.forEach { systemId -> handleUpdate(context, mgr, systemId) }
                    } finally {
                        pending.finish()
                    }
                }
            }
            WidgetRenderer.ACTION_WIDGET_CLICK -> {
                val systemId = WidgetRenderer.getSystemWidgetId(intent)
                if (systemId >= 0) {
                    HermesSync.reportWidgetClick(context, systemId, WidgetRenderer.getClickAction(intent))
                }
            }
            else -> super.onReceive(context, intent)
        }
    }

    override fun onUpdate(context: Context, mgr: AppWidgetManager, appWidgetIds: IntArray) {
        // 备用路径：系统直接调用时同步处理
        appWidgetIds.forEach { handleUpdate(context, mgr, it) }
    }

    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        // 第一个 widget 添加时启动 Hermes 轮询服务
        if (HermesConfig.enabled) {
            HermesSyncService.start(context)
        }
    }

    override fun onDisabled(context: Context) {
        super.onDisabled(context)
        // 所有 widget 删除后停止轮询
        HermesSyncService.stop(context)
        HermesPollScheduler.cancel(context)
    }

    private fun handleUpdate(context: Context, mgr: AppWidgetManager, systemId: Int) {
        AppLogger.i("PROVIDER", "onUpdate systemId=$systemId")
        // 1. 尝试绑定：pin 弹窗触发的，这里拿到内部 ID
        if (WidgetBinding.internalId(context, systemId) == null) {
            WidgetBinding.consumePending(context)?.let {
                WidgetBinding.bind(context, systemId, it)
                AppLogger.i("PROVIDER", "bind systemId=$systemId internalId=$it")
            }
        }

        val internalId = WidgetBinding.internalId(context, systemId)
        if (internalId == null) {
            AppLogger.i("PROVIDER", "unbound systemId=$systemId")
            showUnbound(context, mgr, systemId)
            return
        }

        // 2. 先从本地缓存渲染（快）
        WidgetRenderer.refreshBySystemId(context, systemId)

        // 3. 数据刷新策略
        val config = ServiceLocator.controller.snapshot(internalId)?.config
        when {
            config?.source == WidgetSource.HERMES -> {
                // Hermes 指令 widget：触发一次同步，由 Hermes 回写数据
                WidgetExecutor.pool.submit {
                    try { HermesSync.syncOnce(context) } catch (e: Exception) {
                        AppLogger.e("PROVIDER", "Hermes sync failed: ${e.message}", e)
                    }
                }
            }
            config?.typeId == "balance" -> {
                // 旧版 UI 手动创建的余额 widget：直接拉 DeepSeek（兼容已有用户）
                fetchDeepSeekLegacy(context, systemId, internalId, config)
            }
            else -> {
                // 其他本地 widget 不主动刷新
            }
        }
    }

    private fun fetchDeepSeekLegacy(context: Context, systemId: Int, internalId: Int, config: WidgetConfig) {
        val credId = config.credentialRef ?: run {
            AppLogger.e("PROVIDER", "no credentialRef internalId=$internalId", null); return
        }
        val key = CredentialStore.get(credId, "api_key")
            ?: CredentialStore.get("deepseek_test", "api_key")
            ?: run { AppLogger.e("PROVIDER", "no api_key credId=$credId", null); return }

        AppLogger.i("FETCH", "legacy start systemId=$systemId internalId=$internalId")
        WidgetExecutor.pool.submit {
            try {
                val balance = DeepSeekService(key).fetchBalance()
                if (balance != null) {
                    ServiceLocator.controller.push(internalId,
                        WidgetData.Number(balance.totalBalance.toDoubleOrNull() ?: 0.0, "CNY"))
                    WidgetRenderer.refreshBySystemId(context, systemId)
                }
            } catch (e: Exception) {
                AppLogger.e("FETCH", "legacy fail: ${e.message}", e)
                ServiceLocator.controller.push(internalId,
                    WidgetData.Text("刷新失败: ${e.message ?: "未知"}"))
                WidgetRenderer.refreshBySystemId(context, systemId)
            }
        }
    }

    override fun onDeleted(context: Context, appWidgetIds: IntArray) {
        appWidgetIds.forEach { WidgetBinding.unbind(context, it) }
    }

    private fun showUnbound(context: Context, mgr: AppWidgetManager, systemId: Int) {
        val views = android.widget.RemoteViews(context.packageName, R.layout.widget_minimal)
        views.setTextViewText(R.id.widget_minimal_text, "组件 MCP\n请打开 App 配置")
        mgr.updateAppWidget(systemId, views)
    }
}
