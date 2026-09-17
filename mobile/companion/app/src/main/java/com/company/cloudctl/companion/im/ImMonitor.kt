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
         * DM-like channels only for platforms whose push feed also notifies.
         * Xianyu is governed by [ImFeedNoiseFilter] (channel calibration +
         * peer-name shape); this check accepts it and other platforms filter
         * by channel-id substring.
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
 *
 * I10 dedupe contract: an inbound is a retransmission when EITHER its exact
 * occurrence key (device|platform|peer|second-bucket|text) was seen, OR the
 * same source identity (platform|peer|text) was already accepted inside
 * [RETRANSMIT_WINDOW_MS] — the notification path re-posts the same push with a
 * regenerated timestamp and the duty reader re-reads the same unanswered
 * bubble with a fabricated now() clock, so the second bucket is never proof of
 * a fresh message. Retransmissions are dropped before the queue: no second
 * cloud IN row, no re-armed reply trigger.
 */
object ImMonitor {
    private const val LRU_LIMIT = 512
    private const val QUEUE_LIMIT = 200

    /** Same source identity re-observed inside this window is a retransmission. */
    const val RETRANSMIT_WINDOW_MS = 5 * 60_000L

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
    private val recentByText = object : LinkedHashMap<String, Instant>(64, 0.75f, false) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Instant>?): Boolean =
            size > LRU_LIMIT
    }
    private val pending = ArrayDeque<ImEvent>()

    @Synchronized
    fun accept(deviceId: String, event: ImEvent): Boolean {
        val key = event.dedupeKey(deviceId)
        if (recentKeys.containsKey(key)) return false
        // I10 retransmission window: identical (platform|peer|text) observed
        // again inside the window — a re-posted push or a duty re-read — is
        // never queued twice. Clock base is the event occurrence time: for the
        // duty reader that is the fabricated now(), so the window follows the
        // re-read cadence; an old-when notification re-post is already caught
        // by the exact occurrence key above.
        val textKey = "${event.platform}|${event.peerKey}|${event.text}"
        val lastAcceptedAt = recentByText[textKey]
        val retransmitted = lastAcceptedAt != null &&
            !event.occurredAt.isBefore(lastAcceptedAt) &&
            event.occurredAt.toEpochMilli() - lastAcceptedAt.toEpochMilli() < RETRANSMIT_WINDOW_MS
        if (retransmitted) {
            recentKeys[key] = true
            return false
        }
        recentKeys[key] = true
        recentByText[textKey] = event.occurredAt
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
