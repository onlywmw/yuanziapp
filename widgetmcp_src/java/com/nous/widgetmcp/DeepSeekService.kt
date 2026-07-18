package com.nous.widgetmcp

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class DSBalance(
    val currency: String,
    val totalBalance: String,
    val grantedBalance: String,
    val toppedUpBalance: String
)

class DeepSeekService(private val apiKey: String) {

    companion object { private const val TIMEOUT = 10_000; private const val MAX_RETRIES = 2 }

    fun fetchBalance(): DSBalance? {
        var lastError: Exception? = null
        repeat(MAX_RETRIES) { attempt ->
            try {
                val conn = (URL("https://api.deepseek.com/user/balance").openConnection() as HttpURLConnection).apply {
                    setRequestProperty("Authorization", "Bearer $apiKey")
                    connectTimeout = TIMEOUT; readTimeout = TIMEOUT
                }
                if (conn.responseCode != 200) {
                    val code = conn.responseCode
                    conn.disconnect()
                    throw when (code) { 401 -> Exception("API Key 无效") else -> Exception("HTTP $code") }
                }
                val body = conn.inputStream.bufferedReader().readText()
                conn.disconnect()
                val json = JSONObject(body)
                val infos = json.getJSONArray("balance_infos")
                for (i in 0 until infos.length()) {
                    val info = infos.getJSONObject(i)
                    if (info.getString("currency").equals("CNY", true))
                        return DSBalance("CNY", info.getString("total_balance"),
                            info.getString("granted_balance"), info.getString("topped_up_balance"))
                }
                return null
            } catch (e: Exception) {
                lastError = e
                if (attempt < MAX_RETRIES - 1) Thread.sleep(1000L * (attempt + 1))
            }
        }
        throw lastError ?: Exception("Unknown error")
    }
}
