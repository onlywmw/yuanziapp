package com.nous.widgetmcp

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * 凭据存储 — EncryptedSharedPreferences（BUG-011：token 不再明文落盘）。
 *
 * 需要 Gradle 依赖：androidx.security:security-crypto:1.1.0-alpha06+
 * 若加密初始化失败（极端老设备），回退普通 SharedPreferences 并打印警告。
 */
object CredentialStore {
    private var prefs: SharedPreferences? = null

    fun init(context: Context) {
        prefs = try {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            EncryptedSharedPreferences.create(
                context,
                "cred_store",
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
        } catch (e: Exception) {
            android.util.Log.w("CredentialStore", "encrypted prefs unavailable, fallback to plain", e)
            context.getSharedPreferences("cred_store", Context.MODE_PRIVATE)
        }
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
