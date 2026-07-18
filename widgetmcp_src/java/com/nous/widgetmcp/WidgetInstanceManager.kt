package com.nous.widgetmcp

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.util.UUID

class WidgetInstanceManager(private val context: Context) {

    companion object {
        @Volatile var instance: WidgetInstanceManager? = null; private set
        fun init(context: Context) { if (instance == null) instance = WidgetInstanceManager(context) }
    }

    private val dbHelper = object : SQLiteOpenHelper(context, "widget_instances.db", null, 3) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("""
                CREATE TABLE IF NOT EXISTS widget_instances (
                    widgetId INTEGER PRIMARY KEY,
                    typeId TEXT NOT NULL,
                    dataSourceId TEXT NOT NULL DEFAULT '',
                    refreshInterval INTEGER NOT NULL DEFAULT 900000,
                    createdAt INTEGER NOT NULL,
                    lastUpdated INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'UI',
                    credentialRef TEXT,
                    lastError TEXT,
                    hermesId TEXT
                )
            """)
        }
        override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) {
            if (old < 2) {
                db.execSQL("ALTER TABLE widget_instances ADD COLUMN source TEXT NOT NULL DEFAULT 'UI'")
                db.execSQL("ALTER TABLE widget_instances ADD COLUMN credentialRef TEXT")
                db.execSQL("ALTER TABLE widget_instances ADD COLUMN lastError TEXT")
            }
            if (old < 3) {
                db.execSQL("ALTER TABLE widget_instances ADD COLUMN hermesId TEXT")
            }
        }
    }

    fun save(config: WidgetConfig) {
        val cv = ContentValues().apply {
            put("widgetId", config.widgetId)
            put("typeId", config.typeId)
            put("dataSourceId", config.dataSourceId)
            put("refreshInterval", config.refreshInterval)
            put("createdAt", config.createdAt)
            put("lastUpdated", config.lastUpdated)
            put("source", config.source.name)
            config.credentialRef?.let { put("credentialRef", it) }
            config.lastError?.let { put("lastError", it) }
            config.hermesId?.let { put("hermesId", it) }
        }
        dbHelper.writableDatabase.insertWithOnConflict("widget_instances", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun get(widgetId: Int): WidgetConfig? {
        return dbHelper.readableDatabase.query("widget_instances", null,
            "widgetId=?", arrayOf(widgetId.toString()), null, null, null).use { c ->
            if (c.moveToFirst()) WidgetConfig(
                widgetId = c.getInt(c.getColumnIndexOrThrow("widgetId")),
                typeId = c.getString(c.getColumnIndexOrThrow("typeId")),
                dataSourceId = c.getString(c.getColumnIndexOrThrow("dataSourceId")),
                refreshInterval = c.getLong(c.getColumnIndexOrThrow("refreshInterval")),
                createdAt = c.getLong(c.getColumnIndexOrThrow("createdAt")),
                lastUpdated = c.getLong(c.getColumnIndexOrThrow("lastUpdated")),
                source = try { WidgetSource.valueOf(c.getString(c.getColumnIndexOrThrow("source"))) } catch (_: Exception) { WidgetSource.UI },
                credentialRef = c.getString(c.getColumnIndexOrThrow("credentialRef")),
                lastError = c.getString(c.getColumnIndexOrThrow("lastError")),
                hermesId = c.getString(c.getColumnIndexOrThrow("hermesId"))
            ) else null
        }
    }

    fun list(): List<WidgetConfig> {
        val result = mutableListOf<WidgetConfig>()
        dbHelper.readableDatabase.query("widget_instances", null, null, null, null, null, null).use { c ->
            while (c.moveToNext()) result.add(WidgetConfig(
                widgetId = c.getInt(c.getColumnIndexOrThrow("widgetId")),
                typeId = c.getString(c.getColumnIndexOrThrow("typeId")),
                dataSourceId = c.getString(c.getColumnIndexOrThrow("dataSourceId")),
                refreshInterval = c.getLong(c.getColumnIndexOrThrow("refreshInterval")),
                createdAt = c.getLong(c.getColumnIndexOrThrow("createdAt")),
                lastUpdated = c.getLong(c.getColumnIndexOrThrow("lastUpdated")),
                source = try { WidgetSource.valueOf(c.getString(c.getColumnIndexOrThrow("source"))) } catch (_: Exception) { WidgetSource.UI },
                credentialRef = c.getString(c.getColumnIndexOrThrow("credentialRef")),
                lastError = c.getString(c.getColumnIndexOrThrow("lastError")),
                hermesId = c.getString(c.getColumnIndexOrThrow("hermesId"))
            ))
        }
        return result
    }

    fun delete(widgetId: Int) {
        dbHelper.writableDatabase.delete("widget_instances", "widgetId=?", arrayOf(widgetId.toString()))
    }
}
