package com.company.cloudctl.companion.observation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * K11 consumer obligation / §6 frozen counter-example — banner displacement:
 * a 96px banner appears, every business bound shifts down, the WHOLE-tree
 * digest changes, yet there is NO progress. The replay feeds frames
 * [1, 2, 2]: business digest (banner layer excluded, displacement
 * normalized) stays equal, the no-progress limit trips, and the loop exits
 * NO_PROGRESS with zero side effects. Budget exhaustion fail-closes with
 * LOCATOR_TIMEOUT instead of trying anything dangerous.
 */
class BannerDisplacementReplayTest {

    private fun outcome() = ObservationReplayer.replayPoll(
        FixturePaths.classpathUiReplay("replay/b12-banner-displacement.json"),
    )

    @Test
    fun treeDigestChangesWhileBusinessDigestDoesNot() {
        val poll = outcome()
        assertEquals(3, poll.frameTreeDigests.size) // feed [1, 2, 2]
        assertNotEquals(poll.frameTreeDigests[0], poll.frameTreeDigests[1])
        assertEquals(poll.frameBusinessDigests[0], poll.frameBusinessDigests[1])
        assertEquals(poll.frameBusinessDigests[1], poll.frameBusinessDigests[2])
    }

    @Test
    fun bannerDisplacementExitsNoProgressWithZeroSideEffects() {
        val poll = outcome()
        assertEquals(PollTerminal.NO_PROGRESS, poll.terminal)
        assertEquals(3, poll.attemptsUsed) // noProgressLimit=3 from the fixture budget
        assertEquals(0, poll.sideEffects)
    }

    @Test
    fun expectationsFromDerivedAndContractFixturesHold() {
        val fixture = org.json.JSONObject(
            FixturePaths.classpathUiReplay("replay/b12-banner-displacement.json"),
        )
        val expect = fixture.getJSONObject("expect")
        assertEquals("NO_PROGRESS", expect.getString("result"))
        assertEquals(20, expect.getJSONObject("pollingBudget").getInt("maxAttempts"))
        assertEquals(3, expect.getJSONObject("pollingBudget").getInt("noProgressLimit"))
        // The contract fixture pins the same budget shape and the same
        // after-limit behaviour (NO_PROGRESS, zero side effects).
        val contractBanner = org.json.JSONObject(
            FixturePaths.repoContractFixture("k11-negative-banner-displacement.json").readText(),
        )
        assertEquals(
            contractBanner.getJSONObject("expect").getJSONObject("pollingBudget").toString(),
            expect.getJSONObject("pollingBudget").toString(),
        )
        assertTrue(
            contractBanner.getJSONObject("expect").getString("afterLimit").contains("零副作用"),
        )
    }

    @Test
    fun budgetExhaustionFailClosesWithLocatorTimeout() {
        // Progressing business digests keep resetting the no-progress counter;
        // the attempt budget then expires -> LOCATOR_TIMEOUT, no fallback.
        val monitor = NoProgressMonitor(PollingBudget(maxAttempts = 2, minIntervalMs = 0, noProgressLimit = 3))
        assertEquals(PollTerminal.CONTINUE, monitor.observe("d1", sessionEpoch = 5))
        assertEquals(PollTerminal.CONTINUE, monitor.observe("d2", sessionEpoch = 5))
        assertEquals(PollTerminal.LOCATOR_TIMEOUT, monitor.observe("d3", sessionEpoch = 5))
        assertEquals(0, monitor.sideEffectsPerformed)
    }

    @Test
    fun identicalWholeTreesAlsoTripNoProgress() {
        // §6 baseline rule: identical treeDigest (same business digest, same
        // epoch) counts as no progress too.
        val monitor = NoProgressMonitor(PollingBudget(maxAttempts = 10, minIntervalMs = 0, noProgressLimit = 2))
        assertEquals(PollTerminal.CONTINUE, monitor.observe("same", sessionEpoch = 1))
        assertEquals(PollTerminal.NO_PROGRESS, monitor.observe("same", sessionEpoch = 1))
    }

    @Test
    fun crossEpochFramesAreNeverComparedForProgress() {
        // Same digest but a different sessionEpoch each frame: the counter
        // must reset (§2/§6) — "no progress" across epochs is meaningless.
        val monitor = NoProgressMonitor(PollingBudget(maxAttempts = 10, minIntervalMs = 0, noProgressLimit = 2))
        assertEquals(PollTerminal.CONTINUE, monitor.observe("same", sessionEpoch = 1))
        assertEquals(PollTerminal.CONTINUE, monitor.observe("same", sessionEpoch = 2))
        assertEquals(PollTerminal.CONTINUE, monitor.observe("same", sessionEpoch = 3))
    }

    @Test
    fun monitorRefusesToRunAfterAnySideEffect() {
        val monitor = NoProgressMonitor(PollingBudget(maxAttempts = 10, minIntervalMs = 0, noProgressLimit = 2))
        monitor.observe("d", 1)
        monitor.markSideEffect()
        val error = kotlin.test.assertFailsWith<IllegalStateException> { monitor.observe("d", 1) }
        assertTrue("side effect" in error.message.orEmpty())
    }

    @Test
    fun businessDigestIgnoresExcludedLayersAndNormalizesDisplacement() {
        val fixture = org.json.JSONObject(
            FixturePaths.classpathUiReplay("replay/b12-banner-displacement.json"),
        )
        val frames = fixture.getJSONArray("frames")
        val frame1 = frames.getJSONObject(0)
        val frame2 = frames.getJSONObject(1)
        val digest1 = ObservationReplayer.businessDigest(
            Observation.fromJson(frame1.getJSONObject("observation")),
            frame1.getJSONArray("excludedLayerResourceIds").let { List(it.length()) { i -> it.getString(i) } }.toSet(),
            frame1.getInt("displacementY"),
        )
        val digest2 = ObservationReplayer.businessDigest(
            Observation.fromJson(frame2.getJSONObject("observation")),
            frame2.getJSONArray("excludedLayerResourceIds").let { List(it.length()) { i -> it.getString(i) } }.toSet(),
            frame2.getInt("displacementY"),
        )
        assertEquals(digest1, digest2)
        // Without displacement normalization the raw business trees differ.
        val raw2 = ObservationReplayer.businessDigest(
            Observation.fromJson(frame2.getJSONObject("observation")),
            emptySet(),
            0,
        )
        assertNotEquals(digest1, raw2)
    }
}
