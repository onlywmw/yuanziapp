package com.nous.widgetmcp

import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

class McpServer(port: Int) : NanoHTTPD("127.0.0.1", port) {

    private fun ctrl() = ServiceLocator.controller

    override fun serve(session: IHTTPSession): Response {
        val uri = session.uri

        // === REST 路由 ===
        if (uri.startsWith("/api/")) return serveRest(session, uri)

        // === MCP JSON-RPC 路由 ===
        return serveMcp(session)
    }

    // ==================== MCP ====================

    private fun serveMcp(session: IHTTPSession): Response {
        if (!checkToken(session)) return jsonResponse(Response.Status.UNAUTHORIZED, "Unauthorized")
        if (session.method != Method.POST) return jsonError(null, -32700, "POST only")

        session.parseBody(mapOf())
        val body = session.queryParameterString ?: ""

        return try {
            val trimmed = body.trim()
            if (trimmed.startsWith("[")) {
                val arr = JSONArray(trimmed)
                val results = JSONArray()
                for (i in 0 until arr.length())
                    results.put(process(arr.getJSONObject(i).toString()))
                jsonOk(results.toString())
            } else {
                val req = JsonRpcRequest.fromJson(trimmed)
                if (req != null && req.isNotification()) {
                    Thread { try { handle(req) } catch (_: Exception) {} }.start()
                    newFixedLengthResponse(Response.Status.NO_CONTENT, "text/plain", "")
                } else jsonOk(process(trimmed))
            }
        } catch (e: Exception) {
            jsonOk(JsonRpcResponse.error(null, -32700, "Parse error").toJson())
        }
    }

    // ==================== REST ====================

    private fun serveRest(session: IHTTPSession, uri: String): Response {
        when {
            uri == "/api/health" && session.method == Method.GET -> {
                return jsonOk(JSONObject(ctrl().health()).toString())
            }
            uri == "/api/widgets" && session.method == Method.GET -> {
                if (!checkToken(session)) return jsonResponse(Response.Status.UNAUTHORIZED, "Unauthorized")
                val list = ctrl().list().map { c ->
                    JSONObject().apply {
                        put("widgetId", c.widgetId)
                        put("typeId", c.typeId)
                        put("dataSourceId", c.dataSourceId)
                        put("source", c.source.name)
                        put("lastUpdated", c.lastUpdated)
                    }
                }
                return jsonOk(JSONArray(list).toString())
            }
            uri == "/api/widgets" && session.method == Method.POST -> {
                if (!checkToken(session)) return jsonResponse(Response.Status.UNAUTHORIZED, "Unauthorized")
                session.parseBody(mapOf())
                val body = session.queryParameterString ?: "{}"
                val params = JSONObject(body)
                val id = ctrl().create(
                    params.optString("typeId", ""),
                    params.optString("dataSourceId", ""),
                    WidgetSource.API
                )
                return jsonOk(JSONObject().apply { put("widgetId", id); put("status", "created") }.toString())
            }
            uri.matches(Regex("/api/widgets/\\d+")) && session.method == Method.DELETE -> {
                if (!checkToken(session)) return jsonResponse(Response.Status.UNAUTHORIZED, "Unauthorized")
                val widgetId = uri.substringAfterLast("/").toIntOrNull() ?: return jsonResponse(Response.Status.BAD_REQUEST, "Invalid ID")
                ctrl().delete(widgetId)
                return jsonOk(JSONObject().apply { put("status", "deleted"); put("widgetId", widgetId) }.toString())
            }
            else -> return jsonResponse(Response.Status.NOT_FOUND, "Not Found")
        }
    }

    // ==================== MCP methods ====================

    private fun process(json: String): String {
        val req = JsonRpcRequest.fromJson(json)
        if (req == null) return JsonRpcResponse.error(null, -32700, "Parse error").toJson()
        return try {
            JsonRpcResponse.success(req.id, handle(req)).toJson()
        } catch (e: JsonRpcException) {
            JsonRpcResponse.error(req.id, e.rpcCode, e.message ?: "Error").toJson()
        } catch (e: Exception) {
            JsonRpcResponse.error(req.id, -32000, e.message ?: "Internal error").toJson()
        }
    }

    private fun handle(req: JsonRpcRequest): Any {
        val params = req.params ?: JSONObject()
        return when (req.method) {
            "widget.list" -> mapOf("widgets" to ctrl().list().map { c ->
                mapOf("widgetId" to c.widgetId, "typeId" to c.typeId,
                    "typeName" to (WidgetRegistry.get(c.typeId)?.displayName ?: c.typeId),
                    "dataSourceId" to c.dataSourceId, "lastUpdated" to c.lastUpdated)
            }, "count" to ctrl().list().size)

            "widget.types" -> mapOf("types" to ctrl().types())

            "widget.create" -> {
                val id = ctrl().create(params.optString("typeId", ""), params.optString("dataSourceId", ""), WidgetSource.MCP)
                mapOf("widgetId" to id, "status" to "created")
            }

            "widget.update" -> {
                val widgetId = params.optInt("widgetId", -1)
                if (widgetId < 0) throw JsonRpcException(-32602, "Missing widgetId")
                val data = parseData(params.optJSONObject("data") ?: JSONObject())
                WidgetRenderer.pushAndRefresh(ServiceLocator.app, widgetId, data)
                mapOf("status" to "updated", "widgetId" to widgetId)
            }

            "widget.delete" -> {
                val widgetId = params.optInt("widgetId", -1)
                if (widgetId < 0) throw JsonRpcException(-32602, "Missing widgetId")
                ctrl().delete(widgetId)
                mapOf("status" to "deleted", "widgetId" to widgetId)
            }

            "widget.configure" -> {
                val widgetId = params.optInt("widgetId", -1)
                if (widgetId < 0) throw JsonRpcException(-32602, "Missing widgetId")
                ctrl().configure(widgetId,
                    params.optString("dataSourceId", "").ifEmpty { null },
                    if (params.has("refreshInterval")) params.optLong("refreshInterval") else null)
                mapOf("status" to "configured", "widgetId" to widgetId)
            }

            "system.health" -> ctrl().health()

            else -> throw JsonRpcException(-32601, "Method not found: ${req.method}")
        }
    }

    // ==================== helpers ====================

    private fun checkToken(session: IHTTPSession): Boolean {
        val prefs = ServiceLocator.app.getSharedPreferences("widget_mcp", android.content.Context.MODE_PRIVATE)
        val token = prefs.getString("mcp_token", "") ?: ""
        if (token.isBlank()) return true
        val auth = session.headers["authorization"] ?: return false
        val provided = auth.removePrefix("Bearer ").trim()
        return MessageDigest.isEqual(provided.toByteArray(), token.toByteArray())
    }

    private fun parseData(data: JSONObject): WidgetData {
        return when (data.optString("type", "text")) {
            "text" -> WidgetData.Text(data.optString("content", ""))
            "number" -> WidgetData.Number(data.optDouble("value", 0.0), data.optString("unit", null))
            else -> WidgetData.Text(data.toString())
        }
    }

    private fun jsonOk(body: String) = newFixedLengthResponse(Response.Status.OK, "application/json", body)
    private fun jsonResponse(status: Response.IStatus, body: String) = newFixedLengthResponse(status, "text/plain", body)
    private fun jsonError(id: String?, code: Int, msg: String) = jsonOk(JsonRpcResponse.error(id, code, msg).toJson())
}
