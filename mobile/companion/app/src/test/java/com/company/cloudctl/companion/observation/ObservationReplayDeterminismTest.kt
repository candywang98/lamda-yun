package com.company.cloudctl.companion.observation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * B12 acceptance case 1 — replay determinism: the same fixture always yields
 * the same outcome (pure replay, no clock/randomness/device), across both
 * fixture access paths (classpath mirror and repo-root canonical copy).
 */
class ObservationReplayDeterminismTest {

    private fun locateFixture() = FixturePaths.classpathUiReplay("replay/b12-fullheight-wrapper.json")

    @Test
    fun replayingTheSameLocateFixtureAlwaysYieldsTheSameOutcome() {
        val first = ObservationReplayer.replayLocate(locateFixture())
        repeat(5) {
            assertEquals(first, ObservationReplayer.replayLocate(locateFixture()))
        }
    }

    @Test
    fun replayingTheSamePollFixtureAlwaysYieldsTheSameOutcome() {
        val fixture = FixturePaths.classpathUiReplay("replay/b12-banner-displacement.json")
        val first = ObservationReplayer.replayPoll(fixture)
        repeat(5) {
            assertEquals(first, ObservationReplayer.replayPoll(fixture))
        }
    }

    @Test
    fun classpathMirrorAndRepoRootFixtureReplayIdentically() {
        for (name in FixturePaths.replayFixtureNames) {
            val fromClasspath = FixturePaths.classpathUiReplay("replay/$name")
            val fromRepo = FixturePaths.repoUiReplay("replay/$name").readText()
            if (name == "b12-banner-displacement.json") {
                assertEquals(
                    ObservationReplayer.replayPoll(fromClasspath),
                    ObservationReplayer.replayPoll(fromRepo),
                )
            } else {
                assertEquals(
                    ObservationReplayer.replayLocate(fromClasspath),
                    ObservationReplayer.replayLocate(fromRepo),
                )
            }
        }
    }

    @Test
    fun pinnedDigestsAreRecomputedNeverTrusted() {
        val outcome = ObservationReplayer.replayLocate(locateFixture())
        assertTrue(outcome.pinnedDigestMatches)
        // Tamper the pin: replay must surface the mismatch instead of replaying.
        val tampered = org.json.JSONObject(locateFixture())
            .getJSONObject("observation").put("treeDigest", "0".repeat(64))
        val tamperedText = org.json.JSONObject(locateFixture())
            .put("observation", tampered).toString()
        val bad = ObservationReplayer.replayLocate(tamperedText)
        assertFalse(bad.pinnedDigestMatches)
        assertNotEquals(outcome.recomputedTreeDigest, "0".repeat(64))
        // Resolution itself is unaffected: identity comes from the nodes.
        assertEquals(outcome.resolution, bad.resolution)
    }

    @Test
    fun replayRejectsFixtureFromAnotherContract() {
        val foreign = org.json.JSONObject(locateFixture()).put("contract", "ui-observation/v0@deadbeef")
        assertFailsWithMessage("contract") { ObservationReplayer.replayLocate(foreign.toString()) }
    }

    @Test
    fun everyReplayObservationIsDigestSelfConsistent() {
        for (name in listOf("b12-samename-ambiguous.json", "b12-fullheight-wrapper.json")) {
            val outcome = ObservationReplayer.replayLocate(FixturePaths.classpathUiReplay("replay/$name"))
            assertTrue(outcome.pinnedDigestMatches, "$name pinned treeDigest mismatch")
        }
        val poll = ObservationReplayer.replayPoll(FixturePaths.classpathUiReplay("replay/b12-banner-displacement.json"))
        assertEquals(3, poll.frameTreeDigests.size) // feed [1, 2, 2]: frame 2 polled twice
    }

    private inline fun assertFailsWithMessage(expected: String, block: () -> Unit) {
        val error = kotlin.test.assertFailsWith<IllegalArgumentException>(block = block)
        assertTrue(expected in error.message.orEmpty(), "expected '$expected' in: ${error.message}")
    }
}
