package com.company.cloudctl.companion.device

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Environment
import android.os.StatFs
import com.company.cloudctl.companion.model.DeviceHealth
import java.time.Instant

class LocalHealthCollector(private val context: Context) {
    fun collect(): DeviceHealth {
        val battery = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, 0) ?: 0
        val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, 100)?.coerceAtLeast(1) ?: 100
        val status = battery?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val temperature = battery?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
            ?.takeUnless { it == Int.MIN_VALUE }
            ?.div(10f)
        val connectivity = context.getSystemService(ConnectivityManager::class.java)
        val capabilities = connectivity.getNetworkCapabilities(connectivity.activeNetwork)
        val network = when {
            capabilities == null -> "Offline"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "Wi-Fi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "Cellular"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "Ethernet"
            else -> "Connected"
        }
        return DeviceHealth(
            batteryPercent = (level * 100 / scale).coerceIn(0, 100),
            charging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL,
            network = network,
            temperatureCelsius = temperature,
            freeStorageBytes = StatFs(Environment.getDataDirectory().path).availableBytes,
            executorVersion = packageVersion(context.packageName),
            companionVersion = packageVersion(context.packageName),
            observedAt = Instant.now(),
        )
    }

    @Suppress("DEPRECATION")
    private fun packageVersion(packageName: String): String {
        if (packageName.isBlank()) return "未配置"
        return runCatching {
            context.packageManager.getPackageInfo(packageName, 0).versionName ?: "已安装"
        }.getOrElse { "未安装" }
    }
}
