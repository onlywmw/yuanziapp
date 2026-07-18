package com.nous.widgetmcp

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/**
 * [P0-2 修复] Widget 状态持久化 — 替代 DataBus
 *
 * DataBus 只能在同一进程内通信, AppWidgetProvider 和 McpService
 * 可能在不同生命周期上下文, DataBus 不可靠。
 *
 * 改为 SQLite 持久化: MCP 写入 → Provider 读取 → 渲染。
 *
 * 表结构:
 *   widget_state(widgetId INTEGER PRIMARY KEY, dataType TEXT, content TEXT, raw TEXT, value REAL, unit TEXT)
 */
class WidgetStateStore private constructor(context: Context) {

    companion object {
        private var instance: WidgetStateStore? = null

        fun init(context: Context) {
            if (instance == null) instance = WidgetStateStore(context)
        }

        fun get(widgetId: Int): WidgetData? = instance?.load(widgetId)
        fun put(widgetId: Int, data: WidgetData) = instance?.save(widgetId, data)
    }

    private val dbHelper = object : SQLiteOpenHelper(context, "widget_state.db", null, 1) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("""
                CREATE TABLE IF NOT EXISTS widget_state (
                    widgetId INTEGER PRIMARY KEY,
                    dataType TEXT NOT NULL,
                    content TEXT,
                    raw TEXT,
                    value REAL,
                    unit TEXT,
                    updatedAt INTEGER NOT NULL
                )
            """)
        }
        override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) {}
    }

    fun save(widgetId: Int, data: WidgetData) {
        val db = dbHelper.writableDatabase
        val cv = ContentValues().apply {
            put("widgetId", widgetId)
            put("updatedAt", System.currentTimeMillis())
        }
        when (data) {
            is WidgetData.Text -> {
                cv.put("dataType", "text")
                cv.put("content", data.content)
            }
            is WidgetData.Markdown -> {
                cv.put("dataType", "markdown")
                cv.put("raw", data.raw)
                cv.put("content", data.rendered)
            }
            is WidgetData.Number -> {
                cv.put("dataType", "number")
                cv.put("value", data.value)
                cv.put("unit", data.unit)
            }
            is WidgetData.ListItems -> {
                cv.put("dataType", "list")
                cv.put("content", data.items.joinToString("|") { "${it.title};;${it.subtitle};;${it.value}" })
            }
        }
        db.insertWithOnConflict("widget_state", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun load(widgetId: Int): WidgetData? {
        val db = dbHelper.readableDatabase
        val c = db.query("widget_state", null, "widgetId=?", arrayOf(widgetId.toString()), null, null, null)
        val result = if (c.moveToFirst()) {
            val type = c.getString(c.getColumnIndexOrThrow("dataType"))
            when (type) {
                "text" -> WidgetData.Text(
                    c.getString(c.getColumnIndexOrThrow("content")) ?: ""
                )
                "markdown" -> WidgetData.Markdown(
                    c.getString(c.getColumnIndexOrThrow("raw")) ?: "",
                    c.getString(c.getColumnIndexOrThrow("content")) ?: ""
                )
                "number" -> WidgetData.Number(
                    c.getDouble(c.getColumnIndexOrThrow("value")),
                    c.getString(c.getColumnIndexOrThrow("unit"))
                )
                "list" -> {
                    val raw = c.getString(c.getColumnIndexOrThrow("content")) ?: ""
                    val items = raw.split("|").mapNotNull { part ->
                        val parts = part.split(";;")
                        if (parts.size >= 3) ListItem(parts[0], parts[1], parts[2]) else null
                    }
                    WidgetData.ListItems(items)
                }
                else -> null
            }
        } else null
        c.close()
        return result
    }
}
