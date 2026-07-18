package com.nous.widgetmcp.hermes

import android.content.Context
import android.content.SharedPreferences

/**
 * Hermes 中枢连接配置
 *
 * 默认连接 Termux 侧 127.0.0.1:8080，支持 token 鉴权。
 */
object HermesConfig {
    private const val SP = "hermes_config"
    private const val KEY_HOST = "host"
    private const val KEY_PORT = "port"
    private const val KEY_TOKEN = "token"
    private const val KEY_ENABLED = "enabled"
    private const val KEY_LAST_SYNC = "last_sync"
    private const val KEY_LAST_ERROR = "last_error"

    private var prefs: SharedPreferences? = null

    fun init(context: Context) {
        prefs = context.getSharedPreferences(SP, Context.MODE_PRIVATE)
    }

    var host: String
        get() = prefs?.getString(KEY_HOST, "127.0.0.1") ?: "127.0.0.1"
        set(value) { prefs?.edit()?.putString(KEY_HOST, value)?.apply() }

    var port: Int
        get() = prefs?.getInt(KEY_PORT, 8080) ?: 8080
        set(value) { prefs?.edit()?.putInt(KEY_PORT, value)?.apply() }

    var token: String
        get() = prefs?.getString(KEY_TOKEN, "") ?: ""
        set(value) { prefs?.edit()?.putString(KEY_TOKEN, value)?.apply() }

    var enabled: Boolean
        get() = prefs?.getBoolean(KEY_ENABLED, true) ?: true
        set(value) { prefs?.edit()?.putBoolean(KEY_ENABLED, value)?.apply() }

    var lastSync: Long
        get() = prefs?.getLong(KEY_LAST_SYNC, 0L) ?: 0L
        set(value) { prefs?.edit()?.putLong(KEY_LAST_SYNC, value)?.apply() }

    var lastError: String?
        get() = prefs?.getString(KEY_LAST_ERROR, null)
        set(value) {
            prefs?.edit()?.apply {
                if (value == null) remove(KEY_LAST_ERROR) else putString(KEY_LAST_ERROR, value)
                apply()
            }
        }

    val baseUrl: String get() = "http://$host:$port"

    fun setEndpoint(host: String, port: Int, token: String) {
        prefs?.edit()?.apply {
            putString(KEY_HOST, host)
            putInt(KEY_PORT, port)
            putString(KEY_TOKEN, token)
            apply()
        }
    }
}
