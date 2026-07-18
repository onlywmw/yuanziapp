package com.nous.widgetmcp

enum class WidgetSource { UI, MCP, API, CLI, YUANZI }
enum class Freshness { FRESH, STALE, ERROR }

data class DisplayConfig(
    val theme: String = "auto",
    val fontSize: Int = 14,
    val cornerRadius: Int = 16,
    val cardBackground: String? = null
)

data class WidgetConfig(
    val widgetId: Int,
    val typeId: String,
    val dataSourceId: String,
    val displayConfig: DisplayConfig = DisplayConfig(),
    val refreshInterval: Long = 15 * 60 * 1000,
    val createdAt: Long = System.currentTimeMillis(),
    val lastUpdated: Long = 0,
    val source: WidgetSource = WidgetSource.UI,
    val credentialRef: String? = null,
    val lastError: String? = null,
    val yuanziId: String? = null
) {
    fun toJson(): String {
        val sb = StringBuilder("{")
        sb.append("\"widgetId\":$widgetId,")
        sb.append("\"typeId\":\"$typeId\",")
        sb.append("\"dataSourceId\":\"$dataSourceId\",")
        sb.append("\"refreshInterval\":$refreshInterval,")
        sb.append("\"createdAt\":$createdAt,")
        sb.append("\"lastUpdated\":$lastUpdated,")
        sb.append("\"source\":\"${source.name}\",")
        credentialRef?.let { sb.append("\"credentialRef\":\"$it\",") }
        lastError?.let { sb.append("\"lastError\":\"$it\",") }
        yuanziId?.let { sb.append("\"yuanziId\":\"$it\",") }
        sb.append("\"_\":0}")
        return sb.toString()
    }

    companion object {
        fun fromJson(json: String): WidgetConfig? {
            return try {
                val obj = org.json.JSONObject(json)
                WidgetConfig(
                    widgetId = obj.getInt("widgetId"),
                    typeId = obj.getString("typeId"),
                    dataSourceId = obj.getString("dataSourceId"),
                    refreshInterval = obj.optLong("refreshInterval", 15 * 60 * 1000),
                    createdAt = obj.optLong("createdAt"),
                    lastUpdated = obj.optLong("lastUpdated"),
                    source = try { WidgetSource.valueOf(obj.optString("source", "UI")) } catch (_: Exception) { WidgetSource.UI },
                    credentialRef = obj.optString("credentialRef", null),
                    lastError = obj.optString("lastError", null),
                    yuanziId = obj.optString("yuanziId", null)
                )
            } catch (_: Exception) { null }
        }
    }
}
