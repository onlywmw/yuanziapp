package com.nous.widgetmcp

import android.content.Context
import android.content.SharedPreferences

/**
 * 凭据存储 — M1 用 SharedPreferences, M2 升级 EncryptedSharedPreferences
 */
object CredentialStore {
    private var prefs: SharedPreferences? = null

    fun init(context: Context) {
        prefs = context.getSharedPreferences("cred_store", Context.MODE_PRIVATE)
    }

    fun put(credentialId: String, key: String, value: String) {
        // 同步落盘：pin 流程写完后进程可能被 MIUI 立即冻结/杀死，apply() 会丢
        prefs?.edit()?.putString("$credentialId:$key", value)?.commit()
    }

    fun get(credentialId: String, key: String): String? {
        return prefs?.getString("$credentialId:$key", null)
    }

    fun delete(credentialId: String) {
        prefs?.edit().also { edit ->
            prefs?.all?.keys?.filter { it.startsWith("$credentialId:") }?.forEach { edit?.remove(it) }
            edit?.apply()
        }
    }
}
