package com.company.cloudctl.companion.live

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * L11 requirement 2: per-frame geometry metadata and freshness validation
 * (K13 §3 geometry re-delivery + §4 watermark/TTL rules, device mirror of
 * fleet_live.check_input).
 */
class FrameLedgerTest {
    private val portrait = FrameGeometry(405, 720, 1080, 1920, 0)
    private val rotated = FrameGeometry(720, 405, 1920, 1080, 90)

    private class ManualClock(var now: Long = 0L) {
        fun advance(ms: Long) {
            now += ms
        }
    }

    @Test
    fun frameSeqIsMonotonicAndStampsCarryGeometry() {
        val clock = ManualClock()
        val ledger = FrameLedger()
        val first = ledger.recordNext(portrait, clock.now)
        clock.advance(100)
        val second = ledger.recordNext(portrait, clock.now)
        clock.advance(100)
        val third = ledger.recordNext(rotated, clock.now) // rotation mid-session

        assertEquals(1, first.frameSeq)
        assertEquals(2, second.frameSeq)
        assertEquals(3, third.frameSeq)
        assertEquals(3, ledger.latestFrameSeq)
        assertTrue(third.sentAtMs > second.sentAtMs)

        // The input is validated against the geometry of the frame it named:
        // a click aimed at the pre-rotation frame uses the pre-rotation
        // tables even after the display turned (K13 §3: geometry changes
        // take effect from the NEW frameSeq — old frames keep theirs).
        val freshOnOld = assertIs<FrameFreshness.Fresh>(ledger.checkFreshness(2, clock.now))
        assertEquals(portrait, freshOnOld.stamp.geometry)
        val freshOnNew = assertIs<FrameFreshness.Fresh>(ledger.checkFreshness(3, clock.now))
        assertEquals(rotated, freshOnNew.stamp.geometry)
    }

    @Test
    fun watermarkStalenessRejectsOldFrames() {
        val clock = ManualClock()
        val ledger = FrameLedger() // default threshold 10
        repeat(12) { ledger.recordNext(portrait, clock.now) }
        // latest=12, frameSeq=1: 12-1=11 > 10 -> stale (K13 §4 rule 2).
        val stale = assertIs<FrameFreshness.StaleWatermark>(ledger.checkFreshness(1, clock.now))
        assertEquals(11, stale.latestFrameSeq - stale.frameSeq)
        assertEquals(10, stale.threshold)
        // frameSeq=2: 12-2=10 is NOT > 10 -> falls through to the TTL check.
        assertIs<FrameFreshness.Fresh>(ledger.checkFreshness(2, clock.now))
    }

    @Test
    fun ttlExpiryRejectsAgedFrames() {
        val clock = ManualClock()
        val ledger = FrameLedger()
        val stamp = ledger.recordNext(portrait, clock.now)
        clock.advance(1_999)
        assertIs<FrameFreshness.Fresh>(ledger.checkFreshness(stamp.frameSeq, clock.now))
        clock.advance(2) // 2001 > 2000ms TTL
        val expired = assertIs<FrameFreshness.ExpiredTtl>(ledger.checkFreshness(stamp.frameSeq, clock.now))
        assertEquals(2_001, expired.ageMs)
        assertEquals(2_000, expired.ttlMs)
    }

    @Test
    fun unknownFrameSeqIsExpired() {
        val ledger = FrameLedger()
        val expired = assertIs<FrameFreshness.ExpiredTtl>(ledger.checkFreshness(999, nowMs = 0))
        assertEquals(null, expired.ageMs)
    }

    @Test
    fun evictedFramesNeverPassAsFresh() {
        val clock = ManualClock()
        val ledger = FrameLedger(FramePolicy(staleFrameThreshold = 2, ttlExpiryMs = 5_000, maxTrackedFrames = 4))
        repeat(10) { ledger.recordNext(portrait, clock.now) }
        assertEquals(4, ledger.stamps().size) // ring eviction bound
        // frameSeq=6 was evicted; rule 2 (watermark) fires before the
        // unknown-stamp TTL branch, mirroring fleet_live.check_input order.
        // Either way: never Fresh.
        val verdict = ledger.checkFreshness(6, clock.now)
        assertTrue(verdict !is FrameFreshness.Fresh)
        assertTrue(verdict is FrameFreshness.StaleWatermark)
        // A tracked in-window frame is still fresh here (rule order matters:
        // TTL only applies to stamps the watermark admitted).
        assertIs<FrameFreshness.Fresh>(ledger.checkFreshness(9, clock.now))
    }

    @Test
    fun policyValidatesContractClosedRanges() {
        assertFailsWith<IllegalArgumentException> { FramePolicy(staleFrameThreshold = 0) }
        assertFailsWith<IllegalArgumentException> { FramePolicy(staleFrameThreshold = 31) }
        assertFailsWith<IllegalArgumentException> { FramePolicy(ttlExpiryMs = 499) }
        assertFailsWith<IllegalArgumentException> { FramePolicy(ttlExpiryMs = 5_001) }
    }
}
