package com.nous.widgetmcp.browser

import android.content.Context
import android.webkit.JavascriptInterface
import com.nous.widgetmcp.AppLogger
import com.nous.widgetmcp.WidgetExecutor
import com.nous.widgetmcp.hermes.HermesApi
import com.nous.widgetmcp.hermes.HermesEvent

/**
 * JavaScript 桥接：把页面内的点击、URL 变化上报给 Hermes
 */
class BrowserBridge(private val context: Context) {

    companion object {
        const val NAME = "WidgetMcpBridge"
    }

    @JavascriptInterface
    fun reportClick(elementId: String, x: Int, y: Int, url: String) {
        AppLogger.i("BROWSER_JS", "click $elementId at ($x,$y) on $url")
        WidgetExecutor.pool.submit {
            HermesApi.reportEvent(
                HermesEvent(
                    source = "app",
                    toolId = "browser/click",
                    args = mapOf(
                        "element_id" to elementId,
                        "x" to x,
                        "y" to y,
                        "url" to url
                    )
                )
            )
        }
    }

    @JavascriptInterface
    fun reportUrlChange(url: String) {
        AppLogger.i("BROWSER_JS", "url change $url")
        WidgetExecutor.pool.submit {
            HermesApi.reportEvent(
                HermesEvent(
                    source = "app",
                    toolId = "browser/url_changed",
                    args = mapOf("url" to url)
                )
            )
        }
    }
}
