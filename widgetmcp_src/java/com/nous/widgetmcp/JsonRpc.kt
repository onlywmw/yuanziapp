package com.nous.widgetmcp

import org.json.JSONObject

data class JsonRpcRequest(
    val jsonrpc: String = "2.0",
    val method: String,
    val params: JSONObject? = null,
    val id: String? = null
) {
    fun isNotification(): Boolean = id == null

    companion object {
        fun fromJson(json: String): JsonRpcRequest? {
            return try {
                val obj = JSONObject(json)
                JsonRpcRequest(
                    obj.optString("jsonrpc", "2.0"),
                    obj.getString("method"),
                    obj.optJSONObject("params"),
                    obj.optString("id", null)
                )
            } catch (_: Exception) { null }
        }
    }
}

data class JsonRpcResponse(
    val jsonrpc: String = "2.0",
    val result: Any? = null,
    val error: RpcError? = null,
    val id: String? = null
) {
    fun toJson(): String {
        val obj = JSONObject()
        obj.put("jsonrpc", jsonrpc)
        if (result != null) obj.put("result", result)
        if (error != null) {
            val err = JSONObject()
            err.put("code", error.code)
            err.put("message", error.message)
            obj.put("error", err)
        }
        if (id != null) obj.put("id", id)
        return obj.toString()
    }

    companion object {
        fun success(id: String?, result: Any) = JsonRpcResponse(id = id, result = result)
        fun error(id: String?, code: Int, message: String) = JsonRpcResponse(id = id, error = RpcError(code, message))
    }
}

data class RpcError(val code: Int, val message: String)
