package com.nous.widgetmcp.yuanzi

import com.nous.widgetmcp.AppLogger
import com.nous.widgetmcp.browser.BrowserCommand
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.Proxy
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.Charset

/**
 * Yuanzi HTTP 客户端
 *
 * 默认访问 127.0.0.1:8080，所有请求携带 Yuanzi-API: v1 版本头。
 * 如配置了 token，额外携带 Yuanzi-Token。
 */
object YuanziApi {
    private const val API_VERSION = "v1"
    private const val HEADER_VERSION = "Yuanzi-API"
    private const val HEADER_TOKEN = "Yuanzi-Token"
    private const val TIMEOUT = 15_000

    fun fetchWidgets(): Result<List<YuanziWidget>> = withConnection("/agent/widgets", "GET") { conn ->
        val body = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(body)
        if (json.optBoolean("ok", false)) {
            val data = json.optJSONArray("data") ?: JSONArray()
            val list = mutableListOf<YuanziWidget>()
            for (i in 0 until data.length()) {
                list.add(YuanziWidget.fromJson(data.getJSONObject(i)))
            }
            Result.success(list)
        } else {
            Result.failure(Exception(json.optString("error", "Yuanzi error")))
        }
    }

    fun reportEvent(event: YuanziEvent): Result<JSONObject> = withConnection(
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
            Result.failure(Exception(json.optString("error", "Yuanzi error")))
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
            Result.failure(Exception(json.optString("error", "Yuanzi error")))
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

    /** 语义搜索原子功能（M5 任务 5.4），对应注册中心 GET /search。 */
    fun searchAtoms(query: String, limit: Int = 10): Result<List<YuanziSearchResult>> = withConnection(
        "/search?q=" + URLEncoder.encode(query, "UTF-8") + "&limit=" + limit,
        "GET"
    ) { conn ->
        val body = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(body)
        val results = json.optJSONArray("results") ?: JSONArray()
        val list = mutableListOf<YuanziSearchResult>()
        for (i in 0 until results.length()) {
            list.add(YuanziSearchResult.fromJson(results.getJSONObject(i)))
        }
        Result.success(list)
    }

    fun pollCommand(): Result<BrowserCommand?> = withConnection("/agent/command/poll", "GET") { conn ->
        val body = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(body)
        if (!json.optBoolean("ok", false)) {
            Result.failure(Exception(json.optString("error", "Yuanzi error")))
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
        if (!YuanziConfig.enabled) return Result.failure(Exception("Yuanzi disabled"))
        val url = URL(YuanziConfig.baseUrl + path)
        var conn: HttpURLConnection? = null
        return try {
            // 本地回环直接连接，绕过系统全局 HTTP 代理
            conn = (url.openConnection(Proxy.NO_PROXY) as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = TIMEOUT
                readTimeout = TIMEOUT
                setRequestProperty(HEADER_VERSION, API_VERSION)
                if (YuanziConfig.token.isNotBlank()) {
                    setRequestProperty(HEADER_TOKEN, YuanziConfig.token)
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
            AppLogger.e("YUANZI_API", "$method $path failed: ${e.message}", e)
            Result.failure(e)
        } finally {
            conn?.disconnect()
        }
    }
}
