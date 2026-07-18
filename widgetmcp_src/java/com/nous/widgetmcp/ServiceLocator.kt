package com.nous.widgetmcp

import android.app.Application
import android.util.Log
import com.nous.widgetmcp.data.repo.WidgetRepositoryImpl
import com.nous.widgetmcp.domain.contract.WidgetRepository
import com.nous.widgetmcp.domain.usecase.WidgetController
import com.nous.widgetmcp.yuanzi.YuanziConfig
import java.io.File

/**
 * [DI容器] 手动服务定位器
 *
 * 初始化在 Application.onCreate (主线程) 完成。
 * getter 不做 lazy fallback — 未初始化时抛异常 (真 Fail-Fast)。
 */
object ServiceLocator {

    lateinit var app: Application
        private set

    var bootTime: Long = 0
        private set

    @Volatile private var _repository: WidgetRepository? = null
    @Volatile private var _controller: WidgetController? = null

    val repository: WidgetRepository get() = _repository
        ?: throw IllegalStateException("ServiceLocator 未初始化！")

    val controller: WidgetController get() = _controller
        ?: throw IllegalStateException("ServiceLocator 未初始化！")

    fun init(application: Application) {
        app = application
        bootTime = System.currentTimeMillis()
        AppLogger.init(File(app.filesDir, "logs"))
        CredentialStore.init(app)
        YuanziConfig.init(app)
        AppLogger.i("INIT", "starting")

        // [核心] 存储层
        WidgetInstanceManager.init(app)
        WidgetStateStore.init(app)
        _repository = WidgetRepositoryImpl()
        AppLogger.i("INIT", "repository ok")

        // [核心] 业务控制器
        _controller = WidgetController(_repository!!)
        AppLogger.i("INIT", "controller ok")
    }
}
