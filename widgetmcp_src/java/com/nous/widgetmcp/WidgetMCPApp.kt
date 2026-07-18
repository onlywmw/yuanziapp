package com.nous.widgetmcp

import android.app.Application
import com.nous.widgetmcp.hermes.HermesConfig
import com.nous.widgetmcp.hermes.HermesPollScheduler
import com.nous.widgetmcp.hermes.HermesSyncService

class WidgetMCPApp : Application() {
    override fun onCreate() {
        super.onCreate()
        ServiceLocator.init(this)

        // 注意：不要在 Application.onCreate 里启动前台服务，Android 14 后台启动受限。
        // 轮询恢复交给 MainActivity / WidgetProvider / AlarmManager 广播。
    }
}
