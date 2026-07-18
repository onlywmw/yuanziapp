package com.nous.widgetmcp.hermes

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import com.nous.widgetmcp.AppLogger
import com.nous.widgetmcp.R
import com.nous.widgetmcp.WidgetExecutor
import com.nous.widgetmcp.browser.BrowserCommandProcessor

/**
 * Hermes 同步前台服务
 *
 * 保持后台存活，定期轮询 Hermes /agent/widgets。
 * 启动后服务内部自行安排下一次轮询（通过 AlarmManager 触发 HermesPollReceiver）。
 */
class HermesSyncService : Service() {

    companion object {
        private const val CHANNEL_ID = "hermes_sync"
        private const val NOTIFICATION_ID = 2

        fun start(context: Context) {
            val intent = Intent(context, HermesSyncService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, HermesSyncService::class.java))
        }
    }

    override fun onCreate() {
        super.onCreate()
        try {
            startForegroundNotification()
        } catch (e: SecurityException) {
            AppLogger.e("HERMES_SVC", "foreground service denied: ${e.message}", e)
            stopSelf()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        AppLogger.i("HERMES_SVC", "sync service started")
        WidgetExecutor.pool.submit {
            try {
                HermesSync.syncOnce(this)
            } catch (e: Exception) {
                AppLogger.e("HERMES_SVC", "sync error", e)
            }
            try {
                // 轮询浏览器命令
                BrowserCommandProcessor.processPendingCommands(this)
            } catch (e: Exception) {
                AppLogger.e("HERMES_SVC", "browser command poll error", e)
            } finally {
                // 安排下一次轮询
                HermesPollScheduler.scheduleNext(this)
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startForegroundNotification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Hermes 中枢同步",
                NotificationManager.IMPORTANCE_LOW
            )
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        val notification = Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Hermes 中枢")
            .setContentText("正在同步桌面组件状态")
            .setSmallIcon(android.R.drawable.ic_popup_sync)
            .build()
        startForeground(NOTIFICATION_ID, notification)
    }
}
