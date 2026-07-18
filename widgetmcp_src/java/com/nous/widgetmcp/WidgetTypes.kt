package com.nous.widgetmcp

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.RemoteViews

class ObsidianCardWidget : WidgetType {
    override val typeId = "obsidian-card"
    override val displayName = "Obsidian 卡片"
    override val description = "展示 Obsidian 笔记内容"
    override val defaultSize = WidgetSize.MEDIUM
    override val supportedSizes = listOf(WidgetSize.SMALL, WidgetSize.MEDIUM, WidgetSize.LARGE)

    override fun createConfigIntent(context: Context) =
        Intent(context, MainActivity::class.java)

    override fun render(context: Context, config: WidgetConfig, data: WidgetData): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.widget_card_list)

        return when (data) {
            is WidgetData.Markdown -> {
                val title = data.raw.lines().firstOrNull()?.removePrefix("#")?.trim() ?: ""
                views.setTextViewText(R.id.widget_title, title)
                views
            }
            else -> {
                views.setTextViewText(R.id.widget_title, config.dataSourceId)
                views
            }
        }
    }
}

class BalanceWidget : WidgetType {
    override val typeId = "balance"
    override val displayName = "余额卡片"
    override val description = "展示账户余额"
    override val defaultSize = WidgetSize.SMALL
    override val supportedSizes = listOf(WidgetSize.SMALL, WidgetSize.MEDIUM)

    override fun createConfigIntent(context: Context) =
        Intent(context, MainActivity::class.java)

    override fun render(context: Context, config: WidgetConfig, data: WidgetData): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.widget_balance)

        return when (data) {
            is WidgetData.Number -> {
                views.setTextViewText(R.id.balance_amount, "\u00A5 %.2f".format(data.value))
                views.setTextViewText(R.id.balance_status, "正常")
                views.setInt(R.id.balance_status, "setBackgroundResource", R.drawable.chip_sage)
                views.setTextColor(R.id.balance_status, 0xFF5F7355.toInt())
                views
            }
            else -> {
                views.setTextViewText(R.id.balance_amount, "--")
                views.setTextViewText(R.id.balance_status, "暂无数据")
                views.setInt(R.id.balance_status, "setBackgroundResource", R.drawable.chip_amber)
                views.setTextColor(R.id.balance_status, 0xFF9C7326.toInt())
                views
            }
        }
    }
}

class TextWidget : WidgetType {
    override val typeId = "text"
    override val displayName = "文本卡片"
    override val description = "展示纯文本内容"
    override val defaultSize = WidgetSize.SMALL
    override val supportedSizes = listOf(WidgetSize.SMALL, WidgetSize.MEDIUM)

    override fun createConfigIntent(context: Context) =
        Intent(context, MainActivity::class.java)

    override fun render(context: Context, config: WidgetConfig, data: WidgetData): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.widget_single_card)

        return when (data) {
            is WidgetData.Text -> {
                views.setTextViewText(R.id.card_source, config.dataSourceId)
                views.setTextViewText(R.id.card_body, data.content)
                views
            }
            else -> {
                views.setTextViewText(R.id.card_source, config.typeId)
                views.setTextViewText(R.id.card_body, "")
                views
            }
        }
    }
}
