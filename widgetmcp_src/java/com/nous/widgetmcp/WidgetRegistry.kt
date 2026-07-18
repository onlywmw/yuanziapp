package com.nous.widgetmcp

object WidgetRegistry {
    private val types: Map<String, WidgetType> by lazy {
        linkedMapOf(
            "balance" to BalanceWidget(),
            "obsidian-card" to ObsidianCardWidget(),
            "text" to TextWidget()
        )
    }

    fun get(typeId: String): WidgetType? = types[typeId]
    fun getAll(): Collection<WidgetType> = types.values
}
