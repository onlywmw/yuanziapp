package com.nous.widgetmcp.hermes

import org.json.JSONObject

/**
 * Hermes /graph 端点返回的拓扑结构
 */
data class GraphTopology(
    val nodes: List<Node>,
    val edges: List<Edge>
) {
    data class Node(
        val id: String,
        val label: String,
        val type: String,
        val status: String?,
        val endpoint: String?,
        val capabilities: List<String>
    ) {
        companion object {
            fun fromJson(json: JSONObject): Node = Node(
                id = json.optString("id", ""),
                label = json.optString("label", ""),
                type = json.optString("type", ""),
                status = json.optString("status", null),
                endpoint = json.optString("endpoint", null),
                capabilities = json.optJSONArray("capabilities")?.let { arr ->
                    List(arr.length()) { arr.optString(it, "") }
                } ?: emptyList()
            )
        }
    }

    data class Edge(
        val source: String,
        val target: String,
        val label: String?
    ) {
        companion object {
            fun fromJson(json: JSONObject): Edge = Edge(
                source = json.optString("source", ""),
                target = json.optString("target", ""),
                label = json.optString("label", null)
            )
        }
    }
}
