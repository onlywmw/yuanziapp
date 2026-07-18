package com.nous.widgetmcp

import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.Executors

/**
 * 轻量日志 — 控制台 + 文件持久化, 单线程异步写入
 */
object AppLogger {
    private var logFile: File? = null
    private val fmt = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)
    private val exec = Executors.newSingleThreadExecutor()

    fun init(dir: File) {
        dir.mkdirs()
        logFile = File(dir, "widget.log").also { f ->
            if (f.length() > 5 * 1024 * 1024) { f.delete(); f.createNewFile() }
        }
        i("LOG", "=== START ===")
    }

    fun i(tag: String, msg: String) = write("I", tag, msg)
    fun e(tag: String, msg: String, t: Throwable? = null) = write("E", tag, msg, t)

    private fun write(level: String, tag: String, msg: String, t: Throwable? = null) {
        val ts = fmt.format(Date())
        Log.i("WMCP", "$level/$tag: $msg")
        exec.execute {
            try {
                val line = buildString {
                    append("$ts [$level] $tag: $msg")
                    t?.let { append("\n${Log.getStackTraceString(it)}") }
                }
                logFile?.appendText("$line\n")
            } catch (_: Exception) {}
        }
    }

    fun lastLines(n: Int = 50): String {
        return try {
            logFile?.readLines()?.takeLast(n)?.joinToString("\n") ?: "(no log)"
        } catch (e: Exception) { "(read error: ${e.message})" }
    }
}
