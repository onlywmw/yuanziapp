package com.nous.widgetmcp.yuanzi

import android.content.Context
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.nous.widgetmcp.AppLogger

/**
 * Chaquopy 嵌入式 Python 启动桥（DESIGN_CHAQUOPY_MIGRATION §四）。
 *
 * App 启动时调用 ensureStarted()：
 *   1. 初始化 Chaquopy 运行时
 *   2. 调 api.start_server(filesDir) 在守护线程启动 uvicorn
 *   3. 之后 YuanziApi 的 HTTP 调用（127.0.0.1:8081）一行不改继续可用
 */
object PythonBridge {
    private const val TAG = "PYBRIDGE"

    @Volatile
    private var started = false

    @Synchronized
    fun ensureStarted(context: Context): Boolean {
        if (started) return true
        return try {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(context.applicationContext))
            }
            Python.getInstance()
                .getModule("api")
                .callAttr("start_server", context.filesDir.absolutePath)
            started = true
            AppLogger.i(TAG, "embedded Python API started (127.0.0.1:8081)")
            true
        } catch (e: Exception) {
            AppLogger.e(TAG, "failed to start embedded Python: ${e.message}", e)
            false
        }
    }
}
