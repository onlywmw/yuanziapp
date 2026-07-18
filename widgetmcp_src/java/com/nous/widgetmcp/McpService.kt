package com.nous.widgetmcp

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder

class McpService : Service() {
    private var server: McpServer? = null

    override fun onCreate() {
        super.onCreate()
        startForegroundNotification()
        startServer()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        server?.stop()
        super.onDestroy()
    }

    private fun startForegroundNotification() {
        val channelId = "mcp_service"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(channelId, "MCP 服务", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        val notification = Notification.Builder(this, channelId)
            .setContentTitle("组件 MCP")
            .setContentText("MCP 服务运行中 → :8766")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .build()
        startForeground(1, notification)
    }

    private fun startServer() {
        val prefs = getSharedPreferences("widget_mcp", Context.MODE_PRIVATE)
        val port = prefs.getInt("mcp_port", 8766)
        server = McpServer(port).apply {
            try {
                start()
            } catch (e: Exception) {
                AppLogger.e("McpService", "Server start failed", e)
                stopSelf()
            }
        }
    }
}
