package com.nous.widgetmcp.yuanzi

import org.json.JSONObject

/**
 * Yuanzi /agent/widgets 返回的 widget 数据模型
 *
 * Yuanzi 主库存的是字符串 widget_id、type、config_json。
 * 这里映射到 Android 侧可渲染的数据。
 */
data class YuanziWidget(
    val widgetId: String,
    val type: String,
    val status: String,
    val config: YuanziWidgetConfig,
    val lastError: String? = null,
    val updatedAt: String? = null
) {
    companion object {
        fun fromJson(obj: JSONObject): YuanziWidget {
            val configJson = obj.optJSONObject("config") ?: JSONObject()
            return YuanziWidget(
                widgetId = obj.getString("widget_id"),
                type = obj.getString("type"),
                status = obj.optString("status", "pending"),
                config = YuanziWidgetConfig.fromJson(configJson),
                lastError = obj.optionalString("last_error"),
                updatedAt = obj.optionalString("updated_at")
            )
        }
    }
}

/**
 * Yuanzi widget 的 config 字段。
 * 设计约定：
 * - title / subtitle: 通用标题
 * - value / unit: 数值型数据
 * - items: 列表型数据
 * - data_source_id: 数据源标识（如 deepseek）
 * - credential_ref: 凭据引用
 * - refresh_interval_ms: 刷新间隔
 * - display: 显示配置（颜色、尺寸等）
 */
data class YuanziWidgetConfig(
    val title: String? = null,
    val subtitle: String? = null,
    val value: Double? = null,
    val unit: String? = null,
    val content: String? = null,
    val items: List<YuanziListItem> = emptyList(),
    val dataSourceId: String? = null,
    val credentialRef: String? = null,
    val refreshIntervalMs: Long = 60_000L,
    val display: Map<String, String> = emptyMap()
) {
    companion object {
        fun fromJson(obj: JSONObject): YuanziWidgetConfig {
            val items = mutableListOf<YuanziListItem>()
            val arr = obj.optJSONArray("items")
            if (arr != null) {
                for (i in 0 until arr.length()) {
                    items.add(YuanziListItem.fromJson(arr.getJSONObject(i)))
                }
            }
            val display = mutableMapOf<String, String>()
            val displayObj = obj.optJSONObject("display")
            if (displayObj != null) {
                val keys = displayObj.keys()
                while (keys.hasNext()) {
                    val k = keys.next()
                    display[k] = displayObj.getString(k)
                }
            }

            return YuanziWidgetConfig(
                title = obj.optionalString("title"),
                subtitle = obj.optionalString("subtitle"),
                value = if (obj.has("value")) obj.getDouble("value") else null,
                unit = obj.optionalString("unit"),
                content = obj.optionalString("content"),
                items = items,
                dataSourceId = obj.optionalString("data_source_id"),
                credentialRef = obj.optionalString("credential_ref"),
                refreshIntervalMs = obj.optLong("refresh_interval_ms", 60_000L),
                display = display
            )
        }
    }
}

data class YuanziListItem(
    val title: String,
    val subtitle: String? = null,
    val value: String? = null
) {
    companion object {
        fun fromJson(obj: JSONObject): YuanziListItem = YuanziListItem(
            title = obj.optString("title", ""),
            subtitle = obj.optionalString("subtitle"),
            value = obj.optionalString("value")
        )
    }
}

private fun JSONObject.optionalString(name: String): String? {
    return if (has(name)) getString(name) else null
}

/**
 * 上报 Yuanzi 的事件模型
 */
data class YuanziEvent(
    val source: String,
    val toolId: String? = null,
    val args: Map<String, Any> = emptyMap(),
    val result: Map<String, Any> = emptyMap(),
    val status: String = "success"
) {
    fun toJson(): String {
        val argsObj = org.json.JSONObject()
        args.forEach { (k, v) -> argsObj.put(k, v) }
        val resultObj = org.json.JSONObject()
        result.forEach { (k, v) -> resultObj.put(k, v) }
        return org.json.JSONObject().apply {
            put("source", source)
            put("tool_id", toolId)
            put("args", argsObj)
            put("result", resultObj)
            put("status", status)
        }.toString()
    }
}
