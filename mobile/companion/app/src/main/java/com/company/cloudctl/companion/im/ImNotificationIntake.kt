package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.data.ImOutboxStore
import java.time.Instant

/**
 * Turns one observed notification into a canonical [ImEvent] and a persistent
 * outbox row. Does not click, reply, or synthesize a notification.
 */
object ImNotificationIntake {
    const val OCCURRED_AT_SYNTHESIZED = "OCCURRED_AT_SYNTHESIZED"

    data class Observed(
        val platform: String,
        val peerName: String,
        val text: String,
        val occurredAt: Instant,
        val occurredAtSynthesized: Boolean,
    )

    fun observe(
        platform: String,
        title: String,
        body: String,
        whenMillis: Long,
        arrivedAtMillis: Long,
    ): Observed? {
        val peerName = title.trim()
        val text = body.trim()
        if (platform != ImMonitorConfig.PLATFORM_XIANYU) return null
        if (peerName.isEmpty() || peerName.length > 128 || text.isEmpty()) return null
        val synthesized = whenMillis <= 0L
        val occurredAt = Instant.ofEpochMilli(if (synthesized) arrivedAtMillis else whenMillis)
        return Observed(
            platform = platform,
            peerName = peerName,
            text = ImCanonicalText.canonical(text),
            occurredAt = occurredAt,
            occurredAtSynthesized = synthesized,
        )
    }

    fun accept(
        store: ImOutboxStore,
        deviceId: String?,
        observed: Observed,
        now: Instant = Instant.now(),
    ): ImEnqueueOutcome {
        val event = ImEvent(
            platform = observed.platform,
            peerName = observed.peerName,
            text = observed.text,
            occurredAt = observed.occurredAt,
        )
        val outcome = store.enqueue(deviceId, event, now)
        if (outcome.result == ImEnqueueResult.ENQUEUED || outcome.result == ImEnqueueResult.DUPLICATE) {
            remember(deviceId, event)
        }
        return outcome
    }

    /**
     * Memory LRU is an optimization in front of the persistent outbox. A miss
     * still enqueues; a hit still has to match a row that was already stored.
     * When [deviceId] is missing the memory key uses a placeholder that is
     * not a binding id, matching [ImOutboxStore.UNBOUND_DEVICE].
     */
    private fun remember(deviceId: String?, event: ImEvent) {
        val identity = deviceId?.takeIf { it.isNotBlank() } ?: ImOutboxStore.UNBOUND_DEVICE
        ImMonitor.noteAccepted(identity, event)
    }
}
