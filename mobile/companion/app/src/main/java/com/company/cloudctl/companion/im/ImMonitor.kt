package com.company.cloudctl.companion.im

import java.security.MessageDigest
import java.time.Instant
import java.time.LocalTime

/**
 * Monitored platform identity for a notification (pa-im/20260913.1 + slice 2).
 * Slice 2 maps platform keys to packages; extraction stays generic:
 * title = peer identity, text = body (Xianyu titles the notification with the peer).
 */
data class ImEvent(
    val platform: String,
    val peerName: String,
    val text: String,
    val occurredAt: Instant,
) {
    val peerKey: String get() = peerName.trim()

    fun dedupeKey(deviceId: String): String {
        val bucket = occurredAt.epochSecond
        val raw = "$deviceId|$platform|$peerKey|$bucket|$text"
        return MessageDigest.getInstance("SHA-256")
            .digest(raw.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }
}

/** Runtime monitor configuration mirrored from the cloud (device-scoped). */
data class ImMonitorConfig(
    val enabled: Boolean = true,
    val platforms: Set<String> = setOf(PLATFORM_XIANYU),
    val mode: String = MODE_NOTIFICATION,
    val dutyStart: String = "09:00",
    val dutyEnd: String = "23:00",
) {
    fun dutyActive(now: LocalTime = LocalTime.now()): Boolean {
        if (mode != MODE_DUTY) return false
        val start = LocalTime.parse(dutyStart)
        val end = LocalTime.parse(dutyEnd)
        return if (start <= end) now >= start && now < end else now >= start || now < end
    }

    companion object {
        const val MODE_NOTIFICATION = "NOTIFICATION"
        const val MODE_DUTY = "DUTY"
        const val PLATFORM_XIANYU = "xianyu"
        const val PLATFORM_XHS = "xhs"
        const val PLATFORM_DOUYIN = "douyin"
        const val PLATFORM_WECHAT = "wechat"

        /**
         * DM-like channels only for platforms whose push feed also notifies;
         * Xianyu DM notifications carry no distinguishing channel (all accepted).
         */
        fun isChannelAllowed(platform: String, channelId: String?): Boolean {
            if (platform == PLATFORM_XIANYU) return true
            val id = channelId?.lowercase() ?: return false
            return listOf("message", "msg", "im", "chat", "私信").any { it in id }
        }

        /** Platform key by notification package. */
        fun platformOfPackage(pkg: String): String? = when (pkg) {
            "com.taobao.idlefish" -> PLATFORM_XIANYU
            "com.xingin.xhs" -> PLATFORM_XHS
            "com.ss.android.ugc.aweme" -> PLATFORM_DOUYIN
            "com.tencent.mm" -> PLATFORM_WECHAT
            else -> null
        }
    }
}

/**
 * In-memory dedupe + pending queue + live config. The companion loop drains
 * batches; delivery failures never block task execution.
 */
object ImMonitor {
    private const val LRU_LIMIT = 512
    private const val QUEUE_LIMIT = 200

    @Volatile
    var config: ImMonitorConfig = ImMonitorConfig()
        private set

    fun applyConfig(next: ImMonitorConfig) {
        config = next
    }

    /** A notification from this package is monitored only if its platform is selected. */
    fun isPackageEnabled(pkg: String): Boolean {
        val platform = ImMonitorConfig.platformOfPackage(pkg) ?: return false
        return config.enabled && platform in config.platforms
    }

    private val recentKeys = object : LinkedHashMap<String, Boolean>(64, 0.75f, false) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Boolean>?): Boolean =
            size > LRU_LIMIT
    }
    private val pending = ArrayDeque<ImEvent>()

    @Synchronized
    fun accept(deviceId: String, event: ImEvent): Boolean {
        val key = event.dedupeKey(deviceId)
        if (recentKeys.containsKey(key)) return false
        recentKeys[key] = true
        if (pending.size >= QUEUE_LIMIT) pending.removeFirst()
        pending.addLast(event)
        return true
    }

    @Synchronized
    fun drain(max: Int): List<ImEvent> {
        val batch = buildList {
            while (size < max && pending.isNotEmpty()) add(pending.removeFirst())
        }
        return batch
    }

    @Synchronized
    fun requeue(events: List<ImEvent>) {
        events.reversed().forEach { pending.addFirst(it) }
    }

    @Synchronized
    fun pendingCount(): Int = pending.size
}
