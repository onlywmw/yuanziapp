package com.nous.widgetmcp.yuanzi

import android.content.Context
import android.content.SharedPreferences

/**
 * Yuanzi 中枢连接配置
 *
 * 端口口径（以代码现实为准）：
 *  - Yuanzi Core（yuanzi-atoms/core/main.py）：127.0.0.1:8080，提供 /graph、/agent/*。
 *  - 注册中心（内嵌 Chaquopy FastAPI，api.start_server）：127.0.0.1:8081，提供 /health、/search 等。
 *  - APK 内嵌 McpServer 默认 8766（见 McpService），与本配置无关。
 * 支持 token 鉴权。
 */
object YuanziConfig {
    private const val SP = "yuanzi_config"
    private const val KEY_HOST = "host"
    private const val KEY_PORT = "port"
    private const val KEY_REGISTRY_PORT = "registry_port"
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

    /** Yuanzi Core 端口（/graph、/agent/*），默认 8080 */
    var port: Int
        get() = prefs?.getInt(KEY_PORT, 8080) ?: 8080
        set(value) { prefs?.edit()?.putInt(KEY_PORT, value)?.apply() }

    /** 注册中心端口（/health、/search 等 FastAPI 端点），默认 8081；与 Core 共用 host */
    var registryPort: Int
        get() = prefs?.getInt(KEY_REGISTRY_PORT, 8081) ?: 8081
        set(value) { prefs?.edit()?.putInt(KEY_REGISTRY_PORT, value)?.apply() }

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

    /** Yuanzi Core baseUrl：图谱与 agent 通道（/graph、/agent/*） */
    val coreBaseUrl: String get() = "http://$host:$port"

    /** 注册中心 baseUrl：/health、/search 等 REST 端点 */
    val registryBaseUrl: String get() = "http://$host:$registryPort"

    /** 兼容旧调用方：等价于 coreBaseUrl */
    val baseUrl: String get() = coreBaseUrl

    fun setEndpoint(host: String, port: Int, token: String) {
        prefs?.edit()?.apply {
            putString(KEY_HOST, host)
            putInt(KEY_PORT, port)
            putString(KEY_TOKEN, token)
            apply()
        }
    }
}
