package com.nous.widgetmcp.browser

import org.json.JSONObject

/**
 * 浏览器上报 Yuanzi 的事件模型
 */
data class BrowserEvent(
    val source: String = "app",
    val toolId: String,
    val args: Map<String, Any> = emptyMap(),
    val result: Map<String, Any> = emptyMap(),
    val status: String = "success"
) {
    fun toJson(): String {
        val argsObj = JSONObject()
        args.forEach { (k, v) -> argsObj.put(k, v) }
        val resultObj = JSONObject()
        result.forEach { (k, v) -> resultObj.put(k, v) }
        return JSONObject().apply {
            put("source", source)
            put("tool_id", toolId)
            put("args", argsObj)
            put("result", resultObj)
            put("status", status)
        }.toString()
    }
}

/**
 * Yuanzi 下发的浏览器命令
 */
data class BrowserCommand(
    val eventId: Int,
    val toolId: String,
    val args: Map<String, Any>
) {
    companion object {
        fun fromJson(obj: JSONObject): BrowserCommand {
            val args = mutableMapOf<String, Any>()
            val argsObj = obj.optJSONObject("args")
            if (argsObj != null) {
                val keys = argsObj.keys()
                while (keys.hasNext()) {
                    val k = keys.next()
                    args[k] = argsObj.get(k)
                }
            }
            return BrowserCommand(
                eventId = obj.optInt("event_id", -1),
                toolId = obj.getString("tool_id"),
                args = args
            )
        }
    }
}
