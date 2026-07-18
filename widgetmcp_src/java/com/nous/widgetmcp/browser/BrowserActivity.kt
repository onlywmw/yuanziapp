package com.nous.widgetmcp.browser

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.KeyEvent
import android.view.inputmethod.EditorInfo
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
import com.nous.widgetmcp.AppLogger
import com.nous.widgetmcp.R
import com.nous.widgetmcp.WidgetExecutor
import com.nous.widgetmcp.hermes.HermesApi

class BrowserActivity : Activity() {

    private lateinit var webView: WebView
    private lateinit var urlInput: EditText
    private lateinit var statusText: TextView

    private var restoredUrl: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_browser)

        webView = findViewById(R.id.webView)
        urlInput = findViewById(R.id.urlInput)
        statusText = findViewById(R.id.statusText)

        setupWebView()
        setupControls()

        savedInstanceState?.let { bundle ->
            restoredUrl = bundle.getString(KEY_CURRENT_URL)
            @Suppress("DEPRECATION")
            webView.restoreState(bundle)
        }

        updateStatus("浏览器就绪")
        handleIntentCommand(intent, fromCreate = true)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntentCommand(intent, fromCreate = false)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        @Suppress("DEPRECATION")
        webView.saveState(outState)
        outState.putString(KEY_CURRENT_URL, webView.url ?: urlInput.text.toString())
    }

    private fun setupWebView() {
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            javaScriptCanOpenWindowsAutomatically = false
        }
        webView.webChromeClient = WebChromeClient()
        webView.addJavascriptInterface(BrowserBridge(this), BrowserBridge.NAME)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                request?.url?.toString()?.let { url ->
                    urlInput.setText(url)
                    reportUrlChange(url)
                }
                return false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                updateStatus("加载完成: ${url ?: ""}")
                url?.let { reportPageLoaded(it, view?.title ?: "") }
                injectClickTracker()
            }
        }
    }

    private fun setupControls() {
        urlInput.setOnEditorActionListener { _, actionId, event ->
            if (actionId == EditorInfo.IME_ACTION_GO ||
                (event?.keyCode == KeyEvent.KEYCODE_ENTER && event.action == KeyEvent.ACTION_DOWN)
            ) {
                navigateToInputUrl()
                true
            } else false
        }

        findViewById<Button>(R.id.goBtn).setOnClickListener { navigateToInputUrl() }
        findViewById<Button>(R.id.backBtn).setOnClickListener {
            if (webView.canGoBack()) webView.goBack()
        }
        findViewById<Button>(R.id.forwardBtn).setOnClickListener {
            if (webView.canGoForward()) webView.goForward()
        }
        findViewById<Button>(R.id.reloadBtn).setOnClickListener { webView.reload() }
        findViewById<Button>(R.id.homeBtn).setOnClickListener {
            urlInput.setText("")
            webView.loadUrl("about:blank")
        }
    }

    private fun navigateToInputUrl() {
        var url = urlInput.text.toString().trim()
        if (url.isEmpty()) return
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "https://$url"
            urlInput.setText(url)
        }
        updateStatus("正在加载: $url")
        webView.loadUrl(url)
    }

    private fun handleIntentCommand(intent: Intent?, fromCreate: Boolean) {
        val toolId = intent?.getStringExtra("command_tool_id")
        val eventId = intent?.getIntExtra("command_event_id", -1) ?: -1
        val url = intent?.getStringExtra("arg_url") ?: ""

        if (toolId.isNullOrEmpty()) {
            if (fromCreate && webView.url == null && !restoredUrl.isNullOrEmpty()) {
                urlInput.setText(restoredUrl)
                webView.loadUrl(restoredUrl!!)
            }
            return
        }

        AppLogger.i("BROWSER", "handle command $toolId event=$eventId url=$url")

        when (toolId) {
            "browser/open", "browser/navigate" -> {
                if (url.isNotEmpty()) {
                    urlInput.setText(url)
                    webView.loadUrl(url)
                }
            }
            "browser/back" -> if (webView.canGoBack()) webView.goBack()
            "browser/forward" -> if (webView.canGoForward()) webView.goForward()
            "browser/reload" -> webView.reload()
        }
    }

    private fun injectClickTracker() {
        val js = """
            document.addEventListener('click', function(e) {
                var el = e.target;
                var id = el.id || el.className || el.tagName;
                window.WidgetMcpBridge.reportClick(id, e.clientX, e.clientY, window.location.href);
            }, true);
            window.WidgetMcpBridge.reportUrlChange(window.location.href);
        """.trimIndent()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            webView.evaluateJavascript(js, null)
        } else {
            @Suppress("DEPRECATION")
            webView.loadUrl("javascript:$js")
        }
    }

    private fun reportPageLoaded(url: String, title: String) {
        WidgetExecutor.pool.submit {
            HermesApi.reportEvent(
                com.nous.widgetmcp.hermes.HermesEvent(
                    source = "app",
                    toolId = "browser/page_loaded",
                    args = mapOf("url" to url, "title" to title)
                )
            )
        }
    }

    private fun reportUrlChange(url: String) {
        WidgetExecutor.pool.submit {
            HermesApi.reportEvent(
                com.nous.widgetmcp.hermes.HermesEvent(
                    source = "app",
                    toolId = "browser/url_changed",
                    args = mapOf("url" to url)
                )
            )
        }
    }

    private fun updateStatus(message: String) {
        runOnUiThread { statusText.text = message }
        AppLogger.i("BROWSER", message)
    }

    companion object {
        private const val KEY_CURRENT_URL = "current_url"

        fun open(context: Context) {
            context.startActivity(Intent(context, BrowserActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            })
        }

        fun openWithCommand(context: Context, cmd: BrowserCommand) {
            val intent = Intent(context, BrowserActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("command_tool_id", cmd.toolId)
                putExtra("command_event_id", cmd.eventId)
                for ((key, value) in cmd.args) {
                    when (value) {
                        is String -> putExtra("arg_$key", value)
                        is Int -> putExtra("arg_$key", value)
                        is Double -> putExtra("arg_$key", value)
                        is Boolean -> putExtra("arg_$key", value)
                        else -> putExtra("arg_$key", value.toString())
                    }
                }
            }
            context.startActivity(intent)
        }
    }
}
