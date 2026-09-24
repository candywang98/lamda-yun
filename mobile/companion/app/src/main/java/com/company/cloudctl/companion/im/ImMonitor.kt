package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.data.ImOutboxStore
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

    /**
     * SHA-256 of `deviceId|platform|peerKey|epochSecond|canonicalText`.
     * [text] is canonicalized here so a raw and an already-canonical body share one key.
     */
    fun dedupeKey(deviceId: String): String = ImDedupe.key(deviceId, this)
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
 * In-memory dedupe hint + live config. Reliability is the persistent IM
 * outbox, not this object: LRU eviction must not drop a stored event, and
 * the memory queue is no longer the upload path (pa-im-m3/20260922.1 §4).
 *
 * I10 still treats a same-source retransmission inside [RETRANSMIT_WINDOW_MS]
 * as already accepted, but only after the persistent outbox has the row.
 * Callers that have not stored the event must not use [noteAccepted].
 */
object ImMonitor {
    private const val LRU_LIMIT = 512

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

    /**
     * Process-wide outbox installed by the sync service. Null in unit tests
     * that only exercise the memory hint; production callers set it before
     * notifications or duty reads are accepted.
     */
    @Volatile
    var outbox: ImOutboxStore? = null

    /**
     * Record one inbound in the persistent outbox. Returns false when the
     * memory hint or the outbox already has it, the row is rejected, or the
     * outbox is not installed yet. Never drops an older stored row.
     */
    fun accept(deviceId: String, event: ImEvent, now: Instant = Instant.now()): Boolean {
        if (deviceId.isBlank()) return false
        val store = outbox ?: return false
        if (alreadyRecorded(deviceId, event)) return false
        // Enqueue outside the memory lock. The outbox unique key is the
        // reliability boundary if two callers pass the hint together.
        val outcome = store.enqueue(deviceId, event, now)
        if (outcome.result == ImEnqueueResult.ENQUEUED || outcome.result == ImEnqueueResult.DUPLICATE) {
            noteAccepted(deviceId, event)
        }
        return outcome.result == ImEnqueueResult.ENQUEUED
    }

    /**
     * Memory-only hint. True means this process already recorded the event in
     * the persistent outbox (exact key, or I10 retransmission of canonical text).
     * False means the caller must still consult the outbox.
     */
    @Synchronized
    fun alreadyRecorded(deviceId: String, event: ImEvent): Boolean = alreadyRecordedLocked(deviceId, event)

    /** Remember a row that the persistent outbox has accepted or already stored. */
    @Synchronized
    fun noteAccepted(deviceId: String, event: ImEvent) {
        noteAcceptedLocked(deviceId, event)
    }

    private fun alreadyRecordedLocked(deviceId: String, event: ImEvent): Boolean {
        val canonical = event.copy(text = ImCanonicalText.canonical(event.text))
        val key = canonical.dedupeKey(deviceId)
        if (recentKeys.containsKey(key)) return true
        val textKey = textIdentity(canonical)
        val lastAcceptedAt = recentByText[textKey] ?: return false
        val retransmitted = !canonical.occurredAt.isBefore(lastAcceptedAt) &&
            canonical.occurredAt.toEpochMilli() - lastAcceptedAt.toEpochMilli() < RETRANSMIT_WINDOW_MS
        if (retransmitted) recentKeys[key] = true
        return retransmitted
    }

    private fun noteAcceptedLocked(deviceId: String, event: ImEvent) {
        val canonical = event.copy(text = ImCanonicalText.canonical(event.text))
        recentKeys[canonical.dedupeKey(deviceId)] = true
        recentByText[textIdentity(canonical)] = canonical.occurredAt
    }

    private fun textIdentity(event: ImEvent): String =
        "${event.platform}|${event.peerKey}|${ImCanonicalText.canonical(event.text)}"

    /** Drops the in-memory hint only. Persistent rows are untouched. */
    @Synchronized
    internal fun resetForTest() {
        recentKeys.clear()
        recentByText.clear()
        outbox = null
    }
}
