package com.nous.widgetmcp

import android.content.Context

class DataSourceManager(private val context: Context) {
    private val sources = mutableMapOf<String, DataSource>()

    fun register(source: DataSource) { sources[source.id] = source }
    fun get(id: String): DataSource? = sources[id]
    fun remove(id: String) { sources.remove(id) }

    fun refreshAll(callback: (sourceId: String, data: WidgetData) -> Unit) {
        sources.values.forEach { source ->
            if (source.isValid()) {
                source.fetchData().getOrNull()?.let { data ->
                    callback(source.id, data)
                }
            }
        }
    }
}
