package com.nous.widgetmcp.graph.ui

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Color
import android.graphics.RenderEffect
import android.graphics.Shader
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.animation.DecelerateInterpolator
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.TextView
import com.nous.widgetmcp.graph.templates.ColorScheme
import com.nous.widgetmcp.graph.templates.TemplateParams
import java.util.Locale

/**
 * M8 参数面板（设计文档第四节）
 *
 * 底部滑出面板，半透明 + （可选）模糊背景。
 * 8 个滑块 + 4 个配色按钮 + 混音台滑块 + 5 个预设按钮，
 * 全部映射 [TemplateParams] 对应字段。
 *
 * 存储：SharedPreferences 文件 "graph_params"，键 "graph_params"；
 * 面板关闭时保存，attach 时恢复并回调一次，方便引擎接线。
 *
 * 仅使用 Android 原生 View / SeekBar，无第三方依赖。
 */
class ParameterPanel(private val context: Context) {

    companion object {
        private const val PREFS_NAME = "graph_params"
        private const val KEY_PARAMS = "graph_params"

        private const val SEEKBAR_MAX = 1000
        private const val PRESET_ANIM_DURATION = 320L
        private const val PANEL_ANIM_DURATION = 240L

        private val PANEL_BG = Color.parseColor("#E6141414")
        private val SCRIM_BG = Color.parseColor("#55000000")
        private val TEXT_PRIMARY = Color.parseColor("#E9E2D6")
        private val TEXT_SECONDARY = Color.parseColor("#9A938A")
        private val ACCENT = Color.parseColor("#8AB4F8")
        private val BTN_BG = Color.parseColor("#33FFFFFF")
        private val BTN_BG_ACTIVE = Color.parseColor("#558AB4F8")

        /** 第五节 PRESETS 表，逐值对齐（discover 用 ColorScheme.SOUL）。 */
        val PRESETS: Map<String, TemplateParams> = mapOf(
            "debug" to TemplateParams(
                mixerPosition = 0.0f,
                nodeBaseSize = 1.0f,
                textOpacity = 1.0f,
                edgeThickness = 4.0f,
                edgeLength = 120f,
                centripetal = 0.8f,
                repulsion = 0.3f,
                attraction = 0.8f,
                layoutSpeed = 1.0f,
                colorScheme = ColorScheme.TAG
            ),
            "work" to TemplateParams(
                mixerPosition = 0.3f
            ),
            "browse" to TemplateParams(
                mixerPosition = 0.7f
            ),
            "discover" to TemplateParams(
                mixerPosition = 1.0f,
                nodeBaseSize = 1.4f,
                textOpacity = 1.0f,
                edgeThickness = 1.0f,
                edgeLength = 250f,
                centripetal = 0.2f,
                repulsion = 0.8f,
                attraction = 0.2f,
                layoutSpeed = 0.3f,
                colorScheme = ColorScheme.SOUL
            ),
            "default" to TemplateParams()
        )
    }

    /** 参数变更回调：滑块拖动、配色切换、预设动画的每一帧都会触发。 */
    var onParamsChanged: ((TemplateParams) -> Unit)? = null

    /**
     * 可选：面板弹出时要模糊的背景 View（如 GraphView 容器）。
     * API 31+ 用 RenderEffect 实现高斯模糊；低版本或未设置时退化为半透明遮罩。
     */
    var blurTarget: View? = null

    private var params: TemplateParams = TemplateParams()

    private var containerView: FrameLayout? = null
    private var scrimView: View? = null
    private var panelView: LinearLayout? = null
    private var attached = false
    private var showing = false

    /** 内部刷新（预设动画 / 恢复参数）时不回调，避免循环。 */
    private var internalUpdate = false
    private var presetAnimator: ValueAnimator? = null

    /** 一条滑块与 TemplateParams 字段的双向绑定。 */
    private class SliderBinding(
        val seekBar: SeekBar,
        val valueLabel: TextView,
        val min: Float,
        val max: Float,
        val decimals: Int,
        val getter: (TemplateParams) -> Float,
        val setter: (TemplateParams, Float) -> TemplateParams
    ) {
        fun toProgress(value: Float): Int =
            (((value - min) / (max - min)) * SEEKBAR_MAX).toInt().coerceIn(0, SEEKBAR_MAX)

        fun toValue(progress: Int): Float =
            min + (max - min) * progress / SEEKBAR_MAX

        fun format(value: Float): String =
            String.format(Locale.US, "%.${decimals}f", value)
    }

    private val sliders = mutableListOf<SliderBinding>()
    private val schemeButtons = mutableMapOf<ColorScheme, TextView>()

    // ------------------------------------------------------------------
    // 对外 API
    // ------------------------------------------------------------------

    /** 当前参数。 */
    fun getParams(): TemplateParams = params

    /** 是否已 attach 且面板正在显示。 */
    fun isShowing(): Boolean = showing

    /**
     * 挂到指定父容器（通常是承载 GraphView 的 FrameLayout / 根布局）。
     * attach 时从 SharedPreferences 恢复参数，并通过 [onParamsChanged] 回调一次。
     */
    fun attachTo(root: ViewGroup) {
        if (attached) return
        attached = true

        params = loadParams()
        buildViews(root)
        refreshControls(params)
        refreshSchemeButtons(params.colorScheme)

        containerView?.visibility = View.GONE
        onParamsChanged?.invoke(params)
    }

    /** 滑出面板。 */
    fun show() {
        val container = containerView ?: return
        val panel = panelView ?: return
        if (showing) return
        showing = true

        presetAnimator?.cancel()
        container.visibility = View.VISIBLE
        scrimView?.alpha = 0f
        scrimView?.animate()?.alpha(1f)?.setDuration(PANEL_ANIM_DURATION)?.start()

        panel.post {
            panel.translationY = panel.height.toFloat()
            panel.animate()
                .translationY(0f)
                .setDuration(PANEL_ANIM_DURATION)
                .setInterpolator(DecelerateInterpolator())
                .start()
        }
        applyBlur(true)
    }

    /** 收起面板并保存参数。 */
    fun hide() {
        val container = containerView ?: return
        val panel = panelView ?: return
        if (!showing) return
        showing = false

        saveParams(params)
        applyBlur(false)

        scrimView?.animate()?.alpha(0f)?.setDuration(PANEL_ANIM_DURATION)?.start()
        panel.animate()
            .translationY(panel.height.toFloat().coerceAtLeast(1f))
            .setDuration(PANEL_ANIM_DURATION)
            .withEndAction { container.visibility = View.GONE }
            .start()
    }

    fun toggle() {
        if (showing) hide() else show()
    }

    /** 外部直接设置参数（例如引擎侧初始化）。 */
    fun setParams(newParams: TemplateParams, animate: Boolean = false) {
        if (animate) animateToParams(newParams) else {
            presetAnimator?.cancel()
            applyParams(newParams, notify = true)
        }
    }

    /** 面板销毁时调用，释放引用并保存参数。 */
    fun detach() {
        presetAnimator?.cancel()
        if (attached) saveParams(params)
        applyBlur(false)
        (containerView?.parent as? ViewGroup)?.removeView(containerView)
        containerView = null
        scrimView = null
        panelView = null
        sliders.clear()
        schemeButtons.clear()
        attached = false
        showing = false
    }

    // ------------------------------------------------------------------
    // 视图构建
    // ------------------------------------------------------------------

    private fun buildViews(root: ViewGroup) {
        val container = FrameLayout(context)
        container.layoutParams = ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        )

        // 遮罩：点击关闭
        val scrim = View(context)
        scrim.layoutParams = FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        )
        scrim.setBackgroundColor(SCRIM_BG)
        scrim.setOnClickListener { hide() }
        container.addView(scrim)
        scrimView = scrim

        // 底部面板：半透明圆角背景，内容可滚动
        val panel = LinearLayout(context)
        panel.orientation = LinearLayout.VERTICAL
        val panelLp = FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.BOTTOM
        )
        panel.layoutParams = panelLp
        panel.background = GradientDrawable().apply {
            setColor(PANEL_BG)
            cornerRadii = floatArrayOf(
                dp(20), dp(20), dp(20), dp(20), // top-left
                0f, 0f, 0f, 0f                  // bottom
            )
        }
        panel.setPadding(dp(20).toInt(), dp(10).toInt(), dp(20).toInt(), dp(24).toInt())

        val scroll = ScrollView(context)
        scroll.layoutParams = FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.BOTTOM
        )
        scroll.addView(panel)
        container.addView(scroll)

        // 顶部把手
        val handle = View(context)
        val handleLp = LinearLayout.LayoutParams(dp(36).toInt(), dp(4).toInt())
        handleLp.gravity = Gravity.CENTER_HORIZONTAL
        handleLp.bottomMargin = dp(8).toInt()
        handle.layoutParams = handleLp
        handle.background = GradientDrawable().apply {
            setColor(Color.parseColor("#66FFFFFF"))
            cornerRadius = dp(2)
        }
        panel.addView(handle)

        panel.addView(makeTitle("图谱参数"))
        panel.addView(makePresetRow())
        panel.addView(makeDivider())
        panel.addView(makeSchemeRow())
        panel.addView(makeDivider())
        panel.addView(makeMixerRow())
        panel.addView(makeDivider())

        // 8 个滑块：范围严格按设计文档第四节
        panel.addView(makeSliderRow("节点大小", 0.5f, 2.0f, 2,
            { it.nodeBaseSize }, { p, v -> p.copy(nodeBaseSize = v) }))
        panel.addView(makeSliderRow("文字透明度", 0.0f, 1.0f, 2,
            { it.textOpacity }, { p, v -> p.copy(textOpacity = v) }))
        panel.addView(makeSliderRow("连线粗细", 0.5f, 5.0f, 1,
            { it.edgeThickness }, { p, v -> p.copy(edgeThickness = v) }))
        panel.addView(makeSliderRow("连线长度", 80f, 300f, 0,
            { it.edgeLength }, { p, v -> p.copy(edgeLength = v) }))
        panel.addView(makeSliderRow("向心力", 0.0f, 1.0f, 2,
            { it.centripetal }, { p, v -> p.copy(centripetal = v) }))
        panel.addView(makeSliderRow("排斥力", 0.0f, 1.0f, 2,
            { it.repulsion }, { p, v -> p.copy(repulsion = v) }))
        panel.addView(makeSliderRow("吸引力", 0.0f, 1.0f, 2,
            { it.attraction }, { p, v -> p.copy(attraction = v) }))
        panel.addView(makeSliderRow("布局速度", 0.1f, 1.0f, 2,
            { it.layoutSpeed }, { p, v -> p.copy(layoutSpeed = v) }))

        root.addView(container)
        containerView = container
        panelView = panel
    }

    private fun makeTitle(text: String): TextView {
        val tv = TextView(context)
        tv.text = text
        tv.textSize = 15f
        tv.setTextColor(TEXT_PRIMARY)
        tv.setPadding(0, 0, 0, dp(6).toInt())
        return tv
    }

    private fun makeDivider(): View {
        val v = View(context)
        val lp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1)
        lp.topMargin = dp(8).toInt()
        lp.bottomMargin = dp(8).toInt()
        v.layoutParams = lp
        v.setBackgroundColor(Color.parseColor("#22FFFFFF"))
        return v
    }

    /** 5 个预设按钮：🔧调试 / ⚡工作 / 🎨浏览 / 💎发现 / 🎛默认。 */
    private fun makePresetRow(): LinearLayout {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.HORIZONTAL

        val presets = listOf(
            "🔧调试" to "debug",
            "⚡工作" to "work",
            "🎨浏览" to "browse",
            "💎发现" to "discover",
            "🎛默认" to "default"
        )
        presets.forEach { (label, key) ->
            val btn = TextView(context)
            btn.text = label
            btn.textSize = 13f
            btn.setTextColor(TEXT_PRIMARY)
            btn.gravity = Gravity.CENTER
            btn.setPadding(0, dp(10).toInt(), 0, dp(10).toInt())
            btn.background = GradientDrawable().apply {
                setColor(BTN_BG)
                cornerRadius = dp(10)
            }
            val lp = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            lp.marginEnd = dp(6).toInt()
            btn.layoutParams = lp
            btn.setOnClickListener {
                PRESETS[key]?.let { animateToParams(it) }
            }
            row.addView(btn)
        }
        return row
    }

    /** 4 个配色按钮：路径 / 标签 / 风格 / 属性。 */
    private fun makeSchemeRow(): LinearLayout {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.HORIZONTAL

        val schemes = listOf(
            "路径" to ColorScheme.PATH,
            "标签" to ColorScheme.TAG,
            "风格" to ColorScheme.STYLE,
            "属性" to ColorScheme.ATTRIBUTE
        )
        schemes.forEach { (label, scheme) ->
            val btn = TextView(context)
            btn.text = label
            btn.textSize = 13f
            btn.setTextColor(TEXT_PRIMARY)
            btn.gravity = Gravity.CENTER
            btn.setPadding(0, dp(10).toInt(), 0, dp(10).toInt())
            val lp = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            lp.marginEnd = dp(6).toInt()
            btn.layoutParams = lp
            btn.setOnClickListener {
                if (params.colorScheme != scheme) {
                    applyParams(params.copy(colorScheme = scheme), notify = true)
                }
            }
            schemeButtons[scheme] = btn
            row.addView(btn)
        }
        return row
    }

    /** 混音台滑块：管道 ◄══●══► 作品 → params.mixerPosition (0~1)。 */
    private fun makeMixerRow(): View {
        val col = LinearLayout(context)
        col.orientation = LinearLayout.VERTICAL

        val caption = TextView(context)
        caption.text = "管道 ◄══●══► 作品"
        caption.textSize = 13f
        caption.setTextColor(TEXT_SECONDARY)
        caption.gravity = Gravity.CENTER_HORIZONTAL
        col.addView(caption)

        col.addView(makeSliderRow("混音台", 0.0f, 1.0f, 2,
            { it.mixerPosition }, { p, v -> p.copy(mixerPosition = v) }))
        return col
    }

    private fun makeSliderRow(
        label: String,
        min: Float,
        max: Float,
        decimals: Int,
        getter: (TemplateParams) -> Float,
        setter: (TemplateParams, Float) -> TemplateParams
    ): View {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = Gravity.CENTER_VERTICAL
        row.setPadding(0, dp(2).toInt(), 0, dp(2).toInt())

        val labelView = TextView(context)
        labelView.text = label
        labelView.textSize = 13f
        labelView.setTextColor(TEXT_SECONDARY)
        labelView.layoutParams = LinearLayout.LayoutParams(dp(76).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
        row.addView(labelView)

        val seekBar = SeekBar(context)
        seekBar.max = SEEKBAR_MAX
        seekBar.layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        row.addView(seekBar)

        val valueView = TextView(context)
        valueView.textSize = 12f
        valueView.setTextColor(TEXT_PRIMARY)
        valueView.gravity = Gravity.END
        valueView.layoutParams = LinearLayout.LayoutParams(dp(48).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
        row.addView(valueView)

        val binding = SliderBinding(seekBar, valueView, min, max, decimals, getter, setter)
        sliders.add(binding)

        seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar?, progress: Int, fromUser: Boolean) {
                if (internalUpdate) return
                val value = binding.toValue(progress)
                valueView.text = binding.format(value)
                if (fromUser) {
                    presetAnimator?.cancel()
                    applyParams(setter(params, value), notify = true, refreshSliders = false)
                }
            }

            override fun onStartTrackingTouch(sb: SeekBar?) {}
            override fun onStopTrackingTouch(sb: SeekBar?) {}
        })
        return row
    }

    // ------------------------------------------------------------------
    // 参数应用 / 动画过渡
    // ------------------------------------------------------------------

    /** 应用参数：刷新控件、按需回调、记录当前值。 */
    private fun applyParams(
        newParams: TemplateParams,
        notify: Boolean,
        refreshSliders: Boolean = true
    ) {
        params = newParams
        if (refreshSliders) refreshControls(newParams)
        refreshSchemeButtons(newParams.colorScheme)
        if (notify) onParamsChanged?.invoke(newParams)
    }

    /** 预设切换：数值字段 ValueAnimator 平滑过渡，不跳变（第五节验收标准）。 */
    private fun animateToParams(target: TemplateParams) {
        presetAnimator?.cancel()
        val from = params

        // 配色为离散值，立即切换并高亮对应按钮（SOUL 无按钮，仅清除高亮）。
        refreshSchemeButtons(target.colorScheme)

        val animator = ValueAnimator.ofFloat(0f, 1f)
        animator.duration = PRESET_ANIM_DURATION
        animator.interpolator = DecelerateInterpolator()
        animator.addUpdateListener { va ->
            val t = va.animatedValue as Float
            fun lerp(a: Float, b: Float): Float = a + (b - a) * t
            applyParams(
                TemplateParams(
                    nodeBaseSize = lerp(from.nodeBaseSize, target.nodeBaseSize),
                    textOpacity = lerp(from.textOpacity, target.textOpacity),
                    edgeThickness = lerp(from.edgeThickness, target.edgeThickness),
                    edgeLength = lerp(from.edgeLength, target.edgeLength),
                    centripetal = lerp(from.centripetal, target.centripetal),
                    repulsion = lerp(from.repulsion, target.repulsion),
                    attraction = lerp(from.attraction, target.attraction),
                    layoutSpeed = lerp(from.layoutSpeed, target.layoutSpeed),
                    colorScheme = target.colorScheme,
                    mixerPosition = lerp(from.mixerPosition, target.mixerPosition)
                ),
                notify = true
            )
        }
        animator.start()
        presetAnimator = animator
    }

    /** 把所有滑块位置/数值标签同步到给定参数（预设动画帧 & 恢复时用）。 */
    private fun refreshControls(p: TemplateParams) {
        internalUpdate = true
        sliders.forEach { b ->
            val v = b.getter(p)
            b.seekBar.progress = b.toProgress(v)
            b.valueLabel.text = b.format(v)
        }
        internalUpdate = false
    }

    private fun refreshSchemeButtons(active: ColorScheme) {
        schemeButtons.forEach { (scheme, btn) ->
            val isActive = scheme == active
            btn.background = GradientDrawable().apply {
                setColor(if (isActive) BTN_BG_ACTIVE else BTN_BG)
                cornerRadius = dp(10)
            }
            btn.setTextColor(if (isActive) ACCENT else TEXT_PRIMARY)
        }
    }

    /** API 31+ 对 blurTarget 施加高斯模糊；否则仅半透明遮罩（零破坏回退）。 */
    private fun applyBlur(enable: Boolean) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val target = blurTarget ?: return
            if (enable) {
                target.setRenderEffect(
                    RenderEffect.createBlurEffect(dp(12), dp(12), Shader.TileMode.CLAMP)
                )
            } else {
                target.setRenderEffect(null)
            }
        }
    }

    // ------------------------------------------------------------------
    // SharedPreferences 存储（键 graph_params）
    // ------------------------------------------------------------------

    private fun encode(p: TemplateParams): String = buildString {
        append("nodeBaseSize=").append(p.nodeBaseSize).append(';')
        append("textOpacity=").append(p.textOpacity).append(';')
        append("edgeThickness=").append(p.edgeThickness).append(';')
        append("edgeLength=").append(p.edgeLength).append(';')
        append("centripetal=").append(p.centripetal).append(';')
        append("repulsion=").append(p.repulsion).append(';')
        append("attraction=").append(p.attraction).append(';')
        append("layoutSpeed=").append(p.layoutSpeed).append(';')
        append("colorScheme=").append(p.colorScheme.name).append(';')
        append("mixerPosition=").append(p.mixerPosition)
    }

    private fun decode(raw: String): TemplateParams {
        val map = raw.split(';')
            .mapNotNull {
                val idx = it.indexOf('=')
                if (idx <= 0) null else it.substring(0, idx) to it.substring(idx + 1)
            }
            .toMap()
        fun f(key: String, def: Float): Float = map[key]?.toFloatOrNull() ?: def
        val scheme = map["colorScheme"]?.let { name ->
            runCatching { ColorScheme.valueOf(name) }.getOrNull()
        } ?: ColorScheme.TAG
        return TemplateParams(
            nodeBaseSize = f("nodeBaseSize", 1.0f),
            textOpacity = f("textOpacity", 0.7f),
            edgeThickness = f("edgeThickness", 2.0f),
            edgeLength = f("edgeLength", 180f),
            centripetal = f("centripetal", 0.5f),
            repulsion = f("repulsion", 0.5f),
            attraction = f("attraction", 0.5f),
            layoutSpeed = f("layoutSpeed", 0.5f),
            colorScheme = scheme,
            mixerPosition = f("mixerPosition", 0.5f)
        )
    }

    private fun saveParams(p: TemplateParams) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_PARAMS, encode(p))
            .apply()
    }

    private fun loadParams(): TemplateParams {
        val raw = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_PARAMS, null) ?: return TemplateParams()
        return runCatching { decode(raw) }.getOrDefault(TemplateParams())
    }

    private fun dp(value: Number): Float =
        value.toFloat() * context.resources.displayMetrics.density
}
