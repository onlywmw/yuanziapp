package com.nous.widgetmcp.hermes

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.SystemClock
import com.nous.widgetmcp.AppLogger

/**
 * AlarmManager 轮询触发器
 *
 * 动态频率策略：
 * - 默认闲置：60 秒
 * - 有正在执行的任务（Hermes status == executing）：10 秒
 * - 屏幕亮起时：立即触发一次并临时加速到 10 秒
 */
class HermesPollReceiver : BroadcastReceiver() {

    companion object {
        const val ACTION_POLL = "com.nous.widgetmcp.action.HERMES_POLL"
        const val EXTRA_SCREEN_ON = "screen_on"

        fun createIntent(context: Context, screenOn: Boolean = false): Intent {
            return Intent(context, HermesPollReceiver::class.java).apply {
                action = ACTION_POLL
                putExtra(EXTRA_SCREEN_ON, screenOn)
            }
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        if (action == Intent.ACTION_BOOT_COMPLETED) {
            AppLogger.i("HERMES_POLL", "boot completed")
            if (HermesConfig.enabled) HermesPollScheduler.scheduleNext(context)
            return
        }
        if (action != ACTION_POLL && action != Intent.ACTION_SCREEN_ON) return

        val screenOn = intent.getBooleanExtra(EXTRA_SCREEN_ON, false)
            || action == Intent.ACTION_SCREEN_ON
        AppLogger.i("HERMES_POLL", "trigger screenOn=$screenOn")

        // 启动前台服务执行同步
        HermesSyncService.start(context)

        // 亮屏时临时安排短间隔的下一轮
        if (screenOn) {
            HermesPollScheduler.schedule(context, HermesPollScheduler.FAST_INTERVAL_MS)
        }
    }
}

object HermesPollScheduler {
    const val DEFAULT_INTERVAL_MS = 60_000L
    const val FAST_INTERVAL_MS = 10_000L

    private const val REQ_CODE = 0x7001

    fun scheduleNext(context: Context) {
        val interval = resolveInterval(context)
        schedule(context, interval)
    }

    fun schedule(context: Context, intervalMs: Long) {
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = HermesPollReceiver.createIntent(context)
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        val pending = PendingIntent.getBroadcast(context, REQ_CODE, intent, flags)

        val triggerAt = SystemClock.elapsedRealtime() + intervalMs
        val canExact = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            am.canScheduleExactAlarms()
        } else true

        when {
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && canExact -> {
                am.setExactAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pending)
                AppLogger.i("HERMES_POLL", "scheduled exact in ${intervalMs}ms")
            }
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.M -> {
                // 无精确闹钟权限时用普通 wakeup（省电策略可能略有延迟，但不会崩溃）
                am.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pending)
                AppLogger.i("HERMES_POLL", "scheduled inexact in ${intervalMs}ms")
            }
            else -> {
                am.set(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pending)
                AppLogger.i("HERMES_POLL", "scheduled legacy in ${intervalMs}ms")
            }
        }
    }

    fun cancel(context: Context) {
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = HermesPollReceiver.createIntent(context)
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_NO_CREATE
        }
        val pending = PendingIntent.getBroadcast(context, REQ_CODE, intent, flags)
        if (pending != null) {
            am.cancel(pending)
            pending.cancel()
        }
    }

    private fun resolveInterval(context: Context): Long {
        // 未来可读取 Hermes status 或本地任务状态来决定；目前默认 60s
        return DEFAULT_INTERVAL_MS
    }
}
