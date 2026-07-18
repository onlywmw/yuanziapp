package com.nous.widgetmcp

import android.content.Context
import android.content.Intent
import android.widget.RemoteViews

data class WidgetSize(val width: Int, val height: Int) {
    companion object {
        val SMALL = WidgetSize(2, 1)
        val MEDIUM = WidgetSize(4, 2)
        val LARGE = WidgetSize(4, 4)
    }
}

interface WidgetType {
    val typeId: String
    val displayName: String
    val description: String
    val defaultSize: WidgetSize
    val supportedSizes: List<WidgetSize>
    fun createConfigIntent(context: Context): Intent
    fun render(context: Context, config: WidgetConfig, data: WidgetData): RemoteViews
}
