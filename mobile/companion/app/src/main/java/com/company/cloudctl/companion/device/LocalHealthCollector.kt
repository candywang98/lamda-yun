package com.company.cloudctl.companion.device

import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.StatFs
import android.provider.Settings
import com.company.cloudctl.companion.ime.CloudCtlInputMethod
import com.company.cloudctl.companion.ime.InputRoutePolicy
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

    // -----------------------------------------------------------------------
    // B11 slice (fleet-identity/v1@20260916.1 §2): readiness dimensions are
    // collected and reported SEPARATELY — enabled (secure setting), active
    // (bound service instance), IME ready, screen unlocked, engine version —
    // so the claim gate and the heartbeat payload never conflate them.
    // -----------------------------------------------------------------------

    /**
     * @param transportOnline presence heartbeat seen (online, owned by the
     *   caller — the collector cannot observe it locally)
     * @param activeAccessibilityService probe for the bound accessibility
     *   instance (e.g. `CloudCtlAccessibilityService::active`); passed in so
     *   this collector stays JVM-testable and decoupled from automation/
     */
    fun collectReadiness(
        transportOnline: Boolean,
        activeAccessibilityService: () -> Any?,
        engineVersion: Int = ClaimEligibilityPolicy.ENGINE_FLOOR,
    ): RuntimeReadinessSnapshot = RuntimeReadinessSnapshot(
        transportOnline = transportOnline,
        accessibilityEnabled = accessibilityEnabledBySettings(),
        accessibilityActive = activeAccessibilityService() != null,
        imeReady = inputCapabilityReady(activeAccessibilityService() != null),
        screenUnlocked = context.getSystemService(KeyguardManager::class.java)?.isKeyguardLocked != true,
        engineVersion = engineVersion,
        observedAtEpochMillis = System.currentTimeMillis(),
    )

    private fun accessibilityEnabledBySettings(): Boolean {
        val enabled = runCatching {
            Settings.Secure.getString(context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES)
        }.getOrNull().orEmpty()
        val relative = ".automation.CloudCtlAccessibilityService"
        val wanted = setOf(
            "${context.packageName}/${context.packageName}$relative",
            "${context.packageName}/$relative",
        )
        return enabled.split(':').any { item -> wanted.any { it.equals(item, ignoreCase = true) } }
    }

    /**
     * API 33+ can type through the accessibility editor, so an active service is
     * enough. API 30–32 need CloudCtl enabled (the switch is temporary). API 29
     * still needs it selected. Editor binding stays a runtime check.
     */
    private fun inputCapabilityReady(accessibilityActive: Boolean): Boolean {
        val enabled = runCatching { CloudCtlInputMethod.isEnabled(context) }.getOrDefault(false)
        val selected = runCatching { CloudCtlInputMethod.isSelected(context) }.getOrDefault(false)
        return InputRoutePolicy.ready(Build.VERSION.SDK_INT, accessibilityActive, enabled, selected)
    }
}

/** Per-dimension runtime readiness (§2: online 与 executable 分离，维度各自上报). */
data class RuntimeReadinessSnapshot(
    val transportOnline: Boolean,
    val accessibilityEnabled: Boolean,
    val accessibilityActive: Boolean,
    val imeReady: Boolean,
    val screenUnlocked: Boolean,
    val engineVersion: Int,
    val observedAtEpochMillis: Long,
)

/** Closed capability key set (fleet-identity/v1 §3, V1). */
enum class RequiredCapability { ACCESSIBILITY, IME, SCREEN_CAPTURE, MEDIA_PROJECTION, FLUTTER_ANCHORS, IM_LISTEN }

sealed interface ClaimEligibility {
    data object Eligible : ClaimEligibility
    data class Ineligible(val reasonCode: String) : ClaimEligibility
}

/**
 * B11 任务 4 领取门：输入（IME）与无障碍未就绪时不领取需要它们的任务。
 * §2 executable 门（transport ∧ accessibility enabled∧active ∧ IME ∧
 * screen-unlocked ∧ engine ≥ min）按维度逐项判定；不需要某能力的任务
 * （如纯 im_listen）不被该能力拖累（§3 能力求交语义）。
 */
object ClaimEligibilityPolicy {
    const val ENGINE_FLOOR = 1

    fun executable(
        snapshot: RuntimeReadinessSnapshot,
        requiredEngine: Int = ENGINE_FLOOR,
    ): Boolean = snapshot.transportOnline &&
        snapshot.accessibilityEnabled &&
        snapshot.accessibilityActive &&
        snapshot.imeReady &&
        snapshot.screenUnlocked &&
        snapshot.engineVersion >= requiredEngine

    fun shouldClaim(
        snapshot: RuntimeReadinessSnapshot,
        taskRequires: Set<RequiredCapability>,
        requiredEngine: Int = ENGINE_FLOOR,
    ): ClaimEligibility = when {
        !snapshot.transportOnline -> ClaimEligibility.Ineligible("TRANSPORT_OFFLINE")
        RequiredCapability.ACCESSIBILITY in taskRequires && !snapshot.accessibilityEnabled ->
            ClaimEligibility.Ineligible("ACCESSIBILITY_NOT_ENABLED")
        RequiredCapability.ACCESSIBILITY in taskRequires && !snapshot.accessibilityActive ->
            ClaimEligibility.Ineligible("ACCESSIBILITY_NOT_ACTIVE")
        RequiredCapability.IME in taskRequires && !snapshot.imeReady ->
            ClaimEligibility.Ineligible("IME_NOT_READY")
        !snapshot.screenUnlocked -> ClaimEligibility.Ineligible("SCREEN_LOCKED")
        snapshot.engineVersion < requiredEngine -> ClaimEligibility.Ineligible("ENGINE_BELOW_MIN")
        else -> ClaimEligibility.Eligible
    }
}

/** One health alert entry; identity for merging = key + digest. */
data class HealthAlert(
    val key: String,
    val digest: String,
    val severity: String,
    val occurredAtMillis: Long,
)

/** A merged alert slot: same key+digest inside the window coalesces into one upload. */
data class HealthAlertSlot(
    val alert: HealthAlert,
    val mergedCount: Int,
    val firstSeenAtMillis: Long,
    val lastSeenAtMillis: Long,
)

/**
 * B11 任务 4：健康上报合并 + 断网缓存上限。同一 key+digest 在合并窗口内
 * 反复出现的告警只占一个槽位（mergedCount 累加，上报一次）；缓存有硬上
 * 限，超限丢最旧——断网期间多设备告警不会无限堆积，恢复后也不会以风暴
 * 形式重放。
 */
class HealthReportBuffer(
    private val capacity: Int = DEFAULT_CAPACITY,
    private val mergeWindowMillis: Long = DEFAULT_MERGE_WINDOW_MILLIS,
) {
    init {
        require(capacity > 0) { "capacity must be positive" }
        require(mergeWindowMillis >= 0) { "mergeWindowMillis must not be negative" }
    }

    private val slots = ArrayDeque<HealthAlertSlot>()

    fun add(alert: HealthAlert, nowMillis: Long): HealthAlertSlot {
        val existing = slots.firstOrNull {
            it.alert.key == alert.key && it.alert.digest == alert.digest &&
                nowMillis - it.lastSeenAtMillis <= mergeWindowMillis
        }
        if (existing != null) {
            val merged = HealthAlertSlot(
                alert = alert,
                mergedCount = existing.mergedCount + 1,
                firstSeenAtMillis = existing.firstSeenAtMillis,
                lastSeenAtMillis = nowMillis,
            )
            slots.remove(existing)
            slots.addLast(merged)
            return merged
        }
        if (slots.size >= capacity) slots.removeFirst()
        val slot = HealthAlertSlot(alert, 1, nowMillis, nowMillis)
        slots.addLast(slot)
        return slot
    }

    fun snapshot(): List<HealthAlertSlot> = slots.toList()

    fun drain(): List<HealthAlertSlot> = slots.toList().also { slots.clear() }

    fun size(): Int = slots.size

    companion object {
        const val DEFAULT_CAPACITY = 128
        const val DEFAULT_MERGE_WINDOW_MILLIS = 60_000L
    }
}

/**
 * B11 任务 4：网络退避 + jitter。指数退避乘以 [JITTER_FLOOR, JITTER_CEIL]
 * 区间的随机因子——同批失败的多设备重连时刻被抖开，不构成重试风暴；
 * [attemptsWithin] 给出窗口内单设备尝试次数的上界（按最快 jitter 下界
 * 计算），供风暴断言使用。
 */
class ReconnectBackoff(
    private val initialDelayMillis: Long = 1_000L,
    private val maximumDelayMillis: Long = 60_000L,
    private val jitter: () -> Double = { kotlin.random.Random.nextDouble(JITTER_FLOOR, JITTER_CEIL) },
) {
    init {
        require(initialDelayMillis > 0) { "initialDelayMillis must be positive" }
        require(maximumDelayMillis >= initialDelayMillis) { "maximumDelayMillis must be >= initialDelayMillis" }
    }

    private var failures = 0

    fun nextDelayMillis(): Long {
        val exponent = kotlin.math.min(failures, MAX_EXPONENT)
        val base = kotlin.math.min(initialDelayMillis * (1L shl exponent), maximumDelayMillis)
        failures += 1
        return (base * jitter()).toLong().coerceIn(1L, maximumDelayMillis)
    }

    fun reset() {
        failures = 0
    }

    /** Upper bound of consecutive attempts whose total (fastest) delay fits the window. */
    fun attemptsWithin(windowMillis: Long): Int {
        var total = 0L
        var count = 0
        var exponent = 0
        while (count < HARD_ATTEMPT_CAP) {
            val base = kotlin.math.min(initialDelayMillis * (1L shl exponent), maximumDelayMillis)
            val fastest = (base * JITTER_FLOOR).toLong().coerceAtLeast(1L)
            if (total + fastest > windowMillis) break
            total += fastest
            count += 1
            exponent = kotlin.math.min(exponent + 1, MAX_EXPONENT)
        }
        return count
    }

    companion object {
        const val JITTER_FLOOR = 0.8
        const val JITTER_CEIL = 1.2
        private const val MAX_EXPONENT = 16
        private const val HARD_ATTEMPT_CAP = 10_000
    }
}
