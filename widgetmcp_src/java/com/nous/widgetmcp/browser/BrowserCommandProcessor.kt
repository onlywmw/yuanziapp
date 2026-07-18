package com.nous.widgetmcp.browser

import android.content.Context
import com.nous.widgetmcp.AppLogger
import com.nous.widgetmcp.yuanzi.YuanziApi

/**
 * 浏览器命令处理器
 *
 * 轮询 Yuanzi 的 /agent/command/poll，拿到命令后唤起 BrowserActivity。
 */
object BrowserCommandProcessor {

    @Volatile
    private var lastEventId: Int = -1

    fun processPendingCommands(context: Context) {
        try {
            val result = YuanziApi.pollCommand()
            result.fold(
                onSuccess = { cmd ->
                    if (cmd != null && cmd.eventId != lastEventId) {
                        lastEventId = cmd.eventId
                        AppLogger.i("BROWSER_CMD", "received ${cmd.toolId} args=${cmd.args}")
                        BrowserActivity.openWithCommand(context, cmd)
                    }
                },
                onFailure = { e ->
                    AppLogger.e("BROWSER_CMD", "poll failed: ${e.message}", e)
                }
            )
        } catch (e: Exception) {
            AppLogger.e("BROWSER_CMD", "processor error", e)
        }
    }
}
