package com.company.cloudctl.companion.im

import java.security.MessageDigest
import java.time.Instant

/**
 * Monitored idlefish IM notification (pa-im/20260913.1). Peer identity comes from the
 * notification title; the payload text is the message body.
 */
data class ImEvent(
    val peerName: String,
    val text: String,
    val occurredAt: Instant,
) {
    val peerKey: String get() = peerName.trim()

    fun dedupeKey(deviceId: String): String {
        val bucket = occurredAt.epochSecond
        val raw = "$deviceId|$peerKey|$bucket|$text"
        return MessageDigest.getInstance("SHA-256")
            .digest(raw.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }
}

/**
 * In-memory dedupe + pending queue. The companion loop drains batches; delivery
 * failures never block task execution (callers retry on the next cycle).
 */
object ImMonitor {
    private const val LRU_LIMIT = 512
    private const val QUEUE_LIMIT = 200

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
