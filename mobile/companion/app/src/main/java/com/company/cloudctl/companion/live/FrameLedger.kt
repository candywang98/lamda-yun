package com.company.cloudctl.companion.live

import java.util.ArrayDeque

/**
 * Per-session frame metadata ledger (K13 live-capabilities/v1 §3/§4).
 *
 * Every frame the companion sends gets a strictly monotonic [FrameStamp.frameSeq]
 * and is stamped with the geometry it was captured under and the (monotonic)
 * send time. Remote inputs name the frame they were aimed at; the ledger
 * answers whether that frame is still fresh enough to act on:
 *
 *  - watermark staleness: `latestFrameSeq - inputFrameSeq > staleFrameThreshold`
 *    -> [FrameFreshness.StaleWatermark] (INPUT_EXPIRED, K13 §4 rule 2);
 *  - gesture TTL: the named frame was sent more than `ttlExpiryMs` ago (or is
 *    unknown / already evicted) -> [FrameFreshness.ExpiredTtl] (K13 §4 rule 3).
 *
 * Geometry changes (rotation / resolution change) are simply recorded on the
 * stamps from the next frameSeq on: an input is always validated against the
 * geometry of the exact frame it targeted, so inputs computed on a
 * pre-rotation frame are transformed with the pre-rotation tables and are
 * bounced by the freshness rules when they are too old (K13 §3: geometry
 * changes take effect from the new frameSeq).
 *
 * Pure Kotlin, JVM-unit-testable; the clock is injected.
 */
class FrameLedger(
    val policy: FramePolicy = FramePolicy(),
) {
    private val lock = Any()
    private val tracked = ArrayDeque<FrameStamp>()
    private val index = HashMap<Long, FrameStamp>()
    private var latestSeq = 0L

    val latestFrameSeq: Long get() = synchronized(lock) { latestSeq }

    /** Records the next outgoing frame; frameSeq is strictly increasing. */
    fun recordNext(geometry: FrameGeometry, nowMs: Long): FrameStamp = synchronized(lock) {
        latestSeq += 1
        val stamp = FrameStamp(frameSeq = latestSeq, geometry = geometry, sentAtMs = nowMs)
        tracked.addLast(stamp)
        index[stamp.frameSeq] = stamp
        while (tracked.size > policy.maxTrackedFrames) {
            tracked.pollFirst()?.let { index.remove(it.frameSeq) }
        }
        stamp
    }

    /**
     * K13 §4 rules 2 and 3 for the frame an input names. Rule 2 (watermark) is
     * evaluated first, mirroring the server-side order in fleet_live.check_input.
     */
    fun checkFreshness(frameSeq: Long, nowMs: Long): FrameFreshness = synchronized(lock) {
        if (latestSeq - frameSeq > policy.staleFrameThreshold) {
            return FrameFreshness.StaleWatermark(
                frameSeq = frameSeq,
                latestFrameSeq = latestSeq,
                threshold = policy.staleFrameThreshold,
            )
        }
        val stamp = index[frameSeq]
        if (stamp == null || nowMs - stamp.sentAtMs > policy.ttlExpiryMs) {
            return FrameFreshness.ExpiredTtl(
                frameSeq = frameSeq,
                ageMs = stamp?.let { nowMs - it.sentAtMs },
                ttlMs = policy.ttlExpiryMs,
            )
        }
        FrameFreshness.Fresh(stamp)
    }

    /** Snapshot of the tracked stamps (oldest first); for diagnostics/tests. */
    fun stamps(): List<FrameStamp> = synchronized(lock) { tracked.toList() }
}

/**
 * K13 §4 knob set; closed ranges per contract (staleFrameThreshold in [1,30],
 * ttlExpiryMs in [500,5000]). Defaults match the contract: 10 / 2000.
 */
data class FramePolicy(
    val staleFrameThreshold: Int = 10,
    val ttlExpiryMs: Long = 2_000,
    val maxTrackedFrames: Int = 64,
) {
    init {
        require(staleFrameThreshold in 1..30) { "staleFrameThreshold must be in [1,30]" }
        require(ttlExpiryMs in 500..5_000) { "ttlExpiryMs must be in [500,5000]" }
        require(maxTrackedFrames > staleFrameThreshold) {
            "maxTrackedFrames must exceed staleFrameThreshold or fresh frames get evicted"
        }
    }
}

data class FrameStamp(
    val frameSeq: Long,
    val geometry: FrameGeometry,
    val sentAtMs: Long,
)

sealed interface FrameFreshness {
    data class Fresh(val stamp: FrameStamp) : FrameFreshness

    data class StaleWatermark(val frameSeq: Long, val latestFrameSeq: Long, val threshold: Int) : FrameFreshness

    data class ExpiredTtl(val frameSeq: Long, val ageMs: Long?, val ttlMs: Long) : FrameFreshness
}
