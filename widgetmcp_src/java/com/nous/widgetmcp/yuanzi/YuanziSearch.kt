package com.nous.widgetmcp.yuanzi

import org.json.JSONObject

/**
 * Yuanzi /search 端点返回的单条语义搜索结果（M5 任务 5.4）。
 */
data class YuanziSearchResult(
    val atomId: String,
    val functionName: String,
    val text: String,
    val score: Double,
    val atomName: String,
    val status: String,
    val category: String,
) {
    companion object {
        fun fromJson(json: JSONObject) = YuanziSearchResult(
            atomId = json.optString("atom_id"),
            functionName = json.optString("function_name"),
            text = json.optString("text"),
            score = json.optDouble("score"),
            atomName = json.optString("atom_name"),
            status = json.optString("status"),
            category = json.optString("category"),
        )
    }
}
