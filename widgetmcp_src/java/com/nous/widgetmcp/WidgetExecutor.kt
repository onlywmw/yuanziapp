package com.nous.widgetmcp

import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * [P2-6 修复] 全局线程池 — 替代各 Provider 自己创建的 executor
 *
 * 问题: 每个 Provider 实例创建自己的 SingleThreadExecutor,
 * 删除 Widget 后线程不回收 → 泄漏。
 *
 * 修复: 全局单例 FixedThreadPool(2), 所有异步任务复用。
 */
object WidgetExecutor {
    val pool: ExecutorService = Executors.newFixedThreadPool(2)
}
