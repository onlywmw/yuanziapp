package com.nous.widgetmcp.hermes

import com.nous.widgetmcp.AppLogger
import com.nous.widgetmcp.browser.BrowserCommand
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.Proxy
import java.net.URL
import java.nio.charset.Charset

/**
 * Hermes HTTP 客户端
 *
 * 默认访问 127.0.0.1:8080，所有请求携带 Hermes-API: v1 版本头。
 * 如配置了 token，额外携带 Hermes-Token。
 */
object HermesApi {
    private const val API_VERSION = "v1"
    private const val HEADER_VERSION = "Hermes-API"
    private const val HEADER_TOKEN = "Hermes-Token"
    private const val TIMEOUT = 15_000

    fun fetchWidgets(): Result<List<HermesWidget>> = withConnection("/agent/widgets", "GET") { conn ->
        val body = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(body)
        if (json.optBoolean("ok", false)) {
            val data = json.optJSONArray("data") ?: JSONArray()
            val list = mutableListOf<HermesWidget>()
            for (i in 0 until data.length()) {
                list.add(HermesWidget.fromJson(data.getJSONObject(i)))
            }
            Result.success(list)
        } else {
            Result.failure(Exception(json.optString("error", "Hermes error")))
        }
    }

    fun reportEvent(event: HermesEvent): Result<JSONObject> = withConnection(
        "/agent/event",
        "POST",
        writeBody = { conn ->
            val bytes = event.toJson().toByteArray(Charset.forName("UTF-8"))
            conn.setRequestProperty("Content-Type", "application/json")
            conn.outputStream.write(bytes)
            conn.outputStream.flush()
        }
    ) { conn ->
        val body = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(body)
        if (json.optBoolean("ok", false)) {
            Result.success(json.optJSONObject("data") ?: JSONObject())
        } else {
            Result.failure(Exception(json.optString("error", "Hermes error")))
        }
    }

    fun checkHealth(): Result<String> = withConnection("/health", "GET") { conn ->
        val body = conn.inputStream.bufferedReader().readText()
        Result.success(body)
    }

    fun fetchGraph(): Result<GraphTopology> = withConnection("/graph", "GET") { conn ->
        val body = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(body)
        if (!json.optBoolean("ok", false)) {
            Result.failure(Exception(json.optString("error", "Hermes error")))
        } else {
            val data = json.optJSONObject("data") ?: JSONObject()
            val nodes = data.optJSONArray("nodes") ?: JSONArray()
            val edges = data.optJSONArray("edges") ?: JSONArray()
            val nodeList = mutableListOf<GraphTopology.Node>()
            val edgeList = mutableListOf<GraphTopology.Edge>()
            for (i in 0 until nodes.length()) {
                nodeList.add(GraphTopology.Node.fromJson(nodes.getJSONObject(i)))
            }
            for (i in 0 until edges.length()) {
                edgeList.add(GraphTopology.Edge.fromJson(edges.getJSONObject(i)))
            }
            Result.success(GraphTopology(nodeList, edgeList))
        }
    }

    fun pollCommand(): Result<BrowserCommand?> = withConnection("/agent/command/poll", "GET") { conn ->
        val body = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(body)
        if (!json.optBoolean("ok", false)) {
            Result.failure(Exception(json.optString("error", "Hermes error")))
        } else {
            val data = json.optJSONObject("data")
            if (data == null || data.length() == 0) Result.success(null)
            else Result.success(BrowserCommand.fromJson(data))
        }
    }

    private fun <T> withConnection(
        path: String,
        method: String,
        writeBody: ((HttpURLConnection) -> Unit)? = null,
        block: (HttpURLConnection) -> Result<T>
    ): Result<T> {
        if (!HermesConfig.enabled) return Result.failure(Exception("Hermes disabled"))
        val url = URL(HermesConfig.baseUrl + path)
        var conn: HttpURLConnection? = null
        return try {
            // 本地回环直接连接，绕过系统全局 HTTP 代理
            conn = (url.openConnection(Proxy.NO_PROXY) as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = TIMEOUT
                readTimeout = TIMEOUT
                setRequestProperty(HEADER_VERSION, API_VERSION)
                if (HermesConfig.token.isNotBlank()) {
                    setRequestProperty(HEADER_TOKEN, HermesConfig.token)
                }
                doInput = true
                if (method == "POST") doOutput = true
                writeBody?.invoke(this)
            }
            val code = conn.responseCode
            if (code in 200..299) {
                block(conn)
            } else {
                val err = try { conn.errorStream?.bufferedReader()?.readText() } catch (_: Exception) { null }
                Result.failure(Exception("HTTP $code ${err ?: ""}"))
            }
        } catch (e: Exception) {
            AppLogger.e("HERMES_API", "$method $path failed: ${e.message}", e)
            Result.failure(e)
        } finally {
            conn?.disconnect()
        }
    }
}
