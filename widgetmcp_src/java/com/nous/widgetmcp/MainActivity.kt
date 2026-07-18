package com.nous.widgetmcp

import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.*
import com.nous.widgetmcp.yuanzi.YuanziApi
import com.nous.widgetmcp.yuanzi.YuanziConfig
import com.nous.widgetmcp.yuanzi.YuanziEvent
import com.nous.widgetmcp.yuanzi.YuanziPollScheduler
import com.nous.widgetmcp.yuanzi.YuanziSync
import com.nous.widgetmcp.yuanzi.YuanziSyncService
import com.nous.widgetmcp.ui.GraphEdge
import com.nous.widgetmcp.ui.GraphNode
import com.nous.widgetmcp.ui.GraphView
import com.nous.widgetmcp.browser.BrowserActivity

class MainActivity : Activity() {

    private lateinit var container: ViewFlipper
    private var testSuccess = false

    private lateinit var homeView: View
    private lateinit var graphView: GraphView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        container = ViewFlipper(this)
        homeView = buildHome()
        container.addView(homeView)
        container.addView(buildDeepSeekConfig())
        container.addView(buildYuanziSettings())
        setContentView(container)

        // 用户打开 App（前台）时启动 Yuanzi 轮询
        if (YuanziConfig.enabled) {
            try {
                YuanziSyncService.start(this)
                YuanziPollScheduler.scheduleNext(this)
            } catch (e: Exception) {
                AppLogger.e("MAIN", "Yuanzi scheduler failed: ${e.message}", e)
                YuanziConfig.lastError = e.message
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // 从设置页返回或后台切回时刷新首页状态
        refreshHome()
    }

    private fun refreshHome() {
        if (!::graphView.isInitialized) return
        loadGraphFromYuanzi()
    }

    // ==================== 首页：知识图谱 ====================

    private fun buildHome(): View {
        graphView = GraphView(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            setData(defaultGraphNodes(), defaultGraphEdges())
            onNodeClick = { node -> onGraphNodeClick(node) }
        }
        loadGraphFromYuanzi()
        return graphView
    }

    private fun loadGraphFromYuanzi() {
        Thread {
            val topology = YuanziApi.fetchGraph().getOrNull()
            runOnUiThread {
                if (topology != null) {
                    graphView.setData(
                        mapTopologyToUiNodes(topology) + localAddonNodes(),
                        mapTopologyToUiEdges(topology) + localAddonEdges()
                    )
                } else {
                    // 拉取失败时至少显示本地节点，避免空白
                    graphView.setData(defaultGraphNodes() + localAddonNodes(), defaultGraphEdges() + localAddonEdges())
                }
            }
        }.start()
    }

    private fun mapTopologyToUiNodes(topology: com.nous.widgetmcp.yuanzi.GraphTopology): List<GraphNode> {
        val paper = getColor(R.color.paper)
        return topology.nodes.map { node ->
            when (node.id) {
                "widgetmcp" -> GraphNode(
                    id = "widgetmcp",
                    label = "组件\nMCP",
                    type = GraphNode.NodeType.CENTER,
                    color = getColor(R.color.clay),
                    textColor = paper,
                    radius = 56f
                )
                "yuanzi-core" -> {
                    val connected = YuanziConfig.lastSync > 0 && YuanziConfig.lastError == null
                    val color = when {
                        !YuanziConfig.enabled -> getColor(R.color.amber)
                        connected -> getColor(R.color.sage)
                        else -> getColor(R.color.rust)
                    }
                    GraphNode(
                        id = "yuanzi-core",
                        label = "Yuanzi\n中枢",
                        type = GraphNode.NodeType.YUANZI,
                        color = color,
                        textColor = paper,
                        radius = 48f
                    )
                }
                "yuanzi-browser" -> GraphNode(
                    id = "yuanzi-browser",
                    label = node.label,
                    type = GraphNode.NodeType.BROWSER,
                    color = getColor(R.color.clay_deep),
                    textColor = paper,
                    radius = 44f,
                    payload = node.endpoint
                )
                else -> {
                    val color = when (node.type) {
                        "api" -> getColor(R.color.amber)
                        "note" -> getColor(R.color.sage)
                        "widget" -> getColor(R.color.clay_light)
                        else -> getColor(R.color.sage_light)
                    }
                    GraphNode(
                        id = node.id,
                        label = node.label,
                        type = GraphNode.NodeType.WIDGET,
                        color = color,
                        textColor = getColor(R.color.ink),
                        radius = 42f,
                        payload = node
                    )
                }
            }
        }
    }

    private fun mapTopologyToUiEdges(topology: com.nous.widgetmcp.yuanzi.GraphTopology): List<GraphEdge> {
        val hairline = getColor(R.color.hairline)
        // 只保留原子级拓扑边，能力标签边太密， capabilities 放到节点点击 toast 里展示
        return topology.edges.filter { it.label == null }.map { edge ->
            GraphEdge(edge.source, edge.target, hairline, 2f)
        }
    }

    private fun defaultGraphNodes(): List<GraphNode> {
        val paper = getColor(R.color.paper)
        val connected = YuanziConfig.lastSync > 0 && YuanziConfig.lastError == null
        val yuanziColor = when {
            !YuanziConfig.enabled -> getColor(R.color.amber)
            connected -> getColor(R.color.sage)
            else -> getColor(R.color.rust)
        }
        return listOf(
            GraphNode(
                id = "widgetmcp",
                label = "组件\nMCP",
                type = GraphNode.NodeType.CENTER,
                color = getColor(R.color.clay),
                textColor = paper,
                radius = 56f
            ),
            GraphNode(
                id = "yuanzi-core",
                label = "Yuanzi\n中枢",
                type = GraphNode.NodeType.YUANZI,
                color = yuanziColor,
                textColor = paper,
                radius = 48f
            ),
            GraphNode(
                id = "yuanzi-browser",
                label = "浏览器",
                type = GraphNode.NodeType.BROWSER,
                color = getColor(R.color.clay_deep),
                textColor = paper,
                radius = 44f
            )
        )
    }

    private fun defaultGraphEdges(): List<GraphEdge> {
        return listOf(GraphEdge("widgetmcp", "yuanzi-core", getColor(R.color.hairline)))
    }

    private fun localAddonNodes(): List<GraphNode> {
        val ink = getColor(R.color.ink)
        val sageLight = getColor(R.color.sage_light)
        val amberLight = getColor(R.color.amber_light)
        val clayLight = getColor(R.color.clay_light)
        val nodes = mutableListOf(
            GraphNode(
                id = "add_balance",
                label = "+ 余额",
                type = GraphNode.NodeType.ADD_TEMPLATE,
                color = sageLight,
                textColor = ink,
                radius = 40f,
                payload = "balance"
            ),
            GraphNode(
                id = "add_text",
                label = "+ 文本",
                type = GraphNode.NodeType.ADD_TEMPLATE,
                color = amberLight,
                textColor = ink,
                radius = 40f,
                payload = "text"
            ),
            GraphNode(
                id = "add_obsidian",
                label = "+ Obsidian",
                type = GraphNode.NodeType.ADD_TEMPLATE,
                color = clayLight,
                textColor = ink,
                radius = 40f,
                payload = "obsidian-card"
            )
        )
        val instances = try { ServiceLocator.controller.list() } catch (_: Exception) { emptyList() }
        instances.forEach { cfg ->
            val snap = ServiceLocator.controller.snapshot(cfg.widgetId)
            val desc = when (snap?.data) {
                is WidgetData.Number -> "¥ %.2f".format((snap.data as WidgetData.Number).value)
                is WidgetData.Text -> (snap.data as WidgetData.Text).content.take(8)
                else -> cfg.typeId
            }
            val color = when {
                cfg.lastError != null -> getColor(R.color.rust_light)
                snap == null -> amberLight
                else -> sageLight
            }
            nodes.add(GraphNode(
                id = "widget_${cfg.widgetId}",
                label = desc,
                type = GraphNode.NodeType.WIDGET,
                color = color,
                textColor = ink,
                radius = 42f,
                payload = cfg.widgetId
            ))
        }
        return nodes
    }

    private fun localAddonEdges(): List<GraphEdge> {
        val hairline = getColor(R.color.hairline)
        val edges = mutableListOf(
            GraphEdge("widgetmcp", "add_balance", hairline),
            GraphEdge("widgetmcp", "add_text", hairline),
            GraphEdge("widgetmcp", "add_obsidian", hairline)
        )
        val instances = try { ServiceLocator.controller.list() } catch (_: Exception) { emptyList() }
        instances.forEach { cfg ->
            if (cfg.source == WidgetSource.YUANZI) {
                edges.add(GraphEdge("yuanzi-core", "widget_${cfg.widgetId}", hairline))
            } else {
                edges.add(GraphEdge("widgetmcp", "widget_${cfg.widgetId}", hairline))
            }
        }
        return edges
    }

    private fun onGraphNodeClick(node: GraphNode) {
        when (node.type) {
            GraphNode.NodeType.CENTER -> {
                // 双击空白处重置，中心节点点击无动作
            }
            GraphNode.NodeType.YUANZI -> showPage(2)
            GraphNode.NodeType.BROWSER -> BrowserActivity.open(this)
            GraphNode.NodeType.ADD_TEMPLATE -> {
                val typeId = node.payload as? String
                if (typeId == "balance") showPage(1)
                else Toast.makeText(this, "${node.label} — 即将支持", Toast.LENGTH_SHORT).show()
            }
            GraphNode.NodeType.WIDGET -> {
                when (val payload = node.payload) {
                    is Int -> {
                        val widgetId = payload
                        if (!com.nous.widgetmcp.widget.WidgetBinding.isPinned(this, widgetId)) {
                            pinWidgetToHome(widgetId)
                        } else {
                            Toast.makeText(this, "已固定到桌面", Toast.LENGTH_SHORT).show()
                        }
                    }
                    is com.nous.widgetmcp.yuanzi.GraphTopology.Node -> {
                        Toast.makeText(this, "${payload.label} · ${payload.capabilities.joinToString(", ")}", Toast.LENGTH_SHORT).show()
                    }
                    else -> {}
                }
            }
            else -> {}
        }
    }

    // ==================== Yuanzi 状态卡 ====================

    private fun buildYuanziStatusCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(16), dp(16), dp(16), dp(16))
            setBackgroundResource(R.drawable.app_card_bg)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(12) }
            isClickable = true
            setOnClickListener { showPage(2) }
        }

        val connected = YuanziConfig.lastSync > 0 && YuanziConfig.lastError == null
        val dotRes = when {
            !YuanziConfig.enabled -> R.drawable.app_dot_amber
            connected -> R.drawable.app_dot_sage
            else -> R.drawable.app_dot_rust
        }
        card.addView(View(this).apply {
            setBackgroundResource(dotRes)
            layoutParams = LinearLayout.LayoutParams(dp(8), dp(8)).apply { rightMargin = dp(10) }
        })

        val texts = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        }
        val statusText = when {
            !YuanziConfig.enabled -> "已禁用，点击配置"
            connected -> "已连接 ${YuanziConfig.host}:${YuanziConfig.port}"
            YuanziConfig.lastError != null -> "连接失败：${YuanziConfig.lastError}"
            else -> "等待同步…"
        }
        texts.addView(tv(statusText, 14f, getColor(R.color.ink)))
        texts.addView(tv("Yuanzi 中枢", 12f, getColor(R.color.muted)).apply {
            setPadding(0, dp(2), 0, 0)
        })
        card.addView(texts)
        card.addView(tv("›", 18f, getColor(R.color.faint)))
        return card
    }

    // ==================== DeepSeek 配置页 ====================

    private lateinit var keyInput: EditText
    private lateinit var testBtn: Button
    private lateinit var testResult: TextView
    private lateinit var addBtn: Button
    private lateinit var previewText: TextView

    private fun buildDeepSeekConfig(): View {
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(16), dp(20), dp(24))
            setBackgroundColor(getColor(R.color.paper))
        }

        // 顶部：‹ 返回（clay 文字按钮，无边框）+ 大标题
        layout.addView(tv("‹ 返回", 15f, getColor(R.color.clay)).apply {
            setPadding(0, dp(8), 0, dp(8))
            setOnClickListener { showPage(0) }
        })
        layout.addView(tv("DeepSeek 余额监测", 22f, getColor(R.color.ink)).apply {
            setTypeface(typeface, Typeface.BOLD)
        })

        // 区块①：API Key
        layout.addView(section("API Key"))
        keyInput = EditText(this).apply {
            hint = "sk-..."
            setHintTextColor(getColor(R.color.faint))
            setTextColor(getColor(R.color.ink))
            textSize = 15f
            inputType = InputType.TYPE_TEXT_VARIATION_PASSWORD
            setSingleLine(true)
            setBackgroundResource(R.drawable.app_input_bg)
            setPadding(dp(14), dp(12), dp(14), dp(12))
        }
        layout.addView(keyInput)

        testResult = tv("", 14f, getColor(R.color.muted)).apply { setPadding(0, dp(8), 0, dp(8)) }
        layout.addView(testResult)

        testBtn = outlineBtn("测试连接")
        layout.addView(testBtn)

        testBtn.setOnClickListener {
            val key = keyInput.text.toString().trim()
            if (key.isBlank()) {
                testResult.text = "请输入 API Key"
                testResult.setTextColor(getColor(R.color.rust_deep))
                return@setOnClickListener
            }
            testBtn.isEnabled = false
            testBtn.text = "测试中..."
            testResult.text = "测试中…"
            testResult.setTextColor(getColor(R.color.muted))
            setAddEnabled(false)

            Thread {
                val credentialId = "deepseek_test"
                CredentialStore.put(credentialId, "api_key", key)
                val result = ServiceLocator.controller.test("balance", credentialId)
                runOnUiThread {
                    testBtn.isEnabled = true
                    testBtn.text = "测试连接"
                    result.fold(
                        onSuccess = { data ->
                            testSuccess = true
                            val num = data as WidgetData.Number
                            testResult.text = "✓ 连接成功，当前余额 ¥ %.2f".format(num.value)
                            testResult.setTextColor(getColor(R.color.sage_deep))
                            setAddEnabled(true)
                            previewText.text = "¥ %.2f".format(num.value)
                            previewText.setTextColor(getColor(R.color.ink))
                        },
                        onFailure = { e ->
                            testSuccess = false
                            testResult.text = "✕ ${e.message ?: "连接失败"}"
                            testResult.setTextColor(getColor(R.color.rust_deep))
                            setAddEnabled(false)
                        }
                    )
                }
            }.start()
        }

        // 区块②：桌面预览（白卡模拟 widget：label + ¥ 大字）
        layout.addView(section("桌面预览"))
        val previewCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(14))
            setBackgroundResource(R.drawable.app_preview_widget_bg)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        previewCard.addView(tv("DeepSeek 余额", 11f, getColor(R.color.muted)))
        previewText = tv("¥ --", 26f, getColor(R.color.faint)).apply {
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(4), 0, 0)
        }
        previewCard.addView(previewText)
        layout.addView(previewCard)

        // 区块③：刷新间隔（RadioButton 文字 ink，选中 clay）
        layout.addView(section("刷新间隔"))
        val refreshGroup = RadioGroup(this).apply { orientation = RadioGroup.HORIZONTAL }
        for ((label, mins) in listOf("15分" to 15, "30分" to 30, "1小时" to 60, "手动" to 0)) {
            val rb = RadioButton(this).apply {
                text = label
                textSize = 15f
                setTextColor(getColor(R.color.ink))
                buttonTintList = ColorStateList.valueOf(getColor(R.color.clay))
            }
            if (mins == 30) rb.isChecked = true
            refreshGroup.addView(rb)
        }
        layout.addView(refreshGroup)

        // 底部主 CTA：添加到桌面（clay 填充，禁用态 #66B85C38）
        addBtn = primaryBtn("添加到桌面").apply {
            isEnabled = false
            setBackgroundResource(R.drawable.app_btn_primary_disabled)
            (layoutParams as LinearLayout.LayoutParams).topMargin = dp(24)
        }
        addBtn.setOnClickListener {
            val key = keyInput.text.toString().trim()
            val credentialId = "ds_${System.currentTimeMillis()}"
            CredentialStore.put(credentialId, "api_key", key)
            val internalId = ServiceLocator.controller.create("balance", "deepseek", credentialRef = credentialId)
            pinWidgetToHome(internalId)
        }
        layout.addView(addBtn)

        scroll.addView(layout)
        return scroll
    }

    // ==================== Yuanzi 设置页 ====================

    private lateinit var yuanziHostInput: EditText
    private lateinit var yuanziPortInput: EditText
    private lateinit var yuanziTokenInput: EditText
    private lateinit var yuanziTestResult: TextView
    private lateinit var yuanziSyncResult: TextView
    private lateinit var yuanziEventResult: TextView

    private fun buildYuanziSettings(): View {
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(16), dp(20), dp(24))
            setBackgroundColor(getColor(R.color.paper))
        }

        layout.addView(tv("‹ 返回", 15f, getColor(R.color.clay)).apply {
            setPadding(0, dp(8), 0, dp(8))
            setOnClickListener { showPage(0) }
        })
        layout.addView(tv("Yuanzi 中枢设置", 22f, getColor(R.color.ink)).apply {
            setTypeface(typeface, Typeface.BOLD)
        })

        layout.addView(section("连接地址"))

        yuanziHostInput = inputField("127.0.0.1", YuanziConfig.host)
        layout.addView(yuanziHostInput)
        yuanziPortInput = inputField("8080", YuanziConfig.port.toString()).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
        }
        layout.addView(yuanziPortInput)
        yuanziTokenInput = inputField("Token（可选）", YuanziConfig.token).apply {
            inputType = InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        layout.addView(yuanziTokenInput)

        yuanziTestResult = tv("", 14f, getColor(R.color.muted)).apply { setPadding(0, dp(8), 0, dp(8)) }
        layout.addView(yuanziTestResult)

        layout.addView(outlineBtn("测试连接").apply {
            setOnClickListener { testYuanziConnection() }
        })

        layout.addView(section("同步控制"))
        layout.addView(primaryBtn("立即同步").apply {
            setOnClickListener { syncYuanziNow() }
        })
        yuanziSyncResult = tv("", 14f, getColor(R.color.muted)).apply { setPadding(0, dp(8), 0, dp(8)) }
        layout.addView(yuanziSyncResult)

        layout.addView(outlineBtn("测试事件上报").apply {
            setOnClickListener { testYuanziEvent() }
        })
        yuanziEventResult = tv("", 14f, getColor(R.color.muted)).apply { setPadding(0, dp(8), 0, dp(8)) }
        layout.addView(yuanziEventResult)

        layout.addView(section("开关"))
        val toggleRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(14))
            setBackgroundResource(R.drawable.app_card_bg)
        }
        toggleRow.addView(tv("启用 Yuanzi 轮询", 15f, getColor(R.color.ink)).apply {
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        })
        val toggle = Switch(this).apply { isChecked = YuanziConfig.enabled }
        toggle.setOnCheckedChangeListener { _, checked ->
            YuanziConfig.enabled = checked
            if (checked) {
                YuanziSyncService.start(this@MainActivity)
                YuanziPollScheduler.scheduleNext(this@MainActivity)
            } else {
                YuanziSyncService.stop(this@MainActivity)
                YuanziPollScheduler.cancel(this@MainActivity)
            }
        }
        toggleRow.addView(toggle)
        layout.addView(toggleRow)

        scroll.addView(layout)
        return scroll
    }

    private fun inputField(hintText: String, value: String): EditText {
        return EditText(this).apply {
            hint = hintText
            setHintTextColor(getColor(R.color.faint))
            setTextColor(getColor(R.color.ink))
            textSize = 15f
            setSingleLine(true)
            setBackgroundResource(R.drawable.app_input_bg)
            setPadding(dp(14), dp(12), dp(14), dp(12))
            setText(value)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(8) }
        }
    }

    private fun testYuanziConnection() {
        saveYuanziInputs()
        yuanziTestResult.text = "测试中…"
        yuanziTestResult.setTextColor(getColor(R.color.muted))
        Thread {
            val result = YuanziApi.checkHealth()
            runOnUiThread {
                result.fold(
                    onSuccess = {
                        yuanziTestResult.text = "✓ 连接成功"
                        yuanziTestResult.setTextColor(getColor(R.color.sage_deep))
                    },
                    onFailure = { e ->
                        yuanziTestResult.text = "✕ ${e.message ?: "连接失败"}"
                        yuanziTestResult.setTextColor(getColor(R.color.rust_deep))
                    }
                )
            }
        }.start()
    }

    private fun syncYuanziNow() {
        saveYuanziInputs()
        yuanziSyncResult.text = "同步中…"
        yuanziSyncResult.setTextColor(getColor(R.color.muted))
        Thread {
            val result = YuanziSync.syncOnce(this)
            runOnUiThread {
                result.fold(
                    onSuccess = { count ->
                        yuanziSyncResult.text = "✓ 同步完成，${count} 个 widget"
                        yuanziSyncResult.setTextColor(getColor(R.color.sage_deep))
                        refreshHome()
                    },
                    onFailure = { e ->
                        yuanziSyncResult.text = "✕ ${e.message ?: "同步失败"}"
                        yuanziSyncResult.setTextColor(getColor(R.color.rust_deep))
                    }
                )
            }
        }.start()
    }

    private fun testYuanziEvent() {
        saveYuanziInputs()
        yuanziEventResult.text = "上报中…"
        yuanziEventResult.setTextColor(getColor(R.color.muted))
        Thread {
            val event = YuanziEvent(
                source = "app",
                toolId = "widget/click",
                args = mapOf(
                    "widget_id" to "widget_1da16af1",
                    "internal_id" to -1,
                    "action" to "test"
                )
            )
            val result = YuanziApi.reportEvent(event)
            runOnUiThread {
                result.fold(
                    onSuccess = {
                        yuanziEventResult.text = "✓ 上报成功"
                        yuanziEventResult.setTextColor(getColor(R.color.sage_deep))
                        refreshHome()
                    },
                    onFailure = { e ->
                        yuanziEventResult.text = "✕ ${e.message ?: "上报失败"}"
                        yuanziEventResult.setTextColor(getColor(R.color.rust_deep))
                    }
                )
            }
        }.start()
    }

    private fun saveYuanziInputs() {
        YuanziConfig.setEndpoint(
            host = yuanziHostInput.text.toString().trim().ifEmpty { "127.0.0.1" },
            port = yuanziPortInput.text.toString().trim().toIntOrNull() ?: 8080,
            token = yuanziTokenInput.text.toString().trim()
        )
    }

    // ==================== helpers ====================

    private fun pinWidgetToHome(internalId: Int) {
        val mgr = AppWidgetManager.getInstance(this)
        val supported = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) mgr.isRequestPinAppWidgetSupported else false
        AppLogger.i("PIN", "supported=$supported internalId=$internalId")

        if (!supported) {
            Toast.makeText(this, "当前桌面不支持快捷添加，长按桌面→添加小部件→组件 MCP", Toast.LENGTH_LONG).show()
            return
        }

        try {
            val svc = Intent(this, McpService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(svc) else startService(svc)
            AppLogger.i("PIN", "keepAlive service started")
        } catch (e: Exception) {
            AppLogger.e("PIN", "start service failed", e)
        }

        com.nous.widgetmcp.widget.WidgetBinding.markPending(this, internalId)
        val ok = mgr.requestPinAppWidget(
            ComponentName(this, com.nous.widgetmcp.widget.McpWidgetProvider::class.java), null, null)
        AppLogger.i("PIN", "requestPin=$ok")
        if (!ok) Toast.makeText(this, "添加失败：Provider 未注册或被系统拒绝", Toast.LENGTH_LONG).show()
        else Toast.makeText(this, "已保存，请在弹窗中确认固定", Toast.LENGTH_LONG).show()
    }

    private fun showPage(index: Int) {
        testSuccess = false
        addBtn?.isEnabled = false
        addBtn?.setBackgroundResource(R.drawable.app_btn_primary_disabled)
        testResult?.text = ""
        testResult?.setTextColor(getColor(R.color.muted))
        keyInput?.setText("")
        container.displayedChild = index
    }

    /** 主 CTA 使能切换：isEnabled 与背景（启用/禁用 drawable）保持同步 */
    private fun setAddEnabled(enabled: Boolean) {
        addBtn.isEnabled = enabled
        addBtn.setBackgroundResource(if (enabled) R.drawable.app_btn_primary else R.drawable.app_btn_primary_disabled)
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density + 0.5f).toInt()

    private fun section(title: String) = tv(title, 13f, getColor(R.color.muted)).apply {
        setTypeface(typeface, Typeface.BOLD)
        setPadding(0, dp(24), 0, dp(8))
    }

    private fun tv(text: String, size: Float, color: Int, gravity: Int = Gravity.START): TextView {
        return TextView(this).apply {
            this.text = text; textSize = size; setTextColor(color)
            this.gravity = gravity or Gravity.CENTER_VERTICAL
        }
    }

    /** 主按钮：clay 填充 52dp 高，文字白 16sp，textAllCaps=false */
    private fun primaryBtn(label: String): Button {
        return Button(this).apply {
            text = label
            setBackgroundResource(R.drawable.app_btn_primary)
            setTextColor(0xFFFFFFFF.toInt())
            textSize = 16f
            setAllCaps(false)
            stateListAnimator = null
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(52)
            ).apply { topMargin = dp(8) }
        }
    }

    /** 次按钮：clay 描边 52dp 高，文字 clay 16sp，textAllCaps=false */
    private fun outlineBtn(label: String): Button {
        return Button(this).apply {
            text = label
            setBackgroundResource(R.drawable.app_btn_outline)
            setTextColor(getColor(R.color.clay))
            textSize = 16f
            setAllCaps(false)
            stateListAnimator = null
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(52)
            ).apply { topMargin = dp(8) }
        }
    }
}
