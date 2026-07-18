package com.nous.widgetmcp.domain.usecase

import com.nous.widgetmcp.*
import com.nous.widgetmcp.domain.contract.WidgetRepository
import java.util.UUID

class WidgetController(private val repo: WidgetRepository) {

    fun create(typeId: String, dataSourceId: String, source: WidgetSource = WidgetSource.UI,
               credentialRef: String? = null): Int {
        require(WidgetRegistry.get(typeId) != null) { "Unknown type: $typeId" }
        val id = generateId()
        repo.saveConfig(WidgetConfig(widgetId = id, typeId = typeId, dataSourceId = dataSourceId,
            source = source, credentialRef = credentialRef))
        return id
    }

    fun push(widgetId: Int, data: WidgetData) {
        val config = repo.getConfig(widgetId) ?: throw IllegalStateException("Not found: $widgetId")
        repo.saveState(widgetId, data)
        repo.saveConfig(config.copy(lastUpdated = System.currentTimeMillis(), lastError = null))
    }

    data class WidgetSnapshot(val config: WidgetConfig, val data: WidgetData) {
        val freshness: Freshness get() {
            if (config.lastError != null) return Freshness.ERROR
            val age = System.currentTimeMillis() - config.lastUpdated
            return if (age > config.refreshInterval * 3) Freshness.STALE else Freshness.FRESH
        }
    }

    fun snapshot(widgetId: Int): WidgetSnapshot? {
        val config = repo.getConfig(widgetId) ?: return null
        val data = repo.getState(widgetId) ?: WidgetData.Text("")
        return WidgetSnapshot(config, data)
    }

    fun delete(widgetId: Int) = repo.deleteConfig(widgetId)

    fun configure(widgetId: Int, dataSourceId: String?, refreshInterval: Long?) {
        val c = repo.getConfig(widgetId) ?: return
        repo.saveConfig(c.copy(
            dataSourceId = dataSourceId ?: c.dataSourceId,
            refreshInterval = refreshInterval ?: c.refreshInterval))
    }

    fun list(): List<WidgetConfig> = repo.listConfigs()

    /** 列出所有可用模板类型 */
    fun types(): List<Map<String, Any>> = WidgetRegistry.getAll().map { wt ->
        mapOf(
            "typeId" to wt.typeId,
            "displayName" to wt.displayName,
            "description" to wt.description
        )
    }

    /** 测试数据源连通性 */
    fun test(typeId: String, credentialId: String): Result<WidgetData> {
        WidgetRegistry.get(typeId) ?: return Result.failure(IllegalArgumentException("Unknown: $typeId"))
        return when (typeId) {
            "balance" -> {
                val key = CredentialStore.get(credentialId, "api_key")
                    ?: return Result.failure(IllegalStateException("凭据未找到"))
                try {
                    val svc = DeepSeekService(key)
                    val balance = svc.fetchBalance()
                        ?: return Result.failure(Exception("余额数据为空"))
                    Result.success(WidgetData.Number(value = balance.totalBalance.toDoubleOrNull() ?: 0.0, unit = "CNY"))
                } catch (e: Exception) {
                    Result.failure(e)
                }
            }
            else -> Result.failure(UnsupportedOperationException("$typeId 不支持测试"))
        }
    }

    fun health(): Map<String, Any> = mapOf(
        "status" to "ok",
        "templates" to WidgetRegistry.getAll().size,
        "instances" to list().size,
        "uptime_ms" to (System.currentTimeMillis() - ServiceLocator.bootTime)
    )

    private fun generateId(): Int {
        val existing = repo.listConfigs().map { it.widgetId }.toSet()
        var id: Int
        do { id = UUID.randomUUID().hashCode() and Int.MAX_VALUE } while (id in existing)
        return id
    }
}
