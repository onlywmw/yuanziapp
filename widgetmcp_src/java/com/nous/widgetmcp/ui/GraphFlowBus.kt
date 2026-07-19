package com.nous.widgetmcp.ui

import android.os.Handler
import android.os.Looper

/**
 * M8 数据流事件总线：把后台线程的真实数据事件（Yuanzi 同步拉取、
 * widget 点击上报、widget 数据刷新成功/失败）转发到前台 GraphView，
 * 驱动图谱边上的光尾粒子。
 *
 * 总线上只承载「源节点 id → 目标节点 id」的最小信息；GraphView 侧
 * 经 [GraphView.sendDataFlowBetween] 按 id 找真实存在的边，找不到
 * 就不发射 —— 绝不伪造装饰性粒子。无监听者（App 未在前台）时静默丢弃。
 *
 * 线程约定：post 可在任意线程调用；监听者回调一律切到主线程。
 */
object GraphFlowBus {

    /** 数据流事件。sourceId → targetId 仅作语义记录，GraphView 找边时方向不限。 */
    interface Listener {
        fun onDataFlow(sourceId: String, targetId: String)
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile
    private var listener: Listener? = null

    /** 前台页面（MainActivity）注册/注销；重复注册后者覆盖，传 null 注销。 */
    fun register(l: Listener?) {
        listener = l
    }

    /** 任意线程可调用；有监听者时切主线程回调，无监听者静默丢弃。 */
    fun post(sourceId: String, targetId: String) {
        val l = listener ?: return
        mainHandler.post { l.onDataFlow(sourceId, targetId) }
    }
}
